import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
MODULE_PATH = ROOT / "scripts" / "validate_insurance_clause_explanations.py"
SCHEMA_PATH = (
    WORKSPACE
    / "docs"
    / "content-creation-system"
    / "adapters"
    / "insurance-clause-explanation.schema.json"
)
FIXTURE_PATH = ROOT / "fixtures" / "insurance-clause-explanation.renxin-baobei6.json"

module_spec = importlib.util.spec_from_file_location(
    "validate_insurance_clause_explanations", MODULE_PATH
)
validator = importlib.util.module_from_spec(module_spec)
assert module_spec.loader is not None
module_spec.loader.exec_module(validator)


class InsuranceClauseExplanationTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def validate(self, data):
        return validator.validate_document(data, self.schema, FIXTURE_PATH)

    def unit(self, clause_id):
        return next(
            unit for unit in self.fixture["clause_units"] if unit["clause_id"] == clause_id
        )

    def test_golden_fixture_is_valid(self):
        self.assertEqual([], self.validate(self.fixture))

    def test_schema_requires_negative_example(self):
        broken = copy.deepcopy(self.fixture)
        broken["clause_units"][0]["explanation"]["negative_examples"] = []
        errors = self.validate(broken)
        self.assertTrue(any(item.startswith("schema_error:") for item in errors))

    def test_duplicate_clause_id_is_rejected(self):
        broken = copy.deepcopy(self.fixture)
        broken["clause_units"][1]["clause_id"] = broken["clause_units"][0]["clause_id"]
        errors = self.validate(broken)
        self.assertIn("duplicate_clause_id:clause_waiting-period-general", errors)

    def test_dangling_fact_reference_is_rejected(self):
        broken = copy.deepcopy(self.fixture)
        broken["clause_units"][0]["explanation"]["fact_refs"].append("fact_missing")
        errors = self.validate(broken)
        self.assertTrue(any("dangling_fact_ref" in item for item in errors))

    def test_critical_fact_cannot_be_omitted_from_explanation(self):
        broken = copy.deepcopy(self.fixture)
        refs = broken["clause_units"][0]["explanation"]["fact_refs"]
        refs.remove("fact_wait-accident-exception")
        errors = self.validate(broken)
        self.assertIn(
            "critical_fact_missing_from_explanation:clause_waiting-period-general:fact_wait-accident-exception",
            errors,
        )

    def test_critical_exception_must_remain_structured(self):
        broken = copy.deepcopy(self.fixture)
        broken["clause_units"][0]["normalized_rule"]["exceptions"] = []
        errors = self.validate(broken)
        self.assertIn(
            "critical_exception_not_structured:clause_waiting-period-general:fact_wait-accident-exception",
            errors,
        )

    def test_critical_state_change_must_remain_structured(self):
        broken = copy.deepcopy(self.fixture)
        target = next(
            unit
            for unit in broken["clause_units"]
            if unit["clause_id"] == "clause_post-first-critical-illness-state"
        )
        target["normalized_rule"]["state_changes"] = []
        errors = self.validate(broken)
        self.assertTrue(any(item.startswith("critical_state_change_not_structured") for item in errors))

    def test_reverse_paraphrase_cannot_pass_with_failed_check(self):
        broken = copy.deepcopy(self.fixture)
        reverse = broken["clause_units"][0]["reverse_paraphrase"]
        reverse["result"] = "pass"
        reverse["checks"]["exceptions_preserved"] = False
        errors = self.validate(broken)
        self.assertIn(
            "reverse_pass_with_failed_check:clause_waiting-period-general", errors
        )

    def test_plain_language_overclaim_is_rejected(self):
        broken = copy.deepcopy(self.fixture)
        broken["clause_units"][0]["explanation"]["one_sentence"] = "满足这些条件就一定赔。"
        errors = self.validate(broken)
        self.assertIn(
            "prohibited_overclaim:clause_waiting-period-general:一定赔", errors
        )

    def test_reviewed_status_requires_render_verified_anchors(self):
        broken = copy.deepcopy(self.fixture)
        broken["review"]["status"] = "reviewed"
        for unit in broken["clause_units"]:
            unit["evidence_status"] = "source_verified"
        errors = self.validate(broken)
        self.assertTrue(any(item.startswith("reviewed_without_verified_anchor") for item in errors))

    def test_corrupted_text_layer_cannot_supply_verbatim_text(self):
        broken = copy.deepcopy(self.fixture)
        broken["clause_units"][0]["source_anchors"][0][
            "transcription_method"
        ] = "text_extract"
        errors = self.validate(broken)
        self.assertTrue(any(item.startswith("corrupted_text_layer_used_as_verbatim") for item in errors))

    def test_product_specific_golden_facts_are_stable(self):
        waiting = self.unit("clause_waiting-period-general")
        waiting_facts = {item["fact_id"]: item["value"] for item in waiting["facts"]}
        self.assertEqual(180, waiting_facts["fact_wait-days"])
        self.assertEqual(
            "因意外伤害发生合同约定的保险事故，不适用等待期",
            waiting_facts["fact_wait-accident-exception"],
        )

        initial = self.unit("clause_initial-diagnosis-definition")
        initial_facts = {item["fact_id"]: item["value"] for item in initial["facts"]}
        self.assertIn("出生之日起", initial_facts["fact_initial-diagnosis-since-birth"])

        post_claim = self.unit("clause_post-first-critical-illness-state")
        post_facts = {item["fact_id"]: item["value"] for item in post_claim["facts"]}
        self.assertEqual(
            "本主险合同现金价值降为零",
            post_facts["fact_post-first-ci-cash-value-zero"],
        )

    def test_source_hash_matches_user_pdf_when_present(self):
        source = Path(self.fixture["source_document"]["source_file"])
        if not source.is_file():
            self.skipTest("User-provided PDF is not present on this machine")
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        self.assertEqual(self.fixture["source_document"]["source_sha256"], actual)


if __name__ == "__main__":
    unittest.main()
