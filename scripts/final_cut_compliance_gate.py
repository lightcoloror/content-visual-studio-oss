#!/usr/bin/env python3
"""Validate an exact final-cut review before a human publishes a case video."""

from __future__ import annotations
from studio_paths import STUDIO_ROOT, HUMAN_VOICE_ROOT, research_schema_path

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

import research_output_adapter as research_adapter



DEFAULT_SCHEMA = STUDIO_ROOT / "schemas/case-video-final-cut-compliance-review.v1.schema.json"

GATE_CHECKS = {
    "exact_artifact_binding": {
        "approved-script-review-hash-verified", "final-video-hash-verified",
        "subtitle-hash-verified", "cover-hash-verified",
    },
    "institution_account": {
        "person-institution-role-disclosed", "institution-approved-exact-content",
        "publishing-account-authorized", "platform-and-audience-within-scope",
    },
    "consent_privacy": {
        "participant-patient-third-party-consent-valid", "final-cut-shown-and-confirmed",
        "face-voice-health-claim-scope-within-consent", "identifiers-and-reidentification-risk-rechecked",
    },
    "disclosure_labels": {
        "insurance-limitations-visible", "advertising-label-assessed-and-applied",
        "ai-label-assessed-and-applied", "title-caption-cta-not-materially-misleading",
    },
    "rights": {
        "image-audio-music-font-quote-rights-cleared", "no-unauthorized-customer-record",
        "platform-derivative-reuse-within-consent",
    },
    "platform_preview": {
        "crop-subtitle-audio-and-cover-reviewed", "platform-compressed-file-reviewed",
        "links-comment-prompts-and-cta-reviewed", "no-post-approval-edit",
    },
    "archive_withdrawal": {
        "evidence-package-path-recorded", "correction-withdrawal-owner-recorded",
        "published-instance-verification-planned", "manual-publication-only",
    },
}


class FinalCutGateError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FinalCutGateError("invalid_or_missing_artifact", f"{label}: {error}") from error


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise FinalCutGateError("final_cut_artifact_missing", f"missing final-cut artifact: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def final_cut_subject_payload(review: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope_version": "case-video-final-cut-review-subject.v1",
        "script_id": review["script_id"],
        "content_id": review["content_id"],
        "synthetic_only": review["synthetic_only"],
        "inputs": review["inputs"],
        "publication_instance": review["publication_instance"],
    }


def validate_final_cut_review(
    *,
    review_path: Path,
    script_review_path: Path,
    final_video_path: Path,
    subtitles_path: Path,
    cover_path: Path,
    schema_path: Path = DEFAULT_SCHEMA,
) -> dict[str, Any]:
    review = _load_json(review_path, "final-cut review")
    schema = _load_json(schema_path, "final-cut review schema")
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(review),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        detail = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:8]
        )
        raise FinalCutGateError("schema_validation_failed", detail)

    expected_hashes = {
        "script_review": _sha256_file(script_review_path),
        "final_video": _sha256_file(final_video_path),
        "subtitles": _sha256_file(subtitles_path),
        "cover": _sha256_file(cover_path),
    }
    for key, expected in expected_hashes.items():
        if review["inputs"][key]["sha256"] != expected:
            raise FinalCutGateError("final_cut_artifact_hash_drift", f"{key} changed after review")

    script_review = _load_json(script_review_path, "script review")
    for key in ("script_id", "content_id", "synthetic_only"):
        if review[key] != script_review.get(key):
            raise FinalCutGateError("final_cut_identity_drift", f"{key} does not match script review")
    if script_review.get("decision") != "approved_for_candidate_projection":
        raise FinalCutGateError("script_review_not_approved", "final cut is not based on an approved candidate script")

    if set(review["gates"]) != set(GATE_CHECKS):
        raise FinalCutGateError("final_cut_review_incomplete", "final-cut review omits a mandatory gate")
    for gate_id, expected_checks in GATE_CHECKS.items():
        gate = review["gates"][gate_id]
        if gate["status"] != "pass" or set(gate["reviewed_check_ids"]) != expected_checks:
            raise FinalCutGateError("final_cut_review_incomplete", f"{gate_id} lacks exact mandatory checks")

    expected_subject = research_adapter.sha256_value(final_cut_subject_payload(review))
    if review["subject_sha256"] != expected_subject:
        raise FinalCutGateError("final_cut_subject_hash_drift", "publication fields changed after final-cut review")
    publication = review["publication_instance"]
    if publication["advertising_label"] == "blocked" or publication["ai_generated_label"] == "blocked":
        raise FinalCutGateError("required_label_blocked", "a required publication label is unresolved")
    if review["synthetic_only"] and publication["audience_scope"] != "synthetic-dry-run":
        raise FinalCutGateError("synthetic_publication_blocked", "synthetic review cannot authorize a live audience")
    if not review["synthetic_only"] and publication["audience_scope"] == "synthetic-dry-run":
        raise FinalCutGateError("publication_scope_invalid", "real final cut needs an actual audience scope")

    return {
        "status": review["decision"],
        "review_id": review["review_id"],
        "script_id": review["script_id"],
        "content_id": review["content_id"],
        "subject_sha256": expected_subject,
        "publication_boundary": "manual-only",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--script-review", type=Path, required=True)
    parser.add_argument("--final-video", type=Path, required=True)
    parser.add_argument("--subtitles", type=Path, required=True)
    parser.add_argument("--cover", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = validate_final_cut_review(
            review_path=args.review,
            script_review_path=args.script_review,
            final_video_path=args.final_video,
            subtitles_path=args.subtitles,
            cover_path=args.cover,
            schema_path=args.schema,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except FinalCutGateError as error:
        print(json.dumps({"status": error.code, "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
