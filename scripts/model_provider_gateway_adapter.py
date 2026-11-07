"""Thin, loopback-only Content Studio consumer for model-provider-gateway.

This module owns no Provider catalog, consent format, transport SDK, or fallback
policy.  It binds a versioned local content/research artifact to the canonical
Gateway contracts and projects the result into a review-only Content Studio
receipt.
"""

from __future__ import annotations
from studio_paths import STUDIO_ROOT, HUMAN_VOICE_ROOT, research_schema_path

import argparse
import hashlib
import importlib
import json
import math
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator
from urllib.parse import urlparse

import jsonschema


RECEIPT_SCHEMA = "content_studio.model_assist_receipt.v1"
CONSUMER_ID = "content_studio"
SEMANTIC_CONTRACT_REVISION = "content_studio.gateway_semantic_compat.v1"
REQUIRED_HTTP_API_SCHEMA = "model_provider_gateway.http.v1"
REQUIRED_ADAPTER_SCHEMA = "model_provider_gateway.adapter_contract.v2"
REQUIRED_REQUEST_SCHEMA = "model_provider_gateway.execution_request.v1"
REQUIRED_RESULT_SCHEMA = "model_provider_gateway.execution_result.v1"
REQUIRED_CONSENT_SCHEMA = "model_provider_gateway.consent_manifest.v2"
REQUIRED_TASK_CAPABILITIES = {
    "draft_only": "text",
    "rewrite": "text",
    "vision_candidate": "vision",
}
REQUIRED_FORBIDDEN_FIELDS = {"provider_url", "api_key", "headers", "raw_json", "fallback"}
REQUIRED_GATEWAY_INVARIANTS = {
    "provider_protocol_adapter": "litellm_only",
    "arbitrary_urls_allowed": False,
    "silent_fallback_allowed": False,
    "automatic_retry_allowed": False,
    "saving_profile_is_consent": False,
    "real_provider_called": False,
    "file_upload_requires_exact_manifest_and_user_approval": True,
}
TASK_OUTPUT_STATUS = {
    "draft_only": "draft_only",
    "rewrite": "draft_only",
    "vision_candidate": "candidate_only",
}
WORKSPACE_ROOT = STUDIO_ROOT
RESEARCH_OUTPUT_SCHEMA_PATH = research_schema_path()
CONTENT_ITEM_SCHEMA_PATH = STUDIO_ROOT / "schemas/content-item.schema.json"
RECEIPT_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "model-provider-gateway-content-assist-receipt.v1.schema.json"
MOCK_SENTINELS = {"mock-ok", "mock-vision-ok"}


class ContentGatewayError(RuntimeError):
    """A stable, consumer-owned contract error."""


def run_content_assist(
    *,
    gateway_root: str | Path,
    profile: dict[str, Any],
    route: dict[str, Any],
    consent: dict[str, Any],
    task: str,
    request_id: str,
    source_context_path: str | Path,
    max_estimated_cost_usd: float,
    ledger_path: str | Path,
    receipt_path: str | Path,
    transport: Any,
) -> dict[str, Any]:
    """Execute one synthetic loopback request and persist an idempotent receipt.

    ``source_context_path`` remains local for vision tasks.  The Gateway consent
    manifest is still the sole authority for every artifact sent to the model.
    """
    if task not in TASK_OUTPUT_STATUS:
        raise ContentGatewayError("unsupported Content Studio Gateway task")
    if not request_id:
        raise ContentGatewayError("request_id is required")
    if (
        isinstance(max_estimated_cost_usd, bool)
        or not isinstance(max_estimated_cost_usd, (int, float))
        or not math.isfinite(max_estimated_cost_usd)
        or max_estimated_cost_usd <= 0
    ):
        raise ContentGatewayError("max_estimated_cost_usd must be a finite positive number")
    runtime = _load_gateway_runtime(gateway_root)
    _validate_transport(runtime, transport)
    source = _load_source_context(source_context_path)
    fingerprint = _request_fingerprint(
        semantic_contract=runtime.semantic_contract,
        profile=profile,
        route=route,
        consent=consent,
        task=task,
        request_id=request_id,
        source=source,
        max_estimated_cost_usd=max_estimated_cost_usd,
    )
    receipt_file = Path(receipt_path)
    with _receipt_lock(receipt_file):
        existing = _read_existing_receipt(receipt_file, fingerprint, runtime=runtime, expected_source=source)
        if existing is not None:
            return existing

        try:
            _validate_no_fallback_contract(profile, route)
            _validate_source_binding(source, consent, task)
            request = runtime.build_execution_request(
                profile,
                route,
                consent,
                consumer_id=CONSUMER_ID,
                task=task,
                max_estimated_cost_usd=max_estimated_cost_usd,
                request_id=request_id,
            )
            adapter_request = {
                "schema": "model_provider_gateway.adapter_request.v2",
                "consumer_id": CONSUMER_ID,
                "task": task,
                "required_capabilities": [request["capability"]],
                "route_id": request["route_id"],
                "route_revision": request["route_revision"],
                "consent_hash": request["consent_hash"],
                "input_manifest_hash": request["input_manifest_hash"],
            }
            runtime.validate_adapter_request(
                adapter_request,
                runtime.adapter_contract(CONSUMER_ID),
            )
            result = runtime.execute_model_request(
                request,
                profile=profile,
                route=route,
                consent=consent,
                ledger_path=ledger_path,
                transport=transport,
                secret_resolver=lambda _ref: "synthetic-loopback-only",
            )
            receipt = _result_receipt(
                runtime=runtime,
                task=task,
                request_id=request_id,
                fingerprint=fingerprint,
                source=source,
                profile=profile,
                route=route,
                consent=consent,
                result=result,
            )
        except Exception as exc:
            receipt = _blocked_receipt(
                runtime=runtime,
                task=task,
                request_id=request_id,
                fingerprint=fingerprint,
                source=source,
                error_class=_safe_error_class(exc),
            )

        _seal_receipt(receipt)
        _validate_receipt(receipt, runtime=runtime, expected_source=source)
        _write_receipt(receipt_file, receipt)
        return receipt


def _validate_no_fallback_contract(profile: dict[str, Any], route: dict[str, Any]) -> None:
    if profile.get("fallback_pool"):
        raise ContentGatewayError("fallback profile pool is not authorized for Content Studio")
    policy = route.get("fallback_policy") or {}
    if policy.get("enabled") is not False or len(route.get("members") or []) != 1:
        raise ContentGatewayError("fallback route is not authorized for Content Studio")


def _validate_transport(runtime: SimpleNamespace, transport: Any) -> None:
    if type(transport) is not runtime.LiteLLMTransport:  # exact canonical type; no duck-typed mode spoofing
        raise ContentGatewayError("Content Studio requires the canonical Gateway LiteLLMTransport")
    if "execute" in getattr(transport, "__dict__", {}):
        raise ContentGatewayError("canonical Gateway transport execution method was overridden")
    if transport.mode != "loopback_stub" or transport._synthetic_key != "synthetic-loopback-only":
        raise ContentGatewayError("Content Studio Gateway execution is loopback-only in this release")
    parsed = urlparse(str(transport._api_base_override or ""))
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
        or parsed.username
        or parsed.password
        or parsed.path.rstrip("/") != "/v1"
        or parsed.query
        or parsed.fragment
    ):
        raise ContentGatewayError("canonical Gateway transport does not target a clean loopback /v1 endpoint")


def _load_gateway_runtime(gateway_root: str | Path) -> SimpleNamespace:
    root = Path(gateway_root).resolve()
    source_root = root / "src"
    request_schema_path = source_root / "model_provider_gateway" / "schemas" / "execution-request.v1.schema.json"
    result_schema_path = source_root / "model_provider_gateway" / "schemas" / "execution-result.v1.schema.json"
    if not source_root.is_dir():
        raise ContentGatewayError("canonical Gateway source root is unavailable")
    try:
        execution_request_schema = json.loads(request_schema_path.read_text(encoding="utf-8"))
        execution_result_schema = json.loads(result_schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(execution_request_schema)
        jsonschema.Draft202012Validator.check_schema(execution_result_schema)
    except (OSError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise ContentGatewayError("canonical Gateway execution-result schema is unavailable") from exc
    checkout_commit = _git_head_provenance(root)
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    try:
        package = importlib.import_module("model_provider_gateway")
        adapters = importlib.import_module("model_provider_gateway.adapters")
        coverage = importlib.import_module("model_provider_gateway.coverage")
        execution = importlib.import_module("model_provider_gateway.execution")
        consent_module = importlib.import_module("model_provider_gateway.consent")
        runtime_module = importlib.import_module("model_provider_gateway.runtime")
    except ImportError as exc:
        raise ContentGatewayError("canonical Gateway package is unavailable") from exc
    loaded_modules = {
        "package": package,
        "adapters": adapters,
        "coverage": coverage,
        "execution": execution,
        "consent": consent_module,
        "runtime": runtime_module,
    }
    if any(source_root.resolve() not in Path(str(module.__file__)).resolve().parents for module in loaded_modules.values()):
        raise ContentGatewayError("loaded Gateway modules do not match the explicit source root")
    matrix = coverage.build_consumer_capability_matrix()
    contract = adapters.adapter_contract(CONSUMER_ID)
    semantic_inputs = {
        "http_api_schema": getattr(runtime_module, "HTTP_API_SCHEMA", None),
        "consent_schema": getattr(consent_module, "CONSENT_SCHEMA", None),
        "request_schema": getattr(execution, "EXECUTION_REQUEST_SCHEMA", None),
        "result_schema": getattr(execution, "EXECUTION_RESULT_SCHEMA", None),
        "request_schema_document": execution_request_schema,
        "result_schema_document": execution_result_schema,
        "matrix": matrix,
        "adapter": contract,
    }
    semantic_contract = _validate_gateway_semantics(
        **semantic_inputs,
    )
    return SimpleNamespace(
        checkout_commit=checkout_commit,
        canonical_commit=matrix.get("canonical_gateway_commit"),
        matrix_revision=matrix["matrix_revision"],
        version=package.__version__,
        semantic_contract=semantic_contract,
        semantic_inputs=deepcopy(semantic_inputs),
        adapter_contract=adapters.adapter_contract,
        validate_adapter_request=adapters.validate_adapter_request,
        build_execution_request=package.build_execution_request,
        execute_model_request=package.execute_model_request,
        LiteLLMTransport=execution.LiteLLMTransport,
        execution_result_schema=execution_result_schema,
        execution_request_schema_sha256=_sha256_file(request_schema_path),
        execution_result_schema_sha256=_sha256_file(result_schema_path),
        consumer_adapter_sha256=_sha256_file(Path(__file__).resolve()),
        receipt_schema_sha256=_sha256_file(RECEIPT_SCHEMA_PATH),
        gateway_component_sha256={
            name: _sha256_file(Path(str(module.__file__)).resolve())
            for name, module in loaded_modules.items()
        },
    )


def _git_head_provenance(root: Path) -> str | None:
    """Return best-effort audit provenance without making Git a runtime gate."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip().lower()
    return value if completed.returncode == 0 and len(value) == 40 else None


def _validate_gateway_semantics(
    *,
    http_api_schema: Any,
    consent_schema: Any,
    request_schema: Any,
    result_schema: Any,
    request_schema_document: dict[str, Any],
    result_schema_document: dict[str, Any],
    matrix: dict[str, Any],
    adapter: dict[str, Any],
) -> dict[str, Any]:
    """Validate only consumer-relevant stable semantics, never release identity."""
    observed_schemas = {
        "http_api_schema": http_api_schema,
        "adapter_schema": adapter.get("schema"),
        "request_schema": request_schema,
        "result_schema": result_schema,
        "consent_schema": consent_schema,
    }
    required_schemas = {
        "http_api_schema": REQUIRED_HTTP_API_SCHEMA,
        "adapter_schema": REQUIRED_ADAPTER_SCHEMA,
        "request_schema": REQUIRED_REQUEST_SCHEMA,
        "result_schema": REQUIRED_RESULT_SCHEMA,
        "consent_schema": REQUIRED_CONSENT_SCHEMA,
    }
    for name, required in required_schemas.items():
        if observed_schemas.get(name) != required:
            raise ContentGatewayError(f"Gateway semantic schema is incompatible: {name}")
    if request_schema_document.get("properties", {}).get("schema", {}).get("const") != REQUIRED_REQUEST_SCHEMA:
        raise ContentGatewayError("Gateway execution request schema document is incompatible")
    result_properties = result_schema_document.get("properties", {})
    if result_properties.get("schema", {}).get("const") != REQUIRED_RESULT_SCHEMA:
        raise ContentGatewayError("Gateway execution result schema document is incompatible")
    if not {"status", "error_class", "retryable", "redacted_audit"} <= set(result_properties):
        raise ContentGatewayError("Gateway execution error semantics are incomplete")

    if adapter.get("consumer_id") != CONSUMER_ID:
        raise ContentGatewayError("Gateway Content Studio adapter identity is incompatible")
    tasks = adapter.get("tasks") or {}
    for task, capability in REQUIRED_TASK_CAPABILITIES.items():
        row = tasks.get(task) or {}
        if (
            row.get("capabilities") != [capability]
            or row.get("execution_status") != "enabled"
            or row.get("control_policy") != "shared_consent"
        ):
            raise ContentGatewayError(f"Gateway task capability is incompatible: {task}")
    if not REQUIRED_FORBIDDEN_FIELDS <= set(adapter.get("forbidden_fields") or []):
        raise ContentGatewayError("Gateway adapter safety fields are incomplete")

    consumers = matrix.get("consumers") or []
    consumer = next((row for row in consumers if row.get("consumer_id") == CONSUMER_ID), None)
    if not consumer or consumer.get("integration_status") != "real_adapter":
        raise ContentGatewayError("Gateway Content Studio consumer capability is unavailable")
    consumer_capabilities = consumer.get("capabilities") or {}
    for capability in set(REQUIRED_TASK_CAPABILITIES.values()):
        if (consumer_capabilities.get(capability) or {}).get("status") != "real_adapter":
            raise ContentGatewayError(f"Gateway required capability is unavailable: {capability}")

    policies = {row.get("capability"): row for row in matrix.get("capability_policies") or []}
    for capability in set(REQUIRED_TASK_CAPABILITIES.values()):
        policy = policies.get(capability) or {}
        if (
            policy.get("shared_execution") != "enabled"
            or policy.get("default_location") != "explicit_route"
            or "consent_v2" not in (policy.get("remote_candidate_requires") or [])
        ):
            raise ContentGatewayError(f"Gateway capability safety policy is incompatible: {capability}")
    invariants = matrix.get("invariants") or {}
    for name, required in REQUIRED_GATEWAY_INVARIANTS.items():
        if invariants.get(name) != required:
            raise ContentGatewayError(f"Gateway safety invariant is incompatible: {name}")

    return {
        "revision": SEMANTIC_CONTRACT_REVISION,
        **required_schemas,
        "required_capabilities": sorted(set(REQUIRED_TASK_CAPABILITIES.values())),
        "no_silent_fallback": True,
        "no_automatic_retry": True,
        "loopback_only": True,
        "error_fields": ["error_class", "retryable", "status"],
    }


def _load_source_context(path_value: str | Path) -> dict[str, Any]:
    path = Path(path_value).resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContentGatewayError("source context is unreadable") from exc
    if not isinstance(payload, dict):
        raise ContentGatewayError("source context must be a JSON object")
    if payload.get("schema") == "research-output.v1" and payload.get("schema_version") == "1.0.0":
        schema_sha256 = _validate_canonical_source_schema(payload, RESEARCH_OUTPUT_SCHEMA_PATH, "research-output.v1")
        constraints = set((payload.get("scope") or {}).get("constraints") or [])
        provenance = payload.get("provenance") or {}
        if "synthetic-only" not in constraints or provenance.get("offline_only") is not True:
            raise ContentGatewayError("research source is not a synthetic offline fixture")
        if provenance.get("external_api_called") is not False:
            raise ContentGatewayError("research source reports an external API call")
        completeness = payload["completeness"]
        guarded = payload["guarded_final_answer"]
        if (
            payload["review_status"]["overall"] != "verified"
            or payload["evidence_status"]["overall"] != "verified"
            or completeness["ready_for_answer"] is not True
            or completeness["blocking_gates"]
            or guarded["status"] != "verified"
            or guarded["ready"] is not True
            or guarded["answer"] is None
            or guarded["blocking_gates"]
        ):
            raise ContentGatewayError("research source is not verified, ready, and blocker-free")
        candidate_claim_texts = {
            row["claim_id"]: row["text"]
            for row in payload["claims"]
            if row["review_status"] == "verified" and row["evidence_status"] == "verified"
        }
        valid_source_ids = {
            row["source_id"]
            for row in payload["sources"]
            if row["review_status"] in {"reviewed", "verified"}
            and row["ref_status"] == "resolved"
            and row["hash"]["status"] == "verified"
            and (row.get("provenance") or {}).get("note_fields", {}).get("data_classification") == "synthetic_only"
        }
        evidence_by_id = {
            row["evidence_id"]: row
            for row in payload["evidence"]
            if row["relation"] == "supports"
            and row["evidence_status"] == "verified"
            and row["review_status"] in {"reviewed", "verified"}
            and row["ai_synthesis"] is False
            and row["claim_id"] in candidate_claim_texts
            and row["source_id"] in valid_source_ids
        }
        links = [
            row for row in (payload.get("evidence_links") or [])
            if row.get("relation") == "supports"
            and row.get("evidence_status") == "verified"
            and row.get("evidence_id") in evidence_by_id
            and evidence_by_id[row["evidence_id"]]["claim_id"] == row.get("claim_id")
            and evidence_by_id[row["evidence_id"]]["source_id"] == row.get("source_id")
            and row.get("source_id") in valid_source_ids
        ]
        strict_claim_ids = {row["claim_id"] for row in links}
        strict_evidence_ids = {row["evidence_id"] for row in links}
        strict_source_ids = {row["source_id"] for row in links}
        verified_claim_texts = {
            claim_id: text for claim_id, text in candidate_claim_texts.items()
            if claim_id in strict_claim_ids
        }
        if (
            not set(guarded["claim_ids"]) <= strict_claim_ids
            or not set(guarded["evidence_ids"]) <= strict_evidence_ids
            or not set(guarded["source_ids"]) <= strict_source_ids
        ):
            raise ContentGatewayError("guarded answer is not strictly bound to verified source evidence")
        evidence_refs = sorted(
            {
                str(row[key])
                for row in links
                if isinstance(row, dict)
                for key in ("claim_id", "evidence_id", "source_id")
                if row.get(key)
            }
        )
        context = {
            "artifact_kind": "research-output.v1",
            "artifact_id": payload.get("research_id"),
            "canonical_schema_id": "research-output.v1@1.0.0",
            "canonical_schema_sha256": schema_sha256,
            "evidence_refs": evidence_refs,
            "verified_claim_texts": verified_claim_texts,
            "guarded_verified_answer": guarded["answer"],
            "guarded_answer_claim_refs": deepcopy(guarded["claim_ids"]),
            "unknowns": deepcopy(payload.get("unknowns") or []),
            "contradictions": deepcopy(payload.get("contradictions") or []),
            "risk_review_state": {
                "review_status": deepcopy(payload.get("review_status")),
                "evidence_status": deepcopy(payload.get("evidence_status")),
                "completeness": deepcopy(payload.get("completeness")),
                "guarded_final_answer_status": (payload.get("guarded_final_answer") or {}).get("status"),
            },
        }
    elif payload.get("schema_version") == "0.2" and payload.get("content_id"):
        schema_sha256 = _validate_canonical_source_schema(payload, CONTENT_ITEM_SCHEMA_PATH, "content-item.v0.2")
        tags = set(payload.get("tags") or [])
        if not str(payload["content_id"]).startswith("synthetic-") or not tags.intersection(
            {"synthetic-only", "synthetic_only"}
        ):
            raise ContentGatewayError("content source is not explicitly synthetic")
        gate_statuses = {name: value.get("status") for name, value in payload["gates"].items()}
        if any(status not in {"pass", "needs-review"} for status in gate_statuses.values()):
            raise ContentGatewayError("content source gates are unavailable or blocked")
        sources = (payload.get("provenance") or {}).get("sources") or []
        verified_facts = (payload.get("provenance") or {}).get("verified_facts") or []
        verified_claim_texts = {
            "verified-fact:" + hashlib.sha256(str(value).encode("utf-8")).hexdigest(): str(value)
            for value in verified_facts
        }
        evidence_refs = sorted(
            set(verified_claim_texts).union({
                "source-ref:" + hashlib.sha256(str(row.get("ref", "")).encode("utf-8")).hexdigest()
                for row in sources
                if isinstance(row, dict) and row.get("ref")
            })
        )
        context = {
            "artifact_kind": "content-item.v0.2",
            "artifact_id": payload.get("content_id"),
            "canonical_schema_id": "content-item.v0.2",
            "canonical_schema_sha256": schema_sha256,
            "evidence_refs": evidence_refs,
            "verified_claim_texts": verified_claim_texts,
            "guarded_verified_answer": None,
            "guarded_answer_claim_refs": [],
            "unknowns": deepcopy((payload.get("provenance") or {}).get("uncertainties") or []),
            "contradictions": [],
            "risk_review_state": {
                "content_status": payload.get("status"),
                "gates": deepcopy(payload.get("gates") or {}),
                "forbidden_claims": deepcopy((payload.get("provenance") or {}).get("forbidden_claims") or []),
            },
        }
    else:
        raise ContentGatewayError("unsupported source context schema")
    if not context["artifact_id"]:
        raise ContentGatewayError("source context has no stable artifact id")
    context["artifact_sha256"] = _sha256_file(path)
    context["local_context_uploaded"] = False
    context["_path"] = str(path)
    return context


def _validate_canonical_source_schema(payload: dict[str, Any], schema_path: Path, label: str) -> str:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        ).validate(payload)
    except (OSError, json.JSONDecodeError, jsonschema.SchemaError, jsonschema.ValidationError) as exc:
        raise ContentGatewayError(f"{label} failed canonical schema validation") from exc
    return _sha256_file(schema_path)


def _validate_source_binding(source: dict[str, Any], consent: dict[str, Any], task: str) -> None:
    artifacts = consent.get("artifacts") or []
    if not artifacts:
        raise ContentGatewayError("consent has no artifact manifest")
    if any(row.get("data_type") != "synthetic_fixture" for row in artifacts):
        raise ContentGatewayError("consent artifact is not an explicitly synthetic fixture")
    source_path = Path(source["_path"]).resolve()
    if task in {"draft_only", "rewrite"}:
        matches = [row for row in artifacts if Path(str(row.get("path", ""))).resolve() == source_path]
        if len(matches) != 1 or matches[0].get("sha256") != source["artifact_sha256"]:
            raise ContentGatewayError("source artifact hash provenance drift detected")
    elif any(row.get("mime_type") not in {"image/png", "image/jpeg", "image/webp"} for row in artifacts):
        raise ContentGatewayError("vision consent contains a non-image artifact")


def _result_receipt(
    *, runtime: SimpleNamespace, task: str, request_id: str, fingerprint: str,
    source: dict[str, Any], profile: dict[str, Any], route: dict[str, Any],
    consent: dict[str, Any], result: dict[str, Any],
) -> dict[str, Any]:
    completed = bool(result.get("ok")) and result.get("status") == "completed"
    candidate_claim_refs: list[str] = []
    if completed:
        candidate_claim_refs = _validate_model_candidate(result, source)
    public_source = {key: deepcopy(value) for key, value in source.items() if key != "_path"}
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "ok": completed,
        "status": TASK_OUTPUT_STATUS[task] if completed else "blocked",
        "consumer_id": CONSUMER_ID,
        "task": task,
        "request_id": request_id,
        "request_fingerprint": fingerprint,
        "gateway_provenance": {
            "canonical_execution_commit": runtime.canonical_commit,
            "runtime_checkout_commit": runtime.checkout_commit,
            "package_version": runtime.version,
            "capability_matrix_revision": runtime.matrix_revision,
            "semantic_contract": deepcopy(runtime.semantic_contract),
            "adapter_schema": REQUIRED_ADAPTER_SCHEMA,
            "request_schema": REQUIRED_REQUEST_SCHEMA,
            "result_schema": REQUIRED_RESULT_SCHEMA,
            "execution_request_schema_sha256": runtime.execution_request_schema_sha256,
            "execution_result_schema_sha256": runtime.execution_result_schema_sha256,
            "consumer_adapter_sha256": runtime.consumer_adapter_sha256,
            "receipt_schema_sha256": runtime.receipt_schema_sha256,
            "gateway_component_sha256": deepcopy(runtime.gateway_component_sha256),
            "profile_id": profile.get("profile_id"),
            "profile_revision": profile.get("route_revision"),
            "route_id": route.get("route_id"),
            "route_revision": route.get("route_revision"),
            "consent_hash": consent.get("consent_sha256"),
            "input_manifest_hash": result.get("input_manifest_hash"),
        },
        "source_context": public_source,
        "execution_result": result,
        "candidate": (
            {
                "text": result["output"]["text"],
                "text_sha256": hashlib.sha256(result["output"]["text"].encode("utf-8")).hexdigest(),
                "acceptance_status": TASK_OUTPUT_STATUS[task],
                "claim_refs": candidate_claim_refs,
                "new_fact_count": 0,
            }
            if completed else None
        ),
        "truth_boundary": {
            "may_add_verified_facts": False,
            "source_refs_preserved": True,
            "unknowns_preserved": True,
            "contradictions_preserved": True,
            "risk_review_state_preserved": True,
            "human_review_required": True,
        },
        "execution_boundary": {
            "loopback_stub": result.get("redacted_audit", {}).get("transport") == "loopback_stub",
            "real_provider_called": False,
            "real_secret_read": False,
            "uploaded_source_context": False,
            "automatic_retry_used": False,
            "automatic_fallback_used": False,
            "publication_authorized": False,
            "published": False,
        },
    }
    if not completed:
        receipt["error_class"] = str(result.get("error_class") or "gateway_execution_blocked")
        receipt["error_message"] = "Content Studio model assist failed closed"
    return receipt


def _blocked_receipt(
    *, runtime: SimpleNamespace, task: str, request_id: str, fingerprint: str,
    source: dict[str, Any], error_class: str,
) -> dict[str, Any]:
    public_source = {key: deepcopy(value) for key, value in source.items() if key != "_path"}
    return {
        "schema": RECEIPT_SCHEMA,
        "ok": False,
        "status": "blocked",
        "consumer_id": CONSUMER_ID,
        "task": task,
        "request_id": request_id,
        "request_fingerprint": fingerprint,
        "gateway_provenance": {
            "canonical_execution_commit": runtime.canonical_commit,
            "runtime_checkout_commit": runtime.checkout_commit,
            "package_version": runtime.version,
            "capability_matrix_revision": runtime.matrix_revision,
            "semantic_contract": deepcopy(runtime.semantic_contract),
            "adapter_schema": REQUIRED_ADAPTER_SCHEMA,
            "request_schema": REQUIRED_REQUEST_SCHEMA,
            "result_schema": REQUIRED_RESULT_SCHEMA,
            "execution_request_schema_sha256": runtime.execution_request_schema_sha256,
            "execution_result_schema_sha256": runtime.execution_result_schema_sha256,
            "consumer_adapter_sha256": runtime.consumer_adapter_sha256,
            "receipt_schema_sha256": runtime.receipt_schema_sha256,
            "gateway_component_sha256": deepcopy(runtime.gateway_component_sha256),
        },
        "source_context": public_source,
        "execution_result": None,
        "candidate": None,
        "error_class": error_class,
        "error_message": "Content Studio model assist failed closed",
        "truth_boundary": {
            "may_add_verified_facts": False,
            "source_refs_preserved": True,
            "unknowns_preserved": True,
            "contradictions_preserved": True,
            "risk_review_state_preserved": True,
            "human_review_required": True,
        },
        "execution_boundary": {
            "loopback_stub": False,
            "real_provider_called": False,
            "real_secret_read": False,
            "uploaded_source_context": False,
            "automatic_retry_used": False,
            "automatic_fallback_used": False,
            "publication_authorized": False,
            "published": False,
        },
    }


def _validate_model_candidate(result: dict[str, Any], source: dict[str, Any]) -> list[str]:
    text_value = ((result.get("output") or {}).get("text"))
    if not isinstance(text_value, str) or not text_value:
        raise ContentGatewayError("model output is empty or malformed")
    if text_value in MOCK_SENTINELS:
        return []
    try:
        envelope = json.loads(text_value)
    except json.JSONDecodeError as exc:
        raise ContentGatewayError("model output introduced an unverifiable fact envelope") from exc
    expected_keys = {"text", "claim_refs", "new_facts"}
    if not isinstance(envelope, dict) or set(envelope) != expected_keys:
        raise ContentGatewayError("model output introduced an unverifiable fact envelope")
    claim_refs = envelope.get("claim_refs")
    if (
        not isinstance(envelope.get("text"), str)
        or not envelope["text"]
        or not isinstance(claim_refs, list)
        or not claim_refs
        or any(not isinstance(ref, str) for ref in claim_refs)
        or len(set(claim_refs)) != len(claim_refs)
        or envelope.get("new_facts") != []
    ):
        raise ContentGatewayError("model output introduced unverified or unbound facts")
    verified_texts = source["verified_claim_texts"]
    if not set(claim_refs) <= set(verified_texts):
        raise ContentGatewayError("model output referenced claims outside the source evidence set")
    joined = "\n\n".join(verified_texts[ref] for ref in claim_refs)
    guarded_match = (
        envelope["text"] == source.get("guarded_verified_answer")
        and claim_refs == source.get("guarded_answer_claim_refs")
    )
    if envelope["text"] != joined and not guarded_match:
        raise ContentGatewayError("model output was not extractive from verified source claims")
    return claim_refs


def _seal_receipt(receipt: dict[str, Any]) -> None:
    receipt.pop("receipt_payload_sha256", None)
    receipt["receipt_payload_sha256"] = hashlib.sha256(_canonical_bytes(receipt)).hexdigest()


def _validate_receipt(
    receipt: dict[str, Any], *, runtime: SimpleNamespace, expected_source: dict[str, Any]
) -> None:
    try:
        jsonschema.validate(receipt, json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8")))
    except jsonschema.ValidationError as exc:
        raise ContentGatewayError("receipt failed canonical schema validation") from exc
    sealed = deepcopy(receipt)
    actual_payload_hash = sealed.pop("receipt_payload_sha256")
    if actual_payload_hash != hashlib.sha256(_canonical_bytes(sealed)).hexdigest():
        raise ContentGatewayError("receipt payload hash drifted")
    provenance = receipt["gateway_provenance"]
    if provenance.get("semantic_contract") != runtime.semantic_contract:
        raise ContentGatewayError("receipt Gateway semantic contract drifted")
    if (
        provenance.get("adapter_schema") != REQUIRED_ADAPTER_SCHEMA
        or provenance.get("request_schema") != REQUIRED_REQUEST_SCHEMA
        or provenance.get("result_schema") != REQUIRED_RESULT_SCHEMA
    ):
        raise ContentGatewayError("receipt Gateway schema semantics drifted")
    public_source = {key: deepcopy(value) for key, value in expected_source.items() if key != "_path"}
    if receipt["source_context"] != public_source:
        raise ContentGatewayError("receipt source context drifted")
    truth = receipt["truth_boundary"]
    if truth["may_add_verified_facts"] is not False:
        raise ContentGatewayError("model output cannot add verified facts")
    if not all(
        truth[key] is True
        for key in (
            "source_refs_preserved", "unknowns_preserved", "contradictions_preserved",
            "risk_review_state_preserved", "human_review_required",
        )
    ):
        raise ContentGatewayError("model output dropped a required truth boundary")
    boundary = receipt["execution_boundary"]
    if any(boundary[key] for key in ("real_provider_called", "real_secret_read", "uploaded_source_context", "automatic_retry_used", "automatic_fallback_used", "publication_authorized", "published")):
        raise ContentGatewayError("Content Studio execution boundary was widened")
    result = receipt.get("execution_result")
    if result is not None:
        try:
            jsonschema.Draft202012Validator(runtime.execution_result_schema).validate(result)
        except jsonschema.ValidationError as exc:
            raise ContentGatewayError("embedded Gateway execution result failed canonical schema validation") from exc
        _validate_result_numbers(result)
        audit = result.get("redacted_audit") or {}
        if audit.get("transport") != "loopback_stub" or audit.get("automatic_fallback_used") is not False:
            raise ContentGatewayError("Gateway result is not a no-fallback loopback result")
        expected_capability = "vision" if receipt["task"] == "vision_candidate" else "text"
        cross_bindings = {
            "request_id": receipt["request_id"],
            "route_hash": provenance.get("route_revision"),
            "consent_hash": provenance.get("consent_hash"),
            "input_manifest_hash": provenance.get("input_manifest_hash"),
            "capability": expected_capability,
        }
        if any(result.get(key) != value for key, value in cross_bindings.items()):
            raise ContentGatewayError("Gateway execution result is not bound to the receipt request")
        if audit.get("consumer_id") != CONSUMER_ID or audit.get("task") != receipt["task"]:
            raise ContentGatewayError("Gateway audit identity is not bound to the receipt")
        if audit.get("profile_id") != provenance.get("profile_id"):
            raise ContentGatewayError("Gateway profile identity is not bound to the receipt")
        completed = result.get("ok") is True and result.get("status") == "completed"
        if completed:
            candidate = receipt.get("candidate")
            output_text = (result.get("output") or {}).get("text")
            if (
                receipt["ok"] is not True
                or receipt["status"] != TASK_OUTPUT_STATUS[receipt["task"]]
                or not isinstance(candidate, dict)
                or candidate.get("acceptance_status") != TASK_OUTPUT_STATUS[receipt["task"]]
                or candidate.get("text") != output_text
                or candidate.get("text_sha256") != hashlib.sha256(output_text.encode("utf-8")).hexdigest()
                or candidate.get("new_fact_count") != 0
                or candidate.get("claim_refs") != _validate_model_candidate(result, expected_source)
            ):
                raise ContentGatewayError("candidate is not cross-bound to the canonical Gateway result")
        elif receipt["ok"] is not False or receipt["status"] != "blocked" or receipt.get("candidate") is not None:
            raise ContentGatewayError("failed Gateway result was promoted into a candidate")
        elif receipt.get("error_class") != result.get("error_class"):
            raise ContentGatewayError("blocked receipt error class drifted from Gateway result")
    elif receipt["ok"] is not False or receipt["status"] != "blocked" or receipt.get("candidate") is not None:
        raise ContentGatewayError("receipt without a Gateway result must remain blocked")


def _validate_result_numbers(result: dict[str, Any]) -> None:
    for field in ("estimated_usd", "reserved_ceiling_usd"):
        value = result["cost"].get(field)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ContentGatewayError("Gateway result cost must be finite and nonnegative")
    latency = result.get("latency_ms")
    if isinstance(latency, bool) or not isinstance(latency, int) or latency < 0:
        raise ContentGatewayError("Gateway result latency must be finite and nonnegative")
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = result["usage"].get(field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise ContentGatewayError("Gateway result token usage must be nonnegative integers")


def _safe_error_class(exc: Exception) -> str:
    text = str(exc).lower()
    if "fallback" in text:
        return "fallback_unauthorized"
    if "profile" in text:
        return "profile_drift"
    if "route" in text or "capabilit" in text:
        return "route_or_capability_drift"
    if "consent" in text or "expired" in text or "authorization" in text:
        return "consent_invalid"
    if "provenance" in text or "source context" in text or "artifact" in text:
        return "provenance_drift"
    if "model output" in text or "candidate" in text or "claim" in text or "fact" in text:
        return "model_fact_drift"
    return "consumer_preflight_blocked"


def _request_fingerprint(**values: Any) -> str:
    clean_source = dict(values["source"])
    clean_source.pop("_path", None)
    values["source"] = clean_source
    return hashlib.sha256(_canonical_bytes(values)).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_existing_receipt(
    path: Path,
    fingerprint: str,
    *,
    runtime: SimpleNamespace,
    expected_source: dict[str, Any],
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContentGatewayError("existing receipt is unreadable") from exc
    _validate_receipt(value, runtime=runtime, expected_source=expected_source)
    if value.get("request_fingerprint") != fingerprint:
        raise ContentGatewayError("existing receipt request drift detected")
    return value


def _write_receipt(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(_canonical_bytes(value) + b"\n")
    os.replace(temporary, path)


@contextmanager
def _receipt_lock(path: Path, timeout_seconds: float = 5.0) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(f".{path.name}.lock")
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError("Content Studio receipt lock timed out")
            time.sleep(0.02)
    try:
        yield
    finally:
        try:
            lock.rmdir()
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-root", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--route", required=True)
    parser.add_argument("--consent", required=True)
    parser.add_argument("--task", choices=sorted(TASK_OUTPUT_STATUS), required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--source-context", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--max-cost-usd", required=True, type=float)
    parser.add_argument("--loopback-stub-url", required=True)
    args = parser.parse_args(argv)
    runtime = _load_gateway_runtime(args.gateway_root)
    def load(value: str) -> dict[str, Any]:
        return json.loads(Path(value).read_text(encoding="utf-8"))
    receipt = run_content_assist(
        gateway_root=args.gateway_root,
        profile=load(args.profile),
        route=load(args.route),
        consent=load(args.consent),
        task=args.task,
        request_id=args.request_id,
        source_context_path=args.source_context,
        max_estimated_cost_usd=args.max_cost_usd,
        ledger_path=args.ledger,
        receipt_path=args.receipt,
        transport=runtime.LiteLLMTransport.loopback_stub(args.loopback_stub_url),
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["status"] != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
