from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import final_cut_compliance_gate as GATE  # noqa: E402
import research_output_adapter as RESEARCH  # noqa: E402


SCRIPT_REVIEW = ROOT / "fixtures/case-video-script-v1/synthetic-case-video-review-receipt.v1.json"


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


class FinalCutComplianceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = ROOT / "tests/.tmp-final-cut-compliance-gate"
        shutil.rmtree(self.temp, ignore_errors=True)
        self.temp.mkdir(parents=True)
        self.video = self.temp / "final.mp4"
        self.subtitles = self.temp / "final.srt"
        self.cover = self.temp / "cover.png"
        self.video.write_bytes(b"synthetic-video")
        self.subtitles.write_text("1\n00:00:00,000 --> 00:00:01,000\n合成字幕\n", encoding="utf-8")
        self.cover.write_bytes(b"synthetic-cover")
        source = json.loads(SCRIPT_REVIEW.read_text(encoding="utf-8"))
        generic_ref = lambda artifact_id: {
            "artifact_id": artifact_id,
            "schema_version": "synthetic-artifact.v1",
            "sha256": hashlib.sha256(artifact_id.encode("utf-8")).hexdigest(),
        }
        self.review = {
            "schema_version": "case-video-final-cut-compliance-review.v1",
            "review_id": "final-cut-review-synthetic-case-001",
            "script_id": source["script_id"],
            "content_id": source["content_id"],
            "synthetic_only": True,
            "stage": "exact-platform-preview-pre-publication",
            "inputs": {
                "script_review": {
                    "artifact_id": source["review_id"],
                    "schema_version": source["schema_version"],
                    "sha256": file_sha(SCRIPT_REVIEW),
                },
                "final_video": {"artifact_id": "synthetic-final-video", "schema_version": "media.v1", "sha256": file_sha(self.video)},
                "subtitles": {"artifact_id": "synthetic-subtitles", "schema_version": "subtitle.v1", "sha256": file_sha(self.subtitles)},
                "cover": {"artifact_id": "synthetic-cover", "schema_version": "image.v1", "sha256": file_sha(self.cover)},
                "customer_final_confirmation": generic_ref("synthetic-customer-confirmation"),
                "institution_content_approval": generic_ref("synthetic-institution-approval"),
                "publishing_account_authorization": generic_ref("synthetic-account-authorization"),
                "rights_manifest": generic_ref("synthetic-rights-manifest"),
                "archive_withdrawal_plan": generic_ref("synthetic-archive-plan"),
            },
            "publication_instance": {
                "platform": "synthetic-platform",
                "account_id_hash": "a" * 64,
                "audience_scope": "synthetic-dry-run",
                "region": "synthetic",
                "planned_at": "2026-08-14T20:00:00+08:00",
                "title": "合成案例成片审核",
                "caption": "不发布。",
                "cta": "",
                "links": [],
                "comment_prompt": "",
                "advertising_label": "not-applicable-documented",
                "ai_generated_label": "required-and-applied",
            },
            "gates": {
                gate_id: {
                    "status": "pass",
                    "reviewed_check_ids": sorted(checks),
                    "reasons": ["合成离线回归已逐项检查，不代表真实发布授权。"],
                    "evidence": ["synthetic fixture"],
                }
                for gate_id, checks in GATE.GATE_CHECKS.items()
            },
            "subject_sha256": "0" * 64,
            "review_mode": "synthetic-fixture-review",
            "reviewer": "synthetic-fixture-reviewer",
            "reviewed_at": "2026-08-14T20:00:00+08:00",
            "decision": "verified_synthetic_dry_run",
            "publication_boundary": "manual-only",
        }
        self._sync_subject()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp, ignore_errors=True)

    def _sync_subject(self) -> None:
        self.review["subject_sha256"] = RESEARCH.sha256_value(GATE.final_cut_subject_payload(self.review))

    def _validate(self, review: dict | None = None) -> dict:
        review_path = write_json(self.temp / "review.json", review or self.review)
        return GATE.validate_final_cut_review(
            review_path=review_path,
            script_review_path=SCRIPT_REVIEW,
            final_video_path=self.video,
            subtitles_path=self.subtitles,
            cover_path=self.cover,
        )

    def test_exact_final_cut_review_passes_dry_run_only(self) -> None:
        result = self._validate()
        self.assertEqual("verified_synthetic_dry_run", result["status"])
        self.assertEqual("manual-only", result["publication_boundary"])

    def test_video_change_invalidates_review(self) -> None:
        self.video.write_bytes(b"changed-after-review")
        with self.assertRaises(GATE.FinalCutGateError) as context:
            self._validate()
        self.assertEqual("final_cut_artifact_hash_drift", context.exception.code)

    def test_publication_text_change_invalidates_subject(self) -> None:
        review = copy.deepcopy(self.review)
        review["publication_instance"]["caption"] = "审核后修改的发布文案"
        with self.assertRaises(GATE.FinalCutGateError) as context:
            self._validate(review)
        self.assertEqual("final_cut_subject_hash_drift", context.exception.code)

    def test_missing_mandatory_check_is_blocked(self) -> None:
        review = copy.deepcopy(self.review)
        review["gates"]["consent_privacy"]["reviewed_check_ids"].pop()
        with self.assertRaises(GATE.FinalCutGateError) as context:
            self._validate(review)
        self.assertEqual("final_cut_review_incomplete", context.exception.code)

    def test_synthetic_review_cannot_target_live_audience(self) -> None:
        review = copy.deepcopy(self.review)
        review["publication_instance"]["audience_scope"] = "public-feed"
        self.review = review
        self._sync_subject()
        with self.assertRaises(GATE.FinalCutGateError) as context:
            self._validate(self.review)
        self.assertEqual("synthetic_publication_blocked", context.exception.code)


if __name__ == "__main__":
    unittest.main()
