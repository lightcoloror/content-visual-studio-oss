#!/usr/bin/env python3
"""Budget checks backed by AntV's own syntax parser and the shared registry."""

from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


from studio_paths import STUDIO_ROOT
BUDGET_PATH = STUDIO_ROOT / "config" / "slot-budgets.v1.json"
RENDERER_REGISTRY_PATH = STUDIO_ROOT / "config" / "renderer-registry.v1.json"
LAYOUT_REGISTRY_PATH = STUDIO_ROOT / "config" / "layout-intents.v1.json"
INSPECTOR_PATH = STUDIO_ROOT / "scripts" / "inspect_antv_input.mjs"


@lru_cache(maxsize=None)
def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def count_chars(value: Any) -> int:
    return len("".join(str(value or "").split()))


def inspect_antv_input(input_path: Path) -> dict[str, Any]:
    renderer = load_json(RENDERER_REGISTRY_PATH)["renderers"]["antv-infographic"]
    runtime_root = os.environ.get(renderer.get("runtime_root_env", "CONTENT_STUDIO_ANTV_MODULE_ROOT")) or renderer.get("local_path")
    if not runtime_root:
        raise RuntimeError("antv_module_root_required")
    result = subprocess.run(
        [
            os.environ.get("CONTENT_STUDIO_NODE", "node"),
            str(INSPECTOR_PATH),
            "--module-root",
            str(runtime_root),
            "--input",
            str(input_path),
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"AntV parser exited {result.returncode}")
    return json.loads(result.stdout)


def flatten_items(items: list[dict[str, Any]], depth: int = 1) -> Iterable[tuple[dict[str, Any], int]]:
    for item in items:
        yield item, depth
        children = item.get("children")
        if isinstance(children, list):
            yield from flatten_items(children, depth + 1)


def validate_antv_budget(input_path: Path, template: str, layout_intent: str) -> list[str]:
    budget_registry = load_json(BUDGET_PATH)["antv"]
    global_budget = budget_registry["global"]
    template_budget = budget_registry["templates"].get(template)
    if not template_budget:
        return [f"template {template!r} has no registered slot budget"]
    if template_budget["layout_intent"] != layout_intent:
        return [
            f"template {template!r} is budgeted for {template_budget['layout_intent']!r}, "
            f"not {layout_intent!r}"
        ]

    parsed = inspect_antv_input(input_path)
    errors = [f"AntV syntax: {error}" for error in parsed.get("errors", [])]
    if parsed.get("template") != template:
        errors.append(
            f"parsed template {parsed.get('template')!r} does not match artifact template {template!r}"
        )
    data = parsed.get("data") or {}
    if count_chars(data.get("title")) > global_budget["title_max_chars"]:
        errors.append(f"title exceeds {global_budget['title_max_chars']} characters")

    items = data.get("items") if isinstance(data.get("items"), list) else []
    flattened = list(flatten_items(items))
    descriptions = [data.get("desc", "")]
    descriptions.extend(item.get("desc", "") for item, _ in flattened)
    if any(count_chars(value) > global_budget["description_max_chars"] for value in descriptions):
        errors.append(f"description exceeds {global_budget['description_max_chars']} characters")
    if any(count_chars(item.get("label")) > global_budget["label_max_chars"] for item, _ in flattened):
        errors.append(f"item label exceeds {global_budget['label_max_chars']} characters")

    count_rule = template_budget["item_count"]
    count = len(items) if count_rule.get("scope") == "top-level" else len(flattened)
    if "exact" in count_rule and count != count_rule["exact"]:
        errors.append(f"item count must equal {count_rule['exact']}, got {count}")
    if "min" in count_rule and count < count_rule["min"]:
        errors.append(f"item count must be at least {count_rule['min']}, got {count}")
    if "max" in count_rule and count > count_rule["max"]:
        errors.append(f"item count must be at most {count_rule['max']}, got {count}")

    max_depth = max((depth for _, depth in flattened), default=0)
    if template_budget.get("max_depth") is not None and max_depth > template_budget["max_depth"]:
        errors.append(f"tree depth must be at most {template_budget['max_depth']}, got {max_depth}")
    return errors


def validate_marp_budget(artifact: dict[str, Any]) -> list[str]:
    budget = load_json(BUDGET_PATH)["marp"]
    copy = artifact.get("renderer_options", {}).get("copy", {})
    errors: list[str] = []
    fields = {
        "title": budget["title_max_chars"],
        "supporting_copy": budget["supporting_copy_max_chars"],
        "source": budget["source_max_chars"],
    }
    for field, limit in fields.items():
        value = copy.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Marp renderer_options.copy.{field} is required")
        elif count_chars(value) > limit:
            errors.append(f"Marp {field} exceeds {limit} characters")
    return errors


def validate_budget_registry_coverage() -> list[str]:
    budgets = load_json(BUDGET_PATH)["antv"]["templates"]
    layouts = load_json(LAYOUT_REGISTRY_PATH)["intents"]
    errors: list[str] = []
    for intent, config in layouts.items():
        for template in config.get("antv_templates", []):
            if template not in budgets:
                errors.append(f"layout {intent!r} references template {template!r} without a budget")
            elif budgets[template].get("layout_intent") != intent:
                errors.append(f"template {template!r} budget maps to the wrong layout intent")
    for template in budgets:
        if not any(template in config.get("antv_templates", []) for config in layouts.values()):
            errors.append(f"budgeted template {template!r} is unreachable from layout intents")
    return errors
