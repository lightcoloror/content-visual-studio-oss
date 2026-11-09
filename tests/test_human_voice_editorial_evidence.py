"""Synthetic editorial-evidence tests; no author confirmation is collected here."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import human_voice_gate as gate
from temp_workspace import isolated_test_directory

FIX = ROOT / "fixtures/case-video-script-v1"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class EditorialEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.cm = isolated_test_directory("voice-editorial")
        self.root = self.cm.__enter__()
        self.request = load("synthetic-human-voice-rewrite-request.v1.json")
        self.base = load("synthetic-case-video-script.pre-voice.json")
        for row, op in zip(self.base["segments"], self.request["rewrite_operations"]):
            row["spoken_text"] = op["replacement_text"]
        self.clean = copy.deepcopy(self.base)

    def tearDown(self):
        self.cm.__exit__(None, None, None)

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def make_request(self, unchanged=False):
        req = copy.deepcopy(self.request)
        body = lambda s: gate.research_adapter.sha256_value(gate.case_adapter.stable_body_payload(s))
        before = self.base["segments"][0]["spoken_text"]
        after = self.clean["segments"][0]["spoken_text"]
        req["editing_mode"] = "review_without_rewrite" if unchanged else "rewrite"
        req["rewrite_operations"] = [] if unchanged else [{
            "segment_id": "segment-01", "before_text_sha256": gate._text_sha256(before),
            "replacement_text": after, "reason": "移除制作备注，保留原有事实和口播含义。",
        }]
        for key in ("dbs_content_diagnosis", "dbs_ai_check_diagnosis"):
            req[key] = {"status": "reviewed_no_lexical_match", "issue_codes": [],
                        "note": "未命中特定词法规则；不能据此认定无表达问题。"}
        req["semantic_review"] = {
            "input_body_sha256": body(self.base), "output_body_sha256": body(self.clean),
            "reviewer_kind": "synthetic_fixture",
            "voice_basis": {"artifact_id": "synthetic-voice-basis", "schema_version": "voice-profile.v1", "sha256": "1" * 64},
            "checks": [{"check_id": key, "segment_id": "segment-01", "before_span": before,
                        "after_span": after, "status": "clear" if unchanged or key != "production_note_leak" else "resolved",
                        "reason": "合成编辑检查引用对应句段，口播保留场景与实际问题，不增加案例事实。"}
                       for key in sorted(gate.SEMANTIC_CHECKS)],
        }
        review = load("synthetic-initial-draft-review.v1.json")
        review["input_body_sha256"] = body(self.base)
        self.review_path = self.write("initial.json", review)
        req["initial_draft_review_ref"]["sha256"] = gate.research_adapter.sha256_value(review)
        for key in ("read_aloud", "author_confirmation"):
            req[key]["body_sha256"] = body(self.clean)
        req["hook_input_body_sha256"] = body(self.clean)
        return req

    def apply(self, req):
        return gate.apply_human_voice_gate(
            base_script_path=self.write("base.json", self.base), initial_draft_review_path=self.review_path,
            request_path=self.write("request.json", req), fact_card_path=FIX / "synthetic-fact-card.json",
            output_script_path=self.root / "output.json", output_receipt_path=self.root / "receipt.json")

    def test_semantic_repair_with_zero_lexical_hits_and_stable_repeat(self):
        self.base["segments"][0]["spoken_text"] += "录的时候我会用一条测试消息给你看。"
        req = self.make_request()
        self.assertEqual([], gate.diagnose_human_voice(gate._spoken_text(self.base))["issue_codes"])
        self.apply(req)
        first = (self.root / "receipt.json").read_bytes()
        self.apply(req)
        self.assertEqual(first, (self.root / "receipt.json").read_bytes())

    def test_natural_body_can_remain_unchanged(self):
        req = self.make_request(unchanged=True)
        self.apply(req)
        receipt = json.loads((self.root / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual("reviewed_unchanged", receipt["editing_outcome"])
        self.assertEqual(receipt["input_body_sha256"], receipt["rewritten_body_sha256"])

    def test_missing_stale_unbound_blocked_or_duplicate_review_rejected(self):
        mutations = [
            lambda r: r.pop("semantic_review"),
            lambda r: r["semantic_review"].update(input_body_sha256="0" * 64),
            lambda r: r["semantic_review"]["checks"][0].update(before_span="这句话完全不存在。"),
            lambda r: r["semantic_review"]["checks"][0].update(status="blocked"),
            lambda r: r["semantic_review"]["checks"][0].update(check_id=r["semantic_review"]["checks"][1]["check_id"]),
            lambda r: r["read_aloud"].update(body_sha256="0" * 64),
            lambda r: r["author_confirmation"].update(performed_by="author"),
            lambda r: r.update(hook_input_body_sha256="0" * 64),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutations.index(mutate)):
                req = self.make_request(unchanged=True)
                mutate(req)
                with self.assertRaises(gate.HumanVoiceGateError):
                    self.apply(req)

    def test_no_change_does_not_allow_disguised_edit(self):
        req = self.make_request(unchanged=True)
        req["rewrite_operations"] = [{"segment_id": "segment-01", "before_text_sha256": gate._text_sha256(self.base["segments"][0]["spoken_text"]),
                                     "replacement_text": "改变了一句话。", "reason": "不能以无需改写模式隐藏实际修改。"}]
        with self.assertRaises(gate.HumanVoiceGateError):
            self.apply(req)

    def test_semantic_review_cannot_upgrade_numbers_or_guarantees(self):
        for addition, code in (("费用是30万元。", "rewrite_numeric_fact_drift"), ("这次一定能赔。", "medical_insurance_claim_blocked")):
            with self.subTest(addition=addition):
                self.base = copy.deepcopy(self.clean)
                self.base["segments"][0]["spoken_text"] += "这是录制时的备注。"
                req = self.make_request()
                req["rewrite_operations"][0]["replacement_text"] += addition
                altered = copy.deepcopy(self.clean)
                altered["segments"][0]["spoken_text"] += addition
                req["semantic_review"]["output_body_sha256"] = gate.research_adapter.sha256_value(gate.case_adapter.stable_body_payload(altered))
                with self.assertRaises((gate.HumanVoiceGateError, gate.case_adapter.CaseScriptError)) as caught:
                    self.apply(req)
                self.assertEqual(code, caught.exception.code)


if __name__ == "__main__":
    unittest.main()
