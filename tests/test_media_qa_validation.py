#!/usr/bin/env python3
"""Targeted synthetic-only unit test: media_qa_validation.py.

Uses the shipped first-party media-qa-profiles.v1.json and studio_paths. All
artifacts/receipts are new synthetic objects. No rendering, retry, media
detection, network or service.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SOURCE_CONFIG = ROOT / "config" / "media-qa-profiles.v1.json"
PACKAGED_CONFIG = SCRIPTS / "studio_assets" / "config" / "media-qa-profiles.v1.json"
WORKSPACE = Path(os.environ.get("CANDIDATE_TEST_WORKSPACE", str(ROOT.parent / "synthetic")))
sys.path.insert(0, str(SCRIPTS))

import media_qa_validation as qa_validation  # noqa: E402


def synthetic_artifact(**overrides):
    artifact = {
        "media_adapter": "social-card",
        "format": "png",
        "renderer": "social-card",
        "renderer_options": {"operation": "generate"},
    }
    artifact.update(overrides)
    return artifact


def passing_receipt(artifact, module=qa_validation):
    profile_id, required = module.required_hard_checks(artifact)
    return {
        "profile_id": profile_id,
        "hard_checks": [{"name": name, "status": "pass"} for name in sorted(required)],
        "review_checks": [],
        "needs_review_count": 0,
        "result": "pass",
    }


class MediaQaValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        WORKSPACE.mkdir(parents=True, exist_ok=True)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=str(WORKSPACE), prefix="mediaqa-")
        self.dir = Path(self.temp.name)
        self.original_config = qa_validation.CONFIG_PATH
        qa_validation.CONFIG_PATH = SOURCE_CONFIG
        qa_validation.load_media_qa_profiles.cache_clear()
        self.addCleanup(self.restore_config)

    def restore_config(self) -> None:
        qa_validation.CONFIG_PATH = self.original_config
        qa_validation.load_media_qa_profiles.cache_clear()
        self.temp.cleanup()

    def use_config(self, value: dict | str) -> Path:
        path = self.dir / "registry.json"
        if isinstance(value, str):
            path.write_text(value, encoding="utf-8")
        else:
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        qa_validation.CONFIG_PATH = path
        qa_validation.load_media_qa_profiles.cache_clear()
        return path

    def test_shipped_registry_resolves_from_source_and_packaged_layout(self) -> None:
        self.assertTrue(SOURCE_CONFIG.is_file())
        self.assertTrue(PACKAGED_CONFIG.is_file())
        self.assertEqual(SOURCE_CONFIG.read_bytes(), PACKAGED_CONFIG.read_bytes())
        self.assertEqual(qa_validation.CONFIG_PATH, SOURCE_CONFIG.resolve())
        config = qa_validation.load_media_qa_profiles()
        self.assertEqual(config["schema_version"], "media-qa-profiles.v1")
        self.assertIn("social-card-raster.v1", config["profiles"])
        self.assertEqual(config["policy"]["max_needs_review"], 1)

    def test_explicit_env_override_resolves_packaged_config(self) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SCRIPTS) + os.pathsep + env.get("PYTHONPATH", "")
        env["CONTENT_STUDIO_MEDIA_QA_PROFILES"] = str(PACKAGED_CONFIG)
        code = (
            "import media_qa_validation as m, json; "
            "print(json.dumps({'path': str(m.CONFIG_PATH), 'version': m.load_media_qa_profiles()['schema_version']}))"
        )
        proc = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1200:])
        payload = json.loads(proc.stdout.strip())
        self.assertEqual(Path(payload["path"]), PACKAGED_CONFIG.resolve())
        self.assertEqual(payload["version"], "media-qa-profiles.v1")

    def test_missing_registry_fails_closed(self) -> None:
        qa_validation.CONFIG_PATH = self.dir / "absent.json"
        qa_validation.load_media_qa_profiles.cache_clear()
        with self.assertRaises(FileNotFoundError):
            qa_validation.load_media_qa_profiles()
        with self.assertRaises(FileNotFoundError):
            qa_validation.validate_receipt_qa(synthetic_artifact(), {})

    def test_malformed_or_schema_missing_registry_fails_closed(self) -> None:
        self.use_config("{not-json")
        with self.assertRaises(json.JSONDecodeError):
            qa_validation.load_media_qa_profiles()
        self.use_config({"profiles": {}})
        with self.assertRaisesRegex(ValueError, "schema_version"):
            qa_validation.load_media_qa_profiles()
        self.use_config({"schema_version": "media-qa-profiles.v1"})
        with self.assertRaisesRegex(ValueError, "profiles map"):
            qa_validation.load_media_qa_profiles()

    def test_unknown_and_uncovered_profiles_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown media QA profile"):
            qa_validation.resolve_media_qa_profile(synthetic_artifact(qa_profile="does-not-exist"))
        with self.assertRaisesRegex(ValueError, "no media QA profile covers"):
            qa_validation.resolve_media_qa_profile(synthetic_artifact(media_adapter="unknown", format="bin"))
        errors = qa_validation.validate_receipt_qa(synthetic_artifact(qa_profile="does-not-exist"), {})
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0][0], "profile_id")

    def test_ambiguous_profile_is_rejected(self) -> None:
        config = {
            "schema_version": "media-qa-profiles.v1",
            "profiles": {
                "synthetic-a": {"media_adapters": ["social-card"], "formats": ["png"], "required_hard_checks": []},
                "synthetic-b": {"media_adapters": ["social-card"], "formats": ["png"], "required_hard_checks": []},
            },
        }
        self.use_config(config)
        with self.assertRaisesRegex(ValueError, "ambiguous media QA profiles"):
            qa_validation.resolve_media_qa_profile(synthetic_artifact())

    def test_required_hard_checks_layers(self) -> None:
        profile_id, required = qa_validation.required_hard_checks(synthetic_artifact())
        self.assertEqual(profile_id, "social-card-raster.v1")
        for name in ("file-exists", "fact-gate", "pixel-dimensions", "script-free-html", "font-size-gate"):
            self.assertIn(name, required)
        global_artifact = synthetic_artifact(
            media_adapter="article", format="html", renderer="html-playwright",
            renderer_options={"operation": "generate", "global_visual_v1": True},
        )
        _, global_required = qa_validation.required_hard_checks(global_artifact)
        for name in ("global-visual-context", "chinese-typography-rendered", "responsive-viewport"):
            self.assertIn(name, global_required)
        ppt_artifact = synthetic_artifact(
            media_adapter="pptx", format="pptx", renderer="ppt-master",
            renderer_options={"operation": "data-native"},
        )
        _, ppt_required = qa_validation.required_hard_checks(ppt_artifact)
        self.assertIn("data-spec-hash-match", ppt_required)
        self.assertIn("native-drawingml", ppt_required)

    def test_passing_synthetic_receipt_has_no_errors(self) -> None:
        artifact = synthetic_artifact()
        self.assertEqual(qa_validation.validate_receipt_qa(artifact, passing_receipt(artifact)), [])

    def test_receipt_failures_remain_fail_closed(self) -> None:
        artifact = synthetic_artifact()
        good = passing_receipt(artifact)
        cases = []
        drift = dict(good, profile_id="article-html.v1")
        cases.append((drift, "profile_id"))
        duplicate = dict(good, hard_checks=good["hard_checks"] + [dict(good["hard_checks"][0])])
        cases.append((duplicate, "hard_checks"))
        missing = dict(good, hard_checks=good["hard_checks"][1:])
        cases.append((missing, "hard_checks"))
        failed = dict(good, hard_checks=[{**row, "status": "fail"} if row is good["hard_checks"][0] else row
                                         for row in good["hard_checks"]], result="pass")
        cases.append((failed, "result"))
        cases.append((dict(good, needs_review_count=3), "needs_review_count"))
        too_many_reviews = dict(good, review_checks=[{"status": "needs-review"}, {"status": "needs-review"}],
                                needs_review_count=2, result="review-required")
        cases.append((too_many_reviews, "review_checks"))
        cases.append((dict(good, result="review-required"), "result"))
        for receipt, expected_field in cases:
            errors = qa_validation.validate_receipt_qa(artifact, receipt)
            self.assertTrue(any(field == expected_field for field, _ in errors),
                            f"expected {expected_field} error, got {errors}")
        empty_errors = qa_validation.validate_receipt_qa(artifact, {})
        self.assertTrue(any(field == "hard_checks" for field, _ in empty_errors))
        self.assertTrue(any(field == "result" for field, _ in empty_errors))

    def test_result_derivation_with_one_needs_review(self) -> None:
        artifact = synthetic_artifact()
        receipt = passing_receipt(artifact)
        receipt["review_checks"] = [{"status": "needs-review"}]
        receipt["needs_review_count"] = 1
        receipt["result"] = "review-required"
        self.assertEqual(qa_validation.validate_receipt_qa(artifact, receipt), [])

    def test_config_bytes_are_exactly_the_supplied_registry(self) -> None:
        self.assertEqual(
            hashlib.sha256(SOURCE_CONFIG.read_bytes()).hexdigest(),
            "9226ec1e97616bc55db519a01ad89a44572e7b6f79aa86460cc2204dc015f7f6",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
