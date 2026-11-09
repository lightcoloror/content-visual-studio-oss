import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "visual_asset_routing.py"
ITEM_PATH = ROOT / "fixtures" / "wechat-article-format-v1" / "content-item.synthetic.json"

module_spec = importlib.util.spec_from_file_location("visual_asset_routing", MODULE_PATH)
visual_routing = importlib.util.module_from_spec(module_spec)
assert module_spec.loader is not None
module_spec.loader.exec_module(visual_routing)


class AiImageGenerationOptInTests(unittest.TestCase):
    def load_item(self):
        return json.loads(ITEM_PATH.read_text(encoding="utf-8"))

    def test_general_visual_requests_do_not_enable_generation(self):
        requests = [
            "做一张信息图",
            "给文章做封面图",
            "配一些插图",
            "搜索免费商用图片",
            "使用相关 SVG 图标",
            "请生成一张图片作为封面",
            "这次走图片生成路线",
        ]
        for request in requests:
            with self.subTest(request=request):
                decision = visual_routing.resolve_ai_image_generation(request)
                self.assertFalse(decision["allowed"])
                self.assertEqual("use_non_generated_visual_route", decision["decision"])

    def test_explicit_generation_phrases_enable_generation(self):
        requests = [
            "请让模型生成图片作为封面",
            "这次明确走 AI 生图路线",
            "请用AI生图做两张候选",
        ]
        for request in requests:
            with self.subTest(request=request):
                decision = visual_routing.resolve_ai_image_generation(request)
                self.assertTrue(decision["allowed"])
                self.assertEqual("allow_ai_image_generation_route", decision["decision"])

    def test_generated_asset_without_request_evidence_is_rejected(self):
        item = self.load_item()
        broken = copy.deepcopy(item)
        broken["visual"]["assets"].append(
            {
                "asset_type": "generated-image",
                "ref": "assets/synthetic-generated.png",
                "rights_status": "needs-review",
                "privacy_status": "not-applicable",
            }
        )
        errors = visual_routing.validate_ai_image_generation_opt_in(broken)
        self.assertTrue(any("explicit user opt-in" in message for _, message in errors))

    def test_exact_request_quote_allows_generated_asset(self):
        item = self.load_item()
        allowed = copy.deepcopy(item)
        allowed["visual"]["assets"].append(
            {
                "asset_type": "generated-image",
                "ref": "assets/synthetic-generated.png",
                "rights_status": "needs-review",
                "privacy_status": "not-applicable",
            }
        )
        allowed["visual"]["ai_image_generation"] = {
            "policy": "explicit-opt-in-only",
            "explicit_user_request": True,
            "recommendation_status": "recommended",
            "recommendation_reason": "现有素材无法表达所需的抽象关系",
            "request_text": "请让模型生成图片作为封面",
            "matched_trigger": "模型生成图片",
        }
        self.assertEqual([], visual_routing.validate_ai_image_generation_opt_in(allowed))

    def test_recommendation_alone_does_not_authorize_generated_asset(self):
        item = self.load_item()
        item["visual"]["assets"].append(
            {
                "asset_type": "generated-image",
                "ref": "assets/synthetic-generated.png",
                "rights_status": "needs-review",
                "privacy_status": "not-applicable",
            }
        )
        item["visual"]["ai_image_generation"] = {
            "policy": "explicit-opt-in-only",
            "explicit_user_request": False,
            "recommendation_status": "recommended",
            "recommendation_reason": "可以建议，但用户尚未授权",
        }
        errors = visual_routing.validate_ai_image_generation_opt_in(item)
        self.assertTrue(any("explicitly requested" in message for _, message in errors))


if __name__ == "__main__":
    unittest.main()
