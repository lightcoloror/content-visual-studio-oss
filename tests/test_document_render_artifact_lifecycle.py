from __future__ import annotations

import json
import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts import document_render_artifact_lifecycle as adapter
from temp_workspace import isolated_test_directory

CORE_ROOT = os.environ.get("ARTIFACT_LIFECYCLE_CORE_ROOT")
FIXTURE_ROOT = ROOT / "fixtures" / "artifact-lifecycle" / "synthetic-render-root"


@unittest.skipUnless(CORE_ROOT, "ARTIFACT_LIFECYCLE_CORE_ROOT is not set; native Artifact Core not supplied")
class DocumentRenderArtifactLifecycleTests(unittest.TestCase):
    def make_root(self):
        temporary = self.enterContext(isolated_test_directory("artifact-lifecycle"))
        root = temporary / "render-root"
        shutil.copytree(FIXTURE_ROOT, root)
        return root, temporary

    def scan(self, root, work, name="manifest.json"):
        return adapter.scan(
            root,
            closure_run_id="closure-run-synthetic-document-render-v1",
            output=root.parent / name,
            checkpoint=root.parent / (name + ".sqlite3"),
            synthetic_test_mode=True,
            core_root=CORE_ROOT,
            work_root=work,
        )

    def make_quarantine_root(self, root):
        quarantine = root.parent / "quarantine"
        quarantine.mkdir()
        return quarantine

    def test_scan_enriches_candidate_and_protects_final(self):
        root, work = self.make_root()
        manifest = self.scan(root, work)
        by_path = {item["path"]: item for item in manifest["artifacts"]}
        self.assertEqual(by_path["candidate/preview.html"]["candidate_kind"], "rebuildable_intermediate")
        self.assertFalse(by_path["candidate/preview.html"]["pin"])
        self.assertEqual(by_path["final/publish-ready.html"]["artifact_role"], "final_deliverable")
        self.assertTrue(by_path["final/publish-ready.html"]["pin"])
        self.assertEqual(manifest["cleanup_mode"], "plan_only")
        self.assertFalse(manifest["automatic_purge"])
        self.assertEqual(manifest["content_studio_adapter"]["core_profile_sha256"],
                         adapter.config()["core_contract"]["profile_sha256"])

    def test_unknown_path_is_pinned_and_unavailable_for_cleanup(self):
        root, work = self.make_root()
        unknown = root / "intermediate" / "unclassified.tmp"
        unknown.parent.mkdir()
        unknown.write_text("synthetic unknown", encoding="utf-8")
        manifest = self.scan(root, work)
        item = next(item for item in manifest["artifacts"] if item["path"] == "intermediate/unclassified.tmp")
        self.assertTrue(item["pin"])
        self.assertEqual(item["sensitivity"], "unknown")
        self.assertIn("unknown-classification", item["referenced_by"])
        self.assertIn("artifact_pinned", adapter.explain(manifest, item["artifact_id"], core_root=CORE_ROOT)["blocking_gates"])

    def test_path_traversal_classification_fails_closed(self):
        root, work = self.make_root()
        classification = root / "artifact-classification.v1.json"
        value = json.loads(classification.read_text(encoding="utf-8"))
        value["artifacts"]["../outside.txt"] = value["artifacts"]["candidate/preview.html"]
        classification.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(adapter.AdapterError, "CLASSIFICATION_PATH_OUTSIDE_ROOT"):
            self.scan(root, work)

    def test_root_without_marker_or_admission_fails_closed(self):
        root, work = self.make_root()
        (root / ".content-studio-synthetic-artifact-root.v1.json").unlink()
        with self.assertRaisesRegex(adapter.AdapterError, "JSON_READ_FAILED"):
            self.scan(root, work)
        with isolated_test_directory("artifact-lifecycle-unadmitted") as unadmitted:
            with self.assertRaisesRegex(adapter.AdapterError, "ROOT_NOT_ADMITTED"):
                adapter.assert_admitted_root(unadmitted, adapter.config(), synthetic_test_mode=False)

    def test_dirty_workspace_owner_process_and_dispatch_all_block(self):
        root, work = self.make_root()
        manifest = self.scan(root, work)
        quarantine = self.make_quarantine_root(root)
        dirty = adapter.plan_gc(
            manifest, root=root, quarantine_root=quarantine,
            owner_state="idle_confirmed", process_state="idle_confirmed", dispatch_state="none_active",
            synthetic_test_mode=True, workspace_git_state="dirty", core_root=CORE_ROOT, work_root=work,
        )
        self.assertFalse(any(item["eligible"] for item in dirty["entries"]))
        self.assertIn("content_studio_git_dirty_or_unknown", dirty["entries"][0]["blocking_gates"])
        active = adapter.plan_gc(
            manifest, root=root, quarantine_root=quarantine,
            owner_state="idle_confirmed", process_state="active", dispatch_state="active",
            synthetic_test_mode=True, workspace_git_state="clean", core_root=CORE_ROOT, work_root=work,
        )
        candidate = next(item for item in active["entries"]
                         if item["artifact_id"] == next(a["artifact_id"] for a in manifest["artifacts"]
                                                        if a["path"] == "candidate/preview.html"))
        self.assertFalse(candidate["eligible"])
        self.assertIn("active_process_not_cleared", candidate["blocking_gates"])
        self.assertIn("dispatch_not_cleared", candidate["blocking_gates"])

    def test_plan_verify_and_artifact_drift(self):
        root, work = self.make_root()
        manifest = self.scan(root, work)
        quarantine = self.make_quarantine_root(root)
        plan = adapter.plan_gc(
            manifest, root=root, quarantine_root=quarantine,
            owner_state="idle_confirmed", process_state="idle_confirmed", dispatch_state="none_active",
            synthetic_test_mode=True, workspace_git_state="clean", core_root=CORE_ROOT, work_root=work,
        )
        self.assertTrue(any(item["eligible"] for item in plan["entries"]))
        self.assertTrue(adapter.verify(plan, manifest, root=root, quarantine_root=quarantine,
                                       synthetic_test_mode=True, core_root=CORE_ROOT, work_root=work)["ok"])
        (root / "candidate" / "preview.html").write_text("drift", encoding="utf-8")
        result = adapter.verify(plan, manifest, root=root, quarantine_root=quarantine,
                                synthetic_test_mode=True, core_root=CORE_ROOT, work_root=work)
        self.assertFalse(result["ok"])
        self.assertTrue(any(error.startswith("artifact_digest_drift:") for error in result["errors"]))

    def test_cross_volume_plan_fails_closed(self):
        root, work = self.make_root()
        manifest = self.scan(root, work)
        if Path("C:/").resolve().stat().st_dev == root.stat().st_dev:
            self.skipTest("C and D are the same volume in this environment")
        with self.assertRaises(Exception):
            adapter.plan_gc(
                manifest, root=root, quarantine_root=Path("C:/"),
                owner_state="idle_confirmed", process_state="idle_confirmed", dispatch_state="none_active",
                synthetic_test_mode=True, workspace_git_state="clean", core_root=CORE_ROOT, work_root=work,
            )

    def test_reparse_point_is_blocked_before_scan(self):
        root, work = self.make_root()
        core = adapter.core_module(adapter.config(), CORE_ROOT)
        original = core._is_reparse

        def simulated_reparse(path: Path) -> bool:
            return path.name == "candidate" or original(path)

        with patch.object(adapter, "core_module", return_value=core), \
                patch.object(core, "_is_reparse", side_effect=simulated_reparse):
            with self.assertRaisesRegex(Exception, "REPARSE_POINT_BLOCKED"):
                self.scan(root, work)

    def test_hardlink_coverage_incomplete_blocks_candidate(self):
        root, work = self.make_root()
        source = root / "candidate" / "preview.html"
        external_link = root.parent / "outside-hardlink.html"
        try:
            os.link(source, external_link)
        except OSError as exc:
            self.skipTest(f"hardlink unavailable: {exc}")
        manifest = self.scan(root, work)
        quarantine = self.make_quarantine_root(root)
        plan = adapter.plan_gc(
            manifest, root=root, quarantine_root=quarantine,
            owner_state="idle_confirmed", process_state="idle_confirmed", dispatch_state="none_active",
            synthetic_test_mode=True, workspace_git_state="clean", core_root=CORE_ROOT, work_root=work,
        )
        candidate = next(item for item in plan["entries"] if item["source_path"].endswith("candidate\\preview.html"))
        self.assertFalse(candidate["eligible"])
        self.assertIn("hardlink_coverage_incomplete", candidate["blocking_gates"])

    def test_double_scan_is_idempotent(self):
        root, work = self.make_root()
        first = self.scan(root, work, "first.json")
        second = adapter.scan(
            root,
            closure_run_id="closure-run-synthetic-document-render-v1",
            output=root.parent / "second.json",
            checkpoint=root.parent / "first.json.sqlite3",
            synthetic_test_mode=True, core_root=CORE_ROOT, work_root=work,
        )
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
        self.assertEqual(first["artifacts"], second["artifacts"])

    def test_synthetic_restore_requires_marker_and_round_trips(self):
        root, work = self.make_root()
        manifest = self.scan(root, work)
        quarantine = self.make_quarantine_root(root)
        plan = adapter.plan_gc(
            manifest, root=root, quarantine_root=quarantine,
            owner_state="idle_confirmed", process_state="idle_confirmed", dispatch_state="none_active",
            synthetic_test_mode=True, workspace_git_state="clean", core_root=CORE_ROOT, work_root=work,
        )
        core = adapter.core_module(adapter.config(), CORE_ROOT)
        approval = core.attach_hash({
            "schema_version": "artifact-lifecycle-approval.v1",
            "approved": True,
            "operation": "quarantine",
            "plan_sha256": plan["plan_sha256"],
            "approved_by": "synthetic-test-only",
            "approved_at": "2026-08-29T00:00:00Z",
            "expires_at": "2099-01-01T00:00:00Z",
        }, "approval_sha256")
        receipt = core.apply_quarantine(plan, manifest, root, quarantine, approval,
                                        root.parent / "quarantine-receipt.json")
        self.assertFalse((root / "candidate" / "preview.html").exists())
        result = adapter.restore_synthetic(
            plan=plan, receipt=receipt, root=root, quarantine_root=quarantine,
            output=root.parent / "restore-receipt.json", synthetic_test_mode=True,
            core_root=CORE_ROOT, work_root=work,
        )
        self.assertEqual(result["operation"], "restore")
        self.assertTrue((root / "candidate" / "preview.html").exists())
        with self.assertRaisesRegex(adapter.AdapterError, "SYNTHETIC_RESTORE_FLAG_REQUIRED"):
            adapter.restore_synthetic(plan=plan, receipt=receipt, root=root, quarantine_root=quarantine,
                                      output=root.parent / "blocked.json", core_root=CORE_ROOT, work_root=work)

    def test_doctor_uses_shared_absolute_disk_policy_and_requires_large_estimate(self):
        root, work = self.make_root()
        result = adapter.doctor(root, synthetic_test_mode=True, core_root=CORE_ROOT, work_root=work)
        self.assertEqual(result["cleanup_mode"], "plan_only")
        self.assertFalse(result["filesystem_mutation_performed"])
        self.assertEqual(result["large_render_preflight"], "blocked_missing_estimate")
        self.assertIn("estimated_output_required", result["reason_codes"])
        self.assertIsNone(result["disk"]["minimum_free_ratio"])
        self.assertEqual(result["shared_disk_policy"]["minimum_free_bytes"], 512 * 1024 * 1024)
        self.assertEqual(result["shared_disk_policy"]["warning_free_bytes"], 5 * 1024 * 1024 * 1024)
        self.assertEqual(result["shared_disk_policy"]["output_headroom_multiplier"], 1.25)

    def test_two_gib_warning_allows_small_declared_output_but_blocks_unaffordable_output(self):
        root, work = self.make_root()
        core = adapter.core_module(adapter.config(), CORE_ROOT)
        usage = shutil._ntuple_diskusage(100 * 1024**3, (100 * 1024**3) - (int(2.5 * 1024**3)), int(2.5 * 1024**3))
        with patch.object(adapter, "core_module", return_value=core), \
                patch.object(core.shutil, "disk_usage", return_value=usage):
            allowed = adapter.doctor(root, operation_class="large", estimated_output_bytes=64 * 1024**2,
                                     synthetic_test_mode=True, core_root=CORE_ROOT, work_root=work)
            blocked = adapter.doctor(root, operation_class="large", estimated_output_bytes=2 * 1024**3,
                                     synthetic_test_mode=True, core_root=CORE_ROOT, work_root=work)
        self.assertEqual(allowed["status"], "ready")
        self.assertEqual(allowed["disk"]["status"], "low_disk_allowed")
        self.assertEqual(allowed["large_render_preflight"], "allowed_with_warning")
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["disk"]["status"], "blocked_low_disk")
        self.assertEqual(blocked["large_render_preflight"], "blocked")

    def test_config_has_no_legacy_ratio_gate(self):
        cfg = adapter.config()
        self.assertNotIn("minimum_free_ratio", cfg)
        self.assertNotIn("large_artifact_bytes", cfg)
        self.assertEqual(cfg["disk_policy"]["source"], "shared_core_profile")

    def test_missing_core_root_blocks(self):
        cfg = adapter.config()
        with patch.dict(os.environ, {"ARTIFACT_LIFECYCLE_CORE_ROOT": ""}):
            with self.assertRaisesRegex(adapter.AdapterError, "CORE_ROOT_REQUIRED"):
                adapter._core_root(cfg)

    def test_missing_work_root_blocks_synthetic_admission(self):
        root = self.enterContext(isolated_test_directory("artifact-lifecycle-work")) / "render-root"
        shutil.copytree(FIXTURE_ROOT, root)
        with patch.dict(os.environ, {"CONTENT_STUDIO_ARTIFACT_WORK_ROOT": ""}):
            with self.assertRaisesRegex(adapter.AdapterError, "WORK_ROOT_REQUIRED"):
                adapter.assert_admitted_root(root, adapter.config(), synthetic_test_mode=True)

    def test_core_api_hash_drift_blocks(self):
        root, work = self.make_root()
        with isolated_test_directory("artifact-lifecycle-core-copy") as temporary:
            (temporary / "profiles").mkdir()
            (temporary / "artifact_lifecycle_core.py").write_text("# tampered synthetic copy\n", encoding="utf-8")
            shutil.copy2(Path(CORE_ROOT) / "profiles/artifact-lifecycle-profiles.v1.json",
                         temporary / "profiles/artifact-lifecycle-profiles.v1.json")
            with self.assertRaisesRegex(adapter.AdapterError, "CORE_API_HASH_DRIFT"):
                adapter._core_root(adapter.config(), temporary)

    def test_plan_must_not_authorize_mutation(self):
        root, work = self.make_root()
        manifest = self.scan(root, work)
        quarantine = self.make_quarantine_root(root)
        plan = adapter.plan_gc(
            manifest, root=root, quarantine_root=quarantine,
            owner_state="idle_confirmed", process_state="idle_confirmed", dispatch_state="none_active",
            synthetic_test_mode=True, workspace_git_state="clean", core_root=CORE_ROOT, work_root=work,
        )
        plan["content_studio_adapter"]["filesystem_mutation_authorized"] = True
        result = adapter.verify(plan, manifest, root=root, quarantine_root=quarantine,
                                synthetic_test_mode=True, core_root=CORE_ROOT, work_root=work)
        self.assertFalse(result["ok"])
        self.assertIn("plan_must_not_authorize_mutation", result["errors"])

    def test_process_probe_access_failure_is_fail_closed(self):
        with patch("scripts.document_render_artifact_lifecycle.subprocess.run", side_effect=OSError("denied")):
            probe = adapter._process_probe()
        self.assertEqual(probe["state"], "unknown")

    def test_production_cli_has_no_quarantine_or_purge_outlet(self):
        with self.assertRaises(SystemExit):
            adapter.main(["apply-quarantine"])
        with self.assertRaises(SystemExit):
            adapter.main(["apply-purge"])

    def test_adapter_sources_contain_no_personal_path_or_secret_literal(self):
        files = [
            Path(adapter.__file__),
            adapter.CONFIG_PATH,
            FIXTURE_ROOT / "artifact-classification.v1.json",
        ]
        forbidden = ("C:/Users/", "C:\\\\Users\\\\", "ghp_", "sk-", "Bearer ")
        for path in files:
            text = path.read_text(encoding="utf-8")
            self.assertFalse(any(value in text for value in forbidden), path)


if __name__ == "__main__":
    unittest.main()
