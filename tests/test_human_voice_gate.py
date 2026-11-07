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

import human_voice_gate as VOICE_GATE  # noqa: E402
import case_video_script_adapter as CASE_ADAPTER  # noqa: E402


FIXTURES = ROOT / "fixtures/case-video-script-v1"
BASE = FIXTURES / "synthetic-case-video-script.pre-voice.json"
INITIAL_REVIEW = FIXTURES / "synthetic-initial-draft-review.v1.json"
REQUEST = FIXTURES / "synthetic-human-voice-rewrite-request.v1.json"
FACT = FIXTURES / "synthetic-fact-card.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


class HumanVoiceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = ROOT / "tests/.tmp-human-voice-gate"
        shutil.rmtree(self.temp, ignore_errors=True)
        self.temp.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp, ignore_errors=True)

    def _apply(self, request: dict | None = None) -> tuple[dict, dict, dict]:
        request_path = REQUEST if request is None else write_json(self.temp / "request.json", request)
        script_path = self.temp / "rewritten.json"
        receipt_path = self.temp / "receipt.json"
        result = VOICE_GATE.apply_human_voice_gate(
            base_script_path=BASE,
            initial_draft_review_path=INITIAL_REVIEW,
            request_path=request_path,
            fact_card_path=FACT,
            output_script_path=script_path,
            output_receipt_path=receipt_path,
        )
        return result, read_json(script_path), read_json(receipt_path)

    def _blocked(self, request: dict, code: str) -> None:
        with self.assertRaises((VOICE_GATE.HumanVoiceGateError, CASE_ADAPTER.CaseScriptError)) as context:
            self._apply(request)
        self.assertEqual(code, context.exception.code)

    def test_actual_rewrite_read_aloud_confirmation_and_hook_chain(self) -> None:
        result, script, receipt = self._apply()
        self.assertEqual("human_voice_gate_passed", result["status"])
        self.assertNotEqual(receipt["input_body_sha256"], receipt["rewritten_body_sha256"])
        self.assertTrue(receipt["diagnostics_before"]["issue_codes"])
        self.assertEqual([], receipt["diagnostics_after"]["issue_codes"])
        self.assertEqual(receipt["rewritten_body_sha256"], receipt["read_aloud"]["body_sha256"])
        self.assertEqual(receipt["rewritten_body_sha256"], receipt["author_confirmation"]["body_sha256"])
        self.assertTrue(receipt["hook_gate"]["previous_hooks_invalidated"])
        self.assertTrue(receipt["hook_gate"]["generated_after_author_confirmation"])
        self.assertEqual(
            [
                "content-fact-card",
                "insurance-content-storycraft",
                "dbs-content",
                "dbs-ai-check",
                "human-voice-editor",
                "read-aloud",
                "author-voice-confirmation",
                "dbs-hook",
            ],
            [row["skill_id"] for row in script["skill_stage_receipts"]],
        )
        self.assertEqual("workspace-draft-uninstalled", receipt["source"]["governance_status"])
        self.assertFalse(receipt["boundaries"]["external_service_called"])
        self.assertFalse(receipt["boundaries"]["would_publish"])

    def test_human_voice_cannot_run_without_approved_initial_draft(self) -> None:
        review = read_json(INITIAL_REVIEW)
        gate = review["gates"]["service_causality"]
        gate["status"] = "needs_revision"
        gate["findings"] = ["讲述者的服务动作没有改变故事进程。"]
        gate["remediation"] = ["补充可核验的具体服务动作后重新审核。"]
        review["decision"] = "return_for_revision"
        review_path = write_json(self.temp / "initial-review.json", review)
        with self.assertRaises(VOICE_GATE.initial_draft_quality_gate.InitialDraftGateError) as context:
            VOICE_GATE.apply_human_voice_gate(
                base_script_path=BASE,
                initial_draft_review_path=review_path,
                request_path=REQUEST,
                fact_card_path=FACT,
                output_script_path=self.temp / "rewritten-blocked.json",
                output_receipt_path=self.temp / "receipt-blocked.json",
            )
        self.assertEqual("initial_draft_review_blocked", context.exception.code)

    def test_repeated_symmetric_slogans_are_blocked(self) -> None:
        request = copy.deepcopy(read_json(REQUEST))
        request["rewrite_operations"][0]["replacement_text"] = "这不是卖产品，而是做服务。这不是讲合同，而是讲责任。"
        self._blocked(request, "human_voice_semantic_gate_blocked")

    def test_uniform_cta_and_summary_are_blocked(self) -> None:
        request = copy.deepcopy(read_json(REQUEST))
        request["rewrite_operations"][0]["replacement_text"] = "事情先讲到这里。如果你也认同，欢迎收藏。"
        request["rewrite_operations"][1]["replacement_text"] = "边界先讲到这里。如果你也认同，欢迎收藏。"
        self._blocked(request, "human_voice_semantic_gate_blocked")

    def test_over_explanation_is_blocked(self) -> None:
        request = copy.deepcopy(read_json(REQUEST))
        request["rewrite_operations"][0]["replacement_text"] = "这说明材料要核对。也就是说，合同也要核对。"
        self._blocked(request, "human_voice_semantic_gate_blocked")

    def test_too_even_rhythm_is_blocked(self) -> None:
        request = copy.deepcopy(read_json(REQUEST))
        even = [
            "今天开始核对材料。明天继续准备材料。",
            "今天开始核对合同。明天继续准备合同。",
            "今天开始说明边界。明天继续说明边界。",
            "今天开始记录问题。明天继续记录问题。",
        ]
        for operation, replacement in zip(request["rewrite_operations"], even, strict=True):
            operation["replacement_text"] = replacement
        self._blocked(request, "human_voice_semantic_gate_blocked")

    def test_translation_register_is_blocked(self) -> None:
        request = copy.deepcopy(read_json(REQUEST))
        request["rewrite_operations"][0]["replacement_text"] = "与此同时，先核对材料。此外，再看合同。"
        self._blocked(request, "human_voice_semantic_gate_blocked")

    def test_abstract_service_language_is_blocked(self) -> None:
        request = copy.deepcopy(read_json(REQUEST))
        request["rewrite_operations"][0]["replacement_text"] = "我们用专业价值形成服务闭环。"
        self._blocked(request, "human_voice_semantic_gate_blocked")

    def test_rewrite_cannot_change_numeric_fact_boundary(self) -> None:
        request = copy.deepcopy(read_json(REQUEST))
        request["rewrite_operations"][0]["replacement_text"] += " 费用是30万元。"
        self._blocked(request, "rewrite_numeric_fact_drift")

    def test_rewrite_cannot_add_medical_or_insurance_guarantee(self) -> None:
        request = copy.deepcopy(read_json(REQUEST))
        request["rewrite_operations"][0]["replacement_text"] += " 这次一定能赔。"
        self._blocked(request, "medical_insurance_claim_blocked")

    def test_read_aloud_author_and_hook_must_bind_rewritten_body(self) -> None:
        for field in ("read_aloud", "author_confirmation"):
            with self.subTest(field=field):
                request = copy.deepcopy(read_json(REQUEST))
                request[field]["body_sha256"] = "0" * 64
                expected = "read_aloud_body_hash_drift" if field == "read_aloud" else "author_confirmation_body_hash_drift"
                self._blocked(request, expected)
        request = copy.deepcopy(read_json(REQUEST))
        request["hook_input_body_sha256"] = "0" * 64
        self._blocked(request, "hook_body_hash_drift")

    def test_rewrite_input_hash_must_match_source_text(self) -> None:
        request = copy.deepcopy(read_json(REQUEST))
        request["rewrite_operations"][0]["before_text_sha256"] = "0" * 64
        self._blocked(request, "rewrite_input_hash_drift")


if __name__ == "__main__":
    unittest.main()
