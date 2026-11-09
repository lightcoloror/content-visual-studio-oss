import importlib.util
import os
import shutil
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "render_content_artifacts.py"
module_spec = importlib.util.spec_from_file_location("render_content_artifacts_baoyu", MODULE_PATH)
renderer = importlib.util.module_from_spec(module_spec)
assert module_spec.loader is not None
module_spec.loader.exec_module(renderer)


class BaoyuAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT / "outputs" / ".test-runtime" / self._testMethodName
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self.input_path = self.root / "wound-article.md"
        self.output_path = self.root / "wound-article.html"
        self.receipt_path = self.root / "wound-article.receipt.json"
        self.item_path = self.root / "item.json"
        source_photo = renderer.resolve_external_file_from_env(
            "CONTENT_STUDIO_TEST_BAOYU_PHOTO", "Baoyu adapter test source photo"
        )
        self.photo_path = self.root / "photo.jpg"
        shutil.copyfile(source_photo, self.photo_path)
        antv = renderer.resolve_external_file_from_env(
            "CONTENT_STUDIO_TEST_BAOYU_INFOGRAPHIC", "Baoyu adapter test infographic layout"
        ).read_text(encoding="utf-8").strip()
        self.input_path.write_text(
            "# 什么时候需要联系家长\n\n"
            "老师只要观察敷料，不需要自行处理伤口。\n\n"
            "![[photo.jpg|孩子手臂上的敷料]]\n\n"
            "```mermaid\n"
            "flowchart LR\n"
            "  A[敷料湿透] --> B[联系家长]\n"
            "```\n\n"
            "```infographic\n"
            f"{antv}\n"
            "```\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def item(self) -> dict:
        return {
            "content_id": "wound-baoyu-adapter-fixture",
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
                        "alt_text": "孩子手臂上的敷料",
                        "rights_status": "verified",
                        "privacy_status": "not-applicable",
                    }
                ],
                "render_artifacts": [
                    {
                        "artifact_id": "wound-article-baoyu",
                        "output_family": "article",
                        "media_adapter": "article",
                        "layout_intent": "process",
                        "renderer": "baoyu-md",
                        "format": "html",
                        "status": "planned",
                        "theme": "default",
                        "input_refs": [str(self.input_path)],
                        "asset_ids": ["wound-photo"],
                        "ref": str(self.output_path),
                        "receipt_ref": str(self.receipt_path),
                        "renderer_options": {
                            "explicit_adapter": True,
                            "cache_ref": str(self.root / "cache"),
                        },
                    }
                ],
            },
        }

    def test_baoyu_remains_explicit_item_only(self) -> None:
        artifact = self.item()["visual"]["render_artifacts"][0]
        artifact["renderer_options"]["explicit_adapter"] = False
        with self.assertRaisesRegex(renderer.ArtifactError, "off by default"):
            renderer._renderer_config(artifact)

    def test_remote_markdown_image_is_rejected(self) -> None:
        self.input_path.write_text(
            "# Local-only\n\n![remote](https://example.com/image.jpg)\n",
            encoding="utf-8",
        )
        item = self.item()
        artifact = item["visual"]["render_artifacts"][0]
        config = renderer._renderer_config(artifact)
        with self.assertRaisesRegex(renderer.ArtifactError, "remote image downloads are disabled"):
            renderer._render_baoyu_md(item, self.item_path, artifact, config)

    @unittest.skipUnless(os.environ.get("RUN_BAOYU_INTEGRATION") == "1", "opt-in Baoyu integration")
    def test_static_blocks_and_deterministic_cache(self) -> None:
        item = self.item()
        artifact = item["visual"]["render_artifacts"][0]
        config = renderer._renderer_config(artifact)

        first = renderer._render_baoyu_md(item, self.item_path, artifact, config)
        second = renderer._render_baoyu_md(item, self.item_path, artifact, config)
        self.assertEqual(first["mermaid_cache"][0]["hash"], second["mermaid_cache"][0]["hash"])
        self.assertEqual(first["mermaid_cache"][0]["sha256"], second["mermaid_cache"][0]["sha256"])
        self.assertTrue(second["mermaid_cache"][0]["cached"])
        self.assertEqual(first["antv_cache"][0]["sha256"], second["antv_cache"][0]["sha256"])
        self.assertTrue(second["antv_cache"][0]["cached"])

        receipt = renderer._render(item, self.item_path, artifact)
        html = self.output_path.read_text(encoding="utf-8")
        self.assertIn("<!doctype html>", html.casefold())
        self.assertIn("老师只要观察敷料", html)
        self.assertNotIn("```infographic", html)
        self.assertNotIn("```mermaid", html)
        self.assertNotIn('<pre class="mermaid">', html)
        self.assertEqual("review-required", receipt["qa"]["result"])
        self.assertTrue(all(check["status"] == "pass" for check in receipt["qa"]["hard_checks"]))


if __name__ == "__main__":
    unittest.main()
