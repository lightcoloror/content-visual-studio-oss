"""Deterministic checks for article illustration plans."""

from __future__ import annotations
from studio_paths import STUDIO_ROOT

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


SELECTED_STATUSES = {"selected", "inserted"}
SEARCH_ROUTES = {"stock-photo", "icon"}
PHOTO_ROUTES = {"personal-photo", "work-detail-photo", "stock-photo"}
SOURCE_REGISTRY_PATH = STUDIO_ROOT / "config/visual-source-registry.json"


@lru_cache(maxsize=1)
def load_visual_source_registry() -> dict[str, Any]:
    with SOURCE_REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_selected_stock_asset(asset: dict[str, Any]) -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []
    source_id = asset.get("source_id", "")
    sources = load_visual_source_registry().get("sources", {})
    source = sources.get(source_id)

    if not source_id:
        errors.append(("source_id", "selected stock photos require a registered source_id"))
    elif source is None:
        errors.append(("source_id", f"unknown visual source {source_id!r}"))
    elif source.get("selection_policy") == "original-source-required":
        errors.append(("source_id", f"{source_id!r} is a discovery layer; register the original provider instead"))

    for field in ("landing_page_url", "license", "license_url"):
        if not asset.get(field):
            errors.append((field, f"selected stock photos require {field}"))

    if asset.get("usage_scope") != "commercial":
        errors.append(("usage_scope", "selected stock photos require confirmed commercial scope"))

    attribution_required = asset.get("attribution_required")
    if attribution_required is None:
        errors.append(("attribution_required", "selected stock photos must record whether attribution is required"))
    if source and source.get("attribution_policy") == "required" and attribution_required is not True:
        errors.append(("attribution_required", f"{source_id!r} requires attribution"))
    if attribution_required is True and not asset.get("attribution"):
        errors.append(("attribution", "required attribution text is missing"))

    if asset.get("release_status") not in {"verified", "not-guaranteed", "not-applicable"}:
        errors.append(("release_status", "selected stock photos require a recorded model/property release assessment"))

    return errors


def validate_article_visual_plan(item: dict[str, Any]) -> list[tuple[str, str]]:
    visual = item.get("visual", {})
    plan = visual.get("article_visual_plan")
    if not plan:
        return []

    errors: list[tuple[str, str]] = []
    assets = visual.get("assets", [])
    assets_by_ref = {asset.get("ref"): asset for asset in assets if asset.get("ref")}
    seen_slot_ids: set[str] = set()
    selected_routes: list[str] = []

    article_ref = plan.get("article_ref", "")
    if not article_ref.lower().endswith((".md", ".markdown")):
        errors.append(("visual.article_visual_plan.article_ref", "must reference a Markdown article"))

    for index, slot in enumerate(plan.get("slots", [])):
        location = f"visual.article_visual_plan.slots[{index}]"
        slot_id = slot.get("slot_id", "")
        if slot_id in seen_slot_ids:
            errors.append((f"{location}.slot_id", f"duplicates article visual slot {slot_id!r}"))
        seen_slot_ids.add(slot_id)

        route = slot.get("route")
        role = slot.get("media_role")
        status = slot.get("status")
        search = slot.get("search")
        selected_ref = slot.get("selected_asset_ref", "")
        brief = slot.get("visual_brief") or {}

        if route in PHOTO_ROUTES and brief and brief.get("max_labels") != 0:
            errors.append((f"{location}.visual_brief.max_labels", "real-photo slots require zero in-image labels"))

        if status in SELECTED_STATUSES:
            selected_routes.append(route)

        if route in SEARCH_ROUTES and status not in {"blocked", "skipped"} and not search:
            errors.append((f"{location}.search", f"{route} slots require a structured search intent"))

        if role == "evidence" and route in {"stock-photo", "generated-image"}:
            errors.append((f"{location}.route", "stock or generated images cannot serve as factual evidence"))

        if route == "generated-image":
            gate = visual.get("ai_image_generation", {})
            if gate.get("explicit_user_request") is not True:
                errors.append((f"{location}.route", "generated-image requires explicit user opt-in"))

        if status in SELECTED_STATUSES and not selected_ref:
            errors.append((f"{location}.selected_asset_ref", f"status {status!r} requires a selected asset"))
            continue

        if selected_ref:
            asset = assets_by_ref.get(selected_ref)
            if not asset:
                errors.append((f"{location}.selected_asset_ref", "must match visual.assets[].ref"))
                continue
            if asset.get("rights_status") != "verified":
                errors.append((f"{location}.selected_asset_ref", "selected article assets require verified rights"))
            if asset.get("asset_type") == "stock-photo":
                for field, message in validate_selected_stock_asset(asset):
                    errors.append((f"visual.assets[{selected_ref!r}].{field}", message))
            if asset.get("fit_strategy") == "focal-cover" and not asset.get("focal_point"):
                errors.append((f"visual.assets[{selected_ref!r}].focal_point", "focal-cover requires a focal point"))
            if not slot.get("alt_text") and not asset.get("alt_text"):
                errors.append((f"{location}.alt_text", "selected article assets require meaningful alt text"))

    if plan.get("visual_mode") == "editorial-photo-mix":
        photo_count = sum(route in PHOTO_ROUTES for route in selected_routes)
        icon_count = selected_routes.count("icon")
        if photo_count == 0:
            errors.append(("visual.article_visual_plan.visual_mode", "editorial-photo-mix requires a selected photo"))
        if icon_count > 1 or icon_count > photo_count:
            errors.append(("visual.article_visual_plan.visual_mode", "editorial-photo-mix keeps icons secondary: at most one icon and never more icons than photos"))

    return errors
