#!/usr/bin/env python3
"""Validate semantic visual bindings for HTML-based infographics."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from typing import Any


RICH_INFOGRAPH_ROUTES = {"data_visualization", "explanatory_illustration"}
RICH_INFOGRAPH_RENDERERS = {"html-playwright"}
VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class SemanticContainerParser(HTMLParser):
    """Collect text and image refs inside data-semantic-id containers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.containers: dict[str, dict[str, list[str]]] = {}
        self._stack: list[tuple[str, str | None]] = []
        self._active: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        marker = attributes.get("data-semantic-id")
        if marker:
            self.containers.setdefault(marker, {"text": [], "images": []})
            self._active.append(marker)

        if tag == "img":
            src = attributes.get("src")
            if src:
                for active_marker in self._active:
                    self.containers[active_marker]["images"].append(src)

        if tag not in VOID_ELEMENTS:
            self._stack.append((tag, marker))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_ELEMENTS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        while self._stack:
            open_tag, marker = self._stack.pop()
            if marker and marker in self._active:
                self._active.remove(marker)
            if open_tag == tag:
                break

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        for marker in self._active:
            self.containers[marker]["text"].append(text)


def _path_from_ref(ref: str, item_path: Path) -> Path:
    candidate = Path(ref)
    if candidate.is_absolute():
        return candidate
    return (item_path.parent / candidate).resolve()


def _asset_matches(expected_ref: str, actual_refs: list[str]) -> bool:
    expected_name = Path(expected_ref).name.casefold()
    return any(Path(ref.split("?", 1)[0]).name.casefold() == expected_name for ref in actual_refs)


def validate_semantic_visual_map(
    item: dict[str, Any], item_path: Path
) -> list[tuple[str, str]]:
    """Return location/message pairs for semantic visual contract failures."""

    visual = item.get("visual", {})
    route = visual.get("route")
    renderer = visual.get("render_recipe", {}).get("renderer")
    semantic_map = visual.get("semantic_visual_map")
    requires_map = route in RICH_INFOGRAPH_ROUTES and renderer in RICH_INFOGRAPH_RENDERERS

    if requires_map and not semantic_map:
        return [
            (
                "visual.semantic_visual_map",
                "HTML infographic routes require semantic visual bindings; decorative assets alone are insufficient",
            )
        ]
    if not semantic_map:
        return []

    errors: list[tuple[str, str]] = []
    anchor_count = len(visual.get("cognitive_anchors", []))
    seen_variants: set[str] = set()

    for variant_index, variant in enumerate(semantic_map):
        variant_location = f"visual.semantic_visual_map[{variant_index}]"
        variant_id = variant.get("variant_id", "")
        if variant_id in seen_variants:
            errors.append((f"{variant_location}.variant_id", f"duplicate variant_id: {variant_id}"))
        seen_variants.add(variant_id)

        output_ref = variant.get("output_ref", "")
        output_path = _path_from_ref(output_ref, item_path) if output_ref else None
        parser = SemanticContainerParser()
        if not output_path or output_path.suffix.casefold() not in {".html", ".htm"}:
            errors.append((f"{variant_location}.output_ref", "semantic variant output_ref must be an HTML file"))
        elif not output_path.exists():
            errors.append((f"{variant_location}.output_ref", f"missing semantic HTML output: {output_ref}"))
        else:
            parser.feed(output_path.read_text(encoding="utf-8"))

        covered_anchors: set[int] = set()
        seen_semantics: set[str] = set()
        explanatory_count = 0
        for binding_index, binding in enumerate(variant.get("bindings", [])):
            binding_location = f"{variant_location}.bindings[{binding_index}]"
            semantic_id = binding.get("semantic_id", "")
            if semantic_id in seen_semantics:
                errors.append((f"{binding_location}.semantic_id", f"duplicate semantic_id in variant: {semantic_id}"))
            seen_semantics.add(semantic_id)

            role = binding.get("role")
            placement = binding.get("placement")
            anchor_index = binding.get("anchor_index")
            if role == "explanatory":
                explanatory_count += 1
                if placement == "background":
                    errors.append((f"{binding_location}.placement", "explanatory visuals cannot be background-only"))
                if not isinstance(anchor_index, int) or isinstance(anchor_index, bool):
                    errors.append((f"{binding_location}.anchor_index", "explanatory bindings require an anchor_index"))
                elif anchor_index < 0 or anchor_index >= anchor_count:
                    errors.append((f"{binding_location}.anchor_index", f"anchor_index must reference one of {anchor_count} cognitive anchors"))
                else:
                    covered_anchors.add(anchor_index)

            if role == "decorative":
                continue

            container = parser.containers.get(semantic_id)
            if not container:
                errors.append((f"{binding_location}.semantic_id", f'HTML lacks data-semantic-id="{semantic_id}"'))
                continue

            copy_anchor = " ".join(str(binding.get("copy_anchor", "")).split())
            container_text = " ".join(container["text"])
            if copy_anchor and copy_anchor not in container_text:
                errors.append((f"{binding_location}.copy_anchor", f'copy anchor not found inside data-semantic-id="{semantic_id}"'))

            visual_ref = binding.get("visual_ref", "")
            if visual_ref and not _asset_matches(visual_ref, container["images"]):
                errors.append((f"{binding_location}.visual_ref", f'visual is not colocated inside data-semantic-id="{semantic_id}"'))

        if explanatory_count == 0:
            errors.append((f"{variant_location}.bindings", "each infographic variant needs at least one explanatory visual"))
        missing_anchors = sorted(set(range(anchor_count)) - covered_anchors)
        if missing_anchors:
            errors.append((f"{variant_location}.bindings", f"cognitive anchors without explanatory visuals: {missing_anchors}"))

    return errors
