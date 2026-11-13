"""Narrow reusable extraction of the synthetic PPT acceptance gate.

Purpose
-------
Decide whether an already prepared synthetic gate ``state`` (a plain dict) is
accepted or blocked, and replay the fixed list of ten synthetic negative cases.
The decision preserves the historical error codes, conditions and validation
order of ``scripts/run_visual_ppt_fresh_e2e.py``.

Verification boundaries
-----------------------
This candidate only decides accept/block for the supplied synthetic state. It
does not attest to, and must not be read as evidence about:

* fonts or font files -- ``state["font_checks"]["lucas_noto_sans"]`` is a
  legacy internal contract key kept for compatibility; it is a boolean in the
  prepared state and this module never inspects font files or font metadata;
* Office, an office suite, or any document format;
* a renderer or any rendering pipeline;
* external providers or live model gateways -- gateway receipts are values in
  the supplied state only, nothing is called or verified remotely;
* evidence provenance -- evidence refs are compared as strings inside the
  supplied state;
* real PPT output, or any real document of any kind.

Scope
-----
The full historical runner and its full test are not reconstructed here and
remain out of scope. The synthetic case list is bound explicitly in this module
(``NEGATIVE_CASES``); no historical path is discovered, read or written. The
private historical runner hash helper is replaced by the small standard-library
:func:`sha256_file`. Standard library only.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "E2EError",
    "NEGATIVE_CASES",
    "apply_mutation",
    "parse_time",
    "read_json",
    "run_negative_cases",
    "sha256_file",
    "validate_gate_state",
]


class E2EError(RuntimeError):
    """Stable fail-closed error for this bounded acceptance runner."""


def read_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    """Return the lowercase hex SHA-256 of ``path``.

    Small standard-library implementation (``hashlib``) that replaces the
    dependency on the private historical runner hash helper; no runner module is
    imported. Chunked reads keep it usable for larger files without loading the
    whole resource into memory.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def apply_mutation(payload: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    current: Any = payload
    for part in parts[:-1]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    leaf = parts[-1]
    if isinstance(current, list):
        current[int(leaf)] = value
    else:
        current[leaf] = value


# Fixed synthetic negative cases, bound explicitly to the ten original negative
# cases from the original synthetic suite.
# Ids, mutation path/value and expected error codes are kept verbatim; there is
# no historical path discovery or file read for cases.
NEGATIVE_CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "font-missing",
        "mutation": {"path": "font_checks.lucas_noto_sans", "value": False},
        "expected": "required_font_missing",
    },
    {
        "id": "resource-missing",
        "mutation": {"path": "resources.0.exists", "value": False},
        "expected": "required_resource_missing",
    },
    {
        "id": "checksum-drift",
        "mutation": {
            "path": "resources.0.sha256",
            "value": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        },
        "expected": "resource_checksum_drift",
    },
    {
        "id": "layout-overflow",
        "mutation": {"path": "layout.overflow", "value": True},
        "expected": "layout_overflow",
    },
    {
        "id": "evidence-missing",
        "mutation": {"path": "evidence_refs.0", "value": "claim_missing"},
        "expected": "evidence_ref_unresolved",
    },
    {
        "id": "privacy-field",
        "mutation": {"path": "privacy.contains_personal_data", "value": True},
        "expected": "privacy_data_forbidden",
    },
    {
        "id": "product-suitability",
        "mutation": {
            "path": "texts.0",
            "value": "这款产品最适合你，建议马上购买。",
        },
        "expected": "product_recommendation_forbidden",
    },
    {
        "id": "provider-unavailable",
        "mutation": {"path": "gateway.text.status", "value": "blocked"},
        "expected": "provider_candidate_unavailable",
    },
    {
        "id": "silent-fallback",
        "mutation": {"path": "gateway.vision.automatic_fallback_used", "value": True},
        "expected": "silent_fallback_forbidden",
    },
    {
        "id": "stale-receipt",
        "mutation": {"path": "gateway.text.expires_at", "value": "2026-08-12T00:00:00Z"},
        "expected": "receipt_stale",
    },
)


def validate_gate_state(state: dict[str, Any], *, now: datetime) -> None:
    if not state["font_checks"].get("lucas_noto_sans"):
        raise E2EError("required_font_missing")
    for resource in state["resources"]:
        if not resource.get("exists"):
            raise E2EError("required_resource_missing")
        path = Path(resource["path"])
        if not path.is_file() or sha256_file(path) != resource["sha256"]:
            raise E2EError("resource_checksum_drift")
    if state["layout"].get("overflow"):
        raise E2EError("layout_overflow")
    verified = set(state["verified_evidence_refs"])
    if any(ref not in verified for ref in state["evidence_refs"]):
        raise E2EError("evidence_ref_unresolved")
    if state["privacy"].get("contains_personal_data"):
        raise E2EError("privacy_data_forbidden")
    forbidden = ("最适合你", "建议马上购买", "保证赔付", "一定能赔", "推荐购买")
    if any(token in text for text in state["texts"] for token in forbidden):
        raise E2EError("product_recommendation_forbidden")
    for capability in ("text", "vision"):
        receipt = state["gateway"][capability]
        if receipt.get("status") not in {"draft_only", "candidate_only"}:
            raise E2EError("provider_candidate_unavailable")
        if receipt.get("automatic_fallback_used"):
            raise E2EError("silent_fallback_forbidden")
        if parse_time(receipt["expires_at"]) <= now:
            raise E2EError("receipt_stale")


def run_negative_cases(state: dict[str, Any], *, now: datetime) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in NEGATIVE_CASES:
        mutated = copy.deepcopy(state)
        apply_mutation(mutated, case["mutation"]["path"], case["mutation"]["value"])
        observed = "accepted"
        try:
            validate_gate_state(mutated, now=now)
        except E2EError as exc:
            observed = str(exc)
        if observed != case["expected"]:
            raise E2EError(f"negative_case_failed:{case['id']}:{observed}")
        results.append(
            {"id": case["id"], "status": "blocked_as_expected", "error_class": observed}
        )
    return results
