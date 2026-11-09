"""Synthetic, standard-library-only tests for the portable PPT data projection.

Execution (synthetic, standard library only, fail-fast):
    python -X utf8 -B tests/test_ppt_master_data_projection_portable.py

The direct runner is configured with ``failfast=True`` (including subtests), so a
refusal such as a permission error stops the run at the first error instead of
continuing through unrelated tests. The first error is preserved and the run is
not retried or probed.

Scope notes:
* Synthetic-only data: fictional chart id, generic category/series labels and
  invented values. No real chart, real data, private renderer, font, Office/SVG
  renderer or artifact is read, imported or produced.
* The absent-backend patch and the present-backend stub are test-only controls.
  The stub proves the preserved call order and write sequence of this candidate;
  it does NOT prove real canonical rendering or real backend validation. It is
  never presented as passing the original integration suite.
* The in-memory source mutant is a labeled control: it deliberately removes one
  guard and demonstrates that the matching rejection assertion fails without it.
  The expected mutant failure is a control outcome, not evidence that the real
  module passes, and no production file is modified.
* Existing integration coverage intentionally NOT ported/executed here (the
  original five-test file keeps its real assertions in the parent repository):
  1. the real grouped-bar chart spec projects to a zero-based native column;
  2. unsupported, misaligned and negative variants of the real spec fail closed;
  3. real rendering + materialization is deterministic and detects stale fallback;
  4. planned render artifacts can supply a missing SVG fallback;
  5. dependency cycles and stale SVG artifacts are rejected.
  Intentions 4-5 belong to sibling artifact-validation modules that are not
  provided; no equivalent is claimed or masked with mocks.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import copy
import io
import json
import math
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


CANDIDATE_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_SCRIPTS = CANDIDATE_ROOT / "scripts"
CANDIDATE_SCRIPT = CANDIDATE_SCRIPTS / "ppt_master_data_projection.py"
sys.path.insert(0, str(CANDIDATE_SCRIPTS))

from ppt_master_data_projection import (  # noqa: E402
    PROJECTION_VERSION,
    ProjectionError,
    canonical_json_sha256,
    main,
    materialize_project,
    presentation_svg,
    project_native_payload,
    sha256_bytes,
    sha256_file,
    validate_projection_manifest,
)

BACKEND_MODULE = "render_data_explanations"

# Exactly one finiteness guard in the production source; the mutant control
# removes it in memory only. Keeping the literal here makes the control fail
# loudly if the guarded source ever changes.
MUTANT_GUARD = (
    "    if not math.isfinite(float(value)):\n"
    '        raise ProjectionError(f"{location} must be finite")\n'
)
MUTANT_REPLACEMENT = "    # mutant control: finiteness guard removed in memory\n"


def synthetic_spec(chart_type: str = "grouped_bar") -> dict:
    """Return a wholly synthetic spec; every label/value is fictional."""

    return {
        "chart_id": "synth-portable-01",
        "chart_type": chart_type,
        "render_status": "ready",
        "title": "合成示例标题",
        "conclusion": "合成结论：仅用于结构验证。",
        "scope": "合成统计范围",
        "time_range": "2026 年度",
        "unit": "亿元",
        "denominator": "合成口径",
        "source_refs": [{"label": "合成数据源"}],
        "series": [
            {
                "id": "series-alpha",
                "label": "系列甲",
                "interpolation": "none",
                "points": [
                    {"label": "类别一", "value": 12.5},
                    {"label": "类别二", "value": 7.25},
                ],
            }
        ],
    }


def synthetic_two_series_spec() -> dict:
    spec = synthetic_spec("grouped_bar")
    second = copy.deepcopy(spec["series"][0])
    second.update(
        {
            "id": "series-beta",
            "label": "系列乙",
            "points": [
                {"label": "类别一", "value": 3.5},
                {"label": "类别二", "value": 9.75},
            ],
        }
    )
    spec["series"].append(second)
    return spec


class CandidateSourceShapeTests(unittest.TestCase):
    """Static checks: source parses/compiles and defers the private backend."""

    def test_candidate_source_compiles_and_defers_backend_import(self) -> None:
        source = CANDIDATE_SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(CANDIDATE_SCRIPT))
        compile(tree, str(CANDIDATE_SCRIPT), "exec")  # compile only; never executed here

        top_level = [
            node
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module == BACKEND_MODULE
        ]
        self.assertEqual(
            top_level, [], "the private backend must not be imported at module import time"
        )
        nested = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == BACKEND_MODULE
        ]
        self.assertEqual(len(nested), 1)
        self.assertGreater(
            nested[0].col_offset, 0, "the backend import must live inside a function body"
        )

    def test_candidate_imports_only_standard_library_at_module_load(self) -> None:
        tree = ast.parse(CANDIDATE_SCRIPT.read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module.split(".")[0])
        self.assertLessEqual(
            modules,
            {
                "__future__",
                "argparse",
                "hashlib",
                "html",
                "json",
                "math",
                "sys",
                "pathlib",
                "typing",
            },
        )

    def test_source_guard_mutant_control_for_nonfinite_values(self) -> None:
        """Mutant control: the finiteness rejection disappears if the guard is removed.

        The in-memory mutation is the only change; the production file is untouched.
        The expected mutant failure below is labeled as a control outcome and is
        not evidence that the real module passes.
        """

        source = CANDIDATE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn(MUTANT_GUARD, source)
        mutated_source = source.replace(MUTANT_GUARD, MUTANT_REPLACEMENT, 1)
        self.assertNotEqual(mutated_source, source)

        spec = synthetic_spec()
        spec["series"][0]["points"][0]["value"] = math.nan

        self.assertTrue(
            self._guard_rejects(project_native_payload, ProjectionError, spec),
            "real module must reject a non-finite value",
        )

        mutant = types.ModuleType("ppt_master_data_projection_mutant")
        exec(  # in-memory only; no file, harness or production change
            compile(mutated_source, "<in-memory-guard-mutant>", "exec"),
            mutant.__dict__,
        )
        # EXPECTED MUTANT FAILURE (labeled control): with the finiteness guard
        # removed, the same rejection assertion fails, proving the guard matters.
        self.assertFalse(
            self._guard_rejects(
                mutant.project_native_payload, mutant.ProjectionError, spec
            ),
            "mutant control failed to disable the finiteness guard",
        )

    @staticmethod
    def _guard_rejects(project, error_type, spec) -> bool:
        try:
            project(spec)
        except error_type:
            return True
        return False


class PureMappingTests(unittest.TestCase):
    def test_bar_and_grouped_bar_keep_labels_values_and_zero_baseline(self) -> None:
        for chart_type in ("bar", "grouped_bar"):
            with self.subTest(chart_type=chart_type):
                payload, mapping = project_native_payload(synthetic_spec(chart_type))
                self.assertEqual(payload["type"], "column")
                self.assertEqual(payload["categories"], ["类别一", "类别二"])
                self.assertEqual(
                    payload["series"], [{"name": "系列甲", "values": [12.5, 7.25]}]
                )
                self.assertEqual(payload["axes"]["value"]["minimum"], 0)
                self.assertEqual(payload["axes"]["category"]["kind"], "text")
                self.assertEqual(payload["data_labels"]["number_format"], "0.00")
                self.assertEqual(payload["name"], "synth-portable-01-native-chart")
                self.assertEqual(mapping["source_chart_type"], chart_type)
                self.assertEqual(mapping["native_chart_type"], "column")
                self.assertTrue(mapping["lossless"])
                self.assertEqual(mapping["source_series_ids"], ["series-alpha"])
                self.assertEqual(
                    mapping["source_point_labels"], [["类别一", "类别二"]]
                )
                self.assertEqual(
                    mapping["encoding_transform"]["preserved"],
                    ["category-order", "series-order", "values", "unit"],
                )
                self.assertEqual(
                    mapping["native_payload_sha256"], canonical_json_sha256(payload)
                )

    def test_grouped_bar_multi_series_keeps_order_and_requests_legend(self) -> None:
        payload, mapping = project_native_payload(synthetic_two_series_spec())
        self.assertEqual(
            [entry["name"] for entry in payload["series"]], ["系列甲", "系列乙"]
        )
        self.assertEqual(
            [entry["values"] for entry in payload["series"]],
            [[12.5, 7.25], [3.5, 9.75]],
        )
        self.assertTrue(payload["show_legend"])
        self.assertEqual(payload["legend_position"], "bottom")
        self.assertEqual(len(payload["style"]["colors"]), 2)
        self.assertEqual(
            mapping["source_series_ids"], ["series-alpha", "series-beta"]
        )
        self.assertEqual(
            mapping["source_point_labels"],
            [["类别一", "类别二"], ["类别一", "类别二"]],
        )

    def test_stacked_scenario_projects_components_to_stacked_column(self) -> None:
        payload, mapping = project_native_payload(synthetic_spec("stacked_scenario"))
        self.assertEqual(payload["type"], "column")
        self.assertEqual(payload["grouping"], "stacked")
        self.assertEqual(payload["categories"], ["合成口径"])
        self.assertEqual(
            payload["series"],
            [
                {"name": "类别一", "values": [12.5]},
                {"name": "类别二", "values": [7.25]},
            ],
        )
        self.assertEqual(payload["axes"]["value"]["minimum"], 0)
        self.assertTrue(payload["show_legend"])
        self.assertEqual(payload["legend_position"], "bottom")
        self.assertEqual(len(payload["style"]["colors"]), 2)
        self.assertEqual(mapping["native_chart_type"], "column/stacked")
        self.assertEqual(
            mapping["encoding_transform"]["preserved"],
            ["component-order", "values", "denominator", "unit"],
        )
        self.assertEqual(
            mapping["native_payload_sha256"], canonical_json_sha256(payload)
        )

    def test_mechanism_projects_to_line_and_keeps_negative_values(self) -> None:
        for interpolation in ("none", "linear_between_observations"):
            with self.subTest(interpolation=interpolation):
                spec = synthetic_spec("mechanism")
                spec["series"][0]["interpolation"] = interpolation
                spec["series"][0]["points"][0]["value"] = -4.5
                payload, mapping = project_native_payload(spec)
                self.assertEqual(payload["type"], "line")
                self.assertEqual(payload["line_style"], "lineMarker")
                self.assertEqual(payload["categories"], ["类别一", "类别二"])
                self.assertEqual(
                    payload["series"], [{"name": "系列甲", "values": [-4.5, 7.25]}]
                )
                self.assertNotIn("axes", payload)
                self.assertEqual(mapping["native_chart_type"], "line")

    def test_blocked_and_unsupported_sources_fail_closed(self) -> None:
        for render_status in ("blocked", "blocked_pending_review"):
            with self.subTest(render_status=render_status):
                spec = synthetic_spec()
                spec["render_status"] = render_status
                with self.assertRaisesRegex(
                    ProjectionError, "blocked data specs cannot enter"
                ):
                    project_native_payload(spec)
        for chart_type in ("split_lane", "step", "waterfall"):
            with self.subTest(chart_type=chart_type):
                spec = synthetic_spec()
                spec["chart_type"] = chart_type
                with self.assertRaisesRegex(ProjectionError, "no lossless native mapping"):
                    project_native_payload(spec)

    def test_structurally_broken_sources_fail_closed(self) -> None:
        empty = synthetic_spec()
        empty["series"] = []
        with self.assertRaisesRegex(ProjectionError, "at least one series"):
            project_native_payload(empty)

        no_points = synthetic_spec()
        no_points["series"][0]["points"] = []
        with self.assertRaisesRegex(ProjectionError, r"series\[0\] has no points"):
            project_native_payload(no_points)

        missing = synthetic_spec()
        missing["series"][0]["points"][1]["value"] = None
        with self.assertRaisesRegex(ProjectionError, "contains missing values"):
            project_native_payload(missing)

    def test_nonfinite_non_numeric_and_bool_values_fail_closed(self) -> None:
        for bad_value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(bad_value=bad_value):
                spec = synthetic_spec()
                spec["series"][0]["points"][0]["value"] = bad_value
                with self.assertRaisesRegex(ProjectionError, "must be finite"):
                    project_native_payload(spec)
        for bad_value in (True, False):
            with self.subTest(bad_value=bad_value):
                spec = synthetic_spec()
                spec["series"][0]["points"][0]["value"] = bad_value
                with self.assertRaisesRegex(ProjectionError, "must be numeric"):
                    project_native_payload(spec)
        spec = synthetic_spec()
        spec["series"][0]["points"][0]["value"] = "3.5"
        with self.assertRaisesRegex(ProjectionError, "must be numeric"):
            project_native_payload(spec)

    def test_negative_values_fail_only_where_the_native_baseline_requires(self) -> None:
        bar = synthetic_spec("bar")
        bar["series"][0]["points"][0]["value"] = -1
        with self.assertRaisesRegex(ProjectionError, "non-negative values"):
            project_native_payload(bar)

        grouped = synthetic_two_series_spec()
        grouped["series"][1]["points"][0]["value"] = -0.5
        with self.assertRaisesRegex(ProjectionError, "non-negative values"):
            project_native_payload(grouped)

        stacked = synthetic_spec("stacked_scenario")
        stacked["series"][0]["points"][0]["value"] = -2
        with self.assertRaisesRegex(
            ProjectionError, "stacked_scenario requires non-negative values"
        ):
            project_native_payload(stacked)

    def test_series_count_and_label_alignment_rules_fail_closed(self) -> None:
        misaligned = synthetic_two_series_spec()
        misaligned["series"][1]["points"][1]["label"] = "不同类别"
        with self.assertRaisesRegex(ProjectionError, "identical ordered point labels"):
            project_native_payload(misaligned)

        stacked = synthetic_two_series_spec()
        stacked["chart_type"] = "stacked_scenario"
        with self.assertRaisesRegex(
            ProjectionError, "stacked_scenario requires exactly one source series"
        ):
            project_native_payload(stacked)

        mechanism = synthetic_two_series_spec()
        mechanism["chart_type"] = "mechanism"
        with self.assertRaisesRegex(
            ProjectionError, "mechanism charts require exactly one source series"
        ):
            project_native_payload(mechanism)

        bad_interpolation = synthetic_spec("mechanism")
        bad_interpolation["series"][0]["interpolation"] = "cubic_spline"
        with self.assertRaisesRegex(
            ProjectionError, "interpolation is not representable"
        ):
            project_native_payload(bad_interpolation)

    def test_corrupted_input_data_copies_fail_closed(self) -> None:
        """Bounded input-copy control: mutated spec data fails, the original does not.

        This mutates input data only (not source); the separate in-memory source
        mutant above covers the load-bearing guard check.
        """

        spec = synthetic_spec("bar")
        control_payload, control_mapping = project_native_payload(spec)

        pristine_copy = copy.deepcopy(spec)
        _payload, copied_mapping = project_native_payload(pristine_copy)
        self.assertEqual(
            copied_mapping["native_payload_sha256"],
            control_mapping["native_payload_sha256"],
        )

        nonfinite_copy = copy.deepcopy(spec)
        nonfinite_copy["series"][0]["points"][0]["value"] = math.nan
        with self.assertRaisesRegex(ProjectionError, "must be finite"):
            project_native_payload(nonfinite_copy)

        negative_copy = copy.deepcopy(spec)
        negative_copy["series"][0]["points"][0]["value"] = -3
        with self.assertRaisesRegex(ProjectionError, "non-negative values"):
            project_native_payload(negative_copy)

        # The control spec and its projection are unchanged by the failing copies.
        self.assertEqual(spec, synthetic_spec("bar"))
        self.assertEqual(
            project_native_payload(spec)[1]["native_payload_sha256"],
            control_mapping["native_payload_sha256"],
        )


class PresentationSvgTests(unittest.TestCase):
    def test_presentation_svg_keeps_required_text_and_is_deterministic(self) -> None:
        spec = synthetic_spec("grouped_bar")
        payload, _mapping = project_native_payload(spec)
        first_svg, first_text = presentation_svg(spec, payload)
        second_svg, second_text = presentation_svg(spec, payload)
        self.assertEqual(first_svg, second_svg)
        self.assertEqual(first_text, second_text)
        joined = "\n".join(first_text)
        for expected in (
            spec["title"],
            spec["conclusion"],
            f"范围：{spec['scope']}",
            "时间：2026 年度 · 单位：亿元",
            "口径：合成口径",
            "来源：合成数据源",
            "MANUAL-ONLY · 医疗与保险内容须人工复核",
        ):
            self.assertIn(expected, joined)
        self.assertIn('data-pptx-page-role="content"', first_svg)
        self.assertIn('data-pptx-replace-with="chart"', first_svg)
        self.assertIn('id="synth-portable-01-native-chart"', first_svg)
        self.assertIn('<metadata type="application/json">', first_svg)
        self.assertIn("MANUAL-ONLY · 医疗与保险内容须人工复核", first_svg)
        self.assertIn("#F7F8F5", first_svg)

    def test_source_text_budget_guard_fails_closed(self) -> None:
        spec = synthetic_spec("bar")
        spec["source_refs"] = [
            {"label": "合成来源" + "长" * 100 + str(index)} for index in range(4)
        ]
        payload, _mapping = project_native_payload(spec)
        with self.assertRaisesRegex(ProjectionError, "source text exceeds"):
            presentation_svg(spec, payload)

    def test_all_zero_bar_values_fail_closed_in_svg_fallback(self) -> None:
        spec = synthetic_spec("bar")
        for point in spec["series"][0]["points"]:
            point["value"] = 0
        payload, _mapping = project_native_payload(spec)
        with self.assertRaisesRegex(ProjectionError, "at least one positive value"):
            presentation_svg(spec, payload)


class ManifestValidationTests(unittest.TestCase):
    def _write_projection(self, root: Path) -> tuple[dict, Path]:
        spec_path = root / "synth-spec.json"
        spec_path.write_text(
            json.dumps(synthetic_spec(), ensure_ascii=False), encoding="utf-8"
        )
        fallback_path = root / "synth-fallback.svg"
        fallback_path.write_text('<svg data-synthetic="fallback"/>', encoding="utf-8")
        slide_path = root / "synth-slide.svg"
        slide_path.write_text('<svg data-synthetic="slide"/>', encoding="utf-8")

        payload, mapping = project_native_payload(synthetic_spec())
        projection = {
            "schema_version": PROJECTION_VERSION,
            "projection_id": "synth-portable-01-ppt-native",
            "source": {
                # relative refs resolve against the manifest parent
                "spec_ref": spec_path.name,
                "spec_sha256": sha256_file(spec_path),
                "fallback_ref": fallback_path.name,
                "fallback_sha256": sha256_file(fallback_path),
                "canonical_fallback_sha256": sha256_bytes(fallback_path.read_bytes()),
            },
            "mapping": mapping,
            "native_object": {"object_key": payload["name"], "payload": payload},
            "expected_native_chart": {
                "type": payload["type"],
                "categories": payload["categories"],
                "series": [
                    {"name": entry["name"], "values": entry["values"]}
                    for entry in payload["series"]
                ],
                "value_axis_minimum": payload["axes"]["value"]["minimum"],
            },
            "project": {
                "slide_ref": slide_path.name,
                "slide_sha256": sha256_file(slide_path),
            },
        }
        manifest_path = root / "data_projection.json"
        manifest_path.write_text(
            json.dumps(projection, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return projection, manifest_path

    def test_clean_manifest_and_relative_refs_validate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ppt-projection-manifest-") as tmp:
            projection, manifest_path = self._write_projection(Path(tmp))
            self.assertEqual(validate_projection_manifest(projection, manifest_path), [])

    def test_stale_missing_and_unsupported_manifests_are_reported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ppt-projection-manifest-") as tmp:
            root = Path(tmp)
            projection, manifest_path = self._write_projection(root)

            fallback = root / projection["source"]["fallback_ref"]
            fallback.write_text(
                '<svg data-synthetic="fallback"/>\n', encoding="utf-8"
            )
            self.assertIn(
                "fallback hash is stale",
                validate_projection_manifest(projection, manifest_path),
            )

            missing_file = copy.deepcopy(projection)
            (root / missing_file["source"]["spec_ref"]).unlink()
            errors = validate_projection_manifest(missing_file, manifest_path)
            self.assertTrue(any("spec file is missing:" in error for error in errors))

            missing_ref = copy.deepcopy(projection)
            missing_ref["source"].pop("spec_ref")
            self.assertIn(
                "spec ref is missing",
                validate_projection_manifest(missing_ref, manifest_path),
            )

            unsupported = copy.deepcopy(projection)
            unsupported["schema_version"] = "ppt-master-data-projection.v0"
            self.assertEqual(
                validate_projection_manifest(unsupported, manifest_path),
                ["unsupported projection schema_version"],
            )

    def test_payload_digest_and_expected_chart_divergence_are_reported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ppt-projection-manifest-") as tmp:
            root = Path(tmp)
            projection, manifest_path = self._write_projection(root)

            digest_mismatch = copy.deepcopy(projection)
            digest_mismatch["native_object"]["payload"]["categories"] = [
                "类别一",
                "类别二",
                "类别三",
            ]
            self.assertIn(
                "native payload digest does not match mapping",
                validate_projection_manifest(digest_mismatch, manifest_path),
            )

            divergence = copy.deepcopy(projection)
            divergence["expected_native_chart"]["categories"] = ["类别一"]
            self.assertIn(
                "expected native chart diverges from marker payload",
                validate_projection_manifest(divergence, manifest_path),
            )

            missing_payload = copy.deepcopy(projection)
            missing_payload["native_object"]["payload"] = None
            self.assertIn(
                "native payload is missing",
                validate_projection_manifest(missing_payload, manifest_path),
            )

            missing_expected = copy.deepcopy(projection)
            missing_expected["expected_native_chart"] = None
            self.assertIn(
                "expected_native_chart is missing",
                validate_projection_manifest(missing_expected, manifest_path),
            )


class BackendBoundaryTests(unittest.TestCase):
    """Synthetic backend controls. Stubs are test-only, not real validation."""

    def test_pure_helpers_stay_usable_without_backend(self) -> None:
        with mock.patch.dict(sys.modules, {BACKEND_MODULE: None}):
            spec = synthetic_spec("grouped_bar")
            payload, mapping = project_native_payload(spec)
            svg, required_text = presentation_svg(spec, payload)
            self.assertEqual(
                mapping["native_payload_sha256"], canonical_json_sha256(payload)
            )
            self.assertIn(spec["title"], "\n".join(required_text))
            self.assertIn('data-pptx-replace-with="chart"', svg)

    def test_absent_backend_refuses_materialization_before_any_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ppt-projection-absent-") as tmp:
            root = Path(tmp)
            spec_path = root / "synth-spec.json"
            spec_path.write_text(
                json.dumps(synthetic_spec(), ensure_ascii=False), encoding="utf-8"
            )
            project_root = root / "project"
            with mock.patch.dict(sys.modules, {BACKEND_MODULE: None}):
                with self.assertRaisesRegex(
                    ProjectionError, "renderer backend is not installed"
                ):
                    materialize_project(
                        spec_path, root / "missing-fallback.svg", project_root
                    )
            self.assertFalse(project_root.exists())
            self.assertEqual(
                sorted(entry.name for entry in root.iterdir()), ["synth-spec.json"]
            )

    def test_absent_backend_cli_exits_two_without_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ppt-projection-cli-") as tmp:
            root = Path(tmp)
            spec_path = root / "synth-spec.json"
            spec_path.write_text(
                json.dumps(synthetic_spec(), ensure_ascii=False), encoding="utf-8"
            )
            project_root = root / "project"
            stderr = io.StringIO()
            argv = [
                "ppt_master_data_projection.py",
                "--spec",
                str(spec_path),
                "--fallback",
                str(root / "missing-fallback.svg"),
                "--project",
                str(project_root),
            ]
            with mock.patch.dict(sys.modules, {BACKEND_MODULE: None}), mock.patch.object(
                sys, "argv", argv
            ), contextlib.redirect_stderr(stderr):
                exit_code = main()
            self.assertEqual(exit_code, 2)
            self.assertIn("projection failed", stderr.getvalue())
            self.assertIn("renderer backend is not installed", stderr.getvalue())
            self.assertFalse(project_root.exists())

    def test_installed_backend_import_error_is_not_disguised(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ppt-projection-broken-") as tmp:
            root = Path(tmp)
            spec_path = root / "synth-spec.json"
            spec_path.write_text(
                json.dumps(synthetic_spec(), ensure_ascii=False), encoding="utf-8"
            )
            project_root = root / "project"
            real_import = builtins.__import__

            def broken_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name == BACKEND_MODULE:
                    raise ModuleNotFoundError(
                        "No module named 'synthetic_missing_dependency'",
                        name="synthetic_missing_dependency",
                    )
                return real_import(name, globals, locals, fromlist, level)

            with mock.patch("builtins.__import__", side_effect=broken_import):
                with self.assertRaises(ModuleNotFoundError) as captured:
                    materialize_project(
                        spec_path, root / "missing-fallback.svg", project_root
                    )
            self.assertEqual(captured.exception.name, "synthetic_missing_dependency")
            self.assertNotIsInstance(captured.exception, ProjectionError)
            self.assertFalse(project_root.exists())

    def test_missing_backend_export_is_not_disguised(self) -> None:
        """Bounded control: an importable backend that lacks an expected export."""

        with tempfile.TemporaryDirectory(prefix="ppt-projection-export-") as tmp:
            root = Path(tmp)
            spec_path = root / "synth-spec.json"
            spec_path.write_text(
                json.dumps(synthetic_spec(), ensure_ascii=False), encoding="utf-8"
            )
            project_root = root / "project"
            exportless = types.ModuleType(BACKEND_MODULE)
            exportless.render_svg_text = lambda spec: '<svg data-synthetic="x"/>'
            # validate_spec is deliberately absent; a plain module cannot trigger
            # a transitive import error, but from-import must fail on the export.
            with mock.patch.dict(sys.modules, {BACKEND_MODULE: exportless}):
                with self.assertRaises(ImportError) as captured:
                    materialize_project(
                        spec_path, root / "missing-fallback.svg", project_root
                    )
            self.assertNotIsInstance(captured.exception, ProjectionError)
            self.assertNotIsInstance(captured.exception, ModuleNotFoundError)
            self.assertFalse(project_root.exists())

    def _stub_backend(self, calls: list) -> types.ModuleType:
        stub = types.ModuleType(BACKEND_MODULE)

        def validate_spec(spec, spec_path):
            calls.append(("validate_spec", spec, spec_path))
            return []

        def render_svg_text(spec):
            calls.append(("render_svg_text", spec))
            return '<svg data-synthetic="canonical"/>'

        stub.validate_spec = validate_spec
        stub.render_svg_text = render_svg_text
        return stub

    def test_present_backend_stub_keeps_original_materialization_order(self) -> None:
        """TEST-ONLY stub: proves ordering/guards, not real backend validation."""

        canonical_text = '<svg data-synthetic="canonical"/>'
        with tempfile.TemporaryDirectory(prefix="ppt-projection-stub-") as tmp:
            root = Path(tmp)
            spec = synthetic_spec("grouped_bar")
            spec_path = root / "synth-spec.json"
            spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            fallback_path = root / "synth-fallback.svg"
            fallback_path.write_text(canonical_text, encoding="utf-8")
            project_root = root / "project"
            calls: list = []
            stub = self._stub_backend(calls)

            with mock.patch.dict(sys.modules, {BACKEND_MODULE: stub}):
                result = materialize_project(spec_path, fallback_path, project_root)

                self.assertEqual(
                    [name for name, *_rest in calls], ["validate_spec", "render_svg_text"]
                )
                validate_args = calls[0]
                self.assertEqual(validate_args[1], spec)
                self.assertEqual(validate_args[2], spec_path.resolve())
                self.assertEqual(calls[1][1], spec)

                self.assertEqual(
                    result["native_payload_sha256"],
                    project_native_payload(spec)[1]["native_payload_sha256"],
                )
                slide_path = project_root / "svg_output" / "01_data_chart.svg"
                self.assertTrue(slide_path.is_file())
                projection_path = project_root / "data_projection.json"
                self.assertTrue(projection_path.is_file())
                projection = json.loads(
                    projection_path.read_text(encoding="utf-8")
                )
                self.assertEqual(
                    validate_projection_manifest(projection, projection_path), []
                )
                self.assertEqual(
                    projection["source"]["spec_sha256"], sha256_file(spec_path)
                )
                self.assertEqual(
                    projection["source"]["canonical_fallback_sha256"],
                    sha256_bytes(canonical_text.encode("utf-8")),
                )
                self.assertEqual(
                    projection["expected_native_chart"]["value_axis_minimum"], 0
                )

                stale_project = root / "stale-project"
                fallback_path.write_text(canonical_text + "\n", encoding="utf-8")
                with self.assertRaisesRegex(ProjectionError, "fallback SVG is stale"):
                    materialize_project(spec_path, fallback_path, stale_project)
                self.assertFalse(stale_project.exists())

                stub.validate_spec = lambda spec, spec_path: [
                    "synthetic validation failure"
                ]
                rejected_project = root / "rejected-project"
                with self.assertRaisesRegex(
                    ProjectionError, "synthetic validation failure"
                ):
                    materialize_project(spec_path, fallback_path, rejected_project)
                self.assertFalse(rejected_project.exists())


if __name__ == "__main__":
    # failfast (including subtests) so a refusal such as PermissionError stops at
    # the first error; the first error is preserved, never retried or probed.
    unittest.main(verbosity=2, failfast=True)
