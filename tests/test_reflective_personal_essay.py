import importlib.util
import hashlib
import json
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from temp_workspace import isolated_test_directory


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pipeline = load_module("article_visual_pipeline_reflective", ROOT / "scripts" / "article_visual_pipeline.py")
validation = load_module("design_direction_validation_reflective", ROOT / "scripts" / "design_direction_validation.py")
social_runtime = load_module("social_card_runtime_reflective", ROOT / "scripts" / "social_card_runtime.py")


def expected_typography_policy(gate: dict) -> Path:
    """Resolve the test's explicitly configured reflective typography policy.

    The external policy file is named by the test-only environment variable
    ``CONTENT_STUDIO_TEST_REFLECTIVE_TYPOGRAPHY_POLICY``. Its gate hash must be a
    real lowercase 64-hex digest before the public resolver runs; the resolver
    then rejects an unset variable, a missing file and checksum drift with
    ``SocialCardRuntimeError``. There is no skip, fallback or dummy value.
    """
    policy_sha256 = gate.get("policy_sha256")
    if not isinstance(policy_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", policy_sha256):
        raise social_runtime.SocialCardRuntimeError(
            "typography gate policy_sha256 must be a lowercase 64-hex digest"
        )
    return social_runtime.resolve_external_file_from_env(
        "CONTENT_STUDIO_TEST_REFLECTIVE_TYPOGRAPHY_POLICY",
        "reflective typography policy",
        policy_sha256,
    )


class ReflectivePersonalEssayTests(unittest.TestCase):
    def item(self, media_adapter="article"):
        artifact = {
            "artifact_id": "reflective-output",
            "media_adapter": media_adapter,
            "layout_intent": "sequence",
            "renderer": "html-playwright" if media_adapter == "article" else "social-card",
            "format": "html",
            "theme": "reflective-personal-essay",
        }
        if media_adapter == "social-card":
            artifact["renderer_options"] = {
                "design_direction_id": "reflective-personal-essay"
            }
        return {
            "visual": {
                "visual_profile": "visual/insurance-observational-advisor",
                "visual_profile_version": "0.2.0",
                "route": "text_card",
                "design_system": {
                    "principles_version": "shared-design-principles.v1",
                    "media_adapter": media_adapter,
                    "design_direction": {
                        "direction_id": "reflective-personal-essay",
                        "version": "1.0.0",
                    },
                    "communication_job": {
                        "audience": "正在经历职业转折的读者",
                        "outcome": "理解一次选择的真实来路",
                        "central_takeaway": "改变来自长期积累而非突然冲动",
                    },
                },
                "render_artifacts": [artifact],
            }
        }

    def test_reference_provenance_and_reuse_boundary_are_portable(self):
        methods = json.loads(
            (ROOT / "config" / "design-direction-sources.v1.json").read_text(encoding="utf-8")
        )
        source = next(
            item
            for item in methods["sources"]
            if item["id"] == "living-for-yourself-v3-local-reference"
        )
        self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
        self.assertNotIn("local_path", source)
        self.assertIn("fixed-eight-card-default", source["not_absorbed"])
        self.assertIn("copyrighted-song-lyrics-as-default-device", source["not_absorbed"])
        self.assertIn("remote-google-font-dependency", source["not_absorbed"])

    def test_direction_is_explicit_and_route_bounded(self):
        contract = validation.load_design_directions()
        direction = contract["directions"]["reflective-personal-essay"]
        self.assertEqual("route-eligible-explicit", direction["routes"]["social-card"]["status"])
        self.assertEqual("reflective-personal-essay", direction["routes"]["article"]["artifact_theme"])
        self.assertEqual("structure-only-explicit", direction["routes"]["pptx"]["status"])
        self.assertIn("data_visualization", direction["excluded_routes"]["visual_routes"])
        self.assertEqual([], validation.validate_design_direction(self.item()))
        self.assertEqual([], validation.validate_design_direction(self.item("social-card")))

    def test_wrong_social_card_theme_or_intent_fails_closed(self):
        item = self.item("social-card")
        item["visual"]["render_artifacts"][0]["theme"] = "default"
        self.assertTrue(validation.validate_design_direction(item))
        item = self.item("social-card")
        item["visual"]["render_artifacts"][0]["layout_intent"] = "data-chart"
        self.assertTrue(validation.validate_design_direction(item))

    def test_article_renderer_builds_paced_sections_with_local_fonts(self):
        markdown = (ROOT / "fixtures" / "reflective-personal-essay" / "article.md").read_text(
            encoding="utf-8"
        )
        rendered = pipeline.render_article_html(
            markdown, "我为什么决定停下来重新选择", theme="reflective-personal-essay"
        )
        self.assertIn('data-design-direction="reflective-personal-essay"', rendered)
        self.assertEqual(6, rendered.count('class="essay-section"'))
        self.assertEqual(1, len(re.findall(r'<section class="essay-section"[^>]*data-tone="dark"', rendered)))
        self.assertEqual(1, len(re.findall(r'<section class="essay-section"[^>]*data-tone="resolve"', rendered)))
        self.assertIn("@media (max-width: 720px)", rendered)
        self.assertNotIn("fonts.googleapis.com", rendered)

    def test_explicit_section_tones_are_validated(self):
        markdown = "# 标题\n\n## 第一节\n\n正文。\n\n## 第二节\n\n正文。\n"
        rendered = pipeline.render_article_html(
            markdown,
            "标题",
            theme="reflective-personal-essay",
            section_tones=["dark", "resolve"],
        )
        self.assertEqual(1, len(re.findall(r'<section class="essay-section"[^>]*data-tone="dark"', rendered)))
        with self.assertRaisesRegex(ValueError, "exactly one tone"):
            pipeline.render_article_html(
                markdown,
                "标题",
                theme="reflective-personal-essay",
                section_tones=["paper"],
            )
        with self.assertRaisesRegex(ValueError, "unknown reflective section tone"):
            pipeline.render_article_html(
                markdown,
                "标题",
                theme="reflective-personal-essay",
                section_tones=["paper", "loud"],
            )

    def test_social_card_source_is_local_script_free_and_direction_bound(self):
        source = (ROOT / "fixtures" / "reflective-personal-essay" / "social-deck.html").read_text(
            encoding="utf-8"
        )
        details = social_runtime.validate_social_card_html_source(
            source, "reflective-personal-essay"
        )
        self.assertTrue(details["script_free_html"])
        self.assertTrue(details["local_assets_only"])
        with self.assertRaisesRegex(social_runtime.SocialCardRuntimeError, "remote assets"):
            social_runtime.validate_social_card_html_source(
                source.replace("</head>", '<link href="https://fonts.example/a.css"></head>'),
                "reflective-personal-essay",
            )
        with self.assertRaisesRegex(social_runtime.SocialCardRuntimeError, "script-free"):
            social_runtime.validate_social_card_html_source(
                source.replace("</body>", "<script>alert(1)</script></body>"),
                "reflective-personal-essay",
            )

    def test_registry_editor_and_bridge_expose_the_direction(self):
        registry = json.loads((ROOT / "config" / "renderer-registry.v1.json").read_text(encoding="utf-8"))
        self.assertIn("reflective-personal-essay", registry["renderers"]["social-card"]["themes"])
        self.assertIn("reflective-personal-essay", registry["renderers"]["html-playwright"]["themes"])
        self.assertTrue((ROOT / registry["renderers"]["social-card"]["bridge"]).is_file())
        self.assertEqual(
            "CONTENT_STUDIO_SOCIAL_CARD_PLAYWRIGHT_PACKAGE",
            registry["renderers"]["social-card"]["playwright_package"]["env"],
        )
        self.assertEqual(
            "CONTENT_STUDIO_SOCIAL_CARD_QA_ENTRY",
            registry["renderers"]["social-card"]["external_qa"]["entry_env"],
        )
        typography_gate = registry["renderers"]["social-card"]["typography_gate"]
        expected_policy_path = Path(typography_gate["policy_path"]).expanduser()
        if not expected_policy_path.is_absolute():
            expected_policy_path = ROOT / expected_policy_path
        self.assertEqual(
            expected_policy_path.resolve(),
            expected_typography_policy(typography_gate),
        )
        self.assertEqual("social_card_1080x1440", typography_gate["profile_id"])
        self.assertRegex(typography_gate["policy_sha256"], r"^[0-9a-f]{64}$")
        editor = (ROOT / "admin" / "config.yml").read_text(encoding="utf-8")
        self.assertIn("value: reflective-personal-essay", editor)

    def test_external_runtime_configuration_is_explicit_and_fail_closed(self):
        env_name = "CONTENT_STUDIO_TEST_EXTERNAL_FILE"
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(env_name, None)
            with self.assertRaisesRegex(social_runtime.SocialCardRuntimeError, "is not configured"):
                social_runtime.resolve_external_file_from_env(env_name, "test dependency")
        with isolated_test_directory("social-card-external-runtime") as temporary:
            dependency = temporary / "entry.mjs"
            dependency.write_text("export {};\n", encoding="utf-8")
            digest = hashlib.sha256(dependency.read_bytes()).hexdigest()
            with patch.dict(os.environ, {env_name: str(dependency)}, clear=False):
                self.assertEqual(
                    dependency.resolve(),
                    social_runtime.resolve_external_file_from_env(
                        env_name, "test dependency", digest
                    ),
                )
                with self.assertRaisesRegex(social_runtime.SocialCardRuntimeError, "checksum drift"):
                    social_runtime.resolve_external_file_from_env(
                        env_name, "test dependency", "0" * 64
                    )


if __name__ == "__main__":
    unittest.main()
