import hashlib
import importlib.util
import io
import json
import os
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
ITEM_PATH = Path(os.environ["CONTENT_STUDIO_SPECIAL_MEDICAL_ITEM_PATH"])
CONTENT_SCHEMA_PATH = Path(os.environ["CONTENT_STUDIO_SPECIAL_MEDICAL_CONTENT_SCHEMA_PATH"])
RECEIPT_SCHEMA_PATH = ROOT / "schemas" / "render-receipt.v1.schema.json"
MODULE_PATH = Path(os.environ["CONTENT_STUDIO_SPECIAL_MEDICAL_RENDERER_PATH"])

module_spec = importlib.util.spec_from_file_location("render_data_explanations_special", MODULE_PATH)
renderer = importlib.util.module_from_spec(module_spec)
assert module_spec.loader is not None
module_spec.loader.exec_module(renderer)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SpecialMedicalOfficialArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.item = json.loads(ITEM_PATH.read_text(encoding="utf-8"))

    def test_content_item_and_receipts_match_contracts(self):
        content_schema = json.loads(CONTENT_SCHEMA_PATH.read_text(encoding="utf-8"))
        receipt_schema = json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            [],
            sorted(
                Draft202012Validator(content_schema).iter_errors(self.item),
                key=lambda error: list(error.path),
            ),
        )

        for artifact in self.item["visual"]["render_artifacts"]:
            with self.subTest(artifact=artifact["artifact_id"]):
                output_path = ROOT / artifact["ref"]
                receipt_path = ROOT / artifact["receipt_ref"]
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                errors = sorted(
                    Draft202012Validator(receipt_schema).iter_errors(receipt),
                    key=lambda error: list(error.path),
                )
                self.assertEqual([], errors)
                self.assertEqual("review-required", artifact["status"])
                self.assertTrue(receipt["manual_only"])
                self.assertTrue(receipt["candidate_only"])
                self.assertEqual("review-required", receipt["qa"]["result"])
                self.assertTrue(all(check["status"] == "pass" for check in receipt["qa"]["hard_checks"]))
                self.assertEqual(sha256(output_path), receipt["output"]["sha256"])
                self.assertEqual("0.2", receipt["contract_versions"]["content_item"])
                self.assertEqual(
                    "data-explanation-chart-spec.v1",
                    receipt["contract_versions"]["chart_spec"],
                )
                self.assertEqual("evidence-binding.v1", receipt["contract_versions"]["evidence_binding"])
                self.assertTrue(receipt["evidence_refs"])
                self.assertTrue(
                    all(
                        evidence["ref"].startswith("https://")
                        and evidence["evidence_status"] == "verified"
                        for evidence in receipt["evidence_refs"]
                    )
                )

    def test_outputs_are_idempotent_from_their_hashed_specs(self):
        for artifact in self.item["visual"]["render_artifacts"]:
            with self.subTest(artifact=artifact["artifact_id"]):
                spec_path = (ITEM_PATH.parent / artifact["input_refs"][0]).resolve()
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
                output_path = ROOT / artifact["ref"]
                if artifact["format"] == "svg":
                    first = renderer.render_svg_text(spec)
                    second = renderer.render_svg_text(spec)
                    self.assertEqual(
                        hashlib.sha256(first.encode("utf-8")).hexdigest(),
                        hashlib.sha256(second.encode("utf-8")).hexdigest(),
                    )
                    self.assertEqual(first, output_path.read_text(encoding="utf-8"))
                    continue
                else:
                    buffer = io.BytesIO()
                    renderer.render_canvas(spec).image.save(
                        buffer,
                        format="PNG",
                        optimize=True,
                    )
                    expected = buffer.getvalue()
                self.assertEqual(hashlib.sha256(expected).hexdigest(), sha256(output_path))

    def test_timeline_png_is_readable_and_nonblank(self):
        artifact = next(
            artifact
            for artifact in self.item["visual"]["render_artifacts"]
            if artifact["artifact_id"] == "special-medical-official-case-timeline-png"
        )
        with Image.open(ROOT / artifact["ref"]) as image:
            self.assertEqual(
                (artifact["dimensions"]["width"], artifact["dimensions"]["height"]),
                image.size,
            )
            background = Image.new("RGB", image.size, image.getpixel((0, 0)))
            bbox = ImageChops.difference(image.convert("RGB"), background).getbbox()
            self.assertIsNotNone(bbox)
            self.assertGreater(bbox[2] - bbox[0], image.width * 0.7)
            self.assertGreater(bbox[3] - bbox[1], image.height * 0.55)

    def test_svg_outputs_preserve_cjk_labels_and_canvas_size(self):
        for artifact in self.item["visual"]["render_artifacts"]:
            if artifact["format"] != "svg":
                continue
            with self.subTest(artifact=artifact["artifact_id"]):
                text = (ROOT / artifact["ref"]).read_text(encoding="utf-8")
                spec_path = (ITEM_PATH.parent / artifact["input_refs"][0]).resolve()
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
                self.assertIn(f'width="{artifact["dimensions"]["width"]}"', text)
                self.assertIn(f'height="{artifact["dimensions"]["height"]}"', text)
                self.assertIn("Microsoft YaHei", text)
                for series in spec["series"]:
                    for point in series["points"]:
                        self.assertIn(point["label"], text)


if __name__ == "__main__":
    unittest.main()
