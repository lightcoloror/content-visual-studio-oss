from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import case_video_script_adapter as CASE_ADAPTER  # noqa: E402
import research_output_adapter as RESEARCH_ADAPTER  # noqa: E402
import run_case_video_script_e2e as E2E_RUNNER  # noqa: E402


FIXTURE_ROOT = ROOT / "fixtures/case-video-script-v1"
CASE_SCRIPT = FIXTURE_ROOT / "synthetic-case-video-script.v1.json"
RESEARCH = FIXTURE_ROOT / "synthetic-research-output.v1.json"
FACT_CARD = FIXTURE_ROOT / "synthetic-fact-card.json"
ROUTE_CARD = FIXTURE_ROOT / "synthetic-route-card.json"
REVIEW_RECEIPT = FIXTURE_ROOT / "synthetic-case-video-review-receipt.v1.json"
VOICE_RECEIPT = FIXTURE_ROOT / "synthetic-human-voice-receipt.v1.json"
INTERVIEW_RECEIPT = FIXTURE_ROOT / "synthetic-deidentified-interview-receipt.v1.json"
NEGATIVE_CASES = FIXTURE_ROOT / "negative-cases.json"
CASE_SCHEMA = ROOT / "schemas/case-video-script.v1.schema.json"
REVIEW_SCHEMA = ROOT / "schemas/case-video-review-receipt.v1.schema.json"
VOICE_SCHEMA = ROOT / "schemas/case-video-human-voice-receipt.v1.schema.json"
INTERVIEW_SCHEMA = ROOT / "schemas/case-video-deidentified-interview-receipt.v1.schema.json"
FACT_SCHEMA = ROOT / "schemas/content-fact-card.v0.schema.json"
ROUTE_SCHEMA = ROOT / "schemas/content-route-card.v0.schema.json"
HANDOFF_SCHEMA = ROOT / "schemas/case-video-script-handoff.v1.schema.json"
RESEARCH_SCHEMA = ROOT / "schemas/research-output.v1.schema.json"
CONTENT_SCHEMA = ROOT / "schemas/content-item.schema.json"
VIDEO_SCHEMA = ROOT / "schemas/content-video-brief.v1.schema.json"
MVP_ROOT = WORKSPACE / "mvp-video-pipeline"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


class CaseVideoScriptAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        for path in (
            CASE_SCRIPT,
            RESEARCH,
            FACT_CARD,
            ROUTE_CARD,
            REVIEW_RECEIPT,
            VOICE_RECEIPT,
            INTERVIEW_RECEIPT,
            NEGATIVE_CASES,
            CASE_SCHEMA,
            REVIEW_SCHEMA,
            VOICE_SCHEMA,
            INTERVIEW_SCHEMA,
            FACT_SCHEMA,
            ROUTE_SCHEMA,
            HANDOFF_SCHEMA,
            RESEARCH_SCHEMA,
            CONTENT_SCHEMA,
            VIDEO_SCHEMA,
        ):
            if not path.is_file():
                raise AssertionError(f"required fixture or contract is missing: {path}")

    def setUp(self) -> None:
        self.temp_root = ROOT / "tests/.tmp-case-video-script-adapter"
        shutil.rmtree(self.temp_root, ignore_errors=True)
        self.temp_root.mkdir(parents=True)
        base_output = self.temp_root / "research-adapter"
        RESEARCH_ADAPTER.adapt_research_output(
            RESEARCH,
            base_output,
            RESEARCH_SCHEMA,
            CONTENT_SCHEMA,
            VIDEO_SCHEMA,
        )
        self.content_item = next(base_output.glob("*.content-item.json"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_real_fact_card_requires_canonical_revision(self) -> None:
        fact_card = copy.deepcopy(read_json(FACT_CARD))
        fact_card["synthetic_only"] = False
        with self.assertRaises(CASE_ADAPTER.CaseScriptError) as context:
            CASE_ADAPTER._validate_canonical_fact_card(fact_card)
        self.assertEqual("canonical_fact_card_incomplete", context.exception.code)

    def test_locked_real_fact_card_passes_canonical_revision_gate(self) -> None:
        fact_card = copy.deepcopy(read_json(FACT_CARD))
        fact_card.update(
            {
                "synthetic_only": False,
                "revision_id": "fact-rev-example-001",
                "canonical_status": "locked_for_draft",
                "source_precedence": ["primary-record", "latest-direct-confirmation", "reviewed-transcript"],
                "correction_log": [],
            }
        )
        for sequence, fact in enumerate(fact_card["facts"], start=1):
            fact.update(
                {
                    "fact_type": "objective-event",
                    "sequence": sequence,
                    "actor": "当事人",
                    "action": "完成已核实动作",
                    "status": "confirmed",
                    "allowed_wording": [fact["text"]],
                    "forbidden_paraphrases": [],
                    "last_confirmed_at": "2026-08-15T17:53:49+08:00",
                    "privacy_class": "deidentified",
                }
            )
        CASE_ADAPTER._validate_canonical_fact_card(fact_card)

    def test_real_case_requires_paragraph_level_fact_refs(self) -> None:
        script = copy.deepcopy(read_json(CASE_SCRIPT))
        fact = copy.deepcopy(read_json(FACT_CARD))
        route = copy.deepcopy(read_json(ROUTE_CARD))
        script["synthetic_only"] = False
        fact["synthetic_only"] = False
        route.update({"synthetic_only": False, "narrative_order": "chronological"})
        for sequence, row in enumerate(fact["facts"], start=1):
            row["sequence"] = sequence
        with self.assertRaises(CASE_ADAPTER.CaseScriptError) as context:
            CASE_ADAPTER._validate_segment_fact_routing(script, fact, route)
        self.assertEqual("segment_fact_refs_missing", context.exception.code)

    def test_chronological_paragraph_fact_regression_fails_closed(self) -> None:
        script = copy.deepcopy(read_json(CASE_SCRIPT))
        fact = copy.deepcopy(read_json(FACT_CARD))
        route = copy.deepcopy(read_json(ROUTE_CARD))
        script["synthetic_only"] = False
        fact["synthetic_only"] = False
        route.update({"synthetic_only": False, "narrative_order": "chronological"})
        for sequence, row in enumerate(fact["facts"], start=1):
            row["sequence"] = sequence
        script["segments"][0]["fact_refs"] = ["fact-02"]
        script["segments"][1]["fact_refs"] = ["fact-01"]
        script["segments"][2]["fact_refs"] = ["fact-02"]
        script["segments"][3]["fact_refs"] = ["fact-02"]
        with self.assertRaises(CASE_ADAPTER.CaseScriptError) as context:
            CASE_ADAPTER._validate_segment_fact_routing(script, fact, route)
        self.assertEqual("segment_fact_sequence_regression", context.exception.code)

    def test_nonchronological_paragraph_order_requires_reason(self) -> None:
        script = copy.deepcopy(read_json(CASE_SCRIPT))
        fact = copy.deepcopy(read_json(FACT_CARD))
        route = copy.deepcopy(read_json(ROUTE_CARD))
        script["synthetic_only"] = False
        fact["synthetic_only"] = False
        route.update({"synthetic_only": False, "narrative_order": "editorial_nonchronological"})
        for segment in script["segments"]:
            segment["fact_refs"] = ["fact-01"]
        with self.assertRaises(CASE_ADAPTER.CaseScriptError) as context:
            CASE_ADAPTER._validate_segment_fact_routing(script, fact, route)
        self.assertEqual("nonchronological_reason_missing", context.exception.code)

    def test_quantitative_scope_and_evidence_lifecycle_are_schema_valid(self) -> None:
        fact_card = copy.deepcopy(read_json(FACT_CARD))
        fact_card["facts"][0]["quantitative_scope"] = {
            "region": "虚构地区",
            "period": "2025",
            "population": "虚构样本",
            "event_or_condition": "虚构住院事件",
            "measurement_window": "单次住院",
            "metric_type": "median",
            "denominator": "虚构住院人次",
            "value_nature": "observed-statistic",
            "supports": ["说明虚构样本的中间费用量级"],
            "does_not_support": ["不能代表全国，也不能预测个体费用"],
        }
        fact_card["facts"][0]["evidence_refs"][0].update(
            {
                "usage_status": "active",
                "used_in_versions": ["draft-v2"],
                "rights": {
                    "reuse_mode": "redraw",
                    "license_status": "restricted",
                    "attribution": "按虚构来源数据重绘",
                    "commercial_use_boundary": "不直接裁切原表",
                },
            }
        )
        errors = list(Draft202012Validator(read_json(FACT_SCHEMA)).iter_errors(fact_card))
        self.assertEqual([], errors)

    def test_retired_evidence_requires_retirement_reason(self) -> None:
        fact_card = copy.deepcopy(read_json(FACT_CARD))
        fact_card["facts"][0]["evidence_refs"][0]["usage_status"] = "retired"
        errors = list(Draft202012Validator(read_json(FACT_SCHEMA)).iter_errors(fact_card))
        self.assertTrue(any("retirement_reason" in error.message for error in errors))

    def test_derived_quantitative_scope_requires_derivation_and_assumptions(self) -> None:
        fact_card = copy.deepcopy(read_json(FACT_CARD))
        fact_card["facts"][0]["quantitative_scope"] = {
            "region": "虚构地区",
            "period": "2025",
            "population": "虚构样本",
            "event_or_condition": "虚构住院事件",
            "measurement_window": "一年",
            "metric_type": "ratio",
            "denominator": "虚构获赔人群",
            "value_nature": "derived-estimate",
            "supports": ["仅说明假设成立时的量级"],
            "does_not_support": ["不能写成官方直接公布的平均账单"],
        }
        errors = list(Draft202012Validator(read_json(FACT_SCHEMA)).iter_errors(fact_card))
        messages = [error.message for error in errors]
        self.assertTrue(any("derivation" in message for message in messages))
        self.assertTrue(any("assumptions" in message for message in messages))

    def _adapt(
        self,
        *,
        script: dict | None = None,
        research: dict | None = None,
        content: dict | None = None,
        fact_card: dict | None = None,
        route_card: dict | None = None,
        voice_receipt: dict | None = None,
        interview_receipts: list[dict] | None = None,
        review_receipt: dict | None = None,
        output_name: str = "case-output",
    ) -> tuple[dict, Path]:
        script_path = CASE_SCRIPT if script is None else write_json(self.temp_root / "case-script.json", script)
        research_path = RESEARCH if research is None else write_json(self.temp_root / "research.json", research)
        content_path = self.content_item if content is None else write_json(self.temp_root / "content-item.json", content)
        fact_path = FACT_CARD if fact_card is None else write_json(self.temp_root / "fact-card.json", fact_card)
        route_path = ROUTE_CARD if route_card is None else write_json(self.temp_root / "route-card.json", route_card)
        voice_path = VOICE_RECEIPT if voice_receipt is None else write_json(
            self.temp_root / "voice-receipt.json", voice_receipt
        )
        interview_paths = [
            write_json(self.temp_root / f"interview-receipt-{index}.json", receipt)
            for index, receipt in enumerate(interview_receipts or [], start=1)
        ]
        review_path = REVIEW_RECEIPT if review_receipt is None else write_json(
            self.temp_root / "review-receipt.json", review_receipt
        )
        output_dir = self.temp_root / output_name
        result = CASE_ADAPTER.adapt_case_video_script(
            script_path=script_path,
            research_path=research_path,
            content_item_path=content_path,
            fact_card_path=fact_path,
            route_card_path=route_path,
            voice_receipt_path=voice_path,
            interview_receipt_paths=interview_paths,
            review_receipt_path=review_path,
            output_dir=output_dir,
            script_schema_path=CASE_SCHEMA,
            voice_schema_path=VOICE_SCHEMA,
            review_schema_path=REVIEW_SCHEMA,
            fact_schema_path=FACT_SCHEMA,
            route_schema_path=ROUTE_SCHEMA,
            handoff_schema_path=HANDOFF_SCHEMA,
            research_schema_path=RESEARCH_SCHEMA,
            content_schema_path=CONTENT_SCHEMA,
            video_schema_path=VIDEO_SCHEMA,
        )
        return result, output_dir

    @staticmethod
    def _artifact_ref(artifact: dict, identity_key: str) -> dict:
        return {
            "artifact_id": artifact[identity_key],
            "schema_version": artifact["schema_version"],
            "sha256": RESEARCH_ADAPTER.sha256_value(artifact),
        }

    @staticmethod
    def _sync_stage_hashes(script: dict, voice: dict) -> None:
        body_hash = RESEARCH_ADAPTER.sha256_value(CASE_ADAPTER.stable_body_payload(script))
        hook_hash = RESEARCH_ADAPTER.sha256_value(
            CASE_ADAPTER.hook_bundle_payload(script, body_hash)
        )
        voice["rewritten_body_sha256"] = body_hash
        voice["read_aloud"]["body_sha256"] = body_hash
        read_payload = {
            "scope_version": "case-video-read-aloud.v1",
            "status": voice["read_aloud"]["status"],
            "performed_by": voice["read_aloud"]["performed_by"],
            "body_sha256": body_hash,
            "completed_at": voice["read_aloud"]["completed_at"],
            "notes": voice["read_aloud"]["notes"],
        }
        read_hash = RESEARCH_ADAPTER.sha256_value(read_payload)
        voice["read_aloud"]["receipt_sha256"] = read_hash
        voice["author_confirmation"]["body_sha256"] = body_hash
        voice["author_confirmation"]["read_aloud_receipt_sha256"] = read_hash
        author_payload = {
            "scope_version": "case-video-author-voice-confirmation.v1",
            "status": voice["author_confirmation"]["status"],
            "performed_by": voice["author_confirmation"]["performed_by"],
            "body_sha256": body_hash,
            "read_aloud_receipt_sha256": read_hash,
            "confirmed_at": voice["author_confirmation"]["confirmed_at"],
            "voice_match": voice["author_confirmation"]["voice_match"],
            "facts_preserved": voice["author_confirmation"]["facts_preserved"],
        }
        author_hash = RESEARCH_ADAPTER.sha256_value(author_payload)
        voice["author_confirmation"]["receipt_sha256"] = author_hash
        voice["hook_gate"]["input_body_sha256"] = body_hash
        voice["hook_gate"]["bundle_sha256"] = hook_hash
        script["inputs"]["human_voice_receipt_ref"] = {
            "artifact_id": voice["receipt_id"],
            "schema_version": voice["schema_version"],
            "sha256": RESEARCH_ADAPTER.sha256_value(voice),
        }
        pairs = [
            (script["inputs"]["research_output_ref"]["sha256"], script["inputs"]["fact_card_ref"]["sha256"]),
            (script["inputs"]["fact_card_ref"]["sha256"], voice["input_body_sha256"]),
            (voice["input_body_sha256"], voice["dbs_content_diagnosis_sha256"]),
            (voice["dbs_content_diagnosis_sha256"], voice["dbs_ai_check_diagnosis_sha256"]),
            (voice["dbs_ai_check_diagnosis_sha256"], body_hash),
            (body_hash, read_hash),
            (read_hash, author_hash),
            (author_hash, hook_hash),
        ]
        for receipt, (input_hash, output_hash) in zip(
            sorted(script["skill_stage_receipts"], key=lambda row: row["sequence"]),
            pairs,
            strict=True,
        ):
            receipt["input_sha256"] = input_hash
            receipt["output_sha256"] = output_hash

    def _sync_review_inputs(
        self,
        review: dict,
        script: dict,
        research: dict,
        content: dict,
        fact: dict,
        route: dict,
        voice: dict,
        interviews: list[dict] | None = None,
        *,
        sync_subject: bool = True,
    ) -> None:
        review["script_id"] = script["script_id"]
        review["content_id"] = script["content_id"]
        review["synthetic_only"] = script["synthetic_only"]
        review["inputs"] = {
            "case_video_script": self._artifact_ref(script, "script_id"),
            "research_output": self._artifact_ref(research, "research_id"),
            "content_item": self._artifact_ref(content, "content_id"),
            "fact_card": self._artifact_ref(fact, "fact_card_id"),
            "route_card": self._artifact_ref(route, "route_card_id"),
            "human_voice_receipt": self._artifact_ref(voice, "receipt_id"),
            "interview_receipts": [
                self._artifact_ref(row, "receipt_id")
                for row in sorted(interviews or [], key=lambda item: item["slot_id"])
            ],
        }
        if sync_subject:
            review["subject_sha256"] = RESEARCH_ADAPTER.sha256_value(
                CASE_ADAPTER.review_subject_payload(script)
            )

    def test_contract_preflight_preserves_existing_owners(self) -> None:
        receipt = CASE_ADAPTER.contract_preflight(
            script_schema_path=CASE_SCHEMA,
            voice_schema_path=VOICE_SCHEMA,
            review_schema_path=REVIEW_SCHEMA,
            fact_schema_path=FACT_SCHEMA,
            route_schema_path=ROUTE_SCHEMA,
            handoff_schema_path=HANDOFF_SCHEMA,
            research_schema_path=RESEARCH_SCHEMA,
            content_schema_path=CONTENT_SCHEMA,
            video_schema_path=VIDEO_SCHEMA,
        )
        self.assertEqual("contract_ready", receipt["status"])
        self.assertFalse(receipt["boundaries"]["owns_publication_state"])
        self.assertFalse(receipt["boundaries"]["owns_video_state"])
        self.assertTrue(receipt["boundaries"]["draft_only"])

    def test_positive_fixture_projects_to_existing_video_brief(self) -> None:
        result, output_dir = self._adapt()
        brief = read_json(Path(result["brief"]))
        manifest = read_json(Path(result["manifest"]))
        Draft202012Validator(read_json(VIDEO_SCHEMA)).validate(brief)

        self.assertEqual("generated_draft_only", result["status"])
        self.assertEqual("draft_only", brief["mode"])
        self.assertEqual("manual-only", brief["review_gate"]["publication_boundary"])
        self.assertEqual(read_json(CASE_SCRIPT)["content_id"], brief["content_id"])
        self.assertEqual(read_json(RESEARCH)["research_id"], brief["provenance"]["research_id"])
        self.assertEqual(
            RESEARCH_ADAPTER.sha256_value(read_json(RESEARCH)),
            brief["provenance"]["input_sha256"],
        )
        self.assertTrue(
            all(
                lead["status"] == "candidate"
                for scene in brief["scenes"]
                for lead in scene["visual_leads"]
            )
        )
        narration = "\n".join(scene["narration_draft"] for scene in brief["scenes"])
        self.assertNotIn("客户亲口", narration)
        self.assertIn("unknown-interview-not-recorded", {row["unknown_id"] for row in brief["unknowns"]})
        self.assertTrue(manifest["boundaries"]["manual_only"])
        self.assertFalse(manifest["boundaries"]["would_publish"])
        self.assertEqual("hook-01", manifest["selected_hook_id"])
        self.assertEqual("hook-01", manifest["selected_hook_binding"]["hook_id"])
        self.assertEqual("hook", brief["chapters"][0]["purpose"])
        self.assertEqual("selected-hook", brief["scenes"][0]["purpose"])
        self.assertEqual("planned", manifest["interview_slots"][0]["state"])
        self.assertEqual("selected_hook_id", manifest["experiment"]["variable_to_change"])
        self.assertIn("把虚构个案说成普遍结果", brief["forbidden_expressions"])
        Draft202012Validator(read_json(HANDOFF_SCHEMA)).validate(manifest)
        self.assertEqual(2, len(list(output_dir.iterdir())))

    def test_missing_compliance_check_is_blocked(self) -> None:
        review = copy.deepcopy(read_json(REVIEW_RECEIPT))
        review["compliance_gates"]["content_basis_accuracy"]["reviewed_check_ids"].pop()
        with self.assertRaises(CASE_ADAPTER.CaseScriptError) as context:
            self._adapt(review_receipt=review, output_name="missing-compliance-check")
        self.assertEqual("compliance_review_incomplete", context.exception.code)

    def test_synthetic_review_cannot_claim_live_account_approval(self) -> None:
        review = copy.deepcopy(read_json(REVIEW_RECEIPT))
        review["compliance_context"]["publishing_account_status"] = "authorized-for-planned-scope"
        with self.assertRaises(CASE_ADAPTER.CaseScriptError) as context:
            self._adapt(review_receipt=review, output_name="synthetic-live-account")
        self.assertEqual("compliance_context_drift", context.exception.code)

    def test_double_run_is_byte_stable(self) -> None:
        _, output_a = self._adapt(output_name="run-a")
        bytes_a = {path.name: path.read_bytes() for path in output_a.iterdir()}
        _, output_b = self._adapt(output_name="run-b")
        bytes_b = {path.name: path.read_bytes() for path in output_b.iterdir()}
        self.assertEqual(bytes_a, bytes_b)

    def test_existing_mvp_video_consumer_accepts_and_dry_runs(self) -> None:
        result, _ = self._adapt()
        output_root = self.temp_root / "mvp-dry-run"
        completed = subprocess.run(
            [
                sys.executable,
                str(MVP_ROOT / "scripts/content_video.py"),
                "dry-run",
                "--brief",
                result["brief"],
                "--schema",
                str(VIDEO_SCHEMA),
                "--research-output",
                str(RESEARCH),
                "--research-schema",
                str(RESEARCH_SCHEMA),
                "--case-handoff-manifest",
                result["manifest"],
                "--case-handoff-sha256",
                result["manifest_sha256"],
                "--require-case-handoff",
                "--output-root",
                str(output_root),
                "--max-age-hours",
                "1000000",
            ],
            cwd=MVP_ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        receipt = json.loads(completed.stdout)
        self.assertEqual("candidate_plan_ready", receipt["status"])
        self.assertFalse(receipt["would_execute_ffmpeg"])
        self.assertFalse(receipt["would_call_provider"])
        self.assertFalse(receipt["would_upload"])
        self.assertFalse(receipt["would_publish"])
        self.assertTrue(receipt["case_handoff_verified"])
        self.assertFalse(output_root.exists())

    def test_deidentified_interview_quote_requires_hash_authorization_and_stays_local(self) -> None:
        script = copy.deepcopy(read_json(CASE_SCRIPT))
        research = copy.deepcopy(read_json(RESEARCH))
        content = copy.deepcopy(read_json(self.content_item))
        fact = copy.deepcopy(read_json(FACT_CARD))
        route = copy.deepcopy(read_json(ROUTE_CARD))
        voice = copy.deepcopy(read_json(VOICE_RECEIPT))
        interview = copy.deepcopy(read_json(INTERVIEW_RECEIPT))
        review = copy.deepcopy(read_json(REVIEW_RECEIPT))
        slot = script["interview_slots"][0]
        slot.update(
            {
                "state": "recorded",
                "quote_text": interview["quote_text"],
                "recording_artifact_ref": interview["recording_artifact_ref"],
                "consent_artifact_ref": interview["consent_artifact_ref"],
                "consent_status": "granted",
                "privacy_status": "pass",
                "rights_status": "pass",
            }
        )
        self._sync_review_inputs(review, script, research, content, fact, route, voice, [interview])
        result, _ = self._adapt(
            script=script,
            research=research,
            content=content,
            fact_card=fact,
            route_card=route,
            voice_receipt=voice,
            interview_receipts=[interview],
            review_receipt=review,
        )
        brief = read_json(Path(result["brief"]))
        self.assertIn(interview["quote_text"], [scene["narration_draft"] for scene in brief["scenes"]])
        self.assertFalse(interview["boundaries"]["raw_media_embedded"])
        self.assertFalse(interview["boundaries"]["absolute_path_included"])
        self.assertFalse(interview["boundaries"]["external_service_called"])

        interview["quote_text"] = "患者张伟在北京某医院确诊后告诉了我。"
        interview["quote_sha256"] = __import__("hashlib").sha256(interview["quote_text"].encode("utf-8")).hexdigest()
        slot["quote_text"] = interview["quote_text"]
        self._sync_review_inputs(review, script, research, content, fact, route, voice, [interview])
        with self.assertRaises(CASE_ADAPTER.CaseScriptError) as context:
            self._adapt(
                script=script,
                research=research,
                content=content,
                fact_card=fact,
                route_card=route,
                voice_receipt=voice,
                interview_receipts=[interview],
                review_receipt=review,
                output_name="pii-interview-blocked",
            )
        self.assertEqual("sensitive_content_blocked", context.exception.code)

    def test_deidentified_interview_quote_hash_tamper_fails_closed(self) -> None:
        script = copy.deepcopy(read_json(CASE_SCRIPT))
        research = copy.deepcopy(read_json(RESEARCH))
        content = copy.deepcopy(read_json(self.content_item))
        fact = copy.deepcopy(read_json(FACT_CARD))
        route = copy.deepcopy(read_json(ROUTE_CARD))
        voice = copy.deepcopy(read_json(VOICE_RECEIPT))
        interview = copy.deepcopy(read_json(INTERVIEW_RECEIPT))
        review = copy.deepcopy(read_json(REVIEW_RECEIPT))
        slot = script["interview_slots"][0]
        slot.update(
            {
                "state": "recorded",
                "quote_text": interview["quote_text"],
                "recording_artifact_ref": interview["recording_artifact_ref"],
                "consent_artifact_ref": interview["consent_artifact_ref"],
                "consent_status": "granted",
                "privacy_status": "pass",
                "rights_status": "pass",
            }
        )
        interview["quote_sha256"] = "0" * 64
        self._sync_review_inputs(review, script, research, content, fact, route, voice, [interview])
        with self.assertRaises(CASE_ADAPTER.CaseScriptError) as context:
            self._adapt(
                script=script,
                research=research,
                content=content,
                fact_card=fact,
                route_card=route,
                voice_receipt=voice,
                interview_receipts=[interview],
                review_receipt=review,
                output_name="interview-quote-hash-tampered",
            )
        self.assertEqual("interview_quote_hash_drift", context.exception.code)

    def test_missing_human_voice_receipt_fails_closed(self) -> None:
        with self.assertRaises(CASE_ADAPTER.CaseScriptError) as context:
            CASE_ADAPTER.adapt_case_video_script(
                script_path=CASE_SCRIPT,
                research_path=RESEARCH,
                content_item_path=self.content_item,
                fact_card_path=FACT_CARD,
                route_card_path=ROUTE_CARD,
                voice_receipt_path=self.temp_root / "missing-human-voice-receipt.json",
                interview_receipt_paths=[],
                review_receipt_path=REVIEW_RECEIPT,
                output_dir=self.temp_root / "missing-human-voice-output",
            )
        self.assertEqual("invalid_or_missing_artifact", context.exception.code)

    def test_body_change_invalidates_voice_read_aloud_author_and_hook_chain(self) -> None:
        script = copy.deepcopy(read_json(CASE_SCRIPT))
        script["segments"][0]["spoken_text"] += " 正文冻结以后又被改动。"
        with self.assertRaises(CASE_ADAPTER.CaseScriptError) as context:
            self._adapt(script=script, output_name="stale-human-voice-chain")
        self.assertEqual("human_voice_body_hash_drift", context.exception.code)

    def test_single_command_e2e_is_stable_across_repeated_runs(self) -> None:
        output_root = self.temp_root / "single-command-e2e"
        command = [
            sys.executable,
            str(SCRIPTS / "run_case_video_script_e2e.py"),
            "--output-root",
            str(output_root),
        ]
        first = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
        self.assertEqual(0, first.returncode, first.stderr)
        first_bytes = {
            path.relative_to(output_root).as_posix(): path.read_bytes()
            for path in output_root.rglob("*")
            if path.is_file()
        }
        second = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
        self.assertEqual(0, second.returncode, second.stderr)
        second_bytes = {
            path.relative_to(output_root).as_posix(): path.read_bytes()
            for path in output_root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(first_bytes, second_bytes)
        receipt = read_json(output_root / "case-video-e2e-receipt.json")
        self.assertEqual("synthetic_e2e_passed", receipt["status"])
        self.assertFalse(receipt["verification"]["would_execute_ffmpeg"])
        self.assertFalse(receipt["verification"]["would_publish"])

    def test_single_command_e2e_recovers_from_expected_partial_output(self) -> None:
        output_root = self.temp_root / "recoverable-e2e"
        partial = output_root / "case/case-script-synthetic-insurance-001.manifest.json"
        partial.parent.mkdir(parents=True)
        partial.write_text("interrupted write", encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "run_case_video_script_e2e.py"),
                "--output-root",
                str(output_root),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(
            "synthetic_e2e_passed",
            read_json(output_root / "case-video-e2e-receipt.json")["status"],
        )

    def test_single_command_e2e_refuses_unmanaged_output(self) -> None:
        output_root = self.temp_root / "unmanaged-e2e"
        unmanaged = output_root / "do-not-overwrite.txt"
        unmanaged.parent.mkdir(parents=True)
        unmanaged.write_text("belongs to another workflow", encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "run_case_video_script_e2e.py"),
                "--output-root",
                str(output_root),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
        self.assertEqual(4, completed.returncode)
        self.assertEqual("output_root_unmanaged", json.loads(completed.stderr)["status"])
        self.assertEqual("belongs to another workflow", unmanaged.read_text(encoding="utf-8"))

    def test_schema_rejects_publish_ready_mode(self) -> None:
        script = read_json(CASE_SCRIPT)
        script["mode"] = "publish_ready"
        with self.assertRaises(CASE_ADAPTER.CaseScriptError) as context:
            self._adapt(script=script)
        self.assertEqual("schema_validation_failed", context.exception.code)

    def test_corrupt_json_fails_closed(self) -> None:
        corrupt = self.temp_root / "corrupt-case.json"
        corrupt.write_text("{not-json", encoding="utf-8")
        with self.assertRaises(CASE_ADAPTER.CaseScriptError) as context:
            CASE_ADAPTER.adapt_case_video_script(
                script_path=corrupt,
                research_path=RESEARCH,
                content_item_path=self.content_item,
                fact_card_path=FACT_CARD,
                route_card_path=ROUTE_CARD,
                voice_receipt_path=VOICE_RECEIPT,
                interview_receipt_paths=[],
                review_receipt_path=REVIEW_RECEIPT,
                output_dir=self.temp_root / "corrupt-output",
            )
        self.assertEqual("invalid_or_missing_artifact", context.exception.code)

    def test_missing_review_receipt_fails_closed(self) -> None:
        with self.assertRaises(CASE_ADAPTER.CaseScriptError) as context:
            CASE_ADAPTER.adapt_case_video_script(
                script_path=CASE_SCRIPT,
                research_path=RESEARCH,
                content_item_path=self.content_item,
                fact_card_path=FACT_CARD,
                route_card_path=ROUTE_CARD,
                voice_receipt_path=VOICE_RECEIPT,
                interview_receipt_paths=[],
                review_receipt_path=self.temp_root / "missing-review-receipt.json",
                output_dir=self.temp_root / "missing-review-output",
            )
        self.assertEqual("invalid_or_missing_artifact", context.exception.code)

    def test_missing_downstream_dependency_fails_closed(self) -> None:
        with self.assertRaises(CASE_ADAPTER.CaseScriptError) as context:
            E2E_RUNNER.run_e2e(
                self.temp_root / "missing-downstream-output",
                self.temp_root / "missing-mvp-video",
            )
        self.assertEqual("downstream_dependency_missing", context.exception.code)

    def test_downstream_timeout_fails_closed(self) -> None:
        with patch(
            "run_case_video_script_e2e.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="content-video", timeout=30),
        ):
            with self.assertRaises(CASE_ADAPTER.CaseScriptError) as context:
                E2E_RUNNER.run_e2e(self.temp_root / "timeout-output", MVP_ROOT)
        self.assertEqual("downstream_mvp_timeout", context.exception.code)

    def test_all_negative_fixtures_fail_closed(self) -> None:
        descriptor = read_json(NEGATIVE_CASES)
        for case in descriptor["cases"]:
            with self.subTest(case=case["id"]):
                script = copy.deepcopy(read_json(CASE_SCRIPT))
                research = copy.deepcopy(read_json(RESEARCH))
                content = copy.deepcopy(read_json(self.content_item))
                fact = copy.deepcopy(read_json(FACT_CARD))
                route = copy.deepcopy(read_json(ROUTE_CARD))
                voice = copy.deepcopy(read_json(VOICE_RECEIPT))
                review = copy.deepcopy(read_json(REVIEW_RECEIPT))
                mutation = case["mutation"]

                if mutation == "research_hash_drift":
                    research["scope"]["statement"] += " changed"
                elif mutation == "content_item_hash_drift":
                    content["title"] += " changed"
                elif mutation == "artifact_version_drift":
                    script["inputs"]["fact_card_ref"]["schema_version"] = "content-fact-card.v999"
                elif mutation == "unverified_evidence_ref":
                    script["segments"][0]["evidence_refs"][0]["ref_id"] = "claim_missing"
                elif mutation == "candidate_evidence":
                    target = research["evidence"][0]
                    target["evidence_status"] = "candidate"
                    target["review_status"] = "candidate"
                    research["evidence_links"][0]["evidence_status"] = "candidate"
                elif mutation == "sensitive_phone":
                    script["segments"][0]["spoken_text"] += " 联系电话：13800138000。"
                    self._sync_stage_hashes(script, voice)
                elif mutation == "named_person_timeline":
                    script["segments"][0]["spoken_text"] += " 患者张伟在北京某医院确诊肺癌后向我咨询。"
                    self._sync_stage_hashes(script, voice)
                elif mutation == "named_person_timeline_variant":
                    script["segments"][0]["spoken_text"] += " 这位病人张伟在北京某医院查出肺癌后找到了我。"
                    self._sync_stage_hashes(script, voice)
                elif mutation == "medical_treatment_choice":
                    script["segments"][0]["spoken_text"] += " 你应该选择这种治疗。"
                    self._sync_stage_hashes(script, voice)
                elif mutation == "guaranteed_claim_in_negation":
                    script["segments"][0]["spoken_text"] += " 不要担心，这次一定能赔。"
                    self._sync_stage_hashes(script, voice)
                elif mutation == "universal_treatment_claim":
                    script["story"]["main_judgment"]["text"] = "这种疗法能显著延长所有患者寿命。"
                    self._sync_stage_hashes(script, voice)
                elif mutation == "unsupported_treatment_comparison":
                    script["segments"][0]["spoken_text"] += " 质子治疗比普通放疗更有效。"
                    self._sync_stage_hashes(script, voice)
                elif mutation == "unsupported_survival_claim":
                    script["story"]["main_judgment"]["text"] = "质子治疗能提高五年生存率。"
                    self._sync_stage_hashes(script, voice)
                elif mutation == "unsupported_insurance_scope":
                    script["title"] = "这份保险能报销全部癌症治疗费用"
                    self._sync_stage_hashes(script, voice)
                elif mutation == "unrecorded_interview_quote":
                    script["interview_slots"][0]["quote_text"] = "这是未经录制的虚构回答。"
                elif mutation == "recorded_fake_artifacts":
                    slot = script["interview_slots"][0]
                    slot.update(
                        {
                            "state": "recorded",
                            "quote_text": "这是伪造的录音引用。",
                            "recording_artifact_ref": {
                                "artifact_id": "recording-fake",
                                "schema_version": "recording.v1",
                                "sha256": "1" * 64,
                            },
                            "consent_artifact_ref": {
                                "artifact_id": "consent-fake",
                                "schema_version": "consent.v1",
                                "sha256": "2" * 64,
                            },
                            "consent_status": "granted",
                            "privacy_status": "pass",
                            "rights_status": "pass",
                        }
                    )
                elif mutation == "hook_before_body_stable":
                    script["body_status"] = "draft"
                elif mutation == "hook_adds_number":
                    script["hook_candidates"][0]["text"] += " 30万元已经赔完。"
                elif mutation == "hook_adds_evidence_outside_body":
                    script["story"]["constraint"]["evidence_refs"] = [
                        {"ref_type": "claim", "ref_id": "claim_synthetic_service_boundary"}
                    ]
                    script["hook_candidates"][0]["evidence_refs"].append(
                        {"ref_type": "evidence", "ref_id": "evidence_synthetic_interview_boundary"}
                    )
                elif mutation == "visual_rights_unknown":
                    script["segments"][0]["visual_candidates"][0]["rights_status"] = "unknown"
                elif mutation == "visual_rights_self_asserted":
                    script["segments"][0]["visual_candidates"][0]["rights_status"] = "reviewed-cleared"
                elif mutation == "visual_missing_evidence":
                    script["segments"][0]["visual_candidates"][0]["evidence_refs"] = []
                elif mutation == "visual_real_record_disguised":
                    script["segments"][0]["visual_candidates"][0]["description"] = "真实病历和保单截图"
                elif mutation == "fact_gate_blocked":
                    fact["gates"]["privacy"] = "blocked"
                    script["inputs"]["fact_card_ref"] = self._artifact_ref(fact, "fact_card_id")
                elif mutation == "content_gate_blocked":
                    content["gates"]["fact"]["status"] = "blocked"
                    script["inputs"]["content_item_ref"] = self._artifact_ref(content, "content_id")
                elif mutation == "fact_forbidden_expression_used":
                    script["segments"][0]["spoken_text"] += " 把虚构个案说成普遍结果。"
                    self._sync_stage_hashes(script, voice)
                elif mutation == "skill_order_drift":
                    third = script["skill_stage_receipts"][2]
                    fourth = script["skill_stage_receipts"][3]
                    third["skill_id"], fourth["skill_id"] = fourth["skill_id"], third["skill_id"]
                    third["role"], fourth["role"] = fourth["role"], third["role"]
                elif mutation == "skill_receipt_classification_drift":
                    script["skill_stage_receipts"][0]["synthetic_stub"] = False
                elif mutation == "duplicate_segment_id":
                    duplicate = copy.deepcopy(script["segments"][0])
                    duplicate["spoken_text"] += " duplicate"
                    script["segments"].append(duplicate)
                elif mutation == "route_question_drift":
                    route["single_question"] += " changed"
                    script["inputs"]["route_card_ref"]["sha256"] = RESEARCH_ADAPTER.sha256_value(route)
                elif mutation == "fact_card_content_id_drift":
                    fact["content_id"] = "research-other-synthetic-content"
                    script["inputs"]["fact_card_ref"]["sha256"] = RESEARCH_ADAPTER.sha256_value(fact)
                elif mutation == "synthetic_claimed_as_real":
                    script["segments"][0]["spoken_text"] += " 这是一个真实客户案例。"
                    self._sync_stage_hashes(script, voice)
                elif mutation == "synthetic_boolean_downgrade":
                    script["synthetic_only"] = False
                elif mutation == "full_synthetic_downgrade":
                    script["synthetic_only"] = False
                    fact["synthetic_only"] = False
                    route["synthetic_only"] = False
                    research["scope"]["constraints"] = [
                        value for value in research["scope"]["constraints"] if value != "synthetic-only"
                    ]
                    research["provenance"]["source_systems"] = ["local-case-record"]
                    for source in research["sources"]:
                        source["provenance"]["note_fields"]["data_classification"] = "deidentified"
                    for receipt in script["skill_stage_receipts"]:
                        receipt["synthetic_stub"] = False
                    review["synthetic_only"] = False
                    review["review_mode"] = "human-local-review"
                    review["reviewer"] = "self-asserted-reviewer"
                    script["inputs"]["research_output_ref"] = self._artifact_ref(research, "research_id")
                    script["inputs"]["fact_card_ref"] = self._artifact_ref(fact, "fact_card_id")
                    script["inputs"]["route_card_ref"] = self._artifact_ref(route, "route_card_id")
                    self._sync_stage_hashes(script, voice)
                    self._sync_review_inputs(review, script, research, content, fact, route, voice)
                elif mutation == "title_attributed_quote":
                    script["title"] = "客户告诉我：这次经历改变了他"
                    self._sync_stage_hashes(script, voice)
                elif mutation == "segment_attributed_quote_variant":
                    script["segments"][0]["spoken_text"] += " 这位病人当时对我说，这次终于放心了。"
                    self._sync_stage_hashes(script, voice)
                elif mutation == "review_subject_stale":
                    script["story"]["main_judgment"]["text"] = "服务边界必须清楚。"
                    self._sync_stage_hashes(script, voice)
                    self._sync_review_inputs(
                        review,
                        script,
                        research,
                        content,
                        fact,
                        route,
                        voice,
                        sync_subject=False,
                    )
                elif mutation == "review_input_hash_drift":
                    review["inputs"]["case_video_script"]["sha256"] = "0" * 64
                elif mutation == "required_review_removed":
                    script["human_review"]["required_reviews"].pop()
                elif mutation == "review_gate_removed":
                    review["gates"].pop("rights")
                else:
                    self.fail(f"unknown negative mutation: {mutation}")

                with self.assertRaises(CASE_ADAPTER.CaseScriptError) as context:
                    self._adapt(
                        script=script,
                        research=research,
                        content=content,
                        fact_card=fact,
                        route_card=route,
                        voice_receipt=voice,
                        review_receipt=review,
                        output_name=f"negative-{case['id']}",
                    )
                self.assertEqual(case["expected_error"], context.exception.code)


if __name__ == "__main__":
    unittest.main()
