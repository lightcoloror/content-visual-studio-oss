"""Adversarial sentence/version coverage, not a test of audience response."""
import copy
import json
import sys
import shutil
import uuid
from contextlib import contextmanager
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import narrative_realization as N
import initial_draft_quality_gate as G


@contextmanager
def workspace(base=None):
    base = (base or ROOT / "tests").resolve()
    path = base / ("narrative-" + uuid.uuid4().hex)
    path.mkdir()
    try:
        yield path
    finally:
        if path.resolve().is_relative_to(base) and path != base:
            shutil.rmtree(path)


class NarrativeTests(unittest.TestCase):
    def setUp(self):
        self.script = json.loads((ROOT / "fixtures/case-video-script-v1/synthetic-case-video-script.pre-voice.json").read_text(encoding="utf-8"))
        self.card = json.loads((ROOT / "fixtures/story-design-card-v1/synthetic.input.json").read_text(encoding="utf-8"))
        self.card["content_id"] = self.script["content_id"]
        # A frozen synthetic card is passed to the pure text matcher; the actual
        # owner-card/fact validation is separately tested below.
        for row in self.script["segments"]:
            row["fact_refs"] = self.card["fact_binding"]["allowed_fact_ids"][:]
        self.value = N.template(self.script, self.card, G._body_sha256(self.script))
        for i, row in enumerate(self.value["elements"]):
            segment = self.script["segments"][i % len(self.script["segments"])]
            row.update(status="clear", judgment="Synthetic sentence expresses this planned action and its consequence.",
                       anchors=[{"segment_id": segment["segment_id"], "spoken_span": segment["spoken_text"],
                                 "fact_refs": N.required_elements(self.card)[row["element_id"]][:1]}])
        for row in self.value["craft"].values():
            row.update(status="not_applicable", judgment="No confirmed original quotation or character voice is used in this synthetic case.")

    def check(self):
        return N.validate(self.script, self.value, self.card, G._body_sha256(self.script))

    def blocked(self, code):
        with self.assertRaises(N.NarrativeError) as caught:
            self.check()
        self.assertEqual(code, caught.exception.code)

    def test_complete_anchored_review(self):
        self.assertEqual([], self.check())

    def test_current_contract_pins_match_and_tampering_blocks(self):
        G.validate_storycraft_binding()
        with workspace() as path:
            binding = json.loads((ROOT / 'contracts/storycraft-contract-binding.json').read_text(encoding='utf-8'))
            binding['contracts'][-1]['sha256'] = '0' * 64
            target = path / 'binding.json'
            target.write_text(json.dumps(binding),encoding='utf-8')
            with self.assertRaises(G.InitialDraftGateError) as caught:
                G.validate_storycraft_binding(target)
            self.assertEqual(caught.exception.code,'storycraft_contract_drift')

    def test_card_without_sentence_review_is_not_enough(self):
        self.value = None
        self.blocked("story_realization_required")

    def test_removed_story_element_cannot_pass(self):
        self.value["elements"].pop()
        self.blocked("story_realization_coverage")

    def test_pending_material_returns_revision_without_inventing_text(self):
        self.value["elements"][0].update(status="material_gap", anchors=[])
        self.assertEqual(["protagonist-goal"], self.check())

    def test_quote_from_different_sentence_is_rejected(self):
        self.value["elements"][0]["anchors"][0]["spoken_span"] = "Invented sentence that never appeared."
        self.blocked("story_realization_span_unbound")

    def test_unknown_or_unrelated_fact_is_rejected(self):
        self.value["elements"][0]["anchors"][0]["fact_refs"] = ["fact-unknown"]
        self.blocked("story_realization_fact_unbound")

    def test_edited_body_and_card_invalidate_review(self):
        self.script["segments"][0]["spoken_text"] += " changed"
        self.blocked("story_realization_body_drift")
        self.setUp()
        self.card["story_purpose"] += " changed"
        self.blocked("story_realization_card_drift")

    def test_required_element_cannot_be_marked_na(self):
        self.value["elements"][0].update(status="not_applicable", anchors=[])
        self.blocked("story_realization_invalid_na")

    def test_invented_dialogue_is_not_required_to_make_story(self):
        self.value["craft"]["dialogue"] = {k: v for k, v in self.value["elements"][0].items() if k != "element_id"}
        self.blocked("story_dialogue_not_sourced")

    def test_placeholder_cannot_be_promoted_by_flipping_status(self):
        self.value["elements"][0]["judgment"] = "Pending actual text review; no narrative approval."
        self.blocked("story_realization_judgment_required")

    def test_all_elements_cannot_reuse_one_sentence(self):
        for row in self.value["elements"]:
            row["anchors"][0].update(segment_id=self.script["segments"][0]["segment_id"],
                                    spoken_span=self.script["segments"][0]["spoken_text"])
        self.blocked("story_realization_progression_missing")

    def test_initial_gate_wires_card_and_text_review(self):
        fixture = ROOT / "fixtures/case-video-script-v1"
        script = json.loads((fixture / "synthetic-case-video-script.pre-voice.json").read_text(encoding="utf-8"))
        review = json.loads((fixture / "synthetic-initial-draft-review.v1.json").read_text(encoding="utf-8"))
        with workspace() as folder:
            script_path, review_path = Path(folder) / "draft.json", Path(folder) / "review.json"
            script_path.write_text(json.dumps(script), encoding="utf-8")
            review_path.write_text(json.dumps(review), encoding="utf-8")
            with patch.object(G, "load_story_card", return_value=self.card):
                with self.assertRaises(G.InitialDraftGateError) as caught:
                    G.validate_initial_draft_review(script_path=script_path, review_path=review_path,
                                                   structure_route="story-arc")
                self.assertEqual("story_realization_required", caught.exception.code)
            # Non-story execution retains its own original gates.
            self.assertEqual("initial_draft_review_passed", G.validate_initial_draft_review(
                script_path=script_path, review_path=review_path, structure_route="direct-answer")["status"])

    def test_valid_owner_card_cannot_be_substituted_for_another_fact_revision(self):
        import importlib.util
        owner = ROOT.parent / "self-media-creation-system"
        spec = importlib.util.spec_from_file_location("test_real_owner_card", owner / "scripts/story_design_gate.py")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        card = gate.create_receipt(owner / "fixtures/story-design-card-v1/synthetic.input.json")
        with workspace() as folder:
            path = Path(folder) / "card.json"
            path.write_text(json.dumps(card), encoding="utf-8")
            with self.assertRaises(G.InitialDraftGateError) as caught:
                G.load_story_card(self.script, path)
            self.assertEqual("story_fact_revision_drift", caught.exception.code)

    def test_current_owner_card_and_sentence_review_allow_only_synthetic_draft(self):
        import importlib.util
        owner = ROOT.parent / "self-media-creation-system"
        spec = importlib.util.spec_from_file_location("test_positive_owner_card", owner / "scripts/story_design_gate.py")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        with workspace(owner / "tests") as folder:
            fact = json.loads((owner / "fixtures/story-design-card-v1/synthetic-fact-card.json").read_text(encoding="utf-8"))
            fact["fact_card_id"] = "fact-card-synthetic-story-001"
            fact_path = folder / "fact.json"
            fact_path.write_text(json.dumps(fact), encoding="utf-8")
            raw = copy.deepcopy(self.card)
            raw["fact_binding"].update(fact_card_ref=fact_path.relative_to(owner).as_posix(),
                                       fact_card_sha256=gate.text_sha256(fact_path))
            card = gate.create_receipt_from_value(raw)
            card_path = folder / "card.json"
            card_path.write_text(json.dumps(card), encoding="utf-8")
            script = copy.deepcopy(self.script)
            script["structure_route"] = "story-arc"
            script["inputs"]["fact_card_ref"] = {"artifact_id": fact["fact_card_id"],
                "schema_version": fact["schema_version"], "sha256": N.digest(fact)}
            review = json.loads((ROOT / "fixtures/case-video-script-v1/synthetic-initial-draft-review.v1.json").read_text(encoding="utf-8"))
            review["input_fact_card_ref"] = script["inputs"]["fact_card_ref"]
            review["input_body_sha256"] = G._body_sha256(script)
            review["story_realization"] = copy.deepcopy(self.value)
            review["story_realization"].update(input_body_sha256=G._body_sha256(script), story_card_sha256=N.digest(card))
            script_path, review_path = folder / "script.json", folder / "review.json"
            script_path.write_text(json.dumps(script), encoding="utf-8")
            review_path.write_text(json.dumps(review), encoding="utf-8")
            result = G.validate_initial_draft_review(script_path=script_path, review_path=review_path,
                structure_route="story-arc", story_card_path=card_path)
            self.assertEqual("initial_draft_review_passed", result["status"])
            self.assertEqual("manual-only", result["publication_boundary"])
            review["story_realization"]["elements"][0].update(status="material_gap", anchors=[])
            review_path.write_text(json.dumps(review), encoding="utf-8")
            with self.assertRaises(G.InitialDraftGateError) as caught:
                G.validate_initial_draft_review(script_path=script_path, review_path=review_path,
                    structure_route="story-arc", story_card_path=card_path)
            self.assertEqual("story_realization_unresolved", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
