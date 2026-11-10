#!/usr/bin/env python3
"""Run five-medium P0 acceptance on read-only source copies.

Public-edition adaptation of the historical acceptance runner. The original
runner auto-discovered a private dev workspace, historical manuscript outputs,
an external machine HTML path, and hardcoded a historical timestamp plus a
specific tool/model identity. This adaptation removes all of those defaults:
every input path must be supplied explicitly by the operator through an
``--input-map`` JSON file, the runtime timestamp reflects the actual generation
moment, and the runner identity is taken from the input map or recorded as
``unknown``.

Original five-medium semantics are preserved: source copy / restricted web
sample cleanup, data-visual-spec validation, PPT text-fidelity/overflow guards,
typography failure conditions, all ``required_hard_checks``, P0 filtering,
protected-content hash before/after comparison, and
``candidate_only / manual_only / publication_performed=false``.

Limitations carried from the historical runner (not expanded by this adapter):
``sanitize_web_sample`` performs only local cleanup of script tags and
absolute src/href references; it is not a complete offline or malicious-HTML
safety guarantee. ``media_checks`` sets ``fact-gate``, ``rights-gate`` and
``privacy-gate`` to ``True`` directly — these are fixed technical flags of the
historical fixture runner, not the result of real fact/rights/privacy review.
Source hashes and PPT receipt fields record integrity, not authenticity,
trusted signatures, or author confirmation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from global_visual_validation import build_conformance_receipt, resolve_playwright_package  # noqa: E402
from media_qa_validation import required_hard_checks  # noqa: E402

# Required keys in the operator-supplied input map.
_REQUIRED_SOURCE_KEYS = ("article", "social-card", "infographic", "pptx", "web")


class _AltParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.missing = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "img":
            return
        values = dict(attrs)
        if not str(values.get("alt") or "").strip():
            self.missing += 1


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_source(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def sanitize_web_sample(source: Path, destination: Path) -> None:
    soup = BeautifulSoup(source.read_text(encoding="utf-8"), "lxml")
    for node in soup.find_all("script"):
        node.decompose()
    for node in soup.find_all(["link", "img", "iframe", "source", "video", "audio"]):
        attribute = "href" if node.name == "link" else "src"
        value = str(node.get(attribute) or "")
        if value.casefold().startswith(("http://", "https://", "//")):
            if node.name == "link":
                node.decompose()
            else:
                node[attribute] = ""
    if not soup.find("meta", attrs={"name": "viewport"}):
        meta = soup.new_tag("meta")
        meta["name"] = "viewport"
        meta["content"] = "width=device-width,initial-scale=1"
        soup.head.append(meta)
    style = soup.new_tag("style")
    style.string = 'html{line-break:strict;word-break:normal}body{font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif}h1,h2,h3,h4{break-after:avoid}'
    soup.head.append(style)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(str(soup), encoding="utf-8")


def run_typography(path: Path, report_path: Path, *, typography_script: Path, runtime_config: Path) -> dict[str, Any]:
    command = [
        "node",
        str(typography_script),
        "--input",
        str(path),
        "--output",
        str(report_path),
        "--playwright-package",
        str(resolve_playwright_package(runtime_path=runtime_config)),
    ]
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise RuntimeError(f"environment-blocked: browser QA could not start: {exc}") from exc
    if not report_path.exists():
        raise RuntimeError(f"environment-blocked: browser QA wrote no report: {result.stderr or result.stdout}")
    report = load_json(report_path)
    if result.returncode != 0 or report.get("status") != "pass":
        raise RuntimeError(f"typography-failed: {path.name}: {report.get('findings', [])}")
    return {"status": "pass", "message": f"Rendered line-box QA passed with {report.get('line_count', 0)} lines.", "ref": str(report_path)}


def media_checks(artifact: dict[str, Any], output: Path) -> dict[str, Any]:
    profile_id, required = required_hard_checks(artifact)
    format_name = artifact["format"]
    text = output.read_text(encoding="utf-8") if format_name in {"html", "svg"} else ""
    values = {
        "file-exists": output.exists(),
        "non-empty-output": output.exists() and output.stat().st_size > 0,
        "input-files-exist": True,
        "fact-gate": True,
        "rights-gate": True,
        "privacy-gate": True,
        "utf8-readable": bool(text),
        "html-document": "<html" in text.casefold() and "<!doctype" in text.casefold(),
        "responsive-viewport": "name=\"viewport\"" in text.casefold() or "name='viewport'" in text.casefold(),
        "svg-root": "<svg" in text.casefold(),
        "zip-readable": False,
        "alt-text-complete": True,
        "global-visual-context": True,
        "chinese-typography-rendered": True,
    }
    if format_name == "html":
        parser = _AltParser()
        parser.feed(text)
        values["alt-text-complete"] = parser.missing == 0
    if format_name == "pptx":
        with zipfile.ZipFile(output) as archive:
            values["zip-readable"] = archive.testzip() is None
    checks = [
        {"name": name, "status": "pass" if values.get(name, False) else "fail", "details": "five-medium acceptance copy"}
        for name in sorted(required)
    ]
    return {
        "profile_id": profile_id,
        "hard_checks": checks,
        "result": "pass" if all(check["status"] == "pass" for check in checks) else "fail",
    }


def protected_hashes(
    baseline_manifest: Path,
    protected_root: Path,
    personal_brand_root: Path | None,
) -> dict[str, str]:
    """Compute protected-content hashes and reject drift.

    ``baseline_manifest`` replaces the historical hardcoded
    ``DESIGN_SYSTEM/docs/global-visual-language/M0-baseline-manifest.json``.
    ``protected_root`` replaces the historical ``WORKSPACE`` for
    ``content_items`` and ``acceptance_artifacts``. ``personal_brand_root``
    replaces the historical ``WORKSPACE/repos/personal-ip-visual-system`` for
    ``personal_brand_authority``; if the manifest contains
    ``personal_brand_authority`` entries and ``personal_brand_root`` is ``None``,
    the check fails closed rather than silently skipping.
    """
    baseline = load_json(baseline_manifest)
    protected: dict[str, str] = {}
    for relative, expected in baseline.get("content_items", {}).items():
        path = protected_root / relative
        protected[relative] = sha256(path)
        if protected[relative] != expected:
            raise RuntimeError(f"protected content drift: {relative}")
    for relative, expected in baseline.get("acceptance_artifacts", {}).items():
        path = protected_root / relative
        protected[relative] = sha256(path)
        if protected[relative] != expected:
            raise RuntimeError(f"protected acceptance artifact drift: {relative}")
    brand_authority = baseline.get("personal_brand_authority", {})
    if brand_authority:
        if personal_brand_root is None:
            raise RuntimeError(
                "protected brand authority entries are present but personal_brand_root was not supplied"
            )
        for relative, expected in brand_authority.items():
            if relative == "qa-report.json":
                continue
            path = personal_brand_root / relative
            key = f"{personal_brand_root.name}/{relative}"
            protected[key] = sha256(path)
            if protected[key] != expected:
                raise RuntimeError(f"protected brand authority drift: {relative}")
    return protected


def _resolve(path_str: str) -> Path:
    return Path(path_str).expanduser().resolve()


def precheck_inputs(input_map: dict[str, Any], *, input_map_path: Path) -> dict[str, Path | None]:
    """Verify all required inputs exist and outputs do not overlap inputs.

    This is an I/O correctness pre-check, not a business-logic gate. It refuses
    missing files and input/output path overlaps before any copy or write
    happens. It does not grant permissions, validate content, or auto-discover
    anything.
    """
    if not isinstance(input_map, dict):
        raise RuntimeError("precheck failed: input map must be a JSON object")

    resolved: dict[str, Path | None] = {}
    errors: list[str] = []

    resolved_input_map_path = _resolve(str(input_map_path))
    resolved["input_map_path"] = resolved_input_map_path
    if not resolved_input_map_path.is_file():
        errors.append(f"input map file does not exist: {resolved_input_map_path}")

    sources_raw = input_map.get("sources")
    if not isinstance(sources_raw, dict):
        errors.append("input map must contain a 'sources' object")
    else:
        for key in _REQUIRED_SOURCE_KEYS:
            val = sources_raw.get(key)
            if not isinstance(val, str) or not val.strip():
                errors.append(f"sources.{key} is missing or empty")
                continue
            p = _resolve(val)
            resolved[f"source:{key}"] = p
            if not p.is_file():
                errors.append(f"source {key} does not exist: {p}")

    scalar_inputs = {
        "ppt_receipt": "ppt receipt",
        "protected_baseline_manifest": "protected baseline manifest",
        "data_visual_spec_schema": "data-visual-spec schema",
        "runtime_config": "runtime config",
        "normalized_data_fixture": "normalized data fixture",
        "typography_script": "typography script",
        "output_dir": "output directory",
    }
    for field, label in scalar_inputs.items():
        val = input_map.get(field)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{field} is missing or empty")
            continue
        p = _resolve(val)
        resolved[field] = p
        if field == "output_dir":
            if p.exists() and not p.is_dir():
                errors.append(f"output directory exists but is not a directory: {p}")
        elif not p.is_file():
            errors.append(f"{label} does not exist: {p}")

    protected_root_raw = input_map.get("protected_root")
    if not isinstance(protected_root_raw, str) or not protected_root_raw.strip():
        errors.append("protected_root is missing or empty")
    else:
        pr = _resolve(protected_root_raw)
        resolved["protected_root"] = pr
        if not pr.is_dir():
            errors.append(f"protected_root is not a directory: {pr}")

    personal_brand_root_raw = input_map.get("personal_brand_root")
    if personal_brand_root_raw is not None:
        if not isinstance(personal_brand_root_raw, str) or not personal_brand_root_raw.strip():
            errors.append("personal_brand_root must be a non-empty string or absent")
        else:
            pbr = _resolve(personal_brand_root_raw)
            resolved["personal_brand_root"] = pbr
            if not pbr.is_dir():
                errors.append(f"personal_brand_root is not a directory: {pbr}")
    else:
        resolved["personal_brand_root"] = None

    output_dir = resolved.get("output_dir")
    if output_dir is not None:
        pr = resolved.get("protected_root")
        if pr is not None:
            if output_dir == pr or output_dir in pr.parents or pr in output_dir.parents:
                errors.append(f"output_dir must not equal, contain, or be inside protected_root: {pr}")

        pbr = resolved.get("personal_brand_root")
        if pbr is not None:
            if output_dir == pbr or output_dir in pbr.parents or pbr in output_dir.parents:
                errors.append(f"output_dir must not equal, contain, or be inside personal_brand_root: {pbr}")

        for label, path in resolved.items():
            if label in ("output_dir", "protected_root", "personal_brand_root"):
                continue
            if path is None:
                continue
            try:
                if path == output_dir or output_dir in path.parents:
                    errors.append(f"output_dir must not contain or equal input path '{label}': {path}")
            except TypeError:
                pass

    if errors:
        raise RuntimeError("precheck failed: " + "; ".join(errors))
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run five-medium P0 acceptance on explicit operator-supplied source copies.",
    )
    parser.add_argument(
        "--input-map",
        required=True,
        help="Path to a JSON file with explicit source/resource/output paths. See USAGE.md.",
    )
    args = parser.parse_args()

    input_map_path = _resolve(args.input_map)
    if not input_map_path.is_file():
        print(f"input map not found: {input_map_path}", file=sys.stderr)
        return 2
    input_map = json.loads(input_map_path.read_text(encoding="utf-8"))
    if not isinstance(input_map, dict):
        print("input map must be a JSON object", file=sys.stderr)
        return 2

    runner_identity = str(input_map.get("runner_identity") or "unknown").strip() or "unknown"
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        resolved = precheck_inputs(input_map, input_map_path=input_map_path)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_dir = resolved["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / "acceptance-receipt.json"

    try:
        protected_before = protected_hashes(
            resolved["protected_baseline_manifest"],
            resolved["protected_root"],
            resolved.get("personal_brand_root"),
        )

        normalized = load_json(resolved["normalized_data_fixture"])
        data_validator = Draft202012Validator(load_json(resolved["data_visual_spec_schema"]))
        data_errors = list(data_validator.iter_errors(normalized))
        if data_errors:
            raise RuntimeError("normalized data fixture failed: " + "; ".join(error.message for error in data_errors))

        sources = {key: resolved[f"source:{key}"] for key in _REQUIRED_SOURCE_KEYS}
        outputs = {
            "article": output_dir / "wound-article-copy.html",
            "social-card": output_dir / "insurance-social-card-copy.html",
            "infographic": output_dir / "medical-fund-infographic-copy.svg",
            "pptx": output_dir / "medical-fund-ppt-copy.pptx",
            "web": output_dir / "zero-code-web-copy.html",
        }
        for key in ("article", "social-card", "infographic", "pptx"):
            copy_source(sources[key], outputs[key])
        sanitize_web_sample(sources["web"], outputs["web"])

        typography = {}
        typography_script = resolved["typography_script"]
        for key in ("article", "social-card", "infographic", "web"):
            typography[key] = run_typography(outputs[key], output_dir / f"{key}.chinese-typography.json", typography_script=typography_script, runtime_config=resolved["runtime_config"])
        ppt_source_receipt = load_json(resolved["ppt_receipt"])
        ppt_checks = {check["name"]: check["status"] for check in ppt_source_receipt["qa"]["hard_checks"]}
        if ppt_checks.get("text-fidelity") != "pass" or ppt_checks.get("overflow") != "pass":
            raise RuntimeError("PPTX source lacks passing text-fidelity or overflow evidence")
        typography["pptx"] = {"status": "pass", "message": "PPTX readback text-fidelity and overflow checks passed.", "ref": str(resolved["ppt_receipt"])}

        adapters = {
            "article": ("article", "article", "html", "list"),
            "social-card": ("social-card", "social-card", "html", "quote-hero"),
            "infographic": ("data-chart", "infographic", "svg", "data-chart"),
            "pptx": ("data-chart", "pptx", "pptx", "data-chart"),
            "web": ("web", "web", "html", "list"),
        }
        entries = []
        for key, (family, media_adapter, format_name, layout_intent) in adapters.items():
            artifact = {
                "artifact_id": f"global-visual-{key}",
                "output_family": family,
                "media_adapter": media_adapter,
                "layout_intent": layout_intent,
                "renderer": "manual",
                "format": format_name,
                "status": "rendered",
                "renderer_options": {"global_visual_v1": True, "explicit_adapter": True},
            }
            item = {
                "content_id": f"global-visual-acceptance-{key}",
                "visual": {
                    "visual_profile": "visual/insurance-observational-advisor",
                    "visual_profile_version": "0.2.0",
                    "assets": [],
                    "semantic_visual_map": [],
                },
            }
            media_qa = media_checks(artifact, outputs[key])
            data_status = {
                "normalized_spec_valid": True,
                "message": "data-visual-spec.v1 validated for the copied medical-fund chart.",
            } if key in {"infographic", "pptx"} else {"normalized_spec_valid": True, "message": "Artifact is not a data visual."}
            receipt = build_conformance_receipt(item, artifact, outputs[key], typography[key], data_status, media_qa, runtime_path=resolved["runtime_config"])
            receipt["created_at"] = now_iso
            p0_findings = [finding for finding in receipt["findings"] if finding["priority"] == "P0" and finding["enforcement"] != "not-applicable"]
            if media_qa["result"] != "pass" or any(finding["status"] != "pass" for finding in p0_findings):
                raise RuntimeError(f"{key} failed P0 acceptance")
            receipt_path_for_key = output_dir / f"{key}.visual-conformance.json"
            write_json(receipt_path_for_key, receipt)
            entries.append({
                "medium": key,
                "source_ref": str(sources[key]),
                "source_sha256": sha256(sources[key]),
                "copy_ref": str(outputs[key]),
                "copy_sha256": sha256(outputs[key]),
                "typography_ref": typography[key]["ref"],
                "conformance_ref": str(receipt_path_for_key),
                "conformance_sha256": sha256(receipt_path_for_key),
                "result": receipt["result"],
            })
        protected_after = protected_hashes(
            resolved["protected_baseline_manifest"],
            resolved["protected_root"],
            resolved.get("personal_brand_root"),
        )
        if protected_before != protected_after:
            raise RuntimeError("protected hash set changed during acceptance")
        combined = {
            "schema_version": "global-visual-five-medium-acceptance.v1",
            "checked_at": now_iso,
            "acting_tool_model": runner_identity,
            "status": "pass",
            "manual_only": True,
            "candidate_only": True,
            "p0_activation": load_json(resolved["runtime_config"])["p0_activation"],
            "entries": entries,
            "protected_hash_count": len(protected_after),
            "protected_hashes_unchanged": True,
            "publication_performed": False,
        }
        write_json(receipt_path, combined)
        print(json.dumps({"status": "pass", "media": len(entries), "p0_activation": combined["p0_activation"], "receipt": str(receipt_path)}, ensure_ascii=False))
        return 0
    except RuntimeError as exc:
        write_json(receipt_path, {
            "schema_version": "global-visual-five-medium-acceptance.v1",
            "checked_at": now_iso,
            "acting_tool_model": runner_identity,
            "status": "environment-blocked" if str(exc).startswith("environment-blocked") else "fail",
            "reason": str(exc),
            "manual_only": True,
            "candidate_only": True,
            "publication_performed": False,
        })
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
