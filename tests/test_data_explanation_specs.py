import copy
import hashlib
import importlib.util
import json
import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "render_data_explanations.py"


def _chart_spec_root() -> Path:
    raw = os.environ.get("CONTENT_STUDIO_TEST_CHART_SPEC_ROOT")
    if raw is None or not raw.strip():
        raise ValueError(
            "CONTENT_STUDIO_TEST_CHART_SPEC_ROOT must be set to the operator-owned chart-spec directory"
        )
    path = Path(raw.strip()).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(
            f"CONTENT_STUDIO_TEST_CHART_SPEC_ROOT must be an existing directory: {path}"
        )
    return path


SPEC_ROOT = _chart_spec_root()

module_spec = importlib.util.spec_from_file_location("render_data_explanations", MODULE_PATH)
renderer = importlib.util.module_from_spec(module_spec)
assert module_spec.loader is not None
module_spec.loader.exec_module(renderer)


class DataExplanationSpecTests(unittest.TestCase):
    def load(self, name: str):
        path = SPEC_ROOT / name
        return path, json.loads(path.read_text(encoding="utf-8"))

    def test_all_repository_specs_are_valid(self):
        spec_paths = sorted(SPEC_ROOT.glob("*.json"))
        self.assertTrue(
            spec_paths,
            f"no chart spec JSON files were found under the configured chart-spec directory: {SPEC_ROOT}",
        )
        for path in spec_paths:
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual([], renderer.validate_spec(data, path))

    def test_reviewable_step_requires_exact_effective_dates(self):
        path, data = self.load("insurance-rate-step-chart.json")
        data["chart_type"] = "step"
        data["render_status"] = "reviewable_candidate"
        for series in data["series"]:
            series["interpolation"] = "step_after_effective_date"
        data["series"][0]["points"][0]["effective_start"] = None
        errors = renderer.validate_spec(data, path)
        self.assertTrue(any("missing exact effective_start" in item for item in errors))

    def test_verified_policy_and_company_values_use_split_lanes(self):
        path, data = self.load("insurance-rate-step-chart.json")
        self.assertEqual("reviewable_candidate", data["render_status"])
        self.assertEqual("split_lane", data["chart_type"])
        lane_kinds = {series["lane_kind"] for series in data["series"]}
        self.assertIn("regulatory_ceiling", lane_kinds)
        self.assertIn("company_pricing_max", lane_kinds)
        self.assertEqual([], renderer.validate_spec(data, path))

    def test_regulatory_ceiling_rejects_linear_interpolation(self):
        path, data = self.load("insurance-rate-step-chart.json")
        broken = copy.deepcopy(data)
        broken["series"][0]["interpolation"] = "linear_between_observations"
        errors = renderer.validate_spec(broken, path)
        self.assertTrue(any("cannot use linear interpolation" in item for item in errors))

    def test_unknown_fields_are_rejected(self):
        path, data = self.load("medical-payment-denominator.json")
        data["simulated_comments"] = ["not allowed"]
        errors = renderer.validate_spec(data, path)
        self.assertTrue(any("unknown top-level fields" in item for item in errors))

    def test_all_three_review_outputs_are_required(self):
        path, data = self.load("medical-insurance-fund-2025.json")
        data["render"]["output_refs"] = ["outputs/example/chart.html"]
        errors = renderer.validate_spec(data, path)
        self.assertTrue(any("HTML, SVG and PNG" in item for item in errors))

    def test_special_medical_specs_are_evidence_bound(self):
        names = [
            "special-medical-bed-utilization-2024.json",
            "special-medical-resource-decision-chain.json",
            "special-medical-official-case-timeline.json",
        ]
        for name in names:
            with self.subTest(name=name):
                path, data = self.load(name)
                self.assertEqual([], renderer.validate_spec(data, path))
                self.assertEqual("evidence-binding.v1", data["evidence_binding_version"])
                self.assertTrue(data["unknowns"])
                self.assertEqual("manual-only", data["publication_boundary"])

    def test_special_medical_dangling_evidence_ref_fails_closed(self):
        path, data = self.load("special-medical-bed-utilization-2024.json")
        data["series"][0]["points"][0]["evidence_ref"] = "missing"
        errors = renderer.validate_spec(data, path)
        self.assertTrue(any("dangling evidence_ref" in item for item in errors))

    def test_special_medical_stale_evidence_fails_closed(self):
        path, data = self.load("special-medical-bed-utilization-2024.json")
        data["source_refs"][0]["freshness_status"] = "stale"
        errors = renderer.validate_spec(data, path)
        self.assertTrue(any("stale or unsupported freshness_status" in item for item in errors))

    def test_special_medical_conflicting_evidence_fails_closed(self):
        path, data = self.load("special-medical-bed-utilization-2024.json")
        data["series"][0]["points"][0]["evidence_status"] = "conflicting"
        errors = renderer.validate_spec(data, path)
        self.assertTrue(any("unsupported evidence_status" in item for item in errors))

    def test_special_medical_scope_mismatch_fails_closed(self):
        path, data = self.load("special-medical-bed-utilization-2024.json")
        data["series"][0]["points"][0]["scope_ref"] = "different-denominator"
        errors = renderer.validate_spec(data, path)
        self.assertTrue(any("scope_ref does not match" in item for item in errors))

    def test_special_medical_unknown_value_fails_closed(self):
        path, data = self.load("special-medical-resource-decision-chain.json")
        unknown = next(
            point
            for point in data["series"][0]["points"]
            if point["evidence_status"] == "unknown"
        )
        unknown["value"] = 1
        errors = renderer.validate_spec(data, path)
        self.assertTrue(any("unknown evidence must not carry a value" in item for item in errors))

    def test_special_medical_text_budget_fails_closed(self):
        path, data = self.load("special-medical-official-case-timeline.json")
        data["series"][0]["points"][0]["note"] = "过长" * 20
        errors = renderer.validate_spec(data, path)
        self.assertTrue(any("timeline note exceeds" in item for item in errors))

    def test_special_medical_layouts_are_deterministic_and_semantically_complete(self):
        names = [
            "special-medical-bed-utilization-2024.json",
            "special-medical-resource-decision-chain.json",
            "special-medical-official-case-timeline.json",
        ]
        for name in names:
            with self.subTest(name=name):
                _, data = self.load(name)
                first = renderer.render_svg_text(data).encode("utf-8")
                second = renderer.render_svg_text(data).encode("utf-8")
                self.assertEqual(hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest())
                self.assertIn(data["title"], first.decode("utf-8"))
                for series in data["series"]:
                    for point in series["points"]:
                        self.assertIn(point["label"], first.decode("utf-8"))
                canvas = renderer.render_canvas(data)
                self.assertEqual((canvas.width, canvas.height), (data["render"]["width"], data["render"]["height"]))
                if data["chart_type"] == "timeline":
                    self.assertIsNotNone(canvas.image.getbbox())


if __name__ == "__main__":
    unittest.main()
