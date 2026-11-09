import importlib.util
import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "render_content_artifacts.py"
module_spec = importlib.util.spec_from_file_location("render_content_artifacts_marp", MODULE_PATH)
renderer = importlib.util.module_from_spec(module_spec)
assert module_spec.loader is not None
module_spec.loader.exec_module(renderer)


class MarpAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT / "outputs" / ".test-runtime" / self._testMethodName
        self.root.mkdir(parents=True, exist_ok=True)
        for child in self.root.iterdir():
            if child.is_file():
                child.unlink()
        self.input_path = self.root / "cover.md"
        self.output_path = self.root / "cover.png"
        self.receipt_path = self.root / "cover.receipt.json"
        self.item_path = self.root / "item.json"
        self.photo_path = renderer.resolve_external_file_from_env(
            "CONTENT_STUDIO_TEST_MARP_PHOTO", "Marp adapter test cover photo"
        )
        self.input_path.write_text(
            "# 什么时候需要联系家长\n\n敷料湿透、松脱或出现警示信号时联系。\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        for child in self.root.iterdir():
            if child.is_file():
                child.unlink()
        self.root.rmdir()

    def item(self) -> dict:
        return {
            "content_id": "wound-marp-adapter-fixture",
            "gates": {
                "fact": {"status": "pass"},
                "rights": {"status": "pass"},
                "privacy": {"status": "pass"},
            },
            "qa": {"human_review": {"status": "required"}},
            "visual": {
                "assets": [
                    {
                        "asset_id": "wound-photo",
                        "asset_type": "stock-photo",
                        "ref": str(self.photo_path),
                        "rights_status": "verified",
                        "privacy_status": "not-applicable",
                        "safe_crop": {"x": 0.08, "y": 0.06, "width": 0.84, "height": 0.86},
                        "focal_point": {"x": 0.46, "y": 0.42},
                        "fit_strategy": "focal-cover",
                    }
                ],
                "render_artifacts": [
                    {
                        "artifact_id": "wound-cover",
                        "output_family": "slide",
                        "media_adapter": "pptx",
                        "layout_intent": "quote-hero",
                        "renderer": "marp",
                        "format": "png",
                        "status": "planned",
                        "theme": "cover-photo-overlay",
                        "dimensions": {"width": 1080, "height": 1350},
                        "input_refs": [str(self.input_path)],
                        "asset_ids": ["wound-photo"],
                        "ref": str(self.output_path),
                        "receipt_ref": str(self.receipt_path),
                        "renderer_options": {
                            "explicit_adapter": True,
                            "background_asset_id": "wound-photo",
                            "copy": {
                                "title": "什么时候需要联系家长",
                                "supporting_copy": "敷料湿透、松脱或出现警示信号时联系。",
                                "source": "伤口指南与证据索引",
                            },
                        },
                    }
                ],
            },
        }

    def test_marp_budget_rejects_long_title(self) -> None:
        item = self.item()
        artifact = item["visual"]["render_artifacts"][0]
        artifact["renderer_options"]["copy"]["title"] = "这是一段明显超过二十二个汉字预算而且不应该进入渲染器的封面标题"
        errors = renderer.validate_marp_budget(artifact)
        self.assertTrue(any("title exceeds" in error for error in errors))

    def test_marp_remains_explicit_item_only(self) -> None:
        artifact = self.item()["visual"]["render_artifacts"][0]
        artifact["renderer_options"]["explicit_adapter"] = False
        with self.assertRaisesRegex(renderer.ArtifactError, "off by default"):
            renderer._renderer_config(artifact)

    @unittest.skipUnless(os.environ.get("RUN_MARP_INTEGRATION") == "1", "opt-in Marp integration")
    def test_renders_vertical_cover_and_receipt(self) -> None:
        self.assertTrue(self.photo_path.exists())
        item = self.item()
        artifact = item["visual"]["render_artifacts"][0]
        receipt = renderer._render(item, self.item_path, artifact)
        self.assertTrue(self.output_path.exists())
        self.assertTrue(self.receipt_path.exists())
        self.assertEqual(1080, receipt["output"]["width"])
        self.assertEqual(1350, receipt["output"]["height"])
        self.assertEqual("review-required", receipt["qa"]["result"])
        self.assertTrue(all(check["status"] == "pass" for check in receipt["qa"]["hard_checks"]))


if __name__ == "__main__":
    unittest.main()
