import hashlib
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from temp_workspace import isolated_test_directory


ROOT = Path(__file__).resolve().parents[1]
ARTICLE_QA = ROOT / "scripts" / "article_browser_qa.mjs"
FIXTURES = ROOT / "fixtures" / "typography-gate"


def _env_path(variable: str) -> Path | None:
    """Return an explicitly configured absolute path from the environment, or None."""

    value = os.environ.get(variable, "").strip()
    return Path(value).resolve() if value else None


PUPPETEER_PACKAGE = _env_path("CONTENT_STUDIO_TEST_ARTICLE_PUPPETEER_PACKAGE")
CHROMIUM = _env_path("CONTENT_STUDIO_TEST_ARTICLE_CHROMIUM")


@unittest.skipUnless(
    shutil.which("node")
    and PUPPETEER_PACKAGE is not None
    and PUPPETEER_PACKAGE.is_file()
    and CHROMIUM is not None
    and CHROMIUM.is_file(),
    "local Puppeteer runtime is unavailable",
)
class ArticleTypographyGateTests(unittest.TestCase):
    def run_qa(
        self,
        html_name: str,
        expected_hash: str | None = None,
        *,
        expect_report: bool = True,
    ) -> tuple[int, dict]:
        policy = FIXTURES / "synthetic-policy.json"
        digest = expected_hash or hashlib.sha256(policy.read_bytes()).hexdigest()
        with isolated_test_directory("article-typography-gate") as temporary:
            report_path = temporary / "report.json"
            result = subprocess.run(
                [
                    "node", str(ARTICLE_QA),
                    "--html", str(FIXTURES / html_name),
                    "--desktop", str(temporary / "desktop.png"),
                    "--mobile", str(temporary / "mobile.png"),
                    "--report", str(report_path),
                    "--chromium", str(CHROMIUM),
                    "--puppeteer-package", str(PUPPETEER_PACKAGE),
                    "--typography-policy", str(policy),
                    "--typography-policy-sha256", digest,
                    "--desktop-typography-profile", "synthetic_article_desktop",
                    "--mobile-typography-profile", "synthetic_article_mobile",
                    "--allow-no-figures", "true",
                ],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            if not expect_report:
                self.assertFalse(report_path.exists(), result.stderr)
                self.assertFalse((temporary / "desktop.png").exists(), result.stderr)
                self.assertFalse((temporary / "mobile.png").exists(), result.stderr)
                return result.returncode, {
                    "stderr": result.stderr,
                    "stdout": result.stdout,
                }
            self.assertTrue(report_path.is_file(), result.stderr)
            return result.returncode, json.loads(report_path.read_text(encoding="utf-8"))

    def test_positive_article_passes_both_viewports(self):
        code, report = self.run_qa("article-positive.html")
        self.assertEqual(0, code)
        self.assertTrue(report["passed"])
        for viewport in ("desktop", "mobile"):
            gate = report[viewport]["typography_gate"]
            self.assertTrue(gate["passed"])
            self.assertEqual({"primary_headline", "body"}, {node["role"] for node in gate["text_nodes"]})

    def test_low_font_unknown_missing_role_and_hash_drift_fail_closed(self):
        cases = (
            ("article-negative-small-body.html", "font-below-role-minimum"),
            ("article-negative-unclassified-span.html", "unclassified-reading-node"),
            ("article-negative-missing-headline.html", "missing-required-roles:primary_headline"),
        )
        for fixture, expected_failure in cases:
            with self.subTest(fixture=fixture):
                code, report = self.run_qa(fixture)
                self.assertEqual(2, code)
                self.assertFalse(report["passed"])
                failures = report["desktop"]["typography_gate"]["failures"]
                self.assertTrue(any(expected_failure in failure for failure in failures))

        code, diagnostic = self.run_qa("article-positive.html", "0" * 64, expect_report=False)
        self.assertEqual(2, code)
        self.assertIn("typography policy hash mismatch", diagnostic["stderr"])


if __name__ == "__main__":
    unittest.main()
