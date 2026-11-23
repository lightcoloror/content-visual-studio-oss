import importlib.util
import json
import unittest
from pathlib import Path

from temp_workspace import isolated_test_directory


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pipeline = load_module("article_visual_pipeline_editorial", ROOT / "scripts" / "article_visual_pipeline.py")
validation = load_module("design_direction_validation", ROOT / "scripts" / "design_direction_validation.py")


class EditorialFieldGuideTests(unittest.TestCase):
    def item(self):
        return {
            "primary_format": "longform",
            "visual": {
                "visual_profile": "visual/insurance-observational-advisor",
                "visual_profile_version": "0.2.0",
                "route": "text_card",
                "design_system": {
                    "principles_version": "shared-design-principles.v1",
                    "media_adapter": "article",
                    "design_direction": {
                        "direction_id": "editorial-field-guide",
                        "version": "1.0.0",
                    },
                    "communication_job": {
                        "audience": "需要理解完整流程的读者",
                        "outcome": "能按阶段执行",
                        "central_takeaway": "先判断，再按阶段推进",
                    },
                },
                "render_artifacts": [
                    {
                        "artifact_id": "editorial-article-html",
                        "media_adapter": "article",
                        "layout_intent": "sequence",
                        "renderer": "html-playwright",
                        "format": "html",
                        "theme": "editorial-field-guide",
                    }
                ],
            },
        }

    def test_reference_provenance_and_method_boundary_are_portable(self):
        methods = json.loads(
            (ROOT / "config" / "design-direction-sources.v1.json").read_text(encoding="utf-8")
        )
        source = next(
            item
            for item in methods["sources"]
            if item["id"] == "zero-code-product-guide-local-reference"
        )
        self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
        self.assertNotIn("local_path", source)
        self.assertIn("exact-palette-copy", source["not_absorbed"])
        self.assertIn("remote-google-font-dependency", source["not_absorbed"])

    def test_direction_is_explicit_and_inherits_visual_profile(self):
        contract = validation.load_design_directions()
        direction = contract["directions"]["editorial-field-guide"]
        self.assertEqual("explicit-content-item", contract["selection_policy"]["mode"])
        self.assertTrue(direction["inherits_visual_profile_tokens"])
        self.assertEqual(
            [{"id": "visual/insurance-observational-advisor", "version": "0.2.0"}],
            direction["compatible_visual_profiles"],
        )
        self.assertEqual("editorial-field-guide", direction["routes"]["article"]["artifact_theme"])
        self.assertEqual([], validation.validate_design_direction(self.item()))

    def test_theme_without_direction_fails_closed(self):
        item = self.item()
        del item["visual"]["design_system"]["design_direction"]
        errors = validation.validate_design_direction(item)
        self.assertTrue(any("require visual.design_system.design_direction" in message for _, message in errors))

    def test_data_and_photo_led_routes_are_not_eligible(self):
        data_item = self.item()
        data_item["visual"]["route"] = "data_visualization"
        self.assertTrue(validation.validate_design_direction(data_item))

        photo_item = self.item()
        photo_item["visual"]["article_visual_plan"] = {"visual_mode": "editorial-photo-mix"}
        self.assertTrue(validation.validate_design_direction(photo_item))

    def test_unmapped_visual_profile_fails_closed(self):
        item = self.item()
        item["visual"]["visual_profile"] = "visual/personal-ip-professional-trust"
        item["visual"]["visual_profile_version"] = "0.1.1"
        errors = validation.validate_design_direction(item)
        self.assertTrue(any("no semantic-token mapping" in message for _, message in errors))

    def test_social_card_requires_explicit_renderer_option_and_allowed_intent(self):
        item = self.item()
        item["visual"]["design_system"]["media_adapter"] = "social-card"
        artifact = item["visual"]["render_artifacts"][0]
        artifact.update(media_adapter="social-card", layout_intent="sequence")
        artifact.pop("theme")
        errors = validation.validate_design_direction(item)
        self.assertTrue(any("renderer_options.design_direction_id" in location for location, _ in errors))
        artifact["renderer_options"] = {"design_direction_id": "editorial-field-guide"}
        self.assertEqual([], validation.validate_design_direction(item))
        artifact["layout_intent"] = "data-chart"
        self.assertTrue(validation.validate_design_direction(item))

    def test_renderer_builds_structured_responsive_article_without_remote_fonts(self):
        markdown = """# 零基础也能执行的指南

先确定问题，再选择工具。

## 第一阶段

验证需求，不急着堆功能。

## 第二阶段

用最小流程完成一次闭环。

<div class="guide-grid"><div class="guide-card"><h3>任务</h3><p>只承担一个信息任务。</p></div></div>
"""
        rendered = pipeline.render_article_html(
            markdown, "零基础也能执行的指南", theme="editorial-field-guide"
        )
        self.assertIn('data-design-direction="editorial-field-guide"', rendered)
        self.assertEqual(2, rendered.count('class="guide-section"'))
        self.assertIn('class="guide-hero"', rendered)
        self.assertIn("@media (max-width: 720px)", rendered)
        self.assertIn("grid-template-columns: 1fr", rendered)
        self.assertNotIn("fonts.googleapis.com", rendered)

    def test_unknown_article_theme_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown article theme"):
            pipeline.render_article_html("# 标题", "标题", theme="not-registered")

    def test_editor_and_renderer_expose_versioned_direction(self):
        editor = (ROOT / "admin" / "config.yml").read_text(encoding="utf-8")
        self.assertIn("value: editorial-field-guide", editor)
        renderer_registry = json.loads((ROOT / "config" / "renderer-registry.v1.json").read_text(encoding="utf-8"))
        self.assertIn("editorial-field-guide", renderer_registry["renderers"]["html-playwright"]["themes"])

    def test_missing_or_incompatible_contract_fails_closed(self):
        missing = ROOT / "tests" / "fixtures" / "does-not-exist.json"
        errors = validation.validate_design_direction(self.item(), contract_path=missing)
        self.assertTrue(any("contract is missing" in message for _, message in errors))
        with isolated_test_directory("editorial-direction-contract") as temporary:
            incompatible = temporary / "directions.json"
            incompatible.write_text(
                json.dumps({"schema_version": "shared-design-directions.v0", "directions": {}}),
                encoding="utf-8",
            )
            validation.clear_design_direction_cache()
            errors = validation.validate_design_direction(self.item(), contract_path=incompatible)
            self.assertTrue(any("schema_version is incompatible" in message for _, message in errors))


if __name__ == "__main__":
    unittest.main()
