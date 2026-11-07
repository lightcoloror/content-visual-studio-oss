#!/usr/bin/env python3
"""Plan-safe article visuals: search candidates, review them, and insert verified assets."""

from __future__ import annotations
from studio_paths import STUDIO_ROOT, HUMAN_VOICE_ROOT, research_schema_path

import argparse
import html
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from markdown_it import MarkdownIt


OPENVERSE_ENDPOINT = "https://api.openverse.org/v1/images/"
ALLOWED_LICENSES = "by,by-sa,cc0,pdm"
USER_AGENT = "lightcolor-content-studio/0.1 (article visual candidate review)"
SELECTED_STATUSES = {"selected", "inserted"}
PHOTO_ROUTES = {"personal-photo", "work-detail-photo", "stock-photo"}
SOURCE_REGISTRY_PATH = STUDIO_ROOT / "config" / "visual-source-registry.json"
THEME_ROOT = STUDIO_ROOT / "themes"
ARTICLE_THEMES = {
    "default": None,
    "editorial-field-guide": THEME_ROOT / "editorial-field-guide.css",
    "reflective-personal-essay": THEME_ROOT / "reflective-personal-essay.css",
}
REFLECTIVE_SECTION_TONES = {"paper", "mist", "dark", "resolve"}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_stock_asset_for_insertion(asset: dict[str, Any]) -> None:
    registry = load_json(SOURCE_REGISTRY_PATH)
    source_id = asset.get("source_id", "")
    source = registry.get("sources", {}).get(source_id)
    if source is None:
        raise ValueError(f"selected stock asset has no registered source: {source_id or '<missing>'}")
    if source.get("selection_policy") == "original-source-required":
        raise ValueError(f"selected stock asset must name the original provider, not {source_id}")
    missing = [field for field in ("landing_page_url", "license", "license_url") if not asset.get(field)]
    if missing:
        raise ValueError(f"selected stock asset is missing rights metadata: {', '.join(missing)}")
    if asset.get("usage_scope") != "commercial":
        raise ValueError("selected stock asset is not cleared for commercial use")
    if asset.get("attribution_required") is None:
        raise ValueError("selected stock asset must record whether attribution is required")
    if source.get("attribution_policy") == "required" and asset.get("attribution_required") is not True:
        raise ValueError(f"selected stock asset from {source_id} requires attribution")
    if asset.get("attribution_required") is True and not asset.get("attribution"):
        raise ValueError("selected stock asset is missing required attribution text")
    if asset.get("release_status") not in {"verified", "not-guaranteed", "not-applicable"}:
        raise ValueError("selected stock asset has no completed model/property release assessment")


def build_openverse_url(query: str, per_page: int = 6, page: int = 1) -> str:
    params = {
        "q": query,
        "page_size": per_page,
        "page": page,
        "license": ALLOWED_LICENSES,
        "mature": "false",
    }
    return f"{OPENVERSE_ENDPOINT}?{urllib.parse.urlencode(params)}"


def fetch_json(url: str, timeout: float = 20.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _candidate(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": f"openverse:{result.get('id', '')}",
        "ref": result.get("url", ""),
        "thumbnail": result.get("thumbnail", ""),
        "title": result.get("title") or "Untitled",
        "creator": result.get("creator") or "Unknown",
        "creator_url": result.get("creator_url") or "",
        "landing_page_url": result.get("foreign_landing_url") or "",
        "license": result.get("license") or "unknown",
        "license_version": result.get("license_version") or "",
        "license_url": result.get("license_url") or "",
        "attribution": result.get("attribution") or "",
        "provider": result.get("provider") or "",
        "source": result.get("source") or "",
        "candidate_source_id": "openverse",
        "original_source_hint": result.get("source") or result.get("provider") or "",
        "width": result.get("width"),
        "height": result.get("height"),
        "rights_status": "needs-review",
        "rights_note": "Verify the license and attribution on the original landing page before selection.",
    }


def _matches_negative_term(result: dict[str, Any], negative_terms: list[str]) -> bool:
    tags = " ".join(str(tag.get("name", "")) for tag in result.get("tags", []) if isinstance(tag, dict))
    haystack = f"{result.get('title', '')} {tags}".casefold()
    return any(term.casefold() in haystack for term in negative_terms if term.strip())


def collect_openverse_candidates(
    item: dict[str, Any],
    per_slot: int = 6,
    min_width: int = 800,
    fetcher: Callable[[str], dict[str, Any]] = fetch_json,
) -> dict[str, Any]:
    plan = item.get("visual", {}).get("article_visual_plan", {})
    slots_output: list[dict[str, Any]] = []

    for slot in plan.get("slots", []):
        search = slot.get("search") or {}
        if "openverse" not in search.get("preferred_sources", []):
            continue
        query = search.get("query_en") or search.get("query_zh")
        if not query:
            continue

        url = build_openverse_url(query, per_page=max(per_slot * 2, per_slot))
        payload = fetcher(url)
        candidates = []
        for result in payload.get("results", []):
            width = result.get("width")
            if width is not None and width < min_width:
                continue
            if _matches_negative_term(result, search.get("negative_terms", [])):
                continue
            candidates.append(_candidate(result))
            if len(candidates) >= per_slot:
                break

        slots_output.append(
            {
                "slot_id": slot.get("slot_id"),
                "purpose": slot.get("purpose"),
                "media_role": slot.get("media_role"),
                "layout": slot.get("layout"),
                "query_zh": search.get("query_zh", ""),
                "query_en": search.get("query_en", ""),
                "negative_terms": search.get("negative_terms", []),
                "candidates": candidates,
            }
        )

    return {
        "manifest_version": "0.1",
        "content_id": item.get("content_id"),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "openverse",
        "selection_boundary": "human-review-required",
        "license_boundary": "candidate metadata is not final rights verification",
        "source_registry": str(SOURCE_REGISTRY_PATH),
        "slots": slots_output,
    }


def render_review_html(manifest: dict[str, Any]) -> str:
    sections: list[str] = []
    for slot in manifest.get("slots", []):
        cards: list[str] = []
        for candidate in slot.get("candidates", []):
            title = html.escape(str(candidate.get("title", "Untitled")))
            creator = html.escape(str(candidate.get("creator", "Unknown")))
            image_url = html.escape(str(candidate.get("thumbnail") or candidate.get("ref") or ""), quote=True)
            landing = html.escape(str(candidate.get("landing_page_url") or "#"), quote=True)
            license_url = html.escape(str(candidate.get("license_url") or landing), quote=True)
            license_name = html.escape(str(candidate.get("license", "unknown")).upper())
            ref = html.escape(str(candidate.get("ref", "")))
            dimensions = f"{candidate.get('width') or '?'} x {candidate.get('height') or '?'}"
            cards.append(
                f"""<article class="candidate">
<img src="{image_url}" alt="{title}" loading="lazy">
<div class="meta"><strong>{title}</strong><span>{creator}</span><span>{dimensions}</span>
<span><a href="{license_url}" target="_blank" rel="noreferrer">{license_name}</a></span>
<a href="{landing}" target="_blank" rel="noreferrer">核验原始页面</a>
<details><summary>素材引用</summary><code>{ref}</code></details></div>
</article>"""
            )
        sections.append(
            f"""<section><header><h2>{html.escape(str(slot.get('slot_id', 'slot')))}</h2>
<p>{html.escape(str(slot.get('purpose', '')))}</p>
<small>中文检索：{html.escape(str(slot.get('query_zh', '')))}　英文检索：{html.escape(str(slot.get('query_en', '')))}</small></header>
<div class="grid">{''.join(cards) or '<p>没有合格候选。</p>'}</div></section>"""
        )

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>文章配图候选 · {html.escape(str(manifest.get('content_id', '')))}</title>
<style>
:root{{--ink:#17202a;--muted:#667085;--line:#d0d5dd;--paper:#f7f8fa;--accent:#176b87}}
*{{box-sizing:border-box}}body{{margin:0;color:var(--ink);font-family:"Microsoft YaHei",system-ui,sans-serif;background:var(--paper)}}
main{{max-width:1180px;margin:auto;padding:32px 24px 64px}}h1{{font-size:30px;margin:0 0 8px}}.notice{{border-left:4px solid #c2410c;background:#fff7ed;padding:12px 16px;margin:20px 0 32px}}
section{{margin:36px 0}}section header{{margin-bottom:14px}}h2{{font-size:30px;margin:0 0 6px}}p{{line-height:1.65}}small{{color:var(--muted)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px}}.candidate{{background:#fff;border:1px solid var(--line);border-radius:6px;overflow:hidden}}
.candidate img{{display:block;width:100%;aspect-ratio:4/3;object-fit:cover;background:#eef1f4}}.meta{{display:grid;gap:7px;padding:12px;font-size:14px}}.meta span{{color:var(--muted)}}a{{color:var(--accent)}}code{{display:block;overflow-wrap:anywhere;white-space:normal}}
</style></head><body><main><h1>文章配图候选</h1><p>{html.escape(str(manifest.get('content_id', '')))}</p>
<div class="notice">候选图片尚未通过权利复核。选择前必须打开原始页面，确认许可证、署名要求、人物肖像和商标风险。</div>
{''.join(sections)}</main></body></html>"""


def _render_editorial_sections(markdown: str) -> str:
    parser = MarkdownIt("commonmark", {"html": True})
    tokens = parser.parse(markdown)
    section_starts = [
        index
        for index, token in enumerate(tokens)
        if token.type == "heading_open" and token.tag == "h2"
    ]
    first_section = section_starts[0] if section_starts else len(tokens)
    hero = parser.renderer.render(tokens[:first_section], parser.options, {})
    parts = [f'<header class="guide-hero"><div class="guide-shell">{hero}</div></header>']
    for section_index, start in enumerate(section_starts):
        end = (
            section_starts[section_index + 1]
            if section_index + 1 < len(section_starts)
            else len(tokens)
        )
        section = parser.renderer.render(tokens[start:end], parser.options, {})
        parts.append(
            f'<section class="guide-section" data-guide-section="{section_index + 1}">'
            f'<div class="guide-shell">{section}</div></section>'
        )
    return "".join(parts)


def _default_reflective_tones(section_count: int) -> list[str]:
    tones = ["paper" if index % 2 == 0 else "mist" for index in range(section_count)]
    if section_count >= 3:
        pivot = min(section_count - 2, max(1, round(section_count * 0.6) - 1))
        tones[pivot] = "dark"
    if section_count >= 2:
        tones[-1] = "resolve"
    return tones


def _render_reflective_sections(
    markdown: str, section_tones: list[str] | None = None
) -> str:
    parser = MarkdownIt("commonmark", {"html": True})
    tokens = parser.parse(markdown)
    section_starts = [
        index
        for index, token in enumerate(tokens)
        if token.type == "heading_open" and token.tag == "h2"
    ]
    first_section = section_starts[0] if section_starts else len(tokens)
    hero = parser.renderer.render(tokens[:first_section], parser.options, {})
    tones = section_tones or _default_reflective_tones(len(section_starts))
    if len(tones) != len(section_starts):
        raise ValueError(
            "reflective section_tones must contain exactly one tone for each H2 section"
        )
    invalid = sorted(set(tones).difference(REFLECTIVE_SECTION_TONES))
    if invalid:
        raise ValueError(f"unknown reflective section tone: {', '.join(invalid)}")

    parts = [f'<header class="essay-hero"><div class="essay-shell">{hero}</div></header>']
    for section_index, start in enumerate(section_starts):
        end = (
            section_starts[section_index + 1]
            if section_index + 1 < len(section_starts)
            else len(tokens)
        )
        section = parser.renderer.render(tokens[start:end], parser.options, {})
        tone = tones[section_index]
        parts.append(
            f'<section class="essay-section" data-essay-section="{section_index + 1}" '
            f'data-tone="{tone}"><div class="essay-shell">{section}</div></section>'
        )
    return "".join(parts)


def render_article_html(
    markdown: str,
    title: str,
    theme: str = "default",
    section_tones: list[str] | None = None,
) -> str:
    if theme not in ARTICLE_THEMES:
        raise ValueError(f"unknown article theme: {theme}")
    if theme != "reflective-personal-essay" and section_tones is not None:
        raise ValueError("section_tones are available only for reflective-personal-essay")
    if theme == "editorial-field-guide":
        body = _render_editorial_sections(markdown)
    elif theme == "reflective-personal-essay":
        body = _render_reflective_sections(markdown, section_tones)
    else:
        body = MarkdownIt("commonmark", {"html": True}).render(markdown)
    theme_path = ARTICLE_THEMES[theme]
    theme_css = theme_path.read_text(encoding="utf-8") if theme_path else ""
    article_classes = {
        "editorial-field-guide": "guide-article",
        "reflective-personal-essay": "essay-article",
    }
    article_attribute = (
        f' class="{article_classes[theme]}"' if theme in article_classes else ""
    )
    body_attribute = (
        f' data-design-direction="{theme}"' if theme in article_classes else ""
    )
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title}</title>
<style>
:root{{--ink:#182128;--muted:#5e6b73;--line:#d8e1e3;--paper:#ffffff;--soft:#eef7f5;--mint:#dcefe8;--coral:#d95d47;--yellow:#f4c95d}}
*{{box-sizing:border-box}}html{{background:var(--paper)}}body{{margin:0;color:var(--ink);font-family:"Microsoft YaHei","Noto Sans SC",system-ui,sans-serif;background:var(--paper)}}
article{{width:min(100% - 40px,820px);margin:0 auto;padding:54px 0 88px;font-size:18px;line-height:1.88}}
h1{{max-width:720px;margin:0 0 22px;font-size:clamp(34px,6vw,56px);line-height:1.18;letter-spacing:0}}h2{{clear:both;margin:52px 0 14px;padding-top:8px;font-size:30px;line-height:1.35;letter-spacing:0}}
p{{margin:0 0 18px}}strong{{color:#0d5b55}}ul{{margin:10px 0 24px;padding-left:1.3em}}li{{margin:8px 0}}
blockquote{{margin:24px 0 34px;padding:18px 22px;border-left:5px solid var(--yellow);background:#fff9e8;color:#3f474c}}blockquote p{{margin:0}}
.article-visual{{margin:18px 0 28px}}.article-visual img{{display:block;max-width:100%;height:auto;object-fit:var(--visual-object-fit,cover);object-position:var(--visual-focus-x,50%) var(--visual-focus-y,50%)}}.article-visual figcaption{{margin-top:9px;color:var(--muted);font-size:14px;line-height:1.55}}.article-visual__credit{{display:block;margin-top:4px;font-size:12px}}.article-visual__credit a{{color:inherit}}
.article-visual--full-width{{width:100%;margin:28px 0 34px}}.article-visual--full-width img{{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:6px}}
.article-visual--text-left,.article-visual--text-right{{width:156px;padding:22px;margin-top:6px;background:var(--soft);border:1px solid var(--line);border-radius:6px;text-align:center}}
.article-visual--text-left{{float:right;margin-left:26px}}.article-visual--text-right{{float:left;margin-right:26px}}.article-visual--text-left img,.article-visual--text-right img{{width:76px;height:76px;margin:auto}}
.article-visual--text-left figcaption,.article-visual--text-right figcaption{{font-size:13px}}
.article-visual[data-media-route$="-photo"].article-visual--text-left,.article-visual[data-media-route$="-photo"].article-visual--text-right{{width:min(44%,340px);padding:0;background:transparent;border:0;text-align:left}}
.article-visual[data-media-route$="-photo"].article-visual--text-left img,.article-visual[data-media-route$="-photo"].article-visual--text-right img{{width:100%;height:auto;aspect-ratio:4/3;object-fit:cover;border-radius:6px}}
.article-visual--inline{{display:flex;align-items:center;gap:18px;padding:18px 20px;background:var(--soft);border-top:1px solid var(--line);border-bottom:1px solid var(--line)}}.article-visual--inline img{{width:72px;height:72px;flex:0 0 auto}}
.article-visual--icon-row{{display:flex;align-items:center;gap:18px;padding:16px 0;border-bottom:1px solid var(--line)}}.article-visual--icon-row img{{width:64px;height:64px}}
article::after{{content:"";display:block;clear:both}}
@media (max-width:640px){{article{{width:min(100% - 28px,820px);padding:30px 0 60px;font-size:17px;line-height:1.78}}h1{{font-size:36px}}h2{{margin-top:38px;font-size:24px}}.article-visual--text-left,.article-visual--text-right{{float:none;width:100%;margin:14px 0 20px;display:flex;align-items:center;gap:18px;text-align:left}}.article-visual--text-left img,.article-visual--text-right img{{margin:0;flex:0 0 auto}}.article-visual[data-media-route$="-photo"].article-visual--text-left,.article-visual[data-media-route$="-photo"].article-visual--text-right{{display:block;width:100%;margin:18px 0 24px}}.article-visual[data-media-route$="-photo"].article-visual--text-left img,.article-visual[data-media-route$="-photo"].article-visual--text-right img{{width:100%;height:auto}}}}
{theme_css}
</style></head><body{body_attribute}><article{article_attribute}>{body}</article></body></html>"""


def _normalize(value: str) -> str:    return re.sub(r"\s+", "", value).casefold()


def find_anchor_line(markdown: str, anchor: dict[str, Any]) -> int:
    kind = anchor.get("kind")
    value = str(anchor.get("value", ""))
    occurrence = int(anchor.get("occurrence", 1))

    if kind == "explicit-marker":
        matches = [index + 1 for index, line in enumerate(markdown.splitlines()) if value in line]
    else:
        tokens = MarkdownIt("commonmark").parse(markdown)
        token_type = "heading_open" if kind == "heading" else "paragraph_open"
        matches = []
        for index, token in enumerate(tokens):
            if token.type != token_type or token.map is None:
                continue
            inline = tokens[index + 1] if index + 1 < len(tokens) else None
            content = inline.content if inline and inline.type == "inline" else ""
            if _normalize(value) in _normalize(content):
                matches.append(token.map[1])

    if occurrence < 1 or occurrence > len(matches):
        raise ValueError(f"anchor not found: {kind} {value!r} occurrence {occurrence}")
    return matches[occurrence - 1]


def _asset_src(ref: str, output_path: Path) -> str:
    if re.match(r"^https?://", ref, re.IGNORECASE):
        return ref
    path = Path(ref)
    if path.is_absolute():
        try:
            return os.path.relpath(path, output_path.parent).replace("\\", "/")
        except ValueError:
            return path.as_posix()
    return ref.replace("\\", "/")


def _percentage(value: float) -> str:
    return f"{round(value * 100, 3):g}%"


def _box_attribute(box: dict[str, Any] | None) -> str:
    if not box:
        return ""
    return ",".join(f"{float(box[key]):.4f}" for key in ("x", "y", "width", "height"))


def _asset_focus(asset: dict[str, Any]) -> tuple[float, float]:
    focal = asset.get("focal_point")
    if focal:
        return float(focal["x"]), float(focal["y"])
    safe_crop = asset.get("safe_crop")
    if safe_crop:
        return (
            float(safe_crop["x"]) + float(safe_crop["width"]) / 2,
            float(safe_crop["y"]) + float(safe_crop["height"]) / 2,
        )
    return 0.5, 0.5


def _credit_html(asset: dict[str, Any]) -> str:
    if asset.get("attribution_required") is not True:
        return ""
    attribution = html.escape(str(asset.get("attribution") or asset.get("creator") or "素材来源"))
    landing = html.escape(str(asset.get("landing_page_url") or ""), quote=True)
    license_name = html.escape(str(asset.get("license") or "许可证"))
    license_url = html.escape(str(asset.get("license_url") or landing), quote=True)
    source_link = f'<a href="{landing}" rel="noreferrer">原始来源</a>' if landing else ""
    license_link = f'<a href="{license_url}" rel="noreferrer">{license_name}</a>' if license_url else license_name
    separator = " · " if source_link else ""
    return (
        f'<span class="article-visual__credit">{attribution} · '
        f"{source_link}{separator}{license_link}</span>"
    )


def _figure(slot: dict[str, Any], asset: dict[str, Any], output_path: Path) -> str:
    slot_id = html.escape(str(slot["slot_id"]), quote=True)
    layout = html.escape(str(slot.get("layout", "full-width")), quote=True)
    route = html.escape(str(slot.get("route", "diagram")), quote=True)
    src = html.escape(_asset_src(str(asset["ref"]), output_path), quote=True)
    alt = html.escape(str(slot.get("alt_text") or asset.get("alt_text") or ""), quote=True)
    caption = html.escape(str(slot.get("caption") or ""))
    credit = _credit_html(asset)
    caption_html = f"\n  <figcaption>{caption}{credit}</figcaption>" if caption or credit else ""
    focus_x, focus_y = _asset_focus(asset)
    fit_strategy = str(asset.get("fit_strategy") or ("cover" if route in PHOTO_ROUTES else "contain"))
    object_fit = "cover" if fit_strategy == "focal-cover" else fit_strategy
    style = html.escape(
        f"--visual-focus-x:{_percentage(focus_x)};--visual-focus-y:{_percentage(focus_y)};"
        f"--visual-object-fit:{object_fit}",
        quote=True,
    )
    brief = slot.get("visual_brief") or {}
    semantic_attributes = {
        "data-fit-strategy": fit_strategy,
        "data-safe-crop": _box_attribute(asset.get("safe_crop")),
        "data-subject-bounds": _box_attribute(asset.get("subject_bounds")),
        "data-visual-metaphor": str(brief.get("metaphor") or ""),
        "data-visual-composition": str(brief.get("composition") or ""),
        "data-central-action": str(brief.get("central_action") or ""),
        "data-max-labels": str(brief.get("max_labels", "")),
        "data-source-id": str(asset.get("source_id") or ""),
        "data-license": str(asset.get("license") or ""),
    }
    attributes = " ".join(
        f'{name}="{html.escape(value, quote=True)}"'
        for name, value in semantic_attributes.items()
        if value
    )
    return (
        f"<!-- visual-slot:{slot_id} -->\n"
        f"<figure class=\"article-visual article-visual--{layout}\" data-media-route=\"{route}\" "
        f"data-visual-slot-id=\"{slot_id}\" {attributes}>\n"
        f"  <img src=\"{src}\" alt=\"{alt}\" loading=\"lazy\" style=\"{style}\">{caption_html}\n"
        f"</figure>"
    )


def insert_selected_visuals(item: dict[str, Any], markdown: str, output_path: Path) -> str:
    visual = item.get("visual", {})
    assets = {asset.get("ref"): asset for asset in visual.get("assets", []) if asset.get("ref")}
    slots = visual.get("article_visual_plan", {}).get("slots", [])
    insertions: list[tuple[int, str]] = []

    for slot in slots:
        selected_ref = slot.get("selected_asset_ref")
        if slot.get("status") not in SELECTED_STATUSES or not selected_ref:
            continue
        marker = f"<!-- visual-slot:{slot.get('slot_id')} -->"
        if marker in markdown:
            continue
        asset = assets.get(selected_ref)
        if not asset:
            raise ValueError(f"selected asset is not registered: {selected_ref}")
        if asset.get("rights_status") != "verified":
            raise ValueError(f"selected asset rights are not verified: {selected_ref}")
        if asset.get("asset_type") == "stock-photo":
            validate_stock_asset_for_insertion(asset)
        brief = slot.get("visual_brief") or {}
        max_labels = brief.get("max_labels")
        if slot.get("route") in PHOTO_ROUTES and max_labels not in {None, 0}:
            raise ValueError(f"real-photo slot {slot.get('slot_id')!r} must use max_labels=0")
        if isinstance(max_labels, int) and max_labels > 3:
            raise ValueError(f"visual brief for {slot.get('slot_id')!r} exceeds three labels")
        if asset.get("fit_strategy") == "focal-cover" and not asset.get("focal_point"):
            raise ValueError(f"focal-cover asset has no focal point: {selected_ref}")
        if not slot.get("alt_text") and not asset.get("alt_text"):
            raise ValueError(f"selected asset has no alt text: {selected_ref}")
        line = find_anchor_line(markdown, slot.get("anchor", {}))
        insertions.append((line, _figure(slot, asset, output_path)))

    lines = markdown.splitlines()
    for line, figure in sorted(insertions, reverse=True):
        lines[line:line] = ["", figure, ""]
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search-openverse", help="Create a rights-unverified candidate manifest")
    search.add_argument("--item", type=Path, required=True)
    search.add_argument("--output", type=Path, required=True)
    search.add_argument("--per-slot", type=int, default=6)
    search.add_argument("--min-width", type=int, default=800)

    review = subparsers.add_parser("review-html", help="Render a local candidate contact sheet")
    review.add_argument("--manifest", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)

    render = subparsers.add_parser("render-html", help="Render mixed Markdown and figure blocks as a responsive article")
    render.add_argument("--article", type=Path, required=True)
    render.add_argument("--output", type=Path, required=True)
    render.add_argument("--title", required=True)
    render.add_argument("--theme", choices=sorted(ARTICLE_THEMES), default="default")

    insert = subparsers.add_parser("insert", help="Insert only selected, rights-verified assets")
    insert.add_argument("--item", type=Path, required=True)
    insert.add_argument("--article", type=Path)
    insert.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "search-openverse":
        manifest = collect_openverse_candidates(load_json(args.item), args.per_slot, args.min_width)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {len(manifest['slots'])} visual candidate groups to {args.output}")
        return 0

    if args.command == "review-html":
        manifest = load_json(args.manifest)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_review_html(manifest), encoding="utf-8")
        print(f"Wrote candidate review page to {args.output}")
        return 0

    if args.command == "render-html":
        markdown = args.article.read_text(encoding="utf-8")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            render_article_html(markdown, args.title, theme=args.theme), encoding="utf-8"
        )
        print(f"Wrote responsive article HTML to {args.output}")
        return 0

    item = load_json(args.item)
    article = args.article or Path(item["visual"]["article_visual_plan"]["article_ref"])
    if not article.is_absolute():
        article = (args.item.parent / article).resolve()
    if article.resolve() == args.output.resolve():
        raise ValueError("refusing to overwrite the source article; choose a separate --output path")
    markdown = article.read_text(encoding="utf-8")
    rendered = insert_selected_visuals(item, markdown, args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Wrote article with verified visual insertions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
