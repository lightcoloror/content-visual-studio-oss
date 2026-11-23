import hashlib
import importlib.util
import json
import os
import shutil
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "render_content_artifacts.py"
module_spec = importlib.util.spec_from_file_location("render_content_artifacts_obsidian", MODULE_PATH)
renderer = importlib.util.module_from_spec(module_spec)
assert module_spec.loader is not None
module_spec.loader.exec_module(renderer)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ObsidianPreviewAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT / "outputs" / ".test-runtime" / self._testMethodName
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self.output_path = self.root / "obsidian-infographic-preview.zip"
        self.receipt_path = self.root / "obsidian-infographic-preview.receipt.json"
        self.item_path = self.root / "item.json"

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def item(self) -> dict:
        return {
            "content_id": "obsidian-preview-adapter-fixture",
            "gates": {
                "fact": {"status": "pass"},
                "rights": {"status": "pass"},
                "privacy": {"status": "pass"},
            },
            "qa": {"human_review": {"status": "required"}},
            "visual": {
                "assets": [],
                "render_artifacts": [
                    {
                        "artifact_id": "obsidian-preview-package",
                        "output_family": "web",
                        "media_adapter": "web",
                        "layout_intent": "data-chart",
                        "renderer": "obsidian-infographic-preview",
                        "format": "zip",
                        "status": "planned",
                        "input_refs": [],
                        "asset_ids": [],
                        "ref": str(self.output_path),
                        "receipt_ref": str(self.receipt_path),
                        "renderer_options": {"explicit_adapter": True},
                    }
                ],
            },
        }

    def test_preview_remains_explicit_item_only(self) -> None:
        artifact = self.item()["visual"]["render_artifacts"][0]
        artifact["renderer_options"]["explicit_adapter"] = False
        with self.assertRaisesRegex(renderer.ArtifactError, "off by default"):
            renderer._renderer_config(artifact)

    def test_preview_refuses_vault_destination(self) -> None:
        item = self.item()
        artifact = item["visual"]["render_artifacts"][0]
        artifact["ref"] = str(self.root / ".obsidian" / "plugins" / "plugin.zip")
        config = renderer._renderer_config(artifact)
        with self.assertRaisesRegex(renderer.ArtifactError, "cannot write into"):
            renderer._render_obsidian_preview(item, self.item_path, artifact, config)

    @unittest.skipUnless(
        os.environ.get("RUN_OBSIDIAN_PREVIEW_INTEGRATION") == "1",
        "opt-in Obsidian preview integration",
    )
    def test_builds_deterministic_review_only_package(self) -> None:
        item = self.item()
        artifact = item["visual"]["render_artifacts"][0]

        first = renderer._render(item, self.item_path, artifact)
        first_hash = sha256(self.output_path)
        second = renderer._render(item, self.item_path, artifact)
        second_hash = sha256(self.output_path)
        self.assertEqual(first_hash, second_hash)
        self.assertEqual(first["output"]["sha256"], second["output"]["sha256"])
        self.assertEqual("review-required", second["qa"]["result"])
        self.assertTrue(all(check["status"] == "pass" for check in second["qa"]["hard_checks"]))

        with zipfile.ZipFile(self.output_path) as archive:
            self.assertEqual(
                sorted(archive.namelist()),
                sorted(["BUILD_RECEIPT.json", "LICENSE", "main.js", "manifest.json", "styles.css"]),
            )
            evidence = json.loads(archive.read("BUILD_RECEIPT.json"))
        self.assertEqual("MIT", evidence["license_metadata"]["package_json"])
        self.assertEqual("ISC", evidence["license_metadata"]["license_file_detected"])
        self.assertTrue(evidence["license_metadata"]["review_required"])
        self.assertTrue(any("MIT" in note and "ISC" in note for note in second["notes"]))


if __name__ == "__main__":
    unittest.main()
