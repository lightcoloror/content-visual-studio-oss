#!/usr/bin/env python3
"""Apply a local human-voice rewrite and emit hash-bound manual gate receipts.

This adapter deliberately does not install or impersonate the workspace draft
``human-voice-editor`` skill.  It extracts a small deterministic rule set,
records the draft's governance status, applies explicit segment replacements,
and refuses to produce a final case script until read-aloud and author-voice
confirmation are bound to the rewritten body.
"""

from __future__ import annotations
from studio_paths import STUDIO_ROOT, HUMAN_VOICE_ROOT, research_schema_path

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

import case_video_script_adapter as case_adapter
import initial_draft_quality_gate
import research_output_adapter as research_adapter


ADAPTER_VERSION = "1.1.0"
WORKSPACE = STUDIO_ROOT

DEFAULT_REQUEST_SCHEMA = STUDIO_ROOT / "schemas/case-video-human-voice-request.v1.schema.json"
DEFAULT_RECEIPT_SCHEMA = STUDIO_ROOT / "schemas/case-video-human-voice-receipt.v1.schema.json"
DEFAULT_INITIAL_REVIEW_SCHEMA = STUDIO_ROOT / "schemas/case-video-initial-draft-review.v1.schema.json"
SKILL_PATH = HUMAN_VOICE_ROOT / "SKILL.md"
RULEBOOK_PATH = HUMAN_VOICE_ROOT / "references/rulebook.md"

SYMMETRIC_PATTERNS = (
    re.compile(r"不是[^。！？；]{1,40}[，,、；;]?而是"),
    re.compile(r"不在于[^。！？；]{1,40}[，,、；;]?而在于"),
    re.compile(r"不只是[^。！？；]{1,40}[，,、；;]?更是"),
)
CTA_PATTERNS = (
    re.compile(r"(?:关注|点赞|收藏|转发|评论区|私信我|欢迎咨询)"),
    re.compile(r"如果你也.{0,30}(?:欢迎|可以|记得)"),
    re.compile(r"(?:总结一下|所以说到底|这就是我想说的)"),
)
OVER_EXPLAINED_MARKERS = (
    "这说明",
    "这体现",
    "也就是说",
    "换句话说",
    "归根结底",
    "本质上",
    "核心在于",
    "由此可见",
    "总结来说",
    "这就告诉我们",
)
TRANSLATION_MARKERS = (
    "与此同时",
    "此外",
    "进一步而言",
    "从某种意义上说",
    "不可否认",
    "值得注意的是",
    "因此可以看出",
)
ABSTRACT_SERVICE_MARKERS = (
    "赋能",
    "价值交付",
    "专业价值",
    "陪伴式服务",
    "全生命周期",
    "底层逻辑",
    "风险管理抓手",
    "服务闭环",
)


class HumanVoiceGateError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HumanVoiceGateError("invalid_or_missing_artifact", f"{label}: {error}") from error


def _validate(value: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        detail = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:8]
        )
        raise HumanVoiceGateError("schema_validation_failed", f"{label}: {detail}")


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        raise HumanVoiceGateError("human_voice_source_missing", f"required workspace draft is unavailable: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _spoken_text(script: dict[str, Any]) -> str:
    return "\n".join(str(row["spoken_text"]) for row in script.get("segments", []))


def _sentences(text: str) -> list[str]:
    return [
        re.sub(r"\s+", "", item)
        for item in re.split(r"[。！？!?；;\n]+", text)
        if re.sub(r"\s+", "", item)
    ]


def diagnose_human_voice(text: str) -> dict[str, Any]:
    symmetric = sum(len(pattern.findall(text)) for pattern in SYMMETRIC_PATTERNS)
    uniform_cta = sum(len(pattern.findall(text)) for pattern in CTA_PATTERNS)
    over_explained = sum(text.count(marker) for marker in OVER_EXPLAINED_MARKERS)
    translation_register = sum(text.count(marker) for marker in TRANSLATION_MARKERS)
    abstract_service_language = sum(text.count(marker) for marker in ABSTRACT_SERVICE_MARKERS)
    lengths = [len(sentence) for sentence in _sentences(text)]
    even_rhythm = int(len(lengths) >= 6 and max(lengths) - min(lengths) <= 2)
    issue_codes: list[str] = []
    if symmetric >= 2:
        issue_codes.append("symmetric-slogan")
    if uniform_cta >= 2:
        issue_codes.append("uniform-cta")
    if over_explained >= 2:
        issue_codes.append("over-explained")
    if even_rhythm:
        issue_codes.append("even-rhythm")
    if translation_register >= 2:
        issue_codes.append("translation-register")
    if abstract_service_language:
        issue_codes.append("abstract-service-language")
    return {
        "symmetric_slogan": symmetric,
        "uniform_cta": uniform_cta,
        "over_explained": over_explained,
        "even_rhythm": even_rhythm,
        "translation_register": translation_register,
        "abstract_service_language": abstract_service_language,
        "issue_codes": issue_codes,
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


SEMANTIC_CHECKS = {
    "production_note_leak", "conversation_correction_leak", "information_progression",
    "author_voice_fit", "fact_boundary",
}


def validate_editorial_evidence(base: dict[str, Any], rewritten: dict[str, Any], request: dict[str, Any]) -> bool:
    """Validate review evidence, never infer that a model or human actually performed it."""
    review = request.get("semantic_review")
    mode = request.get("editing_mode", "rewrite")
    if review is None:
        if mode == "review_without_rewrite":
            raise HumanVoiceGateError("editorial_review_missing", "unchanged draft requires span-bound editorial review")
        return False
    if (review["reviewer_kind"] == "synthetic_fixture") != bool(base["synthetic_only"]):
        raise HumanVoiceGateError("editorial_actor_drift", "synthetic review cannot be used for real material")
    for key, script in (("input_body_sha256", base), ("output_body_sha256", rewritten)):
        if review[key] != research_adapter.sha256_value(case_adapter.stable_body_payload(script)):
            raise HumanVoiceGateError("editorial_review_hash_drift", key)
    if {row["check_id"] for row in review["checks"]} != SEMANTIC_CHECKS:
        raise HumanVoiceGateError("editorial_review_incomplete", "all five editorial questions require distinct evidence")
    before = {row["segment_id"]: row["spoken_text"] for row in base["segments"]}
    after = {row["segment_id"]: row["spoken_text"] for row in rewritten["segments"]}
    resolved = False
    for row in review["checks"]:
        sid = row["segment_id"]
        if row["before_span"] not in before.get(sid, "") or row["after_span"] not in after.get(sid, ""):
            raise HumanVoiceGateError("editorial_span_unbound", row["check_id"])
        if row["status"] == "blocked":
            raise HumanVoiceGateError("editorial_review_blocked", row["check_id"])
        if row["status"] == "resolved":
            if row["before_span"] == row["after_span"] or row["before_span"] in after[sid]:
                raise HumanVoiceGateError("editorial_resolution_unproven", row["check_id"])
            resolved = True
    if mode == "review_without_rewrite" and (resolved or request["rewrite_operations"]):
        raise HumanVoiceGateError("unchanged_review_has_edits", "review_without_rewrite must preserve the body")
    return resolved


def _read_aloud_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope_version": "case-video-read-aloud.v1",
        "status": row["status"],
        "performed_by": row["performed_by"],
        "body_sha256": row["body_sha256"],
        "completed_at": row["completed_at"],
        "notes": row["notes"],
    }


def _author_payload(row: dict[str, Any], read_aloud_sha256: str) -> dict[str, Any]:
    return {
        "scope_version": "case-video-author-voice-confirmation.v1",
        "status": row["status"],
        "performed_by": row["performed_by"],
        "body_sha256": row["body_sha256"],
        "read_aloud_receipt_sha256": read_aloud_sha256,
        "confirmed_at": row["confirmed_at"],
        "voice_match": row["voice_match"],
        "facts_preserved": row["facts_preserved"],
    }


def apply_human_voice_gate(
    *,
    base_script_path: Path,
    initial_draft_review_path: Path,
    request_path: Path,
    fact_card_path: Path,
    output_script_path: Path,
    output_receipt_path: Path,
    request_schema_path: Path = DEFAULT_REQUEST_SCHEMA,
    receipt_schema_path: Path = DEFAULT_RECEIPT_SCHEMA,
    initial_draft_review_schema_path: Path = DEFAULT_INITIAL_REVIEW_SCHEMA,
    story_card_path: Path | None = None,
    story_owner_root: Path | None = None,
) -> dict[str, Any]:
    base = _load_json(base_script_path, "base case script")
    request = _load_json(request_path, "human voice request")
    fact_card = _load_json(fact_card_path, "fact card")
    request_schema = _load_json(request_schema_path, "human voice request schema")
    receipt_schema = _load_json(receipt_schema_path, "human voice receipt schema")
    _validate(request, request_schema, "case-video-human-voice-request.v1")

    initial_review_result = initial_draft_quality_gate.validate_initial_draft_review(
        script_path=base_script_path,
        review_path=initial_draft_review_path,
        schema_path=initial_draft_review_schema_path,
        require_approved=True,
        story_card_path=story_card_path,
        story_owner_root=story_owner_root,
    )
    initial_review = _load_json(initial_draft_review_path, "initial draft review")
    initial_review_ref = {
        "artifact_id": initial_review["review_id"],
        "schema_version": initial_review["schema_version"],
        "sha256": research_adapter.sha256_value(initial_review),
    }
    if request["initial_draft_review_ref"] != initial_review_ref:
        raise HumanVoiceGateError(
            "initial_draft_review_ref_drift",
            "human voice request does not bind the approved initial draft review",
        )

    for key in ("script_id", "content_id", "synthetic_only"):
        if request[key] != base.get(key):
            raise HumanVoiceGateError("voice_request_identity_drift", f"request {key} does not match base script")
    if request["synthetic_only"]:
        expected_actor = "synthetic-fixture-author"
    else:
        expected_actor = "author"
    if request["read_aloud"]["performed_by"] != expected_actor:
        raise HumanVoiceGateError("read_aloud_actor_drift", "read-aloud actor does not match data classification")
    if request["author_confirmation"]["performed_by"] != expected_actor:
        raise HumanVoiceGateError("author_confirmation_actor_drift", "author confirmation actor does not match classification")

    before_text = _spoken_text(base)
    mode = request.get("editing_mode", "rewrite")
    if mode == "rewrite" and not request["rewrite_operations"]:
        raise HumanVoiceGateError("rewrite_no_change", "rewrite mode requires an actual edit")
    diagnostics_before = diagnose_human_voice(before_text)
    rewritten = copy.deepcopy(base)
    segments = {row["segment_id"]: row for row in rewritten.get("segments", [])}
    seen: set[str] = set()
    for operation in request["rewrite_operations"]:
        segment_id = operation["segment_id"]
        if segment_id in seen:
            raise HumanVoiceGateError("duplicate_rewrite_target", f"rewrite repeats {segment_id}")
        seen.add(segment_id)
        segment = segments.get(segment_id)
        if segment is None:
            raise HumanVoiceGateError("rewrite_target_missing", f"rewrite target is missing: {segment_id}")
        if _text_sha256(str(segment["spoken_text"])) != operation["before_text_sha256"]:
            raise HumanVoiceGateError("rewrite_input_hash_drift", f"rewrite input changed for {segment_id}")
        replacement = operation["replacement_text"].strip()
        if replacement == str(segment["spoken_text"]).strip():
            raise HumanVoiceGateError("rewrite_no_change", f"rewrite does not change {segment_id}")
        segment["spoken_text"] = replacement

    rewritten["body_status"] = "stable"
    if "pre_voice" in rewritten:
        rewritten["pre_voice"] = False
    rewritten["hook_candidates"] = copy.deepcopy(request["post_freeze_hooks"])
    rewritten["selected_hook_id"] = request["post_freeze_selected_hook_id"]
    after_text = _spoken_text(rewritten)
    diagnostics_after = diagnose_human_voice(after_text)
    semantic_repair = validate_editorial_evidence(base, rewritten, request)
    if base.get("structure_route") == "story-arc" or initial_review.get("story_realization"):
        card = initial_draft_quality_gate.load_story_card(rewritten, story_card_path, owner_root=story_owner_root)
        try:
            findings = initial_draft_quality_gate.narrative_realization.validate(
                rewritten, request.get("semantic_review", {}).get("story_realization"), card,
                research_adapter.sha256_value(case_adapter.stable_body_payload(rewritten)))
        except ValueError as error:
            raise HumanVoiceGateError(getattr(error, "code", "story_realization_invalid"), str(error)) from error
        if findings:
            raise HumanVoiceGateError("story_realization_unresolved", ", ".join(findings))
    if diagnostics_after["issue_codes"]:
        raise HumanVoiceGateError(
            "human_voice_semantic_gate_blocked",
            "rewritten narration still contains: " + ", ".join(diagnostics_after["issue_codes"]),
        )
    if mode == "rewrite" and not diagnostics_before["issue_codes"] and not semantic_repair:
        raise HumanVoiceGateError("human_voice_rewrite_unproven", "input has no diagnosed voice issue to repair")
    if mode == "rewrite" and not semantic_repair and len(diagnostics_after["issue_codes"]) >= len(diagnostics_before["issue_codes"]):
        raise HumanVoiceGateError("human_voice_rewrite_unproven", "rewrite did not reduce diagnosed voice issues")

    before_numbers = case_adapter._numeric_tokens(before_text)
    after_numbers = case_adapter._numeric_tokens(after_text)
    if before_numbers != after_numbers:
        raise HumanVoiceGateError("rewrite_numeric_fact_drift", "rewrite changed numeric tokens")
    case_adapter._validate_sensitive_and_risky_language(rewritten, fact_card)

    input_body_sha256 = research_adapter.sha256_value(case_adapter.stable_body_payload(base))
    rewritten_body_sha256 = research_adapter.sha256_value(case_adapter.stable_body_payload(rewritten))
    if mode == "rewrite" and input_body_sha256 == rewritten_body_sha256:
        raise HumanVoiceGateError("rewrite_no_change", "stable body hash did not change")
    if mode == "review_without_rewrite" and input_body_sha256 != rewritten_body_sha256:
        raise HumanVoiceGateError("unchanged_review_has_edits", "unchanged review cannot alter stable body")
    if request["read_aloud"]["body_sha256"] != rewritten_body_sha256:
        raise HumanVoiceGateError("read_aloud_body_hash_drift", "read-aloud receipt is not bound to rewritten body")
    if request["author_confirmation"]["body_sha256"] != rewritten_body_sha256:
        raise HumanVoiceGateError("author_confirmation_body_hash_drift", "author confirmation is stale")
    if request["hook_input_body_sha256"] != rewritten_body_sha256:
        raise HumanVoiceGateError("hook_body_hash_drift", "hook was generated before the rewritten body was frozen")
    if request["post_freeze_selected_hook_id"] not in {
        row["hook_id"] for row in request["post_freeze_hooks"]
    }:
        raise HumanVoiceGateError("selected_hook_missing", "selected hook is not present after body freeze")

    read_aloud_payload = _read_aloud_payload(request["read_aloud"])
    read_aloud_sha256 = research_adapter.sha256_value(read_aloud_payload)
    author_payload = _author_payload(request["author_confirmation"], read_aloud_sha256)
    author_sha256 = research_adapter.sha256_value(author_payload)
    hook_sha256 = research_adapter.sha256_value(
        case_adapter.hook_bundle_payload(rewritten, rewritten_body_sha256)
    )
    dbs_content_sha256 = research_adapter.sha256_value(request["dbs_content_diagnosis"])
    dbs_ai_sha256 = research_adapter.sha256_value(request["dbs_ai_check_diagnosis"])

    source = {
        "skill_id": "human-voice-editor",
        "skill_path": "skills/human-voice-editor/SKILL.md",
        "skill_sha256": _file_sha256(SKILL_PATH),
        "rulebook_sha256": _file_sha256(RULEBOOK_PATH),
        "governance_status": "workspace-draft-uninstalled",
        "execution_mode": "local-deterministic-adapter",
    }
    receipt = {
        "schema_version": "case-video-human-voice-receipt.v1",
        "receipt_id": "voice-receipt-" + research_adapter.stable_suffix(
            base["script_id"], rewritten_body_sha256, author_sha256, length=20
        ),
        "script_id": base["script_id"],
        "content_id": base["content_id"],
        "synthetic_only": base["synthetic_only"],
        "source": source,
        "initial_draft_review_ref": initial_review_ref,
        "input_body_sha256": input_body_sha256,
        "dbs_content_diagnosis_sha256": dbs_content_sha256,
        "dbs_ai_check_diagnosis_sha256": dbs_ai_sha256,
        "rewritten_body_sha256": rewritten_body_sha256,
        "rewrite_operations_sha256": research_adapter.sha256_value(request["rewrite_operations"]),
        "diagnostics_before": diagnostics_before,
        "diagnostics_after": diagnostics_after,
        "read_aloud": copy.deepcopy(request["read_aloud"]) | {"receipt_sha256": read_aloud_sha256},
        "author_confirmation": copy.deepcopy(request["author_confirmation"])
        | {"read_aloud_receipt_sha256": read_aloud_sha256, "receipt_sha256": author_sha256},
        "hook_gate": {
            "previous_hooks_invalidated": True,
            "generated_after_author_confirmation": True,
            "input_body_sha256": rewritten_body_sha256,
            "bundle_sha256": hook_sha256,
        },
        "fact_boundary": {
            "evidence_refs_unchanged": True,
            "numeric_tokens_unchanged": True,
            "medical_insurance_gate_passed": True,
        },
        "boundaries": {
            "local_only": True,
            "external_service_called": False,
            "raw_sensitive_media_included": False,
            "draft_only": True,
            "manual_only": True,
            "would_publish": False,
        },
    }
    # Keep legacy fixture/review hashes stable; new editorial requests opt into
    # the richer assessment projection instead of rewriting historical receipts.
    if "editing_mode" in request or request.get("semantic_review"):
        receipt.update({
            "editing_outcome": "reviewed_unchanged" if mode == "review_without_rewrite" else "rewritten",
            "semantic_review_sha256": research_adapter.sha256_value(request["semantic_review"]) if request.get("semantic_review") else None,
            "assessment_scope": "artifact-and-review-validation; not proof of human authorship, actual Skill invocation, or audience response",
        })
    _validate(receipt, receipt_schema, "case-video-human-voice-receipt.v1")
    receipt_ref = {
        "artifact_id": receipt["receipt_id"],
        "schema_version": receipt["schema_version"],
        "sha256": research_adapter.sha256_value(receipt),
    }
    rewritten.setdefault("inputs", {})["human_voice_receipt_ref"] = receipt_ref
    rewritten["skill_stage_receipts"] = [
        {
            "sequence": 1,
            "skill_id": "content-fact-card",
            "role": "hard-gate",
            "input_sha256": rewritten["inputs"].get("research_output_ref", rewritten["inputs"]["fact_card_ref"])["sha256"],
            "output_sha256": rewritten["inputs"]["fact_card_ref"]["sha256"],
            "status": "passed",
            "synthetic_stub": bool(rewritten["synthetic_only"]),
        },
        {
            "sequence": 2,
            "skill_id": "insurance-content-storycraft",
            "role": "story-method",
            "input_sha256": rewritten["inputs"]["fact_card_ref"]["sha256"],
            "output_sha256": input_body_sha256,
            "status": "passed",
            "synthetic_stub": bool(rewritten["synthetic_only"]),
        },
        {
            "sequence": 3,
            "skill_id": "dbs-content",
            "role": "diagnosis",
            "input_sha256": input_body_sha256,
            "output_sha256": dbs_content_sha256,
            "status": "passed",
            "synthetic_stub": bool(rewritten["synthetic_only"]),
        },
        {
            "sequence": 4,
            "skill_id": "dbs-ai-check",
            "role": "ai-trace-diagnosis",
            "input_sha256": dbs_content_sha256,
            "output_sha256": dbs_ai_sha256,
            "status": "passed",
            "synthetic_stub": bool(rewritten["synthetic_only"]),
        },
        {
            "sequence": 5,
            "skill_id": "human-voice-editor",
            "role": "local-rewrite",
            "input_sha256": dbs_ai_sha256,
            "output_sha256": rewritten_body_sha256,
            "status": "passed",
            "synthetic_stub": bool(rewritten["synthetic_only"]),
        },
        {
            "sequence": 6,
            "skill_id": "read-aloud",
            "role": "manual-read-aloud",
            "input_sha256": rewritten_body_sha256,
            "output_sha256": read_aloud_sha256,
            "status": "passed",
            "synthetic_stub": bool(rewritten["synthetic_only"]),
        },
        {
            "sequence": 7,
            "skill_id": "author-voice-confirmation",
            "role": "manual-author-confirmation",
            "input_sha256": read_aloud_sha256,
            "output_sha256": author_sha256,
            "status": "passed",
            "synthetic_stub": bool(rewritten["synthetic_only"]),
        },
        {
            "sequence": 8,
            "skill_id": "dbs-hook",
            "role": "post-freeze-hook-candidates",
            "input_sha256": author_sha256,
            "output_sha256": hook_sha256,
            "status": "passed",
            "synthetic_stub": bool(rewritten["synthetic_only"]),
        },
    ]
    rewritten["provenance"]["adapter_version"] = "1.2.0"
    _write_json(output_receipt_path, receipt)
    _write_json(output_script_path, rewritten)
    return {
        "status": "human_voice_gate_passed",
        "script_id": rewritten["script_id"],
        "content_id": rewritten["content_id"],
        "output_script": str(output_script_path.resolve()),
        "output_receipt": str(output_receipt_path.resolve()),
        "input_body_sha256": input_body_sha256,
        "rewritten_body_sha256": rewritten_body_sha256,
        "hook_bundle_sha256": hook_sha256,
        "initial_draft_review_id": initial_review_result["review_id"],
        "manual_author_confirmation_required_for_real_case": not bool(rewritten["synthetic_only"]),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-script", type=Path, required=True)
    parser.add_argument("--initial-draft-review", type=Path, required=True)
    parser.add_argument("--rewrite-request", type=Path, required=True)
    parser.add_argument("--fact-card", type=Path, required=True)
    parser.add_argument("--story-card", type=Path)
    parser.add_argument("--story-owner-root", type=Path)
    parser.add_argument("--output-script", type=Path, required=True)
    parser.add_argument("--output-receipt", type=Path, required=True)
    parser.add_argument("--request-schema", type=Path, default=DEFAULT_REQUEST_SCHEMA)
    parser.add_argument("--receipt-schema", type=Path, default=DEFAULT_RECEIPT_SCHEMA)
    parser.add_argument("--initial-draft-review-schema", type=Path, default=DEFAULT_INITIAL_REVIEW_SCHEMA)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = apply_human_voice_gate(
            base_script_path=args.base_script,
            initial_draft_review_path=args.initial_draft_review,
            request_path=args.rewrite_request,
            fact_card_path=args.fact_card,
            output_script_path=args.output_script,
            output_receipt_path=args.output_receipt,
            request_schema_path=args.request_schema,
            receipt_schema_path=args.receipt_schema,
            initial_draft_review_schema_path=args.initial_draft_review_schema,
            story_card_path=args.story_card,
            story_owner_root=args.story_owner_root,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (
        HumanVoiceGateError,
        initial_draft_quality_gate.InitialDraftGateError,
        case_adapter.CaseScriptError,
    ) as error:
        code = getattr(error, "code", "human_voice_gate_blocked")
        print(json.dumps({"status": code, "message": str(error)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
