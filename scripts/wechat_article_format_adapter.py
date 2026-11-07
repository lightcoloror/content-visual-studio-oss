#!/usr/bin/env python3
"""Render synthetic articles or explicitly declared public review drafts.

This adapter deliberately exposes no clone, upload, draft-creation, or publish action.
It treats the reviewed upstream checkout as an external executable dependency and
emits Content Studio render-receipt.v1 receipts for human review.
"""

from __future__ import annotations
from studio_paths import STUDIO_ROOT

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
CONTENT_SCHEMA = STUDIO_ROOT / "schemas" / "content-item.schema.json"
RECEIPT_SCHEMA = STUDIO_ROOT / "schemas" / "render-receipt.v1.schema.json"
REVIEW_SCRIPT = STUDIO_ROOT / "scripts" / "wechat_public_review.cjs"
DEFAULT_SOURCE_ROOT = Path.cwd() / "external" / "ryan-wechat-publisher"
SOURCE_REPOSITORY = "https://github.com/RyanChen1997/ryan-wechat-publisher"
PINNED_SOURCE_COMMIT = "561e3e736ef8d161247c70c30e694814e898ef59"
ADAPTER_VERSION = "wechat-article-format-adapter@0.2.0"
REMOTE_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((?:https?:|data:|//)", re.IGNORECASE)
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
INLINE_IMAGE_RE = re.compile(r"<(?:img|source)\b", re.IGNORECASE)
ALLOWED_PRESETS = frozenset(
    {
        "blue-dot-notes",
        "purple-badge",
        "vibrant-badge",
        "elegant-minimal",
        "geek-tech",
        "wechat-blue-yellow",
        "childlike-doodle",
    }
)
REQUIRED_SOURCE_FILES = (
    "scripts/render.js",
    "scripts/semantic_compare.py",
    "scripts/validate_wechat_html.py",
    "scripts/check_images.py",
)


class AdapterBlocked(RuntimeError):
    """Fail-closed input or dependency rejection."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_schema(instance: Any, schema_path: Path, label: str) -> None:
    validator = Draft202012Validator(_load_json(schema_path), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.absolute_path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "<root>"
        raise AdapterBlocked(f"{label}_schema_invalid:{location}:{first.message}")


def _run(command: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
    output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    if completed.returncode != 0:
        raise AdapterBlocked(f"external_validator_failed:{Path(command[0]).name}:{output}")
    return output


def _git(source_root: Path, *args: str) -> str:
    return _run(["git", "-C", str(source_root), *args], cwd=source_root).strip()


def _validate_source(source_root: Path, expected_commit: str) -> str:
    if expected_commit != PINNED_SOURCE_COMMIT:
        raise AdapterBlocked("expected_source_commit_not_approved")
    for relative in REQUIRED_SOURCE_FILES:
        if not (source_root / relative).is_file():
            raise AdapterBlocked(f"source_file_missing:{relative}")
    observed = _git(source_root, "rev-parse", "HEAD")
    if observed != expected_commit:
        raise AdapterBlocked("source_commit_drift")
    tracked_changes = _git(source_root, "status", "--porcelain", "--untracked-files=no")
    if tracked_changes:
        raise AdapterBlocked("source_tracked_tree_dirty")
    origins = _git(source_root, "remote", "get-url", "origin").removesuffix(".git").lower()
    if origins != SOURCE_REPOSITORY.lower():
        raise AdapterBlocked("source_origin_drift")
    return observed


def _resolve_body_ref(item_path: Path, body_ref: str) -> Path:
    candidate = Path(body_ref)
    if not candidate.is_absolute():
        candidate = item_path.parent / candidate
    return candidate.resolve()


def _validate_item(item: dict[str, Any], item_path: Path, markdown_path: Path, mode: str = "synthetic") -> None:
    _validate_schema(item, CONTENT_SCHEMA, "content_item")
    if mode == "synthetic":
        if "synthetic-only" not in item.get("tags", []):
            raise AdapterBlocked("synthetic_only_required")
        if item.get("status") != "publish-ready":
            raise AdapterBlocked("content_not_publish_ready")
        for gate_name in ("fact", "privacy", "compliance", "rights"):
            if item["gates"][gate_name]["status"] != "pass":
                raise AdapterBlocked(f"gate_not_pass:{gate_name}")
        if item["qa"]["human_review"]["status"] != "approved":
            raise AdapterBlocked("human_review_not_approved")
    else:
        if "public-material-review" not in item.get("tags", []) or "synthetic-only" in item.get("tags", []):
            raise AdapterBlocked("public_material_declaration_required")
        if item["status"] not in {"draft", "review"}:
            raise AdapterBlocked("review_draft_required")
        if item["gates"]["privacy"]["status"] != "pass":
            raise AdapterBlocked("public_review_privacy_not_pass")
        if any(gate["status"] == "blocked" for gate in item["gates"].values()):
            raise AdapterBlocked("blocked_gate_cannot_preview")
        if item["qa"]["human_review"]["status"] == "blocked":
            raise AdapterBlocked("blocked_human_review")
        if item["publication"]["receipts"]:
            raise AdapterBlocked("unpublished_review_required")
    if item["publication"]["boundary"] != "manual-only":
        raise AdapterBlocked("publication_boundary_not_manual_only")
    channel = item.get("channels", {}).get("wechat_article")
    allowed_channel_states = {"ready"} if mode == "synthetic" else {"draft", "review"}
    if not channel or channel.get("status") not in allowed_channel_states:
        raise AdapterBlocked("wechat_article_not_ready")
    if not channel.get("body_ref"):
        raise AdapterBlocked("wechat_article_body_ref_missing")
    if _resolve_body_ref(item_path, channel["body_ref"]) != markdown_path.resolve():
        raise AdapterBlocked("wechat_article_body_ref_drift")
    markdown = markdown_path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    canonical = item["composition"].get("canonical_body", "").replace("\r\n", "\n").strip()
    if markdown != canonical:
        raise AdapterBlocked("canonical_body_drift")
    if REMOTE_IMAGE_RE.search(markdown):
        raise AdapterBlocked("remote_or_data_image_not_allowed")
    if INLINE_IMAGE_RE.search(markdown):
        raise AdapterBlocked("inline_html_image_not_allowed")
    for raw_ref in MARKDOWN_IMAGE_RE.findall(markdown):
        image_ref = raw_ref.strip().split(maxsplit=1)[0].strip("<>")
        candidate = Path(image_ref)
        if candidate.is_absolute():
            raise AdapterBlocked("absolute_image_path_not_allowed")
        resolved = (markdown_path.parent / candidate).resolve()
        try:
            resolved.relative_to(markdown_path.parent.resolve())
        except ValueError as exc:
            raise AdapterBlocked("image_path_escape_not_allowed") from exc
        if not resolved.is_file():
            raise AdapterBlocked("local_image_missing")


def _public_review_payload(markdown: str, title: str) -> dict[str, Any]:
    # Reuse markdown-it for inline syntax; the pinned formatter still owns layout.
    from markdown_it import MarkdownIt

    if "![[" in markdown:
        raise AdapterBlocked("public_review_wiki_media_not_supported")
    parser = MarkdownIt("commonmark")
    tokens = parser.parse(markdown)
    allowed = {"heading_open", "heading_close", "paragraph_open", "paragraph_close", "inline",
               "bullet_list_open", "bullet_list_close", "list_item_open", "list_item_close", "hr"}
    for token in tokens:
        if token.type not in allowed or (token.type == "heading_open" and token.tag not in {"h1", "h2", "h3"}):
            raise AdapterBlocked(f"public_review_unsupported_block:{token.type}:{token.tag}")
        if token.level > 3:
            raise AdapterBlocked("public_review_nested_blocks_not_supported")
        for child in token.children or []:
            if child.type not in {"text", "softbreak", "strong_open", "strong_close", "em_open", "em_close",
                                  "code_inline", "link_open", "link_close"}:
                raise AdapterBlocked(f"public_review_unsupported_inline:{child.type}")
            if child.type == "link_open":
                url = urlsplit(child.attrGet("href") or "")
                if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
                    raise AdapterBlocked("public_review_link_not_public_http")
    if len(tokens) < 3 or tokens[0].type != "heading_open" or tokens[0].tag != "h1" or tokens[1].content != title:
        raise AdapterBlocked("public_review_title_must_match_first_h1")

    def link_open(renderer, inline, idx, options, env):
        href = inline[idx].attrGet("href")
        env.setdefault("links", []).append(href)
        return f'<a href="{html.escape(href, quote=True)}" rel="noreferrer" style="color:rgb(32,99,145);text-decoration:underline;overflow-wrap:anywhere;">'

    def link_close(renderer, inline, idx, options, env):
        href = env["links"].pop()
        return f'</a>（{html.escape(href)}）'

    parser.add_render_rule("link_open", link_open)
    parser.add_render_rule("link_close", link_close)
    inlines = {}
    for token in tokens:
        if token.type == "inline":
            text = " ".join(line.strip() for line in token.content.splitlines())
            inlines[text] = parser.renderInline(text, {})
    return {"markdown": markdown, "title": title, "inlines": inlines}


def _artifact_receipt(
    *,
    item: dict[str, Any],
    item_path: Path,
    markdown_path: Path,
    output_path: Path,
    artifact_suffix: str,
    checked_at: str,
    source_commit: str,
    mode: str = "synthetic",
) -> dict[str, Any]:
    content_id = item["content_id"]
    receipt = {
        "schema_version": "render-receipt.v1",
        "receipt_id": f"receipt-{content_id}-{artifact_suffix}",
        "artifact_id": f"{content_id}-{artifact_suffix}",
        "content_id": content_id,
        "renderer": "wechat-inline-html",
        "renderer_version": ADAPTER_VERSION,
        "created_at": checked_at,
        "checked_at": checked_at,
        "contract_versions": {
            "content_item": str(item["schema_version"]),
            "render_receipt": "render-receipt.v1",
            "external_formatter_commit": source_commit,
        },
        "manual_only": True,
        "candidate_only": True,
        "source": {
            "repository": SOURCE_REPOSITORY,
            "commit": source_commit,
            "license": "NOASSERTION",
            "local_path": "external-source-checkout",
        },
        "inputs": [
            {"ref": f"artifact://content-item/{item_path.name}", "sha256": _sha256(item_path)},
            {"ref": f"artifact://wechat-markdown/{markdown_path.name}", "sha256": _sha256(markdown_path)},
        ],
        "output": {
            "ref": output_path.name,
            "format": "html",
            "sha256": _sha256(output_path),
            "bytes": output_path.stat().st_size,
        },
        "qa": {
            "profile_id": "wechat-article-manual-preview-v1",
            "hard_checks": [
                {"name": "content-item-schema", "status": "pass"},
                {"name": "synthetic-only", "status": "pass"},
                {"name": "fact-privacy-compliance-rights-gates", "status": "pass"},
                {"name": "human-review-approved", "status": "pass"},
                {"name": "canonical-body-frozen", "status": "pass"},
                {"name": "pinned-source-checkout", "status": "pass"},
                {"name": "semantic-visible-text", "status": "pass"},
                {"name": "wechat-html-validator", "status": "pass"},
                {"name": "local-image-references", "status": "pass"},
                {"name": "remote-actions-disabled", "status": "pass"},
            ],
            "review_checks": [
                {
                    "name": "wechat-backend-preview",
                    "status": "needs-review",
                    "details": "人工粘贴到微信后台后检查，不由适配器上传。",
                },
                {
                    "name": "mobile-dark-mode-preview",
                    "status": "needs-review",
                    "details": "本地深色预览是模拟结果，仍需手机端人工确认。",
                },
            ],
            "needs_review_count": 2,
            "result": "review-required",
            "retry_count": 0,
        },
        "policy": {
            "rights_verified": True,
            "privacy_verified": True,
            "ai_generation_authorized": False,
            "remote_downloads_enabled": False,
        },
        "notes": [
            "Formatting candidate only; no upload, draft creation, or publication occurred.",
            "External repository has no root LICENSE file; source license remains NOASSERTION.",
        ],
    }
    if mode == "public-review":
        receipt["qa"]["hard_checks"] = [check for check in receipt["qa"]["hard_checks"] if check["name"] not in {
            "synthetic-only", "fact-privacy-compliance-rights-gates", "human-review-approved"}]
        receipt["qa"]["hard_checks"].append({"name": "public-draft-input-contract", "status": "pass"})
        receipt["qa"]["review_checks"].append({"name": "author-and-content-approval", "status": "needs-review",
                                              "details": "本地排版不替代作者、事实及发布审核。"})
        receipt["qa"]["needs_review_count"] = 3
        receipt["policy"]["rights_verified"] = item["gates"]["rights"]["status"] == "pass"
        receipt["policy"]["privacy_verified"] = item["gates"]["privacy"]["status"] == "pass"
        receipt["source"]["patch_ref"] = "scripts/wechat_public_review.cjs"
        receipt["notes"].extend([
            "Public text-only review; content gates and author state are preserved, not promoted.",
            "First H1 is preview/title metadata, excluded from paste body to avoid duplicate WeChat titles.",
            "Reference labels and URLs remain visible; links are not fetched.",
        ])
    _validate_schema(receipt, RECEIPT_SCHEMA, "render_receipt")
    return receipt


def render(args: argparse.Namespace) -> dict[str, Any]:
    item_path = Path(args.item).resolve()
    markdown_path = Path(args.markdown).resolve()
    source_root = Path(args.source_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    item = _load_json(item_path)
    mode = args.mode
    item_hash = _sha256(item_path)
    markdown_hash = _sha256(markdown_path)
    _validate_item(item, item_path, markdown_path, mode)
    payload = None
    if mode == "public-review":
        if not args.markdown_sha256 or args.markdown_sha256 != markdown_hash:
            raise AdapterBlocked("public_review_markdown_sha256_required_or_drifted")
        if args.preset != "elegant-minimal":
            raise AdapterBlocked("public_review_requires_elegant_minimal")
        payload = _public_review_payload(markdown_path.read_text(encoding="utf-8"), item["title"])
        if output_dir.exists():
            raise AdapterBlocked("public_review_output_must_be_new")
    if args.preset not in ALLOWED_PRESETS:
        raise AdapterBlocked("preset_not_allowlisted")
    source_commit = _validate_source(source_root, args.expected_source_commit)

    output_dir.mkdir(parents=True, exist_ok=(mode == "synthetic"))
    assets_dir = output_dir / "assets"
    body_path = output_dir / "wechat-article-body.html"
    preview_path = output_dir / "wechat-article-preview.html"
    dark_path = output_dir / "wechat-article-dark-preview.html"
    if payload is not None:
        payload_path = output_dir / "review-render-input.json"
        payload_path.write_bytes(_canonical_bytes(payload))
        _run(["node", str(REVIEW_SCRIPT), str(source_root),
              str(payload_path), str(output_dir)], cwd=source_root)
    else:
        _run(
            [
                "node",
                str(source_root / "scripts" / "render.js"),
                "--md", str(markdown_path),
                "--preset", args.preset,
                "--output-body", str(body_path),
                "--output-preview", str(preview_path),
                "--output-dark-preview", str(dark_path),
                "--asset-dir", str(markdown_path.parent),
                "--asset-output-dir", str(assets_dir),
                "--asset-url-prefix", "assets",
                "--title", item["title"],
            ],
            cwd=source_root,
        )
    _run([sys.executable, str(source_root / "scripts" / "semantic_compare.py"), str(markdown_path),
          str(output_dir / "wechat-article-text-check.html" if payload else body_path)], cwd=source_root)
    _run([sys.executable, str(source_root / "scripts" / "validate_wechat_html.py"), str(body_path)], cwd=source_root)
    _run(
        [sys.executable, str(source_root / "scripts" / "check_images.py"), str(preview_path), "--asset-dir", str(assets_dir), "--url-prefix", "assets"],
        cwd=source_root,
    )
    if _sha256(markdown_path) != markdown_hash or _sha256(item_path) != item_hash:
        raise AdapterBlocked("input_changed_during_render")

    receipts: list[dict[str, Any]] = []
    for artifact_suffix, output_path in (
        ("body", body_path),
        ("preview", preview_path),
        ("dark-preview", dark_path),
    ):
        receipt = _artifact_receipt(
            item=item,
            item_path=item_path,
            markdown_path=markdown_path,
            output_path=output_path,
            artifact_suffix=artifact_suffix,
            checked_at=args.checked_at,
            source_commit=source_commit,
            mode=mode,
        )
        receipt_path = output_dir / f"render-receipt-{artifact_suffix}.json"
        receipt_path.write_bytes(_canonical_bytes(receipt))
        receipts.append(receipt)

    manifest = {
        "status": "review-required",
        "mode": "public-review-candidate-only" if payload else "synthetic-candidate-only",
        "content_id": item["content_id"],
        "preset": args.preset,
        "source_commit": source_commit,
        "outputs": [receipt["output"] for receipt in receipts],
        "publication_boundary": "manual-only",
        "remote_actions_performed": False,
        "publication_authorized": False,
        "input_markdown_sha256": markdown_hash,
        "author_review": item["qa"]["human_review"]["status"],
        "content_gates": {name: gate["status"] for name, gate in item["gates"].items()},
    }
    (output_dir / "manifest.json").write_bytes(_canonical_bytes(manifest))
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manual-only WeChat article formatter adapter")
    subparsers = parser.add_subparsers(dest="action", required=True)
    command = subparsers.add_parser("render", help="Render a synthetic article or an explicit public-review draft")
    command.add_argument("--item", required=True)
    command.add_argument("--markdown", required=True)
    command.add_argument("--mode", choices=("synthetic", "public-review"), default="synthetic")
    command.add_argument("--markdown-sha256", help="Required exact source SHA256 for public-review")
    command.add_argument("--source-root", default=os.environ.get("RYAN_WECHAT_PUBLISHER_SOURCE", str(DEFAULT_SOURCE_ROOT)))
    command.add_argument("--expected-source-commit", default=PINNED_SOURCE_COMMIT)
    command.add_argument("--preset", default="elegant-minimal")
    command.add_argument("--output-dir", required=True)
    command.add_argument("--checked-at", required=True, help="Stable RFC 3339 timestamp for idempotent receipts")
    command.set_defaults(handler=render)
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    try:
        result = args.handler(args)
    except (AdapterBlocked, OSError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"ok": False, "status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
