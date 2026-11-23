import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path


def _visual_profile_workspace():
    value = os.environ.get("CONTENT_STUDIO_TEST_VISUAL_PROFILE_WORKSPACE")
    if value is None or not value.strip():
        raise ValueError(
            "CONTENT_STUDIO_TEST_VISUAL_PROFILE_WORKSPACE must name an existing "
            "workspace directory"
        )
    root = Path(value.strip()).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(
            "CONTENT_STUDIO_TEST_VISUAL_PROFILE_WORKSPACE must name an existing "
            "workspace directory"
        )
    return root


ROOT = _visual_profile_workspace()
REGISTRY = ROOT / "docs" / "content-creation-system" / "profiles" / "profile-registry.json"
ADMIN = ROOT / "content-studio-poc" / "admin" / "config.yml"
THEME = ROOT / "content-studio-poc" / "themes" / "insurance-observational-advisor.css"
VALIDATOR = ROOT / "scripts" / "validate-content-profile-refs.py"
INVALID_CONTRAST_FIXTURE = (
    ROOT
    / "content-studio-poc"
    / "tests"
    / "fixtures"
    / "invalid-low-contrast-profile-registry.json"
)


class VisualProfileRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        cls.profile = next(
            profile
            for profile in cls.registry["profiles"]
            if profile["id"] == "visual/insurance-observational-advisor"
        )

    def test_insurance_default_points_to_versioned_profile(self):
        self.assertEqual(
            self.registry["defaults"]["insurance_broker_visual"],
            {"id": "visual/insurance-observational-advisor", "version": "0.2.0"},
        )
        self.assertEqual(self.profile["version"], "0.2.0")

    def test_palette_tokens_are_exact_and_css_matches(self):
        expected = {
            "ink": "#243238",
            "brand_teal": "#245B5A",
            "human_accent": "#AD4E3D",
            "paper": "#F7F8F5",
            "mist": "#DDEBE9",
        }
        self.assertEqual(self.profile["contract"]["tokens"], expected)
        css = THEME.read_text(encoding="utf-8")
        for color in expected.values():
            self.assertRegex(css, re.compile(re.escape(color), re.IGNORECASE))

    def test_sveltia_exposes_profile(self):
        self.assertIn(
            "visual/insurance-observational-advisor",
            ADMIN.read_text(encoding="utf-8"),
        )

    def test_terracotta_is_not_a_default_risk_color(self):
        contract = self.profile["contract"]
        self.assertIn("不自动表示风险", contract["semantic_roles"]["human_accent"])
        self.assertTrue(
            any("Do not use human_accent" in rule for rule in contract["usage_rules"])
        )

    def test_validator_rejects_declared_low_contrast_pair(self):
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--profiles",
                str(INVALID_CONTRAST_FIXTURE),
                "--root",
                str(ROOT / "content-studio-poc" / "tests"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("below 4.50:1", result.stderr)


if __name__ == "__main__":
    unittest.main()
