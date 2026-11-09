#!/usr/bin/env python3
"""Project evidence-bound chart specs into PPT Master's native chart interface.

The module owns only deterministic adaptation. PPT Master remains responsible for
SVG validation, DrawingML generation, native chart/workbook emission, and package
postflight checks.

Portable candidate: the parent renderer backend (``render_data_explanations``) is
imported lazily, only when materialization needs canonical validation/rendering.
Pure mapping and slide-SVG construction stay importable without that backend; a
missing backend fails closed as ``ProjectionError`` before any output is written.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import sys
from pathlib import Path
from typing import Any


PROJECTION_VERSION = "ppt-master-data-projection.v1"
SUPPORTED_SOURCE_TYPES = {"bar", "grouped_bar", "stacked_scenario", "mechanism"}
PALETTE = ["#245B5A", "#AD4E3D", "#4F7A68", "#7D6B91", "#B8863B"]
INK = "#243238"
BRAND = "#245B5A"
ACCENT = "#AD4E3D"
BACKGROUND = "#F7F8F5"
EXPLANATION = "#DDEBE9"
WHITE = "#FFFFFF"
MUTED = "#59696B"


class ProjectionError(RuntimeError):
    """Raised when a source cannot be projected without changing its meaning."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(value: Any) -> str:
    serialized = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(serialized)


def _number(value: Any, location: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProjectionError(f"{location} must be numeric")
    if not math.isfinite(float(value)):
        raise ProjectionError(f"{location} must be finite")
    return value


def _visible_points(series: dict[str, Any], series_index: int) -> list[dict[str, Any]]:
    points = series.get("points", [])
    if not points:
        raise ProjectionError(f"series[{series_index}] has no points")
    if any(point.get("value") is None for point in points):
        raise ProjectionError(
            f"series[{series_index}] contains missing values; native output cannot invent them"
        )
    return points


def project_native_payload(spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a closed PPT Master payload and an auditable source mapping."""

    source_type = spec.get("chart_type")
    if source_type not in SUPPORTED_SOURCE_TYPES:
        raise ProjectionError(
            f"chart_type {source_type!r} has no lossless native mapping; keep the SVG fallback"
        )
    if str(spec.get("render_status", "")).startswith("blocked"):
        raise ProjectionError("blocked data specs cannot enter native PowerPoint output")

    source_series = spec.get("series", [])
    if not source_series:
        raise ProjectionError("at least one series is required")
    normalized: list[dict[str, Any]] = []
    for series_index, series in enumerate(source_series):
        points = _visible_points(series, series_index)
        normalized.append(
            {
                "id": series.get("id"),
                "name": str(series.get("label", "")),
                "labels": [str(point.get("label", "")) for point in points],
                "values": [
                    _number(point.get("value"), f"series[{series_index}].points[{point_index}].value")
                    for point_index, point in enumerate(points)
                ],
            }
        )

    native: dict[str, Any]
    mapping: dict[str, Any] = {
        "source_chart_type": source_type,
        "lossless": True,
        "source_series_ids": [entry["id"] for entry in normalized],
        "source_point_labels": [entry["labels"] for entry in normalized],
    }
    if source_type in {"bar", "grouped_bar"}:
        categories = normalized[0]["labels"]
        if any(entry["labels"] != categories for entry in normalized[1:]):
            raise ProjectionError(
                "multi-series bars require identical ordered point labels for a lossless native mapping"
            )
        if any(value < 0 for entry in normalized for value in entry["values"]):
            raise ProjectionError(
                "bar projections currently require non-negative values so the native zero baseline can be enforced"
            )
        native = {
            # PPT Master v4.5 deliberately rejects axes on horizontal bars. A
            # vertical column keeps the same categorical length encoding while
            # allowing an explicit zero baseline and stable source order.
            "type": "column",
            "categories": categories,
            "series": [
                {"name": entry["name"], "values": entry["values"]}
                for entry in normalized
            ],
            "axes": {
                "category": {"kind": "text"},
                "value": {
                    "kind": "value",
                    "minimum": 0,
                    "major_gridlines": True,
                    "number_format": "0.0",
                },
            },
            "data_labels": {
                "show_value": True,
                "position": "outside_end",
                "number_format": "0.00",
                "font_size": 15,
                "font_family": "Microsoft YaHei",
                "bold": True,
                "color": INK,
            },
        }
        mapping["native_chart_type"] = "column"
        mapping["encoding_transform"] = {
            "from": "horizontal-bar",
            "to": "vertical-column",
            "preserved": ["category-order", "series-order", "values", "unit"],
            "reason": "PPT Master v4.5 does not support explicit axes on native horizontal bars",
        }
    elif source_type == "stacked_scenario":
        if len(normalized) != 1:
            raise ProjectionError("stacked_scenario requires exactly one source series")
        entry = normalized[0]
        if any(value < 0 for value in entry["values"]):
            raise ProjectionError("stacked_scenario requires non-negative values")
        native = {
            "type": "column",
            "grouping": "stacked",
            "categories": [str(spec.get("denominator", "总量"))],
            "series": [
                {"name": label, "values": [value]}
                for label, value in zip(entry["labels"], entry["values"])
            ],
            "axes": {
                "category": {"kind": "text"},
                "value": {
                    "kind": "value",
                    "minimum": 0,
                    "major_gridlines": True,
                },
            },
            "show_legend": True,
            "legend_position": "bottom",
            "data_labels": {
                "show_value": True,
                "position": "center",
                "number_format": "0.00",
                "font_size": 14,
                "font_family": "Microsoft YaHei",
                "bold": True,
                "color": WHITE,
            },
        }
        mapping["native_chart_type"] = "column/stacked"
        mapping["encoding_transform"] = {
            "from": "horizontal-stacked-bar",
            "to": "vertical-stacked-column",
            "preserved": ["component-order", "values", "denominator", "unit"],
            "reason": "PPT Master v4.5 does not support explicit axes on native horizontal bars",
        }
    else:
        if len(normalized) != 1:
            raise ProjectionError("mechanism charts require exactly one source series")
        if source_series[0].get("interpolation") not in {
            "none",
            "linear_between_observations",
        }:
            raise ProjectionError("mechanism interpolation is not representable as a native line")
        entry = normalized[0]
        native = {
            "type": "line",
            "line_style": "lineMarker",
            "categories": entry["labels"],
            "series": [{"name": entry["name"], "values": entry["values"]}],
            "data_labels": {
                "show_value": True,
                "position": "above",
                "font_size": 14,
                "font_family": "Microsoft YaHei",
                "bold": True,
                "color": INK,
            },
        }
        mapping["native_chart_type"] = "line"

    native.update(
        {
            "name": f"{spec['chart_id']}-native-chart",
            "x": 96,
            "y": 228,
            "width": 1088,
            "height": 314,
            "style": {
                "colors": PALETTE[: max(1, len(native["series"]))],
                "font_family": "Microsoft YaHei",
                "axis_font_size": 13,
                "legend_font_size": 13,
                "chart_area_fill": WHITE,
                "plot_area_fill": WHITE,
                "text_color": INK,
                "axis_color": BRAND,
                "grid_color": EXPLANATION,
            },
        }
    )
    if len(native["series"]) > 1 and "show_legend" not in native:
        native["show_legend"] = True
        native["legend_position"] = "bottom"

    mapping["native_payload_sha256"] = canonical_json_sha256(native)
    return native, mapping


def _chunks(value: str, width: int) -> list[str]:
    text = str(value)
    if not text:
        return [""]
    return [text[index : index + width] for index in range(0, len(text), width)]


def _text_block(
    x: int,
    y: int,
    value: str,
    *,
    size: int,
    width_chars: int,
    fill: str = INK,
    weight: int = 400,
    line_height: int | None = None,
) -> tuple[str, int]:
    step = line_height or int(size * 1.35)
    parts = []
    for index, line in enumerate(_chunks(value, width_chars)):
        parts.append(
            f'<text x="{x}" y="{y + index * step}" font-family="Microsoft YaHei" '
            f'font-size="{size}" font-weight="{weight}" fill="{fill}">{html.escape(line)}</text>'
        )
    return "\n".join(parts), y + len(parts) * step


def _number_text(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    return format(value, ".15g")


def _column_fallback(payload: dict[str, Any]) -> str:
    categories = payload["categories"]
    series = payload["series"]
    values = [float(value) for entry in series for value in entry["values"]]
    max_value = max(values) if values else 1.0
    if max_value <= 0:
        raise ProjectionError("column charts require at least one positive value")
    left, right, top, bottom = 180, 1120, 260, 480
    category_width = (right - left) / max(1, len(categories))
    group_width = min(category_width * 0.68, 300)
    column_width = max(18, group_width / max(1, len(series)))
    elements = [
        f'<rect x="96" y="228" width="1088" height="314" rx="10" fill="{WHITE}" stroke="{EXPLANATION}" stroke-width="2"/>',
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="{BRAND}" stroke-width="2"/>',
    ]
    for category_index, category in enumerate(categories):
        group_left = left + category_index * category_width + (category_width - group_width) / 2
        for series_index, entry in enumerate(series):
            value = float(entry["values"][category_index])
            height = max(2, (bottom - top) * value / max_value)
            x = group_left + series_index * column_width
            y = bottom - height
            color = PALETTE[series_index % len(PALETTE)]
            elements.extend(
                [
                    f'<rect x="{x:.3f}" y="{y:.3f}" width="{column_width - 8:.3f}" height="{height:.3f}" rx="5" fill="{color}"/>',
                    f'<text x="{x + (column_width - 8) / 2:.3f}" y="{y - 10:.3f}" text-anchor="middle" font-family="Microsoft YaHei" font-size="15" font-weight="700" fill="{INK}">{value:.2f}</text>',
                ]
            )
        elements.append(
            f'<text x="{left + category_index * category_width + category_width / 2:.3f}" y="{bottom + 28}" text-anchor="middle" font-family="Microsoft YaHei" font-size="15" fill="{INK}">{html.escape(str(category))}</text>'
        )
    return "\n".join(elements)


def _stacked_column_fallback(payload: dict[str, Any]) -> str:
    values = [float(entry["values"][0]) for entry in payload["series"]]
    total = sum(values)
    if total <= 0:
        raise ProjectionError("stacked charts require a positive total")
    left, right, top, bottom = 180, 1120, 260, 470
    width = 240
    x = (left + right - width) / 2
    y = bottom
    elements = [
        f'<rect x="96" y="228" width="1088" height="314" rx="10" fill="{WHITE}" stroke="{EXPLANATION}" stroke-width="2"/>',
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="{BRAND}" stroke-width="2"/>',
    ]
    for index, (entry, value) in enumerate(zip(payload["series"], values)):
        height = (bottom - top) * value / total
        y -= height
        color = PALETTE[index % len(PALETTE)]
        elements.append(
            f'<rect x="{x:.3f}" y="{y:.3f}" width="{width}" height="{height:.3f}" fill="{color}"/>'
        )
        if height >= 40:
            elements.append(
                f'<text x="{x + width / 2:.3f}" y="{y + height / 2 + 6:.3f}" text-anchor="middle" font-family="Microsoft YaHei" font-size="15" font-weight="700" fill="{WHITE}">{value:.2f}</text>'
            )
    legend_y = 500
    for index, entry in enumerate(payload["series"]):
        x = 150 + index * 310
        elements.append(
            f'<rect x="{x}" y="{legend_y}" width="16" height="16" rx="3" fill="{PALETTE[index % len(PALETTE)]}"/>'
        )
        elements.append(
            f'<text x="{x + 25}" y="{legend_y + 14}" font-family="Microsoft YaHei" font-size="14" fill="{INK}">{html.escape(entry["name"])}</text>'
        )
    return "\n".join(elements)


def _line_fallback(payload: dict[str, Any]) -> str:
    categories = payload["categories"]
    values = [float(value) for value in payload["series"][0]["values"]]
    max_value = max(values) if values else 1.0
    min_value = min(values) if values else 0.0
    spread = max(max_value - min_value, abs(max_value) * 0.1, 1.0)
    left, right, top, bottom = 145, 1135, 265, 475
    coords: list[tuple[float, float]] = []
    for index, value in enumerate(values):
        x = left + index * (right - left) / max(1, len(values) - 1)
        y = bottom - (value - min_value) / spread * (bottom - top)
        coords.append((x, y))
    points = " ".join(f"{x:.3f},{y:.3f}" for x, y in coords)
    elements = [
        f'<rect x="96" y="228" width="1088" height="314" rx="10" fill="{WHITE}" stroke="{EXPLANATION}" stroke-width="2"/>',
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="{BRAND}" stroke-width="2"/>',
        f'<polyline points="{points}" fill="none" stroke="{BRAND}" stroke-width="5" stroke-linejoin="round"/>',
    ]
    for (x, y), category, value in zip(coords, categories, values):
        elements.extend(
            [
                f'<circle cx="{x:.3f}" cy="{y:.3f}" r="7" fill="{WHITE}" stroke="{BRAND}" stroke-width="4"/>',
                f'<text x="{x:.3f}" y="{y - 16:.3f}" text-anchor="middle" font-family="Microsoft YaHei" font-size="14" font-weight="700" fill="{INK}">{_number_text(value)}</text>',
                f'<text x="{x:.3f}" y="{bottom + 28}" text-anchor="middle" font-family="Microsoft YaHei" font-size="13" fill="{INK}">{html.escape(str(category))}</text>',
            ]
        )
    return "\n".join(elements)


def presentation_svg(spec: dict[str, Any], native_payload: dict[str, Any]) -> tuple[str, list[str]]:
    title = str(spec["title"])
    conclusion = str(spec["conclusion"])
    scope = f"范围：{spec['scope']}"
    time_unit = f"时间：{spec['time_range']} · 单位：{spec['unit']}"
    denominator = f"口径：{spec['denominator']}"
    source_lines = [f"来源：{source['label']}" for source in spec["source_refs"]]
    required_text = [
        title,
        conclusion,
        scope,
        time_unit,
        denominator,
        *source_lines,
        "MANUAL-ONLY · 医疗与保险内容须人工复核",
    ]
    title_svg, _ = _text_block(72, 72, title, size=34, width_chars=29, weight=700)
    conclusion_svg, _ = _text_block(
        72, 135, conclusion, size=21, width_chars=49, fill=BRAND, weight=700
    )
    scope_svg, _ = _text_block(72, 568, scope, size=14, width_chars=72, fill=INK)
    denominator_svg, _ = _text_block(
        72, 594, denominator, size=13, width_chars=78, fill=MUTED
    )
    source_svg, source_bottom = _text_block(
        72, 620, "；".join(source_lines), size=12, width_chars=86, fill=MUTED, line_height=18
    )
    if source_bottom > 684:
        raise ProjectionError("source text exceeds the deterministic single-slide budget")

    payload_text = json.dumps(native_payload, ensure_ascii=False, separators=(",", ":"))
    if native_payload.get("grouping") == "stacked":
        chart_svg = _stacked_column_fallback(native_payload)
    elif native_payload["type"] == "line":
        chart_svg = _line_fallback(native_payload)
    else:
        chart_svg = _column_fallback(native_payload)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720" data-pptx-page-role="content">
  <g id="background" data-pptx-bounds="0 0 1280 720">
    <rect x="0" y="0" width="1280" height="720" fill="{BACKGROUND}"/>
    <rect x="0" y="0" width="18" height="720" fill="{BRAND}"/>
  </g>
  <g id="header" data-pptx-bounds="72 36 1136 168">
    {title_svg}
    {conclusion_svg}
    <text x="1208" y="76" text-anchor="end" font-family="Microsoft YaHei" font-size="14" font-weight="700" fill="{ACCENT}">DATA · REVIEW ONLY</text>
    <text x="72" y="198" font-family="Microsoft YaHei" font-size="14" fill="{MUTED}">{html.escape(time_unit)}</text>
  </g>
  <g id="{html.escape(native_payload['name'])}" data-pptx-bounds="96 228 1088 314" data-pptx-replace-with="chart">
    <metadata type="application/json">{html.escape(payload_text)}</metadata>
    <g id="chart-fallback">{chart_svg}</g>
  </g>
  <g id="evidence" data-pptx-bounds="72 552 1136 112">
    {scope_svg}
    {denominator_svg}
    {source_svg}
  </g>
  <g id="footer" data-pptx-bounds="72 684 1136 24">
    <text x="72" y="704" font-family="Microsoft YaHei" font-size="12" font-weight="700" fill="{ACCENT}">MANUAL-ONLY · 医疗与保险内容须人工复核</text>
    <text x="1208" y="704" text-anchor="end" font-family="Microsoft YaHei" font-size="12" fill="{MUTED}">{html.escape(spec['chart_id'])}</text>
  </g>
</svg>'''
    return svg, required_text


def validate_projection_manifest(
    projection: dict[str, Any], projection_path: Path
) -> list[str]:
    errors: list[str] = []
    if projection.get("schema_version") != PROJECTION_VERSION:
        errors.append("unsupported projection schema_version")
        return errors
    source = projection.get("source", {})
    project = projection.get("project", {})
    for label, node, ref_key, hash_key in (
        ("spec", source, "spec_ref", "spec_sha256"),
        ("fallback", source, "fallback_ref", "fallback_sha256"),
        ("slide", project, "slide_ref", "slide_sha256"),
    ):
        ref = node.get(ref_key)
        expected_hash = node.get(hash_key)
        if not ref:
            errors.append(f"{label} ref is missing")
            continue
        path = Path(ref)
        if not path.is_absolute():
            path = (projection_path.parent / path).resolve()
        if not path.is_file():
            errors.append(f"{label} file is missing: {path}")
        elif sha256_file(path) != expected_hash:
            errors.append(f"{label} hash is stale")
    payload = projection.get("native_object", {}).get("payload")
    if not isinstance(payload, dict):
        errors.append("native payload is missing")
    elif canonical_json_sha256(payload) != projection.get("mapping", {}).get(
        "native_payload_sha256"
    ):
        errors.append("native payload digest does not match mapping")
    expected = projection.get("expected_native_chart")
    if not isinstance(expected, dict):
        errors.append("expected_native_chart is missing")
    elif payload:
        comparable = {
            "type": payload.get("type"),
            "categories": payload.get("categories"),
            "series": [
                {"name": entry.get("name"), "values": entry.get("values")}
                for entry in payload.get("series", [])
            ],
        }
        comparable_axis_minimum = payload.get("axes", {}).get("value", {}).get(
            "minimum"
        )
        if comparable_axis_minimum is not None:
            comparable["value_axis_minimum"] = comparable_axis_minimum
        if comparable != expected:
            errors.append("expected native chart diverges from marker payload")
    return errors


def _load_render_backend() -> tuple[Any, Any]:
    """Import the parent renderer only when materialization actually needs it.

    The mapping/SVG helpers above stay importable and usable without the parent
    renderer. Materialization needs it for canonical spec validation and an exact
    canonical SVG comparison, so a missing backend is reported as a fail-closed
    ``ProjectionError`` before any output path is created or written.

    A backend that is installed but broken must not be disguised as a missing or
    successfully validated backend: only ``ModuleNotFoundError`` for this module
    name itself maps to the explicit missing-backend error. Any other import
    failure propagates unchanged.
    """

    try:
        from render_data_explanations import render_svg_text, validate_spec
    except ModuleNotFoundError as exc:
        if exc.name != "render_data_explanations":
            raise
        raise ProjectionError(
            "parent renderer backend is not installed: render_data_explanations is "
            "required for canonical validation and materialization; nothing was written"
        ) from exc
    return render_svg_text, validate_spec


def materialize_project(spec_path: Path, fallback_path: Path, project_root: Path) -> dict[str, Any]:
    spec_path = spec_path.resolve()
    fallback_path = fallback_path.resolve()
    project_root = project_root.resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    render_svg_text, validate_spec = _load_render_backend()
    spec_errors = validate_spec(spec, spec_path)
    if spec_errors:
        raise ProjectionError("; ".join(spec_errors))

    canonical_fallback_text = render_svg_text(spec)
    canonical_fallback = canonical_fallback_text.encode("utf-8")
    if not fallback_path.is_file():
        raise ProjectionError(f"fallback SVG is missing: {fallback_path}")
    fallback_text = fallback_path.read_text(encoding="utf-8")
    if fallback_text != canonical_fallback_text:
        raise ProjectionError(
            "fallback SVG is stale relative to the chart spec; rerender the fallback first"
        )

    native_payload, mapping = project_native_payload(spec)
    slide_svg, required_slide_text = presentation_svg(spec, native_payload)
    slide_path = project_root / "svg_output" / "01_data_chart.svg"
    slide_path.parent.mkdir(parents=True, exist_ok=True)
    slide_path.write_text(slide_svg, encoding="utf-8")
    (project_root / "validation").mkdir(parents=True, exist_ok=True)

    expected_chart = {
        "type": native_payload["type"],
        "categories": native_payload["categories"],
        "series": [
            {"name": entry["name"], "values": entry["values"]}
            for entry in native_payload["series"]
        ],
    }
    value_axis_minimum = native_payload.get("axes", {}).get("value", {}).get(
        "minimum"
    )
    if value_axis_minimum is not None:
        expected_chart["value_axis_minimum"] = value_axis_minimum
    projection = {
        "schema_version": PROJECTION_VERSION,
        "projection_id": f"{spec['chart_id']}-ppt-native",
        "source": {
            "spec_ref": str(spec_path),
            "spec_sha256": sha256_file(spec_path),
            "fallback_ref": str(fallback_path),
            "fallback_sha256": sha256_file(fallback_path),
            "canonical_fallback_sha256": sha256_bytes(canonical_fallback),
        },
        "mapping": mapping,
        "native_object": {
            "object_key": native_payload["name"],
            "payload": native_payload,
        },
        "expected_native_chart": expected_chart,
        "text_contract": {
            "required_slide_text": required_slide_text,
            "unit": spec["unit"],
            "source_labels": [source["label"] for source in spec["source_refs"]],
        },
        "project": {
            "slide_ref": str(slide_path),
            "slide_sha256": sha256_file(slide_path),
            "canvas": {"width": 1280, "height": 720},
        },
        "policy": {
            "data_rewrite_allowed": False,
            "unsupported_mapping": "fail-closed-to-svg",
            "publication_boundary": "manual-only",
            "external_provider_used": False,
        },
    }
    projection_path = project_root / "data_projection.json"
    projection_path.write_text(
        json.dumps(projection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    errors = validate_projection_manifest(projection, projection_path)
    if errors:
        raise ProjectionError("; ".join(errors))
    return {
        "project": str(project_root),
        "projection": str(projection_path),
        "slide": str(slide_path),
        "source_spec_sha256": projection["source"]["spec_sha256"],
        "fallback_sha256": projection["source"]["fallback_sha256"],
        "native_payload_sha256": mapping["native_payload_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--fallback", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = materialize_project(args.spec, args.fallback, args.project)
    except (OSError, json.JSONDecodeError, ProjectionError) as exc:
        print(f"projection failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
