#!/usr/bin/env python3
"""Directed offline contract tests for scripts/slot_budget_validation.py.

The registry documents embedded here mirror the supplied public-edition
fixtures exactly (eight registered templates, their thresholds and the layout
mapping). They are written to a TemporaryDirectory and injected through the
module's own path constants; no threshold is changed, relaxed or weakened.
The AntV parser is always replaced with unittest.mock payloads; the Python
tests never spawn a process, install a package or depend on the optional
native parser. The env/node/timeout wiring is asserted against a mocked
``subprocess.run`` only.

Import contract (host execution plan):
    ``slot_budget_validation`` is imported from PYTHONPATH.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import slot_budget_validation as slot

# Snapshot of the candidate paths as the module resolves them at import time.
ORIGINAL_BUDGET_PATH = slot.BUDGET_PATH
ORIGINAL_LAYOUT_PATH = slot.LAYOUT_REGISTRY_PATH
ORIGINAL_RENDERER_PATH = slot.RENDERER_REGISTRY_PATH

GLOBAL_BUDGET = {
    "title_max_chars": 18,
    "description_max_chars": 30,
    "label_max_chars": 10,
}

MARP_BUDGET = {
    "title_max_chars": 22,
    "supporting_copy_max_chars": 60,
    "source_max_chars": 40,
}

TEMPLATES = {
    "sequence-steps-simple": {
        "layout_intent": "sequence",
        "item_count": {"min": 3, "max": 6, "scope": "top-level"},
    },
    "sequence-timeline-simple": {
        "layout_intent": "timeline",
        "item_count": {"min": 3, "max": 6, "scope": "top-level"},
    },
    "compare-binary-horizontal-simple-vs": {
        "layout_intent": "comparison",
        "item_count": {"exact": 2, "scope": "top-level"},
    },
    "hierarchy-tree-curved-line-rounded-rect-node": {
        "layout_intent": "hierarchy",
        "item_count": {"min": 3, "max": 7, "scope": "all-nodes"},
        "max_depth": 3,
    },
    "relation-dagre-flow-tb-compact-card": {
        "layout_intent": "process",
        "item_count": {"min": 3, "max": 7, "scope": "all-nodes"},
        "max_depth": 3,
    },
    "sequence-circular-simple": {
        "layout_intent": "cycle",
        "item_count": {"min": 3, "max": 5, "scope": "top-level"},
    },
    "compare-quadrant-quarter-simple-card": {
        "layout_intent": "matrix",
        "item_count": {"exact": 4, "scope": "top-level"},
    },
    "list-grid-simple": {
        "layout_intent": "list",
        "item_count": {"min": 3, "max": 6, "scope": "top-level"},
    },
}

INTENTS = {
    "sequence": ["sequence-steps-simple"],
    "timeline": ["sequence-timeline-simple"],
    "comparison": ["compare-binary-horizontal-simple-vs"],
    "hierarchy": ["hierarchy-tree-curved-line-rounded-rect-node"],
    "process": ["relation-dagre-flow-tb-compact-card"],
    "cycle": ["sequence-circular-simple"],
    "matrix": ["compare-quadrant-quarter-simple-card"],
    "list": ["list-grid-simple"],
    "data-chart": [],
    "quote-hero": [],
}


def budget_document() -> dict:
    return {
        "schema_version": "slot-budgets.v1",
        "antv": {
            "global": copy.deepcopy(GLOBAL_BUDGET),
            "templates": copy.deepcopy(TEMPLATES),
        },
        "marp": copy.deepcopy(MARP_BUDGET),
    }


def layout_document() -> dict:
    return {
        "schema_version": "layout-intents.v1",
        "intents": {
            intent: {"antv_templates": list(templates)}
            for intent, templates in INTENTS.items()
        },
    }


def renderer_document(local_path=None) -> dict:
    return {
        "schema_version": "renderer-registry.v1",
        "policy": {"remote_asset_downloads": False},
        "renderers": {
            "antv-infographic": {
                "runtime_root_env": "CONTENT_STUDIO_ANTV_MODULE_ROOT",
                "local_path": local_path,
            }
        },
    }


class SlotBudgetContractTests(unittest.TestCase):
    """Budget, parser-integration and registry-coverage behaviour."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.budget_path = self.root / "slot-budgets.v1.json"
        self.layout_path = self.root / "layout-intents.v1.json"
        self.renderer_path = self.root / "renderer-registry.v1.json"
        self.inspector_path = self.root / "scripts" / "inspect_antv_input.mjs"

        self.write_budget(budget_document())
        self.write_layouts(layout_document())
        self.write_renderer(renderer_document())

        for attribute, value in (
            ("BUDGET_PATH", self.budget_path),
            ("LAYOUT_REGISTRY_PATH", self.layout_path),
            ("RENDERER_REGISTRY_PATH", self.renderer_path),
            ("INSPECTOR_PATH", self.inspector_path),
        ):
            patcher = mock.patch.object(slot, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        slot.load_json.cache_clear()
        self.addCleanup(slot.load_json.cache_clear)

    # ---------------------------------------------------------------- helpers
    def write_json(self, path: Path, value) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")
        slot.load_json.cache_clear()

    def write_budget(self, document) -> None:
        self.write_json(self.budget_path, document)

    def write_layouts(self, document) -> None:
        self.write_json(self.layout_path, document)

    def write_renderer(self, document) -> None:
        self.write_json(self.renderer_path, document)

    def parsed(self, template, data, errors=None, warnings=None) -> dict:
        return {
            "template": template,
            "data": data,
            "errors": list(errors or []),
            "warnings": list(warnings or []),
        }

    def data_for_count(self, template: str, count: int) -> dict:
        if TEMPLATES[template]["item_count"]["scope"] == "top-level":
            return {
                "title": "Synthetic",
                "items": [
                    {"label": f"item-{index}"} for index in range(count)
                ],
            }
        return {
            "title": "Synthetic",
            "items": [
                {
                    "label": "root",
                    "children": [
                        {"label": f"child-{index}"}
                        for index in range(count - 1)
                    ],
                }
            ],
        }

    def validate(self, template, layout_intent, data, input_path="synthetic.ifgc"):
        payload = self.parsed(template, data)
        with mock.patch.object(
            slot, "inspect_antv_input", return_value=payload
        ):
            return slot.validate_antv_budget(Path(input_path), template, layout_intent)

    # ------------------------------------------------ all eight template budgets
    def test_every_registered_template_accepts_its_boundary_counts(self):
        self.assertEqual(len(TEMPLATES), 8)
        for template, budget in TEMPLATES.items():
            rule = budget["item_count"]
            boundaries = (
                [rule["exact"]] if "exact" in rule else [rule["min"], rule["max"]]
            )
            for count in boundaries:
                with self.subTest(template=template, count=count):
                    self.assertEqual(
                        self.validate(
                            template,
                            budget["layout_intent"],
                            self.data_for_count(template, count),
                        ),
                        [],
                    )

    def test_counts_outside_each_template_budget_are_rejected(self):
        for template, budget in TEMPLATES.items():
            rule = budget["item_count"]
            layout_intent = budget["layout_intent"]
            if "exact" in rule:
                outside = [rule["exact"] - 1, rule["exact"] + 1]
                expectation = "item count must equal"
            else:
                outside = [rule["min"] - 1, rule["max"] + 1]
                expectation = "item count must be"
            for count in outside:
                with self.subTest(template=template, count=count):
                    errors = self.validate(
                        template,
                        layout_intent,
                        self.data_for_count(template, count),
                    )
                    self.assertTrue(
                        any(expectation in message for message in errors), errors
                    )

    # -------------------------------------------------- top-level vs all-nodes
    def test_item_count_scope_controls_top_level_versus_recursive_counts(self):
        nested_four = [{"label": f"nested-{index}"} for index in range(4)]
        top_level_three = {
            "title": "Synthetic",
            "items": [
                {"label": f"step-{index}", "children": copy.deepcopy(nested_four)}
                for index in range(3)
            ],
        }
        # 3 top-level nodes & 15 flattened nodes: the top-level scope must pass.
        self.assertEqual(
            self.validate("sequence-steps-simple", "sequence", top_level_three), []
        )

        # 2 top-level nodes & 4 flattened nodes: the top-level scope must fail.
        nested_two = {
            "title": "Synthetic",
            "items": [
                {"label": f"step-{index}", "children": [{"label": "nested"}]}
                for index in range(2)
            ],
        }
        self.assertEqual(
            self.validate("sequence-steps-simple", "sequence", nested_two),
            ["item count must be at least 3, got 2"],
        )

        # 1 top-level node & 3 flattened nodes: all-nodes must pass.
        recursive_three = {
            "title": "Synthetic",
            "items": [
                {
                    "label": "root",
                    "children": [{"label": "child-a"}, {"label": "child-b"}],
                }
            ],
        }
        self.assertEqual(
            self.validate(
                "hierarchy-tree-curved-line-rounded-rect-node",
                "hierarchy",
                recursive_three,
            ),
            [],
        )

        # 2 flattened nodes stay below the all-nodes minimum.
        recursive_two = {
            "title": "Synthetic",
            "items": [{"label": "root"}, {"label": "other"}],
        }
        self.assertEqual(
            self.validate(
                "hierarchy-tree-curved-line-rounded-rect-node",
                "hierarchy",
                recursive_two,
            ),
            ["item count must be at least 3, got 2"],
        )

    # ------------------------------------------------------------ max depth
    def test_max_depth_is_enforced_for_tree_templates(self):
        def chain(length: int) -> dict:
            node = {"label": f"leaf-{length - 1}"}
            for index in range(length - 2, -1, -1):
                node = {"label": f"node-{index}", "children": [node]}
            return node

        for template in (
            "hierarchy-tree-curved-line-rounded-rect-node",
            "relation-dagre-flow-tb-compact-card",
        ):
            budget = TEMPLATES[template]
            layout_intent = budget["layout_intent"]
            with self.subTest(template=template, depth=3):
                self.assertEqual(
                    self.validate(
                        template,
                        layout_intent,
                        {"title": "Synthetic", "items": [chain(3)]},
                    ),
                    [],
                )
            with self.subTest(template=template, depth=4):
                self.assertEqual(
                    self.validate(
                        template,
                        layout_intent,
                        {"title": "Synthetic", "items": [chain(4)]},
                    ),
                    ["tree depth must be at most 3, got 4"],
                )

    # ------------------------------------------- whitespace + text boundaries
    def test_whitespace_is_excluded_from_character_boundaries(self):
        template = "sequence-steps-simple"
        layout_intent = "sequence"

        def data(title="Synthetic", desc=None, items=None):
            document = {
                "title": title,
                "items": (
                    [{"label": "step"} for _ in range(3)]
                    if items is None
                    else items
                ),
            }
            if desc is not None:
                document["desc"] = desc
            return document

        self.assertEqual(
            self.validate(template, layout_intent, data(title="  " + "A" * 18 + "   ")),
            [],
        )
        self.assertEqual(
            self.validate(template, layout_intent, data(title="A" * 19)),
            ["title exceeds 18 characters"],
        )

        self.assertEqual(
            self.validate(template, layout_intent, data(desc=" " + "B" * 30)), []
        )
        self.assertEqual(
            self.validate(template, layout_intent, data(desc="B" * 31)),
            ["description exceeds 30 characters"],
        )

        item_descriptions_ok = [
            {"label": "step", "desc": "C" * 30} for _ in range(3)
        ]
        self.assertEqual(
            self.validate(template, layout_intent, data(items=item_descriptions_ok)),
            [],
        )
        item_descriptions_bad = [
            {"label": "step", "desc": "C" * 31},
            {"label": "step"},
            {"label": "step"},
        ]
        self.assertEqual(
            self.validate(template, layout_intent, data(items=item_descriptions_bad)),
            ["description exceeds 30 characters"],
        )

        labels_ok = [{"label": " " + "D" * 10 + " "} for _ in range(3)]
        self.assertEqual(
            self.validate(template, layout_intent, data(items=labels_ok)), []
        )
        labels_bad = [
            {"label": "D" * 11},
            {"label": "step"},
            {"label": "step"},
        ]
        self.assertEqual(
            self.validate(template, layout_intent, data(items=labels_bad)),
            ["item label exceeds 10 characters"],
        )

    # ------------------------------------- unknown template + layout mismatch
    def test_unknown_template_and_layout_mismatch_fail_before_parsing(self):
        with mock.patch.object(
            slot,
            "inspect_antv_input",
            side_effect=AssertionError("the parser must not run"),
        ) as inspector:
            unknown = slot.validate_antv_budget(
                Path("synthetic.ifgc"), "synthetic-unknown-template", "list"
            )
            mismatch = slot.validate_antv_budget(
                Path("synthetic.ifgc"), "sequence-steps-simple", "list"
            )
        self.assertEqual(
            unknown,
            ["template 'synthetic-unknown-template' has no registered slot budget"],
        )
        self.assertEqual(
            mismatch,
            ["template 'sequence-steps-simple' is budgeted for 'sequence', not 'list'"],
        )
        inspector.assert_not_called()

    # ------------------------------------- parser errors + template mismatch
    def test_parser_errors_and_parsed_template_mismatch_are_reported(self):
        payload = self.parsed(
            "sequence-steps-simple",
            {"title": "Synthetic", "items": [{"label": "a"}, {"label": "b"}, {"label": "c"}]},
            errors=["synthetic syntax failure", "synthetic second failure"],
        )
        with mock.patch.object(slot, "inspect_antv_input", return_value=payload):
            errors = slot.validate_antv_budget(
                Path("synthetic.ifgc"), "sequence-steps-simple", "sequence"
            )
        self.assertEqual(
            errors,
            [
                "AntV syntax: synthetic syntax failure",
                "AntV syntax: synthetic second failure",
            ],
        )

        wrong_template = self.parsed(
            "list-grid-simple",
            {"title": "Synthetic", "items": [{"label": "a"}, {"label": "b"}, {"label": "c"}]},
        )
        with mock.patch.object(
            slot, "inspect_antv_input", return_value=wrong_template
        ):
            errors = slot.validate_antv_budget(
                Path("synthetic.ifgc"), "sequence-steps-simple", "sequence"
            )
        self.assertEqual(
            errors,
            [
                "parsed template 'list-grid-simple' does not match artifact "
                "template 'sequence-steps-simple'"
            ],
        )

    # ------------------------------------------------------------------- Marp
    def test_marp_copy_fields_are_required(self):
        self.assertEqual(
            slot.validate_marp_budget({}),
            [
                "Marp renderer_options.copy.title is required",
                "Marp renderer_options.copy.supporting_copy is required",
                "Marp renderer_options.copy.source is required",
            ],
        )
        whitespace = {
            "renderer_options": {
                "copy": {"title": "   ", "supporting_copy": "copy", "source": "source"}
            }
        }
        self.assertEqual(
            slot.validate_marp_budget(whitespace),
            ["Marp renderer_options.copy.title is required"],
        )
        non_string = {
            "renderer_options": {
                "copy": {"title": 42, "supporting_copy": "copy", "source": "source"}
            }
        }
        self.assertEqual(
            slot.validate_marp_budget(non_string),
            ["Marp renderer_options.copy.title is required"],
        )

    def test_marp_copy_bounds_are_enforced(self):
        valid = {
            "renderer_options": {
                "copy": {
                    "title": "A" * 22,
                    "supporting_copy": "B" * 60,
                    "source": "C" * 40,
                }
            }
        }
        self.assertEqual(slot.validate_marp_budget(valid), [])

        padded = {
            "renderer_options": {
                "copy": {
                    "title": " " + "A" * 22 + " ",
                    "supporting_copy": " " + "B" * 60 + " ",
                    "source": " " + "C" * 40 + " ",
                }
            }
        }
        self.assertEqual(slot.validate_marp_budget(padded), [])

        over_title = copy.deepcopy(valid)
        over_title["renderer_options"]["copy"]["title"] = "A" * 23
        self.assertEqual(
            slot.validate_marp_budget(over_title),
            ["Marp title exceeds 22 characters"],
        )

        over_copy = copy.deepcopy(valid)
        over_copy["renderer_options"]["copy"]["supporting_copy"] = "B" * 61
        self.assertEqual(
            slot.validate_marp_budget(over_copy),
            ["Marp supporting_copy exceeds 60 characters"],
        )

        over_source = copy.deepcopy(valid)
        over_source["renderer_options"]["copy"]["source"] = "C" * 41
        self.assertEqual(
            slot.validate_marp_budget(over_source),
            ["Marp source exceeds 40 characters"],
        )

    # ------------------------------------------------------ registry coverage
    def test_registry_coverage_baseline_passes(self):
        self.assertEqual(slot.validate_budget_registry_coverage(), [])

    def test_registry_coverage_detects_missing_orphan_and_mismatched_budgets(self):
        budgets = budget_document()
        budgets["antv"]["templates"].pop("list-grid-simple")
        self.write_budget(budgets)
        self.assertEqual(
            slot.validate_budget_registry_coverage(),
            ["layout 'list' references template 'list-grid-simple' without a budget"],
        )

        budgets = budget_document()
        budgets["antv"]["templates"]["synthetic-orphan-template"] = {
            "layout_intent": "list",
            "item_count": {"min": 1, "max": 2, "scope": "top-level"},
        }
        self.write_budget(budgets)
        self.assertEqual(
            slot.validate_budget_registry_coverage(),
            [
                "budgeted template 'synthetic-orphan-template' is unreachable "
                "from layout intents"
            ],
        )

        budgets = budget_document()
        budgets["antv"]["templates"]["sequence-steps-simple"]["layout_intent"] = "list"
        self.write_budget(budgets)
        self.assertEqual(
            slot.validate_budget_registry_coverage(),
            ["template 'sequence-steps-simple' budget maps to the wrong layout intent"],
        )

    # ------------------------------------- subprocess wiring (mocked, no spawn)
    def test_inspector_invocation_uses_configured_runtime_node_and_timeout(self):
        completed = SimpleNamespace(
            returncode=0,
            stdout=(
                '{"template": "list-grid-simple", "data": {}, '
                '"errors": [], "warnings": []}'
            ),
            stderr="",
        )
        input_path = Path("synthetic.ifgc")
        environment = {
            "CONTENT_STUDIO_NODE": "synthetic-node",
            "CONTENT_STUDIO_ANTV_MODULE_ROOT": "/synthetic/antv-root",
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            with mock.patch.object(
                slot.subprocess, "run", return_value=completed
            ) as run:
                payload = slot.inspect_antv_input(input_path)

        self.assertEqual(payload, json.loads(completed.stdout))
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(
            command,
            [
                "synthetic-node",
                str(slot.INSPECTOR_PATH),
                "--module-root",
                "/synthetic/antv-root",
                "--input",
                str(input_path),
            ],
        )
        options = run.call_args.kwargs
        self.assertIs(options["text"], True)
        self.assertEqual(options["encoding"], "utf-8")
        self.assertEqual(options["errors"], "replace")
        self.assertIs(options["capture_output"], True)
        self.assertIs(options["check"], False)
        self.assertEqual(options["timeout"], 30)

    def test_inspector_uses_registry_local_path_when_environment_is_absent(self):
        self.write_renderer(renderer_document(local_path="/synthetic/local-package"))
        completed = SimpleNamespace(returncode=0, stdout="{}", stderr="")
        with mock.patch.dict(
            os.environ, {"CONTENT_STUDIO_NODE": "synthetic-node"}, clear=True
        ):
            with mock.patch.object(
                slot.subprocess, "run", return_value=completed
            ) as run:
                slot.inspect_antv_input(Path("synthetic.ifgc"))
        command = run.call_args.args[0]
        self.assertEqual(command[0], "synthetic-node")
        self.assertEqual(command[3], "/synthetic/local-package")

    def test_missing_runtime_root_fails_closed_before_spawning(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(slot.subprocess, "run") as run:
                with self.assertRaisesRegex(
                    RuntimeError, "^antv_module_root_required$"
                ):
                    slot.inspect_antv_input(Path("synthetic.ifgc"))
                run.assert_not_called()

    def _use_local_runtime(self) -> None:
        self.write_renderer(renderer_document(local_path="/synthetic/local-package"))

    def test_nonzero_parser_exit_propagates_its_stderr(self):
        self._use_local_runtime()
        failure = SimpleNamespace(
            returncode=2, stdout="", stderr="  synthetic parser rejected input\n"
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(slot.subprocess, "run", return_value=failure):
                with self.assertRaisesRegex(
                    RuntimeError, "^synthetic parser rejected input$"
                ):
                    slot.inspect_antv_input(Path("synthetic.ifgc"))

    def test_nonzero_parser_exit_without_stderr_is_reported(self):
        self._use_local_runtime()
        failure = SimpleNamespace(returncode=7, stdout="", stderr="")
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(slot.subprocess, "run", return_value=failure):
                with self.assertRaisesRegex(
                    RuntimeError, "^AntV parser exited 7$"
                ):
                    slot.inspect_antv_input(Path("synthetic.ifgc"))

    def test_invalid_parser_json_is_propagated(self):
        self._use_local_runtime()
        completed = SimpleNamespace(
            returncode=0, stdout="<html>not json</html>", stderr=""
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(slot.subprocess, "run", return_value=completed):
                with self.assertRaises(json.JSONDecodeError):
                    slot.inspect_antv_input(Path("synthetic.ifgc"))

    def test_parser_timeout_is_propagated(self):
        self._use_local_runtime()
        timeout = subprocess.TimeoutExpired(cmd=["synthetic-node"], timeout=30)
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(slot.subprocess, "run", side_effect=timeout):
                with self.assertRaises(subprocess.TimeoutExpired):
                    slot.inspect_antv_input(Path("synthetic.ifgc"))


class PublicRegistrySmokeTests(unittest.TestCase):
    """When the host candidate carries the public config, check it directly.

    These tests are skipped when the candidate does not contain the planned
    public config files; the synthetic registry suite above always runs.
    """

    def test_public_registries_match_the_embedded_contract_and_coverage(self):
        missing = [
            str(path)
            for path in (
                ORIGINAL_BUDGET_PATH,
                ORIGINAL_LAYOUT_PATH,
                ORIGINAL_RENDERER_PATH,
            )
            if not path.is_file()
        ]
        if missing:
            self.skipTest("public config not present in candidate: " + ", ".join(missing))

        budget_doc = json.loads(ORIGINAL_BUDGET_PATH.read_text(encoding="utf-8"))
        layout_doc = json.loads(ORIGINAL_LAYOUT_PATH.read_text(encoding="utf-8"))
        renderer_doc = json.loads(ORIGINAL_RENDERER_PATH.read_text(encoding="utf-8"))

        public_templates = budget_doc["antv"]["templates"]
        self.assertEqual(len(public_templates), 8)
        self.assertEqual(set(public_templates), set(TEMPLATES))
        for template, expected in TEMPLATES.items():
            with self.subTest(template=template):
                self.assertEqual(
                    public_templates[template]["layout_intent"],
                    expected["layout_intent"],
                )
                self.assertEqual(
                    public_templates[template]["item_count"],
                    expected["item_count"],
                )
                self.assertEqual(
                    public_templates[template].get("max_depth"),
                    expected.get("max_depth"),
                )
        self.assertEqual(budget_doc["antv"]["global"], GLOBAL_BUDGET)
        self.assertEqual(budget_doc["marp"], MARP_BUDGET)

        intents = layout_doc["intents"]
        mapping = {
            template: [
                intent
                for intent, config in intents.items()
                if template in config.get("antv_templates", [])
            ]
            for template in TEMPLATES
        }
        self.assertEqual(
            mapping,
            {
                template: [budget["layout_intent"]]
                for template, budget in TEMPLATES.items()
            },
        )

        renderer = renderer_doc["renderers"]["antv-infographic"]
        self.assertEqual(renderer["runtime_root_env"], "CONTENT_STUDIO_ANTV_MODULE_ROOT")

        with mock.patch.object(slot, "BUDGET_PATH", ORIGINAL_BUDGET_PATH), \
                mock.patch.object(slot, "LAYOUT_REGISTRY_PATH", ORIGINAL_LAYOUT_PATH), \
                mock.patch.object(slot, "RENDERER_REGISTRY_PATH", ORIGINAL_RENDERER_PATH):
            slot.load_json.cache_clear()
            try:
                self.assertEqual(slot.validate_budget_registry_coverage(), [])
            finally:
                slot.load_json.cache_clear()


if __name__ == "__main__":
    unittest.main()
