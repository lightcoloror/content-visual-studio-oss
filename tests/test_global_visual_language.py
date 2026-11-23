import copy
import hashlib
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(WORKSPACE / "scripts"))

from global_visual_validation import (  # noqa: E402
    build_conformance_receipt,
    build_runtime_context,
    validate_runtime_context,
)
from render_artifact_validation import validate_render_artifacts  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GlobalVisualLanguageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = ROOT / "outputs" / ".test-runtime" / self._testMethodName
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.output = self.runtime / "output.html"
        self.output.write_text("<!doctype html><html lang='zh-Hans'><body><p>结构化测试输出。</p></body></html>", encoding="utf-8")
        self.item_path = self.runtime / "item.json"
        self.artifact = {
            "artifact_id": "global-visual-article",
            "output_family": "article",
            "media_adapter": "article",
            "layout_intent": "list",
            "renderer": "html-playwright",
            "format": "html",
            "status": "planned",
            "renderer_options": {"global_visual_v1": True},
        }
        self.item = {
            "content_id": "global-visual-test-item",
            "visual": {
                "visual_profile": "visual/source-preserved",
                "assets": [],
                "semantic_visual_map": [],
            },
        }

    def tearDown(self) -> None:
        for child in self.runtime.iterdir():
            if child.is_file():
                child.unlink()
        self.runtime.rmdir()

    def context(self) -> dict:
        return build_runtime_context(self.item, self.artifact)

    def media_qa(self) -> dict:
        return {
            "profile_id": "article-html.v1",
            "hard_checks": [{"name": "file-exists", "status": "pass"}],
            "result": "pass",
        }

    def test_runtime_context_is_locked_and_matches_medium(self) -> None:
        context = self.context()
        self.assertEqual(context["authority_scope"], "global-only")
        self.assertEqual(context["conformance_profile"], "article.v1")
        self.assertEqual(validate_runtime_context(context, self.artifact), [])

    def test_wrong_medium_unknown_rule_and_expired_exception_are_rejected(self) -> None:
        context = self.context()
        context["conformance_profile"] = "pptx.v1"
        context["exceptions"] = [{
            "rule_id": "not-a-rule",
            "reason": "用于无效例外负例测试。",
            "reviewer": "tester",
            "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        }]
        errors = validate_runtime_context(context, self.artifact)
        self.assertTrue(any("does not match media adapter" in error for error in errors))
        self.assertTrue(any("unknown rule" in error for error in errors))
        self.assertTrue(any("expired" in error for error in errors))

    def test_ruleset_hash_drift_is_rejected(self) -> None:
        context = self.context()
        context["ruleset"]["sha256"] = "0" * 64
        self.assertTrue(any("hash mismatch" in error for error in validate_runtime_context(context, self.artifact)))

    def test_active_p0_failure_blocks_approval(self) -> None:
        receipt = build_conformance_receipt(
            self.item,
            self.artifact,
            self.output,
            {"status": "fail", "message": "rendered line-box test failed"},
            {"normalized_spec_valid": True, "message": "not a data visual"},
            self.media_qa(),
        )
        typography = next(finding for finding in receipt["findings"] if finding["rule_id"] == "chinese-typography")
        self.assertEqual(typography["status"], "fail")
        self.assertEqual(typography["enforcement"], "blocking")
        self.assertEqual(receipt["result"], "fail")
        self.assertTrue(receipt["policy"]["manual_only"])
        self.assertFalse(receipt["policy"]["candidate_only"])

    def test_p1_icon_imagery_and_ai_failures_are_reported(self) -> None:
        item = copy.deepcopy(self.item)
        item["visual"]["semantic_visual_map"] = [{
            "variant_id": "bad-icons",
            "output_ref": str(self.output),
            "bindings": [{"semantic_id": "generic-risk-shield", "copy_anchor": "保障", "meaning": "保证安全"}],
        }]
        item["visual"]["assets"] = [{
            "asset_id": "generated-without-opt-in",
            "ref": str(self.output),
            "asset_type": "generated-image",
            "rights_status": "verified",
            "privacy_status": "not-applicable",
            "visual_role": "explanatory-illustration",
            "evidence_status": "illustrative-only",
            "treatment": "annotated",
            "text_overlay_policy": "none",
        }]
        receipt = build_conformance_receipt(
            item,
            self.artifact,
            self.output,
            {"status": "pass", "message": "ok"},
            {"normalized_spec_valid": True, "message": "not a data visual"},
            self.media_qa(),
        )
        failures = {finding["diagnostic_id"] for finding in receipt["findings"] if finding["status"] == "fail"}
        self.assertIn("GVL-ICON-002", failures)
        self.assertIn("GVL-IMAGE-005", failures)
        self.assertEqual(receipt["result"], "pass", "P1 remains report-only before calibration promotion")

    def test_sveltia_exposes_new_fields_and_keeps_authority_read_only(self) -> None:
        config = yaml.safe_load((ROOT / "admin" / "config.yml").read_text(encoding="utf-8"))
        fields = config["collections"][0]["fields"]
        visual = next(field for field in fields if field.get("name") == "visual")
        visual_fields = visual["fields"]
        design_system = next(field for field in visual_fields if field.get("name") == "design_system")
        global_visual = next(field for field in design_system["fields"] if field.get("name") == "global_visual")
        global_fields = {field["name"]: field for field in global_visual["fields"]}
        self.assertIn("locale", global_fields)
        authority = global_fields["brand_authority"]
        self.assertTrue(all(field.get("readonly") is True for field in authority["fields"]))
        assets = next(field for field in visual_fields if field.get("name") == "assets")
        asset_names = {field["name"] for field in assets["fields"]}
        self.assertTrue({"visual_role", "evidence_status", "treatment", "text_overlay_policy"} <= asset_names)
        artifacts = next(field for field in visual_fields if field.get("name") == "render_artifacts")
        conformance = next(field for field in artifacts["fields"] if field.get("name") == "conformance_receipt_ref")
        self.assertTrue(conformance.get("readonly"))

    def test_conformance_link_hash_and_media_qa_bridge_are_enforced(self) -> None:
        context = self.context()
        self.item["visual"]["design_system"] = {"global_visual": context}
        self.artifact.update({
            "status": "rendered",
            "ref": str(self.output),
            "receipt_ref": str(self.runtime / "render.receipt.json"),
        })
        self.item["visual"]["render_artifacts"] = [self.artifact]
        conformance = build_conformance_receipt(
            self.item,
            self.artifact,
            self.output,
            {"status": "pass", "message": "ok"},
            {"normalized_spec_valid": True, "message": "not a data visual"},
            {
                "profile_id": "article-html.v1",
                "hard_checks": [
                    {"name": name, "status": "pass"}
                    for name in (
                        "file-exists", "non-empty-output", "input-files-exist", "fact-gate",
                        "rights-gate", "privacy-gate", "utf8-readable", "html-document",
                        "responsive-viewport", "alt-text-complete", "global-visual-context",
                        "chinese-typography-rendered", "font-size-gate",
                    )
                ],
                "result": "pass",
            },
        )
        conformance_path = self.runtime / "visual-conformance.json"
        conformance_path.write_text(json.dumps(conformance), encoding="utf-8")
        receipt = {
            "schema_version": "render-receipt.v1",
            "receipt_id": "global-visual-test-item.global-visual-article.0123456789ab",
            "artifact_id": self.artifact["artifact_id"],
            "content_id": self.item["content_id"],
            "renderer": "html-playwright",
            "renderer_version": "test",
            "created_at": "2026-08-24T00:00:00Z",
            "inputs": [],
            "output": {"ref": str(self.output), "format": "html", "sha256": sha256(self.output), "bytes": self.output.stat().st_size},
            "qa": {
                "profile_id": "article-html.v1",
                "hard_checks": conformance["media_qa"]["hard_checks"] + [{"name": "visual-conformance-receipt", "status": "pass"}],
                "review_checks": [{"name": "human-final-review", "status": "needs-review"}],
                "needs_review_count": 1,
                "result": "review-required",
                "retry_count": 0,
            },
            "policy": {"rights_verified": True, "privacy_verified": True, "ai_generation_authorized": False, "remote_downloads_enabled": False},
            "visual_conformance": {"ref": str(conformance_path), "schema_version": "visual-conformance-receipt.v1", "sha256": sha256(conformance_path), "result": conformance["result"]},
        }
        Path(self.artifact["receipt_ref"]).write_text(json.dumps(receipt), encoding="utf-8")
        self.assertEqual(validate_render_artifacts(self.item, self.item_path), [])
        receipt["visual_conformance"]["sha256"] = "0" * 64
        Path(self.artifact["receipt_ref"]).write_text(json.dumps(receipt), encoding="utf-8")
        messages = [message for _, message in validate_render_artifacts(self.item, self.item_path)]
        self.assertTrue(any("does not match visual conformance receipt" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
