#!/usr/bin/env python3
"""Targeted synthetic-only unit test: validate_insurance_clause_explanations.py.

Uses a minimal, explicitly synthetic test schema created inside the test
workspace. The public baseline has no confirmed canonical schema and this
candidate does not add a default path; --schema remains required. All objects
are new synthetic objects. No real contract, client, clinical or legal data.
"""
from __future__ import annotations

import copy
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
CLI = SCRIPTS / "validate_insurance_clause_explanations.py"
WORKSPACE = Path(os.environ.get("CANDIDATE_TEST_WORKSPACE", str(ROOT.parent / "synthetic")))
sys.path.insert(0, str(SCRIPTS))

import validate_insurance_clause_explanations as ice  # noqa: E402

SYNTHETIC_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:synthetic:insurance-clause-explanation:test-only",
    "title": "SYNTHETIC TEST-ONLY insurance clause explanation schema",
    "$comment": "Minimal synthetic schema for unit boundaries only. NOT a canonical Owner contract schema.",
    "type": "object",
    "required": ["source_document", "clause_units", "review"],
    "properties": {
        "source_document": {"type": "object"},
        "clause_units": {"type": "array", "items": {"type": "object"}},
        "review": {"type": "object"},
    },
}


def synthetic_unit() -> dict:
    return {
        "clause_id": "synthetic-clause-001",
        "evidence_status": "source_verified",
        "source_anchors": [{
            "anchor_id": "synthetic-anchor-001",
            "page": 1,
            "transcription_method": "text_extract",
            "verified_against_render": True,
        }],
        "facts": [{
            "fact_id": "synthetic-fact-001",
            "kind": "amount",
            "critical": False,
            "source_anchor_ids": ["synthetic-anchor-001"],
        }],
        "normalized_rule": {"fact_refs": ["synthetic-fact-001"]},
        "explanation": {
            "fact_refs": ["synthetic-fact-001"],
            "one_sentence": "这是一条完全合成的条款说明。",
            "plain_language": "本说明仅用于离线单元测试。",
        },
        "reverse_paraphrase": {"result": "fail", "checks": {}},
    }


def synthetic_document() -> dict:
    return {
        "source_document": {
            "page_count": 3,
            "source_file": "",
            "source_sha256": "",
            "extraction_status": "text_layer_ok",
        },
        "clause_units": [synthetic_unit()],
        "review": {"status": "reviewed"},
    }


class ValidateInsuranceClauseExplanationsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        WORKSPACE.mkdir(parents=True, exist_ok=True)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=str(WORKSPACE), prefix="insurance-")
        self.dir = Path(self.temp.name)
        self.fixtures = self.dir / "fixtures"
        self.fixtures.mkdir()
        self.schema_path = self.dir / "synthetic-test-only-schema.json"
        self.schema_path.write_text(json.dumps(SYNTHETIC_SCHEMA, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.addCleanup(self.temp.cleanup)

    def run_cli(self, root: Path, schema: Path | None = None, extra: list[str] | None = None):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SCRIPTS) + os.pathsep + env.get("PYTHONPATH", "")
        command = [sys.executable, str(CLI), "--root", str(root)]
        if schema is not None:
            command += ["--schema", str(schema)]
        if extra:
            command += extra
        return subprocess.run(command, cwd=str(ROOT), env=env, capture_output=True, text=True)

    def write_fixture(self, name: str, document: dict) -> Path:
        path = self.fixtures / name
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    # --- schema / CLI fail-closed boundaries ---

    def test_schema_argument_is_required(self) -> None:
        proc = self.run_cli(self.fixtures)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--schema", proc.stderr)

    def test_missing_schema_file_fails_closed(self) -> None:
        self.write_fixture("insurance-clause-explanation.synthetic-001.json", synthetic_document())
        proc = self.run_cli(self.fixtures, self.dir / "absent-schema.json")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("No such file", proc.stderr + " " + proc.stdout)

    def test_invalid_schema_is_rejected(self) -> None:
        bad = self.dir / "bad-schema.json"
        bad.write_text("{not-json", encoding="utf-8")
        self.assertNotEqual(self.run_cli(self.fixtures, bad).returncode, 0)
        invalid = self.dir / "invalid-schema.json"
        invalid.write_text(json.dumps({"type": 3}), encoding="utf-8")
        self.assertNotEqual(self.run_cli(self.fixtures, invalid).returncode, 0)

    def test_no_fixtures_returns_failure(self) -> None:
        proc = self.run_cli(self.fixtures, self.schema_path)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("No insurance clause explanation fixtures found", proc.stderr)

    def test_valid_synthetic_fixture_passes_cli(self) -> None:
        self.write_fixture("insurance-clause-explanation.synthetic-001.json", synthetic_document())
        proc = self.run_cli(self.fixtures, self.schema_path)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1200:])
        self.assertIn("Validated 1 insurance clause explanation fixture(s).", proc.stdout)

    def test_any_bad_fixture_fails_the_whole_cli(self) -> None:
        self.write_fixture("insurance-clause-explanation.synthetic-good.json", synthetic_document())
        bad = synthetic_document()
        bad["clause_units"][0]["explanation"]["one_sentence"] = "一定赔"
        self.write_fixture("insurance-clause-explanation.synthetic-bad.json", bad)
        proc = self.run_cli(self.fixtures, self.schema_path)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("prohibited_overclaim", proc.stderr)
        self.assertIn("validation failed", proc.stderr)

    def test_no_canonical_schema_is_shipped_or_defaulted(self) -> None:
        self.assertFalse(hasattr(ice, "DEFAULT_SCHEMA"))
        self.assertFalse(hasattr(ice, "DEFAULT_SCHEMA_PATH"))
        schema_dir = ROOT / "schemas"
        self.assertFalse(any("insurance" in path.name.lower() for path in schema_dir.glob("*.json")))
        source = CLI.read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--schema", type=Path, required=True)', source)

    # --- generic function boundaries with a synthetic document ---

    def test_synthetic_document_has_no_errors(self) -> None:
        self.assertEqual(ice.validate_document(synthetic_document(), SYNTHETIC_SCHEMA), [])

    def test_schema_required_field_error_is_reported(self) -> None:
        document = synthetic_document()
        document.pop("review")
        errors = ice.validate_document(document, SYNTHETIC_SCHEMA)
        self.assertTrue(any("schema_error" in error for error in errors))

    def test_overclaim_in_any_explanation_field_is_rejected(self) -> None:
        for field in ("one_sentence", "plain_language"):
            document = synthetic_document()
            document["clause_units"][0]["explanation"][field] = "肯定赔，无需等待"
            self.assertTrue(any("prohibited_overclaim" in e for e in ice.validate_document(document, SYNTHETIC_SCHEMA)))
        document = synthetic_document()
        document["clause_units"][0]["explanation"]["positive_examples"] = [
            {"scenario": "合成场景", "outcome": "合成结果", "reason": "百分百赔"}
        ]
        self.assertTrue(any("prohibited_overclaim" in e for e in ice.validate_document(document, SYNTHETIC_SCHEMA)))

    def test_semantic_preservation_failures(self) -> None:
        cases = []
        doc = synthetic_document()
        doc["clause_units"][0]["facts"][0]["critical"] = True
        doc["clause_units"][0]["explanation"]["fact_refs"] = []
        cases.append((doc, "critical_fact_missing_from_explanation"))

        doc = synthetic_document()
        doc["clause_units"][0]["facts"][0]["source_anchor_ids"] = ["absent-anchor"]
        cases.append((doc, "dangling_anchor_ref"))

        doc = synthetic_document()
        doc["clause_units"][0]["normalized_rule"]["all_of"] = [{"fact_refs": ["absent-fact"]}]
        cases.append((doc, "dangling_fact_ref"))

        doc = synthetic_document()
        second = copy.deepcopy(doc["clause_units"][0])
        doc["clause_units"].append(second)
        cases.append((doc, "duplicate_clause_id"))

        doc = synthetic_document()
        doc["clause_units"][0]["source_anchors"][0]["page"] = 99
        cases.append((doc, "anchor_page_out_of_range"))

        doc = synthetic_document()
        doc["source_document"]["extraction_status"] = "text_layer_corrupted"
        cases.append((doc, "corrupted_text_layer_used_as_verbatim"))

        doc = synthetic_document()
        doc["clause_units"][0]["reverse_paraphrase"] = {"result": "pass", "checks": {"paraphrase": False}}
        cases.append((doc, "reverse_pass_with_failed_check"))

        doc = synthetic_document()
        doc["clause_units"][0]["evidence_status"] = "draft"
        doc["clause_units"][0]["source_anchors"][0]["verified_against_render"] = False
        cases.append((doc, "reviewed_with_unverified_unit"))

        for document, expected in cases:
            errors = ice.validate_document(document, SYNTHETIC_SCHEMA)
            self.assertTrue(any(expected in error for error in errors), f"expected {expected}, got {errors}")

    def test_critical_kinds_must_be_structured(self) -> None:
        for kind, collection, expected in (
            ("time", "time_rules", "critical_time_not_structured"),
            ("exception", "exceptions", "critical_exception_not_structured"),
            ("state_change", "state_changes", "critical_state_change_not_structured"),
        ):
            document = synthetic_document()
            unit = document["clause_units"][0]
            unit["facts"][0].update({"kind": kind, "critical": True})
            errors = ice.validate_document(document, SYNTHETIC_SCHEMA)
            self.assertTrue(any(expected in error for error in errors), f"{expected}: {errors}")
            unit["normalized_rule"][collection] = [{"fact_refs": ["synthetic-fact-001"]}]
            self.assertFalse(any(expected in error for error in ice.validate_document(document, SYNTHETIC_SCHEMA)))

    def test_source_hash_drift_is_rejected(self) -> None:
        source_file = self.dir / "synthetic-source.txt"
        source_file.write_text("synthetic source bytes\n", encoding="utf-8")
        document = synthetic_document()
        document["source_document"]["source_file"] = str(source_file)
        document["source_document"]["source_sha256"] = "0" * 64
        self.assertIn("source_hash_mismatch", ice.validate_document(document, SYNTHETIC_SCHEMA))
        document["source_document"]["source_sha256"] = hashlib.sha256(source_file.read_bytes()).hexdigest()
        self.assertNotIn("source_hash_mismatch", ice.validate_document(document, SYNTHETIC_SCHEMA))

    def test_forbidden_overclaim_constant_is_unchanged(self) -> None:
        self.assertEqual(ice.FORBIDDEN_OVERCLAIMS, (
            "一定赔", "肯定赔", "百分百赔", "百分之百赔", "正规医院确诊即可", "合同生效后第一次确诊",
        ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
