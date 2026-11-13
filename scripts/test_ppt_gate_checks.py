"""Independently executable acceptance test for ``ppt_gate_checks``.

Standard library only::

    python test_ppt_gate_checks.py

Exit code 0 means every check passed; any failure prints the problems and exits
1. The test covers one positive control plus the ten original negative cases.
Its only resource fixture is a test-local synthetic byte file created under a
``tempfile.TemporaryDirectory`` at run time; no real document, PPT, log,
manuscript or media is read, copied or required.
"""

from __future__ import annotations

import copy
import hashlib
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ppt_gate_checks as gate  # noqa: E402

NOW = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)

# Deterministic synthetic bytes; deliberately not a document of any format.
FIXTURE_BYTES = b"synthetic gate fixture bytes; not a real document or PPT\n"

# The ten negative cases as supplied by the original synthetic test
# (fixed synthetic fixture):
# (id, mutation path, mutation value, expected error code).
EXPECTED_CASES: tuple[tuple[str, str, Any, str], ...] = (
    ("font-missing", "font_checks.lucas_noto_sans", False, "required_font_missing"),
    ("resource-missing", "resources.0.exists", False, "required_resource_missing"),
    (
        "checksum-drift",
        "resources.0.sha256",
        "f" * 64,
        "resource_checksum_drift",
    ),
    ("layout-overflow", "layout.overflow", True, "layout_overflow"),
    ("evidence-missing", "evidence_refs.0", "claim_missing", "evidence_ref_unresolved"),
    (
        "privacy-field",
        "privacy.contains_personal_data",
        True,
        "privacy_data_forbidden",
    ),
    (
        "product-suitability",
        "texts.0",
        "这款产品最适合你，建议马上购买。",
        "product_recommendation_forbidden",
    ),
    (
        "provider-unavailable",
        "gateway.text.status",
        "blocked",
        "provider_candidate_unavailable",
    ),
    (
        "silent-fallback",
        "gateway.vision.automatic_fallback_used",
        True,
        "silent_fallback_forbidden",
    ),
    (
        "stale-receipt",
        "gateway.text.expires_at",
        "2026-08-12T00:00:00Z",
        "receipt_stale",
    ),
)


def build_positive_state(fixture_path: Path, fixture_sha256: str) -> dict[str, Any]:
    """Build a synthetic state that the gate must accept."""
    return {
        "font_checks": {"lucas_noto_sans": True},
        "resources": [
            {
                "exists": True,
                "path": str(fixture_path),
                "sha256": fixture_sha256,
            }
        ],
        "layout": {"overflow": False},
        "evidence_refs": ["evidence_contract", "evidence_form"],
        "verified_evidence_refs": [
            "evidence_contract",
            "evidence_form",
            "evidence_extra",
        ],
        "privacy": {"contains_personal_data": False},
        "texts": ["保障范围以保险合同约定为准。"],
        "gateway": {
            "text": {
                "status": "draft_only",
                "automatic_fallback_used": False,
                "expires_at": "2026-09-02T00:00:00Z",
            },
            "vision": {
                "status": "candidate_only",
                "automatic_fallback_used": False,
                "expires_at": "2026-09-02T00:00:00Z",
            },
        },
    }


def check_bound_cases() -> list[str]:
    """The module's fixed list must equal the ten original cases verbatim."""
    problems: list[str] = []
    module_cases = list(gate.NEGATIVE_CASES)
    if len(module_cases) != len(EXPECTED_CASES):
        problems.append(
            f"module binds {len(module_cases)} cases, expected {len(EXPECTED_CASES)}"
        )
        return problems
    for index, (module_case, expected_case) in enumerate(zip(module_cases, EXPECTED_CASES)):
        case_id, path, value, expected = expected_case
        if module_case.get("id") != case_id:
            problems.append(f"case[{index}] id {module_case.get('id')!r} != {case_id!r}")
            continue
        mutation = module_case.get("mutation") or {}
        if mutation.get("path") != path:
            problems.append(f"{case_id} path {mutation.get('path')!r} != {path!r}")
        if mutation.get("value") != value:
            problems.append(f"{case_id} value {mutation.get('value')!r} != {value!r}")
        if module_case.get("expected") != expected:
            problems.append(
                f"{case_id} expected {module_case.get('expected')!r} != {expected!r}"
            )
    return problems


def check_positive_control(state: dict[str, Any]) -> list[str]:
    try:
        gate.validate_gate_state(state, now=NOW)
    except gate.E2EError as exc:
        return [f"positive control rejected: {exc}"]
    except Exception as exc:  # noqa: BLE001 - unexpected errors are failures
        return [f"positive control raised {type(exc).__name__}: {exc}"]
    return []


def check_single_negative(
    state: dict[str, Any], path: str, value: Any, expected: str
) -> list[str]:
    mutated = copy.deepcopy(state)
    gate.apply_mutation(mutated, path, value)
    observed = "accepted"
    try:
        gate.validate_gate_state(mutated, now=NOW)
    except gate.E2EError as exc:
        observed = str(exc)
    except Exception as exc:  # noqa: BLE001 - unexpected errors are failures
        return [f"raised {type(exc).__name__}: {exc}"]
    if observed != expected:
        return [f"observed {observed!r} != expected {expected!r}"]
    return []


def check_aggregate_replay(state: dict[str, Any]) -> list[str]:
    try:
        results = gate.run_negative_cases(state, now=NOW)
    except gate.E2EError as exc:
        return [f"run_negative_cases raised: {exc}"]
    except Exception as exc:  # noqa: BLE001 - unexpected errors are failures
        return [f"run_negative_cases raised {type(exc).__name__}: {exc}"]

    problems: list[str] = []
    if len(results) != len(EXPECTED_CASES):
        return [f"got {len(results)} results, expected {len(EXPECTED_CASES)}"]
    result_ids = [result.get("id") for result in results]
    expected_ids = [case[0] for case in EXPECTED_CASES]
    if result_ids != expected_ids:
        problems.append(f"result order {result_ids!r} != {expected_ids!r}")
    for result, (case_id, _path, _value, expected) in zip(results, EXPECTED_CASES):
        if result.get("id") != case_id:
            problems.append(f"result id {result.get('id')!r} != {case_id!r}")
        if result.get("status") != "blocked_as_expected":
            problems.append(
                f"{case_id} status {result.get('status')!r} != 'blocked_as_expected'"
            )
        if result.get("error_class") != expected:
            problems.append(
                f"{case_id} error_class {result.get('error_class')!r} != {expected!r}"
            )
    return problems


def main() -> int:
    failures: list[str] = []
    passed: list[str] = []

    def record(name: str, problems: list[str]) -> None:
        if problems:
            for problem in problems:
                failures.append(f"{name}: {problem}")
            print(f"FAIL {name}")
        else:
            passed.append(name)
            print(f"PASS {name}")

    with tempfile.TemporaryDirectory(prefix="ppt-gate-checks-") as tmpdir:
        fixture = Path(tmpdir) / "synthetic_gate_fixture.txt"
        fixture.write_bytes(FIXTURE_BYTES)
        fixture_sha256 = hashlib.sha256(FIXTURE_BYTES).hexdigest()
        state = build_positive_state(fixture, fixture_sha256)
        snapshot = copy.deepcopy(state)

        record("bound-case-list", check_bound_cases())
        record("positive-control", check_positive_control(state))
        for case_id, path, value, expected in EXPECTED_CASES:
            record(
                f"negative-{case_id}",
                check_single_negative(state, path, value, expected),
            )
        record("aggregate-replay", check_aggregate_replay(state))
        record(
            "base-state-unchanged",
            [] if state == snapshot else ["gate mutated the caller's base state"],
        )

    if failures:
        print(f"\nFAILED: {len(failures)} problem(s)")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print(f"\nOK: {len(passed)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
