#!/usr/bin/env python3
"""Cross-file validation for render artifacts and immutable receipts.

Public-source candidate: filesystem roots come from the public ``studio_paths``
module. The held data backend is imported lazily, only for data-required
renderers. All validation guards from the existing module are retained.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from markdown_it import MarkdownIt

_PUBLIC_SCRIPTS = Path(__file__).resolve().parent
if str(_PUBLIC_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_PUBLIC_SCRIPTS))

from studio_paths import SOURCE_ROOT, STUDIO_ROOT  # noqa: E402
from slot_budget_validation import (  # noqa: E402
    validate_antv_budget,
    validate_budget_registry_coverage,
    validate_marp_budget,
)
from media_qa_validation import required_hard_checks, validate_receipt_qa  # noqa: E402
from global_visual_validation import is_global_visual_enabled  # noqa: E402
from ppt_master_data_projection import (  # noqa: E402
    ProjectionError,
    project_native_payload,
)
from visual_asset_routing import is_ai_image_generation_authorized  # noqa: E402


def _import_data_explanations() -> tuple[str, Any, Any]:
    """Import the held data backend at first data-required use.

    A direct ``render_data_explanations`` absence is mapped to a validation
    error by the caller. Transitive ``ModuleNotFoundError`` and any other
    import or runtime error propagate unchanged.
    """
    from render_data_explanations import (
        SPEC_VERSION,
        render_svg_text,
        validate_spec,
    )

    return SPEC_VERSION, render_svg_text, validate_spec


def _missing_data_backend_error() -> str:
    return (
        "data-native artifact requires the first-party data backend module "
        "'render_data_explanations', which is not installed"
    )


RECEIPT_SCHEMA_PATH = STUDIO_ROOT / "schemas" / "render-receipt.v1.schema.json"
CONFORMANCE_SCHEMA_PATH = (
    STUDIO_ROOT / "visual-contracts" / "schemas" / "visual-conformance-receipt.v1.schema.json"
)
RENDERER_REGISTRY_PATH = STUDIO_ROOT / "config" / "renderer-registry.v1.json"
LAYOUT_REGISTRY_PATH = STUDIO_ROOT / "config" / "layout-intents.v1.json"
PRODUCED_STATUSES = {
    "rendered",
    "qa-failed",
    "review-required",
    "approved",
    "superseded",
}
PHOTO_ROUTES = {"personal-photo", "work-detail-photo", "stock-photo"}


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_local_ref(ref: str, item_path: Path) -> Path:
    """Resolve absolute refs and project-relative refs without guessing a network URL.

    Absolute refs, current-directory refs and ``..`` traversal keep their existing
    behavior; this resolver is a portability fallback, not a confinement or
    path-security boundary. Relative refs are tried under the item directory, the
    public studio root, the public source root and the current directory, in that
    order. The former private workspace-parent lookup is replaced by the
    documented public source root, and a missing ref falls back under the public
    studio root.
    """

    candidate = Path(ref)
    if candidate.is_absolute():
        return candidate

    roots = (item_path.parent, STUDIO_ROOT, SOURCE_ROOT, Path.cwd())
    for root in roots:
        resolved = (root / candidate).resolve()
        if resolved.exists():
            return resolved
    return (STUDIO_ROOT / candidate).resolve()


def _same_ref(left: str, right: str, item_path: Path) -> bool:
    return resolve_local_ref(left, item_path) == resolve_local_ref(right, item_path)


def _markdown_image_refs(markdown: str) -> list[str]:
    refs: list[str] = []
    for token in MarkdownIt("commonmark").parse(markdown):
        for child in token.children or []:
            if child.type == "image":
                src = child.attrGet("src")
                if src:
                    refs.append(src)
    return refs


def _validate_normalized_box(
    box: dict[str, Any], location: str
) -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []
    x = box.get("x")
    y = box.get("y")
    width = box.get("width")
    height = box.get("height")
    if all(isinstance(value, (int, float)) for value in (x, width)) and x + width > 1:
        errors.append((location, "normalized box extends beyond the right edge"))
    if all(isinstance(value, (int, float)) for value in (y, height)) and y + height > 1:
        errors.append((location, "normalized box extends beyond the bottom edge"))
    return errors


def _validate_receipt(
    item: dict[str, Any],
    item_path: Path,
    artifact: dict[str, Any],
    location: str,
) -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []
    receipt_ref = artifact.get("receipt_ref", "")
    output_ref = artifact.get("ref", "")
    if not receipt_ref:
        return [(f"{location}.receipt_ref", "produced artifacts require render-receipt.v1")]

    receipt_path = resolve_local_ref(receipt_ref, item_path)
    if not receipt_path.exists():
        return [(f"{location}.receipt_ref", f"missing render receipt: {receipt_ref}")]

    try:
        receipt = _load_json(receipt_path)
    except (OSError, json.JSONDecodeError) as exc:
        return [(f"{location}.receipt_ref", f"invalid render receipt: {exc}")]

    schema = _load_json(RECEIPT_SCHEMA_PATH)
    validator = Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(receipt), key=lambda value: list(value.path)):
        suffix = ".".join(str(part) for part in error.path)
        receipt_location = f"{location}.receipt_ref"
        if suffix:
            receipt_location += f".{suffix}"
        errors.append((receipt_location, error.message))

    expected_pairs = {
        "artifact_id": artifact.get("artifact_id"),
        "content_id": item.get("content_id"),
        "renderer": artifact.get("renderer"),
    }
    for field, expected in expected_pairs.items():
        if receipt.get(field) != expected:
            errors.append(
                (
                    f"{location}.receipt_ref.{field}",
                    f"receipt value {receipt.get(field)!r} does not match {expected!r}",
                )
            )

    output = receipt.get("output", {})
    if output.get("format") != artifact.get("format"):
        errors.append((f"{location}.receipt_ref.output.format", "does not match artifact format"))
    if output_ref and output.get("ref") and not _same_ref(output_ref, output["ref"], item_path):
        errors.append((f"{location}.receipt_ref.output.ref", "does not match artifact ref"))

    output_path = resolve_local_ref(output_ref, item_path) if output_ref else None
    if output_path and output_path.exists():
        actual_hash = _sha256(output_path)
        if str(output.get("sha256", "")).lower() != actual_hash:
            errors.append((f"{location}.receipt_ref.output.sha256", "does not match rendered file"))
        if output.get("bytes") != output_path.stat().st_size:
            errors.append((f"{location}.receipt_ref.output.bytes", "does not match rendered file"))

    artifact_inputs = artifact.get("input_refs", [])
    receipt_inputs = receipt.get("inputs", [])
    receipt_by_ref = {entry.get("ref"): entry for entry in receipt_inputs}
    for index, input_ref in enumerate(artifact_inputs):
        input_path = resolve_local_ref(input_ref, item_path)
        matching = next(
            (
                entry
                for entry in receipt_inputs
                if entry.get("ref") and _same_ref(input_ref, entry["ref"], item_path)
            ),
            None,
        )
        if matching is None:
            errors.append((f"{location}.receipt_ref.inputs", f"missing hash for input {input_ref!r}"))
        elif input_path.exists() and str(matching.get("sha256", "")).lower() != _sha256(input_path):
            errors.append((f"{location}.receipt_ref.inputs[{index}].sha256", "does not match input file"))

    qa = receipt.get("qa", {})
    for suffix, message in validate_receipt_qa(artifact, qa):
        errors.append((f"{location}.receipt_ref.qa.{suffix}", message))
    hard_checks = qa.get("hard_checks", [])
    has_hard_failure = any(check.get("status") != "pass" for check in hard_checks)
    needs_review_count = qa.get("needs_review_count", 0)
    if artifact.get("status") == "approved":
        if has_hard_failure:
            errors.append((f"{location}.status", "approved artifacts require every hard QA check to pass"))
        if not isinstance(needs_review_count, int) or needs_review_count > 1:
            errors.append((f"{location}.status", "approved artifacts allow at most one needs-review finding"))
        if artifact.get("human_review", {}).get("status") != "approved":
            errors.append((f"{location}.human_review.status", "approved artifact requires explicit human approval"))
        if qa.get("result") == "fail":
            errors.append((f"{location}.status", "an artifact with failed QA cannot be approved"))

    policy = receipt.get("policy", {})
    if artifact.get("asset_ids") and policy.get("rights_verified") is not True:
        errors.append((f"{location}.receipt_ref.policy.rights_verified", "must be true for referenced assets"))
    if artifact.get("renderer") == "baoyu-md" and policy.get("remote_downloads_enabled") is not False:
        errors.append((f"{location}.receipt_ref.policy.remote_downloads_enabled", "Baoyu adapter must keep remote downloads disabled"))
    if artifact.get("renderer") == "ppt-master":
        renderer_config = _load_json(RENDERER_REGISTRY_PATH).get("renderers", {}).get("ppt-master", {})
        source = receipt.get("source", {})
        if source.get("commit") != renderer_config.get("commit"):
            errors.append((f"{location}.receipt_ref.source.commit", "must match the pinned PPT Master registry commit"))
        if policy.get("remote_downloads_enabled") is not False:
            errors.append((f"{location}.receipt_ref.policy.remote_downloads_enabled", "PPT Master adapter must keep remote downloads disabled"))
        if policy.get("ai_generation_authorized") is not False:
            errors.append((f"{location}.receipt_ref.policy.ai_generation_authorized", "PPT Master local brief adapter does not use image generation"))
    if artifact.get("renderer") == "obsidian-infographic-preview":
        notes = " ".join(str(note) for note in receipt.get("notes", []))
        if "MIT" not in notes or "ISC" not in notes:
            errors.append((f"{location}.receipt_ref.notes", "must record the MIT/ISC license metadata mismatch"))
        if receipt.get("source", {}).get("license") != "metadata-mismatch-review-required":
            errors.append((f"{location}.receipt_ref.source.license", "must preserve license review status"))

    conformance_link = receipt.get("visual_conformance")
    if is_global_visual_enabled(artifact, item) and not conformance_link:
        errors.append((f"{location}.receipt_ref.visual_conformance", "global visual artifacts require visual-conformance-receipt.v1"))
    if conformance_link:
        conformance_path = resolve_local_ref(conformance_link.get("ref", ""), item_path)
        if not conformance_path.exists():
            errors.append((f"{location}.receipt_ref.visual_conformance.ref", "missing visual conformance receipt"))
        else:
            actual_hash = _sha256(conformance_path)
            if str(conformance_link.get("sha256", "")).lower() != actual_hash:
                errors.append((f"{location}.receipt_ref.visual_conformance.sha256", "does not match visual conformance receipt"))
            try:
                conformance = _load_json(conformance_path)
            except (OSError, json.JSONDecodeError) as exc:
                errors.append((f"{location}.receipt_ref.visual_conformance.ref", f"invalid visual conformance receipt: {exc}"))
            else:
                conformance_validator = Draft202012Validator(_load_json(CONFORMANCE_SCHEMA_PATH))
                for error in conformance_validator.iter_errors(conformance):
                    errors.append((f"{location}.receipt_ref.visual_conformance", error.message))
                for field, expected in (("artifact_id", artifact.get("artifact_id")), ("content_id", item.get("content_id"))):
                    if conformance.get(field) != expected:
                        errors.append((f"{location}.receipt_ref.visual_conformance.{field}", "does not match artifact"))
                if output_path and output_path.exists() and conformance.get("output", {}).get("sha256") != _sha256(output_path):
                    errors.append((f"{location}.receipt_ref.visual_conformance.output.sha256", "does not match rendered file"))
                if conformance_link.get("result") != conformance.get("result"):
                    errors.append((f"{location}.receipt_ref.visual_conformance.result", "does not match visual conformance receipt"))
                media_qa = conformance.get("media_qa", {})
                if media_qa.get("profile_id") != qa.get("profile_id"):
                    errors.append((f"{location}.receipt_ref.visual_conformance.media_qa.profile_id", "does not match render receipt QA profile"))
                expected_media_checks = {
                    check.get("name"): check.get("status")
                    for check in hard_checks
                    if check.get("name") != "visual-conformance-receipt"
                }
                actual_media_checks = {
                    check.get("name"): check.get("status")
                    for check in media_qa.get("hard_checks", [])
                }
                if actual_media_checks != expected_media_checks:
                    errors.append((f"{location}.receipt_ref.visual_conformance.media_qa.hard_checks", "does not match pre-conformance media QA checks"))
                for authority_index, authority in enumerate(conformance.get("authority_receipts", [])):
                    authority_path = resolve_local_ref(authority.get("ref", ""), item_path)
                    authority_location = f"{location}.receipt_ref.visual_conformance.authority_receipts[{authority_index}]"
                    if not authority_path.exists():
                        errors.append((f"{authority_location}.ref", "authority receipt or ruleset is missing"))
                    elif str(authority.get("sha256", "")).lower() != _sha256(authority_path):
                        errors.append((f"{authority_location}.sha256", "authority receipt or ruleset hash mismatch"))
                if conformance.get("result") == "fail" and artifact.get("status") == "approved":
                    errors.append((f"{location}.status", "failed visual conformance cannot be approved"))

    return errors


def validate_render_artifacts(
    item: dict[str, Any], item_path: Path
) -> list[tuple[str, str]]:
    """Return location/message pairs for artifact, asset, and receipt failures."""

    errors: list[tuple[str, str]] = []
    visual = item.get("visual", {})
    assets = visual.get("assets", [])
    artifacts = visual.get("render_artifacts", [])

    asset_ids: dict[str, int] = {}
    asset_refs: set[str] = set()
    for index, asset in enumerate(assets):
        location = f"visual.assets[{index}]"
        asset_id = asset.get("asset_id")
        if asset_id:
            if asset_id in asset_ids:
                errors.append((f"{location}.asset_id", f"duplicates visual.assets[{asset_ids[asset_id]}].asset_id"))
            else:
                asset_ids[asset_id] = index
        if asset.get("ref"):
            asset_refs.add(asset["ref"])
        for box_name in ("safe_crop", "subject_bounds"):
            box = asset.get(box_name)
            if isinstance(box, dict):
                errors.extend(_validate_normalized_box(box, f"{location}.{box_name}"))

    brand_spec = visual.get("brand_spec", {})
    for group, refs in brand_spec.get("asset_refs", {}).items():
        for index, ref in enumerate(refs):
            if ref not in asset_ids and ref not in asset_refs:
                errors.append((f"visual.brand_spec.asset_refs.{group}[{index}]", "must reference visual.assets[].asset_id or .ref"))

    exploration = visual.get("design_exploration", {})
    selected_direction = exploration.get("selected_direction_id")
    if selected_direction:
        direction_ids = {entry.get("direction_id") for entry in exploration.get("directions", [])}
        if selected_direction not in direction_ids:
            errors.append(("visual.design_exploration.selected_direction_id", "must match a declared direction_id"))

    for slot_index, slot in enumerate(visual.get("article_visual_plan", {}).get("slots", [])):
        brief = slot.get("visual_brief")
        if slot.get("route") in PHOTO_ROUTES and brief and brief.get("max_labels") != 0:
            errors.append((f"visual.article_visual_plan.slots[{slot_index}].visual_brief.max_labels", "real-photo slots default to zero in-image labels"))

    if not artifacts:
        return errors

    errors.extend(("visual.render_artifacts", message) for message in validate_budget_registry_coverage())

    renderer_registry = _load_json(RENDERER_REGISTRY_PATH).get("renderers", {})
    layout_registry = _load_json(LAYOUT_REGISTRY_PATH).get("intents", {})
    seen_artifacts: dict[str, int] = {}
    seen_outputs: dict[Path, int] = {}
    declared_artifacts = {
        artifact.get("artifact_id"): artifact
        for artifact in artifacts
        if artifact.get("artifact_id")
    }
    declared_outputs = {
        resolve_local_ref(artifact["ref"], item_path): artifact
        for artifact in artifacts
        if artifact.get("ref")
    }
    dependency_graph = {
        artifact_id: set(artifact.get("depends_on_artifact_ids", []))
        for artifact_id, artifact in declared_artifacts.items()
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit_dependency(artifact_id: str) -> None:
        if artifact_id in visited:
            return
        if artifact_id in visiting:
            errors.append(("visual.render_artifacts", f"artifact dependency cycle includes {artifact_id!r}"))
            return
        visiting.add(artifact_id)
        for dependency_id in dependency_graph.get(artifact_id, set()):
            if dependency_id in dependency_graph:
                visit_dependency(dependency_id)
        visiting.remove(artifact_id)
        visited.add(artifact_id)

    for declared_id in dependency_graph:
        visit_dependency(declared_id)

    for index, artifact in enumerate(artifacts):
        location = f"visual.render_artifacts[{index}]"
        artifact_id = artifact.get("artifact_id", "")
        if artifact_id in seen_artifacts:
            errors.append((f"{location}.artifact_id", f"duplicates visual.render_artifacts[{seen_artifacts[artifact_id]}].artifact_id"))
        elif artifact_id:
            seen_artifacts[artifact_id] = index

        dependencies = artifact.get("depends_on_artifact_ids", [])
        for dependency_index, dependency_id in enumerate(dependencies):
            if dependency_id == artifact_id:
                errors.append((f"{location}.depends_on_artifact_ids[{dependency_index}]", "artifact cannot depend on itself"))
            elif dependency_id not in declared_artifacts:
                errors.append((f"{location}.depends_on_artifact_ids[{dependency_index}]", f"unknown artifact dependency {dependency_id!r}"))

        layout_intent = artifact.get("layout_intent")
        if layout_intent and layout_intent not in layout_registry:
            errors.append((f"{location}.layout_intent", f"unregistered layout intent {layout_intent!r}"))

        renderer = artifact.get("renderer")
        renderer_config = renderer_registry.get(renderer)
        if not renderer_config:
            errors.append((f"{location}.renderer", f"unregistered renderer {renderer!r}"))
        else:
            selection_policy = renderer_config.get("selection_policy")
            explicit_enabled = artifact.get("renderer_options", {}).get("explicit_adapter") is True
            if selection_policy == "disabled":
                errors.append((f"{location}.renderer", f"renderer {renderer!r} is disabled"))
            elif renderer_config.get("enabled") is not True:
                if selection_policy != "explicit-item-only" or not explicit_enabled:
                    errors.append((f"{location}.renderer", f"renderer {renderer!r} is off by default; set renderer_options.explicit_adapter=true on this artifact"))
            elif selection_policy == "explicit-item-only" and not explicit_enabled:
                errors.append((f"{location}.renderer_options.explicit_adapter", "explicit-item-only renderer requires true"))

            supported_formats = renderer_config.get("formats", [])
            if artifact.get("format") not in supported_formats:
                errors.append((f"{location}.format", f"renderer {renderer!r} does not support {artifact.get('format')!r}"))

        try:
            required_hard_checks(artifact)
        except ValueError as exc:
            errors.append((f"{location}.qa_profile", str(exc)))

        for asset_index, asset_id in enumerate(artifact.get("asset_ids", [])):
            source_index = asset_ids.get(asset_id)
            if source_index is None:
                errors.append((f"{location}.asset_ids[{asset_index}]", f"unknown asset_id {asset_id!r}"))
                continue
            asset = assets[source_index]
            if asset.get("rights_status") != "verified":
                errors.append((f"{location}.asset_ids[{asset_index}]", "artifact assets require verified rights"))
            if asset.get("privacy_status") in {"needs-review", "blocked"}:
                errors.append((f"{location}.asset_ids[{asset_index}]", "artifact assets require cleared privacy status"))

        for input_index, input_ref in enumerate(artifact.get("input_refs", [])):
            input_path = resolve_local_ref(input_ref, item_path)
            if input_path.exists():
                continue
            upstream = declared_outputs.get(input_path)
            upstream_id = upstream.get("artifact_id") if upstream else None
            if upstream_id and upstream_id in artifact.get(
                "depends_on_artifact_ids", []
            ):
                continue
            errors.append((f"{location}.input_refs[{input_index}]", f"missing local input: {input_ref}"))

        if artifact.get("renderer") == "antv-infographic":
            input_refs = artifact.get("input_refs", [])
            if len(input_refs) != 1:
                errors.append((f"{location}.input_refs", "AntV artifacts require exactly one input"))
            elif resolve_local_ref(input_refs[0], item_path).exists():
                try:
                    budget_errors = validate_antv_budget(
                        resolve_local_ref(input_refs[0], item_path),
                        artifact.get("template", ""),
                        artifact.get("layout_intent", ""),
                    )
                except (OSError, RuntimeError, json.JSONDecodeError) as exc:
                    budget_errors = [f"budget inspection failed: {exc}"]
                errors.extend((f"{location}.template", message) for message in budget_errors)

        if artifact.get("renderer") == "lieflat-charts":
            try:
                DATA_SPEC_VERSION, _, validate_data_spec = _import_data_explanations()
            except ModuleNotFoundError as exc:
                if exc.name != "render_data_explanations":
                    raise
                errors.append((f"{location}.renderer", _missing_data_backend_error()))
            else:
                input_refs = artifact.get("input_refs", [])
                legacy_refs = []
                for ref in input_refs:
                    candidate = resolve_local_ref(ref, item_path)
                    if candidate.exists() and candidate.suffix.casefold() == ".json":
                        try:
                            if _load_json(candidate).get("schema_version") == DATA_SPEC_VERSION:
                                legacy_refs.append(ref)
                        except (OSError, json.JSONDecodeError):
                            pass
                if len(input_refs) not in {1, 2} or len(legacy_refs) != 1:
                    errors.append((f"{location}.input_refs", "data-explanation artifacts require exactly one legacy chart spec and may include one normalized contract"))
                elif resolve_local_ref(legacy_refs[0], item_path).exists():
                    spec_path = resolve_local_ref(legacy_refs[0], item_path)
                    if spec_path.suffix.casefold() != ".json":
                        errors.append((f"{location}.input_refs[0]", "data-explanation input must be JSON"))
                    else:
                        try:
                            chart_spec = _load_json(spec_path)
                        except (OSError, json.JSONDecodeError) as exc:
                            errors.append((f"{location}.input_refs[0]", f"invalid data chart spec: {exc}"))
                        else:
                            errors.extend(
                                (f"{location}.input_refs[0]", message)
                                for message in validate_data_spec(chart_spec, spec_path)
                            )

        if artifact.get("renderer") == "ppt-master":
            input_refs = artifact.get("input_refs", [])
            options = artifact.get("renderer_options", {})
            operation = options.get("operation", "generate")
            allowed_operations = (
                (renderer_config or {}).get("operations", {}).get("allowed", ["generate"])
            )
            if operation not in allowed_operations:
                errors.append((f"{location}.renderer_options.operation", f"must be one of {allowed_operations!r}"))
            elif operation == "generate":
                if len(input_refs) != 1:
                    errors.append((f"{location}.input_refs", "PPT Master generate requires exactly one structured brief input"))
                elif resolve_local_ref(input_refs[0], item_path).exists():
                    brief_path = resolve_local_ref(input_refs[0], item_path)
                    if brief_path.suffix.casefold() != ".json":
                        errors.append((f"{location}.input_refs[0]", "PPT Master input must be ai-ppt-brief.v1 JSON"))
                    else:
                        try:
                            brief = _load_json(brief_path)
                        except (OSError, json.JSONDecodeError) as exc:
                            errors.append((f"{location}.input_refs[0]", f"invalid PPT brief: {exc}"))
                        else:
                            if brief.get("schema_version") != "ai-ppt-brief.v1":
                                errors.append((f"{location}.input_refs[0]", "PPT Master input schema must be ai-ppt-brief.v1"))
                            if brief.get("contains_sensitive_data") is not False:
                                errors.append((f"{location}.input_refs[0]", "PPT Master local adapter rejects sensitive brief input"))
                            if brief.get("external_provider_required") is not False:
                                errors.append((f"{location}.input_refs[0]", "PPT Master local adapter cannot require an external provider"))
            elif operation == "template-fill":
                if len(input_refs) != 2:
                    errors.append((f"{location}.input_refs", "PPT Master template-fill requires source PPTX and confirmed fill plan"))
                else:
                    source_path = resolve_local_ref(input_refs[0], item_path)
                    plan_path = resolve_local_ref(input_refs[1], item_path)
                    if source_path.suffix.casefold() != ".pptx":
                        errors.append((f"{location}.input_refs[0]", "template-fill source must be PPTX"))
                    if plan_path.suffix.casefold() != ".json":
                        errors.append((f"{location}.input_refs[1]", "template-fill plan must be JSON"))
                    elif plan_path.exists():
                        try:
                            fill_plan = _load_json(plan_path)
                        except (OSError, json.JSONDecodeError) as exc:
                            errors.append((f"{location}.input_refs[1]", f"invalid fill plan: {exc}"))
                        else:
                            if fill_plan.get("schema") != "template_fill_pptx_plan.v1":
                                errors.append((f"{location}.input_refs[1]", "fill plan schema must be template_fill_pptx_plan.v1"))
                            if fill_plan.get("status") != "confirmed":
                                errors.append((f"{location}.input_refs[1]", "fill plan status must be confirmed"))
                            if any(slide.get("table_edits") for slide in fill_plan.get("slides", [])) or any(slide.get("chart_edits") for slide in fill_plan.get("slides", [])):
                                errors.append((f"{location}.input_refs[1]", "M2 template-fill accepts text replacements only"))
                if options.get("template_fill_plan_confirmed") is not True:
                    errors.append((f"{location}.renderer_options.template_fill_plan_confirmed", "must be true after explicit plan review"))
            elif operation == "data-native":
                try:
                    _, render_data_svg, validate_data_spec = _import_data_explanations()
                except ModuleNotFoundError as exc:
                    if exc.name != "render_data_explanations":
                        raise
                    errors.append((f"{location}.renderer", _missing_data_backend_error()))
                else:
                    data_spec: dict[str, Any] | None = None
                    if len(input_refs) not in {2, 3}:
                        errors.append((f"{location}.input_refs", "PPT Master data-native requires chart spec and SVG fallback, with an optional normalized contract"))
                    else:
                        spec_path = resolve_local_ref(input_refs[0], item_path)
                        fallback_path = resolve_local_ref(input_refs[1], item_path)
                        if spec_path.suffix.casefold() != ".json":
                            errors.append((f"{location}.input_refs[0]", "data-native source must be a JSON chart spec"))
                        elif spec_path.exists():
                            try:
                                data_spec = _load_json(spec_path)
                            except (OSError, json.JSONDecodeError) as exc:
                                errors.append((f"{location}.input_refs[0]", f"invalid data chart spec: {exc}"))
                            else:
                                for message in validate_data_spec(data_spec, spec_path):
                                    errors.append((f"{location}.input_refs[0]", message))
                                try:
                                    project_native_payload(data_spec)
                                except ProjectionError as exc:
                                    errors.append((f"{location}.input_refs[0]", str(exc)))
                        if fallback_path.suffix.casefold() != ".svg":
                            errors.append((f"{location}.input_refs[1]", "data-native fallback must be SVG"))
                        elif fallback_path.exists() and data_spec is not None:
                            if fallback_path.read_text(encoding="utf-8") != render_data_svg(data_spec):
                                errors.append((f"{location}.input_refs[1]", "SVG fallback is stale relative to the chart spec"))

                        fallback_artifact_id = options.get("fallback_artifact_id")
                        dependencies = artifact.get("depends_on_artifact_ids", [])
                        if not fallback_artifact_id:
                            errors.append((f"{location}.renderer_options.fallback_artifact_id", "data-native requires an explicit fallback artifact"))
                        elif fallback_artifact_id not in dependencies:
                            errors.append((f"{location}.depends_on_artifact_ids", "must include renderer_options.fallback_artifact_id"))
                        else:
                            fallback_artifact = declared_artifacts.get(fallback_artifact_id)
                            if fallback_artifact:
                                if fallback_artifact.get("renderer") != "lieflat-charts" or fallback_artifact.get("format") != "svg":
                                    errors.append((f"{location}.renderer_options.fallback_artifact_id", "must reference a lieflat-charts SVG artifact"))
                                fallback_ref = fallback_artifact.get("ref")
                                if fallback_ref and not _same_ref(input_refs[1], fallback_ref, item_path):
                                    errors.append((f"{location}.input_refs[1]", "must match the declared fallback artifact output"))
            if artifact.get("asset_ids"):
                errors.append((f"{location}.asset_ids", "PPT Master local adapter does not accept content assets"))
            expected_protocol = (renderer_config or {}).get("protocol")
            if options.get("ppt_master_protocol") != expected_protocol:
                errors.append((f"{location}.renderer_options.ppt_master_protocol", f"must explicitly select pinned protocol {expected_protocol!r}"))
            if "ppt_master_root" in options:
                errors.append((f"{location}.renderer_options.ppt_master_root", "source root is registry-owned and cannot be overridden by an item"))
            if (renderer_config or {}).get("external_provider_required") is not False:
                errors.append((f"{location}.renderer", "PPT Master registry must keep external providers disabled"))
            if (renderer_config or {}).get("remote_downloads_enabled") is not False:
                errors.append((f"{location}.renderer", "PPT Master registry must keep remote downloads disabled"))
            if (renderer_config or {}).get("visual_validation_required") is not True:
                errors.append((f"{location}.renderer", "PPT Master registry must require render and overflow validation"))

        if artifact.get("renderer") == "marp":
            errors.extend(
                (f"{location}.renderer_options.copy", message)
                for message in validate_marp_budget(artifact)
            )
            if artifact.get("theme") not in {"cover-photo-overlay", "section-photo-overlay"}:
                errors.append((f"{location}.theme", "Marp requires a registered photo-overlay theme"))
            background_id = artifact.get("renderer_options", {}).get("background_asset_id")
            if not background_id:
                errors.append((f"{location}.renderer_options.background_asset_id", "Marp requires a background asset"))
            elif background_id not in artifact.get("asset_ids", []):
                errors.append((f"{location}.renderer_options.background_asset_id", "must also be listed in artifact.asset_ids"))
            elif background_id in asset_ids:
                background_asset = assets[asset_ids[background_id]]
                if not background_asset.get("safe_crop"):
                    errors.append((f"visual.assets[{asset_ids[background_id]}].safe_crop", "Marp background requires safe-crop metadata"))
                background_ref = str(background_asset.get("ref", ""))
                if background_ref.casefold().startswith(("http://", "https://")):
                    errors.append((f"visual.assets[{asset_ids[background_id]}].ref", "Marp background must be a registered local file"))

        if artifact.get("renderer") == "baoyu-md":
            input_refs = artifact.get("input_refs", [])
            if len(input_refs) != 1:
                errors.append((f"{location}.input_refs", "Baoyu Markdown requires exactly one input"))
            elif resolve_local_ref(input_refs[0], item_path).exists():
                markdown_path = resolve_local_ref(input_refs[0], item_path)
                if markdown_path.suffix.casefold() not in {".md", ".markdown"}:
                    errors.append((f"{location}.input_refs[0]", "Baoyu input must be Markdown"))
                else:
                    markdown = markdown_path.read_text(encoding="utf-8")
                    remote_images = [
                        ref
                        for ref in _markdown_image_refs(markdown)
                        if ref.casefold().startswith(("http://", "https://"))
                    ]
                    if remote_images:
                        errors.append((f"{location}.input_refs[0]", "Baoyu remote image downloads are disabled"))
                    if "![[http://" in markdown.casefold() or "![[https://" in markdown.casefold():
                        errors.append((f"{location}.input_refs[0]", "Baoyu remote image wikilinks are disabled"))
                    if "<img" in markdown.casefold():
                        errors.append((f"{location}.input_refs[0]", "Baoyu raw HTML images are not accepted"))
            baoyu_config = renderer_config or {}
            if artifact.get("theme") not in baoyu_config.get("themes", []):
                errors.append((f"{location}.theme", "Baoyu theme must be pinned in the renderer registry"))
            if baoyu_config.get("remote_downloads_enabled") is not False:
                errors.append((f"{location}.renderer", "Baoyu renderer registry must disable remote downloads"))
            for asset_id in artifact.get("asset_ids", []):
                source_index = asset_ids.get(asset_id)
                if source_index is None:
                    continue
                asset_ref = str(assets[source_index].get("ref", ""))
                if asset_ref.casefold().startswith(("http://", "https://")):
                    errors.append((f"visual.assets[{source_index}].ref", "Baoyu accepts registered local assets only"))

        if artifact.get("renderer") == "obsidian-infographic-preview":
            preview_config = renderer_config or {}
            if artifact.get("input_refs"):
                errors.append((f"{location}.input_refs", "Obsidian preview uses only its pinned source checkout"))
            if artifact.get("asset_ids"):
                errors.append((f"{location}.asset_ids", "Obsidian preview does not consume content assets"))
            if preview_config.get("boundary") != "build-package-only-no-install-no-vault-write":
                errors.append((f"{location}.renderer", "Obsidian preview build-only boundary is missing"))
            preview_ref = str(artifact.get("ref", ""))
            if preview_ref and ".obsidian" in {
                part.casefold() for part in resolve_local_ref(preview_ref, item_path).parts
            }:
                errors.append((f"{location}.ref", "Obsidian preview cannot target a vault plugin directory"))

        output_ref = artifact.get("ref", "")
        receipt_ref = artifact.get("receipt_ref", "")
        output_path = resolve_local_ref(output_ref, item_path) if output_ref else None
        produced = artifact.get("status") in PRODUCED_STATUSES or bool(
            output_path and output_path.exists()
        )
        if produced and not output_ref:
            errors.append((f"{location}.ref", "produced artifacts require an output ref"))
        if output_ref:
            if output_path in seen_outputs:
                errors.append((f"{location}.ref", f"duplicates visual.render_artifacts[{seen_outputs[output_path]}].ref"))
            else:
                seen_outputs[output_path] = index
            if produced and not output_path.exists():
                errors.append((f"{location}.ref", f"missing rendered output: {output_ref}"))
        if produced and not receipt_ref:
            errors.append((f"{location}.receipt_ref", "produced artifacts require a render receipt"))
        elif produced and not resolve_local_ref(receipt_ref, item_path).exists():
            errors.append((f"{location}.receipt_ref", f"missing render receipt: {receipt_ref}"))
        elif receipt_ref and resolve_local_ref(receipt_ref, item_path).exists():
            errors.extend(_validate_receipt(item, item_path, artifact, location))

    legacy_refs = visual.get("render_recipe", {}).get("output_refs", [])
    if legacy_refs and artifacts:
        artifact_refs = [artifact.get("ref") for artifact in artifacts if artifact.get("ref")]
        for index, legacy_ref in enumerate(legacy_refs):
            if not any(_same_ref(legacy_ref, artifact_ref, item_path) for artifact_ref in artifact_refs):
                errors.append((f"visual.render_recipe.output_refs[{index}]", "legacy output must also be registered as a render artifact"))

    uses_imagegen = any(artifact.get("renderer") == "imagegen" for artifact in artifacts)
    if uses_imagegen and not is_ai_image_generation_authorized(visual.get("ai_image_generation")):
        errors.append((
            "visual.ai_image_generation",
            "imagegen artifact requires user-request evidence containing 模型生成图片 or AI 生图",
        ))

    return errors
