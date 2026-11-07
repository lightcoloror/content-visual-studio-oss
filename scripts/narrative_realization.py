"""Check editorial evidence against the actual draft, never infer story quality.

The caller must first validate the current Story Design Card with its owner gate.
This adds no approval state: unresolved findings return the existing draft review.
"""
from __future__ import annotations
from studio_paths import STUDIO_ROOT, HUMAN_VOICE_ROOT, research_schema_path

import hashlib
import json


class NarrativeError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def fail(code, message):
    raise NarrativeError(code, message)


def keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        fail("story_realization_shape", label)


def meaningful(value):
    return isinstance(value, str) and len(value.strip()) >= 8 and value.strip().casefold() not in {
        "pending review", "not reviewed", "to be reviewed", "尚未填写。", "待人工逐项确认。"}


def required_elements(card):
    result = {
        "protagonist-goal": card["protagonist"]["goal_fact_refs"],
        "scene-anchor": card["scene_anchor"]["fact_refs"],
        "inciting-incident": card["inciting_incident"]["fact_refs"],
        "expectation-gap": card["expectation_gap"]["fact_refs"],
        "pressure": [ref for row in card["pressure"] for ref in row["fact_refs"]],
        "choice-under-pressure": card["choice_under_pressure"]["fact_refs"],
        "climax": card["climax"]["fact_refs"],
        "resolution": card["resolution"]["fact_refs"],
    }
    result.update({"turn:" + row["beat_id"]: row["fact_refs"] for row in card["turning_points"]})
    result.update({"emotion:" + str(i): row["fact_refs"]
                   for i, row in enumerate(card["emotional_design"]["emotion_beats"])})
    return result


def template(script, card, body_sha256):
    return {
        "schema_version": "narrative-realization.v1", "structure_route": "story-arc",
        "input_body_sha256": body_sha256, "story_card_sha256": digest(card),
        "elements": [{"element_id": key, "status": "needs_revision", "anchors": [],
                      "judgment": "Pending actual text review; no narrative approval."}
                     for key in required_elements(card)],
        "craft": {key: {"status": "needs_revision", "anchors": [],
                         "judgment": "Pending applicability and actual text review."}
                  for key in ("dialogue", "subtext", "character-voice")},
        "scope": "anchored-editorial-review-not-audience-effect",
    }


def validate(script, review, card, body_sha256):
    if not isinstance(review, dict):
        fail("story_realization_required", "story draft review needs actual sentence anchors")
    keys(review, {"schema_version", "structure_route", "input_body_sha256", "story_card_sha256",
                  "elements", "craft", "scope"}, "story_realization")
    if (review["schema_version"] != "narrative-realization.v1" or
        review["structure_route"] != "story-arc" or
        review["scope"] != "anchored-editorial-review-not-audience-effect"):
        fail("story_realization_shape", "unsupported contract or claimed audience effect")
    if review["input_body_sha256"] != body_sha256:
        fail("story_realization_body_drift", "sentence review belongs to another draft")
    if review["story_card_sha256"] != digest(card):
        fail("story_realization_card_drift", "sentence review belongs to another story design")
    if script["content_id"] != card["content_id"]:
        fail("story_content_drift", "story card and draft content IDs differ")
    segments = {row["segment_id"]: row for row in script["segments"]}
    if len(segments) != len(script["segments"]):
        fail("story_duplicate_segment", "ambiguous sentence anchors")
    expected = required_elements(card)
    elements = review["elements"]
    if (not isinstance(elements, list) or any(not isinstance(row, dict) for row in elements) or
        any(not isinstance(row.get("element_id"), str) for row in elements) or
        len(elements) != len(expected) or {r.get("element_id") for r in elements} != set(expected)):
        fail("story_realization_coverage", "each planned story element needs one text review")

    unresolved = []
    distinct = set()

    def check_row(row, allowed, label, optional=False):
        keys(row, {"status", "anchors", "judgment"}, label)
        if not isinstance(row["status"], str) or row["status"] not in {"clear", "needs_revision", "material_gap", "not_applicable"}:
            fail("story_realization_shape", label + " status")
        if not meaningful(row["judgment"]) or not isinstance(row["anchors"], list):
            fail("story_realization_judgment_required", label)
        if row["status"] in {"clear", "not_applicable"} and any(
            word in row["judgment"].casefold() for word in ("pending", "尚未", "待审核", "待人工", "待复核")):
            fail("story_realization_judgment_required", label)
        if row["status"] == "not_applicable":
            if not optional or row["anchors"]:
                fail("story_realization_invalid_na", label)
            return
        if row["status"] != "clear":
            unresolved.append(label)
        elif not row["anchors"]:
            fail("story_realization_anchor_required", label)
        for anchor in row["anchors"]:
            keys(anchor, {"segment_id", "spoken_span", "fact_refs"}, label + " anchor")
            if not isinstance(anchor["segment_id"], str):
                fail("story_realization_shape", label + " segment ID")
            segment = segments.get(anchor["segment_id"])
            span = anchor["spoken_span"]
            if (segment is None or not isinstance(span, str) or len(span.strip()) < 4 or
                span not in segment["spoken_text"]):
                fail("story_realization_span_unbound", label)
            refs = anchor["fact_refs"]
            if (not isinstance(refs, list) or not refs or any(not isinstance(ref, str) for ref in refs) or
                len(refs) != len(set(refs)) or not set(refs) <= set(segment.get("fact_refs", [])) or
                not set(refs) <= set(allowed)):
                fail("story_realization_fact_unbound", label)
            distinct.add((anchor["segment_id"], span))

    for element in elements:
        check_row({k: v for k, v in element.items() if k != "element_id"},
                  expected[element["element_id"]], element["element_id"])
    keys(review["craft"], {"dialogue", "subtext", "character-voice"}, "craft")
    for key, row in review["craft"].items():
        check_row(row, card["fact_binding"]["allowed_fact_ids"], key, optional=True)
    if (card["story_source"]["quote_treatment"] == "none" and
        review["craft"]["dialogue"]["status"] == "clear"):
        fail("story_dialogue_not_sourced", "card records no quotation source; do not invent dialogue")
    if review["craft"]["dialogue"]["status"] == "not_applicable" and review["craft"]["subtext"]["status"] == "clear":
        fail("story_subtext_not_sourced", "spoken dialogue is not applicable")
    if not unresolved and len(distinct) < 3:
        fail("story_realization_progression_missing", "one pasted sentence cannot approve the whole story")
    return unresolved
