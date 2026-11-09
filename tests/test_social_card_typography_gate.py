import hashlib
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from temp_workspace import isolated_test_directory


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "scripts" / "social_card_playwright_bridge.mjs"
FIXTURES = ROOT / "fixtures" / "typography-gate"
CANONICAL_GATE_ENV = "CONTENT_STUDIO_TEST_SOCIAL_CARD_RENDERER_REGISTRY"


def _env_path(variable: str) -> Path | None:
    """Return an explicitly configured absolute path from the environment, or None."""

    value = os.environ.get(variable, "").strip()
    return Path(value).resolve() if value else None


def _canonical_gate() -> dict:
    """Load the operator-supplied canonical social-card typography gate binding."""

    registry_path = _env_path(CANONICAL_GATE_ENV)
    if registry_path is None:
        raise AssertionError(
            f"{CANONICAL_GATE_ENV} must point at an explicit renderer registry file"
        )
    if not registry_path.is_file():
        raise AssertionError(f"renderer registry is not a file: {registry_path}")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    try:
        gate = registry["renderers"]["social-card"]["typography_gate"]
    except (KeyError, TypeError):
        raise AssertionError(
            "renderer registry must declare renderers.social-card.typography_gate"
        ) from None
    if not isinstance(gate, dict):
        raise AssertionError("renderers.social-card.typography_gate must be a JSON object")
    policy_path = gate.get("policy_path")
    profile_id = gate.get("profile_id")
    policy_sha256 = gate.get("policy_sha256")
    if not isinstance(policy_path, str) or not policy_path.strip():
        raise AssertionError("typography_gate.policy_path must be a non-empty string")
    if not Path(policy_path).is_absolute():
        raise AssertionError("typography_gate.policy_path must be an absolute path")
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise AssertionError("typography_gate.profile_id must be a non-empty string")
    digest = policy_sha256.strip() if isinstance(policy_sha256, str) else ""
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise AssertionError("typography_gate.policy_sha256 must be a lowercase SHA-256 digest")
    return {
        "policy_path": policy_path,
        "profile_id": profile_id,
        "policy_sha256": digest,
    }


PLAYWRIGHT_PACKAGE = _env_path("CONTENT_STUDIO_TEST_SOCIAL_CARD_PLAYWRIGHT_PACKAGE")
CHROMIUM = _env_path("CONTENT_STUDIO_TEST_SOCIAL_CARD_CHROMIUM")


@unittest.skipUnless(
    shutil.which("node")
    and PLAYWRIGHT_PACKAGE is not None
    and PLAYWRIGHT_PACKAGE.is_file()
    and CHROMIUM is not None
    and CHROMIUM.is_file(),
    "local Playwright runtime is unavailable",
)
class SocialCardTypographyGateTests(unittest.TestCase):
    def run_bridge(
        self,
        html_name: str,
        expected_hash: str | None = None,
        *,
        expect_policy_refusal: bool = False,
    ) -> dict:
        policy = FIXTURES / "synthetic-policy.json"
        digest = expected_hash or hashlib.sha256(policy.read_bytes()).hexdigest()
        with isolated_test_directory("social-card-typography-gate") as temporary:
            output = temporary / "preview.png"
            result = subprocess.run(
                [
                    "node", str(BRIDGE),
                    "--html", str(FIXTURES / html_name),
                    "--output", str(output),
                    "--selector", "section.poster",
                    "--card-index", "0",
                    "--chromium", str(CHROMIUM),
                    "--playwright-package", str(PLAYWRIGHT_PACKAGE),
                    "--typography-policy", str(policy),
                    "--typography-profile", "synthetic_social_card",
                    "--typography-policy-sha256", digest,
                ],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            if expect_policy_refusal:
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertIn("typography policy hash mismatch", result.stderr)
                self.assertEqual("", result.stdout)
                self.assertFalse(output.exists(), result.stderr)
                return {
                    "returncode": result.returncode,
                    "stderr": result.stderr,
                    "stdout": result.stdout,
                }
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(output.is_file())
            return json.loads(result.stdout)

    def test_positive_fixture_emits_structured_role_receipt(self):
        report = self.run_bridge("positive.html")
        gate = report["font_gate"]
        self.assertTrue(gate["passed"])
        self.assertTrue(gate["policy_hash_matches"])
        self.assertEqual("synthetic_social_card", gate["profile_id"])
        self.assertEqual({"width": 1080, "height": 1440}, gate["viewport"])
        self.assertEqual({"width": 270, "height": 360}, gate["preview"])
        self.assertTrue(gate["hard_gate"])
        self.assertEqual(60, gate["roles"]["primary_headline"]["min_font_px"])
        self.assertEqual({"primary_headline", "body"}, {node["role"] for node in gate["text_nodes"]})
        self.assertTrue(all("bbox" in node and "font_px" in node for node in gate["text_nodes"]))

    def test_small_body_font_fails_closed_in_receipt(self):
        report = self.run_bridge("negative-small-body.html")
        gate = report["font_gate"]
        self.assertFalse(gate["passed"])
        self.assertGreater(gate["low_font_node_count"], 0)
        self.assertIn("font-below-role-minimum:1", gate["failures"])

    def test_policy_hash_drift_is_rejected_before_render(self):
        diagnostic = self.run_bridge("positive.html", "0" * 64, expect_policy_refusal=True)
        self.assertEqual(1, diagnostic["returncode"])
        self.assertIn("typography policy hash mismatch", diagnostic["stderr"])
        self.assertEqual("", diagnostic["stdout"])

    def test_nested_small_font_css_scale_and_svg_viewbox_are_measured(self):
        gate = self.run_bridge("negative-nested-and-scaled.html")["font_gate"]
        self.assertFalse(gate["passed"])
        small = [node for node in gate["text_nodes"] if not node["passes_font_minimum"]]
        self.assertEqual([10, 20, 20], sorted(round(node["effective_font_px"]) for node in small))
        self.assertTrue(all(node["role"] == "body" for node in small))
        self.assertEqual("requires_human_review", gate["target_preview_readability"])

    def test_inherited_fonts_and_rotation_are_not_false_failures(self):
        gate = self.run_bridge("positive-nested-and-rotated.html")["font_gate"]
        self.assertTrue(gate["passed"], gate["failures"])

    def test_missing_required_primary_headline_fails_closed(self):
        report = self.run_bridge("negative-missing-primary-headline.html")
        gate = report["font_gate"]
        self.assertFalse(gate["passed"])
        self.assertEqual(["primary_headline"], gate["missing_required_roles"])
        self.assertIn("missing-required-roles:primary_headline", gate["failures"])

    def test_unclassified_reading_span_fails_closed(self):
        report = self.run_bridge("negative-unclassified-span.html")
        gate = report["font_gate"]
        self.assertFalse(gate["passed"])
        self.assertEqual(1, gate["unclassified_reading_node_count"])
        self.assertIn("unclassified-reading-node:1", gate["failures"])

    def test_registered_canonical_policy_is_current_and_usable(self):
        CANONICAL_GATE = _canonical_gate()
        policy = Path(CANONICAL_GATE["policy_path"])
        self.assertTrue(policy.is_file())
        self.assertEqual(
            CANONICAL_GATE["policy_sha256"],
            hashlib.sha256(policy.read_bytes()).hexdigest(),
        )
        with isolated_test_directory("social-card-typography-canonical") as temporary:
            output = temporary / "preview.png"
            result = subprocess.run(
                [
                    "node", str(BRIDGE),
                    "--html", str(FIXTURES / "positive.html"),
                    "--output", str(output),
                    "--selector", "section.poster",
                    "--card-index", "0",
                    "--chromium", str(CHROMIUM),
                    "--playwright-package", str(PLAYWRIGHT_PACKAGE),
                    "--typography-policy", str(policy),
                    "--typography-profile", CANONICAL_GATE["profile_id"],
                    "--typography-policy-sha256", CANONICAL_GATE["policy_sha256"],
                ],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
        self.assertTrue(report["font_gate"]["passed"])
        self.assertEqual("social_card_1080x1440", report["font_gate"]["profile_id"])


if __name__ == "__main__":
    unittest.main()
