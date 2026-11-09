import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
# The public checkout keeps scripts/ and schemas/ beside the tests/ directory.
WORKSPACE = ROOT
MODULE_PATH = WORKSPACE / "scripts" / "article_visual_validation.py"
# The real validator imports studio_paths as a top-level module from scripts/.
if str(MODULE_PATH.parent) not in sys.path:
    sys.path.insert(0, str(MODULE_PATH.parent))
module_spec = importlib.util.spec_from_file_location("article_visual_validation", MODULE_PATH)
validation = importlib.util.module_from_spec(module_spec)
assert module_spec.loader is not None
module_spec.loader.exec_module(validation)


class ArticleVisualValidationTests(unittest.TestCase):
    def item(self):
        return {
            "visual": {
                "assets": [
                    {
                        "ref": "assets/teacher-call.svg",
                        "asset_type": "illustration",
                        "rights_status": "verified",
                        "alt_text": "老师发现敷料异常后联系家长",
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
                            "purpose": "把通知动作放在对应说明旁边",
                            "media_role": "explanatory",
                            "route": "icon",
                            "status": "selected",
                            "layout": "text-left",
                            "search": {
                                "query_zh": "老师 电话 家长",
                                "preferred_sources": ["iconify"],
                            },
                            "selected_asset_ref": "assets/teacher-call.svg",
                        }
                    ],
                },
            }
        }

    def test_valid_plan_passes(self):
        self.assertEqual([], validation.validate_article_visual_plan(self.item()))

    def test_article_plan_is_accepted_by_content_schema(self):
        schema = json.loads((WORKSPACE / "schemas" / "content-item.schema.json").read_text(encoding="utf-8"))
        fixture = json.loads((ROOT / "fixtures" / "wechat-article-format-v1" / "content-item.synthetic.json").read_text(encoding="utf-8"))
        fixture["visual"]["article_visual_plan"] = self.item()["visual"]["article_visual_plan"]
        errors = list(Draft202012Validator(schema).iter_errors(fixture))
        self.assertEqual([], errors)

    def test_shared_design_context_is_accepted_and_versioned(self):
        schema = json.loads((WORKSPACE / "schemas" / "content-item.schema.json").read_text(encoding="utf-8"))
        fixture = json.loads((ROOT / "fixtures" / "wechat-article-format-v1" / "content-item.synthetic.json").read_text(encoding="utf-8"))
        fixture["visual"]["design_system"] = {
            "principles_version": "shared-design-principles.v1",
            "media_adapter": "article",
            "communication_job": {
                "audience": "需要快速判断何时联系家长的老师",
                "outcome": "能识别需要联系家长的敷料异常",
                "central_takeaway": "按可观察信号联系家长，不代替医疗判断",
            },
        }
        validator = Draft202012Validator(schema)
        self.assertEqual([], list(validator.iter_errors(fixture)))
        fixture["visual"]["design_system"]["principles_version"] = "unversioned"
        self.assertTrue(list(validator.iter_errors(fixture)))

    def test_huashu_method_contracts_are_structured_and_fail_closed(self):
        schema = json.loads((WORKSPACE / "schemas" / "content-item.schema.json").read_text(encoding="utf-8"))
        fixture = json.loads((ROOT / "fixtures" / "wechat-article-format-v1" / "content-item.synthetic.json").read_text(encoding="utf-8"))
        fixture["visual"]["brand_spec"] = {
            "schema_version": "brand-spec.v1",
            "subject": "观察型顾问",
            "status": "ready",
            "official_source_refs": [],
            "asset_refs": {"logos": [], "product_images": [], "ui_screenshots": []},
            "palette_source": "visual/insurance-observational-advisor@0.2.0",
            "typography": ["Microsoft YaHei"],
            "signature_details": ["深青结构线", "陶红观察标签"],
            "forbidden_patterns": ["销售腔", "无依据风险红"],
            "mood_keywords": ["克制", "具体"],
            "missing_assets": [],
        }
        fixture["visual"]["design_exploration"] = {
            "schema_version": "design-exploration.v1",
            "mode": "optional",
            "trigger": "ambiguous-direction",
            "status": "rendered",
            "directions": [
                {"direction_id": "editorial", "rationale": "适合连续阅读", "artifact_ref": "outputs/editorial.html", "status": "candidate"},
                {"direction_id": "explanatory", "rationale": "适合快速判断", "artifact_ref": "outputs/explanatory.html", "status": "candidate"},
            ],
        }
        score = lambda value, evidence: {"score": value, "evidence": evidence}
        fixture["qa"]["design_review"] = {
            "schema_version": "huashu-derived-design-review.v1",
            "status": "pass",
            "artifact_refs": ["outputs/explanatory.html"],
            "dimensions": {
                "philosophy_alignment": score(8, "符合观察型顾问视觉角色"),
                "visual_hierarchy": score(9, "中心结论优先"),
                "craft_quality": score(8, "间距和对齐稳定"),
                "functionality": score(9, "能完成判断任务"),
                "originality": score(7, "避免通用卡片模板"),
            },
            "keep": ["中心结论"],
            "fix": [],
            "quick_wins": ["复核最终署名"],
        }
        validator = Draft202012Validator(schema)
        self.assertEqual([], list(validator.iter_errors(fixture)))
        fixture["qa"]["design_review"]["dimensions"]["originality"]["score"] = 11
        self.assertTrue(list(validator.iter_errors(fixture)))

    def test_source_registry_matches_schema_source_ids(self):
        schema = json.loads((WORKSPACE / "schemas" / "content-item.schema.json").read_text(encoding="utf-8"))
        registry = json.loads((ROOT / "config" / "visual-source-registry.json").read_text(encoding="utf-8"))
        schema_sources = set(schema["$defs"]["articleVisualSearch"]["properties"]["preferred_sources"]["items"]["enum"])
        self.assertEqual(schema_sources, set(registry["sources"]))

    def test_selected_asset_requires_verified_rights(self):
        item = self.item()
        item["visual"]["assets"][0]["rights_status"] = "needs-review"
        errors = validation.validate_article_visual_plan(item)
        self.assertTrue(any("verified rights" in message for _, message in errors))

    def test_stock_photo_cannot_be_factual_evidence(self):
        item = self.item()
        slot = item["visual"]["article_visual_plan"]["slots"][0]
        slot["media_role"] = "evidence"
        slot["route"] = "stock-photo"
        errors = validation.validate_article_visual_plan(item)
        self.assertTrue(any("cannot serve as factual evidence" in message for _, message in errors))

    def test_generated_image_requires_explicit_opt_in(self):
        item = self.item()
        slot = item["visual"]["article_visual_plan"]["slots"][0]
        slot["route"] = "generated-image"
        errors = validation.validate_article_visual_plan(item)
        self.assertTrue(any("explicit user opt-in" in message for _, message in errors))

    def test_editorial_photo_mix_rejects_icon_only_plan(self):
        item = self.item()
        item["visual"]["article_visual_plan"]["visual_mode"] = "editorial-photo-mix"
        errors = validation.validate_article_visual_plan(item)
        self.assertTrue(any("requires a selected photo" in message for _, message in errors))

    def test_editorial_photo_mix_accepts_photo_led_plan(self):
        item = self.item()
        plan = item["visual"]["article_visual_plan"]
        plan["visual_mode"] = "editorial-photo-mix"
        plan["slots"][0]["route"] = "stock-photo"
        item["visual"]["assets"][0].update(
            {
                "asset_type": "stock-photo",
                "source_id": "pexels",
                "usage_scope": "commercial",
                "attribution_required": False,
                "release_status": "not-applicable",
                "landing_page_url": "https://www.pexels.com/photo/123/",
                "license": "Pexels License",
                "license_url": "https://www.pexels.com/license/",
            }
        )
        self.assertEqual([], validation.validate_article_visual_plan(item))

    def test_selected_stock_photo_requires_rights_record(self):
        item = self.item()
        asset = item["visual"]["assets"][0]
        asset["asset_type"] = "stock-photo"
        errors = validation.validate_article_visual_plan(item)
        self.assertTrue(any("registered source_id" in message for _, message in errors))
        self.assertTrue(any("confirmed commercial scope" in message for _, message in errors))

    def test_aggregator_cannot_be_final_stock_source(self):
        item = self.item()
        asset = item["visual"]["assets"][0]
        asset.update(
            {
                "asset_type": "stock-photo",
                "source_id": "openverse",
                "usage_scope": "commercial",
                "attribution_required": False,
                "release_status": "not-applicable",
                "landing_page_url": "https://example.test/original",
                "license": "CC BY 4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
            }
        )
        errors = validation.validate_article_visual_plan(item)
        self.assertTrue(any("discovery layer" in message for _, message in errors))

    def test_required_attribution_must_be_present(self):
        item = self.item()
        asset = item["visual"]["assets"][0]
        asset.update(
            {
                "asset_type": "stock-photo",
                "source_id": "cdc-phil",
                "usage_scope": "commercial",
                "attribution_required": True,
                "release_status": "not-applicable",
                "landing_page_url": "https://phil.cdc.gov/Details.aspx?pid=1",
                "license": "CDC PHIL item terms",
                "license_url": "https://www.cdc.gov/other/agencymaterials.html",
            }
        )
        errors = validation.validate_article_visual_plan(item)
        self.assertTrue(any("attribution text is missing" in message for _, message in errors))

    def test_duplicate_slot_ids_fail(self):
        item = self.item()
        duplicate = copy.deepcopy(item["visual"]["article_visual_plan"]["slots"][0])
        item["visual"]["article_visual_plan"]["slots"].append(duplicate)
        errors = validation.validate_article_visual_plan(item)
        self.assertTrue(any("duplicates article visual slot" in message for _, message in errors))


if __name__ == "__main__":
    unittest.main()
