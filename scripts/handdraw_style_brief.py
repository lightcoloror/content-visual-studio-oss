#!/usr/bin/env python3
"""Create an optional, image-free style brief for an existing content target."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

try:  # The installed public package ships studio_paths; keep a source-tree fallback.
    from studio_paths import STUDIO_ROOT
except ModuleNotFoundError:  # pragma: no cover - isolated source/test trees
    STUDIO_ROOT = Path(__file__).resolve().parents[1]

ROOT = Path(STUDIO_ROOT)
REGISTRY = ROOT / "config" / "handdraw-style-brief.v1.json"
DIRECTIONS = ROOT / "config" / "design-directions.v1.json"

LEGACY_ROOT_ENV = "CONTENT_STUDIO_HANDDRAW_LEGACY_ROOT"
MISSING_LEGACY_ROOT = (
    "Pinned handdraw-style source root is not configured; provide an explicit "
    "source_root, set CONTENT_STUDIO_HANDDRAW_LEGACY_ROOT, or configure a nonempty "
    "source.local_path"
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _configured_source_root(source: dict, source_root) -> Path:
    """Resolve the operator-explicit legacy checkout; never guess a vendor path."""
    candidate: Path | None = None
    if source_root is not None:
        candidate = Path(source_root).expanduser()
    if candidate is None:
        env_value = os.environ.get(LEGACY_ROOT_ENV, "").strip()
        if env_value:
            candidate = Path(env_value).expanduser()
    if candidate is None:
        local_path = source.get("local_path")
        if isinstance(local_path, str) and local_path.strip():
            candidate = Path(local_path).expanduser()
            if not candidate.is_absolute():
                candidate = ROOT / candidate
    if candidate is None:
        raise ValueError(MISSING_LEGACY_ROOT)
    return candidate.resolve()


def _pinned_commit(source: dict, checkout: Path):
    """Return (commit, manifest-or-None) using packaged, legacy-relative or Git HEAD pins."""
    manifest_path = source.get("manifest_path")
    if manifest_path:
        configured = Path(manifest_path).expanduser()
        if not configured.is_absolute():
            configured = ROOT / configured
        path = configured.resolve()
        expected = source.get("manifest_sha256")
        if not expected:
            raise ValueError("Pinned handdraw-style source manifest hash is not configured")
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise ValueError("Pinned handdraw-style source manifest has drifted") from exc
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError("Pinned handdraw-style source manifest has drifted")
        manifest = json.loads(payload.decode("utf-8"))
        return manifest["commit"], manifest
    manifest_ref = source.get("manifest_ref")
    if manifest_ref:
        path = (checkout / manifest_ref).resolve()
        if not path.is_relative_to(checkout):
            raise ValueError("Pinned handdraw-style source manifest escapes source snapshot")
        expected = source.get("manifest_sha256")
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise ValueError("Pinned handdraw-style source manifest has drifted") from exc
        if not expected or hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError("Pinned handdraw-style source manifest has drifted")
        manifest = json.loads(payload.decode("utf-8"))
        return manifest["commit"], manifest
    commit = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip()
    return commit, None


def verify_source(registry: dict, *, source_root=None) -> dict[str, dict]:
    source = registry["source"]
    checkout = _configured_source_root(source, source_root)
    index = (checkout / source["index_ref"]).resolve()
    if not index.is_relative_to(checkout):
        raise ValueError("Pinned handdraw-style index escapes source snapshot")
    if not checkout.is_dir() or not index.is_file():
        raise ValueError("Pinned handdraw-style checkout or index is missing")
    commit, manifest = _pinned_commit(source, checkout)
    if manifest is not None:
        if manifest["files"].get(source["index_ref"]) != source["index_sha256"]:
            raise ValueError("Pinned handdraw-style index has drifted")
    if commit != source["commit"]:
        raise ValueError("Pinned handdraw-style commit has drifted")
    payload = index.read_bytes()
    if hashlib.sha256(payload).hexdigest() != source["index_sha256"]:
        raise ValueError("Pinned handdraw-style index has drifted")
    records = {entry["number"]: entry for entry in json.loads(payload.decode("utf-8"))}
    for style_id, style in registry["styles"].items():
        record = records.get(style["source_number"])
        if not record or record["generation_name"] != style["source_generation_name"]:
            raise ValueError(f"Style index mapping has drifted: {style_id}")
        if not record["group"].startswith("F "):
            raise ValueError(f"Personal-creator style is not approved: {style_id}")
    return records


def target_from_item(item: dict, target_id: str) -> tuple[str, dict]:
    visual = item.get("visual") or {}
    slots = (visual.get("article_visual_plan") or {}).get("slots") or []
    artifacts = visual.get("render_artifacts") or []
    matches = sum(slot.get("slot_id") == target_id for slot in slots)
    matches += sum(artifact.get("artifact_id") == target_id for artifact in artifacts)
    if matches != 1:
        raise ValueError(f"Target ID must resolve exactly once: {target_id}")
    for slot in slots:
        if slot.get("slot_id") == target_id:
            if slot.get("status") not in {"planned", "candidates-ready"}:
                raise ValueError("Style brief cannot alter a selected or inserted article slot")
            if slot.get("media_role") not in {"explanatory", "contextual"}:
                raise ValueError("Style brief is not factual evidence or decoration")
            if slot.get("route") not in {"diagram", "generated-image"}:
                raise ValueError("Target article slot is not an illustration candidate")
            return "article", slot
    for artifact in artifacts:
        if artifact.get("artifact_id") == target_id:
            media = artifact.get("media_adapter")
            if media not in {"social-card", "web"}:
                raise ValueError("Target artifact is not an allowed style-brief medium")
            if artifact.get("status") != "planned":
                raise ValueError("Style brief cannot alter a rendered artifact")
            if media == "social-card" and artifact.get("renderer") != "social-card":
                raise ValueError("Social target must use the existing social-card renderer")
            if media == "web" and artifact.get("renderer") != "html-playwright":
                raise ValueError("Web target must use the existing HTML renderer")
            return media, artifact
    raise ValueError(f"Target ID is not registered in this content item: {target_id}")


def create_brief(
    item: dict, target_id: str, style_id: str, metaphor: str | None = None,
    central_action: str | None = None, registry: dict | None = None,
    *, source_root=None,
) -> dict:
    registry = registry or read_json(REGISTRY)
    if item.get("schema_version") != "0.2" or not item.get("content_id"):
        raise ValueError("Style brief requires a versioned content object with content_id")
    if registry.get("selection_policy") != "explicit-item-and-style-only":
        raise ValueError("Style selection policy is not explicit-only")
    style = registry["styles"].get(style_id)
    if not style:
        raise ValueError(f"Unregistered style candidate: {style_id}")
    verify_source(registry, source_root=source_root)
    visual = item.get("visual") or {}
    design_system = visual.get("design_system") or {}
    direction = (design_system.get("design_direction") or {}).get("direction_id")
    if not direction:
        raise ValueError("Content item must explicitly select a design direction")
    media, target = target_from_item(item, target_id)
    if design_system.get("media_adapter") != media:
        raise ValueError("Content design-system media adapter does not match target")
    target_key = f"{direction}/{media}"
    if target_key not in style["allowed_targets"]:
        raise ValueError(f"Style candidate is not allowed for {target_key}")
    directions = read_json(DIRECTIONS)["directions"]
    if (design_system.get("design_direction") or {}).get("version") != directions.get(direction, {}).get("version"):
        raise ValueError("Content design direction version has drifted")
    route = directions.get(direction, {}).get("routes", {}).get(media, {})
    if not route.get("status", "").startswith("route-eligible"):
        raise ValueError(f"Design direction is not route-eligible for {media}")
    visual_mode = (visual.get("article_visual_plan") or {}).get("visual_mode")
    excluded = directions[direction].get("excluded_routes", {}).get("article_visual_modes", [])
    if media == "article" and visual_mode in excluded:
        raise ValueError(f"Design direction excludes article visual mode: {visual_mode}")
    existing = target.get("visual_brief") or {}
    metaphor = (metaphor or existing.get("metaphor") or "").strip()
    central_action = (central_action or existing.get("central_action") or "").strip()
    if not metaphor or not central_action:
        raise ValueError("Metaphor and central action must come from the content brief")
    composition = " ".join(filter(None, [existing.get("composition", "").strip(), style["composition_guidance"]]))
    if len(metaphor) > 160 or len(central_action) > 160 or len(composition) > 240:
        raise ValueError("Style brief exceeds the existing visual_brief budget")
    return {
        "schema_version": "handdraw-style-brief.v1",
        "status": "candidate-only",
        "content_id": item.get("content_id"),
        "target_id": target_id,
        "media_adapter": media,
        "design_direction_id": direction,
        "style_id": style_id,
        "source_ref": f"handraw-style@{registry['source']['commit']}#{style['source_number']}",
        "source_index_sha256": registry["source"]["index_sha256"],
        "source_license_status": registry["source"]["license_status"],
        "upstream_asset_rights_status": registry["source"]["asset_rights_status"],
        "visual_role": "explanatory-illustration",
        "visual_brief": {
            "metaphor": metaphor,
            "composition": composition,
            "central_action": central_action,
            "max_labels": 0,
        },
        "upstream_image_used": False,
        "image_generated": False,
        "manual_review_required": True,
        "boundary": "Planning brief only; no asset rights, image generation, rendering, or publication authority",
    }


def _root_argument(args, name: str):
    specific = getattr(args, name, None)
    if specific is not None:
        return specific
    return getattr(args, name + "_global", None)


def _run(args) -> dict:
    legacy_root = _root_argument(args, "legacy_root")
    library_root = _root_argument(args, "library_root")
    if args.command in {"gallery", "catalog", "prompt"}:
        from handdraw_style_library import Library
        library = Library(source_root=library_root)
        if args.command == "gallery":
            return library.gallery(args.output_root)
        if args.command == "catalog":
            return library.catalog(args.query)
        result = library.prompt(read_json(args.item), args.target_id, read_json(args.request))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as target:
                target.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return result
    registry = read_json(REGISTRY)
    if args.command == "list":
        verify_source(registry, source_root=legacy_root)
        return {"status": "candidate-only", "styles": {
            key: value["allowed_targets"] for key, value in registry["styles"].items()
        }}
    result = create_brief(
        read_json(args.item), args.target_id, args.style_id,
        args.metaphor, args.central_action, registry, source_root=legacy_root,
    )
    if args.output:
        # Exclusive creation keeps a race from overwriting an existing brief.
        args.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with args.output.open("x", encoding="utf-8") as target:
                target.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        except FileExistsError as exc:
            raise ValueError("Output already exists; existing briefs are not overwritten") from exc
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--legacy-root", dest="legacy_root_global", type=Path, default=None,
        help="Explicit checkout root for the pinned legacy style brief/index",
    )
    parser.add_argument(
        "--library-root", dest="library_root_global", type=Path, default=None,
        help="Explicit checkout root for the pinned full style library",
    )
    command = parser.add_subparsers(dest="command", required=True)
    listing = command.add_parser("list", help="List locally verified generic style candidates")
    listing.add_argument("--legacy-root", type=Path, help="Explicit checkout root for the legacy style index")
    gallery = command.add_parser("gallery", help="Locate the pinned full style/layout/color galleries")
    gallery.add_argument("--library-root", type=Path, help="Explicit checkout root for the full style library")
    gallery.add_argument("--output-root", type=Path, help="Explicit writable root for generated gallery files")
    catalog = command.add_parser("catalog", help="Browse all numbered styles, layouts and colors")
    catalog.add_argument("--library-root", type=Path, help="Explicit checkout root for the full style library")
    catalog.add_argument("--query", default="")
    prompt = command.add_parser("prompt", help="Prepare a frozen-text style prompt for an existing image slot")
    prompt.add_argument("--library-root", type=Path, help="Explicit checkout root for the full style library")
    prompt.add_argument("--item", type=Path, required=True)
    prompt.add_argument("--target-id", required=True)
    prompt.add_argument("--request", type=Path, required=True)
    prompt.add_argument("--output", type=Path)
    brief = command.add_parser("brief", help="Draft a style brief for an explicit content target")
    brief.add_argument("--legacy-root", type=Path, help="Explicit checkout root for the legacy style index")
    brief.add_argument("--item", type=Path, required=True)
    brief.add_argument("--target-id", required=True)
    brief.add_argument("--style-id", required=True)
    brief.add_argument("--metaphor")
    brief.add_argument("--central-action")
    brief.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _run(args)
    except (ValueError, KeyError, FileNotFoundError, subprocess.CalledProcessError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
