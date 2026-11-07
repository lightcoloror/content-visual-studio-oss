"""Fail-closed validation for explicit cross-medium design directions."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


from studio_paths import STUDIO_ROOT
DEFAULT_CONTRACT_PATH = STUDIO_ROOT / "config" / "design-directions.v1.json"
CONTRACT_ENV_VAR = "CONTENT_STUDIO_DESIGN_DIRECTIONS_CONTRACT"
DESIGN_DIRECTION_THEMES = {"editorial-field-guide", "reflective-personal-essay"}


def resolve_design_directions_path(contract_path: Path | str | None = None) -> Path:
    """Resolve the repository snapshot or an explicit operator override.

    The override is intentionally opt-in.  The validator never guesses a sibling
    checkout, workstation root, or downloaded design-system location.
    """

    if contract_path is not None:
        candidate = Path(contract_path)
    else:
        override = os.environ.get(CONTRACT_ENV_VAR, "").strip()
        candidate = Path(override) if override else DEFAULT_CONTRACT_PATH
    return candidate.expanduser().resolve()


@lru_cache(maxsize=8)
def _load_design_directions_cached(resolved_path: str) -> dict[str, Any]:
    path = Path(resolved_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"design-directions contract is missing: {path}; set {CONTRACT_ENV_VAR} "
            "to an explicit compatible contract path"
        )
    with path.open("r", encoding="utf-8") as handle:
        contract = json.load(handle)
    if contract.get("schema_version") != "shared-design-directions.v1":
        raise ValueError("design-directions contract schema_version is incompatible")
    if not isinstance(contract.get("directions"), dict):
        raise ValueError("design-directions contract must contain a directions object")
    return contract


def load_design_directions(contract_path: Path | str | None = None) -> dict[str, Any]:
    return _load_design_directions_cached(str(resolve_design_directions_path(contract_path)))


def clear_design_direction_cache() -> None:
    _load_design_directions_cached.cache_clear()


def validate_design_direction(
    item: dict[str, Any], contract_path: Path | str | None = None
) -> list[tuple[str, str]]:
    visual = item.get("visual", {})
    design_system = visual.get("design_system") or {}
    selection = design_system.get("design_direction")
    artifacts = visual.get("render_artifacts", [])
    errors: list[tuple[str, str]] = []

    if not selection:
        for index, artifact in enumerate(artifacts):
            if artifact.get("theme") in DESIGN_DIRECTION_THEMES:
                errors.append(
                    (
                        f"visual.render_artifacts[{index}].theme",
                        "registered design-direction themes require visual.design_system.design_direction",
                    )
                )
        return errors

    try:
        contract = load_design_directions(contract_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [("visual.design_system.design_direction", str(exc))]
    directions = contract.get("directions", {})

    direction_id = selection.get("direction_id", "")
    direction = directions.get(direction_id)
    location = "visual.design_system.design_direction"
    if direction is None:
        return [(f"{location}.direction_id", f"unknown design direction {direction_id!r}")]
    if selection.get("version") != direction.get("version"):
        errors.append(
            (
                f"{location}.version",
                f"must equal registered version {direction.get('version')!r}",
            )
        )

    compatible_profiles = {
        (profile.get("id"), profile.get("version"))
        for profile in direction.get("compatible_visual_profiles", [])
    }
    selected_profile = (
        visual.get("visual_profile"),
        visual.get("visual_profile_version"),
    )
    if compatible_profiles and selected_profile not in compatible_profiles:
        errors.append(
            (
                "visual.visual_profile",
                f"design direction {direction_id!r} has no semantic-token mapping for "
                f"{selected_profile[0]!r}@{selected_profile[1]!r}",
            )
        )

    media_adapter = design_system.get("media_adapter")
    route = direction.get("routes", {}).get(media_adapter)
    if route is None:
        errors.append(
            (
                "visual.design_system.media_adapter",
                f"design direction {direction_id!r} is not registered for {media_adapter!r}",
            )
        )
        return errors

    excluded = direction.get("excluded_routes", {})
    if visual.get("route") in excluded.get("visual_routes", []):
        errors.append(
            (
                "visual.route",
                f"design direction {direction_id!r} excludes visual route {visual.get('route')!r}",
            )
        )
    article_mode = (visual.get("article_visual_plan") or {}).get("visual_mode")
    if article_mode in excluded.get("article_visual_modes", []):
        errors.append(
            (
                "visual.article_visual_plan.visual_mode",
                f"design direction {direction_id!r} excludes article mode {article_mode!r}",
            )
        )

    matching_artifacts = [
        (index, artifact)
        for index, artifact in enumerate(artifacts)
        if artifact.get("media_adapter") == media_adapter
    ]
    required_theme = route.get("artifact_theme") if route.get("requires_artifact_theme") else None
    required_option = route.get("requires_renderer_option")
    for index, artifact in matching_artifacts:
        artifact_location = f"visual.render_artifacts[{index}]"
        if required_theme and artifact.get("theme") != required_theme:
            errors.append(
                (
                    f"{artifact_location}.theme",
                    f"design direction {direction_id!r} requires theme {required_theme!r}",
                )
            )
        if required_option:
            selected = (artifact.get("renderer_options") or {}).get(required_option)
            if selected != direction_id:
                errors.append(
                    (
                        f"{artifact_location}.renderer_options.{required_option}",
                        f"must explicitly select {direction_id!r}",
                    )
                )
        allowed_intents = route.get("allowed_layout_intents")
        if allowed_intents and artifact.get("layout_intent") not in allowed_intents:
            errors.append(
                (
                    f"{artifact_location}.layout_intent",
                    f"is not eligible for design direction {direction_id!r}",
                )
            )

    return errors
