#!/usr/bin/env python3
"""Validate a high-risk case-video sidecar and project it into the existing video brief.

The adapter owns only a draft-only contract boundary.  It reuses the canonical
research graph, content-item, and existing video brief; it does not own content,
publication, review, or video-production state.
"""

from __future__ import annotations
from studio_paths import STUDIO_ROOT, HUMAN_VOICE_ROOT, research_schema_path

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

import research_output_adapter as research_adapter


ADAPTER_VERSION = "1.3.0"
WORKSPACE = STUDIO_ROOT

DEFAULT_SCRIPT_SCHEMA = STUDIO_ROOT / "schemas/case-video-script.v1.schema.json"
DEFAULT_REVIEW_SCHEMA = STUDIO_ROOT / "schemas/case-video-review-receipt.v1.schema.json"
DEFAULT_VOICE_SCHEMA = STUDIO_ROOT / "schemas/case-video-human-voice-receipt.v1.schema.json"
DEFAULT_INTERVIEW_SCHEMA = STUDIO_ROOT / "schemas/case-video-deidentified-interview-receipt.v1.schema.json"
DEFAULT_FACT_SCHEMA = STUDIO_ROOT / "schemas/content-fact-card.v0.schema.json"
DEFAULT_ROUTE_SCHEMA = STUDIO_ROOT / "schemas/content-route-card.v0.schema.json"
DEFAULT_HANDOFF_SCHEMA = STUDIO_ROOT / "schemas/case-video-script-handoff.v1.schema.json"
DEFAULT_RESEARCH_SCHEMA = research_schema_path()
DEFAULT_CONTENT_SCHEMA = STUDIO_ROOT / "schemas/content-item.schema.json"
DEFAULT_VIDEO_SCHEMA = STUDIO_ROOT / "schemas/content-video-brief.v1.schema.json"
HUMAN_VOICE_SKILL = HUMAN_VOICE_ROOT / "SKILL.md"
HUMAN_VOICE_RULEBOOK = HUMAN_VOICE_ROOT / "references/rulebook.md"

REQUIRED_SKILL_SEQUENCE = [
    ("content-fact-card", "hard-gate"),
    ("insurance-content-storycraft", "story-method"),
    ("dbs-content", "diagnosis"),
    ("dbs-ai-check", "ai-trace-diagnosis"),
    ("human-voice-editor", "local-rewrite"),
    ("read-aloud", "manual-read-aloud"),
    ("author-voice-confirmation", "manual-author-confirmation"),
    ("dbs-hook", "post-freeze-hook-candidates"),
]
REQUIRED_REVIEWS = {
    "fact",
    "privacy",
    "medical-insurance",
    "authorization",
    "rights",
    "voice",
    "video-production",
}
COMPLIANCE_GATE_CHECKS = {
    "identity_account_authorization": {
        "person-role-recorded",
        "publishing-account-recorded",
        "institution-review-status-recorded",
        "no-education-or-private-domain-exemption-assumed",
    },
    "content_basis_accuracy": {
        "official-current-rule-source-recorded",
        "future-rule-effective-date-separated",
        "product-version-or-not-applicable-recorded",
        "case-claims-traceable-to-evidence",
    },
    "suitability": {
        "public-content-not-personal-recommendation",
        "specific-product-fit-boundary-recorded",
        "no-pressure-or-platform-circumvention",
        "cta-does-not-bypass-needed-assessment",
    },
    "key_matters_disclosure": {
        "identity-and-institution-disclosure-planned",
        "policy-limitations-and-conditions-visible",
        "no-material-condition-omitted",
        "advertising-and-ai-label-assessed",
    },
    "customer_autonomy_privacy": {
        "service-data-and-publication-consent-separated",
        "subject-patient-third-party-consent-separated",
        "face-voice-health-claim-scope-recorded",
        "reidentification-withdrawal-and-deletion-addressed",
    },
    "traceability_human_confirmation": {
        "exact-script-hash-bound",
        "sources-reviewer-and-time-recorded",
        "final-cut-review-mandatory",
        "correction-withdrawal-and-archive-route-recorded",
    },
}

SENSITIVE_PATTERNS = (
    ("phone_number", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("email_address", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
    ("identity_number", re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")),
    (
        "labelled_sensitive_identifier",
        re.compile(r"(?:姓名|病历号|住院号|保单号|身份证号|手机号|详细地址)\s*[:：]\s*\S+"),
    ),
    ("precise_case_date", re.compile(r"20\d{2}(?:[-/.年])\d{1,2}(?:[-/.月])\d{1,2}日?")),
    (
        "named_person_case_timeline",
        re.compile(
            r"(?:(?:这位|该|一位)?(?:患者|病人|客户|家属|投保人|被保险人))"
            r"(?:名叫|叫|是|为)?\s*[\u4e00-\u9fff]{2,4}"
            r"(?=在|于|曾|因|被|去|到|查|确|找|说|告诉)"
        ),
    ),
)

RISK_PHRASES = (
    "一定能赔",
    "肯定能赔",
    "百分之百能赔",
    "100%能赔",
    "保证理赔",
    "保证承保",
    "一定承保",
    "包赔",
    "这种治疗更好",
    "这种治疗最好",
    "治疗效果最好",
    "你应该选择这种治疗",
    "必须选择这种治疗",
    "报销全部癌症治疗费用",
    "覆盖全部癌症治疗费用",
    "赔付全部癌症治疗费用",
)
RISK_PATTERNS = (
    re.compile(r"(?:所有|任何|每一位|人人).{0,8}(?:患者|客户).{0,10}(?:都能|一定|肯定).{0,8}(?:获赔|治愈|延长寿命)"),
    re.compile(r"(?:这种|这个|该).{0,5}(?:疗法|治疗).{0,8}(?:显著|一定|肯定).{0,8}(?:延长|提高|治愈)"),
    re.compile(r"(?:延长|多活)\s*\d+(?:\.\d+)?\s*(?:年|个月)"),
    re.compile(
        r"(?:质子治疗|普通放疗|放疗|疗法|治疗).{0,12}"
        r"(?:优于|比.{0,8}(?:更好|更有效)|更有效|提高.{0,6}生存率|降低.{0,6}死亡率|治愈)"
    ),
    re.compile(
        r"(?:保险|保单|保障).{0,12}(?:报销|赔付|覆盖).{0,8}(?:全部|所有|任何)"
    ),
    re.compile(
        r"(?:全部|所有|任何).{0,8}(?:癌症|疾病|治疗|费用).{0,12}(?:报销|赔付|覆盖)"
    ),
)
ATTRIBUTED_QUOTE_PATTERN = re.compile(
    r"(?:(?:这位|该|一位)?(?:患者|病人|客户|家属|投保人|被保险人))"
    r".{0,12}(?:亲口|当时)?(?:对我)?(?:说|告诉|提到|表示|回忆)|亲口告诉我"
)
REAL_RECORD_VISUAL_PATTERN = re.compile(
    r"(?:真实|原始|客户|患者).{0,8}(?:病历|保单|理赔材料|医疗记录|检查报告|身份证|发票|处方)"
    r"|(?:病历|保单|理赔材料|医疗记录|检查报告|身份证|发票|处方).{0,8}(?:截图|照片|扫描|原件|影像|录屏)"
)


class CaseScriptError(RuntimeError):
    """A deterministic, fail-closed case-script validation error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        return research_adapter.load_json(path)
    except (OSError, json.JSONDecodeError, research_adapter.AdapterError) as error:
        raise CaseScriptError("invalid_or_missing_artifact", f"{label}: {error}") from error


def validate_instance(instance: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    try:
        research_adapter.validate_instance(instance, schema, label)
    except research_adapter.AdapterError as error:
        raise CaseScriptError(error.code, str(error)) from error


def _identity(artifact: dict[str, Any], keys: Iterable[str], label: str) -> str:
    for key in keys:
        value = artifact.get(key)
        if isinstance(value, str) and value:
            return value
    raise CaseScriptError("artifact_identity_missing", f"{label} has no stable identity")


def _artifact_ref(artifact: dict[str, Any], identity_keys: tuple[str, ...], label: str) -> dict[str, str]:
    return {
        "artifact_id": _identity(artifact, identity_keys, label),
        "schema_version": str(artifact.get("schema_version") or ""),
        "sha256": research_adapter.sha256_value(artifact),
    }


def _validate_artifact_ref(
    reference: dict[str, Any],
    artifact: dict[str, Any],
    *,
    identity_keys: tuple[str, ...],
    label: str,
) -> None:
    actual = _artifact_ref(artifact, identity_keys, label)
    if reference["artifact_id"] != actual["artifact_id"]:
        raise CaseScriptError("artifact_id_drift", f"{label} identity drifted")
    if reference["schema_version"] != actual["schema_version"]:
        raise CaseScriptError("artifact_version_drift", f"{label} schema version drifted")
    if reference["sha256"] != actual["sha256"]:
        raise CaseScriptError("artifact_hash_drift", f"{label} SHA-256 drifted")


def _index_unique(rows: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        identifier = str(row.get(key) or "")
        if not identifier:
            raise CaseScriptError("identifier_missing", f"{label} contains an empty {key}")
        if identifier in result:
            raise CaseScriptError("duplicate_identifier", f"{label} duplicates {identifier}")
        result[identifier] = row
    return result


def _story_texts(script: dict[str, Any]) -> list[str]:
    return [str(row["text"]) for row in script["story"].values()]


def _publishable_strings(script: dict[str, Any]) -> list[str]:
    values = [
        script["title"],
        script["single_question"],
        script["service_capability"]["statement"],
        script["service_capability"]["boundary"],
        *_story_texts(script),
    ]
    for segment in script["segments"]:
        values.extend([segment["purpose"], segment["spoken_text"]])
        values.extend(segment["subtitle_candidates"])
        values.extend(visual["description"] for visual in segment["visual_candidates"])
    values.extend(hook["text"] for hook in script["hook_candidates"])
    for slot in script["interview_slots"]:
        values.extend([slot["question"], slot["fallback_edit"]])
        values.extend(slot["selection_criteria"])
        if slot["state"] == "recorded":
            values.append(slot.get("quote_text", ""))
    return [str(value) for value in values if value]


def stable_body_payload(script: dict[str, Any]) -> dict[str, Any]:
    """Return the fixed subset reviewed before hooks are generated."""

    payload = {
        "scope_version": "case-video-stable-body.v1",
        "content_id": script["content_id"],
        "title": script["title"],
        "title_evidence_refs": script["title_evidence_refs"],
        "audience": script["audience"],
        "target_duration_seconds": script["target_duration_seconds"],
        "single_question": script["single_question"],
        "service_capability": script["service_capability"],
        "story": script["story"],
        "body_status": script["body_status"],
        "segments": script["segments"],
        "forbidden_expressions": script["forbidden_expressions"],
        "unknowns": script["unknowns"],
    }
    if "structure_route" in script:
        payload["structure_route"] = script["structure_route"]
    return payload


def hook_bundle_payload(script: dict[str, Any], body_sha256: str) -> dict[str, Any]:
    return {
        "scope_version": "case-video-hook-bundle.v1",
        "input_body_sha256": body_sha256,
        "selected_hook_id": script["selected_hook_id"],
        "hook_candidates": script["hook_candidates"],
    }


def review_subject_payload(script: dict[str, Any]) -> dict[str, Any]:
    body_sha256 = research_adapter.sha256_value(stable_body_payload(script))
    return {
        "scope_version": "case-video-review-subject.v1",
        "inputs": script["inputs"],
        "synthetic_only": script["synthetic_only"],
        "body_sha256": body_sha256,
        "hook_bundle": hook_bundle_payload(script, body_sha256),
        "interview_slots": script["interview_slots"],
        "human_review": script["human_review"],
        "experiment": script["experiment"],
    }


def _research_is_synthetic(research: dict[str, Any]) -> bool:
    constraints = {str(value) for value in research.get("scope", {}).get("constraints", [])}
    source_systems = {str(value) for value in research.get("provenance", {}).get("source_systems", [])}
    classifications = {
        str(row.get("provenance", {}).get("note_fields", {}).get("data_classification") or "")
        for row in research.get("sources", [])
    }
    signals = [
        "synthetic-only" in constraints,
        bool(source_systems) and source_systems == {"synthetic-fixture"},
        bool(classifications) and classifications == {"synthetic_only"},
    ]
    if any(signals) and not all(signals):
        raise CaseScriptError("data_classification_drift", "research synthetic classification signals disagree")
    return all(signals)


def _validate_sensitive_and_risky_language(script: dict[str, Any], fact_card: dict[str, Any]) -> None:
    texts = _publishable_strings(script)
    for text in texts:
        if ATTRIBUTED_QUOTE_PATTERN.search(text):
            raise CaseScriptError(
                "unbound_attributed_quote",
                "an attributed client or patient quote appears outside a verified interview artifact",
            )
        for code, pattern in SENSITIVE_PATTERNS:
            if pattern.search(text):
                raise CaseScriptError("sensitive_content_blocked", f"{code} found in publishable script text")
        for phrase in RISK_PHRASES:
            if phrase in text:
                raise CaseScriptError("medical_insurance_claim_blocked", f"unsupported claim found: {phrase}")
        if any(pattern.search(text) for pattern in RISK_PATTERNS):
            raise CaseScriptError("medical_insurance_claim_blocked", "unsupported medical or insurance generalization found")
    forbidden = list(script["forbidden_expressions"]) + list(fact_card["forbidden_claims"])
    for phrase in dict.fromkeys(forbidden):
        if any(phrase in text for text in texts):
            raise CaseScriptError("forbidden_expression_used", f"forbidden expression appears in script: {phrase}")
    if script["synthetic_only"] and any(
        phrase in text
        for text in texts
        for phrase in ("真实客户案例", "客户亲口告诉我", "我服务的客户")
    ):
        raise CaseScriptError("synthetic_represented_as_real", "synthetic fixture is represented as a real case")


def _validate_canonical_fact_card(fact_card: dict[str, Any]) -> None:
    """Require a locked, traceable fact revision for every non-synthetic case."""

    if fact_card.get("synthetic_only"):
        return
    required_top = ("revision_id", "canonical_status", "source_precedence", "correction_log")
    missing_top = [key for key in required_top if key not in fact_card]
    if missing_top:
        raise CaseScriptError(
            "canonical_fact_card_incomplete",
            f"real case fact-card lacks canonical revision fields: {missing_top}",
        )
    if fact_card["canonical_status"] != "locked_for_draft":
        raise CaseScriptError(
            "canonical_fact_card_not_locked",
            "real case fact-card must be locked_for_draft before Storycraft or script projection",
        )
    required_fact = (
        "fact_type",
        "sequence",
        "actor",
        "action",
        "status",
        "allowed_wording",
        "forbidden_paraphrases",
        "last_confirmed_at",
        "privacy_class",
    )
    sequences: list[int] = []
    for fact in fact_card.get("facts", []):
        missing = [key for key in required_fact if key not in fact]
        if missing:
            raise CaseScriptError(
                "canonical_fact_card_incomplete",
                f"{fact.get('fact_id', '<unknown>')} lacks canonical fields: {missing}",
            )
        if fact["status"] != "confirmed":
            raise CaseScriptError(
                "canonical_fact_card_contains_unconfirmed_fact",
                f"{fact['fact_id']} is not confirmed; move it to unknowns or exclude it from the draft fact set",
            )
        sequences.append(int(fact["sequence"]))
    if len(sequences) != len(set(sequences)):
        raise CaseScriptError("canonical_fact_sequence_conflict", "fact sequence values must be unique")


def _validate_segment_fact_routing(
    script: dict[str, Any],
    fact_card: dict[str, Any],
    route_card: dict[str, Any],
) -> None:
    """Bind publishable paragraphs to facts without sentence-level annotation."""

    facts = {str(row["fact_id"]): row for row in fact_card.get("facts", [])}
    real_case = not bool(script.get("synthetic_only"))
    narrative_order = route_card.get("narrative_order")
    if real_case and narrative_order not in {"chronological", "editorial_nonchronological"}:
        raise CaseScriptError(
            "narrative_order_missing",
            "real case route-card must choose chronological or editorial_nonchronological order",
        )
    if narrative_order == "editorial_nonchronological" and not str(
        route_card.get("nonchronological_reason") or ""
    ).strip():
        raise CaseScriptError(
            "nonchronological_reason_missing",
            "editorial nonchronological order requires a recorded reason",
        )

    previous_max_sequence = 0
    for segment in script.get("segments", []):
        fact_refs = [str(value) for value in segment.get("fact_refs") or []]
        if real_case and segment.get("role") != "cta" and not fact_refs:
            raise CaseScriptError(
                "segment_fact_refs_missing",
                f"{segment.get('segment_id', '<unknown>')} requires paragraph-level fact_refs",
            )
        if not fact_refs:
            continue
        missing = sorted(set(fact_refs).difference(facts))
        if missing:
            raise CaseScriptError(
                "segment_fact_ref_unknown",
                f"{segment.get('segment_id', '<unknown>')} references unknown facts: {missing}",
            )
        if narrative_order != "chronological":
            continue
        sequences = [facts[fact_id].get("sequence") for fact_id in fact_refs]
        if any(not isinstance(value, int) for value in sequences):
            raise CaseScriptError(
                "canonical_fact_sequence_missing",
                "chronological routing requires integer sequence values on every referenced fact",
            )
        current_min = min(sequences)
        current_max = max(sequences)
        if current_min < previous_max_sequence:
            raise CaseScriptError(
                "segment_fact_sequence_regression",
                f"{segment.get('segment_id', '<unknown>')} moves backward in the locked fact timeline",
            )
        previous_max_sequence = max(previous_max_sequence, current_max)


def _allowed_evidence_graph(research: dict[str, Any], policy: dict[str, Any]) -> dict[str, set[str]]:
    return {
        "claim": {row["claim_id"] for row in policy["selected_claims"]},
        "evidence": {row["evidence_id"] for row in policy["used_evidence"]},
        "source": {row["source_id"] for row in policy["used_sources"]},
        "unknown": {row["code"] for row in research["unknowns"] if row["severity"] == "warning"},
        "contradiction": {
            value
            for row in research["contradictions"]
            if row["resolution_status"] == "rejected"
            for value in (
                row["claim_id"],
                row["evidence_id"],
                ":".join((row["claim_id"], row["evidence_id"], row["source_id"])),
            )
        },
    }


def _ref_key(reference: dict[str, Any]) -> tuple[str, str]:
    return str(reference["ref_type"]), str(reference["ref_id"])


def _validate_evidence_refs(
    references: list[dict[str, Any]],
    allowed: dict[str, set[str]],
    label: str,
    *,
    assertive: bool = False,
) -> set[tuple[str, str]]:
    resolved: set[tuple[str, str]] = set()
    for reference in references:
        kind, identifier = _ref_key(reference)
        if identifier not in allowed.get(kind, set()):
            raise CaseScriptError(
                "unverified_case_evidence_ref",
                f"{label} references unresolved or unverified evidence {kind}:{identifier}",
            )
        resolved.add((kind, identifier))
    if assertive and not any(kind in {"claim", "evidence"} for kind, _ in resolved):
        raise CaseScriptError("assertive_text_evidence_missing", f"{label} needs a verified claim or evidence ref")
    return resolved


def _numeric_tokens(text: str) -> set[str]:
    arabic = re.findall(r"(?<![A-Za-z0-9_])\d+(?:\.\d+)?\s*(?:%|万|千|百|元|天|小时|分钟|年|月|日)?", text)
    chinese = re.findall(r"[零一二三四五六七八九十百千万两]+(?:元|万元|天|小时|分钟|年|月|日)", text)
    return {value.replace(" ", "") for value in [*arabic, *chinese]}


def _evidence_texts(research: dict[str, Any]) -> dict[tuple[str, str], str]:
    rows: dict[tuple[str, str], str] = {}
    for kind, collection, key in (
        ("claim", "claims", "claim_id"),
        ("evidence", "evidence", "evidence_id"),
    ):
        for row in research.get(collection, []):
            rows[(kind, str(row[key]))] = str(row.get("text") or row.get("statement") or row.get("excerpt") or "")
    return rows


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        raise CaseScriptError("human_voice_source_missing", f"human voice source is unavailable: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_human_voice_receipt(receipt: dict[str, Any], script: dict[str, Any]) -> None:
    if receipt["script_id"] != script["script_id"] or receipt["content_id"] != script["content_id"]:
        raise CaseScriptError("human_voice_receipt_identity_drift", "human voice receipt binds another script")
    if bool(receipt["synthetic_only"]) is not bool(script["synthetic_only"]):
        raise CaseScriptError("data_classification_drift", "human voice receipt classification drifted")
    _validate_artifact_ref(
        script["inputs"]["human_voice_receipt_ref"],
        receipt,
        identity_keys=("receipt_id",),
        label="human-voice-receipt",
    )
    source = receipt["source"]
    if source["skill_sha256"] != _file_sha256(HUMAN_VOICE_SKILL):
        raise CaseScriptError("human_voice_source_hash_drift", "human-voice-editor draft changed after rewrite")
    if source["rulebook_sha256"] != _file_sha256(HUMAN_VOICE_RULEBOOK):
        raise CaseScriptError("human_voice_source_hash_drift", "human-voice-editor rulebook changed after rewrite")
    body_sha256 = research_adapter.sha256_value(stable_body_payload(script))
    hook_sha256 = research_adapter.sha256_value(hook_bundle_payload(script, body_sha256))
    if receipt["rewritten_body_sha256"] != body_sha256:
        raise CaseScriptError("human_voice_body_hash_drift", "human voice receipt is stale for the current body")
    if receipt["diagnostics_after"]["issue_codes"]:
        raise CaseScriptError("human_voice_semantic_gate_blocked", "human voice receipt still contains blocked style issues")
    read_aloud = receipt["read_aloud"]
    read_payload = {
        "scope_version": "case-video-read-aloud.v1",
        "status": read_aloud["status"],
        "performed_by": read_aloud["performed_by"],
        "body_sha256": read_aloud["body_sha256"],
        "completed_at": read_aloud["completed_at"],
        "notes": read_aloud["notes"],
    }
    read_sha256 = research_adapter.sha256_value(read_payload)
    if read_aloud["body_sha256"] != body_sha256 or read_aloud["receipt_sha256"] != read_sha256:
        raise CaseScriptError("read_aloud_receipt_hash_drift", "read-aloud receipt is stale or malformed")
    confirmation = receipt["author_confirmation"]
    author_payload = {
        "scope_version": "case-video-author-voice-confirmation.v1",
        "status": confirmation["status"],
        "performed_by": confirmation["performed_by"],
        "body_sha256": confirmation["body_sha256"],
        "read_aloud_receipt_sha256": confirmation["read_aloud_receipt_sha256"],
        "confirmed_at": confirmation["confirmed_at"],
        "voice_match": confirmation["voice_match"],
        "facts_preserved": confirmation["facts_preserved"],
    }
    author_sha256 = research_adapter.sha256_value(author_payload)
    if (
        confirmation["body_sha256"] != body_sha256
        or confirmation["read_aloud_receipt_sha256"] != read_sha256
        or confirmation["receipt_sha256"] != author_sha256
    ):
        raise CaseScriptError("author_confirmation_hash_drift", "author voice confirmation is stale or malformed")
    expected_actor = "synthetic-fixture-author" if script["synthetic_only"] else "author"
    if read_aloud["performed_by"] != expected_actor or confirmation["performed_by"] != expected_actor:
        raise CaseScriptError("author_confirmation_actor_drift", "voice receipts use the wrong actor")
    hook_gate = receipt["hook_gate"]
    if hook_gate["input_body_sha256"] != body_sha256 or hook_gate["bundle_sha256"] != hook_sha256:
        raise CaseScriptError("hook_body_hash_drift", "hooks were not regenerated after author-confirmed body freeze")


def _validate_interview_receipts(
    receipts: list[dict[str, Any]], script: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    indexed = _index_unique(receipts, "slot_id", "deidentified interview receipts")
    slots = _index_unique(script["interview_slots"], "slot_id", "interview slots")
    recorded = {slot_id for slot_id, slot in slots.items() if slot["state"] == "recorded"}
    if set(indexed) != recorded:
        raise CaseScriptError(
            "interview_receipt_set_drift",
            "deidentified interview receipts must match recorded slots exactly",
        )
    for slot_id, receipt in indexed.items():
        slot = slots[slot_id]
        if receipt["script_id"] != script["script_id"] or receipt["content_id"] != script["content_id"]:
            raise CaseScriptError("interview_receipt_identity_drift", f"{slot_id} binds another script")
        if bool(receipt["synthetic_only"]) is not bool(script["synthetic_only"]):
            raise CaseScriptError("data_classification_drift", f"{slot_id} classification drifted")
        if receipt["quote_text"] != slot.get("quote_text"):
            raise CaseScriptError("interview_quote_hash_drift", f"{slot_id} quote text drifted")
        if receipt["quote_sha256"] != hashlib.sha256(receipt["quote_text"].encode("utf-8")).hexdigest():
            raise CaseScriptError("interview_quote_hash_drift", f"{slot_id} quote hash drifted")
        if receipt["recording_artifact_ref"] != slot.get("recording_artifact_ref"):
            raise CaseScriptError("interview_recording_hash_drift", f"{slot_id} recording ref drifted")
        if receipt["consent_artifact_ref"] != slot.get("consent_artifact_ref"):
            raise CaseScriptError("interview_consent_hash_drift", f"{slot_id} consent ref drifted")
        if receipt["consent"]["scope_sha256"] != research_adapter.sha256_value(receipt["consent"]["scope"]):
            raise CaseScriptError("interview_consent_hash_drift", f"{slot_id} consent scope hash drifted")
        reviewer = receipt["human_verification"]["reviewer"]
        expected_reviewer = "synthetic-fixture-reviewer" if script["synthetic_only"] else "local-reviewer-"
        if script["synthetic_only"] and reviewer != expected_reviewer:
            raise CaseScriptError("interview_review_owner_drift", f"{slot_id} uses the wrong synthetic reviewer")
        if not script["synthetic_only"] and not reviewer.startswith(expected_reviewer):
            raise CaseScriptError("interview_review_owner_drift", f"{slot_id} lacks a local human reviewer")
        for code, pattern in SENSITIVE_PATTERNS:
            if pattern.search(receipt["quote_text"]):
                raise CaseScriptError("sensitive_content_blocked", f"{slot_id} deidentified quote contains {code}")
        if any(phrase in receipt["quote_text"] for phrase in RISK_PHRASES) or any(
            pattern.search(receipt["quote_text"]) for pattern in RISK_PATTERNS
        ):
            raise CaseScriptError("medical_insurance_claim_blocked", f"{slot_id} quote contains a risky claim")
    return indexed



def _validate_review_receipt(
    receipt: dict[str, Any],
    script: dict[str, Any],
    research: dict[str, Any],
    content_item: dict[str, Any],
    fact_card: dict[str, Any],
    route_card: dict[str, Any],
    voice_receipt: dict[str, Any],
    interview_receipts: list[dict[str, Any]],
) -> None:
    if script["synthetic_only"]:
        if receipt.get("review_mode") != "synthetic-fixture-review" or receipt.get("reviewer") != "synthetic-fixture-reviewer":
            raise CaseScriptError("review_issuer_untrusted", "synthetic case uses an untrusted reviewer")
    elif (
        receipt.get("review_mode") != "human-local-high-stakes-review"
        or not str(receipt.get("reviewer") or "").startswith("local-reviewer-")
        or not receipt.get("reviewer_artifact_ref")
    ):
        raise CaseScriptError("review_issuer_untrusted", "real case lacks a local high-stakes review artifact")
    if receipt["script_id"] != script["script_id"] or receipt["content_id"] != script["content_id"]:
        raise CaseScriptError("review_receipt_hash_drift", "review receipt binds another script or content item")
    if receipt["synthetic_only"] is not script["synthetic_only"]:
        raise CaseScriptError("data_classification_drift", "review receipt classification drifted")
    expected_inputs = {
        "case_video_script": _artifact_ref(script, ("script_id",), "case-video-script"),
        "research_output": _artifact_ref(research, ("research_id",), "research-output"),
        "content_item": _artifact_ref(content_item, ("content_id",), "content-item"),
        "fact_card": _artifact_ref(fact_card, ("fact_card_id",), "fact-card"),
        "route_card": _artifact_ref(route_card, ("route_card_id",), "route-card"),
        "human_voice_receipt": _artifact_ref(voice_receipt, ("receipt_id",), "human-voice-receipt"),
        "interview_receipts": [
            _artifact_ref(row, ("receipt_id",), "deidentified-interview-receipt")
            for row in sorted(interview_receipts, key=lambda item: item["slot_id"])
        ],
    }
    if receipt["inputs"] != expected_inputs:
        raise CaseScriptError("review_receipt_hash_drift", "review receipt input refs drifted")
    subject_sha256 = research_adapter.sha256_value(review_subject_payload(script))
    if receipt["subject_sha256"] != subject_sha256:
        raise CaseScriptError("review_subject_hash_drift", "review receipt no longer matches reviewed prose and refs")
    if set(receipt["required_reviews"]) != REQUIRED_REVIEWS:
        raise CaseScriptError("review_receipt_incomplete", "review receipt omits a mandatory review")
    if set(script["human_review"]["required_reviews"]) != REQUIRED_REVIEWS:
        raise CaseScriptError("review_receipt_incomplete", "case script omits a mandatory review")
    if any(row["status"] != "pass" for row in receipt["gates"].values()):
        raise CaseScriptError("review_receipt_incomplete", "all review receipt gates must pass")
    compliance_gates = receipt["compliance_gates"]
    if set(compliance_gates) != set(COMPLIANCE_GATE_CHECKS):
        raise CaseScriptError("compliance_review_incomplete", "compliance review omits a mandatory gate")
    for gate_id, expected_checks in COMPLIANCE_GATE_CHECKS.items():
        gate = compliance_gates[gate_id]
        if gate["status"] != "pass" or set(gate["reviewed_check_ids"]) != expected_checks:
            raise CaseScriptError(
                "compliance_review_incomplete",
                f"{gate_id} does not cover the exact mandatory compliance checks",
            )
    context = receipt["compliance_context"]
    if not context["final_cut_review_required"]:
        raise CaseScriptError("compliance_review_incomplete", "final-cut compliance review must remain mandatory")
    if script["synthetic_only"]:
        if context["content_classification"] != "synthetic-no-distribution":
            raise CaseScriptError("compliance_context_drift", "synthetic fixture must not claim a live distribution class")
        if context["distribution_scope"] != "synthetic-no-distribution":
            raise CaseScriptError("compliance_context_drift", "synthetic fixture must not claim a live audience scope")
        expected_statuses = {
            context["institutional_review_status"],
            context["publishing_account_status"],
            context["customer_publication_consent_status"],
        }
        if expected_statuses != {"not-required-synthetic"}:
            raise CaseScriptError("compliance_context_drift", "synthetic fixture uses a live approval status")
    else:
        if context["content_classification"] == "synthetic-no-distribution":
            raise CaseScriptError("compliance_context_drift", "real case cannot use the synthetic content class")
        if context["distribution_scope"] == "synthetic-no-distribution":
            raise CaseScriptError("compliance_context_drift", "real case cannot use the synthetic distribution scope")
        if context["institutional_review_status"] == "blocked" or context["publishing_account_status"] == "blocked":
            raise CaseScriptError("compliance_route_blocked", "institution or account route is blocked")
        if context["customer_publication_consent_status"] == "blocked":
            raise CaseScriptError("compliance_route_blocked", "customer publication consent is blocked")
    current_official = {
        row["source_id"]
        for row in context["rules_snapshot"]["sources"]
        if row["authority"] == "official-rule" and row["effective_status"] == "current"
    }
    if not script["synthetic_only"] and not current_official:
        raise CaseScriptError("compliance_current_rule_missing", "real-case review lacks a current official rule source")


def validate_case_script_semantics(
    script: dict[str, Any],
    research: dict[str, Any],
    content_item: dict[str, Any],
    fact_card: dict[str, Any],
    route_card: dict[str, Any],
    voice_receipt: dict[str, Any],
    interview_receipts: list[dict[str, Any]],
    review_receipt: dict[str, Any],
) -> dict[str, Any]:
    if script.get("pre_voice"):
        raise CaseScriptError("pre_voice_not_production_ready", "Writing a draft requires no recording; production requires completed voice and evidence review")
    try:
        policy = research_adapter.validate_research_semantics(research)
    except research_adapter.AdapterError as error:
        raise CaseScriptError(error.code, str(error)) from error

    refs = script["inputs"]
    for key, artifact, identity_keys, label in (
        ("research_output_ref", research, ("research_id",), "research-output"),
        ("content_item_ref", content_item, ("content_id",), "content-item"),
        ("fact_card_ref", fact_card, ("fact_card_id",), "fact-card"),
        ("route_card_ref", route_card, ("route_card_id",), "route-card"),
        ("human_voice_receipt_ref", voice_receipt, ("receipt_id",), "human-voice-receipt"),
    ):
        _validate_artifact_ref(refs[key], artifact, identity_keys=identity_keys, label=label)

    linked_ids = {
        script["content_id"],
        str(content_item.get("content_id") or ""),
        str(fact_card.get("content_id") or ""),
        str(route_card.get("content_id") or ""),
    }
    if len(linked_ids) != 1:
        raise CaseScriptError("content_id_drift", f"case artifacts disagree on content_id: {sorted(linked_ids)}")
    if content_item.get("publication", {}).get("boundary") != "manual-only":
        raise CaseScriptError("publication_boundary_drift", "content-item publication boundary must be manual-only")

    classifications = {
        bool(script["synthetic_only"]),
        bool(fact_card["synthetic_only"]),
        bool(route_card["synthetic_only"]),
        _research_is_synthetic(research),
    }
    if len(classifications) != 1:
        raise CaseScriptError("data_classification_drift", "research, fact, route, and script classification disagree")

    content_gate_warnings: list[str] = []
    for name, gate in content_item.get("gates", {}).items():
        status = str(gate.get("status") or "")
        if status == "blocked":
            raise CaseScriptError("upstream_content_gate_blocked", f"content-item gate is blocked: {name}")
        if status != "pass":
            content_gate_warnings.append(f"content-item {name} gate is {status or 'missing'}")
    failed_fact_gates = {name: status for name, status in fact_card["gates"].items() if status != "pass"}
    if failed_fact_gates:
        raise CaseScriptError("upstream_fact_gate_blocked", f"fact-card gates are not pass: {failed_fact_gates}")
    _validate_canonical_fact_card(fact_card)
    _validate_segment_fact_routing(script, fact_card, route_card)

    if route_card["single_question"] != script["single_question"]:
        raise CaseScriptError("route_question_drift", "route card and case script must share one question")
    if route_card["one_variable"] != script["experiment"]["variable_to_change"]:
        raise CaseScriptError("experiment_variable_drift", "route and case script disagree on the one variable")

    allowed = _allowed_evidence_graph(research, policy)
    body_refs: set[tuple[str, str]] = set()
    body_refs |= _validate_evidence_refs(script["title_evidence_refs"], allowed, "title", assertive=True)
    body_refs |= _validate_evidence_refs(
        script["service_capability"]["action_evidence_refs"], allowed, "service capability", assertive=True
    )
    for name, row in script["story"].items():
        body_refs |= _validate_evidence_refs(row["evidence_refs"], allowed, f"story.{name}", assertive=True)
    for fact in fact_card["facts"]:
        _validate_evidence_refs(fact["evidence_refs"], allowed, f"fact-card.{fact['fact_id']}", assertive=True)

    segments = _index_unique(script["segments"], "segment_id", "segments")
    hooks = _index_unique(script["hook_candidates"], "hook_id", "hook_candidates")
    _index_unique(script["interview_slots"], "slot_id", "interview_slots")
    verified_interviews = _validate_interview_receipts(interview_receipts, script)
    if script["selected_hook_id"] not in hooks:
        raise CaseScriptError("selected_hook_missing", "selected_hook_id must name one candidate")

    for segment in script["segments"]:
        body_refs |= _validate_evidence_refs(segment["evidence_refs"], allowed, segment["segment_id"], assertive=True)
        for visual in segment["visual_candidates"]:
            assertive = visual["evidence_role"] in {"data", "quotation"}
            _validate_evidence_refs(visual["evidence_refs"], allowed, visual["visual_id"], assertive=assertive)
            if script["synthetic_only"] and visual["rights_status"] != "synthetic":
                raise CaseScriptError("visual_rights_evidence_missing", "synthetic fixtures require synthetic visual rights")
            if REAL_RECORD_VISUAL_PATTERN.search(str(visual["description"])):
                raise CaseScriptError(
                    "visual_real_record_disguised",
                    "a real record or screenshot cannot be represented as a synthetic visual candidate",
                )
            if visual["rights_status"] == "reviewed-cleared":
                raise CaseScriptError(
                    "visual_rights_artifact_unresolved",
                    "reviewed-cleared visuals require the existing rights owner artifact; this sidecar cannot self-assert clearance",
                )
            if visual["rights_status"] in {"unknown", "blocked"}:
                raise CaseScriptError("visual_rights_evidence_missing", f"{visual['visual_id']} lacks usable rights")

    evidence_text = _evidence_texts(research)
    for hook in script["hook_candidates"]:
        hook_refs = _validate_evidence_refs(hook["evidence_refs"], allowed, hook["hook_id"], assertive=True)
        if hook["risk_status"] != "pass":
            raise CaseScriptError("hook_risk_blocked", f"{hook['hook_id']} is blocked")
        if not hook_refs.issubset(body_refs):
            raise CaseScriptError("hook_adds_claim", f"{hook['hook_id']} adds evidence outside the stable body")
        allowed_numbers = _numeric_tokens(" ".join(evidence_text.get(key, "") for key in hook_refs))
        new_numbers = _numeric_tokens(hook["text"]) - allowed_numbers
        if new_numbers:
            raise CaseScriptError("hook_adds_number", f"{hook['hook_id']} adds unsupported numbers: {sorted(new_numbers)}")

    for slot in script["interview_slots"]:
        if slot["story_segment_ref"] not in segments:
            raise CaseScriptError("interview_segment_missing", f"{slot['slot_id']} references a missing segment")
        _validate_evidence_refs(slot["evidence_refs"], allowed, slot["slot_id"], assertive=True)
        if slot["state"] == "recorded":
            if slot["slot_id"] not in verified_interviews:
                raise CaseScriptError("interview_artifact_unresolved", "recorded interview lacks a deidentified receipt")
        if slot.get("quote_text") or slot.get("recording_artifact_ref") or slot.get("consent_artifact_ref"):
            if slot["state"] != "recorded":
                raise CaseScriptError("unrecorded_interview_has_quote", f"{slot['slot_id']} has media before authorization")

    body_sha256 = research_adapter.sha256_value(stable_body_payload(script))
    hook_sha256 = research_adapter.sha256_value(hook_bundle_payload(script, body_sha256))
    subject_sha256 = research_adapter.sha256_value(review_subject_payload(script))
    _validate_human_voice_receipt(voice_receipt, script)
    receipts = sorted(script["skill_stage_receipts"], key=lambda row: row["sequence"])
    if [(row["skill_id"], row["role"]) for row in receipts] != REQUIRED_SKILL_SEQUENCE:
        raise CaseScriptError("skill_route_drift", "skill receipts do not follow the registered route")
    expected_hash_pairs = [
        (refs["research_output_ref"]["sha256"], refs["fact_card_ref"]["sha256"]),
        (refs["fact_card_ref"]["sha256"], voice_receipt["input_body_sha256"]),
        (voice_receipt["input_body_sha256"], voice_receipt["dbs_content_diagnosis_sha256"]),
        (voice_receipt["dbs_content_diagnosis_sha256"], voice_receipt["dbs_ai_check_diagnosis_sha256"]),
        (voice_receipt["dbs_ai_check_diagnosis_sha256"], body_sha256),
        (body_sha256, voice_receipt["read_aloud"]["receipt_sha256"]),
        (voice_receipt["read_aloud"]["receipt_sha256"], voice_receipt["author_confirmation"]["receipt_sha256"]),
        (voice_receipt["author_confirmation"]["receipt_sha256"], hook_sha256),
    ]
    for receipt, expected in zip(receipts, expected_hash_pairs, strict=True):
        if (receipt["input_sha256"], receipt["output_sha256"]) != expected:
            raise CaseScriptError("skill_hash_chain_drift", f"{receipt['skill_id']} is not bound to its reviewed subject")
        if receipt["status"] != "passed":
            raise CaseScriptError("skill_stage_not_passed", f"{receipt['skill_id']} did not pass")
        if bool(receipt["synthetic_stub"]) is not bool(script["synthetic_only"]):
            raise CaseScriptError(
                "skill_receipt_classification_drift",
                f"{receipt['skill_id']} synthetic_stub disagrees with the case classification",
            )

    _validate_sensitive_and_risky_language(script, fact_card)
    _validate_review_receipt(
        review_receipt,
        script,
        research,
        content_item,
        fact_card,
        route_card,
        voice_receipt,
        interview_receipts,
    )
    return {
        "policy": policy,
        "allowed_evidence": allowed,
        "content_gate_warnings": content_gate_warnings,
        "body_sha256": body_sha256,
        "hook_bundle_sha256": hook_sha256,
        "review_subject_sha256": subject_sha256,
        "forbidden_expressions": list(
            dict.fromkeys(script["forbidden_expressions"] + fact_card["forbidden_claims"])
        ),
    }


def _evidence_ref(reference: dict[str, Any]) -> dict[str, str]:
    return {"ref_type": reference["ref_type"], "ref_id": reference["ref_id"]}


def _merged_unknowns(script: dict[str, Any], research: dict[str, Any]) -> list[dict[str, str]]:
    rows = [
        {"unknown_id": row["unknown_id"], "text": row["text"], "handling": row["handling"]}
        for row in script["unknowns"]
    ]
    seen = {row["text"] for row in rows}
    warnings = [
        *research.get("completeness", {}).get("warnings", []),
        *research.get("guarded_final_answer", {}).get("warnings", []),
    ]
    warnings.extend(row["text"] for row in research.get("unknowns", []) if row.get("severity") == "warning")
    for warning in warnings:
        text = str(warning)
        if text and text not in seen:
            rows.append(
                {
                    "unknown_id": "upstream-warning-" + research_adapter.stable_suffix(text, length=12),
                    "text": text,
                    "handling": "requires-review",
                }
            )
            seen.add(text)
    return rows


def build_video_brief(
    script: dict[str, Any],
    research: dict[str, Any],
    voice_receipt: dict[str, Any],
    interview_receipts: list[dict[str, Any]],
    review_receipt: dict[str, Any],
    semantics: dict[str, Any],
    *,
    manifest_name: str,
    research_schema_id: str,
) -> dict[str, Any]:
    selected_hook = next(row for row in script["hook_candidates"] if row["hook_id"] == script["selected_hook_id"])
    units = [
        {
            "purpose": "selected-hook",
            "role": "hook",
            "spoken_text": selected_hook["text"],
            "evidence_refs": selected_hook["evidence_refs"],
            "subtitle_candidates": [selected_hook["text"]],
            "visual_candidates": [],
        },
        *script["segments"],
    ]
    units.extend(
        {
            "purpose": "deidentified-interview-quote",
            "role": "quotation",
            "spoken_text": slot["quote_text"],
            "evidence_refs": slot["evidence_refs"],
            "subtitle_candidates": [slot["quote_text"]],
            "visual_candidates": [],
        }
        for slot in script["interview_slots"]
        if slot["state"] == "recorded"
    )
    chapter_duration = max(5, script["target_duration_seconds"] // len(units))
    chapters: list[dict[str, Any]] = []
    scenes: list[dict[str, Any]] = []
    visual_counter = 0
    for index, unit in enumerate(units, start=1):
        chapter_id = f"chapter-{index:02d}"
        evidence_refs = [_evidence_ref(row) for row in unit["evidence_refs"]]
        chapters.append(
            {
                "chapter_id": chapter_id,
                "title": unit["purpose"],
                "purpose": unit["role"],
                "target_duration_seconds": chapter_duration,
                "narration_draft": unit["spoken_text"],
                "evidence_refs": evidence_refs,
            }
        )
        visual_leads = []
        for visual in unit["visual_candidates"]:
            visual_counter += 1
            visual_leads.append(
                {
                    "lead_id": f"visual-lead-{visual_counter:02d}",
                    "description": visual["description"],
                    "status": "candidate",
                    "upstream_status": "candidate",
                    "evidence_role": visual["evidence_role"],
                    "evidence_refs": [_evidence_ref(row) for row in visual["evidence_refs"]],
                    "rights_note": visual["rights_note"],
                    "boundary_note": "候选视觉，不代表镜头已经拍摄、素材已经存在或事实已经发生。",
                }
            )
        scenes.append(
            {
                "scene_id": f"scene-{index:02d}",
                "chapter_ref": chapter_id,
                "purpose": unit["purpose"],
                "narration_draft": unit["spoken_text"],
                "evidence_refs": evidence_refs,
                "visual_leads": visual_leads,
                "subtitle_candidates": unit["subtitle_candidates"],
            }
        )

    upstream_files = list(research["provenance"]["input_files"])
    for label, reference in (
        ("case-video-script", _artifact_ref(script, ("script_id",), "case-video-script")),
        ("content-item", script["inputs"]["content_item_ref"]),
        ("fact-card", script["inputs"]["fact_card_ref"]),
        ("route-card", script["inputs"]["route_card_ref"]),
        ("human-voice-receipt", _artifact_ref(voice_receipt, ("receipt_id",), "human-voice-receipt")),
        ("case-review", _artifact_ref(review_receipt, ("review_id",), "case-review")),
    ):
        upstream_files.append(
            {"path": f"artifact://{label}/{reference['artifact_id']}", "sha256": reference["sha256"], "status": "present"}
        )
    for receipt in sorted(interview_receipts, key=lambda row: row["slot_id"]):
        reference = _artifact_ref(receipt, ("receipt_id",), "deidentified-interview-receipt")
        upstream_files.append(
            {
                "path": f"artifact://deidentified-interview-receipt/{reference['artifact_id']}",
                "sha256": reference["sha256"],
                "status": "present",
            }
        )

    research_warnings = [
        *research.get("completeness", {}).get("warnings", []),
        *research.get("guarded_final_answer", {}).get("warnings", []),
        *semantics["content_gate_warnings"],
    ]
    reasons = [
        "human voice rewrite、逐字朗读和作者口吻确认均已绑定本版正文；正文变化会同时使声音回执和 Hook 失效。",
        "外置 case-video-review-receipt 已绑定本版正文、证据、钩子、视觉和采访槽位；发布仍须人工决定。",
        "客户采访未录制或未由既有授权 owner 验证时，只执行 fallback，不生成客户回答。",
        "所有视觉只保持 candidate，不代表真实素材或真实事件。",
        *[str(value) for value in research_warnings],
    ]
    return {
        "schema_version": "content-video-brief.v1",
        "brief_id": f"vbrief-{research_adapter.stable_suffix(script['content_id'], script['script_id'], ADAPTER_VERSION, length=20)}",
        "content_id": script["content_id"],
        "mode": "draft_only",
        "title": script["title"],
        "thesis": script["story"]["main_judgment"]["text"],
        "audience": script["audience"],
        "target_duration_seconds": script["target_duration_seconds"],
        "chapters": chapters,
        "scenes": scenes,
        "forbidden_expressions": list(
            dict.fromkeys(
                semantics["forbidden_expressions"]
                + [
                    research["guarded_final_answer"]["guardrail"],
                    "不得把 synthetic_only fixture 表述为真实客户案例。",
                    "不得把候选视觉写成已经拍到、已经取得或真实发生的镜头。",
                ]
            )
        ),
        "unknowns": _merged_unknowns(script, research),
        "review_gate": {
            "status": "required",
            "reasons": list(dict.fromkeys(reasons)),
            "required_reviews": sorted(REQUIRED_REVIEWS),
            "publication_boundary": "manual-only",
        },
        "provenance": {
            "research_id": research["research_id"],
            "input_schema_id": research_schema_id,
            "input_sha256": research_adapter.sha256_value(research),
            "adapter": "research-output-to-content",
            "adapter_version": f"{research_adapter.ADAPTER_VERSION}+case-script.{ADAPTER_VERSION}",
            "generated_at": script["provenance"]["generated_at"],
            "manifest_ref": manifest_name,
            "offline_only": True,
            "external_api_called": False,
            "model_memory_used_as_evidence": False,
            "upstream_input_files": upstream_files,
        },
    }


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _handoff_projection(manifest: dict[str, Any]) -> dict[str, Any]:
    """Bind every handoff field except the digest itself, avoiding a hash cycle."""

    return {
        key: value
        for key, value in manifest.items()
        if key != "brief_projection_sha256"
    }


def adapt_case_video_script(
    *,
    script_path: Path,
    research_path: Path,
    content_item_path: Path,
    fact_card_path: Path,
    route_card_path: Path,
    voice_receipt_path: Path,
    interview_receipt_paths: list[Path] | None,
    review_receipt_path: Path,
    output_dir: Path,
    script_schema_path: Path = DEFAULT_SCRIPT_SCHEMA,
    voice_schema_path: Path = DEFAULT_VOICE_SCHEMA,
    interview_schema_path: Path = DEFAULT_INTERVIEW_SCHEMA,
    review_schema_path: Path = DEFAULT_REVIEW_SCHEMA,
    fact_schema_path: Path = DEFAULT_FACT_SCHEMA,
    route_schema_path: Path = DEFAULT_ROUTE_SCHEMA,
    handoff_schema_path: Path = DEFAULT_HANDOFF_SCHEMA,
    research_schema_path: Path = DEFAULT_RESEARCH_SCHEMA,
    content_schema_path: Path = DEFAULT_CONTENT_SCHEMA,
    video_schema_path: Path = DEFAULT_VIDEO_SCHEMA,
) -> dict[str, Any]:
    script = load_json(script_path, "case-video-script")
    research = load_json(research_path, "research-output")
    content_item = load_json(content_item_path, "content-item")
    fact_card = load_json(fact_card_path, "fact-card")
    route_card = load_json(route_card_path, "route-card")
    voice_receipt = load_json(voice_receipt_path, "case-video-human-voice-receipt")
    interview_receipts = [
        load_json(path, f"deidentified interview receipt {path.name}")
        for path in (interview_receipt_paths or [])
    ]
    review_receipt = load_json(review_receipt_path, "case-video-review-receipt")
    schemas = {
        "script": load_json(script_schema_path, "case-video-script schema"),
        "voice": load_json(voice_schema_path, "case-video-human-voice schema"),
        "interview": load_json(interview_schema_path, "deidentified interview schema"),
        "review": load_json(review_schema_path, "case-video-review schema"),
        "fact": load_json(fact_schema_path, "content-fact-card schema"),
        "route": load_json(route_schema_path, "content-route-card schema"),
        "handoff": load_json(handoff_schema_path, "case-video-handoff schema"),
        "research": load_json(research_schema_path, "research-output schema"),
        "content": load_json(content_schema_path, "content-item schema"),
        "video": load_json(video_schema_path, "content-video-brief schema"),
    }
    for label, value, schema in (
        ("case-video-script.v1", script, schemas["script"]),
        ("research-output.v1", research, schemas["research"]),
        ("content-item", content_item, schemas["content"]),
        ("content-fact-card.v0", fact_card, schemas["fact"]),
        ("content-route-card.v0", route_card, schemas["route"]),
        ("case-video-human-voice-receipt.v1", voice_receipt, schemas["voice"]),
        ("case-video-review-receipt.v1", review_receipt, schemas["review"]),
    ):
        validate_instance(value, schema, label)
    for receipt in interview_receipts:
        validate_instance(receipt, schemas["interview"], "case-video-deidentified-interview-receipt.v1")

    semantics = validate_case_script_semantics(
        script,
        research,
        content_item,
        fact_card,
        route_card,
        voice_receipt,
        interview_receipts,
        review_receipt,
    )
    manifest_name = f"{script['script_id']}.manifest.json"
    research_schema_id = schemas["research"].get("$id")
    if not isinstance(research_schema_id, str) or not research_schema_id:
        raise CaseScriptError("research_schema_id_missing", "research-output schema needs a non-empty $id")
    brief = build_video_brief(
        script,
        research,
        voice_receipt,
        interview_receipts,
        review_receipt,
        semantics,
        manifest_name=manifest_name,
        research_schema_id=research_schema_id,
    )
    validate_instance(brief, schemas["video"], "content-video-brief.v1")

    brief_name = f"{script['script_id']}.content-video-brief.json"
    brief_sha256 = research_adapter.sha256_value(brief)
    selected_hook = next(
        row for row in script["hook_candidates"] if row["hook_id"] == script["selected_hook_id"]
    )
    inputs = {
        "case_video_script": _artifact_ref(script, ("script_id",), "case-video-script"),
        "research_output": script["inputs"]["research_output_ref"],
        "content_item": script["inputs"]["content_item_ref"],
        "fact_card": script["inputs"]["fact_card_ref"],
        "route_card": script["inputs"]["route_card_ref"],
        "review_receipt": _artifact_ref(review_receipt, ("review_id",), "case-video-review"),
    }
    boundaries = {
        "draft_only": True,
        "manual_only": True,
        "candidate_visuals_only": True,
        "external_api_called": False,
        "would_publish": False,
    }
    manifest = {
        "schema_version": "case-video-script-handoff.v1",
        "status": "generated_draft_only",
        "adapter": "case-video-script-sidecar",
        "adapter_version": ADAPTER_VERSION,
        "handoff_id": "case-handoff-" + research_adapter.stable_suffix(script["script_id"], brief_sha256, length=20),
        "script_id": script["script_id"],
        "content_id": script["content_id"],
        "brief_id": brief["brief_id"],
        "synthetic_only": script["synthetic_only"],
        "inputs": inputs,
        "output": {
            "path": brief_name,
            "brief_id": brief["brief_id"],
            "schema_version": brief["schema_version"],
            "sha256": brief_sha256,
        },
        "brief_projection_sha256": "0" * 64,
        "selected_hook_id": script["selected_hook_id"],
        "selected_hook_binding": {
            "hook_id": selected_hook["hook_id"],
            "text_sha256": research_adapter.sha256_value(selected_hook["text"]),
            "evidence_refs_sha256": research_adapter.sha256_value(selected_hook["evidence_refs"]),
        },
        "interview_slots": [
            {
                "slot_id": row["slot_id"],
                "state": row["state"],
                "story_segment_ref": row["story_segment_ref"],
                "fallback_edit": row["fallback_edit"],
            }
            for row in script["interview_slots"]
        ],
        "experiment": script["experiment"],
        "boundaries": boundaries,
    }
    manifest["brief_projection_sha256"] = research_adapter.sha256_value(_handoff_projection(manifest))
    validate_instance(manifest, schemas["handoff"], "case-video-script-handoff.v1")

    _write_text(output_dir / brief_name, _json_text(brief))
    _write_text(output_dir / manifest_name, _json_text(manifest))
    return {
        "status": "generated_draft_only",
        "script_id": script["script_id"],
        "content_id": script["content_id"],
        "brief": str((output_dir / brief_name).resolve()),
        "manifest": str((output_dir / manifest_name).resolve()),
        "brief_sha256": brief_sha256,
        "manifest_sha256": research_adapter.sha256_value(manifest),
        "body_sha256": semantics["body_sha256"],
        "hook_bundle_sha256": semantics["hook_bundle_sha256"],
        "review_subject_sha256": semantics["review_subject_sha256"],
    }


def contract_preflight(
    script_schema_path: Path = DEFAULT_SCRIPT_SCHEMA,
    voice_schema_path: Path = DEFAULT_VOICE_SCHEMA,
    interview_schema_path: Path = DEFAULT_INTERVIEW_SCHEMA,
    review_schema_path: Path = DEFAULT_REVIEW_SCHEMA,
    fact_schema_path: Path = DEFAULT_FACT_SCHEMA,
    route_schema_path: Path = DEFAULT_ROUTE_SCHEMA,
    handoff_schema_path: Path = DEFAULT_HANDOFF_SCHEMA,
    research_schema_path: Path = DEFAULT_RESEARCH_SCHEMA,
    content_schema_path: Path = DEFAULT_CONTENT_SCHEMA,
    video_schema_path: Path = DEFAULT_VIDEO_SCHEMA,
) -> dict[str, Any]:
    schema_paths = {
        "case_video_script": script_schema_path,
        "case_video_human_voice": voice_schema_path,
        "case_video_deidentified_interview": interview_schema_path,
        "case_video_review": review_schema_path,
        "content_fact_card": fact_schema_path,
        "content_route_card": route_schema_path,
        "case_video_handoff": handoff_schema_path,
        "research_output": research_schema_path,
        "content_item": content_schema_path,
        "content_video_brief": video_schema_path,
    }
    schemas = {name: load_json(path, f"{name} schema") for name, path in schema_paths.items()}
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
    return {
        "status": "contract_ready",
        "adapter_version": ADAPTER_VERSION,
        "schemas": {
            name: {"id": schema.get("$id"), "sha256": research_adapter.sha256_value(schema)}
            for name, schema in schemas.items()
        },
        "boundaries": {
            "draft_only": True,
            "manual_only": True,
            "external_api_called": False,
            "owns_publication_state": False,
            "owns_video_state": False,
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-script", type=Path)
    parser.add_argument("--research-output", type=Path)
    parser.add_argument("--content-item", type=Path)
    parser.add_argument("--fact-card", type=Path)
    parser.add_argument("--route-card", type=Path)
    parser.add_argument("--human-voice-receipt", type=Path)
    parser.add_argument("--interview-receipt", type=Path, action="append", default=[])
    parser.add_argument("--review-receipt", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--case-script-schema", type=Path, default=DEFAULT_SCRIPT_SCHEMA)
    parser.add_argument("--human-voice-schema", type=Path, default=DEFAULT_VOICE_SCHEMA)
    parser.add_argument("--interview-schema", type=Path, default=DEFAULT_INTERVIEW_SCHEMA)
    parser.add_argument("--review-schema", type=Path, default=DEFAULT_REVIEW_SCHEMA)
    parser.add_argument("--fact-schema", type=Path, default=DEFAULT_FACT_SCHEMA)
    parser.add_argument("--route-schema", type=Path, default=DEFAULT_ROUTE_SCHEMA)
    parser.add_argument("--handoff-schema", type=Path, default=DEFAULT_HANDOFF_SCHEMA)
    parser.add_argument("--research-schema", type=Path, default=DEFAULT_RESEARCH_SCHEMA)
    parser.add_argument("--content-schema", type=Path, default=DEFAULT_CONTENT_SCHEMA)
    parser.add_argument("--video-schema", type=Path, default=DEFAULT_VIDEO_SCHEMA)
    parser.add_argument("--check-contract-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.check_contract_only:
            result = contract_preflight(
                args.case_script_schema,
                args.human_voice_schema,
                args.interview_schema,
                args.review_schema,
                args.fact_schema,
                args.route_schema,
                args.handoff_schema,
                args.research_schema,
                args.content_schema,
                args.video_schema,
            )
        else:
            required = {
                "--case-script": args.case_script,
                "--research-output": args.research_output,
                "--content-item": args.content_item,
                "--fact-card": args.fact_card,
                "--route-card": args.route_card,
                "--human-voice-receipt": args.human_voice_receipt,
                "--review-receipt": args.review_receipt,
                "--output-dir": args.output_dir,
            }
            missing = [name for name, value in required.items() if value is None]
            if missing:
                raise CaseScriptError("missing_arguments", f"missing required arguments: {', '.join(missing)}")
            result = adapt_case_video_script(
                script_path=args.case_script,
                research_path=args.research_output,
                content_item_path=args.content_item,
                fact_card_path=args.fact_card,
                route_card_path=args.route_card,
                voice_receipt_path=args.human_voice_receipt,
                interview_receipt_paths=args.interview_receipt,
                review_receipt_path=args.review_receipt,
                output_dir=args.output_dir,
                script_schema_path=args.case_script_schema,
                voice_schema_path=args.human_voice_schema,
                interview_schema_path=args.interview_schema,
                review_schema_path=args.review_schema,
                fact_schema_path=args.fact_schema,
                route_schema_path=args.route_schema,
                handoff_schema_path=args.handoff_schema,
                research_schema_path=args.research_schema,
                content_schema_path=args.content_schema,
                video_schema_path=args.video_schema,
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except CaseScriptError as error:
        print(json.dumps({"status": error.code, "message": str(error)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
