"""Bounded synthetic acceptance; retained test artifacts, no cleanup or rendering."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import qrp_candidate_adapter as q

WORKSPACE = Path(__file__).resolve().parents[1]
SOURCE = WORKSPACE / "fixtures/qrp-candidate-pack"
EXPECTED = "2ce9907c8567dc10566846b478232e207f55fc158028bd1160a7460fcd4a108f"


class CandidateTests(unittest.TestCase):
    def setUp(self):
        # Only files explicitly indexed by the reviewed synthetic pack are copied.
        self.root = Path(os.environ["CONTENT_CANDIDATE_TEST_ROOT"]) / (self._testMethodName + "-" + uuid4().hex)
        self.root.mkdir(parents=True)
        p = q.adapter.load_json(SOURCE / "offline-evidence-brief.v1.json")
        self.assertEqual(q.digest(SOURCE / "offline-evidence-brief.v1.json"), EXPECTED)
        files = ["offline-evidence-brief.v1.json", p["core"]["manifest_path"], p["projection_receipt"]["path"]]
        files += [r["path"] for r in p["deliverables"]]
        for r in p["core"]["stage_receipts"]:
            files += [r["path"], r["artifact_path"]]
        for name in files:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((SOURCE / name).read_bytes())
        self.pack = self.root / "offline-evidence-brief.v1.json"

    def run_conversion(self, expected=None):
        return q.convert_pack(self.pack, expected or EXPECTED, allow_unverified_draft=True)

    def mutate(self, name, fn):
        p = self.root / name
        value = q.adapter.load_json(p)
        fn(value)
        p.write_text(q.adapter._json_text(value), encoding="utf-8")

    def resign_projection(self):
        p = q.adapter.load_json(self.pack)
        for row in p["deliverables"]:
            row["sha256"] = q.digest(self.root / row["path"])
        rp = self.root / p["projection_receipt"]["path"]
        r = q.adapter.load_json(rp)
        r["artifacts"] = p["deliverables"]
        rp.write_text(q.adapter._json_text(r), encoding="utf-8")
        p["projection_receipt"]["sha256"] = q.digest(rp)
        self.pack.write_text(q.adapter._json_text(p), encoding="utf-8")
        return q.digest(self.pack)

    def rejected(self, code, expected=None):
        with self.assertRaises(q.adapter.AdapterError) as caught:
            self.run_conversion(expected)
        self.assertEqual(caught.exception.code, code)

    def test_candidate_schema_and_boundaries(self):
        item, body, manifest = self.run_conversion()
        self.assertEqual(item["status"], "candidate")
        self.assertEqual(item["channels"]["article"]["status"], "draft")
        self.assertEqual(item["gates"]["fact"]["status"], "blocked")
        self.assertEqual(item["provenance"]["verified_facts"], [])
        self.assertTrue(all(x["evidence_status"] == "unverified" for x in item["provenance"]["sources"]))
        self.assertEqual(item["publication"], {"boundary": "manual-only", "receipts": []})
        self.assertEqual(item["qa"]["human_review"]["status"], "required")
        binding = item["channels"]["article"]["platform_metadata"]["qrp_candidate_binding"]
        self.assertEqual(binding["input_sha256"], manifest["input_sha256"])
        self.assertEqual(binding["closure_run_id"], manifest["closure_run_id"])

    def test_unknown_and_contradiction_preserved(self):
        item, body, _ = self.run_conversion()
        b = q.adapter.load_json(self.root / "deliverables/content-brief.v1.json")
        kept = item["channels"]["article"]["platform_metadata"]["qrp_candidate_binding"]["brief"]
        self.assertEqual(kept, b)
        self.assertIn("claim-single-sufficient", body)
        self.assertIn("claim-cause", json.dumps(item))

    def test_explicit_candidate_opt_in(self):
        with self.assertRaises(q.adapter.AdapterError) as caught:
            q.convert_pack(self.pack, EXPECTED)
        self.assertEqual(caught.exception.code, "candidate_opt_in_required")

    def test_verified_default_still_rejects(self):
        r = q.adapter.load_json(self.root / "deliverables/evidence-bundle.v1.json")
        with self.assertRaises(q.adapter.AdapterError) as caught:
            q.adapter.validate_research_semantics(r)
        self.assertEqual(caught.exception.code, "guarded_answer_not_verified")

    def test_schema_version_mismatch(self):
        self.mutate("offline-evidence-brief.v1.json", lambda p: p.update(schema_version="2.0.0"))
        self.rejected("pack_version_unsupported", q.digest(self.pack))

    def test_native_schema_version_mismatch(self):
        self.mutate("deliverables/content-brief.v1.json", lambda p: p.update(native_contract="unknown.v2"))
        self.rejected("brief_version_unsupported", self.resign_projection())

    def test_input_hash_drift(self):
        self.mutate("deliverables/evidence-bundle.v1.json", lambda p: p.update(question="changed"))
        self.rejected("input_or_receipt_hash_drift")

    def test_receipt_hash_drift(self):
        self.mutate("receipts/02-source_admission.json", lambda p: p.update(input_sha256="0" * 64))
        self.rejected("input_or_receipt_hash_drift")

    def test_projection_receipt_drift(self):
        self.mutate("deliverables/projection-receipt.v1.json", lambda p: p.update(status="published"))
        self.rejected("input_or_receipt_hash_drift")

    def test_pack_hash_drift(self):
        self.mutate("offline-evidence-brief.v1.json", lambda p: p.update(status="published"))
        self.rejected("pack_hash_drift")

    def test_input_path_escape(self):
        self.mutate("offline-evidence-brief.v1.json", lambda p: p["core"].update(manifest_path="../outside.json"))
        self.rejected("input_path_escape", q.digest(self.pack))

    def test_sensitive_unknown_stays_blocked(self):
        research = q.adapter.load_json(self.root / "deliverables/evidence-bundle.v1.json")
        research["unknowns"].append({"code": "privacy", "message": "unredacted sensitive data", "severity": "blocker"})
        with self.assertRaises(q.adapter.AdapterError) as caught:
            q.adapter.validate_unverified_draft_semantics(research)
        self.assertEqual(caught.exception.code, "sensitive_content_blocked")

    def test_missing_evidence(self):
        self.mutate("deliverables/evidence-bundle.v1.json", lambda p: p.update(evidence=[]))
        self.rejected("evidence_link_mismatch", self.resign_projection())

    def test_publish_attempt(self):
        self.mutate("deliverables/content-brief.v1.json", lambda p: p.update(status="published"))
        self.rejected("authority_escalation", self.resign_projection())

    def test_recommendation_upgrade(self):
        self.mutate("deliverables/content-brief.v1.json", lambda p: p["authority"].update(publish_authorized=True))
        self.rejected("authority_escalation", self.resign_projection())

    def test_closure_drift(self):
        self.mutate("deliverables/content-brief.v1.json", lambda p: p.update(closure_run_id="different"))
        self.rejected("closure_binding_drift", self.resign_projection())

    def test_no_model_browser_or_renderer_dependency(self):
        with patch.object(q.adapter, "render_article_html", side_effect=RuntimeError("renderer unavailable")), \
             patch("socket.create_connection", side_effect=RuntimeError("model/network unavailable")):
            item, _, _ = self.run_conversion()
        self.assertEqual(item["status"], "candidate")

    def test_double_run_identical(self):
        self.assertEqual(self.run_conversion(), self.run_conversion())

    def test_partial_output_recovery(self):
        item, body, manifest = self.run_conversion()
        output = self.root / "converted"
        output.mkdir()
        (output / "article.md").write_bytes(body.encode())
        result = q.write_conversion(self.pack, EXPECTED, output, allow_unverified_draft=True)
        self.assertEqual(result["input_sha256"], manifest["input_sha256"])
        self.assertTrue((output / "conversion-manifest.json").exists())
        self.assertEqual(result, q.write_conversion(self.pack, EXPECTED, output, allow_unverified_draft=True))

    def test_output_drift_no_overwrite(self):
        output = self.root / "converted"
        output.mkdir()
        (output / "article.md").write_bytes(b"changed")
        with self.assertRaises(q.adapter.AdapterError) as caught:
            q.write_conversion(self.pack, EXPECTED, output, allow_unverified_draft=True)
        self.assertEqual(caught.exception.code, "output_hash_drift")
        self.assertEqual((output / "article.md").read_bytes(), b"changed")
        self.assertFalse((output / "content-item.json").exists())


if __name__ == "__main__":
    unittest.main()
