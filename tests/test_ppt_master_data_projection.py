from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from ppt_master_data_projection import (  # noqa: E402
    ProjectionError,
    materialize_project,
    project_native_payload,
    validate_projection_manifest,
)
from render_artifact_validation import validate_render_artifacts  # noqa: E402
from render_data_explanations import render_svg_text  # noqa: E402
from temp_workspace import isolated_test_directory  # noqa: E402


SPEC_PATH = ROOT / "content" / "chart-specs" / "medical-insurance-fund-2025.json"


class PptMasterDataProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))

    def test_grouped_bar_projects_to_zero_based_native_column(self) -> None:
        payload, mapping = project_native_payload(self.spec)

        self.assertEqual(payload["type"], "column")
        self.assertEqual(payload["categories"], ["总收入", "总支出"])
        self.assertEqual(
            payload["series"],
            [{"name": "年度基金收支", "values": [3.592132, 3.005519]}],
        )
        self.assertEqual(payload["axes"]["value"]["minimum"], 0)
        self.assertEqual(payload["data_labels"]["number_format"], "0.00")
        self.assertEqual(mapping["source_chart_type"], "grouped_bar")
        self.assertEqual(mapping["native_chart_type"], "column")
        self.assertEqual(
            mapping["encoding_transform"]["preserved"],
            ["category-order", "series-order", "values", "unit"],
        )

    def test_unsupported_and_misaligned_sources_fail_closed(self) -> None:
        for chart_type in ("split_lane", "step"):
            with self.subTest(chart_type=chart_type):
                source = copy.deepcopy(self.spec)
                source["chart_type"] = chart_type
                with self.assertRaisesRegex(ProjectionError, "no lossless native mapping"):
                    project_native_payload(source)

        misaligned = copy.deepcopy(self.spec)
        second = copy.deepcopy(misaligned["series"][0])
        second["id"] = "second-series"
        second["points"][1]["label"] = "不同分类"
        misaligned["series"].append(second)
        with self.assertRaisesRegex(ProjectionError, "identical ordered point labels"):
            project_native_payload(misaligned)

        negative = copy.deepcopy(self.spec)
        negative["series"][0]["points"][0]["value"] = -1
        with self.assertRaisesRegex(ProjectionError, "non-negative values"):
            project_native_payload(negative)

    def test_materialization_is_deterministic_and_detects_stale_fallback(self) -> None:
        with isolated_test_directory("ppt-data-projection") as root:
            fallback = root / "fallback.svg"
            fallback.write_text(render_svg_text(self.spec), encoding="utf-8")
            first = materialize_project(SPEC_PATH, fallback, root / "project")
            second = materialize_project(SPEC_PATH, fallback, root / "project")
            self.assertEqual(first["native_payload_sha256"], second["native_payload_sha256"])

            projection_path = Path(first["projection"])
            projection = json.loads(projection_path.read_text(encoding="utf-8"))
            self.assertEqual(
                projection["expected_native_chart"]["value_axis_minimum"], 0
            )
            self.assertEqual(validate_projection_manifest(projection, projection_path), [])

            fallback.write_text(fallback.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            errors = validate_projection_manifest(projection, projection_path)
            self.assertIn("fallback hash is stale", errors)
            with self.assertRaisesRegex(ProjectionError, "fallback SVG is stale"):
                materialize_project(SPEC_PATH, fallback, root / "stale-project")

    def _planned_item(self, fallback: Path, output: Path) -> dict:
        return {
            "content_id": "ppt-master-data-dependency-fixture",
            "gates": {
                "fact": {"status": "pass"},
                "rights": {"status": "pass"},
                "privacy": {"status": "pass"},
            },
            "visual": {
                "assets": [],
                "render_artifacts": [
                    {
                        "artifact_id": "chart-fallback",
                        "output_family": "data-chart",
                        "media_adapter": "infographic",
                        "layout_intent": "data-chart",
                        "renderer": "lieflat-charts",
                        "format": "svg",
                        "status": "planned",
                        "input_refs": [str(SPEC_PATH)],
                        "ref": str(fallback),
                        "receipt_ref": str(fallback.with_suffix(".receipt.json")),
                    },
                    {
                        "artifact_id": "chart-native",
                        "output_family": "slide",
                        "media_adapter": "pptx",
                        "layout_intent": "data-chart",
                        "renderer": "ppt-master",
                        "format": "pptx",
                        "status": "planned",
                        "input_refs": [str(SPEC_PATH), str(fallback)],
                        "depends_on_artifact_ids": ["chart-fallback"],
                        "ref": str(output),
                        "receipt_ref": str(output.with_suffix(".receipt.json")),
                        "renderer_options": {
                            "explicit_adapter": True,
                            "operation": "data-native",
                            "ppt_master_protocol": "v4.5",
                            "fallback_artifact_id": "chart-fallback",
                        },
                    },
                ],
            },
        }

    def test_planned_dependency_can_supply_a_missing_fallback(self) -> None:
        with isolated_test_directory("ppt-data-projection") as root:
            item = self._planned_item(root / "planned.svg", root / "planned.pptx")
            self.assertEqual(validate_render_artifacts(item, root / "item.json"), [])

            item["visual"]["render_artifacts"][1]["depends_on_artifact_ids"] = []
            messages = [
                message
                for _, message in validate_render_artifacts(item, root / "item.json")
            ]
            self.assertTrue(any("missing local input" in message for message in messages))
            self.assertTrue(any("fallback_artifact_id" in message for message in messages))

    def test_dependency_cycles_and_stale_svg_are_rejected(self) -> None:
        with isolated_test_directory("ppt-data-projection") as root:
            fallback = root / "fallback.svg"
            fallback.write_text("<svg/>", encoding="utf-8")
            item = self._planned_item(fallback, root / "native.pptx")
            item["visual"]["render_artifacts"][0]["depends_on_artifact_ids"] = [
                "chart-native"
            ]
            messages = [
                message
                for _, message in validate_render_artifacts(item, root / "item.json")
            ]
            self.assertTrue(any("dependency cycle" in message for message in messages))
            self.assertTrue(any("SVG fallback is stale" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
