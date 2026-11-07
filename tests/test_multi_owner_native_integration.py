"""Native multi-owner synthetic integration for the two candidate adapters.

This is the executable integration plan: it copies the supplied public QRP/Main/
Artifact owner bytes into a throw-away workspace, generates a brand-new fictional
offline QRP pack, runs the synthesis adapter through the real Main consistency
gate (text-only and HTML), then runs the real Artifact Core scan/plan/verify over
a marker-bound synthetic render root. No real output, manuscript, customer data,
service or network is used.

Required explicit roots:
  CONTENT_STUDIO_PUBLIC_OWNERS_ROOT - directory containing public-qrp/,
                                      public-main/ and public-lifecycle/
The test is skipped with that reason when the roots are absent; a skip is not a
pass and never substitutes a mock for an owner.
"""
from __future__ import annotations

import copy
import importlib
import json
import os
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import document_render_artifact_lifecycle as lifecycle
import original_synthesis_adapter as synthesis
from temp_workspace import isolated_test_directory, prepare_test_temp_root

FIXTURES = ROOT / "fixtures" / "synthesis-lifecycle"
UPSTREAM = FIXTURES / "upstream"
ARTIFACT_FIXTURE = ROOT / "fixtures" / "artifact-lifecycle" / "synthetic-render-root"
OWNERS = os.environ.get("CONTENT_STUDIO_PUBLIC_OWNERS_ROOT")
CORE_ROOT = os.environ.get("ARTIFACT_LIFECYCLE_CORE_ROOT")


def sha_bytes(path):
    return synthesis.sha(Path(path).read_bytes())


def copy_owner_tree(source, destination):
    shutil.copytree(source, destination)


class NativeMultiOwnerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not OWNERS:
            raise unittest.SkipTest("CONTENT_STUDIO_PUBLIC_OWNERS_ROOT is not set; public owners not supplied")
        cls.owners = Path(OWNERS).resolve()
        qrp = cls.owners / "public-qrp"
        main = cls.owners / "public-main" / "self-media-creation-system"
        core = Path(CORE_ROOT).resolve() if CORE_ROOT else cls.owners / "public-lifecycle"
        cls.core_root = core
        if not (qrp / "src/question_research_poc/bounded_deep_loop.py").is_file():
            raise unittest.SkipTest("public-qrp source missing under CONTENT_STUDIO_PUBLIC_OWNERS_ROOT")
        if not (main / "scripts/cross_platform_fact_consistency_gate.py").is_file():
            raise unittest.SkipTest("public-main gate missing under CONTENT_STUDIO_PUBLIC_OWNERS_ROOT")
        if not (core / "artifact_lifecycle_core.py").is_file():
            raise unittest.SkipTest("public-lifecycle core missing; set ARTIFACT_LIFECYCLE_CORE_ROOT")

        cls.temp = prepare_test_temp_root() / f"multi-owner-{os.getpid()}"
        cls.workspace = cls.temp / "workspace"
        cls.workspace.mkdir(parents=True)
        copy_owner_tree(main, cls.workspace / "self-media-creation-system")
        copy_owner_tree(qrp, cls.workspace / "question-research-poc")
        cls.registry = cls.workspace / "tool-registry.json"
        cls.registry.write_text(json.dumps({"tools": {"content-creation-system": {
            "self_media_path": str(cls.workspace / "self-media-creation-system"),
            "runtime_main": {"repositories": {"self": {
                "path": str(cls.workspace / "self-media-creation-system")}}},
        }}}), encoding="utf-8")
        cls.qrp, cls.core, cls.gate = synthesis.bind_owners(
            qrp_root=cls.workspace / "question-research-poc", tool_registry=cls.registry)

        # Fresh fictional pack produced by the real public QRP offline API.
        off = importlib.import_module("question_research_poc.offline_evidence_brief")
        result = off.run_offline_evidence_brief(
            UPSTREAM / "public-input.json", cls.temp / "pack-out",
            closure_run_id="synthetic-multi-owner-field-notes-001")
        if result.get("projection_status") != "complete_candidate_only":
            raise AssertionError(f"QRP projection did not complete: {result}")
        cls.pack_path = Path(result["manifest_path"])
        cls.pack_sha = sha_bytes(cls.pack_path)
        cls.plan_path = FIXTURES / "editorial-plan.json"
        cls.plan_sha = sha_bytes(cls.plan_path)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "temp", None), ignore_errors=True)

    def run_synthesis(self, name, *, text_only):
        output = self.workspace / "output" / name
        result = synthesis.run(
            self.plan_path, self.plan_sha, self.pack_path, self.pack_sha, UPSTREAM, output,
            text_only=text_only, workspace_root=self.workspace,
            qrp_root=self.workspace / "question-research-poc", tool_registry=self.registry)
        return output, result

    def test_owner_copies_match_public_bytes(self):
        pairs = [
            (self.workspace / "self-media-creation-system/scripts/cross_platform_fact_consistency_gate.py",
             self.owners / "public-main/self-media-creation-system/scripts/cross_platform_fact_consistency_gate.py"),
            (self.workspace / "question-research-poc/src/question_research_poc/bounded_deep_loop.py",
             self.owners / "public-qrp/src/question_research_poc/bounded_deep_loop.py"),
            (self.workspace / "self-media-creation-system/scripts/self_media_agent.py",
             self.owners / "public-main/self-media-creation-system/scripts/self_media_agent.py"),
        ]
        for copied, original in pairs:
            self.assertTrue(copied.is_file(), copied)
            self.assertEqual(sha_bytes(copied), sha_bytes(original), copied)
        public_lifecycle = self.owners / "public-lifecycle"
        if public_lifecycle.is_dir():
            self.assertEqual(sha_bytes(self.core_root / "artifact_lifecycle_core.py"),
                             sha_bytes(public_lifecycle / "artifact_lifecycle_core.py"))
            self.assertEqual(
                sha_bytes(self.core_root / "profiles/artifact-lifecycle-profiles.v1.json"),
                sha_bytes(public_lifecycle / "profiles/artifact-lifecycle-profiles.v1.json"))
        config = json.loads((ROOT / "config/document-render-artifact-lifecycle.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(sha_bytes(self.core_root / "artifact_lifecycle_core.py"),
                         config["core_contract"]["api_sha256"])
        self.assertEqual(sha_bytes(self.core_root / "profiles/artifact-lifecycle-profiles.v1.json"),
                         config["core_contract"]["profile_sha256"])

    def test_text_only_and_html_runs(self):
        text_out, text_result = self.run_synthesis("text", text_only=True)
        html_out, html_result = self.run_synthesis("html", text_only=False)
        self.assertEqual(text_result["status"], "complete_candidate_only")
        self.assertEqual(html_result["status"], "complete_candidate_only")
        for output in (text_out, html_out):
            for name in ("article.md", "oral-script.md", "content-item.json", "fact-card.json",
                         "trace.json", "visual-plan.json", "review-packet.json",
                         "cross-platform-input.json", "consumer-index.json", "checkpoint.json"):
                self.assertTrue((output / name).is_file(), name)
        self.assertFalse((text_out / "article.html").exists())
        self.assertTrue((html_out / "article.html").is_file())
        html = (html_out / "article.html").read_text(encoding="utf-8")
        self.assertIn("<!doctype html>", html.lower())
        self.assertIn("A fictional offline index keeps one reviewed trail", html)
        self.assertEqual((text_out / "article.md").read_bytes(), (html_out / "article.md").read_bytes())
        self.assertEqual((text_out / "oral-script.md").read_bytes(), (html_out / "oral-script.md").read_bytes())

        consumer = json.loads((text_out / "consumer-index.json").read_text(encoding="utf-8"))
        self.assertIs(consumer["text_only"], True)
        self.assertIs(consumer["publication_authorized"], False)
        listed = {row["path"]: row["sha256"] for row in consumer["artifacts"]}
        for name, expected in listed.items():
            self.assertEqual(sha_bytes(text_out / name), expected, name)
        review = json.loads((html_out / "review-packet.json").read_text(encoding="utf-8"))
        self.assertEqual(review["status"], "pending_human_review")
        self.assertIs(review["publication_authorized"], False)
        self.assertEqual(review["canonical_status"], "draft")
        card = json.loads((html_out / "fact-card.json").read_text(encoding="utf-8"))
        self.assertIs(card["synthetic_only"], True)
        self.assertEqual(card["canonical_status"], "draft")
        self.assertEqual(card["gates"]["fact"], "needs-review")
        self.assertEqual(review["consistency_receipt"], html_result["consistency_receipt"])
        receipt = Path(html_result["consistency_receipt"])
        self.assertTrue(receipt.is_file())
        self.assertTrue(receipt.resolve().is_relative_to(self.workspace))
        self.assertEqual(receipt, Path(review["consistency_receipt"]))
        self.gate.validate_receipt(synthesis.read(receipt))

    def test_main_gate_rejects_cross_platform_claim_hash_drift(self):
        output, _ = self.run_synthesis("gate-negative", text_only=True)
        value = json.loads((output / "cross-platform-input.json").read_text(encoding="utf-8"))
        drifted = copy.deepcopy(value)
        drifted["variants"][1]["claims"][0]["normalized_claim_sha256"] = "0" * 64
        with self.assertRaises(self.gate.CrossPlatformFactError) as caught:
            self.gate.validate_input(drifted)
        self.assertEqual(caught.exception.code, "cross_platform_claim_drift")
        self.assertEqual(self.gate.validate_input(value)["content_family_id"], value["content_family_id"])

    def test_plan_and_pack_hashes_are_enforced_before_writes(self):
        output = self.workspace / "output" / "bad-plan"
        with self.assertRaises(synthesis.SynthesisError) as caught:
            synthesis.run(self.plan_path, "0" * 64, self.pack_path, self.pack_sha, UPSTREAM, output,
                          text_only=True, workspace_root=self.workspace,
                          qrp_root=self.workspace / "question-research-poc", tool_registry=self.registry)
        self.assertEqual(caught.exception.code, "plan_hash_drift")
        self.assertFalse(output.exists())
        with self.assertRaises(Exception) as pack_caught:
            synthesis.run(self.plan_path, self.plan_sha, self.pack_path, "0" * 64, UPSTREAM, output,
                          text_only=True, workspace_root=self.workspace,
                          qrp_root=self.workspace / "question-research-poc", tool_registry=self.registry)
        self.assertEqual(getattr(pack_caught.exception, "code", ""), "pack_hash_drift")

    def test_output_must_stay_inside_explicit_workspace(self):
        with self.assertRaisesRegex(synthesis.SynthesisError, "output_path_escape"):
            synthesis.run(self.plan_path, self.plan_sha, self.pack_path, self.pack_sha, UPSTREAM,
                          self.temp / "outside", text_only=True, workspace_root=self.workspace,
                          qrp_root=self.workspace / "question-research-poc", tool_registry=self.registry)

    def test_missing_owner_roots_block(self):
        with self.assertRaises(synthesis.SynthesisError):
            synthesis.bind_owners(qrp_root=self.temp / "no-qrp")
        with isolated_test_directory("missing-main-owner") as temporary:
            registry = temporary / "tool-registry.json"
            absent = temporary / "no-main"
            registry.write_text(json.dumps({"tools": {"content-creation-system": {
                "self_media_path": str(absent),
                "runtime_main": {"repositories": {"self": {"path": str(absent)}}},
            }}}), encoding="utf-8")
            with self.assertRaises(synthesis.SynthesisError):
                synthesis.bind_owners(qrp_root=self.workspace / "question-research-poc",
                                      tool_registry=registry)

    def test_lifecycle_scan_plan_verify_on_synthetic_render_root(self):
        render_root = self.workspace / "output" / "render-root"
        shutil.copytree(ARTIFACT_FIXTURE, render_root)
        html_out, _ = self.run_synthesis("lifecycle-source", text_only=False)
        shutil.copy2(html_out / "article.html", render_root / "candidate" / "preview.html")
        checkpoint = self.workspace / "output" / "lifecycle.sqlite3"
        manifest = lifecycle.scan(
            render_root, closure_run_id="synthetic-lifecycle-multi-owner-001",
            output=self.workspace / "output" / "lifecycle-manifest.json", checkpoint=checkpoint,
            synthetic_test_mode=True, core_root=self.core_root, work_root=self.workspace)
        self.assertEqual(manifest["cleanup_mode"], "plan_only")
        self.assertFalse(manifest["automatic_purge"])
        quarantine = self.workspace / "output" / "quarantine"
        quarantine.mkdir()
        plan = lifecycle.plan_gc(
            manifest, root=render_root, quarantine_root=quarantine,
            owner_state="idle_confirmed", process_state="idle_confirmed", dispatch_state="none_active",
            synthetic_test_mode=True, workspace_git_state="clean",
            core_root=self.core_root, work_root=self.workspace)
        self.assertEqual(plan["authorization_state"], "not_authorized")
        self.assertFalse(plan["content_studio_adapter"]["filesystem_mutation_authorized"])
        verified = lifecycle.verify(plan, manifest, root=render_root, quarantine_root=quarantine,
                                    synthetic_test_mode=True, core_root=self.core_root, work_root=self.workspace)
        self.assertTrue(verified["ok"], verified["errors"])
        self.assertFalse(verified["filesystem_mutation_performed"])
        doctor = lifecycle.doctor(render_root, synthetic_test_mode=True,
                                  core_root=self.core_root, work_root=self.workspace)
        self.assertEqual(doctor["large_render_preflight"], "blocked_missing_estimate")
        self.assertEqual(doctor["shared_disk_policy"]["minimum_free_bytes"], 512 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
