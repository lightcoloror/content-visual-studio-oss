"""Contract tests for the portable handdraw style library and gallery adapters.

SYNTHETIC TEST ONLY: every pinned repository, manifest, resolver, layout module,
style, color, layout and gallery HTML page in this module is fabricated locally.
No real upstream checkout, Git, model, browser, command or network call is used.
"""
from __future__ import annotations

import builtins
import contextlib
import copy
import hashlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import handdraw_style_brief as brief
import handdraw_style_library as library


LIBRARY_ROOT_ENV = "CONTENT_STUDIO_HANDDRAW_ROOT"
GALLERY_ROOT_ENV = "CONTENT_STUDIO_HANDDRAW_GALLERY_ROOT"
COMMIT = "b" * 40
PREFIX = "skills/handdraw-style-prompter/"
REFERENCE_IMAGE = b"SYNTHETIC-REFERENCE-IMAGE-BYTES"

DIRECTIONS_PAYLOAD = {
    "schema_version": "shared-design-directions.v1",
    "directions": {
        "editorial-field-guide": {
            "version": "1.0.0",
            "routes": {
                "article": {"status": "route-eligible"},
                "social-card": {"status": "route-eligible-explicit"},
            },
            "excluded_routes": {"article_visual_modes": ["editorial-photo-mix"]},
        },
        "structure-only": {
            "version": "1.0.0",
            "routes": {"article": {"status": "structure-only-explicit"}},
            "excluded_routes": {"article_visual_modes": []},
        },
    },
}

STYLE_ASSET_PATHS = '''from pathlib import Path


def asset_root():
    return Path(__file__).resolve().parent.parent / "references"
'''

RESOLVER = '''from style_asset_paths import asset_root


def resolve(model, number, capabilities):
    return {"reference_path": str(asset_root() / "styles" / f"style-{number}.png"), "model": model}
'''

LAYOUT_LIBRARY = '''from pathlib import Path


def read_prompt(path):
    return Path(path).read_text(encoding="utf-8")
'''

STYLES = [
    {"number": "001", "generation_name": "Synthetic Line", "family": "line", "tags": ["synthetic", "line"]},
    {"number": "002", "generation_name": "Synthetic Article", "family": "article"},
]
COLORS = [
    {"id": "c1", "name_zh": "墨黑", "name_en": "Ink Black", "hex": "#111111"},
    {"id": "c2", "name_zh": "朱红", "name_en": "Vermilion", "hex": "#cc3311"},
]
LAYOUTS = [{"id": "L1", "prompt_file": "layouts/L1.txt", "name_en": "Synthetic Layout"}]
MODEL_CAPABILITIES = {"default": {"name_activation": "unknown"}, "models": {}}

GALLERY_INDEX = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Synthetic Style Gallery</title>
</head>
<body>
<header>
<a href="index.html">Styles</a>
<a href="./layouts.html">Layouts</a>
<a href="colors.html">Colors</a>
<a href="assets.html">Assets</a>
<a href="tutorials.html">Tutorials</a>
</header>
<main><p id="caption">Synthetic style catalog</p></main>
<button id="button" type="button">Copy prompt</button>
<textarea id="area"></textarea>
<script>
const currentLang = 'en';
const I18N = { en: { copyFailed: 'Copy failed' }, zh: { copyFailed: 'Copy failed' } };
const button = document.getElementById('button');
function copySelected() {
  const area = document.getElementById('area');
  area.select();
  document.execCommand('copy');
  document.body.append(area);
}
checkRepositoryUpdate();
</script>
</body>
</html>
"""

GALLERY_LAYOUTS = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Synthetic Layout Gallery</title>
</head>
<body>
<header>
<a href="index.html">Styles</a>
<a href="layouts.html">Layouts</a>
<a href="colors.html">Colors</a>
<a href="assets.html">Assets</a>
<a href="tutorials.html">Tutorials</a>
</header>
<button id="copyButton" type="button">Copy layout</button>
<textarea id="area"></textarea>
<script>
const currentLang = 'en';
const I18N = { en: { copyFailed: 'Copy failed' } };
const copyButton = document.getElementById('copyButton');
function copyLayout() {
  const area = document.getElementById('area');
  area.select();
  document.execCommand('copy');
  document.body.append(area);
}
</script>
</body>
</html>
"""

GALLERY_COLORS = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Synthetic Color Gallery</title>
</head>
<body>
<header>
<a href="index.html">Styles</a>
<a href="layouts.html">Layouts</a>
<a href="colors.html">Colors</a>
<a href="assets.html">Assets</a>
<a href="tutorials.html">Tutorials</a>
</header>
<main><p id="caption">Synthetic colors</p></main>
</body>
</html>
"""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)


def _patch_reads(target: Path, payloads):
    """Script read_bytes/read_text for one exact path with a shared call counter."""
    real_bytes = Path.read_bytes
    real_text = Path.read_text
    state = {"calls": 0}

    def next_payload():
        state["calls"] += 1
        position = state["calls"] - 1
        if position < len(payloads):
            return payloads[position]
        return payloads[-1]

    def fake_read_bytes(self):
        if self.resolve() == target:
            return next_payload()
        return real_bytes(self)

    def fake_read_text(self, *args, **kwargs):
        if self.resolve() == target:
            encoding = kwargs.get("encoding") or "utf-8"
            return next_payload().decode(encoding)
        return real_text(self, *args, **kwargs)

    stack = contextlib.ExitStack()
    stack.enter_context(mock.patch.object(Path, "read_bytes", fake_read_bytes))
    stack.enter_context(mock.patch.object(Path, "read_text", fake_read_text))
    return stack, state


class LibraryFixture:
    """Fabricate one pinned full library checkout plus packaged config resources."""

    def __init__(self, base: Path):
        self.base = Path(base)
        self.studio = self.base / "studio"
        self.upstream = self.base / "upstream"
        self.config_dir = self.studio / "config"
        self.manifest_path = self.config_dir / "handdraw-library-source-manifest.v1.json"
        self.directions_path = self.config_dir / "design-directions.v1.json"
        self.default_config_path = self.config_dir / "handdraw-style-library.v1.json"
        self.commit = COMMIT
        self.files: dict[str, str] = {}
        _write(self.directions_path, json.dumps(DIRECTIONS_PAYLOAD, ensure_ascii=False, indent=2))
        self._write_upstream()
        self._write_manifest()
        self._write_config()

    def _put(self, relative: str, data) -> None:
        path = self.upstream / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            data = data.encode("utf-8")
        path.write_bytes(data)
        self.files[relative] = _sha(data)

    def _write_upstream(self) -> None:
        self._put(PREFIX + "scripts/style_asset_paths.py", STYLE_ASSET_PATHS)
        self._put(PREFIX + "scripts/resolve_reference.py", RESOLVER)
        self._put(PREFIX + "scripts/layout_library.py", LAYOUT_LIBRARY)
        self._put(PREFIX + "references/styles.json", json.dumps(STYLES, ensure_ascii=False, indent=2))
        self._put(PREFIX + "references/colors.json", json.dumps(COLORS, ensure_ascii=False, indent=2))
        self._put(PREFIX + "references/layouts.json", json.dumps(LAYOUTS, ensure_ascii=False, indent=2))
        self._put(PREFIX + "references/model_capabilities.json",
                  json.dumps(MODEL_CAPABILITIES, ensure_ascii=False, indent=2))
        self._put(PREFIX + "references/styles/style-001.png", REFERENCE_IMAGE)
        self._put(PREFIX + "references/layouts/L1.txt", "SYNTHETIC LAYOUT PROMPT\n")
        self._put(PREFIX + "gallery/index.html", GALLERY_INDEX)
        self._put(PREFIX + "gallery/layouts.html", GALLERY_LAYOUTS)
        self._put(PREFIX + "gallery/colors.html", GALLERY_COLORS)

    def _write_manifest(self) -> None:
        payload = json.dumps(
            {"commit": self.commit, "files": dict(self.files)},
            ensure_ascii=False, sort_keys=True,
        ).encode("utf-8")
        self.manifest_bytes = payload
        self.manifest_sha = _sha(payload)
        _write(self.upstream / "local-source-manifest.json", payload)
        _write(self.manifest_path, payload)

    def _write_config(self) -> None:
        self.default_config = {
            "schema_version": "handdraw-style-library.v1",
            "repository": "https://example.invalid/synthetic-handraw-style",
            "commit": self.commit,
            "local_path": None,
            "manifest_sha256": self.manifest_sha,
            "attribution": "Synthetic Creator <synthetic@example.invalid>",
            "license": "Synthetic fixture only; attribution required",
            "license_status": "verified-pinned-custom-license-with-attribution",
            "asset_rights_status": "unverified-for-redistribution",
            "manifest_path": "config/handdraw-library-source-manifest.v1.json",
        }
        _write(self.default_config_path,
               json.dumps(self.default_config, ensure_ascii=False, indent=2))

    def config(self, **overrides) -> dict:
        config = dict(self.default_config)
        config.update(overrides)
        return config

    def set_upstream(self, relative: str, data) -> None:
        self._put(relative, data)
        self._write_manifest()
        self._write_config()

    def path(self, relative: str) -> Path:
        return self.upstream / relative


class LibraryCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.fixture = LibraryFixture(self.base)
        clean_env = {
            key: value for key, value in os.environ.items()
            if key not in (LIBRARY_ROOT_ENV, GALLERY_ROOT_ENV, "CONTENT_STUDIO_HANDDRAW_LEGACY_ROOT")
        }
        env_patch = mock.patch.dict(os.environ, clean_env, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.patchers = [
            mock.patch.object(library, "ROOT", self.fixture.studio),
            mock.patch.object(library, "CONFIG", self.fixture.default_config_path),
            mock.patch.object(brief, "DIRECTIONS", self.fixture.directions_path),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.addCleanup(self._stop_patchers)

    def _stop_patchers(self):
        for patcher in self.patchers:
            patcher.stop()

    def make_library(self, **overrides) -> library.Library:
        return library.Library(self.fixture.config(**overrides), source_root=self.fixture.upstream)


class LibraryRootTests(LibraryCase):
    def test_absent_root_fails_closed_with_stable_error(self):
        with self.assertRaises(ValueError) as caught:
            library.Library(self.fixture.config())
        self.assertEqual(str(caught.exception), library.MISSING_LIBRARY_ROOT)

    def test_explicit_env_and_configured_roots(self):
        self.make_library()
        with mock.patch.dict(os.environ, {LIBRARY_ROOT_ENV: str(self.fixture.upstream)}, clear=True):
            library.Library(self.fixture.config())
        with mock.patch.dict(os.environ, {LIBRARY_ROOT_ENV: str(self.base / "wrong")}, clear=True):
            self.make_library()
        library.Library(self.fixture.config(local_path=str(self.fixture.upstream)))
        library.Library(self.fixture.config(local_path="../upstream"))

    def test_default_packaged_config_uses_studio_root(self):
        lib = library.Library(source_root=self.fixture.upstream)
        self.assertEqual(lib.root, self.fixture.upstream.resolve())
        with self.assertRaises(ValueError) as caught:
            library.Library()
        self.assertEqual(str(caught.exception), library.MISSING_LIBRARY_ROOT)

    def test_packaged_manifest_binding_and_legacy_fallback(self):
        self.make_library()
        fallback_manifest = self.fixture.upstream / "local-source-manifest.json"
        original = fallback_manifest.read_bytes()
        fallback_manifest.unlink()
        try:
            self.make_library()
        finally:
            fallback_manifest.write_bytes(original)
        library.Library(self.fixture.config(manifest_path=None), source_root=self.fixture.upstream)
        self.fixture.manifest_path.unlink()
        try:
            with self.assertRaisesRegex(ValueError, "manifest has drifted"):
                self.make_library()
        finally:
            self.fixture._write_manifest()
            self.fixture._write_config()

    def test_manifest_commit_and_asset_hash_drift(self):
        lib = self.make_library()
        original_manifest = self.fixture.manifest_path.read_bytes()
        self.fixture.manifest_path.write_bytes(b'{"commit": "tampered"}')
        try:
            with self.assertRaisesRegex(ValueError, "manifest has drifted"):
                self.make_library()
        finally:
            self.fixture.manifest_path.write_bytes(original_manifest)

        new_manifest = json.dumps(
            {"commit": "c" * 40, "files": dict(self.fixture.files)}, sort_keys=True,
        ).encode("utf-8")
        self.fixture.manifest_path.write_bytes(new_manifest)
        try:
            drifted = library.Library(
                self.fixture.config(manifest_sha256=_sha(new_manifest)),
                source_root=self.fixture.upstream,
            )
            self.fail("commit drift must fail closed")
        except ValueError as exc:
            self.assertIn("commit binding has drifted", str(exc))
        finally:
            self.fixture._write_manifest()
            self.fixture._write_config()

        styles_path = self.fixture.path(PREFIX + "references/styles.json")
        original_styles = styles_path.read_bytes()
        styles_path.write_bytes(original_styles + b"\n")
        try:
            with self.assertRaisesRegex(ValueError, "missing or changed"):
                self.make_library()
        finally:
            styles_path.write_bytes(original_styles)
        self.make_library()
        self.assertIsInstance(lib, library.Library)

    def test_checked_path_confinement(self):
        lib = self.make_library()
        for relative in ("../outside.json", "skills/../../etc/passwd", str(self.base / "outside.json")):
            with self.subTest(relative=relative):
                with self.assertRaisesRegex(ValueError, "escapes pinned package"):
                    lib.checked(relative)


class LibraryModuleTests(LibraryCase):
    def test_module_allowlist_rejects_unknown_and_traversal_names(self):
        lib = self.make_library()
        for name in (
            "os", "sys", "../resolve_reference", "resolve_reference.py",
            "layout_library/../resolve_reference", "unknown_helper", "", None, ["resolve_reference"],
        ):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    lib.module(name)

    def test_module_import_leaves_no_pyc_and_restores_ambient_module(self):
        lib = self.make_library()
        sentinel = types.ModuleType("synthetic_ambient_style_asset_paths")
        sys.modules["style_asset_paths"] = sentinel
        try:
            resolver = lib.module("resolve_reference")
            self.assertIs(sys.modules["style_asset_paths"], sentinel)
            self.assertEqual(resolver.resolve("synthetic-model", "001", {})["model"], "synthetic-model")
        finally:
            sys.modules.pop("style_asset_paths", None)
        lib.module("resolve_reference")
        self.assertNotIn("style_asset_paths", sys.modules)
        self.assertFalse(list(self.fixture.upstream.rglob("__pycache__")))
        self.assertFalse(list(self.fixture.upstream.rglob("*.pyc")))

    def test_module_rechecks_hashes_at_call_time(self):
        lib = self.make_library()
        resolver_path = self.fixture.path(PREFIX + "scripts/resolve_reference.py")
        original = resolver_path.read_bytes()
        resolver_path.write_bytes(original + b"\n# synthetic drift\n")
        try:
            with self.assertRaisesRegex(ValueError, "missing or changed"):
                lib.module("resolve_reference")
        finally:
            resolver_path.write_bytes(original)

    def test_layout_library_reads_checked_prompt_file(self):
        lib = self.make_library()
        prompt_file = lib.checked(PREFIX + "references/layouts/L1.txt")
        module = lib.module("layout_library")
        self.assertEqual(module.read_prompt(prompt_file), "SYNTHETIC LAYOUT PROMPT\n")


class CatalogTests(LibraryCase):
    def test_catalog_counts_search_and_selection_policy(self):
        lib = self.make_library()
        catalog = lib.catalog()
        self.assertEqual(len(catalog["styles"]), len(STYLES))
        self.assertEqual(len(catalog["layouts"]), len(LAYOUTS))
        self.assertEqual(len(catalog["colors"]), len(COLORS))
        self.assertEqual(catalog["selection"], "browse-or-explicit-selection; no aesthetic scoring")

        colors = lib.catalog("ink black")
        self.assertEqual([row["id"] for row in colors["colors"]], ["c1"])
        self.assertEqual(colors["styles"], [])
        self.assertEqual(colors["layouts"], [])

        styles = lib.catalog("synthetic line")
        self.assertEqual([row["number"] for row in styles["styles"]], ["001"])

        empty = lib.catalog("definitely-absent-token")
        self.assertEqual(empty["styles"], [])
        self.assertEqual(empty["layouts"], [])
        self.assertEqual(empty["colors"], [])


def make_prompt_item(
    *, direction="editorial-field-guide", version="1.0.0", media="article",
    slot_overrides=None, visual_mode="editorial-line", artifacts=None,
) -> dict:
    slot = {
        "slot_id": "slot-1",
        "status": "planned",
        "media_role": "explanatory",
        "route": "generated-image",
        "purpose": "Synthetic explanatory purpose",
        "visual_brief": {"metaphor": "m", "central_action": "a"},
    }
    slot.update(slot_overrides or {})
    return {
        "schema_version": "0.2",
        "content_id": "content-synthetic-2",
        "visual": {
            "design_system": {
                "design_direction": {"direction_id": direction, "version": version},
                "media_adapter": media,
            },
            "article_visual_plan": {"visual_mode": visual_mode, "slots": [slot]},
            "render_artifacts": [] if artifacts is None else artifacts,
        },
    }


def make_request(**overrides) -> dict:
    request = {
        "style_number": 1,
        "theme": {"zh": "合成主题", "en": "Synthetic theme"},
        "mode": "pure-image",
        "frozen_text": ["Exact 42", "第二行"],
        "model": "synthetic-model",
    }
    request.update(overrides)
    return request


class PromptTests(LibraryCase):
    def test_prompt_fields_frozen_text_and_no_mutation(self):
        lib = self.make_library()
        item = make_prompt_item()
        before = copy.deepcopy(item)
        request = make_request()
        result = lib.prompt(item, "slot-1", request)
        self.assertEqual(item, before)
        self.assertEqual(result["schema_version"], "handdraw-style-prompt.v1")
        self.assertEqual(result["status"], "candidate-only")
        self.assertEqual(result["content_id"], "content-synthetic-2")
        self.assertEqual(result["target_id"], "slot-1")
        self.assertEqual(result["purpose"], "Synthetic explanatory purpose")
        self.assertEqual(result["style_number"], "001")
        self.assertEqual(result["style_name"], "Synthetic Line")
        self.assertEqual(result["source_commit"], COMMIT)
        self.assertEqual(result["color_ids"], [])
        self.assertIsNone(result["layout_reference"])
        self.assertEqual(result["frozen_text"], request["frozen_text"])
        self.assertEqual(result["content_sha256"],
                         hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True).encode()).hexdigest())
        expected_asset = (self.fixture.path(PREFIX + "references/styles/style-001.png")).resolve()
        self.assertEqual(result["referenced_image_paths"], [str(expected_asset)])
        self.assertEqual(result["reference_sha256"], _sha(REFERENCE_IMAGE))
        self.assertEqual(result["reference_role"], "style-only")
        self.assertEqual(result["model"], "synthetic-model")
        self.assertEqual(result["model_calibration"],
                         "upstream_claim_not_locally_verified; conservative_reference_required")
        self.assertEqual(result["attribution"], self.fixture.default_config["attribution"])
        self.assertFalse(result["image_generated"])
        self.assertTrue(result["manual_review_required"])
        frozen_json = json.dumps(request["frozen_text"], ensure_ascii=False)
        zh, en = result["prompts"]["zh"], result["prompts"]["en"]
        self.assertIn("风格：Synthetic Line", zh)
        self.assertIn("主题（锁定）：合成主题", zh)
        self.assertIn("画中文字只能逐字使用：" + frozen_json, zh)
        self.assertIn("不得增删、润色、翻译文字或数字", zh)
        self.assertIn("Style: Synthetic Line", en)
        self.assertIn("Locked subject: Synthetic theme", en)
        self.assertIn("Use only this exact visible text: " + frozen_json, en)
        self.assertIn("Do not add, rewrite or translate text or numbers.", en)
        self.assertIn("沿用当前内容已确认配色，不自行重新推荐。", zh)
        self.assertIn("Retain the existing approved palette; do not select a new palette.", en)

    def test_prompt_without_frozen_text_declares_no_visible_text(self):
        lib = self.make_library()
        result = lib.prompt(make_prompt_item(), "slot-1", make_request(frozen_text=[]))
        self.assertEqual(result["frozen_text"], [])
        self.assertIn("画面不出现文字、数字、水印或编号。", result["prompts"]["zh"])
        self.assertIn("No visible text, numbers, watermarks or identifiers.", result["prompts"]["en"])
        self.assertNotIn("逐字使用", result["prompts"]["zh"])

    def test_prompt_layout_colors_composition_and_exact_frozen_text(self):
        lib = self.make_library()
        item = make_prompt_item()
        before = copy.deepcopy(item)
        request = make_request(
            layout_id="l1",
            composition={"zh": "左侧主体", "en": "left subject"},
            color_ids=["c1", "c2"],
        )
        result = lib.prompt(item, "slot-1", request)
        self.assertEqual(item, before)
        layout = result["layout_reference"]
        self.assertEqual(layout["id"], "L1")
        self.assertEqual(layout["source_prompts"], "SYNTHETIC LAYOUT PROMPT\n")
        self.assertIn("构图（已确认）：左侧主体", result["prompts"]["zh"])
        self.assertIn("配色：墨黑, 朱红", result["prompts"]["zh"])
        self.assertIn("Confirmed composition: left subject", result["prompts"]["en"])
        self.assertIn("Palette: Ink Black, Vermilion", result["prompts"]["en"])
        self.assertEqual(result["color_ids"], ["c1", "c2"])
        self.assertEqual(result["prompts"]["zh"].splitlines()[2], "构图（已确认）：左侧主体")

        palette = lib.prompt(make_prompt_item(), "slot-1", make_request(
            layout_id=None, palette={"zh": "米白与墨黑", "en": "off-white and ink"}))
        self.assertIn("配色：米白与墨黑", palette["prompts"]["zh"])
        self.assertIn("Palette: off-white and ink", palette["prompts"]["en"])

        cases = [
            ("unknown-layout", {"layout_id": "L9"}, "Unknown layout ID"),
            ("layout-without-composition", {"layout_id": "L1"}, "requires confirmed composition"),
            ("duplicate-colors", {"color_ids": ["c1", "c1"]}, "unique list"),
            ("unknown-color", {"color_ids": ["c9"]}, "Unknown color ID"),
            ("colors-and-palette", {"color_ids": ["c1"], "palette": {"zh": "红", "en": "red"}},
             "either selected colors"),
            ("unconfirmed-palette", {"palette": {"zh": "红"}}, "either selected colors"),
            ("unknown-style", {"style_number": 999}, "Unknown style number"),
            ("unknown-mode", {"mode": "poster"}, "Unknown prompt mode"),
            ("missing-theme-en", {"theme": {"zh": "合成主题"}}, "Supply confirmed theme"),
            ("blank-theme-zh", {"theme": {"zh": "   ", "en": "Synthetic theme"}}, "Supply confirmed theme"),
            ("frozen-not-list", {"frozen_text": "Exact 42"}, "frozen_text must contain"),
            ("frozen-blank", {"frozen_text": [""]}, "frozen_text must contain"),
        ]
        for label, overrides, pattern in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, pattern):
                    lib.prompt(make_prompt_item(), "slot-1", make_request(**overrides))

    def test_prompt_target_and_design_eligibility_refusals(self):
        lib = self.make_library()
        cases = [
            ("selected-slot", make_prompt_item(slot_overrides={"status": "selected"}), "cannot alter"),
            ("diagram-slot", make_prompt_item(slot_overrides={"route": "diagram"}),
             "generated-image article slot"),
            ("blank-purpose", make_prompt_item(slot_overrides={"purpose": "  "}), "purpose is required"),
            ("media-mismatch", make_prompt_item(media="web"), "not eligible"),
            ("version-mismatch", make_prompt_item(version="0.0.1"), "not eligible"),
            ("structure-route", make_prompt_item(direction="structure-only"), "not eligible"),
            ("excluded-mode", make_prompt_item(visual_mode="editorial-photo-mix"),
             "excludes this article visual mode"),
        ]
        for label, item, pattern in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, pattern):
                    lib.prompt(item, "slot-1", make_request())
        artifact_item = make_prompt_item(
            artifacts=[{"artifact_id": "social-1", "media_adapter": "social-card",
                        "renderer": "social-card", "status": "planned"}],
        )
        with self.assertRaisesRegex(ValueError, "generated-image article slot"):
            lib.prompt(artifact_item, "social-1", make_request())
        no_content = make_prompt_item()
        no_content["schema_version"] = "0.1"
        with self.assertRaisesRegex(ValueError, "versioned content item"):
            lib.prompt(no_content, "slot-1", make_request())


class GalleryTests(LibraryCase):
    def test_gallery_requires_explicit_output_root_or_env(self):
        lib = self.make_library()
        with self.assertRaises(ValueError) as caught:
            lib.gallery()
        self.assertEqual(str(caught.exception), library.MISSING_GALLERY_ROOT)
        output = self.base / "env-gallery"
        with mock.patch.dict(os.environ, {GALLERY_ROOT_ENV: str(output)}, clear=True):
            result = lib.gallery()
        self.assertTrue(Path(result["galleries"]["styles"]).is_file())

    def test_gallery_refuses_upstream_and_installed_resource_roots(self):
        lib = self.make_library()
        with self.assertRaisesRegex(ValueError, "upstream"):
            lib.gallery(self.fixture.upstream / "gallery-cache")
        with self.assertRaisesRegex(ValueError, "upstream"):
            lib.gallery(self.fixture.upstream)
        with self.assertRaisesRegex(ValueError, "installed resource"):
            lib.gallery(self.fixture.studio / "gallery-cache")
        with self.assertRaisesRegex(ValueError, "installed resource"):
            lib.gallery(lib.resource_root)

    def test_gallery_builds_credited_navigation_overlay(self):
        lib = self.make_library()
        output = self.base / "gallery-out"
        result = lib.gallery(output)
        self.assertEqual(result["status"], "local-reference-library")
        self.assertEqual(result["counts"],
                         {"styles": len(STYLES), "layouts": len(LAYOUTS), "colors": len(COLORS)})
        self.assertEqual(result["source"], self.fixture.default_config["repository"])
        self.assertEqual(result["commit"], COMMIT)
        self.assertEqual(result["attribution"], self.fixture.default_config["attribution"])
        self.assertEqual(result["license_status"], "verified-pinned-custom-license-with-attribution")
        self.assertEqual(result["asset_rights_status"], "unverified-for-redistribution")
        self.assertTrue(result["manual_review_required"])
        self.assertFalse(result["image_generated"])

        styles = Path(result["galleries"]["styles"])
        layouts = Path(result["galleries"]["layouts"])
        colors = Path(result["galleries"]["colors"])
        for path in (styles, layouts, colors):
            self.assertTrue(path.is_file())
        destination = styles.parent
        source_gallery = (self.fixture.upstream / (PREFIX + "gallery")).resolve()
        index_text = styles.read_text(encoding="utf-8")
        layouts_text = layouts.read_text(encoding="utf-8")
        colors_text = colors.read_text(encoding="utf-8")
        for text in (index_text, layouts_text, colors_text):
            self.assertIn('<base href="' + source_gallery.as_uri() + '/">', text)
            self.assertIn('id="handdraw-source-attribution"', text)
            self.assertIn("yang0", text)
            self.assertIn("https://github.com/yang0/handraw-style", text)
            self.assertIn("&lt;synthetic@example.invalid&gt;", text)
            self.assertNotIn("<synthetic@example.invalid>", text)
            self.assertIn('aria-disabled="true"', text)
            self.assertNotIn('href="assets.html"', text)
            self.assertNotIn('href="tutorials.html"', text)
        for name in ("index", "layouts", "colors"):
            self.assertIn('href="' + (destination / f"{name}.html").as_uri() + '"', index_text)
        self.assertIn("handdrawManualCopy", index_text)
        self.assertIn("handdrawManualCopy", layouts_text)
        self.assertIn("let copied=false;try{copied=document.execCommand('copy');}catch{}", index_text)
        self.assertIn("if(!copied){const payload=area.value;area.remove();button.textContent=", index_text)
        self.assertIn("if(!copied){const payload=area.value;area.remove();copyButton.textContent=", layouts_text)
        self.assertNotIn("checkRepositoryUpdate();", index_text)
        self.assertIn("update checks disabled", index_text)

    def test_gallery_repeat_is_immutable_and_changed_cache_is_refused(self):
        lib = self.make_library()
        output = self.base / "gallery-out"
        first = lib.gallery(output)
        styles_path = Path(first["galleries"]["styles"])
        first_bytes = styles_path.read_bytes()
        second = lib.gallery(output)
        self.assertEqual(second["galleries"], first["galleries"])
        self.assertEqual(styles_path.read_bytes(), first_bytes)
        styles_path.write_text("changed by synthetic test", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cache changed"):
            lib.gallery(output)

    def test_pinned_gallery_shape_drift_is_refused(self):
        broken_copy = LibraryFixture(self.base / "drift-copy")
        broken_copy.set_upstream(
            PREFIX + "gallery/index.html",
            GALLERY_INDEX.replace(
                "document.execCommand('copy');",
                "document.execCommand('copy');document.execCommand('copy');",
            ),
        )
        with mock.patch.object(library, "ROOT", broken_copy.studio), \
                mock.patch.object(library, "CONFIG", broken_copy.default_config_path):
            lib = library.Library(broken_copy.config(), source_root=broken_copy.upstream)
            with self.assertRaisesRegex(ValueError, "copy handler shape changed"):
                lib.gallery(self.base / "drift-copy-out")

        broken_body = LibraryFixture(self.base / "drift-body")
        broken_body.set_upstream(PREFIX + "gallery/colors.html",
                                 GALLERY_COLORS.replace("</body>", ""))
        with mock.patch.object(library, "ROOT", broken_body.studio), \
                mock.patch.object(library, "CONFIG", broken_body.default_config_path):
            lib = library.Library(broken_body.config(), source_root=broken_body.upstream)
            with self.assertRaisesRegex(ValueError, "document shape changed"):
                lib.gallery(self.base / "drift-body-out")

    def test_symlink_output_escape_is_refused_or_skipped(self):
        lib = self.make_library()
        link = self.base / "upstream-link"
        try:
            os.symlink(self.fixture.upstream, link, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation not permitted on this host: {exc}")
        with self.assertRaisesRegex(ValueError, "upstream"):
            lib.gallery(link)


class BriefCliLibraryTests(LibraryCase):
    def test_gallery_catalog_and_prompt_cli_use_library_root(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = brief.main([
                "--library-root", str(self.fixture.upstream),
                "gallery", "--output-root", str(self.base / "cli-gallery"),
            ])
        self.assertEqual(status, 0)
        gallery = json.loads(stdout.getvalue())
        self.assertTrue(Path(gallery["galleries"]["styles"]).is_file())

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = brief.main([
                "catalog", "--library-root", str(self.fixture.upstream), "--query", "ink black",
            ])
        self.assertEqual(status, 0)
        catalog = json.loads(stdout.getvalue())
        self.assertEqual([row["id"] for row in catalog["colors"]], ["c1"])

        item_path = self.base / "prompt-item.json"
        request_path = self.base / "prompt-request.json"
        output = self.base / "prompt-out.json"
        _write(item_path, json.dumps(make_prompt_item(), ensure_ascii=False))
        _write(request_path, json.dumps(make_request(), ensure_ascii=False))
        argv = [
            "prompt", "--library-root", str(self.fixture.upstream),
            "--item", str(item_path), "--target-id", "slot-1",
            "--request", str(request_path), "--output", str(output),
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(brief.main(argv), 0)
        first = output.read_bytes()
        payload = json.loads(first.decode("utf-8"))
        self.assertEqual(payload["schema_version"], "handdraw-style-prompt.v1")
        stderr = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            self.assertEqual(brief.main(argv), 2)
        self.assertIn("ERROR:", stderr.getvalue())
        self.assertEqual(output.read_bytes(), first)

    def test_gallery_cli_without_output_root_returns_controlled_error(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = brief.main(["gallery", "--library-root", str(self.fixture.upstream)])
        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("not configured", stderr.getvalue())


class LibraryConsumedBytesTests(LibraryCase):
    def test_tampered_resolver_buffer_is_refused_before_exec(self):
        lib = self.make_library()
        resolver_path = self.fixture.path(PREFIX + "scripts/resolve_reference.py").resolve()
        real = resolver_path.read_bytes()
        tampered = real + b"\nimport builtins\nbuiltins.SYNTHETIC_UNHASHED_MARKER = True\n"
        patcher, state = _patch_reads(resolver_path, [tampered])
        try:
            with self.assertRaisesRegex(ValueError, "missing or changed"):
                with patcher:
                    lib.module("resolve_reference")
            self.assertFalse(hasattr(builtins, "SYNTHETIC_UNHASHED_MARKER"))
        finally:
            builtins.__dict__.pop("SYNTHETIC_UNHASHED_MARKER", None)
        self.assertEqual(state["calls"], 1)

    def test_resolver_swap_is_not_consumed_after_verification(self):
        lib = self.make_library()
        resolver_path = self.fixture.path(PREFIX + "scripts/resolve_reference.py").resolve()
        real = resolver_path.read_bytes()
        tampered = real + b"\nimport builtins\nbuiltins.SYNTHETIC_UNHASHED_MARKER = True\n"
        patcher, state = _patch_reads(resolver_path, [real, tampered])
        try:
            with patcher:
                module = lib.module("resolve_reference")
            self.assertFalse(hasattr(builtins, "SYNTHETIC_UNHASHED_MARKER"))
        finally:
            builtins.__dict__.pop("SYNTHETIC_UNHASHED_MARKER", None)
        self.assertEqual(state["calls"], 1)
        self.assertEqual(module.resolve("m", "001", {})["model"], "m")

    def test_tampered_manifest_bytes_are_refused_before_decode(self):
        manifest_path = self.fixture.manifest_path.resolve()
        tampered = json.dumps(
            {"commit": "c" * 40, "files": dict(self.fixture.files)}, sort_keys=True,
        ).encode("utf-8")
        patcher, state = _patch_reads(manifest_path, [tampered])
        with self.assertRaisesRegex(ValueError, "manifest has drifted"):
            with patcher:
                library.Library(self.fixture.config(), source_root=self.fixture.upstream)
        self.assertEqual(state["calls"], 1)

    def test_manifest_swap_is_not_consumed_after_verification(self):
        manifest_path = self.fixture.manifest_path.resolve()
        real = manifest_path.read_bytes()
        tampered = json.dumps(
            {"commit": "c" * 40, "files": dict(self.fixture.files)}, sort_keys=True,
        ).encode("utf-8")
        patcher, state = _patch_reads(manifest_path, [real, tampered])
        with patcher:
            lib = self.make_library()
        self.assertEqual(state["calls"], 1)
        self.assertEqual(lib.manifest["commit"], COMMIT)

    def test_tampered_styles_bytes_are_refused_before_decode(self):
        lib = self.make_library()
        styles_path = self.fixture.path(PREFIX + "references/styles.json").resolve()
        tampered = json.dumps([{"number": "999", "generation_name": "Tampered"}]).encode("utf-8")
        patcher, state = _patch_reads(styles_path, [tampered])
        with self.assertRaisesRegex(ValueError, "missing or changed"):
            with patcher:
                lib.data("styles.json")
        self.assertEqual(state["calls"], 1)
        self.assertEqual(lib.styles[0]["number"], "001")

    def test_prompt_reference_asset_uses_single_verified_buffer(self):
        lib = self.make_library()
        asset_path = self.fixture.path(PREFIX + "references/styles/style-001.png").resolve()
        real = asset_path.read_bytes()
        tampered = real + b"SYNTHETIC-UNVERIFIED-REFERENCE-BYTES"
        patcher, state = _patch_reads(asset_path, [real, tampered])
        with patcher:
            result = lib.prompt(make_prompt_item(), "slot-1", make_request())
        self.assertEqual(state["calls"], 1)
        self.assertEqual(result["reference_sha256"], _sha(real))

    def test_gallery_html_swap_is_not_consumed_after_verification(self):
        lib = self.make_library()
        index_path = self.fixture.path(PREFIX + "gallery/index.html").resolve()
        real = index_path.read_bytes()
        tampered = real + b"\n<!-- SYNTHETIC_UNVERIFIED_MARKER -->\n"
        patcher, state = _patch_reads(index_path, [real, tampered])
        with patcher:
            result = lib.gallery(self.base / "swap-gallery")
        self.assertEqual(state["calls"], 1)
        index_text = Path(result["galleries"]["styles"]).read_text(encoding="utf-8")
        self.assertNotIn("SYNTHETIC_UNVERIFIED_MARKER", index_text)


class GalleryContainmentTests(LibraryCase):
    def test_generated_destination_alias_is_refused(self):
        lib = self.make_library()
        output = self.base / "aliased-gallery"
        target_parent = output.resolve()
        real_resolve = Path.resolve

        def fake_resolve(self, *args, **kwargs):
            if self != target_parent and self.parent == target_parent:
                return lib.root
            return real_resolve(self, *args, **kwargs)

        before = self.fixture.path(PREFIX + "gallery/index.html").read_bytes()
        with mock.patch.object(Path, "resolve", fake_resolve):
            with self.assertRaises(ValueError):
                lib.gallery(output)
        self.assertEqual(self.fixture.path(PREFIX + "gallery/index.html").read_bytes(), before)
        self.assertFalse(output.exists())

    def test_generated_page_alias_is_refused(self):
        lib = self.make_library()
        output = self.base / "page-alias-gallery"
        target_parent = output.resolve()
        real_resolve = Path.resolve

        def fake_resolve(self, *args, **kwargs):
            resolved = real_resolve(self, *args, **kwargs)
            if self.name == "index.html" and self.parent.parent == target_parent:
                return lib.root / (PREFIX + "gallery/index.html")
            return resolved

        with mock.patch.object(Path, "resolve", fake_resolve):
            with self.assertRaises(ValueError):
                lib.gallery(output)
        self.assertFalse(output.exists())

    def test_gallery_exclusive_creation_does_not_overwrite_raced_page(self):
        lib = self.make_library()
        output = self.base / "race-gallery"
        first = lib.gallery(output)
        styles_path = Path(first["galleries"]["styles"]).resolve()
        styles_path.unlink()
        real_open = Path.open
        state = {"raced": False}

        def fake_open(self, mode="r", *args, **kwargs):
            if self == styles_path and mode == "x" and not state["raced"]:
                state["raced"] = True
                with real_open(self, "w", encoding="utf-8") as handle:
                    handle.write("raced page bytes")
                return real_open(self, mode, *args, **kwargs)
            return real_open(self, mode, *args, **kwargs)

        with mock.patch.object(Path, "open", fake_open):
            with self.assertRaisesRegex(ValueError, "cache changed"):
                lib.gallery(output)
        self.assertEqual(styles_path.read_text(encoding="utf-8"), "raced page bytes")

    def test_gallery_missing_license_evidence_stays_not_declared(self):
        config = self.fixture.config()
        config.pop("license_status", None)
        config.pop("asset_rights_status", None)
        lib = library.Library(config, source_root=self.fixture.upstream)
        result = lib.gallery(self.base / "license-missing-gallery")
        self.assertEqual(result["license_status"], "not-declared")
        self.assertEqual(result["asset_rights_status"], "unverified-for-redistribution")

    def test_gallery_explicit_license_metadata_passes_through(self):
        config = self.fixture.config(
            license_status="verified-pinned-custom-license-with-attribution",
            asset_rights_status="unverified-for-redistribution",
        )
        lib = library.Library(config, source_root=self.fixture.upstream)
        result = lib.gallery(self.base / "license-explicit-gallery")
        self.assertEqual(result["license_status"], "verified-pinned-custom-license-with-attribution")
        self.assertEqual(result["asset_rights_status"], "unverified-for-redistribution")


if __name__ == "__main__":
    unittest.main()
