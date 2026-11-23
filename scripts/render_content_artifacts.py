#!/usr/bin/env python3
"""Plan, render, and validate one explicitly selected content artifact.

Public-source candidate: filesystem roots come from the public ``studio_paths``
module, external runtimes are resolved only from explicit environment variables,
and the held ``render_data_explanations`` backend is imported lazily only inside
the data-explanation renderer. All original renderer branches, QA profiles,
policy guards, retry limits and receipt metadata are retained.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator
from markdown_it import MarkdownIt
from PIL import Image
import yaml


_PUBLIC_SCRIPTS = Path(__file__).resolve().parent
if str(_PUBLIC_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_PUBLIC_SCRIPTS))

from studio_paths import SOURCE_ROOT, STUDIO_ROOT  # noqa: E402

from article_visual_validation import validate_article_visual_plan  # noqa: E402
from article_visual_pipeline import insert_selected_visuals, render_article_html  # noqa: E402
from design_direction_validation import validate_design_direction  # noqa: E402
from media_qa_validation import required_hard_checks  # noqa: E402
from social_card_runtime import (  # noqa: E402
    SocialCardRuntimeError as ArtifactError,
    resolve_external_file_from_env,
    validate_social_card_html_source,
)
from ppt_master_data_projection import (  # noqa: E402
    ProjectionError,
    materialize_project as materialize_ppt_data_project,
)
from render_artifact_validation import (  # noqa: E402
    resolve_local_ref,
    validate_render_artifacts,
)
from semantic_visual_validation import validate_semantic_visual_map  # noqa: E402
from slot_budget_validation import validate_antv_budget, validate_marp_budget  # noqa: E402
from visual_asset_routing import (  # noqa: E402
    is_ai_image_generation_authorized,
    validate_ai_image_generation_opt_in,
)
from global_visual_validation import (  # noqa: E402
    build_conformance_receipt,
    build_runtime_context,
    is_global_visual_enabled,
    resolve_playwright_package,
    validate_global_visual_item,
)


STUDIO_SCRIPTS = _PUBLIC_SCRIPTS
SCHEMA_PATH = STUDIO_ROOT / "schemas" / "content-item.schema.json"
RENDERER_REGISTRY_PATH = STUDIO_ROOT / "config" / "renderer-registry.v1.json"
# Existing first-party format identifier taken from this module's original error
# text. It classifies receipt evidence metadata only; it never loads the backend.
DATA_SPEC_VERSION = "data-explanation-chart-spec.v1"
DEFAULT_BACKGROUND = "#F7F8F5"
MAX_RENDER_RETRIES = 2
RETRYABLE_QA_CHECKS = {
    "file-exists",
    "non-empty-output",
    "pixel-dimensions",
    "nonblank-pixels",
    "local-cjk-font",
    "no-remote-font-stylesheet",
}


class _ImageAltParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.missing_alt = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "img":
            return
        attributes = {name.casefold(): value for name, value in attrs}
        if "alt" not in attributes or not str(attributes.get("alt") or "").strip():
            self.missing_alt += 1


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as handle:
        handle.write(serialized)
        temporary = Path(handle.name)
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _percentage(value: float) -> str:
    return f"{round(value * 100, 3):g}%"


def _find_artifact(item: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    matches = [
        artifact
        for artifact in item.get("visual", {}).get("render_artifacts", [])
        if artifact.get("artifact_id") == artifact_id
    ]
    if not matches:
        raise ArtifactError(f"artifact {artifact_id!r} is not declared in visual.render_artifacts")
    if len(matches) > 1:
        raise ArtifactError(f"artifact {artifact_id!r} is duplicated")
    return matches[0]


def _ai_generation_authorized(item: dict[str, Any]) -> bool:
    return is_ai_image_generation_authorized(
        item.get("visual", {}).get("ai_image_generation", {})
    )


def _format_validation_errors(item: dict[str, Any], item_path: Path) -> list[str]:
    schema = _load_json(SCHEMA_PATH)
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for error in sorted(validator.iter_errors(item), key=lambda value: list(value.path)):
        location = ".".join(str(part) for part in error.path) or "$"
        errors.append(f"{location}: {error.message}")
    for check in (
        lambda: validate_semantic_visual_map(item, item_path),
        lambda: validate_article_visual_plan(item),
        lambda: validate_design_direction(item),
        lambda: validate_ai_image_generation_opt_in(item),
        lambda: validate_render_artifacts(item, item_path),
    ):
        errors.extend(f"{location}: {message}" for location, message in check())
    for artifact in item.get("visual", {}).get("render_artifacts", []):
        errors.extend(f"{location}: {message}" for location, message in validate_global_visual_item(item, artifact))
    return errors


def _global_visual_typography_qa(
    item: dict[str, Any],
    item_path: Path,
    artifact: dict[str, Any],
    output_path: Path,
    render_details: dict[str, Any],
) -> dict[str, Any]:
    if not is_global_visual_enabled(artifact, item):
        return {"status": "not-applicable", "message": "Legacy artifact does not activate global-visual-context.v1."}
    format_name = artifact.get("format")
    if format_name in {"html", "svg"}:
        report_path = output_path.with_suffix(output_path.suffix + ".chinese-typography.json")
        command = [
            "node",
            str(STUDIO_SCRIPTS / "chinese_typography_browser_qa.mjs"),
            "--input",
            str(output_path),
            "--output",
            str(report_path),
            "--playwright-package",
            str(resolve_playwright_package()),
        ]
        result = subprocess.run(command, cwd=STUDIO_ROOT, capture_output=True, text=True, check=False)
        if result.returncode not in {0, 2} or not report_path.exists():
            return {"status": "fail", "message": f"Rendered typography QA could not run: {result.stderr.strip() or result.stdout.strip()}"}
        report = _load_json(report_path)
        return {"status": report.get("status", "fail"), "message": f"Rendered line-box QA found {len(report.get('findings', []))} finding(s).", "ref": str(report_path)}
    if format_name in {"png", "jpg", "pdf"}:
        structural = [
            ref for ref in artifact.get("input_refs", [])
            if resolve_local_ref(ref, item_path).suffix.casefold() in {".html", ".svg", ".pptx"}
        ]
        return {"status": "pass" if structural else "fail", "message": "Raster/PDF output is bound to a structural source." if structural else "Raster/PDF output has no HTML, SVG, or PPTX structural source.", **({"ref": structural[0]} if structural else {})}
    if format_name == "pptx":
        passed = render_details.get("text_fidelity") is True and render_details.get("overflow") is True
        return {"status": "pass" if passed else "fail", "message": "PPTX typography reuses text-fidelity and overflow postflight evidence."}
    if format_name == "md":
        return {"status": "pass", "message": "Markdown remains structural text; rendered adapters must run their own line-box QA."}
    return {"status": "fail", "message": f"No Chinese typography QA adapter for format {format_name!r}."}


def _global_visual_data_status(artifact: dict[str, Any], item_path: Path) -> dict[str, Any]:
    if artifact.get("layout_intent") != "data-chart" and artifact.get("output_family") != "data-chart":
        return {"normalized_spec_valid": True, "message": "Artifact is not a data visual."}
    schema_path = STUDIO_ROOT / "visual-contracts" / "schemas" / "data-visual-spec.v1.schema.json"
    schema = _load_json(schema_path)
    validator = Draft202012Validator(schema)
    for ref in artifact.get("input_refs", []):
        path = resolve_local_ref(ref, item_path)
        if path.suffix.casefold() != ".json":
            continue
        try:
            payload = _load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("schema_version") != "data-visual-spec.v1":
            continue
        errors = list(validator.iter_errors(payload))
        if not errors:
            return {"normalized_spec_valid": True, "message": "data-visual-spec.v1 is valid."}
        return {"normalized_spec_valid": False, "message": "; ".join(error.message for error in errors)}
    return {"normalized_spec_valid": False, "message": "New data visuals require a data-visual-spec.v1 input; legacy specs remain compatibility-only."}


def _renderer_config(artifact: dict[str, Any]) -> dict[str, Any]:
    registry = _load_json(RENDERER_REGISTRY_PATH)
    renderer = artifact.get("renderer")
    config = registry.get("renderers", {}).get(renderer)
    if not config:
        raise ArtifactError(f"renderer {renderer!r} is not registered")

    policy = config.get("selection_policy")
    explicit = artifact.get("renderer_options", {}).get("explicit_adapter") is True
    if policy == "disabled":
        raise ArtifactError(f"renderer {renderer!r} is disabled: {config.get('reason', 'no reason recorded')}")
    if config.get("enabled") is not True:
        if policy != "explicit-item-only" or not explicit:
            raise ArtifactError(
                f"renderer {renderer!r} is off by default; this artifact must set "
                "renderer_options.explicit_adapter=true"
            )
    if policy == "explicit-item-only" and not explicit:
        raise ArtifactError(f"renderer {renderer!r} requires explicit artifact activation")
    if artifact.get("format") not in config.get("formats", []):
        raise ArtifactError(
            f"renderer {renderer!r} does not support format {artifact.get('format')!r}"
        )
    return config


def _preflight(item: dict[str, Any], item_path: Path, artifact: dict[str, Any]) -> None:
    if artifact.get("status") in {"blocked", "superseded"}:
        raise ArtifactError(f"artifact status {artifact.get('status')!r} cannot be rendered")

    _renderer_config(artifact)
    try:
        required_hard_checks(artifact)
    except ValueError as exc:
        raise ArtifactError(str(exc)) from exc
    gates = item.get("gates", {})
    for gate_name in ("rights", "privacy"):
        if gates.get(gate_name, {}).get("status") != "pass":
            raise ArtifactError(f"{gate_name} gate must pass before rendering")

    assets_by_id = {
        asset.get("asset_id"): asset
        for asset in item.get("visual", {}).get("assets", [])
        if asset.get("asset_id")
    }
    for asset_id in artifact.get("asset_ids", []):
        asset = assets_by_id.get(asset_id)
        if not asset:
            raise ArtifactError(f"artifact references unknown asset_id {asset_id!r}")
        if asset.get("rights_status") != "verified":
            raise ArtifactError(f"asset {asset_id!r} has unverified rights")
        if asset.get("privacy_status") in {"needs-review", "blocked"}:
            raise ArtifactError(f"asset {asset_id!r} has uncleared privacy status")

    for input_ref in artifact.get("input_refs", []):
        if not resolve_local_ref(input_ref, item_path).exists():
            raise ArtifactError(f"missing local input {input_ref!r}")

    if not artifact.get("ref"):
        raise ArtifactError("render requires artifact.ref as an explicit local output target")
    if not artifact.get("receipt_ref"):
        raise ArtifactError("render requires artifact.receipt_ref")

    if artifact.get("renderer") == "imagegen":
        if not _ai_generation_authorized(item):
            raise ArtifactError(
                "imagegen requires user-request evidence containing 模型生成图片 or AI 生图"
            )


def _discover_chromium() -> Path:
    return resolve_external_file_from_env(
        "PLAYWRIGHT_CHROMIUM_EXECUTABLE", "Playwright Chromium executable"
    )


def _discover_primary_runtime_python() -> Path:
    return resolve_external_file_from_env(
        "CODEX_PRIMARY_RUNTIME_PYTHON", "PPT visual validation Python runtime"
    )


def _run(
    command: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise ArtifactError(detail)
    return result


def _render_social_card(
    item: dict[str, Any], item_path: Path, artifact: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    inputs = artifact.get("input_refs", [])
    if len(inputs) != 1:
        raise ArtifactError("social-card requires exactly one local HTML input_ref")
    input_path = resolve_local_ref(inputs[0], item_path)
    if input_path.suffix.casefold() not in {".html", ".htm"}:
        raise ArtifactError("social-card input must be HTML")
    html_text = input_path.read_text(encoding="utf-8")
    theme = artifact.get("theme") or "default"
    if theme not in config.get("themes", ["default"]):
        raise ArtifactError(f"social-card theme {theme!r} is not registered")
    required_direction = None if theme == "default" else theme
    details = validate_social_card_html_source(html_text, required_direction)

    options = artifact.get("renderer_options", {})
    selector = options.get("card_selector", "section.poster")
    if selector != "section.poster":
        raise ArtifactError("social-card card_selector is fixed to 'section.poster' for DOM QA")
    card_index = options.get("card_index", 0)
    expected_count = options.get("expected_card_count")
    if not isinstance(card_index, int) or card_index < 0:
        raise ArtifactError("social-card card_index must be a non-negative integer")
    if expected_count is not None and (
        not isinstance(expected_count, int) or expected_count < 1
    ):
        raise ArtifactError("social-card expected_card_count must be a positive integer")
    qa_style = options.get("qa_style") or (
        "editorial" if theme == "reflective-personal-essay" else "swiss"
    )
    if qa_style not in {"editorial", "swiss"}:
        raise ArtifactError("social-card qa_style must be 'editorial' or 'swiss'")

    qa_config = config.get("external_qa", {})
    qa_entry = resolve_external_file_from_env(
        qa_config.get("entry_env"),
        "social-card external DOM QA entry",
        qa_config.get("entry_sha256"),
    )
    qa_env = os.environ.copy()
    qa_env["SOCIAL_CARD_BROWSER"] = str(_discover_chromium())
    qa_result = _run(
        ["node", str(qa_entry), str(input_path), f"--style={qa_style}"],
        cwd=qa_entry.parent,
        env=qa_env,
    )
    raw_summary = next(
        (line.strip() for line in qa_result.stdout.splitlines() if line.startswith("sections:")),
        "",
    )
    summary_match = re.search(
        r"sections:\s*(\d+).*?(\d+)\s+clean.*?(\d+)\s+fails.*?(\d+)\s+warns",
        raw_summary,
    )
    if not summary_match or int(summary_match.group(1)) == 0:
        raise ArtifactError("social-card external DOM QA did not inspect any boards")
    section_count, clean_count, fail_count, warning_count = (
        int(value) for value in summary_match.groups()
    )
    qa_summary = (
        f"sections={section_count}; clean={clean_count}; "
        f"fails={fail_count}; warns={warning_count}"
    )
    if fail_count:
        raise ArtifactError("social-card external DOM QA reported failed boards")

    output_path = resolve_local_ref(artifact["ref"], item_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_format = artifact.get("format")
    bridge_metrics: dict[str, Any] = {}
    typography_gate_config = config.get("typography_gate") or {}
    if not isinstance(typography_gate_config, dict):
        raise ArtifactError("social-card typography_gate contract must be an object")
    policy_path_raw = typography_gate_config.get("policy_path")
    policy_sha256 = typography_gate_config.get("policy_sha256")
    profile_id = typography_gate_config.get("profile_id")
    if not isinstance(policy_path_raw, str) or not policy_path_raw.strip():
        raise ArtifactError("social-card typography_gate.policy_path is required")
    if not isinstance(policy_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", policy_sha256):
        raise ArtifactError("social-card typography_gate.policy_sha256 must be a SHA-256 digest")
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise ArtifactError("social-card typography_gate.profile_id is required")
    typography_policy_path = Path(policy_path_raw).expanduser().resolve()
    if not typography_policy_path.is_file():
        raise ArtifactError(
            f"social-card canonical typography policy is missing: {typography_policy_path}"
        )
    if output_format == "html":
        if output_path.resolve() == input_path.resolve():
            raise ArtifactError("social-card renderer refuses to overwrite its source HTML")
        output_path.write_text(html_text, encoding="utf-8")
    elif output_format != "png":
        raise ArtifactError("social-card adapter supports HTML or PNG")

    if output_format in {"html", "png"}:
        bridge = STUDIO_ROOT / str(config.get("bridge", ""))
        if not bridge.is_file():
            raise ArtifactError("social-card repository Playwright bridge is missing")
        playwright_config = config.get("playwright_package") or {}
        if not isinstance(playwright_config, dict):
            raise ArtifactError("social-card Playwright package contract must be an object")
        playwright_package = resolve_external_file_from_env(
            playwright_config.get("env"), "social-card Playwright package.json"
        )
        try:
            package_metadata = _load_json(playwright_package)
        except (OSError, json.JSONDecodeError) as exc:
            raise ArtifactError("social-card Playwright package metadata is invalid") from exc
        if package_metadata.get("name") != "playwright":
            raise ArtifactError("social-card Playwright package must identify name=playwright")
        bridge_screenshot = (
            output_path
            if output_format == "png"
            else output_path.with_suffix(output_path.suffix + ".typography-gate-preview.png")
        )
        command = [
            "node",
            str(bridge),
            "--html",
            str(input_path),
            "--output",
            str(bridge_screenshot),
            "--selector",
            selector,
            "--card-index",
            str(card_index),
            "--chromium",
            str(_discover_chromium()),
            "--playwright-package",
            str(playwright_package),
            "--typography-policy",
            str(typography_policy_path),
            "--typography-profile",
            profile_id,
            "--typography-policy-sha256",
            policy_sha256.casefold(),
        ]
        if expected_count is not None:
            command.extend(["--expected-count", str(expected_count)])
        result = _run(command, cwd=STUDIO_ROOT)
        try:
            bridge_metrics = json.loads(result.stdout.strip())
        except json.JSONDecodeError as exc:
            raise ArtifactError("social-card bridge returned invalid JSON") from exc
    return {
        **details,
        "theme": theme,
        "qa_style": qa_style,
        "dom_qa_passed": True,
        "dom_qa_summary": qa_summary,
        "dom_qa_warning_count": warning_count,
        "external_qa_source_commit": qa_config.get("source_commit"),
        "external_qa_license": qa_config.get("license"),
        "card_count": bridge_metrics.get("card_count"),
        "card_overflow_px": bridge_metrics.get("overflow_px", 0),
        "minimum_font_px": bridge_metrics.get("minimum_font_px"),
        "font_gate": bridge_metrics.get("font_gate", {}),
        "blocked_remote_requests": bridge_metrics.get("blocked_remote_requests", []),
    }


def _read_antv_template(input_path: Path) -> str:
    for line in input_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            parts = stripped.split()
            if len(parts) == 2 and parts[0] == "infographic":
                return parts[1]
            break
    raise ArtifactError("AntV input must begin with 'infographic <template>'")


def _render_svg_with_chromium(
    svg_path: Path,
    output_path: Path,
    width: int,
    height: int,
    background: str,
) -> None:
    svg = svg_path.read_text(encoding="utf-8")
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <style>
    html, body {{ width: {width}px; height: {height}px; margin: 0; overflow: hidden; background: {html.escape(background)}; }}
    body {{ display: flex; align-items: center; justify-content: center; font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Source Han Sans SC", sans-serif; }}
    svg {{ display: block; width: calc(100% - 96px); height: calc(100% - 96px); max-width: calc(100% - 96px); max-height: calc(100% - 96px); }}
  </style>
</head>
<body>{svg}</body>
</html>
"""
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=output_path.parent, delete=False, suffix=".html"
    ) as handle:
        handle.write(document)
        html_path = Path(handle.name)
    try:
        chromium = _discover_chromium()
        _run(
            [
                str(chromium),
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=1000",
                "--force-device-scale-factor=1",
                f"--window-size={width},{height}",
                f"--screenshot={output_path}",
                html_path.resolve().as_uri(),
            ]
        )
    finally:
        html_path.unlink(missing_ok=True)


def _render_antv(
    item: dict[str, Any], item_path: Path, artifact: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    inputs = artifact.get("input_refs", [])
    if len(inputs) != 1:
        raise ArtifactError("antv-infographic requires exactly one .ifgc input_ref")
    input_path = resolve_local_ref(inputs[0], item_path)
    if input_path.suffix.lower() not in {".ifgc", ".txt", ".info"}:
        raise ArtifactError("antv-infographic input must be .ifgc, .txt, or .info")

    actual_template = _read_antv_template(input_path)
    declared_template = artifact.get("template")
    if not declared_template:
        raise ArtifactError("antv-infographic artifacts require a declared template")
    if actual_template != declared_template:
        raise ArtifactError(
            f"artifact template {declared_template!r} does not match input {actual_template!r}"
        )
    budget_errors = validate_antv_budget(input_path, actual_template, artifact["layout_intent"])
    if budget_errors:
        raise ArtifactError("AntV slot budget failed: " + "; ".join(budget_errors))

    local_path = Path(config["local_path"])
    cli = local_path / config["entry"]
    if not cli.exists():
        raise ArtifactError(f"missing fixed infographic-cli entry: {cli}")

    output_path = resolve_local_ref(artifact["ref"], item_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_format = artifact["format"]
    svg_path = output_path if output_format == "svg" else output_path.with_suffix(".intermediate.svg")
    command = ["node", str(cli), "-i", str(input_path), "-o", str(svg_path), "--quiet"]
    if artifact.get("theme"):
        command.extend(["--theme", artifact["theme"]])
    _run(command, cwd=local_path)

    svg_text = svg_path.read_text(encoding="utf-8")
    if output_format == "png":
        dimensions = artifact.get("dimensions") or {"width": 1080, "height": 1440}
        background = artifact.get("renderer_options", {}).get("background", DEFAULT_BACKGROUND)
        _render_svg_with_chromium(
            svg_path,
            output_path,
            int(dimensions["width"]),
            int(dimensions["height"]),
            str(background),
        )
        svg_path.unlink(missing_ok=True)

    return {"svg_text": svg_text, "template": actual_template, "slot_budget_valid": True}


def _render_html_playwright(
    item: dict[str, Any], item_path: Path, artifact: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    if artifact.get("media_adapter") != "article" or artifact.get("format") != "html":
        raise ArtifactError(
            "the unified html-playwright adapter currently supports article HTML only"
        )
    inputs = artifact.get("input_refs", [])
    if len(inputs) != 1:
        raise ArtifactError("article html-playwright requires exactly one Markdown input_ref")
    input_path = resolve_local_ref(inputs[0], item_path)
    if input_path.suffix.casefold() not in {".md", ".markdown"}:
        raise ArtifactError("article html-playwright input must be Markdown")

    output_path = resolve_local_ref(artifact["ref"], item_path)
    if output_path.suffix.casefold() != ".html":
        raise ArtifactError("article html-playwright output must end in .html")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_markdown = input_path.read_text(encoding="utf-8")
    enriched_markdown = insert_selected_visuals(item, source_markdown, output_path)
    theme = artifact.get("theme") or "default"
    allowed_themes = config.get("themes", ["default"])
    if theme not in allowed_themes:
        raise ArtifactError(
            f"html-playwright article theme must be one of {', '.join(allowed_themes)}"
        )
    output_path.write_text(
        render_article_html(
            enriched_markdown,
            str(item.get("title") or item["content_id"]),
            theme=theme,
            section_tones=(artifact.get("renderer_options") or {}).get("section_tones"),
        ),
        encoding="utf-8",
    )

    enriched_ref = artifact.get("renderer_options", {}).get("enriched_markdown_ref")
    if enriched_ref:
        enriched_path = resolve_local_ref(str(enriched_ref), item_path)
        if enriched_path.resolve() == input_path.resolve():
            raise ArtifactError("article renderer refuses to overwrite its source Markdown")
        enriched_path.parent.mkdir(parents=True, exist_ok=True)
        enriched_path.write_text(enriched_markdown, encoding="utf-8")

    font_gate = _run_article_typography_gate(output_path, config)
    return {
        "selected_visual_count": enriched_markdown.count("<!-- visual-slot:"),
        "local_assets_only": True,
        "ai_generation_used": False,
        "theme": theme,
        "design_direction_id": (
            item.get("visual", {})
            .get("design_system", {})
            .get("design_direction", {})
            .get("direction_id")
        ),
        "font_gate": font_gate,
    }


def _run_article_typography_gate(output_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    gate = config.get("typography_gate") or {}
    if not isinstance(gate, dict):
        raise ArtifactError("html-playwright typography_gate contract must be an object")
    required = ("policy_path", "policy_sha256", "desktop_profile_id", "mobile_profile_id")
    if any(not isinstance(gate.get(key), str) or not gate[key].strip() for key in required):
        raise ArtifactError("html-playwright typography_gate is missing a canonical policy binding")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", gate["policy_sha256"]):
        raise ArtifactError("html-playwright typography_gate.policy_sha256 must be a SHA-256 digest")
    policy_path = Path(gate["policy_path"]).expanduser().resolve()
    if not policy_path.is_file():
        raise ArtifactError(f"article canonical typography policy is missing: {policy_path}")
    browser_qa = STUDIO_ROOT / str(config.get("article_browser_qa", ""))
    if not browser_qa.is_file():
        raise ArtifactError("html-playwright article browser typography QA entry is missing")
    puppeteer_package = Path(str(config.get("puppeteer_package", ""))).expanduser().resolve()
    if not puppeteer_package.is_file():
        raise ArtifactError("html-playwright Puppeteer package metadata is missing")
    report_path = output_path.with_suffix(output_path.suffix + ".article-browser-qa.json")
    desktop_path = output_path.with_suffix(output_path.suffix + ".article-desktop.png")
    mobile_path = output_path.with_suffix(output_path.suffix + ".article-mobile.png")
    command = [
        "node", str(browser_qa), "--html", str(output_path),
        "--desktop", str(desktop_path), "--mobile", str(mobile_path),
        "--report", str(report_path), "--chromium", str(_discover_chromium()),
        "--puppeteer-package", str(puppeteer_package),
        "--typography-policy", str(policy_path),
        "--typography-policy-sha256", gate["policy_sha256"].casefold(),
        "--desktop-typography-profile", gate["desktop_profile_id"],
        "--mobile-typography-profile", gate["mobile_profile_id"],
        "--allow-no-figures", "true",
    ]
    result = subprocess.run(command, cwd=STUDIO_ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    if result.returncode not in {0, 2} or not report_path.is_file():
        raise ArtifactError("article browser typography QA could not produce a report: " + (result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"))
    report = _load_json(report_path)
    return {
        "passed": report.get("passed") is True,
        "report_ref": str(report_path),
        "report_sha256": _sha256(report_path),
        "desktop": report.get("desktop", {}).get("typography_gate", {}),
        "mobile": report.get("mobile", {}).get("typography_gate", {}),
    }


def _split_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, markdown
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as exc:
        raise ArtifactError("Marp input has an unterminated YAML frontmatter block") from exc
    frontmatter = yaml.safe_load("\n".join(lines[1:end])) or {}
    if not isinstance(frontmatter, dict):
        raise ArtifactError("Marp frontmatter must be a YAML object")
    return frontmatter, "\n".join(lines[end + 1 :]).lstrip("\n")


def _markdown_image_refs(markdown: str) -> list[str]:
    refs: list[str] = []
    for token in MarkdownIt("commonmark").parse(markdown):
        children = token.children or []
        for child in children:
            if child.type == "image":
                src = child.attrGet("src")
                if src:
                    refs.append(src)
    return refs


def _render_marp(
    item: dict[str, Any], item_path: Path, artifact: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    inputs = artifact.get("input_refs", [])
    if len(inputs) != 1:
        raise ArtifactError("marp requires exactly one Markdown input_ref")
    input_path = resolve_local_ref(inputs[0], item_path)
    if input_path.suffix.casefold() not in {".md", ".markdown"}:
        raise ArtifactError("marp input must be Markdown")

    theme = artifact.get("theme")
    themes = {
        "cover-photo-overlay": STUDIO_ROOT / "themes" / "cover-photo-overlay.css",
        "section-photo-overlay": STUDIO_ROOT / "themes" / "section-photo-overlay.css",
    }
    theme_path = themes.get(theme)
    if theme_path is None:
        raise ArtifactError(f"marp theme must be one of {', '.join(themes)}")

    budget_errors = validate_marp_budget(artifact)
    if budget_errors:
        raise ArtifactError("Marp slot budget failed: " + "; ".join(budget_errors))
    copy_fields = artifact["renderer_options"]["copy"]
    markdown = input_path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(markdown)
    for field in ("title", "supporting_copy"):
        if copy_fields[field] not in body:
            raise ArtifactError(f"Marp copy field {field!r} does not occur verbatim in the input")

    assets = {
        asset.get("asset_id"): asset
        for asset in item.get("visual", {}).get("assets", [])
        if asset.get("asset_id")
    }
    background_asset_id = artifact.get("renderer_options", {}).get("background_asset_id")
    if not background_asset_id:
        raise ArtifactError("Marp photo-overlay themes require renderer_options.background_asset_id")
    if background_asset_id not in artifact.get("asset_ids", []):
        raise ArtifactError("Marp background_asset_id must also be listed in artifact.asset_ids")
    background_asset = assets.get(background_asset_id)
    if not background_asset:
        raise ArtifactError(f"unknown Marp background asset {background_asset_id!r}")
    if background_asset.get("rights_status") != "verified":
        raise ArtifactError("Marp background image rights must be verified")
    safe_crop = background_asset.get("safe_crop")
    if not safe_crop:
        raise ArtifactError("Marp background image requires safe_crop metadata")
    background_path = resolve_local_ref(str(background_asset.get("ref", "")), item_path)
    if not background_path.exists() or str(background_asset.get("ref", "")).casefold().startswith(("http://", "https://")):
        raise ArtifactError("Marp background image must be a registered local file")

    for image_ref in _markdown_image_refs(body):
        raise ArtifactError(
            "Marp photo-overlay inputs cannot contain inline images; register the single "
            f"background asset instead: {image_ref}"
        )

    focus = background_asset.get("focal_point") or {
        "x": float(safe_crop["x"]) + float(safe_crop["width"]) / 2,
        "y": float(safe_crop["y"]) + float(safe_crop["height"]) / 2,
    }
    frontmatter.update(
        {
            "marp": True,
            "theme": theme,
            "size": "content-portrait",
            "paginate": False,
            "backgroundImage": f'url("{background_path.resolve().as_uri()}")',
            "backgroundPosition": f"{_percentage(float(focus['x']))} {_percentage(float(focus['y']))}",
            "backgroundSize": "cover",
            "footer": copy_fields["source"],
        }
    )
    normalized = "---\n" + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False) + "---\n\n" + body

    local_path = Path(config["local_path"])
    cli = local_path / config["entry"]
    if not cli.exists():
        raise ArtifactError(f"missing fixed Marp CLI entry: {cli}")
    output_path = resolve_local_ref(artifact["ref"], item_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=output_path.parent, delete=False, suffix=".marp.md"
    ) as handle:
        handle.write(normalized)
        normalized_path = Path(handle.name)
    try:
        command = [
            "node",
            str(cli),
            str(normalized_path),
            "--no-config-file",
            "--theme-set",
            str(theme_path),
            "--theme",
            str(theme),
            "--allow-local-files",
            "--browser",
            "chrome",
            "--browser-path",
            str(_discover_chromium()),
            "--output",
            str(output_path),
        ]
        if artifact.get("format") == "png":
            command.extend(["--image", "png", "--image-scale", "1"])
        elif artifact.get("format") == "pdf":
            command.append("--pdf")
        else:
            raise ArtifactError("Marp adapter only publishes PNG or PDF")
        _run(command, cwd=local_path)
    finally:
        normalized_path.unlink(missing_ok=True)

    return {
        "text_budget_valid": True,
        "background_rights_verified": True,
        "safe_crop_present": True,
        "local_assets_only": True,
        "theme": theme,
        "background_position": frontmatter["backgroundPosition"],
    }


def _render_data_explanation(
    item: dict[str, Any], item_path: Path, artifact: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    try:
        from render_data_explanations import (
            SPEC_VERSION as DATA_SPEC_VERSION,
            html_document as data_explanation_html,
            render_canvas as render_data_canvas,
            render_svg_text as render_data_svg,
            validate_spec as validate_data_spec,
        )
    except ModuleNotFoundError as exc:
        if exc.name != "render_data_explanations":
            raise
        raise ArtifactError(
            "data-explanation rendering requires the held first-party data backend "
            "module 'render_data_explanations', which is not installed"
        ) from exc

    inputs = artifact.get("input_refs", [])
    if not 1 <= len(inputs) <= 2:
        raise ArtifactError("data-explanation rendering requires one legacy chart spec and may include one normalized contract")
    candidates = []
    for ref in inputs:
        candidate = resolve_local_ref(ref, item_path)
        if candidate.suffix.casefold() == ".json":
            candidates.append((candidate, _load_json(candidate)))
    legacy = [(path, payload) for path, payload in candidates if payload.get("schema_version") == DATA_SPEC_VERSION]
    if len(legacy) != 1:
        raise ArtifactError("data-explanation rendering requires exactly one data-explanation-chart-spec.v1 input")
    spec_path, spec = legacy[0]
    spec_errors = validate_data_spec(spec, spec_path)
    if spec_errors:
        raise ArtifactError("invalid data-explanation spec: " + "; ".join(spec_errors))

    output_path = resolve_local_ref(artifact["ref"], item_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    svg_text = render_data_svg(spec)
    output_format = artifact.get("format")
    if output_format == "svg":
        output_path.write_text(svg_text, encoding="utf-8")
    elif output_format == "html":
        output_path.write_text(
            data_explanation_html(spec, svg_text), encoding="utf-8"
        )
    elif output_format == "png":
        render_data_canvas(spec).image.save(output_path, format="PNG", optimize=True)
    else:
        raise ArtifactError("data-explanation adapter supports HTML, SVG, or PNG")
    return {
        "data_spec_valid": True,
        "canonical_fallback": (
            output_format != "svg" or output_path.read_text(encoding="utf-8") == svg_text
        ),
        "chart_id": spec["chart_id"],
        "chart_type": spec["chart_type"],
        "spec_sha256": _sha256(spec_path),
    }


def _render_ppt_master(
    item: dict[str, Any], item_path: Path, artifact: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    options = artifact.get("renderer_options", {})
    operation = options.get("operation", config.get("operations", {}).get("default", "generate"))
    allowed_operations = config.get("operations", {}).get("allowed", ["generate"])
    if operation not in allowed_operations:
        raise ArtifactError(
            f"ppt-master operation {operation!r} is not one of {allowed_operations!r}"
        )

    inputs = artifact.get("input_refs", [])
    if artifact.get("asset_ids"):
        raise ArtifactError("ppt-master local adapter does not accept content assets")

    protocol = options.get("ppt_master_protocol")
    if protocol != config.get("protocol"):
        raise ArtifactError(
            f"ppt-master artifact must explicitly select pinned protocol {config.get('protocol')!r}"
        )
    if "ppt_master_root" in options:
        raise ArtifactError("ppt-master source root is registry-owned and cannot be overridden")

    adapter = Path(config["adapter_entry"])
    source_root = Path(config["local_path"])
    if not adapter.is_file():
        raise ArtifactError(f"missing fixed ai-ppt-local adapter: {adapter}")
    if not source_root.is_dir():
        raise ArtifactError(f"missing fixed PPT Master checkout: {source_root}")

    output_path = resolve_local_ref(artifact["ref"], item_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if operation == "generate":
        if len(inputs) != 1:
            raise ArtifactError(
                "ppt-master generate requires exactly one ai-ppt-brief.v1 input_ref"
            )
        brief_path = resolve_local_ref(inputs[0], item_path)
        if brief_path.suffix.casefold() != ".json":
            raise ArtifactError("ppt-master generate input must be ai-ppt-brief.v1 JSON")
        brief = _load_json(brief_path)
        if brief.get("schema_version") != config.get("input_schema"):
            raise ArtifactError(
                f"ppt-master input schema must be {config.get('input_schema')!r}"
            )
        if brief.get("contains_sensitive_data") is not False:
            raise ArtifactError("ppt-master local adapter rejects sensitive brief input")
        if brief.get("external_provider_required") is not False:
            raise ArtifactError(
                "ppt-master local adapter cannot require an external provider"
            )
        command = [
            sys.executable,
            str(adapter),
            "generate",
            "--brief",
            str(brief_path),
            "--output",
            str(output_path),
            "--ppt-master-root",
            str(source_root),
            "--ppt-master-protocol",
            str(protocol),
            "--overwrite",
        ]
    elif operation == "template-fill":
        if len(inputs) != 2:
            raise ArtifactError(
                "ppt-master template-fill requires source PPTX and confirmed fill plan"
            )
        source_path = resolve_local_ref(inputs[0], item_path)
        plan_path = resolve_local_ref(inputs[1], item_path)
        if source_path.suffix.casefold() != ".pptx":
            raise ArtifactError("ppt-master template-fill source must be PPTX")
        if plan_path.suffix.casefold() != ".json":
            raise ArtifactError("ppt-master template-fill plan must be JSON")
        fill_plan = _load_json(plan_path)
        template_fill_config = config.get("operations", {}).get("template-fill", {})
        if fill_plan.get("schema") != template_fill_config.get("plan_schema"):
            raise ArtifactError(
                f"ppt-master fill plan schema must be {template_fill_config.get('plan_schema')!r}"
            )
        if fill_plan.get("status") != "confirmed":
            raise ArtifactError("ppt-master fill plan status must be confirmed")
        if options.get("template_fill_plan_confirmed") is not True:
            raise ArtifactError(
                "ppt-master template-fill requires explicit template_fill_plan_confirmed=true"
            )
        if template_fill_config.get("m2_text_replacements_only") is True:
            for slide in fill_plan.get("slides", []):
                if slide.get("table_edits") or slide.get("chart_edits"):
                    raise ArtifactError(
                        "ppt-master M2 template-fill accepts text replacements only"
                    )
        work_dir = output_path.parent / f".{output_path.stem}.template-fill-work"
        command = [
            sys.executable,
            str(adapter),
            "template-fill",
            "apply",
            "--source",
            str(source_path),
            "--plan",
            str(plan_path),
            "--output",
            str(output_path),
            "--work-dir",
            str(work_dir),
            "--confirmed-plan",
            "--overwrite",
            "--ppt-master-root",
            str(source_root),
            "--ppt-master-protocol",
            str(protocol),
            "--timeout",
            "180",
        ]
    else:
        if len(inputs) not in {2, 3}:
            raise ArtifactError(
                "ppt-master data-native requires chart spec and rendered SVG fallback, with an optional normalized data contract"
            )
        spec_path = resolve_local_ref(inputs[0], item_path)
        fallback_path = resolve_local_ref(inputs[1], item_path)
        if spec_path.suffix.casefold() != ".json":
            raise ArtifactError("ppt-master data-native spec input must be JSON")
        if fallback_path.suffix.casefold() != ".svg":
            raise ArtifactError("ppt-master data-native fallback input must be SVG")
        fallback_artifact_id = options.get("fallback_artifact_id")
        if not fallback_artifact_id:
            raise ArtifactError(
                "ppt-master data-native requires renderer_options.fallback_artifact_id"
            )
        if fallback_artifact_id not in artifact.get("depends_on_artifact_ids", []):
            raise ArtifactError(
                "ppt-master data-native fallback must be an explicit artifact dependency"
            )
        work_dir = output_path.parent / f"{output_path.stem}.data-native-project"
        try:
            projection = materialize_ppt_data_project(
                spec_path, fallback_path, work_dir
            )
        except (OSError, json.JSONDecodeError, ProjectionError) as exc:
            raise ArtifactError(f"ppt-master data projection failed: {exc}") from exc
        command = [
            sys.executable,
            str(adapter),
            "generate",
            "--project",
            str(work_dir),
            "--native-data-projection",
            projection["projection"],
            "--output",
            str(output_path),
            "--ppt-master-root",
            str(source_root),
            "--ppt-master-protocol",
            str(protocol),
            "--overwrite",
            "--timeout",
            "180",
        ]
    _run(command, cwd=adapter.parent.parent)

    manifest_path = Path(str(output_path) + ".manifest.json")
    if not manifest_path.is_file():
        raise ArtifactError("ai-ppt-local did not produce its companion manifest")
    validation_report_path = Path(str(output_path) + ".quality.json")
    if config.get("visual_validation_required") is True:
        validation_python = _discover_primary_runtime_python()
        _run(
            [
                str(validation_python),
                str(adapter),
                "validate",
                "--artifact",
                str(output_path),
                "--report",
                str(validation_report_path),
                "--render",
                "--timeout",
                "180",
            ],
            cwd=adapter.parent.parent,
        )
    if not validation_report_path.is_file():
        raise ArtifactError("ai-ppt-local did not produce its visual validation report")
    validation_report = _load_json(validation_report_path)
    validation_stages = validation_report.get("stages", {})
    manifest = _load_json(manifest_path)
    generation = manifest.get("generation", {})
    artifact_report = manifest.get("artifact", {})
    evidence = manifest.get("ppt_master_evidence", {})
    template_fill_evidence = manifest.get("template_fill_evidence", {})
    native_data_evidence = manifest.get("native_data_evidence", {})
    semantic = generation.get("semantic_structure") or {}
    quality = evidence.get("quality_status") or {}
    manifest_fresh = (
        artifact_report.get("sha256") == _sha256(output_path)
        and artifact_report.get("path") == str(output_path.resolve())
    )
    protocol_pinned = (
        generation.get("protocol") == config.get("protocol")
        and generation.get("protocol_schema_version") == config.get("adapter_protocol")
    )
    source_commit_pinned = (
        generation.get("source_commit") == config.get("commit")
        and generation.get("source_commit_verified") is True
    )
    details = {
        "operation": operation,
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": _sha256(manifest_path),
        "validation_report_path": str(validation_report_path.resolve()),
        "validation_report_sha256": _sha256(validation_report_path),
        "manifest_fresh": manifest_fresh,
        "protocol_pinned": protocol_pinned,
        "source_commit_pinned": source_commit_pinned,
        "native_drawingml": (
            artifact_report.get("editable") is True
            and artifact_report.get("native_powerpoint_objects") is True
            and int(artifact_report.get("structure_summary", {}).get("native_shapes") or 0) > 0
        ),
        "structural_validation": validation_stages.get("structural", {}).get("ok") is True,
        "render_preview": validation_stages.get("render", {}).get("ok") is True,
        "render_output_directory": validation_stages.get("render", {}).get("output_directory"),
        "overflow": validation_stages.get("overflow", {}).get("ok") is True,
        "external_provider_disabled": generation.get("external_provider_used") is False,
    }
    if operation == "generate":
        details.update(
            {
                "text_fidelity": artifact_report.get("text_fidelity")
                == "exact_normalized_match",
                "semantic_page_roles": semantic.get("all_pages_have_page_role") is True,
                "semantic_logical_groups": (
                    int(semantic.get("logical_group_count") or 0) > 0
                    and int(
                        artifact_report.get("structure_summary", {}).get("group_shapes")
                        or 0
                    )
                    > 0
                ),
                "semantic_structure": semantic,
                "svg_quality": quality.get("errors") == 0
                and quality.get("warnings") == 0,
                "quality_status": quality,
                "postflight": evidence.get("postflight_status") == "passed",
                "postflight_status": evidence.get("postflight_status"),
                "delivery_check": evidence.get("delivery_status") == "passed",
                "delivery_status": evidence.get("delivery_status"),
            }
        )
    elif operation == "template-fill":
        check_summary = template_fill_evidence.get("check_plan_summary") or {}
        upstream_summary = template_fill_evidence.get("upstream_validate_summary") or {}
        target_audit = template_fill_evidence.get("text_target_audit") or {}
        details.update(
            {
                "fill_plan_confirmed": (
                    template_fill_evidence.get("plan_status") == "confirmed"
                    and template_fill_evidence.get("explicit_confirmed_plan_flag") is True
                ),
                "fill_plan_capacity": (
                    int(check_summary.get("error") or 0) == 0
                    and int(check_summary.get("warn") or 0) == 0
                ),
                "fill_plan_summary": check_summary,
                "upstream_readback": int(upstream_summary.get("error") or 0) == 0,
                "upstream_validate_summary": upstream_summary,
                "planned_targets_only": (
                    target_audit.get("ok") is True
                    and int(target_audit.get("unplanned_change_count") or 0) == 0
                ),
                "text_target_audit": target_audit,
                "template_structure_audit": template_fill_evidence.get(
                    "template_structure_audit"
                )
                or {},
                "template_structure_preserved": template_fill_evidence.get(
                    "template_structure_preserved"
                )
                is True,
                "text_fidelity": artifact_report.get("text_fidelity")
                == "planned_replacements_exact_unplanned_unchanged",
            }
        )
    else:
        source_audit = native_data_evidence.get("source_audit", {})
        files = source_audit.get("files", {})
        details.update(
            {
                "data_spec_hash_match": files.get("spec", {}).get("ok") is True,
                "fallback_fresh": files.get("fallback", {}).get("ok") is True,
                "projection_validated": (
                    source_audit.get("ok") is True
                    and source_audit.get("native_payload_hash_match") is True
                ),
                "native_chart_present": int(
                    native_data_evidence.get("native_chart_count") or 0
                )
                == 1,
                "native_data_exact": (
                    native_data_evidence.get("type_exact") is True
                    and native_data_evidence.get("values_exact") is True
                ),
                "native_zero_baseline": native_data_evidence.get(
                    "zero_baseline_exact"
                )
                is True,
                "native_labels_exact": (
                    native_data_evidence.get("categories_exact") is True
                    and native_data_evidence.get("series_labels_exact") is True
                    and native_data_evidence.get("text_exact") is True
                ),
                "native_data_evidence": native_data_evidence,
                "projection_path": native_data_evidence.get("projection"),
                "projection_sha256": native_data_evidence.get("projection_sha256"),
                "text_fidelity": artifact_report.get("text_fidelity")
                == "native_data_projection_verified",
                "svg_quality": quality.get("errors") == 0
                and quality.get("warnings") == 0,
                "quality_status": quality,
                "postflight": evidence.get("postflight_status") == "passed",
                "postflight_status": evidence.get("postflight_status"),
                "delivery_check": evidence.get("delivery_status") == "passed",
                "delivery_status": evidence.get("delivery_status"),
            }
        )
    return details


def _render_baoyu_md(
    item: dict[str, Any], item_path: Path, artifact: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    inputs = artifact.get("input_refs", [])
    if len(inputs) != 1:
        raise ArtifactError("baoyu-md requires exactly one Markdown input_ref")
    input_path = resolve_local_ref(inputs[0], item_path)
    if input_path.suffix.casefold() not in {".md", ".markdown"}:
        raise ArtifactError("baoyu-md input must be Markdown")

    output_path = resolve_local_ref(artifact["ref"], item_path)
    if output_path.resolve() == input_path.resolve():
        raise ArtifactError("baoyu-md refuses to overwrite its input Markdown")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    expected_suffix = ".html" if artifact["format"] == "html" else ".md"
    if output_path.suffix.casefold() != expected_suffix:
        raise ArtifactError(f"baoyu-md {artifact['format']} output must end in {expected_suffix}")

    theme = artifact.get("theme") or "default"
    if theme not in config.get("themes", []):
        raise ArtifactError(f"baoyu-md theme {theme!r} is not pinned in the renderer registry")

    assets_by_id = {
        asset.get("asset_id"): asset
        for asset in item.get("visual", {}).get("assets", [])
        if asset.get("asset_id")
    }
    asset_manifest: list[dict[str, str]] = []
    for asset_id in artifact.get("asset_ids", []):
        asset = assets_by_id[asset_id]
        ref = str(asset.get("ref", ""))
        if ref.casefold().startswith(("http://", "https://")):
            raise ArtifactError("baoyu-md only accepts registered local assets")
        local_path = resolve_local_ref(ref, item_path)
        if not local_path.exists():
            raise ArtifactError(f"baoyu-md asset {asset_id!r} is missing: {ref}")
        asset_manifest.append(
            {
                "asset_id": asset_id,
                "absolute_ref": str(local_path.resolve()),
                "alt_text": str(asset.get("alt_text", "")),
            }
        )

    bridge = STUDIO_ROOT / config["bridge"]
    baoyu_entry = Path(config["local_path"]) / config["entry"]
    mermaid_runtime = config.get("mermaid_runtime", {})
    mermaid_script = Path(str(mermaid_runtime.get("browser_bundle", "")))
    puppeteer_package = Path(str(config.get("puppeteer_package", "")))
    renderer_registry = _load_json(RENDERER_REGISTRY_PATH).get("renderers", {})
    antv_config = renderer_registry.get("antv-infographic", {})
    antv_cli = Path(str(antv_config.get("local_path", ""))) / str(antv_config.get("entry", ""))
    required_paths = {
        "Baoyu bridge": bridge,
        "Baoyu entry": baoyu_entry,
        "Mermaid browser bundle": mermaid_script,
        "Puppeteer package": puppeteer_package,
        "AntV CLI": antv_cli,
    }
    for label, required_path in required_paths.items():
        if not required_path.exists():
            raise ArtifactError(f"missing fixed {label}: {required_path}")

    renderer_options = artifact.get("renderer_options", {})
    cache_ref = renderer_options.get("cache_ref")
    cache_dir = (
        resolve_local_ref(str(cache_ref), item_path)
        if cache_ref
        else output_path.parent / f".{output_path.stem}.baoyu-cache"
    )
    cache_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=output_path.parent, delete=False, suffix=".assets.json"
    ) as handle:
        json.dump(asset_manifest, handle, ensure_ascii=False, indent=2)
        manifest_path = Path(handle.name)
    try:
        result = _run(
            [
                "node",
                str(bridge),
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--format",
                artifact["format"],
                "--assets-json",
                str(manifest_path),
                "--baoyu-entry",
                str(baoyu_entry),
                "--antv-cli",
                str(antv_cli),
                "--antv-commit",
                str(antv_config.get("commit", "unknown")),
                "--chromium",
                str(_discover_chromium()),
                "--mermaid-script",
                str(mermaid_script),
                "--mermaid-version",
                str(mermaid_runtime.get("version", "unknown")),
                "--puppeteer-package",
                str(puppeteer_package),
                "--cache-dir",
                str(cache_dir),
                "--theme",
                theme,
            ],
            cwd=STUDIO_ROOT,
        )
    finally:
        manifest_path.unlink(missing_ok=True)

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise ArtifactError("baoyu-md bridge returned no evidence JSON")
    try:
        details = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise ArtifactError(f"baoyu-md bridge returned invalid evidence JSON: {exc}") from exc
    if details.get("remote_downloads_enabled") is not False:
        raise ArtifactError("baoyu-md bridge did not prove remote downloads are disabled")
    return details


def _render_obsidian_preview(
    item: dict[str, Any], item_path: Path, artifact: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    if artifact.get("input_refs"):
        raise ArtifactError("obsidian preview packages use only the pinned source checkout")
    if artifact.get("asset_ids"):
        raise ArtifactError("obsidian preview packages do not consume content assets")

    output_path = resolve_local_ref(artifact["ref"], item_path)
    if output_path.suffix.casefold() != ".zip":
        raise ArtifactError("obsidian preview package output must end in .zip")
    lowered_parts = [part.casefold() for part in output_path.parts]
    if ".obsidian" in lowered_parts:
        raise ArtifactError("obsidian preview package cannot write into an Obsidian plugin directory")

    local_path = Path(config["local_path"])
    actual_commit = _run(["git", "rev-parse", "HEAD"], cwd=local_path).stdout.strip()
    if actual_commit != config.get("commit"):
        raise ArtifactError(
            f"obsidian preview source commit {actual_commit!r} does not match registry"
        )
    tracked_changes = _run(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=local_path
    ).stdout.strip()
    if tracked_changes:
        raise ArtifactError("obsidian preview source has tracked changes; refusing an unpinned build")

    npm = shutil.which("npm")
    if not npm:
        raise ArtifactError("npm is required to build the pinned Obsidian preview source")
    _run([npm, "run", "build"], cwd=local_path)
    tracked_after = _run(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=local_path
    ).stdout.strip()
    if tracked_after:
        raise ArtifactError("obsidian preview build modified tracked source files")

    package_files = [str(name) for name in config.get("package_files", [])]
    if not package_files:
        raise ArtifactError("obsidian preview registry has no package file allowlist")
    component_paths = {name: local_path / name for name in package_files}
    missing = [name for name, source_path in component_paths.items() if not source_path.exists()]
    if missing:
        raise ArtifactError(f"obsidian preview build is missing package files: {missing}")

    manifest = _load_json(component_paths["manifest.json"])
    package_json = _load_json(local_path / "package.json")
    license_text = component_paths["LICENSE"].read_text(encoding="utf-8")
    package_license = str(package_json.get("license", "unknown"))
    detected_license = (
        "ISC"
        if "with or without fee" in license_text and "THE SOFTWARE IS PROVIDED" in license_text
        else "unknown"
    )
    license_mismatch = package_license != detected_license
    if manifest.get("version") != config.get("version"):
        raise ArtifactError("obsidian preview manifest version does not match renderer registry")
    if package_license != config.get("package_license"):
        raise ArtifactError("obsidian preview package.json license does not match renderer registry")
    if detected_license != config.get("license_file_detected"):
        raise ArtifactError("obsidian preview LICENSE detection does not match renderer registry")

    components = {
        name: {"sha256": _sha256(source_path), "bytes": source_path.stat().st_size}
        for name, source_path in component_paths.items()
    }
    build_evidence = {
        "schema_version": "obsidian-preview-build.v1",
        "source_commit": actual_commit,
        "plugin_id": manifest.get("id"),
        "plugin_version": manifest.get("version"),
        "components": components,
        "license_metadata": {
            "package_json": package_license,
            "license_file_detected": detected_license,
            "mismatch": license_mismatch,
            "review_required": license_mismatch,
        },
        "boundary": config.get("boundary"),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(component_paths):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, component_paths[name].read_bytes())
        info = zipfile.ZipInfo("BUILD_RECEIPT.json", date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(
            info,
            (json.dumps(build_evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            ),
        )

    return {
        "package_manifest_valid": bool(manifest.get("id") and manifest.get("version")),
        "package_checksum": _sha256(output_path),
        "license_metadata_recorded": license_mismatch,
        "license_note": (
            f"package.json declares {package_license}; LICENSE text matches {detected_license}; "
            "personal local preview only, review required"
        ),
        "no_install_side_effect": True,
        "component_hashes": components,
    }


def _image_metrics(path: Path) -> tuple[int, int, float]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        sample = rgb.copy()
        sample.thumbnail((256, 256))
        colors = sample.getcolors(sample.width * sample.height) or []
        dominant = max((count for count, _ in colors), default=sample.width * sample.height)
        nonblank_ratio = 1 - dominant / max(1, sample.width * sample.height)
    return width, height, round(nonblank_ratio, 6)


def _qa_output(
    item: dict[str, Any],
    item_path: Path,
    output_path: Path,
    artifact: dict[str, Any],
    render_details: dict[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    checks: dict[str, dict[str, str]] = {}

    def check(name: str, passed: bool, details: str) -> None:
        checks[name] = {"name": name, "status": "pass" if passed else "fail", "details": details}

    exists = output_path.exists()
    check("file-exists", exists, str(output_path))
    size = output_path.stat().st_size if exists else 0
    check("non-empty-output", size > 0, f"{size} bytes")
    missing_inputs = [
        ref
        for ref in artifact.get("input_refs", [])
        if not resolve_local_ref(ref, item_path).exists()
    ]
    check("input-files-exist", not missing_inputs, f"missing={missing_inputs}")
    gates = item.get("gates", {})
    for gate_name in ("fact", "rights", "privacy"):
        status = gates.get(gate_name, {}).get("status")
        check(f"{gate_name}-gate", status == "pass", f"status={status!r}")
    if is_global_visual_enabled(artifact, item):
        context_errors = validate_global_visual_item(item, artifact)
        check("global-visual-context", not context_errors, "; ".join(message for _, message in context_errors) or "global-visual-context.v1 resolved")
        typography = render_details.get("global_visual_typography", {})
        check("chinese-typography-rendered", typography.get("status") == "pass", typography.get("message", "missing rendered typography evidence"))
    metrics: dict[str, Any] = {}

    if exists and artifact.get("format") in {"png", "jpg"}:
        width, height, nonblank_ratio = _image_metrics(output_path)
        metrics.update(width=width, height=height, nonblank_ratio=nonblank_ratio)
        expected = artifact.get("dimensions")
        dimensions_match = not expected or (
            width == expected.get("width") and height == expected.get("height")
        )
        check("pixel-dimensions", dimensions_match, f"actual={width}x{height}, expected={expected}")
        check("nonblank-pixels", nonblank_ratio >= 0.01, f"ratio={nonblank_ratio}")

    text = ""
    if exists and artifact.get("format") in {"svg", "html", "md"}:
        try:
            text = output_path.read_text(encoding="utf-8")
            check("utf8-readable", True, "output decodes as UTF-8")
        except UnicodeDecodeError as exc:
            check("utf8-readable", False, str(exc))

    if artifact.get("format") == "svg":
        check("svg-root", "<svg" in text.casefold(), "output contains an SVG root")
    elif artifact.get("format") == "html":
        lowered = text.casefold()
        check(
            "html-document",
            "<!doctype html" in lowered and "<html" in lowered,
            "output contains a complete HTML document",
        )
        check(
            "responsive-viewport",
            "name=\"viewport\"" in lowered or "name='viewport'" in lowered,
            "output declares a responsive viewport",
        )
        if artifact.get("media_adapter") == "article":
            parser = _ImageAltParser()
            parser.feed(text)
            check(
                "alt-text-complete",
                parser.missing_alt == 0,
                f"images missing non-empty alt={parser.missing_alt}",
            )
    elif artifact.get("format") == "md":
        check("markdown-readable", bool(text.strip()), "Markdown output contains text")
    elif artifact.get("format") == "pdf":
        signature = output_path.read_bytes()[:5] if exists else b""
        check("pdf-signature", signature == b"%PDF-", f"signature={signature!r}")
    elif artifact.get("format") in {"zip", "pptx"}:
        readable = False
        details = "output is not a readable ZIP container"
        if exists:
            try:
                with zipfile.ZipFile(output_path) as archive:
                    bad_member = archive.testzip()
                readable = bad_member is None
                details = f"bad_member={bad_member!r}"
            except zipfile.BadZipFile as exc:
                details = str(exc)
        check("zip-readable", readable, details)

    if artifact.get("renderer") == "social-card":
        check(
            "script-free-html",
            render_details.get("script_free_html") is True,
            "active HTML and inline event handlers are absent",
        )
        check(
            "local-assets-only",
            render_details.get("local_assets_only") is True
            and not render_details.get("blocked_remote_requests"),
            f"blocked remote requests={render_details.get('blocked_remote_requests', [])}",
        )
        check(
            "social-card-dom-qa",
            render_details.get("dom_qa_passed") is True,
            str(render_details.get("dom_qa_summary", "")),
        )
        check(
            "card-overflow",
            int(render_details.get("card_overflow_px") or 0) <= 4,
            f"overflow={render_details.get('card_overflow_px', 0)}px",
        )
        font_gate = render_details.get("font_gate") or {}
        check(
            "font-size-gate",
            font_gate.get("passed") is True,
            "policy={policy}; profile={profile}; failures={failures}".format(
                policy=font_gate.get("policy_id") or "missing",
                profile=font_gate.get("profile_id") or "missing",
                failures=font_gate.get("failures") or [],
            ),
        )

    if artifact.get("renderer") == "html-playwright":
        font_gate = render_details.get("font_gate") or {}
        check(
            "font-size-gate",
            font_gate.get("passed") is True,
            "desktop={desktop}; mobile={mobile}".format(
                desktop=(font_gate.get("desktop") or {}).get("failures") or [],
                mobile=(font_gate.get("mobile") or {}).get("failures") or [],
            ),
        )

    if artifact.get("renderer") == "antv-infographic":
        svg_text = render_details.get("svg_text", "")
        check("svg-root", "<svg" in svg_text, "AntV SSR output contains an SVG root")
        check(
            "no-remote-font-stylesheet",
            "assets.antv.antgroup.com" not in svg_text,
            "remote AntV font stylesheets are absent",
        )
        check(
            "local-cjk-font",
            "Microsoft YaHei" in svg_text,
            "local CJK font stack is embedded",
        )
        check(
            "slot-budget",
            render_details.get("slot_budget_valid") is True,
            f"template={render_details.get('template')!r}",
        )

    if artifact.get("renderer") == "marp":
        check("text-budget", render_details.get("text_budget_valid") is True, "Marp copy budget passed")
        check(
            "background-rights",
            render_details.get("background_rights_verified") is True,
            "background asset rights are verified",
        )
        check(
            "safe-crop-metadata",
            render_details.get("safe_crop_present") is True,
            f"background position={render_details.get('background_position')}",
        )
        check(
            "local-assets-only",
            render_details.get("local_assets_only") is True,
            "all Marp images resolve to declared local assets",
        )

    if artifact.get("renderer") == "baoyu-md":
        check(
            "local-assets-only",
            render_details.get("local_assets_only") is True,
            f"used assets={render_details.get('used_asset_ids', [])}",
        )
        check(
            "wikilinks-resolved",
            render_details.get("wikilinks_resolved") is True,
            "Obsidian image wikilinks resolve to registered local assets",
        )
        check(
            "cjk-text-preserved",
            render_details.get("cjk_text_preserved") is True,
            "Chinese prose survives Baoyu CJK preprocessing",
        )
        check(
            "mermaid-cache-deterministic",
            render_details.get("mermaid_cache_deterministic") is True,
            f"cache={render_details.get('mermaid_cache', [])}",
        )
        check(
            "static-antv-blocks",
            render_details.get("static_antv_blocks") is True,
            f"cache={render_details.get('antv_cache', [])}",
        )

    if artifact.get("renderer") == "obsidian-infographic-preview":
        check(
            "package-manifest",
            render_details.get("package_manifest_valid") is True,
            "manifest id and pinned version are present",
        )
        check(
            "package-checksum",
            bool(render_details.get("package_checksum")),
            f"sha256={render_details.get('package_checksum')}",
        )
        check(
            "license-metadata-recorded",
            render_details.get("license_metadata_recorded") is True,
            str(render_details.get("license_note", "")),
        )
        check(
            "no-install-side-effect",
            render_details.get("no_install_side_effect") is True,
            "build-only package; no plugin install, enablement, or vault write",
        )

    if artifact.get("renderer") == "lieflat-charts":
        check(
            "data-spec-valid",
            render_details.get("data_spec_valid") is True,
            f"chart_id={render_details.get('chart_id')!r}, type={render_details.get('chart_type')!r}",
        )
        check(
            "canonical-fallback",
            render_details.get("canonical_fallback") is True,
            f"spec_sha256={render_details.get('spec_sha256')}",
        )

    if artifact.get("renderer") == "ppt-master":
        operation = render_details.get("operation", "generate")
        check(
            "manifest-fresh",
            render_details.get("manifest_fresh") is True,
            f"manifest={render_details.get('manifest_path')}, sha256={render_details.get('manifest_sha256')}",
        )
        check(
            "ppt-master-protocol-pinned",
            render_details.get("protocol_pinned") is True,
            "artifact uses ppt-master-protocol.v1 with explicit v4.5 selection",
        )
        check(
            "source-commit-pinned",
            render_details.get("source_commit_pinned") is True,
            "PPT Master source commit matches the renderer registry",
        )
        check(
            "native-drawingml",
            render_details.get("native_drawingml") is True,
            "PPTX contains editable native DrawingML shapes",
        )
        check(
            "structural-validation",
            render_details.get("structural_validation") is True,
            f"report={render_details.get('validation_report_path')}, sha256={render_details.get('validation_report_sha256')}",
        )
        check(
            "render-preview",
            render_details.get("render_preview") is True,
            f"slides={render_details.get('render_output_directory')}",
        )
        check(
            "overflow",
            render_details.get("overflow") is True,
            "padded-canvas overflow test passed",
        )
        check(
            "external-provider-disabled",
            render_details.get("external_provider_disabled") is True,
            "no external provider was used",
        )
        if operation == "generate":
            check(
                "text-fidelity",
                render_details.get("text_fidelity") is True,
                "normalized SVG and PPTX text match exactly",
            )
            check(
                "semantic-page-roles",
                render_details.get("semantic_page_roles") is True,
                f"roles={render_details.get('semantic_structure', {}).get('page_roles')}",
            )
            check(
                "semantic-logical-groups",
                render_details.get("semantic_logical_groups") is True,
                f"groups={render_details.get('semantic_structure', {}).get('logical_group_count')}",
            )
            check(
                "svg-quality",
                render_details.get("svg_quality") is True,
                f"summary={render_details.get('quality_status')}",
            )
            check(
                "postflight",
                render_details.get("postflight") is True,
                f"status={render_details.get('postflight_status')!r}",
            )
            check(
                "delivery-check",
                render_details.get("delivery_check") is True,
                f"status={render_details.get('delivery_status')!r}",
            )
        elif operation == "template-fill":
            check(
                "fill-plan-confirmed",
                render_details.get("fill_plan_confirmed") is True,
                "fill plan and explicit content-item confirmation are both present",
            )
            check(
                "fill-plan-capacity",
                render_details.get("fill_plan_capacity") is True,
                f"summary={render_details.get('fill_plan_summary')}",
            )
            check(
                "upstream-readback",
                render_details.get("upstream_readback") is True,
                f"summary={render_details.get('upstream_validate_summary')}",
            )
            check(
                "planned-targets-only",
                render_details.get("planned_targets_only") is True,
                f"audit={render_details.get('text_target_audit')}",
            )
            check(
                "template-structure-preserved",
                render_details.get("template_structure_preserved") is True,
                f"audit={render_details.get('template_structure_audit')}",
            )
        elif operation == "data-native":
            check(
                "data-spec-hash-match",
                render_details.get("data_spec_hash_match") is True,
                f"projection={render_details.get('projection_path')}",
            )
            check(
                "fallback-fresh",
                render_details.get("fallback_fresh") is True,
                "rendered SVG fallback hash matches the projection input",
            )
            check(
                "native-projection-validated",
                render_details.get("projection_validated") is True,
                f"projection_sha256={render_details.get('projection_sha256')}",
            )
            check(
                "native-chart-present",
                render_details.get("native_chart_present") is True,
                "PPTX contains exactly one PowerPoint-native chart",
            )
            check(
                "native-data-exact",
                render_details.get("native_data_exact") is True,
                "chart type and numeric series round-trip exactly",
            )
            check(
                "native-zero-baseline",
                render_details.get("native_zero_baseline") is True,
                "native value axis minimum matches the explicit projection contract",
            )
            check(
                "native-labels-exact",
                render_details.get("native_labels_exact") is True,
                "categories, series labels, unit, source, and required slide text round-trip exactly",
            )
            check(
                "text-fidelity",
                render_details.get("text_fidelity") is True,
                "non-chart evidence text matches the deterministic projection",
            )
            check(
                "svg-quality",
                render_details.get("svg_quality") is True,
                f"summary={render_details.get('quality_status')}",
            )
            check(
                "postflight",
                render_details.get("postflight") is True,
                f"status={render_details.get('postflight_status')!r}",
            )
            check(
                "delivery-check",
                render_details.get("delivery_check") is True,
                f"status={render_details.get('delivery_status')!r}",
            )

    if artifact.get("renderer") == "imagegen":
        authorized = _ai_generation_authorized(item)
        check("ai-generation-authorized", authorized, f"authorized={authorized}")

    _, required = required_hard_checks(artifact)
    for missing_name in sorted(required.difference(checks)):
        check(missing_name, False, "renderer adapter did not report this required check")

    return list(checks.values()), metrics


def _human_review_checks(item: dict[str, Any]) -> list[dict[str, str]]:
    review = item.get("qa", {}).get("human_review", {})
    if review.get("status") == "approved":
        return [{"name": "human-final-review", "status": "pass", "details": "content item records approval"}]
    return [
        {
            "name": "human-final-review",
            "status": "needs-review",
            "details": "medical, insurance, customer-case, and final outputs remain manual-review only",
        }
    ]


def _receipt_evidence_metadata(
    item: dict[str, Any],
    item_path: Path,
    artifact: dict[str, Any],
) -> tuple[list[dict[str, str]], str, dict[str, str]]:
    evidence_refs: list[dict[str, str]] = []
    checked_at_values: list[str] = []
    contract_versions = {
        "content_item": str(item.get("schema_version", "unknown")),
        "render_receipt": "render-receipt.v1",
    }
    for input_ref in artifact.get("input_refs", []):
        input_path = resolve_local_ref(input_ref, item_path)
        if input_path.suffix.casefold() != ".json":
            continue
        try:
            payload = _load_json(input_path)
        except (OSError, json.JSONDecodeError):
            continue
        schema_version = payload.get("schema_version")
        if schema_version == "data-visual-spec.v1":
            contract_versions["data_visual_spec"] = str(schema_version)
            if payload.get("updated_at"):
                checked_at_values.append(str(payload["updated_at"]))
            for source in payload.get("sources", []):
                if not source.get("ref"):
                    continue
                evidence_refs.append(
                    {
                        "evidence_id": str(source.get("source_id") or f"source-{len(evidence_refs) + 1}"),
                        "ref": str(source["ref"]),
                        "evidence_status": str(source.get("evidence_status", "unknown")),
                        "label": str(source.get("label", "")),
                    }
                )
        if schema_version == DATA_SPEC_VERSION:
            contract_versions["chart_spec"] = str(schema_version)
            if payload.get("evidence_binding_version"):
                contract_versions["evidence_binding"] = str(
                    payload["evidence_binding_version"]
                )
            if payload.get("checked_at"):
                checked_at_values.append(str(payload["checked_at"]))
            for source in payload.get("source_refs", []):
                if not source.get("ref"):
                    continue
                evidence_refs.append(
                    {
                        "evidence_id": str(
                            source.get("evidence_id")
                            or f"source-{len(evidence_refs) + 1}"
                        ),
                        "ref": str(source["ref"]),
                        "evidence_status": str(
                            source.get("evidence_status", "unverified")
                        ),
                        "label": str(source.get("label", "")),
                    }
                )
    checked_at = max(checked_at_values) if checked_at_values else _now_iso()
    return evidence_refs, checked_at, contract_versions


def _build_receipt(
    item: dict[str, Any],
    item_path: Path,
    artifact: dict[str, Any],
    renderer_config: dict[str, Any],
    output_path: Path,
    hard_checks: list[dict[str, str]],
    metrics: dict[str, Any],
    retry_count: int,
) -> dict[str, Any]:
    review_checks = _human_review_checks(item)
    needs_review_count = sum(check["status"] == "needs-review" for check in review_checks)
    hard_pass = all(check["status"] == "pass" for check in hard_checks)
    result = "fail" if not hard_pass else ("review-required" if needs_review_count else "pass")
    output_hash = _sha256(output_path)
    visual = item.get("visual", {})
    generated = artifact.get("renderer") == "imagegen" or any(
        asset.get("asset_type") == "generated-image" for asset in visual.get("assets", [])
    )
    source = {
        key: renderer_config[key]
        for key in ("repository", "commit", "license", "local_path")
        if renderer_config.get(key)
    }
    if renderer_config.get("integration_commit"):
        source["patch_ref"] = renderer_config["integration_commit"]

    profile_id, _ = required_hard_checks(artifact)
    evidence_refs, checked_at, contract_versions = _receipt_evidence_metadata(
        item,
        item_path,
        artifact,
    )
    receipt: dict[str, Any] = {
        "schema_version": "render-receipt.v1",
        "receipt_id": f"{item['content_id']}.{artifact['artifact_id']}.{output_hash[:12]}",
        "artifact_id": artifact["artifact_id"],
        "content_id": item["content_id"],
        "renderer": artifact["renderer"],
        "renderer_version": str(
            artifact.get("renderer_version")
            or renderer_config.get("version")
            or renderer_config.get("integration_commit")
            or renderer_config.get("commit")
            or "local"
        ),
        "created_at": _now_iso(),
        "checked_at": checked_at,
        "contract_versions": contract_versions,
        "evidence_refs": evidence_refs,
        "manual_only": item.get("publication", {}).get("boundary") == "manual-only",
        "candidate_only": (
            item.get("status") != "approved"
            or artifact.get("status") != "approved"
        ),
        "inputs": [
            {"ref": ref, "sha256": _sha256(resolve_local_ref(ref, item_path))}
            for ref in artifact.get("input_refs", [])
        ],
        "output": {
            "ref": artifact["ref"],
            "format": artifact["format"],
            "sha256": output_hash,
            "bytes": output_path.stat().st_size,
            **metrics,
        },
        "qa": {
            "profile_id": profile_id,
            "hard_checks": hard_checks,
            "review_checks": review_checks,
            "needs_review_count": needs_review_count,
            "result": result,
            "retry_count": retry_count,
        },
        "policy": {
            "rights_verified": item.get("gates", {}).get("rights", {}).get("status") == "pass",
            "privacy_verified": item.get("gates", {}).get("privacy", {}).get("status") == "pass",
            "ai_generation_authorized": bool(
                generated
                and _ai_generation_authorized(item)
            ),
            "remote_downloads_enabled": False,
        },
        "notes": [
            "No publication, customer contact, CRM, Logseq, or Obsidian write was performed.",
            "Candidate output only; medical, insurance, and current resource availability require human review.",
        ],
    }
    if source:
        receipt["source"] = source
    return receipt


def _attach_renderer_receipt_evidence(
    receipt: dict[str, Any], artifact: dict[str, Any], details: dict[str, Any]
) -> None:
    """Bind renderer-native evidence into the generic receipt without duplicating QA state."""
    if artifact.get("renderer") in {"social-card", "html-playwright"}:
        receipt["font_gate"] = details.get("font_gate") or {
            "passed": False,
            "failures": ["missing-font-gate-evidence"],
        }


def _render(item: dict[str, Any], item_path: Path, artifact: dict[str, Any]) -> dict[str, Any]:
    _preflight(item, item_path, artifact)
    config = _renderer_config(artifact)
    output_path = resolve_local_ref(artifact["ref"], item_path)
    receipt_path = resolve_local_ref(artifact["receipt_ref"], item_path)

    renderers: dict[str, Callable[..., dict[str, Any]]] = {
        "social-card": _render_social_card,
        "html-playwright": _render_html_playwright,
        "lieflat-charts": _render_data_explanation,
        "antv-infographic": _render_antv,
        "marp": _render_marp,
        "ppt-master": _render_ppt_master,
        "baoyu-md": _render_baoyu_md,
        "obsidian-infographic-preview": _render_obsidian_preview,
    }
    renderer = renderers.get(artifact["renderer"])
    if renderer is None:
        raise ArtifactError(
            f"renderer {artifact['renderer']!r} is registered but has no unified CLI adapter yet"
        )

    hard_checks: list[dict[str, str]] = []
    metrics: dict[str, Any] = {}
    retries = 0
    while True:
        details = renderer(item, item_path, artifact, config)
        details["global_visual_typography"] = _global_visual_typography_qa(item, item_path, artifact, output_path, details)
        hard_checks, metrics = _qa_output(item, item_path, output_path, artifact, details)
        failures = {check["name"] for check in hard_checks if check["status"] == "fail"}
        if not failures or retries >= MAX_RENDER_RETRIES or not failures.issubset(RETRYABLE_QA_CHECKS):
            break
        retries += 1

    conformance = None
    conformance_path = None
    if is_global_visual_enabled(artifact, item):
        media_profile_id, _ = required_hard_checks(artifact)
        media_hard_checks = [dict(check) for check in hard_checks]
        conformance = build_conformance_receipt(
            item,
            artifact,
            output_path,
            details.get("global_visual_typography", {}),
            _global_visual_data_status(artifact, item_path),
            {
                "profile_id": media_profile_id,
                "hard_checks": media_hard_checks,
                "result": "pass" if all(check["status"] == "pass" for check in media_hard_checks) else "fail",
            },
        )
        conformance_path = resolve_local_ref(
            artifact.get("conformance_receipt_ref")
            or str(receipt_path.with_name(receipt_path.stem + ".visual-conformance.json")),
            item_path,
        )
        _write_json_atomic(conformance_path, conformance)
        hard_checks.append({"name": "visual-conformance-receipt", "status": "pass" if conformance["result"] != "fail" else "fail", "details": f"result={conformance['result']} ref={conformance_path}"})

    receipt = _build_receipt(
        item,
        item_path,
        artifact,
        config,
        output_path,
        hard_checks,
        metrics,
        retries,
    )
    _attach_renderer_receipt_evidence(receipt, artifact, details)
    if artifact.get("renderer") == "obsidian-infographic-preview":
        receipt["notes"].append(str(details.get("license_note", "license metadata review required")))
    if artifact.get("renderer") == "social-card" and details.get("dom_qa_warning_count"):
        receipt["notes"].append(
            "External social-card QA warnings remain a single human density review item: "
            f"{details['dom_qa_warning_count']} warning(s)."
        )
    if conformance and conformance_path:
        receipt["contract_versions"]["global_visual_context"] = "global-visual-context.v1"
        receipt["contract_versions"]["visual_conformance"] = "visual-conformance-receipt.v1"
        receipt["visual_conformance"] = {
            "ref": str(conformance_path),
            "schema_version": "visual-conformance-receipt.v1",
            "sha256": _sha256(conformance_path),
            "result": conformance["result"],
        }
    _write_json_atomic(receipt_path, receipt)
    if any(check["status"] == "fail" for check in hard_checks):
        raise ArtifactError(f"rendered output failed QA; receipt written to {receipt_path}")
    return receipt


def _plan(item: dict[str, Any], item_path: Path, artifact: dict[str, Any]) -> dict[str, Any]:
    config = _renderer_config(artifact)
    errors = _format_validation_errors(item, item_path)
    if errors:
        raise ArtifactError("item validation failed:\n- " + "\n- ".join(errors))
    return {
        "status": "planned",
        "content_id": item["content_id"],
        "artifact_id": artifact["artifact_id"],
        "renderer": artifact["renderer"],
        "selection_policy": config.get("selection_policy"),
        "layout_intent": artifact["layout_intent"],
        "input_refs": artifact.get("input_refs", []),
        "output_ref": artifact.get("ref"),
        "receipt_ref": artifact.get("receipt_ref"),
        "publication_boundary": "manual-only",
        **({"global_visual": build_runtime_context(item, artifact)} if is_global_visual_enabled(artifact, item) else {}),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "render", "validate"))
    parser.add_argument("--item", type=Path, required=True)
    parser.add_argument("--artifact-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    item_path = args.item.resolve()
    try:
        item = _load_json(item_path)
        artifact = _find_artifact(item, args.artifact_id)
        if args.action == "plan":
            result = _plan(item, item_path, artifact)
        elif args.action == "validate":
            errors = _format_validation_errors(item, item_path)
            if errors:
                raise ArtifactError("item validation failed:\n- " + "\n- ".join(errors))
            result = {
                "status": "valid",
                "content_id": item["content_id"],
                "artifact_id": artifact["artifact_id"],
            }
        else:
            result = _render(item, item_path, artifact)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ArtifactError, OSError, json.JSONDecodeError) as exc:
        print(f"artifact command failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
