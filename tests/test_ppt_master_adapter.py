from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from render_artifact_validation import validate_render_artifacts  # noqa: E402
from render_content_artifacts import (  # noqa: E402
    ArtifactError,
    _renderer_config,
)
from media_qa_validation import required_hard_checks  # noqa: E402
from temp_workspace import isolated_test_directory  # noqa: E402


BRIEF = (
    WORKSPACE
    / "local-deployments"
    / "ai-ppt-local"
    / "fixtures"
    / "brief-shared-design-system"
    / "brief.json"
)
V4_ROOT = (
    WORKSPACE
    / "source-reviews"
    / "ppt-master-20260811"
    / "source-v4.5.0"
)
EXPECTED_COMMIT = "ec824aecd551a0bc2990b617a131d907a5d808ea"
SOURCE_DECK = ROOT / "outputs" / "acceptance" / "ppt-master-v45-bridge" / "deck.pptx"
FILL_PLAN = (
    WORKSPACE
    / "local-deployments"
    / "ai-ppt-local"
    / "fixtures"
    / "template-fill-v45"
    / "fill_plan.json"
)
UNCONFIRMED_FILL_PLAN = (
    ROOT / "fixtures" / "ppt-master-v45" / "unconfirmed-fill-plan.json"
)
DATA_NATIVE_ITEM = (
    ROOT / "fixtures" / "ppt-master-v45" / "data-native-content-item.json"
)
DATA_SPEC = ROOT / "content" / "chart-specs" / "medical-insurance-fund-2025.json"


class PptMasterAdapterTests(unittest.TestCase):
    def artifact(self, output: Path, receipt: Path) -> dict:
        return {
            "artifact_id": "ppt-master-v45-deck",
            "output_family": "slide",
            "media_adapter": "pptx",
            "layout_intent": "comparison",
            "renderer": "ppt-master",
            "format": "pptx",
            "status": "planned",
            "input_refs": [str(BRIEF)],
            "asset_ids": [],
            "ref": str(output),
            "receipt_ref": str(receipt),
            "renderer_options": {
                "explicit_adapter": True,
                "ppt_master_protocol": "v4.5",
            },
        }

    def item(self, artifact: dict) -> dict:
        return {
            "content_id": "ppt-master-v45-fixture",
            "gates": {
                "fact": {"status": "pass"},
                "rights": {"status": "pass"},
                "privacy": {"status": "pass"},
            },
            "visual": {"assets": [], "render_artifacts": [artifact]},
        }

    def template_fill_artifact(self, output: Path, receipt: Path) -> dict:
        return {
            "artifact_id": "ppt-master-v45-template-fill",
            "output_family": "slide",
            "media_adapter": "pptx",
            "layout_intent": "comparison",
            "renderer": "ppt-master",
            "format": "pptx",
            "status": "planned",
            "input_refs": [str(SOURCE_DECK), str(FILL_PLAN)],
            "asset_ids": [],
            "ref": str(output),
            "receipt_ref": str(receipt),
            "qa_profile": "slide-pptx.v1",
            "renderer_options": {
                "explicit_adapter": True,
                "operation": "template-fill",
                "ppt_master_protocol": "v4.5",
                "template_fill_plan_confirmed": True,
            },
        }

    def test_registry_is_pinned_and_off_by_default(self) -> None:
        registry = json.loads(
            (ROOT / "config" / "renderer-registry.v1.json").read_text(encoding="utf-8")
        )["renderers"]["ppt-master"]
        self.assertFalse(registry["enabled"])
        self.assertEqual(registry["selection_policy"], "explicit-item-only")
        self.assertEqual(registry["commit"], EXPECTED_COMMIT)
        self.assertEqual(registry["protocol"], "v4.5")
        self.assertEqual(registry["operations"]["default"], "generate")
        self.assertEqual(
            registry["operations"]["allowed"],
            ["generate", "template-fill", "data-native"],
        )
        self.assertTrue(
            registry["operations"]["data-native"]["fallback_dependency_required"]
        )
        self.assertEqual(
            registry["operations"]["data-native"]["unsupported_mapping"],
            "fail-closed-to-svg",
        )
        self.assertFalse(registry["automatic_layout_selection"])
        self.assertTrue(Path(registry["compiled_profile_manifest"]).is_file())
        layout_registry = json.loads(
            Path(registry["layout_candidate_registry"]).read_text(encoding="utf-8")
        )
        self.assertFalse(layout_registry["policy"]["automatic_selection"])
        self.assertEqual(
            set(layout_registry["candidates"]), {"report_core", "xiaohongshu_post"}
        )
        self.assertTrue(registry["visual_validation_required"])
        artifact = self.artifact(Path("deck.pptx"), Path("deck.receipt.json"))
        artifact["renderer_options"]["explicit_adapter"] = False
        with self.assertRaisesRegex(ArtifactError, "off by default"):
            _renderer_config(artifact)

    def test_protocol_and_source_root_are_item_level_fail_closed(self) -> None:
        artifact = self.artifact(Path("deck.pptx"), Path("deck.receipt.json"))
        artifact["renderer_options"]["ppt_master_protocol"] = "auto"
        artifact["renderer_options"]["ppt_master_root"] = "D:/unreviewed"
        messages = [
            message
            for _, message in validate_render_artifacts(
                self.item(artifact), ROOT / "content" / "items" / "fixture.json"
            )
        ]
        self.assertTrue(any("explicitly select pinned protocol" in message for message in messages))
        self.assertTrue(any("registry-owned" in message for message in messages))

    def test_template_fill_requires_two_layers_of_confirmation(self) -> None:
        artifact = self.template_fill_artifact(
            Path("filled.pptx"), Path("filled.receipt.json")
        )
        _, required = required_hard_checks(artifact)
        self.assertTrue(
            {
                "fill-plan-confirmed",
                "fill-plan-capacity",
                "upstream-readback",
                "planned-targets-only",
                "template-structure-preserved",
            }.issubset(required)
        )
        self.assertNotIn("semantic-page-roles", required)
        artifact["renderer_options"]["template_fill_plan_confirmed"] = False
        messages = [
            message
            for _, message in validate_render_artifacts(
                self.item(artifact), ROOT / "content" / "items" / "fixture.json"
            )
        ]
        self.assertTrue(any("explicit plan review" in message for message in messages))

        artifact["renderer_options"]["template_fill_plan_confirmed"] = True
        artifact["input_refs"][1] = str(UNCONFIRMED_FILL_PLAN)
        messages = [
            message
            for _, message in validate_render_artifacts(
                self.item(artifact), ROOT / "content" / "items" / "fixture.json"
            )
        ]
        self.assertTrue(any("status must be confirmed" in message for message in messages))

    def test_data_native_requires_fallback_dependency_and_zero_baseline_gate(self) -> None:
        item = json.loads(DATA_NATIVE_ITEM.read_text(encoding="utf-8"))
        artifact = item["visual"]["render_artifacts"][1]
        _, required = required_hard_checks(artifact)
        self.assertTrue(
            {
                "data-spec-hash-match",
                "fallback-fresh",
                "native-projection-validated",
                "native-chart-present",
                "native-data-exact",
                "native-zero-baseline",
                "native-labels-exact",
            }.issubset(required)
        )
        self.assertEqual(validate_render_artifacts(item, DATA_NATIVE_ITEM), [])

        artifact["depends_on_artifact_ids"] = []
        messages = [
            message
            for _, message in validate_render_artifacts(item, DATA_NATIVE_ITEM)
        ]
        self.assertTrue(any("fallback_artifact_id" in message for message in messages))

    @unittest.skipUnless(
        os.environ.get("RUN_PPT_MASTER_INTEGRATION") == "1" and V4_ROOT.is_dir(),
        "set RUN_PPT_MASTER_INTEGRATION=1 for real PPT Master v4.5 generation",
    )
    def test_real_v45_render_produces_unified_receipt(self) -> None:
        with isolated_test_directory("ppt-master-adapter") as root:
            output = root / "deck.pptx"
            receipt_path = root / "deck.receipt.json"
            artifact = self.artifact(output, receipt_path)
            item = self.item(artifact)
            item_path = root / "item.json"
            item_path.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "render_content_artifacts.py"),
                    "render",
                    "--item",
                    str(item_path),
                    "--artifact-id",
                    artifact["artifact_id"],
                ],
                text=True,
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            receipt = json.loads(completed.stdout)

            self.assertEqual(receipt["renderer"], "ppt-master")
            self.assertEqual(receipt["source"]["commit"], EXPECTED_COMMIT)
            self.assertEqual(receipt["qa"]["profile_id"], "slide-pptx.v1")
            self.assertEqual(receipt["qa"]["result"], "review-required")
            self.assertTrue(
                all(check["status"] == "pass" for check in receipt["qa"]["hard_checks"]),
                receipt["qa"]["hard_checks"],
            )
            hard_check_names = {
                check["name"] for check in receipt["qa"]["hard_checks"]
            }
            self.assertTrue(
                {"structural-validation", "render-preview", "overflow"}.issubset(
                    hard_check_names
                )
            )
            self.assertEqual(validate_render_artifacts(item, item_path), [])

            manifest = json.loads(
                Path(str(output) + ".manifest.json").read_text(encoding="utf-8")
            )
            semantic = manifest["generation"]["semantic_structure"]
            self.assertTrue(semantic["all_pages_have_page_role"])
            self.assertEqual(semantic["logical_group_count"], 13)
            self.assertEqual(manifest["ppt_master_evidence"]["quality_status"]["warnings"], 0)
            self.assertEqual(manifest["ppt_master_evidence"]["postflight_status"], "passed")

    @unittest.skipUnless(
        os.environ.get("RUN_PPT_MASTER_INTEGRATION") == "1"
        and V4_ROOT.is_dir()
        and SOURCE_DECK.is_file(),
        "set RUN_PPT_MASTER_INTEGRATION=1 for real PPT Master template-fill",
    )
    def test_real_template_fill_changes_only_confirmed_target(self) -> None:
        with isolated_test_directory("ppt-master-adapter") as root:
            output = root / "filled.pptx"
            receipt_path = root / "filled.receipt.json"
            artifact = self.template_fill_artifact(output, receipt_path)
            item = self.item(artifact)
            item_path = root / "item.json"
            item_path.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "render_content_artifacts.py"),
                    "render",
                    "--item",
                    str(item_path),
                    "--artifact-id",
                    artifact["artifact_id"],
                ],
                text=True,
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            receipt = json.loads(completed.stdout)
            checks = {check["name"]: check for check in receipt["qa"]["hard_checks"]}
            for name in (
                "fill-plan-confirmed",
                "fill-plan-capacity",
                "upstream-readback",
                "planned-targets-only",
                "template-structure-preserved",
            ):
                self.assertEqual(checks[name]["status"], "pass", checks[name])
            self.assertNotIn("semantic-page-roles", checks)

            manifest = json.loads(
                Path(str(output) + ".manifest.json").read_text(encoding="utf-8")
            )
            audit = manifest["template_fill_evidence"]["text_target_audit"]
            self.assertTrue(audit["ok"])
            self.assertEqual(audit["planned_target_count"], 1)
            self.assertEqual(audit["actual_change_count"], 1)
            self.assertEqual(audit["unplanned_change_count"], 0)
            self.assertTrue(
                manifest["template_fill_evidence"]["template_structure_preserved"]
            )
            self.assertTrue(
                all(
                    manifest["template_fill_evidence"][
                        "template_structure_audit"
                    ].values()
                )
            )

    @unittest.skipUnless(
        os.environ.get("RUN_PPT_MASTER_INTEGRATION") == "1" and V4_ROOT.is_dir(),
        "set RUN_PPT_MASTER_INTEGRATION=1 for real native-data generation",
    )
    def test_real_data_native_round_trips_exact_values_and_zero_baseline(self) -> None:
        with isolated_test_directory("ppt-master-adapter") as root:
            item = json.loads(DATA_NATIVE_ITEM.read_text(encoding="utf-8"))
            fallback, native = item["visual"]["render_artifacts"]
            fallback["input_refs"] = [str(DATA_SPEC)]
            fallback["ref"] = str(root / "fallback.svg")
            fallback["receipt_ref"] = str(root / "fallback.receipt.json")
            native["input_refs"] = [str(DATA_SPEC), fallback["ref"]]
            native["ref"] = str(root / "native-chart.pptx")
            native["receipt_ref"] = str(root / "native-chart.receipt.json")
            item_path = root / "item.json"
            item_path.write_text(
                json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            for artifact_id in (fallback["artifact_id"], native["artifact_id"]):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPTS / "render_content_artifacts.py"),
                        "render",
                        "--item",
                        str(item_path),
                        "--artifact-id",
                        artifact_id,
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                    encoding="utf-8",
                    errors="replace",
                )
                self.assertEqual(
                    completed.returncode, 0, completed.stdout + completed.stderr
                )

            receipt = json.loads(Path(native["receipt_ref"]).read_text(encoding="utf-8"))
            checks = {check["name"]: check for check in receipt["qa"]["hard_checks"]}
            self.assertEqual(checks["native-data-exact"]["status"], "pass")
            self.assertEqual(checks["native-labels-exact"]["status"], "pass")
            self.assertEqual(checks["native-zero-baseline"]["status"], "pass")

            manifest = json.loads(
                Path(native["ref"] + ".manifest.json").read_text(encoding="utf-8")
            )
            evidence = manifest["native_data_evidence"]
            self.assertEqual(manifest["generation"]["operation"], "data-native")
            self.assertTrue(evidence["values_exact"])
            self.assertTrue(evidence["categories_exact"])
            self.assertTrue(evidence["zero_baseline_exact"])
            self.assertEqual(
                evidence["actual"]["series"][0]["values"],
                [3.592132, 3.005519],
            )


if __name__ == "__main__":
    unittest.main()
