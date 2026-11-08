"""Contract tests for the portable handdraw style brief adapter.

SYNTHETIC TEST ONLY: every repository, manifest, index, style, design direction
and content item in this module is fabricated locally. No real upstream checkout,
Git, model, browser, command or network call is used.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import handdraw_style_brief as brief


LEGACY_ROOT_ENV = "CONTENT_STUDIO_HANDDRAW_LEGACY_ROOT"
COMMIT = "1" * 40
STYLE_TARGETS = [
    "editorial-field-guide/article",
    "editorial-field-guide/web",
    "reflective-personal-essay/social-card",
    "reflective-personal-essay/article",
]

DIRECTIONS_PAYLOAD = {
    "schema_version": "shared-design-directions.v1",
    "directions": {
        "editorial-field-guide": {
            "version": "1.0.0",
            "routes": {
                "article": {"status": "route-eligible"},
                "web": {"status": "route-eligible"},
                "social-card": {"status": "route-eligible-explicit"},
            },
            "excluded_routes": {"article_visual_modes": ["editorial-photo-mix"]},
        },
        "reflective-personal-essay": {
            "version": "2.0.0",
            "routes": {
                "article": {"status": "route-eligible-explicit"},
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

INDEX_RECORDS = [
    {"number": "157", "generation_name": "Synthetic Line", "group": "F Synthetic"},
    {"number": "158", "generation_name": "Synthetic Article Only", "group": "F Synthetic"},
]


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


def default_styles() -> dict:
    return {
        "synthetic-line": {
            "source_number": "157",
            "source_generation_name": "Synthetic Line",
            "composition_guidance": "SYNTHETIC composition guidance.",
            "allowed_targets": list(STYLE_TARGETS),
        },
        "article-only": {
            "source_number": "158",
            "source_generation_name": "Synthetic Article Only",
            "composition_guidance": "SYNTHETIC article guidance.",
            "allowed_targets": ["editorial-field-guide/article"],
        },
        "structure-only-style": {
            "source_number": "158",
            "source_generation_name": "Synthetic Article Only",
            "composition_guidance": "SYNTHETIC structure guidance.",
            "allowed_targets": ["structure-only/article"],
        },
        "mystery-style": {
            "source_number": "157",
            "source_generation_name": "Synthetic Line",
            "composition_guidance": "SYNTHETIC mystery guidance.",
            "allowed_targets": ["mystery-direction/article"],
        },
    }


class LegacyFixture:
    """Fabricate one pinned legacy checkout plus its packaged config resources."""

    def __init__(self, base: Path):
        self.base = Path(base)
        self.studio = self.base / "studio"
        self.checkout = self.studio / "legacy-checkout"
        self.directions_path = self.studio / "config" / "design-directions.v1.json"
        self.registry_path = self.studio / "config" / "handdraw-style-brief.v1.json"
        self.manifest_path = self.studio / "config" / "handdraw-legacy-source-manifest.v1.json"
        _write(self.directions_path, json.dumps(DIRECTIONS_PAYLOAD, ensure_ascii=False, indent=2))
        self.set_index(INDEX_RECORDS)
        _write(self.registry_path, json.dumps(self.registry(), ensure_ascii=False, indent=2))

    def set_index(self, records, commit: str = COMMIT) -> None:
        index_bytes = json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8")
        manifest_bytes = json.dumps(
            {"commit": commit, "files": {"styles.json": _sha(index_bytes)}},
            ensure_ascii=False, sort_keys=True,
        ).encode("utf-8")
        self.index_sha = _sha(index_bytes)
        self.manifest_sha = _sha(manifest_bytes)
        _write(self.checkout / "styles.json", index_bytes)
        _write(self.checkout / "source-manifest.json", manifest_bytes)
        _write(self.manifest_path, manifest_bytes)

    def registry(
        self, *, local_path=None,
        manifest_path="config/handdraw-legacy-source-manifest.v1.json",
        manifest_ref="source-manifest.json", commit=None, index_ref="styles.json",
        index_sha256=None, manifest_sha256=None, styles=None,
    ) -> dict:
        source = {
            "repository": "https://example.invalid/synthetic-handraw-style",
            "commit": COMMIT if commit is None else commit,
            "local_path": local_path,
            "index_ref": index_ref,
            "index_sha256": self.index_sha if index_sha256 is None else index_sha256,
            "license_status": "not-declared",
            "asset_rights_status": "unverified",
            "manifest_path": manifest_path,
            "manifest_sha256": self.manifest_sha if manifest_sha256 is None else manifest_sha256,
        }
        if manifest_ref is not None:
            source["manifest_ref"] = manifest_ref
        return {
            "schema_version": "handdraw-style-brief.v1",
            "selection_policy": "explicit-item-and-style-only",
            "status": "candidate-only",
            "source": source,
            "styles": default_styles() if styles is None else styles,
        }


def make_slot(slot_id: str = "slot-1", **overrides) -> dict:
    slot = {
        "slot_id": slot_id,
        "status": "planned",
        "media_role": "explanatory",
        "route": "generated-image",
        "purpose": "Explain the synthetic checklist",
        "visual_brief": {
            "metaphor": "a synthetic bridge",
            "central_action": "crossing the gap",
            "composition": "generous negative space",
        },
    }
    slot.update(overrides)
    return slot


def make_artifact(artifact_id: str, media: str, renderer: str, status: str = "planned") -> dict:
    return {
        "artifact_id": artifact_id,
        "media_adapter": media,
        "renderer": renderer,
        "status": status,
        # Invented, explicit brief fields: rendered media targets also need a
        # metaphor/action before the adapter may draft a candidate brief.
        "visual_brief": {
            "metaphor": "a synthetic social bridge",
            "central_action": "sharing the invented crossing",
            "composition": "single focal panel",
        },
    }


def make_item(
    media: str = "article", *, direction="editorial-field-guide", version="1.0.0",
    slots=None, artifacts=None, visual_mode="editorial-line",
) -> dict:
    return {
        "schema_version": "0.2",
        "content_id": "content-synthetic-1",
        "visual": {
            "design_system": {
                "design_direction": {"direction_id": direction, "version": version},
                "media_adapter": media,
            },
            "article_visual_plan": {
                "visual_mode": visual_mode,
                "slots": [make_slot()] if slots is None else slots,
            },
            "render_artifacts": (
                [make_artifact("social-1", "social-card", "social-card"),
                 make_artifact("web-1", "web", "html-playwright")]
                if artifacts is None else artifacts
            ),
        },
    }


class BriefCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.fixture = LegacyFixture(self.base)
        clean_env = {key: value for key, value in os.environ.items()
                     if key not in (LEGACY_ROOT_ENV,)}
        env_patch = mock.patch.dict(os.environ, clean_env, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        git_guard = mock.patch.object(
            brief.subprocess, "run",
            side_effect=AssertionError("subprocess must be patched in synthetic tests"),
        )
        git_guard.start()
        self.addCleanup(git_guard.stop)
        self.patchers = [
            mock.patch.object(brief, "ROOT", self.fixture.studio),
            mock.patch.object(brief, "REGISTRY", self.fixture.registry_path),
            mock.patch.object(brief, "DIRECTIONS", self.fixture.directions_path),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.addCleanup(self._stop_patchers)

    def _stop_patchers(self):
        for patcher in self.patchers:
            patcher.stop()

    def create(self, item, target="slot-1", style="synthetic-line", *,
               registry=None, metaphor=None, central_action=None, source_root=None):
        if registry is None:
            registry = self.fixture.registry()
        if source_root is None:
            source_root = self.fixture.checkout
        return brief.create_brief(
            item, target, style, metaphor, central_action, registry, source_root=source_root,
        )


class BriefSourceTests(BriefCase):
    def test_absent_root_fails_closed_with_stable_error(self):
        registry = self.fixture.registry()
        with self.assertRaises(ValueError) as caught:
            brief.verify_source(registry)
        self.assertEqual(str(caught.exception), brief.MISSING_LEGACY_ROOT)
        with self.assertRaises(ValueError) as caught:
            brief.create_brief(make_item(), "slot-1", "synthetic-line", None, None, registry)
        self.assertEqual(str(caught.exception), brief.MISSING_LEGACY_ROOT)

    def test_explicit_env_and_configured_roots(self):
        brief.verify_source(self.fixture.registry(), source_root=self.fixture.checkout)
        with mock.patch.dict(os.environ, {LEGACY_ROOT_ENV: str(self.fixture.checkout)}, clear=True):
            brief.verify_source(self.fixture.registry())
        brief.verify_source(self.fixture.registry(local_path="legacy-checkout"))
        brief.verify_source(self.fixture.registry(local_path=str(self.fixture.checkout)))
        with mock.patch.dict(os.environ, {LEGACY_ROOT_ENV: str(self.base / "wrong")}, clear=True):
            brief.verify_source(self.fixture.registry(), source_root=self.fixture.checkout)

    def test_packaged_manifest_path_binding(self):
        brief.verify_source(self.fixture.registry(), source_root=self.fixture.checkout)
        original = self.fixture.manifest_path.read_bytes()
        self.fixture.manifest_path.write_bytes(b'{"commit": "tampered"}')
        with self.assertRaisesRegex(ValueError, "manifest has drifted"):
            brief.verify_source(self.fixture.registry(), source_root=self.fixture.checkout)
        self.fixture.manifest_path.write_bytes(original)

        packaged_only = self.fixture.registry(manifest_ref=None)
        checkout_manifest = self.fixture.checkout / "source-manifest.json"
        original_checkout = checkout_manifest.read_bytes()
        checkout_manifest.unlink()
        try:
            brief.verify_source(packaged_only, source_root=self.fixture.checkout)
        finally:
            checkout_manifest.write_bytes(original_checkout)

        self.fixture.manifest_path.unlink()
        try:
            with self.assertRaisesRegex(ValueError, "manifest has drifted"):
                brief.verify_source(self.fixture.registry(), source_root=self.fixture.checkout)
        finally:
            self.fixture.set_index(INDEX_RECORDS)

    def test_legacy_manifest_ref_fallback_and_escape(self):
        registry = self.fixture.registry(manifest_path=None)
        brief.verify_source(registry, source_root=self.fixture.checkout)
        checkout_manifest = self.fixture.checkout / "source-manifest.json"
        original = checkout_manifest.read_bytes()
        checkout_manifest.write_bytes(b'{"commit": "tampered"}')
        with self.assertRaisesRegex(ValueError, "manifest has drifted"):
            brief.verify_source(registry, source_root=self.fixture.checkout)
        checkout_manifest.write_bytes(original)
        escaping = self.fixture.registry(manifest_path=None, manifest_ref="../source-manifest.json")
        with self.assertRaisesRegex(ValueError, "escapes source snapshot"):
            brief.verify_source(escaping, source_root=self.fixture.checkout)

    def test_git_head_fallback_only_without_manifest(self):
        registry = self.fixture.registry(manifest_path=None, manifest_ref=None)
        completed = mock.Mock(stdout=COMMIT + "\n")
        with mock.patch.object(brief.subprocess, "run", return_value=completed) as run:
            records = brief.verify_source(registry, source_root=self.fixture.checkout)
        self.assertIn("157", records)
        run.assert_called_once()
        command = run.call_args[0][0]
        self.assertEqual(command[:2], ["git", "-C"])
        self.assertEqual(command[2], str(self.fixture.checkout))
        self.assertTrue(run.call_args[1].get("check"))

        drifted = mock.Mock(stdout="2" * 40 + "\n")
        with mock.patch.object(brief.subprocess, "run", return_value=drifted):
            with self.assertRaisesRegex(ValueError, "commit has drifted"):
                brief.verify_source(registry, source_root=self.fixture.checkout)

    def test_index_escape_missing_checkout_and_index(self):
        escaping = self.fixture.registry(index_ref="../styles.json")
        with self.assertRaisesRegex(ValueError, "index escapes source snapshot"):
            brief.verify_source(escaping, source_root=self.fixture.checkout)
        empty = self.base / "empty-checkout"
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, "missing"):
            brief.verify_source(self.fixture.registry(), source_root=empty)
        with self.assertRaisesRegex(ValueError, "missing"):
            brief.verify_source(self.fixture.registry(), source_root=self.base / "absent-checkout")

    def test_index_commit_and_manifest_hash_drift(self):
        self.fixture.checkout.joinpath("styles.json").write_bytes(b"[]")
        with self.assertRaisesRegex(ValueError, "index has drifted"):
            brief.verify_source(self.fixture.registry(), source_root=self.fixture.checkout)
        self.fixture.set_index(INDEX_RECORDS)

        new_manifest = json.dumps(
            {"commit": "3" * 40, "files": {"styles.json": self.fixture.index_sha}},
            sort_keys=True,
        ).encode("utf-8")
        self.fixture.manifest_path.write_bytes(new_manifest)
        registry = self.fixture.registry(manifest_sha256=_sha(new_manifest))
        with self.assertRaisesRegex(ValueError, "commit has drifted"):
            brief.verify_source(registry, source_root=self.fixture.checkout)
        self.fixture.set_index(INDEX_RECORDS)

        with self.assertRaisesRegex(ValueError, "manifest has drifted"):
            brief.verify_source(self.fixture.registry(manifest_sha256="0" * 64),
                                source_root=self.fixture.checkout)

    def test_style_mapping_and_approval_guards(self):
        self.fixture.set_index([
            {"number": "157", "generation_name": "Different Name", "group": "F Synthetic"},
            {"number": "158", "generation_name": "Synthetic Article Only", "group": "F Synthetic"},
        ])
        with self.assertRaisesRegex(ValueError, "Style index mapping has drifted: synthetic-line"):
            brief.verify_source(self.fixture.registry(), source_root=self.fixture.checkout)
        self.fixture.set_index([
            {"number": "157", "generation_name": "Synthetic Line", "group": "X Personal"},
            {"number": "158", "generation_name": "Synthetic Article Only", "group": "F Synthetic"},
        ])
        with self.assertRaisesRegex(ValueError, "Personal-creator style is not approved"):
            brief.verify_source(self.fixture.registry(), source_root=self.fixture.checkout)

    def test_verify_source_accepts_positional_registry_unchanged(self):
        # Existing callers may pass only the registry; the root keyword is additive.
        with mock.patch.dict(os.environ, {LEGACY_ROOT_ENV: str(self.fixture.checkout)}, clear=True):
            records = brief.verify_source(self.fixture.registry())
        self.assertEqual(sorted(records), ["157", "158"])


class BriefContractTests(BriefCase):
    def test_positive_article_web_social_briefs(self):
        cases = [
            ("article", "slot-1", "editorial-field-guide", "1.0.0"),
            ("web", "web-1", "editorial-field-guide", "1.0.0"),
            ("social-card", "social-1", "reflective-personal-essay", "2.0.0"),
        ]
        for media, target, direction, version in cases:
            with self.subTest(media=media):
                item = make_item(media, direction=direction, version=version)
                before = copy.deepcopy(item)
                result = self.create(
                    item, target=target,
                    metaphor="a synthetic bridge over the invented gap",
                    central_action="crossing the invented gap",
                )
                self.assertEqual(item, before, "content item must not be mutated")
                self.assertEqual(result["schema_version"], "handdraw-style-brief.v1")
                self.assertEqual(result["status"], "candidate-only")
                self.assertEqual(result["content_id"], "content-synthetic-1")
                self.assertEqual(result["target_id"], target)
                self.assertEqual(result["media_adapter"], media)
                self.assertEqual(result["design_direction_id"], direction)
                self.assertEqual(result["style_id"], "synthetic-line")
                self.assertEqual(result["source_ref"], f"handraw-style@{COMMIT}#157")
                self.assertEqual(result["source_index_sha256"], self.fixture.index_sha)
                self.assertEqual(result["source_license_status"], "not-declared")
                self.assertEqual(result["upstream_asset_rights_status"], "unverified")
                self.assertEqual(result["visual_role"], "explanatory-illustration")
                self.assertEqual(result["visual_brief"]["max_labels"], 0)
                self.assertFalse(result["upstream_image_used"])
                self.assertFalse(result["image_generated"])
                self.assertTrue(result["manual_review_required"])
                self.assertIn("Planning brief only", result["boundary"])

    def test_article_slot_status_role_and_route_refusals(self):
        cases = [
            ("selected", {"status": "selected"}, "cannot alter"),
            ("inserted", {"status": "inserted"}, "cannot alter"),
            ("evidence", {"media_role": "evidence"}, "not factual evidence"),
            ("decorative", {"media_role": "decorative"}, "not factual evidence"),
            ("photo-route", {"route": "photo"}, "not an illustration candidate"),
        ]
        for label, overrides, pattern in cases:
            with self.subTest(label=label):
                item = make_item("article", slots=[make_slot(**overrides)])
                with self.assertRaisesRegex(ValueError, pattern):
                    self.create(item)
        ready = make_item("article", slots=[make_slot(status="candidates-ready")])
        self.create(ready)

    def test_target_resolution_errors(self):
        missing = make_item("article", slots=[make_slot("slot-1")])
        with self.assertRaisesRegex(ValueError, "resolve exactly once"):
            self.create(missing, target="slot-missing")
        duplicated = make_item("article", slots=[make_slot("slot-1"), make_slot("slot-1")])
        with self.assertRaisesRegex(ValueError, "resolve exactly once"):
            self.create(duplicated)
        cross_duplicate = make_item(
            "article", slots=[make_slot("slot-1")],
            artifacts=[make_artifact("slot-1", "social-card", "social-card")],
        )
        with self.assertRaisesRegex(ValueError, "resolve exactly once"):
            self.create(cross_duplicate)

    def test_artifact_medium_renderer_and_status_refusals(self):
        cases = [
            ("video", "video", None, "allowed style-brief medium"),
            ("social-renderer", "social-card", "html-playwright", "social-card renderer"),
            ("web-renderer", "web", "social-card", "HTML renderer"),
            ("rendered", "web", "html-playwright", "cannot alter a rendered artifact"),
        ]
        for label, media, renderer, pattern in cases:
            with self.subTest(label=label):
                status = "rendered" if label == "rendered" else "planned"
                artifact = make_artifact("target-1", media, renderer or "social-card", status=status)
                item = make_item(media if media != "video" else "web", artifacts=[artifact])
                with self.assertRaisesRegex(ValueError, pattern):
                    self.create(item, target="target-1")

    def test_design_media_version_route_and_exclusion_refusals(self):
        mismatch = make_item("article")
        mismatch["visual"]["design_system"]["media_adapter"] = "web"
        with self.assertRaisesRegex(ValueError, "does not match target"):
            self.create(mismatch)

        drifted = make_item("article", version="0.0.1")
        with self.assertRaisesRegex(ValueError, "version has drifted"):
            self.create(drifted)

        structure = make_item("article", direction="structure-only")
        with self.assertRaisesRegex(ValueError, "not route-eligible"):
            self.create(structure, style="structure-only-style")

        excluded = make_item("article", visual_mode="editorial-photo-mix")
        with self.assertRaisesRegex(ValueError, "excludes article visual mode"):
            self.create(excluded)

        unregistered = make_item("article", direction="mystery-direction")
        with self.assertRaisesRegex(ValueError, "version has drifted"):
            self.create(unregistered, style="mystery-style")

    def test_blank_metaphor_action_and_budget_limits(self):
        bare = make_item("article", slots=[make_slot(visual_brief={})])
        with self.assertRaisesRegex(ValueError, "Metaphor and central action"):
            self.create(bare)
        with self.assertRaisesRegex(ValueError, "Metaphor and central action"):
            self.create(bare, metaphor="   ", central_action="")
        with self.assertRaisesRegex(ValueError, "budget"):
            self.create(make_item(), metaphor="x" * 161)
        with self.assertRaisesRegex(ValueError, "budget"):
            self.create(make_item(), central_action="x" * 161)
        long_composition = make_item(
            "article",
            slots=[make_slot(visual_brief={
                "metaphor": "m", "central_action": "a", "composition": "y" * 230,
            })],
        )
        with self.assertRaisesRegex(ValueError, "budget"):
            self.create(long_composition)

    def test_selection_policy_version_and_unregistered_style(self):
        registry = self.fixture.registry()
        registry["selection_policy"] = "score-everything"
        with self.assertRaisesRegex(ValueError, "explicit-only"):
            self.create(make_item(), registry=registry)
        with self.assertRaisesRegex(ValueError, "Unregistered style candidate"):
            self.create(make_item(), style="missing-style")
        with self.assertRaisesRegex(ValueError, "not allowed for"):
            self.create(make_item("web"), target="web-1", style="article-only")

        old_schema = make_item()
        old_schema["schema_version"] = "0.1"
        with self.assertRaisesRegex(ValueError, "versioned content object"):
            self.create(old_schema)
        no_content = make_item()
        no_content["content_id"] = ""
        with self.assertRaisesRegex(ValueError, "versioned content object"):
            self.create(no_content)
        no_direction = make_item()
        no_direction["visual"]["design_system"]["design_direction"] = {}
        with self.assertRaisesRegex(ValueError, "design direction"):
            self.create(no_direction)


class BriefCliTests(BriefCase):
    def test_help_succeeds_without_external_dependency(self):
        for argv in (["--help"], ["brief", "--help"], ["list", "--help"]):
            with self.subTest(argv=argv):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    with self.assertRaises(SystemExit) as caught:
                        brief.main(argv)
                self.assertEqual(caught.exception.code, 0)
                self.assertTrue(stdout.getvalue())

    def test_list_accepts_global_and_subcommand_root_flags(self):
        expected = list(STYLE_TARGETS)
        for argv in (
            ["--legacy-root", str(self.fixture.checkout), "list"],
            ["list", "--legacy-root", str(self.fixture.checkout)],
        ):
            with self.subTest(argv=argv):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    status = brief.main(argv)
                self.assertEqual(status, 0)
                payload = json.loads(stdout.getvalue())
                self.assertEqual(payload["status"], "candidate-only")
                self.assertEqual(payload["styles"]["synthetic-line"], expected)

    def test_brief_output_is_exclusive(self):
        item_path = self.base / "item.json"
        _write(item_path, json.dumps(make_item(), ensure_ascii=False))
        output = self.base / "nested" / "brief.json"
        argv = [
            "brief", "--item", str(item_path), "--target-id", "slot-1",
            "--style-id", "synthetic-line", "--legacy-root", str(self.fixture.checkout),
            "--output", str(output),
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(brief.main(argv), 0)
        first = output.read_text(encoding="utf-8")
        payload = json.loads(first)
        self.assertEqual(payload["status"], "candidate-only")
        stderr = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            self.assertEqual(brief.main(argv), 2)
        self.assertIn("already exists", stderr.getvalue())
        self.assertEqual(output.read_text(encoding="utf-8"), first)

    def test_brief_output_race_is_refused_without_overwriting(self):
        item_path = self.base / "race-item.json"
        _write(item_path, json.dumps(make_item(), ensure_ascii=False))
        output = self.base / "race-out" / "brief.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        argv = [
            "brief", "--item", str(item_path), "--target-id", "slot-1",
            "--style-id", "synthetic-line", "--legacy-root", str(self.fixture.checkout),
            "--output", str(output),
        ]
        real_open = Path.open
        state = {"raced": False}

        def fake_open(self, mode="r", *args, **kwargs):
            if self == output and mode == "x" and not state["raced"]:
                state["raced"] = True
                with real_open(self, "w", encoding="utf-8") as handle:
                    handle.write("existing raced bytes")
                return real_open(self, mode, *args, **kwargs)
            return real_open(self, mode, *args, **kwargs)

        stderr = io.StringIO()
        with mock.patch.object(Path, "open", fake_open):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                status = brief.main(argv)
        self.assertEqual(status, 2)
        self.assertIn("already exists", stderr.getvalue())
        self.assertEqual(output.read_text(encoding="utf-8"), "existing raced bytes")

    def test_controlled_errors_return_two_without_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = brief.main(["list"])
        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("not configured", stderr.getvalue())

        stderr = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            status = brief.main(["--legacy-root", str(self.base / "missing"), "list"])
        self.assertEqual(status, 2)
        self.assertIn("missing", stderr.getvalue())

        stderr = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            status = brief.main([
                "brief", "--item", str(self.base / "absent.json"), "--target-id", "slot-1",
                "--style-id", "synthetic-line", "--legacy-root", str(self.fixture.checkout),
            ])
        self.assertEqual(status, 2)
        self.assertIn("ERROR:", stderr.getvalue())


class BriefConsumedBytesTests(BriefCase):
    def test_tampered_index_bytes_are_refused_before_records_are_used(self):
        index_path = (self.fixture.checkout / "styles.json").resolve()
        tampered = json.dumps([
            {"number": "157", "generation_name": "Tampered Name", "group": "F Synthetic"},
            {"number": "158", "generation_name": "Synthetic Article Only", "group": "F Synthetic"},
        ], ensure_ascii=False, indent=2).encode("utf-8")
        patcher, state = _patch_reads(index_path, [tampered])
        with self.assertRaisesRegex(ValueError, "index has drifted"):
            with patcher:
                brief.verify_source(self.fixture.registry(), source_root=self.fixture.checkout)
        self.assertEqual(state["calls"], 1)

    def test_index_swap_is_not_consumed_after_verification(self):
        index_path = (self.fixture.checkout / "styles.json").resolve()
        real = index_path.read_bytes()
        tampered = json.dumps([
            {"number": "157", "generation_name": "Tampered Name", "group": "F Synthetic"},
        ], ensure_ascii=False, indent=2).encode("utf-8")
        patcher, state = _patch_reads(index_path, [real, tampered])
        with patcher:
            records = brief.verify_source(self.fixture.registry(), source_root=self.fixture.checkout)
        self.assertEqual(state["calls"], 1)
        self.assertEqual(records["157"]["generation_name"], "Synthetic Line")

    def test_tampered_manifest_bytes_are_refused_before_decode(self):
        manifest_path = self.fixture.manifest_path.resolve()
        tampered = json.dumps(
            {"commit": "4" * 40, "files": {"styles.json": "0" * 64}}, sort_keys=True,
        ).encode("utf-8")
        patcher, state = _patch_reads(manifest_path, [tampered])
        with self.assertRaisesRegex(ValueError, "manifest has drifted"):
            with patcher:
                brief.verify_source(self.fixture.registry(), source_root=self.fixture.checkout)
        self.assertEqual(state["calls"], 1)

    def test_manifest_swap_is_not_consumed_after_verification(self):
        manifest_path = self.fixture.manifest_path.resolve()
        real = manifest_path.read_bytes()
        tampered = json.dumps(
            {"commit": "4" * 40, "files": {"styles.json": self.fixture.index_sha}},
            sort_keys=True,
        ).encode("utf-8")
        patcher, state = _patch_reads(manifest_path, [real, tampered])
        with patcher:
            records = brief.verify_source(self.fixture.registry(), source_root=self.fixture.checkout)
        self.assertEqual(state["calls"], 1)
        self.assertEqual(records["157"]["generation_name"], "Synthetic Line")


if __name__ == "__main__":
    unittest.main()
