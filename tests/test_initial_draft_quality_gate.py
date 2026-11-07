from __future__ import annotations

import copy
import json
import shutil
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import initial_draft_quality_gate as GATE  # noqa: E402


FIXTURES = ROOT / "fixtures/case-video-script-v1"
SCRIPT = FIXTURES / "synthetic-case-video-script.pre-voice.json"
REVIEW = FIXTURES / "synthetic-initial-draft-review.v1.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


class InitialDraftQualityGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = ROOT / "tests/.tmp-initial-draft-quality-gate"
        shutil.rmtree(self.temp, ignore_errors=True)
        self.temp.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp, ignore_errors=True)

    def _validate(self, *, script: dict | None = None, review: dict | None = None, require_approved: bool = True) -> dict:
        script_path = SCRIPT if script is None else write_json(self.temp / "script.json", script)
        review_path = REVIEW if review is None else write_json(self.temp / "review.json", review)
        return GATE.validate_initial_draft_review(
            script_path=script_path,
            review_path=review_path,
            require_approved=require_approved,
        )

    def _blocked(self, review: dict, code: str, *, script: dict | None = None) -> None:
        with self.assertRaises(GATE.InitialDraftGateError) as context:
            self._validate(script=script, review=review)
        self.assertEqual(code, context.exception.code)

    def test_complete_review_allows_voice_pipeline(self) -> None:
        result = self._validate()
        self.assertEqual("initial_draft_review_passed", result["status"])
        self.assertEqual("approved_for_voice_pipeline", result["decision"])
        self.assertEqual("manual-only", result["publication_boundary"])

    def test_template_is_fail_closed_until_reviewed(self) -> None:
        output = self.temp / "template.json"
        template = GATE.build_review_template(
            script_path=SCRIPT,
            output_path=output,
            content_goal="education",
            reviewer="local-editor-author",
            reviewed_at="2026-08-14T19:10:00+08:00",
        )
        self.assertEqual("return_for_revision", template["decision"])
        with self.assertRaises(GATE.InitialDraftGateError) as context:
            self._validate(review=template)
        self.assertEqual("initial_draft_review_blocked", context.exception.code)

    def test_missing_check_is_blocked(self) -> None:
        review = copy.deepcopy(read_json(REVIEW))
        review["gates"]["service_causality"]["reviewed_check_ids"].pop()
        self._blocked(review, "initial_draft_review_incomplete")

    def test_distribution_compliance_cannot_be_skipped(self) -> None:
        review = copy.deepcopy(read_json(REVIEW))
        gate = review["gates"]["distribution_compliance"]
        gate["status"] = "not_applicable"
        gate["findings"] = ["错误地把教育内容当成发布豁免。"]
        self._blocked(review, "initial_draft_review_invalid_na")

    def test_draft_change_invalidates_review(self) -> None:
        script = copy.deepcopy(read_json(SCRIPT))
        script["segments"][0]["spoken_text"] += "已修改。"
        self._blocked(read_json(REVIEW), "initial_draft_review_body_hash_drift", script=script)

    def test_fact_revision_change_invalidates_review(self) -> None:
        script = copy.deepcopy(read_json(SCRIPT))
        script["inputs"]["fact_card_ref"]["sha256"] = "a" * 64
        self._blocked(read_json(REVIEW), "initial_draft_review_fact_revision_drift", script=script)

    def test_needs_revision_cannot_enter_voice_pipeline(self) -> None:
        review = copy.deepcopy(read_json(REVIEW))
        gate = review["gates"]["service_causality"]
        gate["status"] = "needs_revision"
        gate["findings"] = ["删掉讲述者后，客户故事仍然完整。"]
        gate["remediation"] = ["补回讲述者实际完成的服务动作及其作用。"]
        review["decision"] = "return_for_revision"
        self._blocked(review, "initial_draft_review_blocked")

    def test_decision_must_match_gate_statuses(self) -> None:
        review = copy.deepcopy(read_json(REVIEW))
        review["decision"] = "return_for_revision"
        self._blocked(review, "initial_draft_review_decision_drift")

    def test_interview_gate_cannot_be_skipped_when_slot_exists(self) -> None:
        review = copy.deepcopy(read_json(REVIEW))
        gate = review["gates"]["interview_integrity"]
        gate["status"] = "not_applicable"
        gate["findings"] = ["错误地跳过。"]
        self._blocked(review, "initial_draft_review_invalid_na")

    def test_acquisition_goal_requires_cta_segment(self) -> None:
        review = copy.deepcopy(read_json(REVIEW))
        review["content_goal"] = "acquisition"
        review["gates"]["cta_product"]["status"] = "pass"
        review["gates"]["cta_product"]["findings"] = []
        self._blocked(review, "cta_missing_for_goal")


if __name__ == "__main__":
    unittest.main()
