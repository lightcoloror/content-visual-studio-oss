import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


renderer = load_module("render_content_artifacts_typography_receipt", ROOT / "scripts" / "render_content_artifacts.py")


class SocialCardTypographyReceiptTests(unittest.TestCase):
    artifact = {"renderer": "social-card"}

    def test_font_gate_is_a_required_hard_check(self):
        _, required = renderer.required_hard_checks(
            {
                "media_adapter": "social-card",
                "renderer": "social-card",
                "format": "html",
                "qa_profile": "social-card-html.v1",
                "renderer_options": {},
            }
        )
        self.assertIn("font-size-gate", required)

    def test_passed_font_gate_is_preserved_in_receipt(self):
        receipt = {}
        gate = {
            "passed": True,
            "policy_id": "lucas.typography_gates.v1",
            "profile_id": "social_card_1080x1440",
            "text_nodes": [{"role": "primary_headline", "font_px": 60}],
        }
        renderer._attach_renderer_receipt_evidence(receipt, self.artifact, {"font_gate": gate})
        self.assertEqual(gate, receipt["font_gate"])

    def test_missing_font_gate_evidence_is_explicitly_failed(self):
        receipt = {}
        renderer._attach_renderer_receipt_evidence(receipt, self.artifact, {})
        self.assertFalse(receipt["font_gate"]["passed"])
        self.assertEqual(["missing-font-gate-evidence"], receipt["font_gate"]["failures"])


if __name__ == "__main__":
    unittest.main()
