import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
sys.path.insert(0, str(ROOT / "scripts"))

from render_artifact_validation import validate_render_artifacts  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RenderArtifactValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT / "outputs" / ".test-runtime" / self._testMethodName
        self.root.mkdir(parents=True, exist_ok=True)
        for child in self.root.iterdir():
            if child.is_file():
                child.unlink()
        self.item_path = self.root / "item.json"
        self.input_path = self.root / "input.md"
        self.asset_path = self.root / "asset.jpg"
        self.output_path = self.root / "output.html"
        self.receipt_path = self.root / "output.receipt.json"
        self.input_path.write_text("# Input\n", encoding="utf-8")
        self.asset_path.write_bytes(b"rights-cleared-test-asset")

    def tearDown(self) -> None:
        for child in self.root.iterdir():
            if child.is_file():
                child.unlink()
        self.root.rmdir()

    def base_item(self) -> dict:
        return {
            "content_id": "artifact-validation-fixture",
            "gates": {
                "fact": {"status": "pass"},
                "rights": {"status": "pass"},
                "privacy": {"status": "pass"},
            },
            "visual": {
                "assets": [
                    {
                        "asset_id": "asset-1",
                        "ref": str(self.asset_path),
                        "asset_type": "stock-photo",
                        "rights_status": "verified",
                        "privacy_status": "verified",
                    }
                ],
                "brand_spec": {
                    "asset_refs": {
                        "logos": [],
                        "product_images": ["asset-1"],
                        "ui_screenshots": [],
                    }
                },
                "design_exploration": {
                    "directions": [{"direction_id": "clear-list"}],
                    "selected_direction_id": "clear-list",
                },
                "render_artifacts": [
                    {
                        "artifact_id": "article-html",
                        "output_family": "article",
                        "media_adapter": "article",
                        "layout_intent": "list",
                        "renderer": "html-playwright",
                        "format": "html",
                        "status": "planned",
                        "input_refs": [str(self.input_path)],
                        "asset_ids": ["asset-1"],
                        "ref": str(self.output_path),
                        "receipt_ref": str(self.receipt_path),
                    }
                ],
            },
        }

    def write_valid_output_and_receipt(self, item: dict) -> None:
        self.output_path.write_text(
            '<!doctype html><html><head><meta name="viewport" content="width=device-width"></head><body><p>ok</p></body></html>',
            encoding="utf-8",
        )
        artifact = item["visual"]["render_artifacts"][0]
        receipt = {
            "schema_version": "render-receipt.v1",
            "receipt_id": "artifact-validation-fixture.article-html.0123456789ab",
            "artifact_id": artifact["artifact_id"],
            "content_id": item["content_id"],
            "renderer": artifact["renderer"],
            "renderer_version": "local-test",
            "created_at": "2026-08-08T13:23:41+08:00",
            "inputs": [{"ref": str(self.input_path), "sha256": sha256(self.input_path)}],
            "output": {
                "ref": str(self.output_path),
                "format": "html",
                "sha256": sha256(self.output_path),
                "bytes": self.output_path.stat().st_size,
            },
            "qa": {
                "profile_id": "article-html.v1",
                "hard_checks": [
                    {"name": name, "status": "pass"}
                    for name in (
                        "file-exists",
                        "non-empty-output",
                        "input-files-exist",
                        "fact-gate",
                        "rights-gate",
                        "privacy-gate",
                        "utf8-readable",
                        "html-document",
                        "responsive-viewport",
                        "alt-text-complete",
                        "font-size-gate",
                    )
                ],
                "review_checks": [{"name": "human-final-review", "status": "needs-review"}],
                "needs_review_count": 1,
                "result": "review-required",
                "retry_count": 0,
            },
            "policy": {
                "rights_verified": True,
                "privacy_verified": True,
                "ai_generation_authorized": False,
                "remote_downloads_enabled": False,
            },
        }
        self.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    def messages(self, item: dict) -> list[str]:
        return [message for _, message in validate_render_artifacts(item, self.item_path)]

    def baoyu_item(self) -> dict:
        item = self.base_item()
        artifact = item["visual"]["render_artifacts"][0]
        artifact.update(
            renderer="baoyu-md",
            theme="default",
            renderer_options={"explicit_adapter": True},
        )
        return item

    def test_valid_produced_artifact_and_receipt(self) -> None:
        item = self.base_item()
        item["visual"]["render_artifacts"][0]["status"] = "rendered"
        self.write_valid_output_and_receipt(item)
        self.assertEqual(self.messages(item), [])

    def test_duplicate_artifact_id_is_rejected(self) -> None:
        item = self.base_item()
        duplicate = copy.deepcopy(item["visual"]["render_artifacts"][0])
        duplicate.pop("ref")
        duplicate.pop("receipt_ref")
        item["visual"]["render_artifacts"].append(duplicate)
        self.assertTrue(any("duplicates visual.render_artifacts" in message for message in self.messages(item)))

    def test_duplicate_asset_id_is_rejected(self) -> None:
        item = self.base_item()
        item["visual"]["assets"].append(copy.deepcopy(item["visual"]["assets"][0]))
        self.assertTrue(any("duplicates visual.assets" in message for message in self.messages(item)))

    def test_dangling_asset_and_brand_refs_are_rejected(self) -> None:
        item = self.base_item()
        item["visual"]["render_artifacts"][0]["asset_ids"] = ["missing"]
        item["visual"]["brand_spec"]["asset_refs"]["logos"] = ["missing-logo"]
        messages = self.messages(item)
        self.assertTrue(any("unknown asset_id" in message for message in messages))
        self.assertTrue(any("must reference visual.assets" in message for message in messages))

    def test_unknown_selected_direction_is_rejected(self) -> None:
        item = self.base_item()
        item["visual"]["design_exploration"]["selected_direction_id"] = "missing"
        self.assertTrue(any("declared direction_id" in message for message in self.messages(item)))

    def test_rendered_status_requires_output_and_receipt(self) -> None:
        item = self.base_item()
        item["visual"]["render_artifacts"][0]["status"] = "rendered"
        messages = self.messages(item)
        self.assertTrue(any("missing rendered output" in message for message in messages))
        self.assertTrue(any("missing render receipt" in message for message in messages))

    def test_receipt_hash_mismatch_is_rejected(self) -> None:
        item = self.base_item()
        item["visual"]["render_artifacts"][0]["status"] = "rendered"
        self.write_valid_output_and_receipt(item)
        receipt = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        receipt["output"]["sha256"] = "0" * 64
        self.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        self.assertTrue(any("does not match rendered file" in message for message in self.messages(item)))

    def test_receipt_is_invalidated_when_a_hashed_input_changes(self) -> None:
        item = self.base_item()
        item["visual"]["render_artifacts"][0]["status"] = "rendered"
        self.write_valid_output_and_receipt(item)
        self.input_path.write_text("# Changed after rendering\n", encoding="utf-8")
        self.assertTrue(
            any("does not match input file" in message for message in self.messages(item))
        )

    def test_receipt_requires_every_media_profile_hard_check(self) -> None:
        item = self.base_item()
        item["visual"]["render_artifacts"][0]["status"] = "rendered"
        self.write_valid_output_and_receipt(item)
        receipt = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        receipt["qa"]["hard_checks"] = receipt["qa"]["hard_checks"][:-1]
        self.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        self.assertTrue(any("missing required hard checks" in message for message in self.messages(item)))

    def test_receipt_needs_review_count_must_match_findings(self) -> None:
        item = self.base_item()
        item["visual"]["render_artifacts"][0]["status"] = "rendered"
        self.write_valid_output_and_receipt(item)
        receipt = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        receipt["qa"]["needs_review_count"] = 0
        self.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        self.assertTrue(any("must equal actual count" in message for message in self.messages(item)))

    def test_failed_hard_check_cannot_be_approved(self) -> None:
        item = self.base_item()
        artifact = item["visual"]["render_artifacts"][0]
        artifact["status"] = "approved"
        artifact["human_review"] = {"status": "approved"}
        self.write_valid_output_and_receipt(item)
        receipt = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        receipt["qa"]["hard_checks"][0]["status"] = "fail"
        receipt["qa"]["result"] = "fail"
        self.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        self.assertTrue(any("every hard QA check" in message for message in self.messages(item)))

    def test_imagegen_artifact_requires_explicit_authorization(self) -> None:
        item = self.base_item()
        artifact = item["visual"]["render_artifacts"][0]
        artifact.update(renderer="imagegen", format="png")
        artifact.pop("ref")
        artifact.pop("receipt_ref")
        self.assertTrue(any("模型生成图片 or AI 生图" in message for message in self.messages(item)))

    def test_imagegen_artifact_rejects_forged_generic_generation_quote(self) -> None:
        item = self.base_item()
        artifact = item["visual"]["render_artifacts"][0]
        artifact.update(renderer="imagegen", format="png")
        artifact.pop("ref")
        artifact.pop("receipt_ref")
        item["visual"]["ai_image_generation"] = {
            "policy": "explicit-opt-in-only",
            "explicit_user_request": True,
            "request_text": "请生成一张图片作为封面",
            "matched_trigger": "生成一张图片",
        }
        self.assertTrue(any("模型生成图片 or AI 生图" in message for message in self.messages(item)))

    def test_imagegen_artifact_accepts_exact_authorization_phrase(self) -> None:
        item = self.base_item()
        artifact = item["visual"]["render_artifacts"][0]
        artifact.update(renderer="imagegen", format="png")
        artifact.pop("ref")
        artifact.pop("receipt_ref")
        item["visual"]["ai_image_generation"] = {
            "policy": "explicit-opt-in-only",
            "explicit_user_request": True,
            "request_text": "请让模型生成图片作为封面候选",
            "matched_trigger": "模型生成图片",
        }
        self.assertFalse(any("模型生成图片 or AI 生图" in message for message in self.messages(item)))

    def test_legacy_outputs_must_map_to_artifacts_when_both_exist(self) -> None:
        item = self.base_item()
        item["visual"]["render_recipe"] = {
            "renderer": "html-playwright",
            "output_format": "html",
            "output_refs": [str(self.root / "different.html")],
        }
        self.assertTrue(any("must also be registered" in message for message in self.messages(item)))

    def test_baoyu_local_markdown_plan_is_valid(self) -> None:
        self.assertEqual(self.messages(self.baoyu_item()), [])

    def test_baoyu_remote_markdown_image_is_rejected_before_render(self) -> None:
        self.input_path.write_text(
            "# Input\n\n![remote](https://example.com/image.jpg)\n",
            encoding="utf-8",
        )
        self.assertTrue(
            any("remote image downloads are disabled" in message for message in self.messages(self.baoyu_item()))
        )

    def test_baoyu_remote_registered_asset_is_rejected(self) -> None:
        item = self.baoyu_item()
        item["visual"]["assets"][0]["ref"] = "https://example.com/image.jpg"
        self.assertTrue(
            any("registered local assets only" in message for message in self.messages(item))
        )


if __name__ == "__main__":
    unittest.main()
