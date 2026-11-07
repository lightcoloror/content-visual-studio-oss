import importlib.util
import unittest
import urllib.parse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "article_visual_pipeline.py"
module_spec = importlib.util.spec_from_file_location("article_visual_pipeline", MODULE_PATH)
pipeline = importlib.util.module_from_spec(module_spec)
assert module_spec.loader is not None
module_spec.loader.exec_module(pipeline)


class ArticleVisualPipelineTests(unittest.TestCase):
    def item(self, rights_status="verified"):
        return {
            "content_id": "health-wound-article",
            "visual": {
                "assets": [
                    {
                        "ref": "assets/teacher-call.svg",
                        "asset_type": "stock-photo",
                        "rights_status": rights_status,
                        "source_id": "pexels",
                        "usage_scope": "commercial",
                        "attribution_required": False,
                        "release_status": "not-applicable",
                        "landing_page_url": "https://www.pexels.com/photo/123/",
                        "license": "Pexels License",
                        "license_url": "https://www.pexels.com/license/",
                        "alt_text": "老师发现敷料异常后联系家长",
                        "fit_strategy": "focal-cover",
                        "focal_point": {"x": 0.25, "y": 0.4},
                        "safe_crop": {"x": 0.1, "y": 0.1, "width": 0.7, "height": 0.8},
                        "subject_bounds": {"x": 0.2, "y": 0.2, "width": 0.35, "height": 0.5},
                    }
                ],
                "article_visual_plan": {
                    "article_ref": "article.md",
                    "workflow": "human-in-the-loop",
                    "ai_generation_policy": "explicit-opt-in-only",
                    "slots": [
                        {
                            "slot_id": "teacher-call",
                            "anchor": {"kind": "heading", "value": "什么时候联系家长"},
                            "purpose": "解释联系家长的动作",
                            "media_role": "explanatory",
                            "route": "stock-photo",
                            "status": "selected",
                            "layout": "text-left",
                            "visual_brief": {
                                "metaphor": "异常信号触发联系",
                                "composition": "老师查看敷料，手机位于动作方向一侧",
                                "central_action": "老师联系家长",
                                "max_labels": 0,
                            },
                            "search": {
                                "query_zh": "老师 联系 家长",
                                "query_en": "teacher calling parent kindergarten",
                                "negative_terms": ["hospital surgery"],
                                "preferred_sources": ["openverse"],
                            },
                            "selected_asset_ref": "assets/teacher-call.svg",
                            "caption": "发现异常时，请先联系家长。",
                        }
                    ],
                },
            },
        }

    def test_openverse_query_uses_modifiable_commercial_licenses(self):
        url = pipeline.build_openverse_url("teacher calling parent", per_page=8)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(["by,by-sa,cc0,pdm"], query["license"])
        self.assertEqual(["false"], query["mature"])
        self.assertEqual(["8"], query["page_size"])

    def test_candidate_collection_filters_small_and_negative_results(self):
        def fake_fetcher(_url):
            return {
                "results": [
                    {"id": "small", "title": "Teacher", "width": 320, "height": 240},
                    {"id": "wrong", "title": "Hospital surgery", "width": 1600, "height": 1200},
                    {
                        "id": "good",
                        "title": "Teacher calling a parent",
                        "creator": "Example",
                        "width": 1600,
                        "height": 1200,
                        "url": "https://example.test/image.jpg",
                        "thumbnail": "https://example.test/thumb.jpg",
                        "foreign_landing_url": "https://example.test/source",
                        "license": "by",
                    },
                ]
            }

        manifest = pipeline.collect_openverse_candidates(self.item(), per_slot=3, min_width=800, fetcher=fake_fetcher)
        candidates = manifest["slots"][0]["candidates"]
        self.assertEqual(["openverse:good"], [candidate["candidate_id"] for candidate in candidates])
        self.assertEqual("needs-review", candidates[0]["rights_status"])
        self.assertEqual("openverse", candidates[0]["candidate_source_id"])
        self.assertEqual("human-review-required", manifest["selection_boundary"])

    def test_insert_selected_visual_after_heading(self):
        markdown = "# 标题\n\n## 什么时候联系家长\n\n出现以下情况时联系。\n"
        output = ROOT / "outputs" / "_test-article-with-visuals.md"
        rendered = pipeline.insert_selected_visuals(self.item(), markdown, output)
        heading_position = rendered.index("## 什么时候联系家长")
        figure_position = rendered.index('data-visual-slot-id="teacher-call"')
        paragraph_position = rendered.index("出现以下情况时联系。")
        self.assertLess(heading_position, figure_position)
        self.assertLess(figure_position, paragraph_position)
        self.assertIn("<figcaption>发现异常时，请先联系家长。</figcaption>", rendered)
        self.assertIn("--visual-focus-x:25%", rendered)
        self.assertIn("--visual-focus-y:40%", rendered)
        self.assertIn('data-safe-crop="0.1000,0.1000,0.7000,0.8000"', rendered)
        self.assertIn('data-central-action="老师联系家长"', rendered)
        self.assertIn('data-max-labels="0"', rendered)

    def test_existing_slot_marker_is_not_duplicated(self):
        markdown = "## 什么时候联系家长\n\n<!-- visual-slot:teacher-call -->\n"
        output = ROOT / "outputs" / "_test-article-with-visuals.md"
        rendered = pipeline.insert_selected_visuals(self.item(), markdown, output)
        self.assertEqual(1, rendered.count("<!-- visual-slot:teacher-call -->"))

    def test_unverified_asset_cannot_be_inserted(self):
        markdown = "## 什么时候联系家长\n"
        output = ROOT / "outputs" / "_test-article-with-visuals.md"
        with self.assertRaisesRegex(ValueError, "rights are not verified"):
            pipeline.insert_selected_visuals(self.item("needs-review"), markdown, output)

    def test_real_photo_rejects_in_image_labels(self):
        item = self.item()
        item["visual"]["article_visual_plan"]["slots"][0]["visual_brief"]["max_labels"] = 1
        markdown = "## 什么时候联系家长\n"
        output = ROOT / "outputs" / "_test-article-with-visuals.md"
        with self.assertRaisesRegex(ValueError, "must use max_labels=0"):
            pipeline.insert_selected_visuals(item, markdown, output)

    def test_required_attribution_is_rendered_with_source_and_license(self):
        item = self.item()
        asset = item["visual"]["assets"][0]
        asset["attribution_required"] = True
        asset["attribution"] = "Photo by Example"
        markdown = "## 什么时候联系家长\n"
        output = ROOT / "outputs" / "_test-article-with-visuals.md"
        rendered = pipeline.insert_selected_visuals(item, markdown, output)
        self.assertIn("Photo by Example", rendered)
        self.assertIn("https://www.pexels.com/photo/123/", rendered)
        self.assertIn("https://www.pexels.com/license/", rendered)

    def test_aggregator_cannot_be_used_as_final_source(self):
        item = self.item()
        item["visual"]["assets"][0]["source_id"] = "openverse"
        markdown = "## 什么时候联系家长\n"
        output = ROOT / "outputs" / "_test-article-with-visuals.md"
        with self.assertRaisesRegex(ValueError, "original provider"):
            pipeline.insert_selected_visuals(item, markdown, output)

    def test_responsive_html_renderer_preserves_figure_blocks(self):
        markdown = "# 标题\n\n<figure class=\"article-visual article-visual--text-left\"><img src=\"icon.svg\" alt=\"说明图标\"></figure>\n\n正文。\n"
        page = pipeline.render_article_html(markdown, "标题")
        self.assertIn('article-visual--text-left', page)
        self.assertIn('<img src="icon.svg" alt="说明图标">', page)
        self.assertIn('@media (max-width:640px)', page)
        self.assertIn('<article><h1>标题</h1>', page)

    def test_review_page_keeps_license_warning_and_source_link(self):
        manifest = {
            "content_id": "article-one",
            "slots": [
                {
                    "slot_id": "slot-one",
                    "purpose": "解释动作",
                    "candidates": [
                        {
                            "title": "Candidate",
                            "creator": "Creator",
                            "ref": "https://example.test/image.jpg",
                            "thumbnail": "https://example.test/thumb.jpg",
                            "landing_page_url": "https://example.test/source",
                            "license": "by",
                        }
                    ],
                }
            ],
        }
        page = pipeline.render_review_html(manifest)
        self.assertIn("候选图片尚未通过权利复核", page)
        self.assertIn("https://example.test/source", page)
        self.assertIn("核验原始页面", page)


if __name__ == "__main__":
    unittest.main()
