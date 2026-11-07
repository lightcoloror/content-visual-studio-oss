#!/usr/bin/env python3
"""Validate the mandatory post-Storycraft review before voice and hook work."""

from __future__ import annotations
from studio_paths import STUDIO_ROOT, HUMAN_VOICE_ROOT, research_schema_path

import argparse
import importlib.util
import hashlib
import json
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

import case_video_script_adapter as case_adapter
import research_output_adapter as research_adapter
import narrative_realization



DEFAULT_SCHEMA = STUDIO_ROOT / "schemas/case-video-initial-draft-review.v1.schema.json"


def validate_storycraft_binding(binding_path=None):
    binding_path = binding_path or STUDIO_ROOT / "contracts/storycraft-contract-binding.json"
    expected = {
        "content-fact-card.v0": "schemas/content-fact-card.v0.schema.json",
        "case-video-initial-draft-review.v1": "schemas/case-video-initial-draft-review.v1.schema.json",
        "initial-draft-quality-gate-validator": "scripts/initial_draft_quality_gate.py",
        "narrative-realization-validator": "scripts/narrative_realization.py",
    }
    try:
        binding = json.loads(Path(binding_path).read_text(encoding="utf-8"))
        rows = binding["contracts"]
        if len(rows) != len(expected) or {row["contract_id"] for row in rows} != set(expected):
            raise ValueError("incomplete contract set")
        for row in rows:
            relative = expected[row["contract_id"]]
            path = Path(__file__).resolve().parent / Path(relative).name if relative.startswith("scripts/") else STUDIO_ROOT / relative
            if row["relative_path"] != relative or row["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError("contract drift: " + row["contract_id"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise InitialDraftGateError("storycraft_contract_drift", str(error)) from error

GATE_CHECKS: OrderedDict[str, tuple[str, ...]] = OrderedDict(
    [
        (
            "fact_evidence",
            (
                "timeline-and-causality-supported",
                "numbers-dates-and-counts-supported",
                "fact-memory-judgment-and-unknown-separated",
                "canonical-fact-revision-bound",
                "script-claims-mapped-to-fact-ids",
                "latest-corrections-applied",
                "ambiguous-actions-not-upgraded-or-conflated",
                "no-invented-quote-or-story-smoothing",
                "ai-output-not-promoted-to-fact",
            ),
        ),
        (
            "single_task",
            (
                "one-primary-audience",
                "one-primary-question",
                "one-service-capability",
                "nonessential-content-removed-or-visual-only",
            ),
        ),
        (
            "service_causality",
            (
                "customer-pressure-is-hook",
                "creator-action-changes-process",
                "customer-quote-supports-not-substitutes",
                "normal-process-not-claimed-as-creator-credit",
                "viewer-can-name-service-action-and-boundary",
            ),
        ),
        (
            "interview_integrity",
            (
                "quote-reheard-and-timecoded",
                "prompt-context-preserved",
                "no-spliced-praise",
                "quote-proves-only-lived-experience",
                "objective-facts-use-records",
            ),
        ),
        (
            "distribution_compliance",
            (
                "content-classification-recorded",
                "current-and-future-rules-separated",
                "institution-review-route-recorded",
                "authorized-person-and-account-route-recorded",
                "advertising-and-ai-label-assessed",
                "no-education-or-private-domain-exemption-assumed",
            ),
        ),
        (
            "medical_insurance",
            (
                "no-medical-decision-substitution",
                "no-treatment-superiority-generalization",
                "policy-specific-boundary",
                "no-unconfirmed-claim-promise",
                "service-scope-not-implied-free-or-universal",
            ),
        ),
        (
            "privacy_authorization",
            (
                "service-data-publication-consent-separated",
                "subject-and-patient-authorization-separated",
                "face-voice-health-claim-and-platform-scope-recorded",
                "reidentification-risk-reviewed",
                "screens-and-identifiers-redacted",
                "final-cut-approval-required",
                "withdrawal-route-recorded",
            ),
        ),
        (
            "title_opening_alignment",
            (
                "title-opening-body-cta-same-promise",
                "first-five-seconds-concrete",
                "no-fear-bait-or-hidden-condition",
                "body-can-fulfill-hook",
            ),
        ),
        (
            "voice_ai_trace",
            (
                "preliminary-spoken-language-pass-complete",
                "no-stagey-turn-or-neat-moral",
                "no-repetitive-contrast-or-symmetry",
                "concrete-actions-over-abstract-praise",
                "natural-rhythm-not-uniform",
            ),
        ),
        (
            "cta_product",
            (
                "cta-matches-proven-capability",
                "paid-and-included-service-boundary-clear",
                "next-step-is-minimum-necessary",
                "no-sudden-hard-sell",
            ),
        ),
        (
            "production_series",
            (
                "standalone-comprehensible",
                "neighbor-episode-overlap-reviewed",
                "audio-and-visual-role-defined",
                "length-and-cut-order-feasible",
                "single-test-variable",
            ),
        ),
    ]
)

OPTIONAL_GATES = {"interview_integrity", "cta_product"}
CTA_REQUIRED_GOALS = {"acquisition", "consultation", "conversion"}


class InitialDraftGateError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InitialDraftGateError("invalid_or_missing_artifact", f"{label}: {error}") from error


def _validate_schema(value: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        detail = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:8]
        )
        raise InitialDraftGateError("schema_validation_failed", f"{label}: {detail}")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _body_sha256(script: dict[str, Any]) -> str:
    return research_adapter.sha256_value(case_adapter.stable_body_payload(script))


def _expected_decision(review: dict[str, Any]) -> str:
    statuses = {row["status"] for row in review["gates"].values()}
    if "blocked" in statuses:
        return "blocked_from_downstream"
    if "needs_revision" in statuses:
        return "return_for_revision"
    return "approved_for_voice_pipeline"


def _validate_gate_coverage(script: dict[str, Any], review: dict[str, Any]) -> None:
    gates = review["gates"]
    if set(gates) != set(GATE_CHECKS):
        raise InitialDraftGateError("initial_draft_review_incomplete", "initial draft review omits a mandatory gate")
    has_interview = bool(script.get("interview_slots"))
    for gate_id, expected_checks in GATE_CHECKS.items():
        gate = gates[gate_id]
        if set(gate["reviewed_check_ids"]) != set(expected_checks):
            raise InitialDraftGateError(
                "initial_draft_review_incomplete",
                f"{gate_id} does not cover the exact mandatory checks",
            )
        if gate["status"] == "not_applicable":
            if gate_id not in OPTIONAL_GATES:
                raise InitialDraftGateError("initial_draft_review_invalid_na", f"{gate_id} cannot be not_applicable")
            if gate_id == "interview_integrity" and has_interview:
                raise InitialDraftGateError("initial_draft_review_invalid_na", "interview review is required when a slot exists")
            if gate_id == "cta_product" and review["content_goal"] in CTA_REQUIRED_GOALS:
                raise InitialDraftGateError("initial_draft_review_invalid_na", "CTA review is required for this content goal")
        if gate["status"] in {"needs_revision", "blocked"}:
            if not gate["findings"] or not gate["remediation"]:
                raise InitialDraftGateError(
                    "initial_draft_review_incomplete",
                    f"{gate_id} must record findings and remediation when it does not pass",
                )
        elif gate["remediation"]:
            raise InitialDraftGateError(
                "initial_draft_review_inconsistent",
                f"{gate_id} cannot carry remediation after pass or not_applicable",
            )


def _validate_script_structure(script: dict[str, Any], review: dict[str, Any]) -> None:
    roles = [str(row.get("role")) for row in script.get("segments", [])]
    if "service-action" not in roles:
        raise InitialDraftGateError(
            "service_causality_missing",
            "a case-acquisition draft must contain a concrete service-action segment",
        )
    if review["content_goal"] in CTA_REQUIRED_GOALS and "cta" not in roles:
        raise InitialDraftGateError(
            "cta_missing_for_goal",
            "acquisition, consultation, and conversion drafts require a CTA segment",
        )
    if not str(script.get("single_question") or "").strip():
        raise InitialDraftGateError("single_task_missing", "single_question is required")
    capability = script.get("service_capability") or {}
    if not str(capability.get("statement") or "").strip():
        raise InitialDraftGateError("service_causality_missing", "service capability statement is required")


def validate_initial_draft_review(
    *,
    script_path: Path,
    review_path: Path,
    schema_path: Path = DEFAULT_SCHEMA,
    require_approved: bool = True,
    structure_route: str | None = None,
    story_card_path: Path | None = None,
    story_owner_root: Path | None = None,
) -> dict[str, Any]:
    script = _load_json(script_path, "case video initial draft")
    review = _load_json(review_path, "case video initial draft review")
    schema = _load_json(schema_path, "case video initial draft review schema")
    _validate_schema(review, schema, "case-video-initial-draft-review.v1")

    for key in ("script_id", "content_id", "synthetic_only"):
        if review[key] != script.get(key):
            raise InitialDraftGateError("initial_draft_review_identity_drift", f"review {key} does not match draft")
    if review["input_fact_card_ref"] != script.get("inputs", {}).get("fact_card_ref"):
        raise InitialDraftGateError(
            "initial_draft_review_fact_revision_drift",
            "review is bound to a different canonical fact-card revision",
        )
    body_sha256 = _body_sha256(script)
    if review["input_body_sha256"] != body_sha256:
        raise InitialDraftGateError("initial_draft_review_body_hash_drift", "review is stale for the current draft")

    _validate_gate_coverage(script, review)
    _validate_script_structure(script, review)
    narrative_findings = []
    if structure_route or script.get("structure_route") or review.get("story_realization") is not None:
        validate_storycraft_binding()
    if structure_route and script.get("structure_route", structure_route) != structure_route:
        raise InitialDraftGateError("story_route_mismatch", "declared draft and selected route differ")
    route = structure_route or script.get("structure_route")
    if route == "story-arc" or review.get("story_realization") is not None:
        card = load_story_card(script, story_card_path, owner_root=story_owner_root)
        try:
            narrative_findings = narrative_realization.validate(
                script, review.get("story_realization"), card, body_sha256)
        except narrative_realization.NarrativeError as error:
            raise InitialDraftGateError(error.code, str(error)) from error
        if narrative_findings and review["decision"] == "approved_for_voice_pipeline":
            raise InitialDraftGateError("story_realization_unresolved", ", ".join(narrative_findings))
    elif story_card_path is not None:
        raise InitialDraftGateError("story_route_mismatch", "non-story review cannot bind a story card")
    expected = _expected_decision(review)
    if narrative_findings and expected == "approved_for_voice_pipeline":
        expected = "return_for_revision"
    if review["decision"] != expected:
        raise InitialDraftGateError(
            "initial_draft_review_decision_drift",
            f"decision must be {expected} for the recorded gate statuses",
        )
    if require_approved and expected != "approved_for_voice_pipeline":
        failed = sorted(
            gate_id
            for gate_id, gate in review["gates"].items()
            if gate["status"] in {"needs_revision", "blocked"}
        )
        raise InitialDraftGateError(
            "initial_draft_review_blocked",
            f"draft cannot enter the voice pipeline; unresolved gates: {failed}",
        )
    return {
        "status": "initial_draft_review_passed" if expected == "approved_for_voice_pipeline" else expected,
        "script_id": script["script_id"],
        "content_id": script["content_id"],
        "input_body_sha256": body_sha256,
        "input_fact_card_ref": review["input_fact_card_ref"],
        "review_id": review["review_id"],
        "review_sha256": research_adapter.sha256_value(review),
        "decision": expected,
        "publication_boundary": review["publication_boundary"],
        "narrative_findings": narrative_findings,
    }


def load_story_card(script, path, *, owner_root=None):
    if path is None:
        raise InitialDraftGateError("story_design_required", "supply the current Story Design Card")
    owner_root = Path(owner_root) if owner_root is not None else STUDIO_ROOT.parent / "self-media-creation-system"
    gate_path = owner_root / "scripts/story_design_gate.py"
    spec = importlib.util.spec_from_file_location("initial_review_story_design", gate_path)
    gate = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(gate)
        card = gate.load_json(path)
        gate.validate_receipt(card)
        fact = gate.load_json(gate.resolve_ref(card["fact_binding"]["fact_card_ref"]))
    except (OSError, ValueError, RuntimeError) as error:
        raise InitialDraftGateError("story_design_invalid", str(error)) from error
    expected = script["inputs"]["fact_card_ref"]
    if (bool(fact.get("synthetic_only")) != bool(script["synthetic_only"]) or
        (card["story_source"]["identity_treatment"] == "synthetic") != bool(script["synthetic_only"])):
        raise InitialDraftGateError("story_classification_drift", "story design and draft data classification differ")
    if (fact.get("fact_card_id") != expected["artifact_id"] or
        research_adapter.sha256_value(fact) != expected["sha256"]):
        raise InitialDraftGateError("story_fact_revision_drift", "story card uses another fact-card revision")
    if card["content_id"] != script["content_id"]:
        raise InitialDraftGateError("story_content_drift", "story card belongs to another content item")
    return card


def build_review_template(
    *, script_path: Path, output_path: Path, content_goal: str, reviewer: str, reviewed_at: str,
    structure_route: str | None = None, story_card_path: Path | None = None,
    story_owner_root: Path | None = None,
) -> dict[str, Any]:
    script = _load_json(script_path, "case video initial draft")
    synthetic = bool(script.get("synthetic_only"))
    review_mode = "synthetic-fixture-review" if synthetic else "human-local-editorial-review"
    gates = {}
    for gate_id, check_ids in GATE_CHECKS.items():
        gates[gate_id] = {
            "status": "needs_revision",
            "reviewed_check_ids": list(check_ids),
            "findings": ["待人工逐项确认。"],
            "remediation": ["完成检查后，将本门改为 pass、not_applicable 或 blocked，并记录依据。"],
            "evidence": ["尚未填写。"],
        }
    review = {
        "schema_version": "case-video-initial-draft-review.v1",
        "review_id": "initial-draft-review-" + research_adapter.stable_suffix(
            script["script_id"], _body_sha256(script), content_goal, length=20
        ),
        "script_id": script["script_id"],
        "content_id": script["content_id"],
        "synthetic_only": synthetic,
        "stage": "post-storycraft-pre-voice",
        "content_goal": content_goal,
        "input_body_sha256": _body_sha256(script),
        "input_fact_card_ref": script["inputs"]["fact_card_ref"],
        "gates": gates,
        "review_mode": review_mode,
        "reviewer": "synthetic-fixture-reviewer" if synthetic else reviewer,
        "reviewed_at": reviewed_at,
        "decision": "return_for_revision",
        "publication_boundary": "manual-only",
    }
    if (structure_route or script.get("structure_route")) == "story-arc":
        card = load_story_card(script, story_card_path, owner_root=story_owner_root)
        review["story_realization"] = narrative_realization.template(script, card, _body_sha256(script))
    _write_json(output_path, review)
    return review


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--script", type=Path, required=True)
    validate.add_argument("--review", type=Path, required=True)
    validate.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    validate.add_argument("--allow-return", action="store_true")
    validate.add_argument("--structure-route", choices=["story-arc", "direct-answer"], required=True)
    validate.add_argument("--story-card", type=Path)
    validate.add_argument("--story-owner-root", type=Path)
    template = subparsers.add_parser("template")
    template.add_argument("--script", type=Path, required=True)
    template.add_argument("--output", type=Path, required=True)
    template.add_argument("--content-goal", required=True)
    template.add_argument("--reviewer", default="local-editor-author")
    template.add_argument("--reviewed-at", required=True)
    template.add_argument("--structure-route", choices=["story-arc", "direct-answer"], required=True)
    template.add_argument("--story-card", type=Path)
    template.add_argument("--story-owner-root", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "template":
            review = build_review_template(
                script_path=args.script,
                output_path=args.output,
                content_goal=args.content_goal,
                reviewer=args.reviewer,
                reviewed_at=args.reviewed_at,
                structure_route=args.structure_route, story_card_path=args.story_card,
                story_owner_root=args.story_owner_root,
            )
            result = {
                "status": "initial_draft_review_template_created",
                "output": str(args.output.resolve()),
                "decision": review["decision"],
            }
        else:
            result = validate_initial_draft_review(
                script_path=args.script,
                review_path=args.review,
                schema_path=args.schema,
                require_approved=not args.allow_return,
                structure_route=args.structure_route, story_card_path=args.story_card,
                story_owner_root=args.story_owner_root,
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (InitialDraftGateError, case_adapter.CaseScriptError) as error:
        code = getattr(error, "code", "initial_draft_review_blocked")
        print(
            json.dumps({"status": code, "message": str(error)}, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
