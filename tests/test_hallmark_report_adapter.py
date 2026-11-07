#!/usr/bin/env python3
"""Targeted synthetic-only unit test: hallmark_report_adapter.py.

Reuses the declared markdown-it-py dependency and the existing Keep/Fix/Quick
Wins protocol. No new report protocol, no external CLI, no network.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
WORKSPACE = Path(os.environ.get("CANDIDATE_TEST_WORKSPACE", str(ROOT.parent / "synthetic")))
sys.path.insert(0, str(SCRIPTS))

import hallmark_report_adapter as adapter  # noqa: E402


MARKDOWN_INPUT = """# Synthetic Hallmark audit

### Critical

| # | Tell | Where | Fix |
| --- | --- | --- | --- |
| 1 | Symmetric slogan | Intro | Rewrite the opening |

### Minor

| # | Tell | Where | Fix |
| --- | --- | --- | --- |
| 2 | Uniform CTA | Outro | Vary the CTA |

### Pass

| # | Tell | Where | Fix |
| --- | --- | --- | --- |
| 3 | Clear hierarchy | Grid | Keep as is |
"""


class HallmarkReportAdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        WORKSPACE.mkdir(parents=True, exist_ok=True)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=str(WORKSPACE), prefix="hallmark-")
        self.dir = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def write(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_unsupported_output_format_is_rejected(self) -> None:
        source = self.write("audit.json", json.dumps({"findings": []}))
        with self.assertRaisesRegex(ValueError, "unsupported Hallmark report format"):
            adapter.write_report(source, self.dir / "out.json", "pdf")
        self.assertFalse((self.dir / "out.json").exists())

    def test_unsupported_input_suffix_is_rejected(self) -> None:
        source = self.write("audit.txt", "not a report")
        with self.assertRaisesRegex(ValueError, "input must be JSON or Markdown"):
            adapter.build_report(source)

    def test_bad_json_and_bad_findings_shape_are_rejected(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            adapter.build_report(self.write("broken.json", "{not-json"))
        with self.assertRaisesRegex(ValueError, "findings list"):
            adapter.build_report(self.write("shape.json", json.dumps({"findings": "nope"})))

    def test_empty_input_keeps_all_three_buckets(self) -> None:
        source = self.write("empty.json", json.dumps({"findings": []}))
        report = adapter.build_report(source)
        self.assertEqual(report["schema_version"], "hallmark-review-adapter.v1")
        self.assertEqual(report["summary"], {"keep": 0, "fix": 0, "quick_wins": 0})
        self.assertEqual(report["policy"], {
            "mode": "report-only",
            "automatic_design_changes": False,
            "source_mutation": False,
            "human_review_required": True,
        })
        self.assertEqual(report["source"]["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        rendered = adapter.render_markdown(report)
        for heading in ("## Keep", "## Fix", "## Quick Wins"):
            self.assertIn(heading, rendered)
        self.assertEqual(rendered.count("No findings."), 3)

    def test_json_findings_bucket_mapping_and_report_only_write(self) -> None:
        payload = {"findings": [
            {"id": "f1", "severity": "critical", "title": "Slogan", "where": "Intro", "fix": "Rewrite"},
            {"id": "f2", "level": "minor", "finding": "CTA"},
            {"id": "f3", "bucket": "keep", "severity": "major", "title": "Hierarchy"},
            {"id": "f4", "category": "quick-wins", "severity": "pass", "title": "Spacing"},
        ]}
        source = self.write("findings.json", json.dumps(payload, ensure_ascii=False))
        before = source.read_bytes()
        output = self.dir / "report.json"
        report = adapter.write_report(source, output, "json")
        self.assertEqual(source.read_bytes(), before, "report-only adapter must not mutate its source")
        self.assertEqual(report["summary"], {"keep": 1, "fix": 1, "quick_wins": 2})
        self.assertEqual([row["finding_id"] for row in report["fix"]], ["f1"])
        self.assertEqual([row["finding_id"] for row in report["keep"]], ["f3"])
        self.assertEqual({row["finding_id"] for row in report["quick_wins"]}, {"f2", "f4"})
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["source"]["format"], "json")

    def test_markdown_table_parsing_and_severity_headings(self) -> None:
        source = self.write("findings.md", MARKDOWN_INPUT)
        report = adapter.build_report(source)
        self.assertEqual(report["source"]["format"], "markdown")
        self.assertEqual(report["summary"], {"keep": 1, "fix": 1, "quick_wins": 1})
        self.assertEqual(report["fix"][0]["severity"], "critical")
        self.assertEqual(report["fix"][0]["where"], "Intro")
        self.assertEqual(report["quick_wins"][0]["severity"], "minor")
        self.assertEqual(report["keep"][0]["severity"], "pass")
        self.assertIn("Recommendation: Rewrite the opening", adapter.render_markdown(report))

    def test_source_mutation_guard_and_overwrite_guard(self) -> None:
        source = self.write("mutable.json", json.dumps({"findings": []}))
        with patch.object(adapter, "sha256", side_effect=["before", "after"]):
            with self.assertRaisesRegex(RuntimeError, "source changed during conversion"):
                adapter.build_report(source)
        with self.assertRaisesRegex(ValueError, "refuses to overwrite its source"):
            adapter.write_report(source, source, "json")

    def test_markdown_output_format_is_supported(self) -> None:
        source = self.write("two.md", MARKDOWN_INPUT)
        output = self.dir / "review.md"
        adapter.write_report(source, output, "markdown")
        self.assertIn("# Hallmark Design Review", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
