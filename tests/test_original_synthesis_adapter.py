"""Targeted counterexamples for the bounded editorial compiler (offline only).

The plan/persistence guards run with no native owner installed. The reviewed
research and native gate cases require the explicit public owner roots recorded
by the host contract; without them they are skipped with that exact reason, never
mocked into a pass.
"""
import copy
import json
import os
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import original_synthesis_adapter as sut
from temp_workspace import isolated_test_directory, prepare_test_temp_root

FIXTURES = ROOT / "fixtures" / "synthesis-lifecycle"
UPSTREAM = FIXTURES / "upstream"
PUBLIC_OWNERS = os.environ.get("CONTENT_STUDIO_PUBLIC_OWNERS_ROOT")
CORE_ROOT = os.environ.get("ARTIFACT_LIFECYCLE_CORE_ROOT")


def load_plan():
    return sut.read(FIXTURES / "editorial-plan.json")


def candidate_plan():
    """Plan without reviewed_research: exercises candidate-only guards."""
    plan = load_plan()
    plan.pop("reviewed_research", None)
    for unit in plan["units"]:
        if unit["id"] == "unit-fact-trail":
            unit["type"] = "agent_inference"
            unit["assertion_kind"] = "source_interpretation"
    return plan


def plain_research():
    return sut.read(UPSTREAM / "public-input.json")


class PlanGuardTests(unittest.TestCase):
    def setUp(self):
        self.plan = candidate_plan()
        self.research = plain_research()

    def reject(self, plan, code):
        with self.assertRaises(sut.SynthesisError) as caught:
            sut.validate_plan(plan, self.research)
        self.assertEqual(caught.exception.code, code)

    def test_valid_candidate_plan(self):
        sut.validate_plan(self.plan, self.research)

    def test_authority_escalation(self):
        self.plan["human_approved"] = True
        self.reject(self.plan, "authority_escalation")

    def test_invented_number(self):
        self.plan["units"][2]["text"] = "这套虚构办法节省了80%的时间。"
        self.reject(self.plan, "number_needs_source")

    def test_unsourced_case(self):
        self.plan["units"][2]["assertion_kind"] = "case"
        self.reject(self.plan, "case_needs_source")

    def test_quote_retyped_as_inference(self):
        q = next(u for u in self.plan["units"] if u["type"] == "verified_quote")
        q["type"] = "agent_inference"
        self.reject(self.plan, "quote_type_drift")

    def test_platform_claim_promoted(self):
        self.plan["units"][2]["platform_sample_refs"] = ["xhs:fiction"]
        self.reject(self.plan, "platform_claim_not_fact_authority")

    def test_canonical_claim_drift(self):
        u = next(u for u in self.plan["units"] if u.get("claim_id"))
        u["text"] = "The handbook asks a note-taker to delete the reviewed trail."
        self.reject(self.plan, "canonical_claim_drift")

    def test_quote_text_drift(self):
        q = next(u for u in self.plan["units"] if u["type"] == "verified_quote")
        q["text"] += " Nobody loses data."
        self.reject(self.plan, "quote_not_in_admitted_excerpt")

    def test_quote_length_limit_counts_both_orders(self):
        q = next(u for u in self.plan["units"] if u["type"] == "verified_quote")
        second = copy.deepcopy(q)
        second["id"] = "unit-quote-trail-second"
        self.plan["units"].append(second)
        self.plan["article_order"].append(second["id"])
        self.plan["oral_order"].append(second["id"])
        self.reject(self.plan, "quote_length_limit")

    def test_withheld_promotion(self):
        self.plan["withheld"][0]["status"] = "verified"
        self.reject(self.plan, "withheld_promotion")

    def test_unit_order_missing_claim(self):
        self.plan["article_order"].remove("unit-fact-trail")
        self.reject(self.plan, "platform_claim_set_drift")


class PersistenceTests(unittest.TestCase):
    def test_partial_write_resume_and_idempotence(self):
        root = self.enterContext(isolated_test_directory("synthesis-resume")) / "out"
        texts = {"a.txt": "a", "b.txt": "b"}
        sut.persist(root, texts, stop_after=1)
        self.assertFalse((root / "b.txt").exists())
        sut.persist(root, texts)
        before = {p.name: p.stat().st_mtime_ns for p in root.iterdir()}
        sut.persist(root, texts)
        self.assertEqual(before, {p.name: p.stat().st_mtime_ns for p in root.iterdir()})

    def test_drift_precheck_before_new_writes(self):
        root = self.enterContext(isolated_test_directory("synthesis-drift")) / "out"
        sut.persist(root, {"z.txt": "original"})
        with self.assertRaises(sut.SynthesisError):
            sut.persist(root, {"a.txt": "new", "z.txt": "changed"})
        self.assertFalse((root / "a.txt").exists())

    def test_output_path_escape(self):
        root = self.enterContext(isolated_test_directory("synthesis-escape")) / "out"
        with self.assertRaisesRegex(sut.SynthesisError, "output_path_escape"):
            sut.persist(root, {"../escape.txt": "x"})


class ReviewedOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PUBLIC_OWNERS:
            raise unittest.SkipTest("CONTENT_STUDIO_PUBLIC_OWNERS_ROOT is not set; native owner not supplied")
        owners = Path(PUBLIC_OWNERS).resolve()
        qrp_source = owners / "public-qrp" / "src/question_research_poc/bounded_deep_loop.py"
        main_scripts = owners / "public-main/self-media-creation-system/scripts"
        if not qrp_source.is_file():
            raise unittest.SkipTest("public-qrp source is not supplied under CONTENT_STUDIO_PUBLIC_OWNERS_ROOT")
        if not (main_scripts / "cross_platform_fact_consistency_gate.py").is_file():
            raise unittest.SkipTest("public-main gate source is not supplied under CONTENT_STUDIO_PUBLIC_OWNERS_ROOT")
        cls.owners = owners
        cls.main_root = owners / "public-main/self-media-creation-system"
        cls.temp = prepare_test_temp_root() / f"synthesis-owners-{os.getpid()}"
        cls.temp.mkdir()
        registry = cls.temp / "tool-registry.json"
        registry.write_text(json.dumps({"tools": {"content-creation-system": {
            "self_media_path": str(cls.main_root),
            "runtime_main": {"repositories": {"self": {"path": str(cls.main_root)}}},
        }}}), encoding="utf-8")
        cls.qrp, cls.core, cls.gate = sut.bind_owners(
            qrp_root=owners / "public-qrp", tool_registry=registry)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "temp", None), ignore_errors=True)

    def setUp(self):
        self.plan = load_plan()
        self.research = self.core._load_fixture(UPSTREAM / "public-input.json")
        self.policy = sut.reviewed_policy(self.plan, self.research, UPSTREAM, self.qrp)

    def test_reviewed_plan_is_valid(self):
        sut.validate_plan(self.plan, self.research, self.policy)

    def test_unreviewed_source_fact_is_blocked(self):
        plan = copy.deepcopy(self.plan)
        plan.pop("reviewed_research", None)
        with self.assertRaises(sut.SynthesisError) as caught:
            sut.validate_plan(plan, self.research)
        self.assertEqual(caught.exception.code, "source_fact_not_admitted")

    def test_incomplete_capture_cannot_become_source_fact(self):
        research = copy.deepcopy(self.research)
        research["sources"][0]["capture_content_ok"] = False
        with self.assertRaises(sut.SynthesisError) as caught:
            sut.reviewed_policy(self.plan, research, UPSTREAM, self.qrp)
        self.assertEqual(caught.exception.code, "source_fact_requires_complete_capture")

    def test_reviewed_claim_binding_drift(self):
        research = copy.deepcopy(self.research)
        research["claims"][0]["text"] = "A different fictional claim."
        with self.assertRaises(sut.SynthesisError) as caught:
            sut.reviewed_policy(self.plan, research, UPSTREAM, self.qrp)
        self.assertEqual(caught.exception.code, "reviewed_claim_binding_drift")

    def test_reviewed_evidence_binding_drift(self):
        with isolated_test_directory("synthesis-native") as temporary:
            upstream = temporary / "upstream"
            upstream.mkdir()
            for name in ("public-input.json", "consumer-index.json", "reviewed-research.json"):
                (upstream / name).write_bytes((UPSTREAM / name).read_bytes())
            (upstream / "archives").mkdir()
            (upstream / "archives" / "field-notes-primary.json").write_bytes(
                (UPSTREAM / "archives" / "field-notes-primary.json").read_bytes())
            native = sut.read(upstream / "reviewed-research.json")
            native["evidence"][0]["excerpt"] = "a different fictional excerpt"
            (upstream / "reviewed-research.json").write_text(sut.json_text(native), encoding="utf-8")
            plan = copy.deepcopy(self.plan)
            plan["reviewed_research"]["sha256"] = sut.sha((upstream / "reviewed-research.json").read_bytes())
            with self.assertRaises(sut.SynthesisError) as caught:
                sut.reviewed_policy(plan, self.research, upstream, self.qrp)
            self.assertEqual(caught.exception.code, "reviewed_evidence_binding_drift")

    def test_rendered_copy_drift(self):
        texts, _, _ = sut.compile_candidate(self.plan, self.research, self.policy, qrp=self.qrp)
        texts["oral-script.md"] = texts["oral-script.md"].replace(
            "keep one reviewed trail", "delete the reviewed trail")
        with self.assertRaises(sut.SynthesisError) as caught:
            sut.validate_rendered(texts, self.plan, self.research, self.policy, qrp=self.qrp)
        self.assertEqual(caught.exception.code, "rendered_copy_drift")

    def test_missing_gate_owner_blocks(self):
        with isolated_test_directory("synthesis-missing-owner") as temporary:
            registry = temporary / "tool-registry.json"
            absent = temporary / "no-owner"
            registry.write_text(json.dumps({"tools": {"content-creation-system": {
                "self_media_path": str(absent),
                "runtime_main": {"repositories": {"self": {"path": str(absent)}}},
            }}}), encoding="utf-8")
            with self.assertRaises(sut.SynthesisError):
                sut.bind_owners(qrp_root=self.owners / "public-qrp", tool_registry=registry)


if __name__ == "__main__":
    unittest.main()
