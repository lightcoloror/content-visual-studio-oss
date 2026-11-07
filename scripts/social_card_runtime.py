"""Portable, dependency-light guards for optional social-card runtimes.

Public-edition adaptation: ``resolve_external_file_from_env`` accepts an
optional ``allowed_root`` so callers can confine an env-configured file to a
specific directory. The original env / path / sha256 / HTML-source guards and
their default behaviour are unchanged; without ``allowed_root`` no new
restriction is applied.
"""

from __future__ import annotations

import hashlib
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


class SocialCardRuntimeError(RuntimeError):
    """Raised when social-card input or an explicitly configured runtime is unsafe."""


class _SafeSocialCardHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.has_viewport = False
        self.html_design_direction = ""
        self.blocked_features: list[str] = []
        self.remote_refs: list[str] = []
        self.poster_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered_tag = tag.casefold()
        attr_map = {name.casefold(): value or "" for name, value in attrs}
        if lowered_tag in {"script", "iframe", "object", "embed"}:
            self.blocked_features.append(lowered_tag)
        if lowered_tag == "meta" and attr_map.get("name", "").casefold() == "viewport":
            self.has_viewport = True
        if lowered_tag == "html":
            self.html_design_direction = attr_map.get("data-design-direction", "")
        if lowered_tag == "section" and "poster" in attr_map.get("class", "").split():
            self.poster_count += 1
        for name, value in attr_map.items():
            if name.startswith("on"):
                self.blocked_features.append(f"event-handler:{name}")
            if name in {"src", "href", "poster", "srcset"} and value.casefold().startswith(
                ("http://", "https://", "//")
            ):
                self.remote_refs.append(value)
            if name == "style" and re.search(
                r"(?:url|@import)\s*\([^)]*(?:https?:)?//", value, re.I
            ):
                self.remote_refs.append(value)


def validate_social_card_html_source(
    html_text: str, required_direction: str | None = None
) -> dict[str, Any]:
    parser = _SafeSocialCardHtmlParser()
    parser.feed(html_text)
    css_remote_refs = re.findall(
        r"(?:url\s*\(|@import\s+)[^;)}]*(?:https?:)?//[^;)}]+",
        html_text,
        flags=re.I,
    )
    remote_refs = parser.remote_refs + css_remote_refs
    if parser.blocked_features:
        raise SocialCardRuntimeError(
            "social-card HTML must be script-free and cannot embed active documents: "
            + ", ".join(sorted(set(parser.blocked_features)))
        )
    if remote_refs:
        raise SocialCardRuntimeError("social-card HTML cannot load remote assets")
    if not parser.has_viewport:
        raise SocialCardRuntimeError("social-card HTML must declare a responsive viewport")
    if required_direction and parser.html_design_direction != required_direction:
        raise SocialCardRuntimeError(
            "social-card HTML data-design-direction must equal the selected artifact theme"
        )
    if parser.poster_count < 1:
        raise SocialCardRuntimeError(
            "social-card HTML must contain at least one section.poster board"
        )
    return {
        "script_free_html": True,
        "local_assets_only": True,
        "html_design_direction": parser.html_design_direction,
        "poster_count": parser.poster_count,
    }


def resolve_external_file_from_env(
    env_name: str | None,
    label: str,
    expected_sha256: str | None = None,
    allowed_root: str | Path | None = None,
) -> Path:
    """Resolve an env-configured file, optionally confined to ``allowed_root``.

    ``Path.resolve()`` dereferences symlinks/junctions before the containment
    check, so an in-root link pointing outside the approved root is rejected.
    """
    if not env_name:
        raise SocialCardRuntimeError(
            f"{label} is missing its environment-variable contract"
        )
    raw_path = os.environ.get(env_name, "").strip()
    if not raw_path:
        raise SocialCardRuntimeError(f"{label} is not configured; set {env_name}")
    resolved = Path(raw_path).expanduser().resolve()
    if allowed_root is not None:
        root = Path(allowed_root).expanduser().resolve()
        if not resolved.is_relative_to(root):
            raise SocialCardRuntimeError(
                f"{label} configured by {env_name} escapes the approved root: {resolved}"
            )
    if not resolved.is_file():
        raise SocialCardRuntimeError(
            f"{label} configured by {env_name} is missing: {resolved}"
        )
    if expected_sha256:
        actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
        if actual.casefold() != expected_sha256.casefold():
            raise SocialCardRuntimeError(
                f"{label} checksum drift: expected {expected_sha256}, got {actual}"
            )
    return resolved
