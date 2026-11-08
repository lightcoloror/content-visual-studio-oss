#!/usr/bin/env python3
"""Resolve and validate explicit opt-in for AI image generation.

Boundary (important): the strings, ``explicit_user_request`` flag and
``matched_trigger`` value handled here are caller-provided *record
consistency* data. Deterministic text matching proves only that a recorded
quote contains a trigger phrase; it is not proof of a native user's consent and
it is never permission to execute a protected tool, publish an artifact or
spend money. No image generation, model call, network request or filesystem
write happens in this module.
"""

from __future__ import annotations

import re
from typing import Any


AI_IMAGE_POLICY = "explicit-opt-in-only"
AI_IMAGE_TRIGGER_PATTERNS = (
    re.compile(r"模型\s*生成\s*图片", re.IGNORECASE),
    re.compile(r"AI\s*生图", re.IGNORECASE),
)


def resolve_ai_image_generation(request_text: str) -> dict[str, Any]:
    """Return a deterministic opt-in decision from the user's exact request.

    The decision is derived only from the supplied text. It records what a
    caller claims the user wrote; it does not authenticate the caller or the
    claim.
    """

    for pattern in AI_IMAGE_TRIGGER_PATTERNS:
        match = pattern.search(request_text)
        if match:
            return {
                "policy": AI_IMAGE_POLICY,
                "allowed": True,
                "matched_trigger": match.group(0),
                "decision": "allow_ai_image_generation_route",
            }
    return {
        "policy": AI_IMAGE_POLICY,
        "allowed": False,
        "matched_trigger": None,
        "decision": "use_non_generated_visual_route",
    }


def is_ai_image_generation_authorized(gate: Any) -> bool:
    """Return true only when the recorded user quote deterministically authorizes generation.

    This is structural record consistency, not proof of a real user's consent
    and not authorization to run any generation tool.
    """

    if not isinstance(gate, dict) or gate.get("explicit_user_request") is not True:
        return False
    request_text = gate.get("request_text")
    if not isinstance(request_text, str):
        return False
    decision = resolve_ai_image_generation(request_text)
    return bool(
        decision["allowed"]
        and gate.get("matched_trigger") == decision.get("matched_trigger")
    )


def validate_ai_image_generation_opt_in(
    item: dict[str, Any],
) -> list[tuple[str, str]]:
    """Reject generated-image/imagegen usage without an explicit request quote.

    Passing this structural check only means the recorded metadata is
    internally consistent. It does not grant execution permission.
    """

    visual = item.get("visual", {})
    renderer = visual.get("render_recipe", {}).get("renderer")
    artifact_renderers = {
        artifact.get("renderer")
        for artifact in visual.get("render_artifacts", [])
        if isinstance(artifact, dict)
    }
    uses_generated_asset = any(
        asset.get("asset_type") == "generated-image"
        for asset in visual.get("assets", [])
    )
    uses_ai_route = renderer == "imagegen" or "imagegen" in artifact_renderers or uses_generated_asset
    if not uses_ai_route:
        return []

    gate = visual.get("ai_image_generation")
    if not isinstance(gate, dict):
        return [
            (
                "visual.ai_image_generation",
                "imagegen/generated-image requires explicit user opt-in evidence",
            )
        ]

    errors: list[tuple[str, str]] = []
    if gate.get("policy") != AI_IMAGE_POLICY:
        errors.append(
            (
                "visual.ai_image_generation.policy",
                f"policy must be {AI_IMAGE_POLICY}",
            )
        )
    if gate.get("explicit_user_request") is not True:
        errors.append(
            (
                "visual.ai_image_generation.explicit_user_request",
                "AI image generation must be explicitly requested by the user",
            )
        )

    request_text = gate.get("request_text", "")
    decision = resolve_ai_image_generation(request_text) if isinstance(request_text, str) else None
    if not decision or not decision["allowed"]:
        errors.append(
            (
                "visual.ai_image_generation.request_text",
                "request_text must contain 模型生成图片 or AI 生图",
            )
        )
    elif gate.get("matched_trigger") != decision["matched_trigger"]:
        errors.append(
            (
                "visual.ai_image_generation.matched_trigger",
                "matched_trigger must equal the trigger extracted from request_text",
            )
        )
    if not errors and not is_ai_image_generation_authorized(gate):
        errors.append(
            (
                "visual.ai_image_generation",
                "recorded AI image-generation evidence is not authorized",
            )
        )
    return errors
