import os
import sys
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from render_content_artifacts import _image_metrics, _render_antv  # noqa: E402
from slot_budget_validation import (  # noqa: E402
    load_json,
    validate_antv_budget,
    validate_budget_registry_coverage,
)


FIXTURE_ROOT = ROOT / "fixtures" / "antv"
BUDGETS = load_json(ROOT / "config" / "slot-budgets.v1.json")["antv"]["templates"]
RENDERER = load_json(ROOT / "config" / "renderer-registry.v1.json")["renderers"]["antv-infographic"]


class AntvArtifactPipelineTests(unittest.TestCase):
    def test_every_allowlisted_template_has_a_budget_and_fixture(self) -> None:
        self.assertEqual(validate_budget_registry_coverage(), [])
        self.assertEqual(len(BUDGETS), 8)
        for template, budget in BUDGETS.items():
            fixture = FIXTURE_ROOT / f"{template}.ifgc"
            self.assertTrue(fixture.exists(), template)
            self.assertEqual(
                validate_antv_budget(fixture, template, budget["layout_intent"]),
                [],
                template,
            )

    @unittest.skipUnless(
        os.environ.get("RUN_VISUAL_INTEGRATION") == "1",
        "set RUN_VISUAL_INTEGRATION=1 for Chromium pixel acceptance",
    )
    def test_eight_chinese_templates_render_to_nonblank_chromium_png(self) -> None:
        item = {"content_id": "antv-template-acceptance"}
        output_root = ROOT / "outputs" / ".test-runtime" / "antv-eight-templates"
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            for template, budget in BUDGETS.items():
                output = output_root / f"{template}.png"
                artifact = {
                    "artifact_id": template,
                    "renderer": "antv-infographic",
                    "format": "png",
                    "layout_intent": budget["layout_intent"],
                    "template": template,
                    "input_refs": [str(FIXTURE_ROOT / f"{template}.ifgc")],
                    "ref": str(output),
                    "dimensions": {"width": 800, "height": 1000},
                    "renderer_options": {"background": "#F7F8F5"},
                }
                details = _render_antv(item, ROOT / "content" / "items" / "fixture.json", artifact, RENDERER)
                self.assertIn("Microsoft YaHei", details["svg_text"], template)
                self.assertNotIn("assets.antv.antgroup.com", details["svg_text"], template)
                self.assertTrue(any("\u4e00" <= char <= "\u9fff" for char in details["svg_text"]), template)
                with Image.open(output) as image:
                    self.assertEqual(image.size, (800, 1000), template)
                _, _, nonblank_ratio = _image_metrics(output)
                self.assertGreaterEqual(nonblank_ratio, 0.01, template)
        finally:
            for child in output_root.iterdir():
                if child.is_file():
                    child.unlink()
            output_root.rmdir()


if __name__ == "__main__":
    unittest.main()
