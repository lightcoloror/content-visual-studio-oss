#!/usr/bin/env python3
"""Resolve media QA profiles and validate receipt-level QA invariants.

Public-edition adaptation: the profile registry is now a shipped first-party
resource resolved through ``studio_paths.STUDIO_ROOT`` (source tree and
installed ``studio_assets`` layouts). An explicit
``CONTENT_STUDIO_MEDIA_QA_PROFILES`` path overrides the default, and a missing
or malformed registry fails closed. All receipt-level invariants are unchanged.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from studio_paths import STUDIO_ROOT


CONFIG_ENV = "CONTENT_STUDIO_MEDIA_QA_PROFILES"
EXPECTED_SCHEMA_VERSION = "media-qa-profiles.v1"


def default_config_path() -> Path:
    explicit = os.environ.get(CONFIG_ENV, "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return (STUDIO_ROOT / "config" / "media-qa-profiles.v1.json").resolve()


CONFIG_PATH = default_config_path()


@lru_cache(maxsize=1)
def load_media_qa_profiles() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict) or config.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise ValueError(
            f"media QA profile registry schema_version must be {EXPECTED_SCHEMA_VERSION!r}"
        )
    if not isinstance(config.get("profiles"), dict):
        raise ValueError("media QA profile registry is missing its profiles map")
    return config


def resolve_media_qa_profile(artifact: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    config = load_media_qa_profiles()
    profiles = config.get("profiles", {})
    explicit_profile = artifact.get("qa_profile")
    if explicit_profile:
        profile = profiles.get(explicit_profile)
        if profile is None:
            raise ValueError(f"unknown media QA profile {explicit_profile!r}")
        candidates = [(explicit_profile, profile)]
    else:
        candidates = [
            (profile_id, profile)
            for profile_id, profile in profiles.items()
            if artifact.get("media_adapter") in profile.get("media_adapters", [])
            and artifact.get("format") in profile.get("formats", [])
        ]

    applicable = [
        (profile_id, profile)
        for profile_id, profile in candidates
        if artifact.get("media_adapter") in profile.get("media_adapters", [])
        and artifact.get("format") in profile.get("formats", [])
    ]
    if not applicable:
        raise ValueError(
            "no media QA profile covers "
            f"media_adapter={artifact.get('media_adapter')!r}, format={artifact.get('format')!r}"
        )
    if len(applicable) > 1:
        profile_ids = ", ".join(profile_id for profile_id, _ in applicable)
        raise ValueError(f"ambiguous media QA profiles: {profile_ids}")
    return applicable[0]


def required_hard_checks(artifact: dict[str, Any]) -> tuple[str, set[str]]:
    config = load_media_qa_profiles()
    profile_id, profile = resolve_media_qa_profile(artifact)
    required = set(config.get("common_required_hard_checks", []))
    required.update(profile.get("required_hard_checks", []))
    required.update(
        config.get("renderer_required_hard_checks", {}).get(artifact.get("renderer"), [])
    )
    operation = artifact.get("renderer_options", {}).get("operation", "generate")
    required.update(
        config.get("renderer_operation_required_hard_checks", {})
        .get(artifact.get("renderer"), {})
        .get(operation, [])
    )
    if artifact.get("renderer_options", {}).get("global_visual_v1") is True:
        required.update(config.get("global_visual_required_hard_checks", []))
    return profile_id, required


def validate_receipt_qa(
    artifact: dict[str, Any], qa: dict[str, Any]
) -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []
    try:
        expected_profile, required = required_hard_checks(artifact)
    except ValueError as exc:
        return [("profile_id", str(exc))]

    if qa.get("profile_id") != expected_profile:
        errors.append(
            (
                "profile_id",
                f"must be {expected_profile!r} for this media adapter and format",
            )
        )

    hard_checks = qa.get("hard_checks", [])
    names = [check.get("name") for check in hard_checks]
    duplicate_names = sorted({name for name in names if name and names.count(name) > 1})
    if duplicate_names:
        errors.append(("hard_checks", f"duplicate hard checks: {', '.join(duplicate_names)}"))
    missing = sorted(required.difference(name for name in names if name))
    if missing:
        errors.append(("hard_checks", f"missing required hard checks: {', '.join(missing)}"))

    hard_failed = any(check.get("status") != "pass" for check in hard_checks)
    review_checks = qa.get("review_checks", [])
    actual_needs_review = sum(
        check.get("status") == "needs-review" for check in review_checks
    )
    if qa.get("needs_review_count") != actual_needs_review:
        errors.append(("needs_review_count", f"must equal actual count {actual_needs_review}"))

    max_needs_review = int(
        load_media_qa_profiles().get("policy", {}).get("max_needs_review", 1)
    )
    if actual_needs_review > max_needs_review:
        errors.append(
            (
                "review_checks",
                f"at most {max_needs_review} needs-review finding may enter human review",
            )
        )

    expected_result = (
        "fail" if hard_failed else ("review-required" if actual_needs_review else "pass")
    )
    if qa.get("result") != expected_result:
        errors.append(("result", f"must be {expected_result!r} for the recorded checks"))
    return errors
