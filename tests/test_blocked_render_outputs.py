import json
import os
import re
import unittest
from pathlib import Path


def _render_workspace():
    value = os.environ.get("CONTENT_STUDIO_TEST_RENDER_WORKSPACE")
    if value is None:
        raise ValueError("CONTENT_STUDIO_TEST_RENDER_WORKSPACE is not set")
    value = value.strip()
    if not value:
        raise ValueError("CONTENT_STUDIO_TEST_RENDER_WORKSPACE is blank")
    root = Path(value).expanduser().resolve()
    if not root.exists():
        raise ValueError("CONTENT_STUDIO_TEST_RENDER_WORKSPACE does not exist")
    if not root.is_dir():
        raise ValueError("CONTENT_STUDIO_TEST_RENDER_WORKSPACE is not a directory")
    return root


ROOT = _render_workspace()


class BlockedRenderOutputTests(unittest.TestCase):
    def test_policy_company_split_lane_has_no_cross_track_line(self):
        item = json.loads((ROOT / "content/items/data-insurance-rate-step-chart-20260801.json").read_text(encoding="utf-8"))
        svg_path = next(Path(ref) for ref in item["visual"]["render_recipe"]["output_refs"] if ref.endswith(".svg"))
        svg = svg_path.read_text(encoding="utf-8")
        self.assertNotIn("<polyline", svg)
        self.assertIn("监管上限", svg)
        self.assertIn("中国人寿", svg)

    def test_concept_lane_output_has_no_slope_line_and_keeps_product_blank(self):
        item = json.loads((ROOT / "content/items/data-insurance-rate-concept-lanes-20260801.json").read_text(encoding="utf-8"))
        svg_path = next(Path(ref) for ref in item["visual"]["render_recipe"]["output_refs"] if ref.endswith(".svg"))
        svg = svg_path.read_text(encoding="utf-8")
        self.assertNotIn("<polyline", svg)
        self.assertIn("未提供具体产品", svg)

    def test_review_html_is_offline_and_has_manual_boundary(self):
        html_path = ROOT / "outputs/data-medical-payment-denominator-20260801/chart.html"
        page = html_path.read_text(encoding="utf-8")
        self.assertNotIn('src="http', page)
        self.assertNotIn('href="http', page)
        self.assertNotIn("<script", page)
        self.assertIn("manual-only", page)

    def test_rendered_svg_text_stays_inside_canvas(self):
        svg_paths = sorted((ROOT / "outputs").glob("data-*/chart.svg"))
        self.assertTrue(svg_paths)
        for svg_path in svg_paths:
            with self.subTest(svg=svg_path.parent.name):
                svg = svg_path.read_text(encoding="utf-8")
                height_match = re.search(r'<svg[^>]*height="([0-9.]+)"', svg)
                self.assertIsNotNone(height_match)
                height = float(height_match.group(1))
                text_y = [float(value) for value in re.findall(r'<text[^>]* y="([0-9.]+)"', svg)]
                self.assertTrue(text_y)
                self.assertLessEqual(max(text_y), height)


if __name__ == "__main__":
    unittest.main()
