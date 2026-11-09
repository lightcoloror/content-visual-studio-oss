import copy
import importlib.util
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "handdraw_style_brief", ROOT / "scripts" / "handdraw_style_brief.py"
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class HanddrawStyleBriefTests(unittest.TestCase):
    def setUp(self):
        self.registry = module.read_json(ROOT / "config" / "handdraw-style-brief.v1.json")
        self.item = {
            "schema_version": "0.2",
            "content_id": "synthetic-essay-style-brief",
            "visual": {
                "design_system": {
                    "media_adapter": "article",
                    "design_direction": {
                        "direction_id": "reflective-personal-essay", "version": "1.0.0"
                    },
                },
                "article_visual_plan": {
                    "workflow": "human-in-the-loop",
                    "ai_generation_policy": "explicit-opt-in-only",
                    "slots": [{
                        "slot_id": "waiting-chair",
                        "route": "generated-image",
                        "status": "planned",
                        "media_role": "explanatory",
                        "layout": "full-width",
                        "purpose": "A visual metaphor, not evidence",
                    }],
                },
                "render_artifacts": [{
                    "artifact_id": "essay-cover",
                    "media_adapter": "social-card",
                    "output_family": "social-card",
                    "renderer": "social-card",
                    "status": "planned",
                    "format": "png",
                }],
            },
        }

    def brief(self, target="waiting-chair", style="conceptual-line"):
        return module.create_brief(
            self.item, target, style, "an empty chair", "place a ticket beside it",
            self.registry,
        )

    def test_pinned_generic_index_is_available(self):
        records = module.verify_source(self.registry)
        self.assertEqual("Conceptual Line Drawing", records["157"]["generation_name"])

    def test_article_brief_uses_existing_visual_brief_contract(self):
        result = self.brief()
        visual_brief_schema = json.loads((ROOT / "schemas" / "handdraw-visual-brief.schema.snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual([], list(Draft202012Validator(visual_brief_schema).iter_errors(result["visual_brief"])))
        self.assertFalse(result["image_generated"])
        self.assertFalse(result["upstream_image_used"])
        self.assertEqual("not-declared", result["source_license_status"])
        self.assertEqual("unverified", result["upstream_asset_rights_status"])
        self.assertEqual("candidate-only", result["status"])
        self.assertNotIn("artist", json.dumps(result).lower())

    def test_social_card_brief_is_explicit_planning_only(self):
        self.item["visual"]["design_system"]["media_adapter"] = "social-card"
        result = self.brief("essay-cover", "ink-spot-color")
        self.assertEqual("social-card", result["media_adapter"])
        self.assertIn("Planning brief only", result["boundary"])

    def test_unregistered_style_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Unregistered style"):
            self.brief(style="creator-018")

    def test_personal_creator_style_cannot_be_added_to_generic_allowlist(self):
        registry = copy.deepcopy(self.registry)
        registry["styles"]["creator-018"] = {
            "source_number": "018",
            "source_generation_name": "Minimal Deadpan Dialogue Cartoon",
            "composition_guidance": "Copy a creator",
            "allowed_targets": ["reflective-personal-essay/article"],
        }
        with self.assertRaisesRegex(ValueError, "Personal-creator style"):
            module.create_brief(self.item, "waiting-chair", "creator-018", "chair", "place ticket", registry)

    def test_source_index_hash_drift_fails_closed(self):
        registry = copy.deepcopy(self.registry)
        registry["source"]["index_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "index has drifted"):
            module.verify_source(registry)

    def test_source_commit_drift_fails_closed(self):
        registry = copy.deepcopy(self.registry)
        registry["source"]["commit"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "commit has drifted"):
            module.verify_source(registry)

    def test_source_snapshot_manifest_drift_fails_closed(self):
        registry = copy.deepcopy(self.registry)
        registry['source']['manifest_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'manifest has drifted'):
            module.verify_source(registry)

    def test_source_snapshot_path_escape_fails_closed(self):
        registry = copy.deepcopy(self.registry)
        registry['source']['index_ref'] = '../outside.json'
        with self.assertRaisesRegex(ValueError, 'escapes'):
            module.verify_source(registry)

    def test_same_inputs_produce_the_same_candidate_brief(self):
        self.assertEqual(self.brief(), self.brief())

    def test_target_id_collision_fails_closed(self):
        self.item["visual"]["render_artifacts"][0]["artifact_id"] = "waiting-chair"
        with self.assertRaisesRegex(ValueError, "exactly once"):
            self.brief()

    def test_content_media_binding_fails_closed(self):
        self.item["visual"]["design_system"]["media_adapter"] = "social-card"
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.brief()

    def test_direction_version_drift_fails_closed(self):
        self.item["visual"]["design_system"]["design_direction"]["version"] = "0.0.0"
        with self.assertRaisesRegex(ValueError, "version has drifted"):
            self.brief()

    def test_wrong_direction_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "not allowed"):
            module.create_brief(
                self._item_with_direction("editorial-field-guide"),
                "waiting-chair", "colored-pencil-notes", "chair", "place ticket", self.registry,
            )

    def _item_with_direction(self, direction):
        item = copy.deepcopy(self.item)
        item["visual"]["design_system"]["design_direction"]["direction_id"] = direction
        return item

    def test_selected_article_slot_is_not_rewritten(self):
        self.item["visual"]["article_visual_plan"]["slots"][0]["status"] = "selected"
        with self.assertRaisesRegex(ValueError, "selected or inserted"):
            self.brief()

    def test_evidence_role_is_rejected(self):
        self.item["visual"]["article_visual_plan"]["slots"][0]["media_role"] = "evidence"
        with self.assertRaisesRegex(ValueError, "not factual evidence"):
            self.brief()

    def test_photo_mix_exclusion_is_respected(self):
        self.item["visual"]["article_visual_plan"]["visual_mode"] = "editorial-photo-mix"
        with self.assertRaisesRegex(ValueError, "excludes article visual mode"):
            self.brief()

    def test_missing_design_direction_fails_closed(self):
        self.item["visual"]["design_system"]["design_direction"] = {}
        with self.assertRaisesRegex(ValueError, "explicitly select"):
            self.brief()

    def test_semantic_inputs_are_not_invented(self):
        with self.assertRaisesRegex(ValueError, "must come from"):
            module.create_brief(self.item, "waiting-chair", "conceptual-line", registry=self.registry)

    def test_existing_composition_overflow_fails_closed(self):
        self.item["visual"]["article_visual_plan"]["slots"][0]["visual_brief"] = {
            "metaphor": "chair", "central_action": "place ticket",
            "composition": "x" * 239, "max_labels": 0,
        }
        with self.assertRaisesRegex(ValueError, "exceeds"):
            self.brief()


if __name__ == "__main__":
    unittest.main()
