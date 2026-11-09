import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "semantic_visual_validation.py"
ITEM_PATH = ROOT / "tests" / "fixtures" / "semantic-visual-map" / "item.json"

module_spec = importlib.util.spec_from_file_location("semantic_visual_validation", MODULE_PATH)
semantic_visuals = importlib.util.module_from_spec(module_spec)
assert module_spec.loader is not None
module_spec.loader.exec_module(semantic_visuals)


class SemanticVisualMapTests(unittest.TestCase):
    def load_item(self):
        return json.loads(ITEM_PATH.read_text(encoding="utf-8"))

    def test_current_infographic_variants_are_semantically_colocated(self):
        errors = semantic_visuals.validate_semantic_visual_map(self.load_item(), ITEM_PATH)
        self.assertEqual([], errors)

    def test_html_infographic_requires_semantic_map(self):
        item = self.load_item()
        item["visual"].pop("semantic_visual_map", None)
        errors = semantic_visuals.validate_semantic_visual_map(item, ITEM_PATH)
        self.assertTrue(any("require semantic visual bindings" in message for _, message in errors))

    def test_corner_asset_does_not_satisfy_colocation(self):
        item = self.load_item()
        broken = copy.deepcopy(item)
        binding = broken["visual"]["semantic_visual_map"][0]["bindings"][0]
        binding["visual_ref"] = str(
            ROOT / "tests" / "fixtures" / "semantic-visual-map" / "assets" / "corner-callout.svg"
        )
        errors = semantic_visuals.validate_semantic_visual_map(broken, ITEM_PATH)
        self.assertTrue(any("not colocated" in message for _, message in errors))

    def test_each_variant_covers_every_cognitive_anchor(self):
        item = self.load_item()
        broken = copy.deepcopy(item)
        broken["visual"]["semantic_visual_map"][1]["bindings"] = [
            binding
            for binding in broken["visual"]["semantic_visual_map"][1]["bindings"]
            if binding.get("anchor_index") != 2
        ]
        errors = semantic_visuals.validate_semantic_visual_map(broken, ITEM_PATH)
        self.assertTrue(any("without explanatory visuals" in message for _, message in errors))


if __name__ == "__main__":
    unittest.main()
