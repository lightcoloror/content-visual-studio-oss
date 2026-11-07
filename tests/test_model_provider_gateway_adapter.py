from __future__ import annotations

import base64
import copy
import json
import shutil
import sys
import threading
import unittest
import uuid
from contextlib import contextmanager, suppress
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_ROOT = ROOT.parent / "model-provider-gateway"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(GATEWAY_ROOT / "src"))

import pytest
pytest.importorskip("model_provider_gateway", reason="Optional Gateway extra is not installed")

from model_provider_gateway.consent import build_consent_plan, consent_revision  # noqa: E402
from model_provider_gateway.execution import LiteLLMTransport  # noqa: E402
from model_provider_gateway.mock_server import mock_server  # noqa: E402
from model_provider_gateway.profile import build_profile, profile_revision  # noqa: E402
from model_provider_gateway.route import build_route_plan, route_revision  # noqa: E402
from model_provider_gateway_adapter import (  # noqa: E402
    ContentGatewayError,
    _load_gateway_runtime,
    _seal_receipt,
    _validate_gateway_semantics,
    run_content_assist,
)


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@contextmanager
def _custom_text_server(content: str) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            payload = json.dumps(
                {
                    "id": "custom-mock-chat",
                    "object": "chat.completion",
                    "model": "mock-model",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            with suppress(BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _research_source(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "research-output.v1.json"
    canonical_fixture = ROOT / "fixtures" / "case-video-script-v1" / "synthetic-research-output.v1.json"
    payload = json.loads(canonical_fixture.read_text(encoding="utf-8"))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _contracts(tmp_path: Path, source: Path, capability: str = "text") -> tuple[dict, dict, dict]:
    if capability == "text":
        artifact = source
        preset = "modelscope-glm-5-2"
    else:
        artifact = tmp_path / "synthetic-visual.png"
        artifact.write_bytes(PNG_1X1)
        preset = "siliconflow-glm-4-5v"
    profile = build_profile(
        preset,
        "env:MPG_SYNTHETIC_ONLY",
        last_verified="2026-08-05T00:00:00+00:00",
        timeout_seconds=1,
        max_calls=4,
        max_cost_usd=1.0,
    )
    route = build_route_plan(
        f"content-studio-{capability}", capability, [profile], max_calls=4, max_cost_usd=1.0
    )
    consent = build_consent_plan(
        route,
        [artifact],
        capability=capability,
        purpose="Return a synthetic review-only Content Studio candidate.",
        data_type="synthetic_fixture",
        max_calls=4,
        max_cost_usd=1.0,
    )
    return profile, route, consent


def _run(
    tmp_path: Path,
    *,
    task: str = "rewrite",
    capability: str = "text",
    status: int = 200,
    delay: float = 0.0,
    profile: dict | None = None,
    route: dict | None = None,
    consent: dict | None = None,
    request_id: str = "content-studio-test-request",
) -> tuple[dict, Path]:
    source = _research_source(tmp_path)
    if profile is None or route is None or consent is None:
        profile, route, consent = _contracts(tmp_path, source, capability)
    receipt_path = tmp_path / "receipt.json"
    with mock_server(status=status, delay_seconds=delay) as base_url:
        receipt = run_content_assist(
            gateway_root=GATEWAY_ROOT,
            profile=profile,
            route=route,
            consent=consent,
            task=task,
            request_id=request_id,
            source_context_path=source,
            max_estimated_cost_usd=0.1,
            ledger_path=tmp_path / "ledger.json",
            receipt_path=receipt_path,
            transport=LiteLLMTransport.loopback_stub(base_url),
        )
    return receipt, receipt_path


def _case_text_roundtrip_preserves_evidence_and_double_run_is_byte_stable(tmp_path: Path) -> None:
    source = _research_source(tmp_path)
    profile, route, consent = _contracts(tmp_path, source)
    receipt_path = tmp_path / "receipt.json"
    with mock_server() as base_url:
        first = run_content_assist(
            gateway_root=GATEWAY_ROOT,
            profile=profile,
            route=route,
            consent=consent,
            task="rewrite",
            request_id="idempotent-rewrite",
            source_context_path=source,
            max_estimated_cost_usd=0.1,
            ledger_path=tmp_path / "ledger.json",
            receipt_path=receipt_path,
            transport=LiteLLMTransport.loopback_stub(base_url),
        )
    first_bytes = receipt_path.read_bytes()
    second = run_content_assist(
        gateway_root=GATEWAY_ROOT,
        profile=profile,
        route=route,
        consent=consent,
        task="rewrite",
        request_id="idempotent-rewrite",
        source_context_path=source,
        max_estimated_cost_usd=0.1,
        ledger_path=tmp_path / "ledger.json",
        receipt_path=receipt_path,
        transport=LiteLLMTransport.loopback_stub("http://127.0.0.1:1"),
    )
    assert first == second
    assert receipt_path.read_bytes() == first_bytes
    assert first["status"] == "draft_only"
    assert first["candidate"]["text"] == "mock-ok"
    assert "claim_synthetic_service_boundary" in first["source_context"]["evidence_refs"]
    assert first["source_context"]["unknowns"] == []
    assert first["source_context"]["contradictions"] == []
    assert first["source_context"]["risk_review_state"]["guarded_final_answer_status"] == "verified"
    assert first["truth_boundary"]["may_add_verified_facts"] is False
    assert first["execution_boundary"]["automatic_fallback_used"] is False
    assert len(first["receipt_payload_sha256"]) == 64
    assert len(first["gateway_provenance"]["consumer_adapter_sha256"]) == 64
    assert len(first["gateway_provenance"]["receipt_schema_sha256"]) == 64
    serialized = json.dumps(first)
    assert "MPG_SYNTHETIC_ONLY" not in serialized
    assert str(tmp_path) not in serialized


def _case_vision_roundtrip_is_candidate_only_and_does_not_upload_source_context(tmp_path: Path) -> None:
    receipt, _ = _run(tmp_path, task="vision_candidate", capability="vision")
    assert receipt["status"] == "candidate_only"
    assert receipt["candidate"]["text"] == "mock-vision-ok"
    assert receipt["source_context"]["local_context_uploaded"] is False
    assert receipt["execution_boundary"]["uploaded_source_context"] is False
    assert receipt["execution_result"]["artifact_refs"][0]["mime_type"] == "image/png"
    assert "base64" not in json.dumps(receipt)


def _case_draft_only_task_remains_draft_only(tmp_path: Path) -> None:
    receipt, _ = _run(tmp_path, task="draft_only")
    assert receipt["status"] == "draft_only"
    assert receipt["candidate"]["acceptance_status"] == "draft_only"


def _case_provider_failures_are_blocked_without_retry_or_fallback(
    tmp_path: Path, status: int, expected_class: str
) -> None:
    receipt, _ = _run(tmp_path, status=status)
    assert receipt["status"] == "blocked"
    assert receipt["candidate"] is None
    assert receipt["error_class"] == expected_class
    assert receipt["execution_result"]["retryable"] is True
    assert receipt["execution_boundary"]["automatic_retry_used"] is False
    assert receipt["execution_boundary"]["automatic_fallback_used"] is False


def _case_timeout_is_blocked_and_not_retried(tmp_path: Path) -> None:
    receipt, _ = _run(tmp_path, delay=1.3)
    assert receipt["status"] == "blocked"
    assert receipt["error_class"] == "timeout"
    assert receipt["execution_result"]["retryable"] is True
    assert receipt["execution_boundary"]["automatic_retry_used"] is False


def _case_profile_route_consent_and_source_provenance_drift_fail_closed(tmp_path: Path) -> None:
    profile_case = tmp_path / "profile-drift"
    source = _research_source(profile_case)
    profile, route, consent = _contracts(profile_case, source)
    drifted_profile = copy.deepcopy(profile)
    drifted_profile["model"] = "unreviewed-model"
    drifted_profile["route_revision"] = profile_revision(drifted_profile)
    receipt, _ = _run(profile_case, profile=drifted_profile, route=route, consent=consent)
    assert receipt["status"] == "blocked"
    assert receipt["error_class"] == "profile_drift"

    route_case = tmp_path / "route-drift"
    source = _research_source(route_case)
    profile, route, consent = _contracts(route_case, source)
    drifted_route = copy.deepcopy(route)
    drifted_route["route_id"] = "drifted-route"
    receipt, _ = _run(route_case, profile=profile, route=drifted_route, consent=consent)
    assert receipt["status"] == "blocked"
    assert receipt["error_class"] == "route_or_capability_drift"

    consent_case = tmp_path / "consent-drift"
    source = _research_source(consent_case)
    profile, route, consent = _contracts(consent_case, source)
    expired = copy.deepcopy(consent)
    expired["expires_at"] = "2020-01-01T00:00:00+00:00"
    expired["consent_sha256"] = consent_revision(expired)
    receipt, _ = _run(consent_case, profile=profile, route=route, consent=expired)
    assert receipt["status"] == "blocked"
    assert receipt["error_class"] == "consent_invalid"

    source_case = tmp_path / "source-drift"
    source = _research_source(source_case)
    profile, route, consent = _contracts(source_case, source)
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with mock_server() as base_url:
        receipt = run_content_assist(
            gateway_root=GATEWAY_ROOT,
            profile=profile,
            route=route,
            consent=consent,
            task="rewrite",
            request_id="source-drift",
            source_context_path=source,
            max_estimated_cost_usd=0.1,
            ledger_path=source_case / "source-ledger.json",
            receipt_path=source_case / "source-drift.json",
            transport=LiteLLMTransport.loopback_stub(base_url),
        )
    assert receipt["status"] == "blocked"
    assert receipt["error_class"] == "provenance_drift"


def _case_non_loopback_transport_and_real_content_fail_closed(tmp_path: Path) -> None:
    source = _research_source(tmp_path)
    profile, route, consent = _contracts(tmp_path, source)

    class NonLoopback:
        mode = "litellm"

    try:
        run_content_assist(
            gateway_root=GATEWAY_ROOT,
            profile=profile,
            route=route,
            consent=consent,
            task="rewrite",
            request_id="blocked-real-provider",
            source_context_path=source,
            max_estimated_cost_usd=0.1,
            ledger_path=tmp_path / "ledger.json",
            receipt_path=tmp_path / "receipt.json",
            transport=NonLoopback(),
        )
    except ContentGatewayError as exc:
        assert "canonical Gateway LiteLLMTransport" in str(exc)
    else:
        raise AssertionError("non-loopback transport was not blocked")

    real_content = tmp_path / "real-content.json"
    real_content.write_text(
        json.dumps({"schema_version": "0.2", "content_id": "not-synthetic", "provenance": {}}),
        encoding="utf-8",
    )
    try:
        run_content_assist(
            gateway_root=GATEWAY_ROOT,
            profile=profile,
            route=route,
            consent=consent,
            task="rewrite",
            request_id="blocked-real-content",
            source_context_path=real_content,
            max_estimated_cost_usd=0.1,
            ledger_path=tmp_path / "ledger-2.json",
            receipt_path=tmp_path / "receipt-2.json",
            transport=LiteLLMTransport.loopback_stub("http://127.0.0.1:1"),
        )
    except ContentGatewayError as exc:
        assert "failed canonical schema validation" in str(exc)
    else:
        raise AssertionError("non-synthetic content was not blocked")


def _case_explicit_fallback_route_is_rejected_by_content_studio_preflight(tmp_path: Path) -> None:
    source = _research_source(tmp_path)
    profile, route, consent = _contracts(tmp_path, source)
    route["fallback_policy"]["enabled"] = True
    route["fallback_policy"]["ordered"] = True
    route["route_revision"] = route_revision(route)
    consent = build_consent_plan(
        route,
        [source],
        capability="text",
        purpose="Return a synthetic review-only Content Studio candidate.",
        data_type="synthetic_fixture",
        max_calls=4,
        max_cost_usd=1.0,
    )
    receipt, _ = _run(tmp_path, profile=profile, route=route, consent=consent)
    assert receipt["status"] == "blocked"
    assert receipt["candidate"] is None
    assert receipt["error_class"] == "fallback_unauthorized"
    assert receipt["execution_result"] is None
    assert receipt["execution_boundary"]["automatic_fallback_used"] is False


def _case_source_and_consent_truth_gates_fail_closed(tmp_path: Path) -> None:
    invalid_case = tmp_path / "invalid-schema"
    invalid_case.mkdir(parents=True)
    invalid_source = invalid_case / "research-output.v1.json"
    invalid_payload = json.loads(_research_source(invalid_case).read_text(encoding="utf-8"))
    invalid_payload.pop("claims")
    invalid_source.write_text(json.dumps(invalid_payload), encoding="utf-8")
    profile, route, consent = _contracts(invalid_case, invalid_source)
    with self_assert_raises_text(ContentGatewayError, "failed canonical schema validation"):
        run_content_assist(
            gateway_root=GATEWAY_ROOT, profile=profile, route=route, consent=consent,
            task="rewrite", request_id="invalid-source", source_context_path=invalid_source,
            max_estimated_cost_usd=0.1, ledger_path=invalid_case / "ledger.json",
            receipt_path=invalid_case / "receipt.json",
            transport=LiteLLMTransport.loopback_stub("http://127.0.0.1:1"),
        )

    blocked_case = tmp_path / "blocked-research"
    source = _research_source(blocked_case)
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["completeness"]["ready_for_answer"] = False
    payload["completeness"]["blocking_gates"] = ["candidate_evidence_not_reviewed"]
    payload["guarded_final_answer"].update(
        status="blocked", ready=False, answer=None,
        blocking_gates=["candidate_evidence_not_reviewed"],
    )
    source.write_text(json.dumps(payload), encoding="utf-8")
    profile, route, consent = _contracts(blocked_case, source)
    with self_assert_raises_text(ContentGatewayError, "not verified, ready, and blocker-free"):
        run_content_assist(
            gateway_root=GATEWAY_ROOT, profile=profile, route=route, consent=consent,
            task="rewrite", request_id="blocked-source", source_context_path=source,
            max_estimated_cost_usd=0.1, ledger_path=blocked_case / "ledger.json",
            receipt_path=blocked_case / "receipt.json",
            transport=LiteLLMTransport.loopback_stub("http://127.0.0.1:1"),
        )

    consent_case = tmp_path / "consent-data-type"
    source = _research_source(consent_case)
    profile, route, consent = _contracts(consent_case, source)
    consent["artifacts"][0]["data_type"] = "personal_document"
    consent["consent_sha256"] = consent_revision(consent)
    receipt, _ = _run(consent_case, profile=profile, route=route, consent=consent)
    assert receipt["status"] == "blocked"
    assert receipt["error_class"] == "consent_invalid"


@contextmanager
def self_assert_raises_text(error_type: type[Exception], expected: str) -> Iterator[None]:
    try:
        yield
    except error_type as exc:
        assert expected in str(exc), str(exc)
    else:
        raise AssertionError(f"{error_type.__name__} was not raised")


def _case_transport_spoof_and_nonfinite_cost_fail_closed(tmp_path: Path) -> None:
    source = _research_source(tmp_path)
    profile, route, consent = _contracts(tmp_path, source)

    class SpoofTransport:
        mode = "loopback_stub"
        _synthetic_key = "synthetic-loopback-only"
        _api_base_override = "http://127.0.0.1:1/v1"

    for transport, expected in (
        (SpoofTransport(), "canonical Gateway LiteLLMTransport"),
        (
            LiteLLMTransport(
                _api_base_override="http://example.com/v1",
                _synthetic_key="synthetic-loopback-only",
                mode="loopback_stub",
            ),
            "clean loopback /v1 endpoint",
        ),
    ):
        with self_assert_raises_text(ContentGatewayError, expected):
            run_content_assist(
                gateway_root=GATEWAY_ROOT, profile=profile, route=route, consent=consent,
                task="rewrite", request_id="spoof", source_context_path=source,
                max_estimated_cost_usd=0.1, ledger_path=tmp_path / "ledger.json",
                receipt_path=tmp_path / "receipt.json", transport=transport,
            )
    with self_assert_raises_text(ContentGatewayError, "finite positive"):
        run_content_assist(
            gateway_root=GATEWAY_ROOT, profile=profile, route=route, consent=consent,
            task="rewrite", request_id="nan", source_context_path=source,
            max_estimated_cost_usd=float("nan"), ledger_path=tmp_path / "nan-ledger.json",
            receipt_path=tmp_path / "nan-receipt.json",
            transport=LiteLLMTransport.loopback_stub("http://127.0.0.1:1"),
        )


def _case_extract_only_candidate_gate(tmp_path: Path) -> None:
    source = _research_source(tmp_path)
    source_payload = json.loads(source.read_text(encoding="utf-8"))
    claim = source_payload["claims"][0]
    profile, route, consent = _contracts(tmp_path, source)

    supported = json.dumps(
        {"text": claim["text"], "claim_refs": [claim["claim_id"]], "new_facts": []},
        ensure_ascii=False, sort_keys=True,
    )
    with _custom_text_server(supported) as base_url:
        receipt = run_content_assist(
            gateway_root=GATEWAY_ROOT, profile=profile, route=route, consent=consent,
            task="rewrite", request_id="extractive-positive", source_context_path=source,
            max_estimated_cost_usd=0.1, ledger_path=tmp_path / "positive-ledger.json",
            receipt_path=tmp_path / "positive-receipt.json",
            transport=LiteLLMTransport.loopback_stub(base_url),
        )
    assert receipt["status"] == "draft_only"
    assert receipt["candidate"]["claim_refs"] == [claim["claim_id"]]

    unsupported = json.dumps(
        {
            "text": claim["text"] + " 该方案疗效提升80%，并保证全部赔付。",
            "claim_refs": [claim["claim_id"]],
            "new_facts": [],
        },
        ensure_ascii=False, sort_keys=True,
    )
    with _custom_text_server(unsupported) as base_url:
        blocked = run_content_assist(
            gateway_root=GATEWAY_ROOT, profile=profile, route=route, consent=consent,
            task="rewrite", request_id="extractive-negative", source_context_path=source,
            max_estimated_cost_usd=0.1, ledger_path=tmp_path / "negative-ledger.json",
            receipt_path=tmp_path / "negative-receipt.json",
            transport=LiteLLMTransport.loopback_stub(base_url),
        )
    assert blocked["status"] == "blocked"
    assert blocked["error_class"] == "model_fact_drift"
    assert blocked["candidate"] is None


def _case_verified_evidence_tuple_is_required(tmp_path: Path) -> None:
    mutations = {
        "missing-link": lambda value: value["evidence_links"].pop(0),
        "cross-wired-link": lambda value: value["evidence_links"][0].update(
            claim_id="claim_synthetic_interview_boundary"
        ),
        "ai-synthesis": lambda value: value["evidence"][0].update(ai_synthesis=True),
        "candidate-source": lambda value: value["sources"][0].update(review_status="candidate"),
    }
    for label, mutate in mutations.items():
        case = tmp_path / label
        source = _research_source(case)
        payload = json.loads(source.read_text(encoding="utf-8"))
        mutate(payload)
        source.write_text(json.dumps(payload), encoding="utf-8")
        profile, route, consent = _contracts(case, source)
        with self_assert_raises_text(ContentGatewayError, "strictly bound"):
            run_content_assist(
                gateway_root=GATEWAY_ROOT, profile=profile, route=route, consent=consent,
                task="rewrite", request_id=f"tuple-{label}", source_context_path=source,
                max_estimated_cost_usd=0.1, ledger_path=case / "ledger.json",
                receipt_path=case / "receipt.json",
                transport=LiteLLMTransport.loopback_stub("http://127.0.0.1:1"),
            )


def _write_sealed(path: Path, receipt: dict) -> None:
    _seal_receipt(receipt)
    path.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _case_resealed_receipt_tampering_and_runtime_drift_fail_closed(tmp_path: Path) -> None:
    for mutation, expected in (
        ("candidate", "extractive"),
        ("route", "not bound"),
        ("cost-nan", "finite and nonnegative"),
        ("negative-usage", "nonnegative integers"),
    ):
        case = tmp_path / mutation
        receipt, receipt_path = _run(case, request_id=f"tamper-{mutation}")
        tampered = copy.deepcopy(receipt)
        if mutation == "candidate":
            forged = json.dumps(
                {
                    "text": "该治疗方案疗效提升80%，并保证全部赔付。",
                    "claim_refs": ["claim_synthetic_service_boundary"],
                    "new_facts": [],
                },
                ensure_ascii=False, sort_keys=True,
            )
            tampered["execution_result"]["output"]["text"] = forged
            tampered["candidate"]["text"] = forged
            import hashlib
            tampered["candidate"]["text_sha256"] = hashlib.sha256(forged.encode("utf-8")).hexdigest()
            tampered["candidate"]["claim_refs"] = ["claim_synthetic_service_boundary"]
        elif mutation == "route":
            tampered["execution_result"]["route_hash"] = "0" * 64
        elif mutation == "cost-nan":
            tampered["execution_result"]["cost"]["estimated_usd"] = float("nan")
        elif mutation == "negative-usage":
            tampered["execution_result"]["usage"]["total_tokens"] = -1
        _write_sealed(receipt_path, tampered)
        source = _research_source(case)
        profile, route, consent = _contracts(case, source)
        with self_assert_raises_text(ContentGatewayError, expected):
            run_content_assist(
                gateway_root=GATEWAY_ROOT, profile=profile, route=route, consent=consent,
                task="rewrite", request_id=f"tamper-{mutation}", source_context_path=source,
                max_estimated_cost_usd=0.1, ledger_path=case / "ledger.json",
                receipt_path=receipt_path,
                transport=LiteLLMTransport.loopback_stub("http://127.0.0.1:1"),
            )


def _case_compatible_gateway_upgrade_is_not_a_runtime_blocker(tmp_path: Path) -> None:
    source = _research_source(tmp_path)
    profile, route, consent = _contracts(tmp_path, source)
    receipt_path = tmp_path / "receipt.json"
    with mock_server() as base_url:
        first = run_content_assist(
            gateway_root=GATEWAY_ROOT, profile=profile, route=route, consent=consent,
            task="rewrite", request_id="compatible-upgrade", source_context_path=source,
            max_estimated_cost_usd=0.1, ledger_path=tmp_path / "ledger.json",
            receipt_path=receipt_path, transport=LiteLLMTransport.loopback_stub(base_url),
        )
    original_bytes = receipt_path.read_bytes()
    runtime = _load_gateway_runtime(GATEWAY_ROOT)
    upgraded = SimpleNamespace(**vars(runtime))
    upgraded.version = "9.0.0-compatible-test"
    upgraded.checkout_commit = "0" * 40
    upgraded.canonical_commit = "1" * 40
    upgraded.matrix_revision = "2" * 64
    upgraded.execution_request_schema_sha256 = "3" * 64
    upgraded.execution_result_schema_sha256 = "4" * 64
    upgraded.gateway_component_sha256 = {
        key: "5" * 64 for key in runtime.gateway_component_sha256
    }
    with patch("model_provider_gateway_adapter._load_gateway_runtime", return_value=upgraded):
        second = run_content_assist(
            gateway_root=GATEWAY_ROOT, profile=profile, route=route, consent=consent,
            task="rewrite", request_id="compatible-upgrade", source_context_path=source,
            max_estimated_cost_usd=0.1, ledger_path=tmp_path / "ledger.json",
            receipt_path=receipt_path,
            transport=LiteLLMTransport.loopback_stub("http://127.0.0.1:1"),
        )
    assert second == first
    assert receipt_path.read_bytes() == original_bytes
    assert first["gateway_provenance"]["package_version"] != upgraded.version


def _case_semantic_incompatibilities_fail_closed() -> None:
    runtime = _load_gateway_runtime(GATEWAY_ROOT)
    cases = {}

    incompatible_http = copy.deepcopy(runtime.semantic_inputs)
    incompatible_http["http_api_schema"] = "model_provider_gateway.http.v2"
    cases["http-schema"] = (incompatible_http, "http_api_schema")

    incompatible_consent = copy.deepcopy(runtime.semantic_inputs)
    incompatible_consent["consent_schema"] = "model_provider_gateway.consent_manifest.v1"
    cases["consent-schema"] = (incompatible_consent, "consent_schema")

    incompatible_result = copy.deepcopy(runtime.semantic_inputs)
    incompatible_result["result_schema_document"]["properties"]["schema"]["const"] = (
        "model_provider_gateway.execution_result.v2"
    )
    cases["result-schema"] = (incompatible_result, "result schema document")

    missing_capability = copy.deepcopy(runtime.semantic_inputs)
    consumer = next(
        row for row in missing_capability["matrix"]["consumers"]
        if row["consumer_id"] == "content_studio"
    )
    consumer["capabilities"]["vision"]["status"] = "fixture_only"
    cases["missing-capability"] = (missing_capability, "required capability")

    fallback_widened = copy.deepcopy(runtime.semantic_inputs)
    fallback_widened["matrix"]["invariants"]["silent_fallback_allowed"] = True
    cases["fallback-policy"] = (fallback_widened, "safety invariant")

    for label, (inputs, expected) in cases.items():
        with unittest.TestCase().subTest(label=label):
            with self_assert_raises_text(ContentGatewayError, expected):
                _validate_gateway_semantics(**inputs)


class ModelProviderGatewayAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        runtime_root = ROOT / ".gateway-adapter-test"
        runtime_root.mkdir(exist_ok=True)
        self.tmp_path = runtime_root / uuid.uuid4().hex
        self.tmp_path.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_path)

    def test_text_roundtrip_and_idempotence(self) -> None:
        _case_text_roundtrip_preserves_evidence_and_double_run_is_byte_stable(self.tmp_path)

    def test_vision_roundtrip(self) -> None:
        _case_vision_roundtrip_is_candidate_only_and_does_not_upload_source_context(self.tmp_path)

    def test_draft_only_task(self) -> None:
        _case_draft_only_task_remains_draft_only(self.tmp_path)

    def test_http_failures(self) -> None:
        for status, expected_class in ((429, "rate_limited"), (500, "provider_server_error")):
            with self.subTest(status=status):
                _case_provider_failures_are_blocked_without_retry_or_fallback(
                    self.tmp_path / str(status), status, expected_class
                )

    def test_timeout(self) -> None:
        _case_timeout_is_blocked_and_not_retried(self.tmp_path)

    def test_contract_and_provenance_drift(self) -> None:
        _case_profile_route_consent_and_source_provenance_drift_fail_closed(self.tmp_path)

    def test_non_loopback_and_real_content(self) -> None:
        _case_non_loopback_transport_and_real_content_fail_closed(self.tmp_path)

    def test_explicit_fallback_route(self) -> None:
        _case_explicit_fallback_route_is_rejected_by_content_studio_preflight(self.tmp_path)

    def test_source_and_consent_truth_gates(self) -> None:
        _case_source_and_consent_truth_gates_fail_closed(self.tmp_path)

    def test_transport_spoof_and_nonfinite_cost(self) -> None:
        _case_transport_spoof_and_nonfinite_cost_fail_closed(self.tmp_path)

    def test_extract_only_candidate_gate(self) -> None:
        _case_extract_only_candidate_gate(self.tmp_path)

    def test_verified_evidence_tuple(self) -> None:
        _case_verified_evidence_tuple_is_required(self.tmp_path)

    def test_resealed_receipt_tampering(self) -> None:
        _case_resealed_receipt_tampering_and_runtime_drift_fail_closed(self.tmp_path)

    def test_compatible_gateway_upgrade(self) -> None:
        _case_compatible_gateway_upgrade_is_not_a_runtime_blocker(self.tmp_path)

    def test_semantic_incompatibilities(self) -> None:
        _case_semantic_incompatibilities_fail_closed()


if __name__ == "__main__":
    unittest.main()
