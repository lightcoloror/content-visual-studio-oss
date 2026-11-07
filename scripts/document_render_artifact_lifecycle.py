"""Fail-closed, plan-only adapter for Content Studio document-render artifacts.

The generic lifecycle core remains the only implementation of scanning, plan
integrity, quarantine, and restore.  This adapter contributes only Content
Studio root admission, classification, and project-specific protection gates.
It intentionally has no quarantine or purge command.

Public candidate adaptation 2026-11-07: source/installed resources resolve via
`studio_paths`; the Core and the synthetic work root are explicit (no workstation
default root); the process probe reports `unknown` when the host cannot observe
it. Hash-pinned Core API/profile and no-mutation boundaries are unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from studio_paths import STUDIO_ROOT


PROJECT_ROOT = STUDIO_ROOT
CONFIG_PATH = PROJECT_ROOT / "config" / "document-render-artifact-lifecycle.v1.json"
CONFIG_ENV = "CONTENT_STUDIO_ARTIFACT_LIFECYCLE_CONFIG"
WORK_ROOT_ENV = "CONTENT_STUDIO_ARTIFACT_WORK_ROOT"
ADAPTER_SCHEMA = "content-studio.document-render-artifact-lifecycle.v1"
CLASSIFICATION_SCHEMA = "content-studio.document-render-artifact-classification.v1"
MARKER_SCHEMA = "content-studio.synthetic-artifact-root.v1"
TOOL_ID = "content-studio-poc.document-render-lifecycle"
OWNER_LANE = "content-creation-self-media"
PROTECTED_ROLES = {
    "authoritative_input",
    "source_code",
    "runtime_state",
    "secret_or_account_state",
    "final_deliverable",
    "evidence_receipt_manifest",
}
SAFE_ROLES = {"reproducible_derived", "cache_build_test_temp", "duplicate_or_obsolete"}
ALLOWED_LIFECYCLE_STATES = {
    "created", "candidate", "verified", "failed", "superseded", "locked",
    "expired", "retired", "quarantined", "purged",
}


class AdapterError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterError("JSON_READ_FAILED", str(path)) from exc
    if not isinstance(value, dict):
        raise AdapterError("JSON_OBJECT_REQUIRED", str(path))
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        return False
    return True


def config_path() -> Path:
    explicit = os.environ.get(CONFIG_ENV)
    return Path(explicit).expanduser().resolve() if explicit else CONFIG_PATH


def config() -> dict[str, Any]:
    value = _json(config_path())
    if value.get("schema_version") != ADAPTER_SCHEMA:
        raise AdapterError("CONFIG_SCHEMA_INVALID")
    if value.get("tool_id") != TOOL_ID or value.get("owner_lane") != OWNER_LANE:
        raise AdapterError("CONFIG_IDENTITY_INVALID")
    if value.get("lifecycle_profile") != "document_render":
        raise AdapterError("PROFILE_NOT_DOCUMENT_RENDER")
    if value.get("cleanup_mode") != "plan_only" or value.get("automatic_purge") is not False:
        raise AdapterError("UNSAFE_CLEANUP_POLICY")
    return value


def _core_root(cfg: dict[str, Any], core_root: Path | str | None = None) -> Path:
    """Resolve the explicit hash-pinned Core root; never fall back to the cwd."""
    contract = cfg["core_contract"]
    value = core_root if core_root is not None else os.environ.get(contract["core_root_env"])
    if not value:
        value = contract.get("default_root")
    if not value:
        raise AdapterError("CORE_ROOT_REQUIRED", contract["core_root_env"])
    root = Path(value).expanduser().resolve()
    api = root / "artifact_lifecycle_core.py"
    profile = root / "profiles" / "artifact-lifecycle-profiles.v1.json"
    if not api.is_file() or not profile.is_file():
        raise AdapterError("CORE_UNAVAILABLE", str(root))
    if _sha256(api) != contract["api_sha256"]:
        raise AdapterError("CORE_API_HASH_DRIFT")
    if _sha256(profile) != contract["profile_sha256"]:
        raise AdapterError("CORE_PROFILE_HASH_DRIFT")
    return root


def core_module(cfg: dict[str, Any], core_root: Path | str | None = None):
    root = _core_root(cfg, core_root)
    spec = importlib.util.spec_from_file_location("content_studio_artifact_lifecycle_core",
                                                  root / "artifact_lifecycle_core.py")
    if not spec or not spec.loader:
        raise AdapterError("CORE_IMPORT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _shared_disk_policy(core: Any, cfg: dict[str, Any], core_root: Path | str | None = None) -> dict[str, Any]:
    """Read the live, hash-pinned document_render policy from the shared core.

    The adapter deliberately does not mirror reserve, warning, or headroom
    numbers.  Keeping those values in the shared Profile prevents consumer
    drift when the disk policy changes.
    """
    profile_path = _core_root(cfg, core_root) / "profiles" / "artifact-lifecycle-profiles.v1.json"
    profiles = core.read_json(profile_path)
    errors = core.validate_profiles(profiles)
    if errors:
        raise AdapterError("CORE_PROFILE_INVALID", ";".join(errors))
    policy = next((item for item in profiles["profiles"] if item.get("profile_id") == cfg["lifecycle_profile"]), None)
    if not isinstance(policy, dict):
        raise AdapterError("SHARED_PROFILE_NOT_FOUND")
    return policy


def _work_root(work_root: Path | str | None) -> Path:
    value = work_root if work_root is not None else os.environ.get(WORK_ROOT_ENV)
    if not value:
        raise AdapterError("WORK_ROOT_REQUIRED", WORK_ROOT_ENV)
    resolved = Path(value).expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise AdapterError("WORK_ROOT_NOT_DIRECTORY", str(resolved))
    return resolved


def _marker(root: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    marker = root / cfg["synthetic_root_marker"]
    value = _json(marker)
    if value.get("schema_version") != MARKER_SCHEMA:
        raise AdapterError("SYNTHETIC_ROOT_MARKER_INVALID")
    if value.get("synthetic_only") is not True:
        raise AdapterError("SYNTHETIC_ONLY_REQUIRED")
    if value.get("lifecycle_profile") != "document_render":
        raise AdapterError("SYNTHETIC_ROOT_PROFILE_INVALID")
    if value.get("cleanup_mode") != "plan_only":
        raise AdapterError("SYNTHETIC_ROOT_POLICY_INVALID")
    return value


def assert_admitted_root(root: Path, cfg: dict[str, Any], *, synthetic_test_mode: bool = False,
                         work_root: Path | str | None = None) -> Path:
    resolved = root.resolve(strict=True)
    if not resolved.is_dir():
        raise AdapterError("ROOT_NOT_DIRECTORY")
    allowed = [(PROJECT_ROOT / item).resolve() for item in cfg["allowed_synthetic_roots"]]
    in_config = any(resolved == item for item in allowed)
    if not in_config:
        # A test copy must live under an explicit operator work root; a candidate
        # checkout outputs directory is not an implicit admission.
        if not synthetic_test_mode:
            raise AdapterError("ROOT_NOT_ADMITTED", str(resolved))
        if not _is_under(resolved, _work_root(work_root)):
            raise AdapterError("ROOT_NOT_ADMITTED", str(resolved))
    _marker(resolved, cfg)
    return resolved


def _safe_relative(value: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not value:
        raise AdapterError("CLASSIFICATION_PATH_OUTSIDE_ROOT", value)
    return path.as_posix()


def classification(root: Path) -> dict[str, Any]:
    path = root / "artifact-classification.v1.json"
    value = _json(path)
    if value.get("schema_version") != CLASSIFICATION_SCHEMA or not isinstance(value.get("artifacts"), dict):
        raise AdapterError("CLASSIFICATION_SCHEMA_INVALID")
    result: dict[str, Any] = {}
    for relative, policy in value["artifacts"].items():
        safe = _safe_relative(str(relative))
        if not isinstance(policy, dict):
            raise AdapterError("CLASSIFICATION_ITEM_INVALID", safe)
        result[safe] = policy
    return result


def _rebuild_proof(policy: dict[str, Any]) -> dict[str, Any]:
    proof = policy.get("rebuild_proof")
    if not isinstance(proof, dict):
        raise AdapterError("REBUILD_PROOF_REQUIRED")
    required = {"status", "command", "input_hashes", "dependency_lock", "verification_ref"}
    if required - set(proof):
        raise AdapterError("REBUILD_PROOF_INCOMPLETE")
    return proof


def _policy_for(relative: str, policy: dict[str, Any] | None) -> dict[str, Any]:
    if policy is None:
        return {
            "artifact_role": "authoritative_input",
            "lifecycle_state": "locked",
            "sensitivity": "unknown",
            "depends_on": [],
            "referenced_by": ["unknown-classification"],
            "rebuild_proof": {"status": "unknown", "command": None, "input_hashes": [],
                              "dependency_lock": None, "verification_ref": None},
            "minimum_keep_until": None,
            "pin": True,
            "protection_reason": "unknown_path",
        }
    role = policy.get("artifact_role")
    state = policy.get("lifecycle_state")
    if role not in PROTECTED_ROLES | SAFE_ROLES:
        raise AdapterError("ARTIFACT_ROLE_INVALID", relative)
    if state not in ALLOWED_LIFECYCLE_STATES:
        raise AdapterError("LIFECYCLE_STATE_INVALID", relative)
    rebuilt = _rebuild_proof(policy)
    referenced_by = policy.get("referenced_by")
    depends_on = policy.get("depends_on")
    if not isinstance(referenced_by, list) or not isinstance(depends_on, list):
        raise AdapterError("ARTIFACT_REFERENCE_FIELDS_INVALID", relative)
    protected = role in PROTECTED_ROLES or bool(policy.get("pin"))
    return {
        "artifact_role": role,
        "lifecycle_state": state,
        "sensitivity": str(policy.get("sensitivity", "unknown")),
        "depends_on": depends_on,
        "referenced_by": referenced_by,
        "rebuild_proof": rebuilt,
        "minimum_keep_until": policy.get("minimum_keep_until"),
        "pin": protected,
        "protection_reason": "declared_protected" if protected else None,
    }


def _workspace_git_state(git_root: Path | str | None = None) -> str:
    root = Path(git_root).expanduser().resolve() if git_root else PROJECT_ROOT
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    return "dirty" if result.stdout.strip() else "clean"


def _process_probe() -> dict[str, Any]:
    """Conservative read-only process probe; permission failure intentionally blocks plans."""
    try:
        result = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"state": "unknown", "reason": f"process_probe_error:{type(exc).__name__}"}
    if result.returncode != 0:
        return {"state": "unknown", "reason": "process_probe_unavailable"}
    lowered = result.stdout.casefold()
    active = [name for name in ("node.exe", "python.exe", "chrome.exe", "msedge.exe", "playwright.exe")
              if name in lowered]
    return {"state": "active" if active else "idle_confirmed", "active_images": active}


def _adapter_hash(core: Any, cfg: dict[str, Any]) -> str:
    return core.canonical_sha256({"config": cfg, "adapter_sha256": _sha256(Path(__file__))})


def scan(
    root: Path, *, closure_run_id: str, output: Path, checkpoint: Path,
    max_files: int | None = None, synthetic_test_mode: bool = False,
    core_root: Path | str | None = None, work_root: Path | str | None = None,
) -> dict[str, Any]:
    cfg = config()
    core = core_module(cfg, core_root)
    admitted = assert_admitted_root(root, cfg, synthetic_test_mode=synthetic_test_mode, work_root=work_root)
    policies = classification(admitted)
    bounded = min(max_files or int(cfg["max_files"]), int(cfg["max_files"]))
    if bounded < 1:
        raise AdapterError("SCAN_LIMIT_INVALID")
    raw = core.scan_root(
        admitted,
        profile_id="document_render",
        producer_tool_id=TOOL_ID,
        owner_lane=OWNER_LANE,
        closure_run_id=closure_run_id,
        max_files=bounded,
        checkpoint=checkpoint.resolve(),
    )
    if (raw.get("scan") or {}).get("errors"):
        raise AdapterError("SCAN_ERRORS_PRESENT",
                           ";".join(item.get("error", "unknown") for item in raw["scan"]["errors"]))
    for item in raw["artifacts"]:
        policy = _policy_for(item["path"], policies.get(item["path"]))
        item.update(policy)
        item["candidate_kind"] = "protected" if item["pin"] else "rebuildable_intermediate"
    raw["content_studio_adapter"] = {
        "schema_version": ADAPTER_SCHEMA,
        "adapter_sha256": _adapter_hash(core, cfg),
        "synthetic_only": True,
        "artifact_root": str(admitted),
        "authoritative_paths": cfg["authoritative_paths"],
        "core_api_sha256": cfg["core_contract"]["api_sha256"],
        "core_profile_sha256": cfg["core_contract"]["profile_sha256"],
    }
    raw = core.attach_hash(raw, "manifest_sha256")
    errors = core.validate_manifest(raw)
    if errors:
        raise AdapterError("MANIFEST_INVALID", ";".join(errors))
    core.atomic_write_json(output.resolve(), raw)
    return raw


def doctor(
    root: Path, *, operation_class: str = "large", estimated_output_bytes: int | None = None,
    synthetic_test_mode: bool = False, core_root: Path | str | None = None,
    work_root: Path | str | None = None,
) -> dict[str, Any]:
    cfg = config()
    core = core_module(cfg, core_root)
    admitted = assert_admitted_root(root, cfg, synthetic_test_mode=synthetic_test_mode, work_root=work_root)
    if operation_class not in {"large", "non_large"}:
        raise AdapterError("OPERATION_CLASS_INVALID", operation_class)
    if estimated_output_bytes is not None and estimated_output_bytes < 0:
        raise AdapterError("ESTIMATED_OUTPUT_INVALID")
    policy = _shared_disk_policy(core, cfg, core_root)
    estimate_required = operation_class == "large"
    missing_estimate = estimate_required and estimated_output_bytes is None
    result = core.doctor(
        _core_root(cfg, core_root), admitted, "document_render",
        estimated_output_bytes=estimated_output_bytes or 0,
        minimum_free_bytes=policy["minimum_free_bytes"],
        warning_free_bytes=policy["warning_free_bytes"],
        output_headroom_multiplier=policy["output_headroom_multiplier"],
        minimum_free_ratio=None,
    )
    if missing_estimate:
        result["status"] = "blocked"
        result["runtime_ready"] = False
        result["reason_codes"] = sorted(set(result.get("reason_codes", []) + ["estimated_output_required"]))
    result["adapter_schema_version"] = ADAPTER_SCHEMA
    result["artifact_root_admitted"] = True
    result["synthetic_only"] = True
    result["operation_class"] = operation_class
    result["estimated_output_bytes_declared"] = estimated_output_bytes
    result["shared_disk_policy"] = {
        "profile_id": policy["profile_id"],
        "minimum_free_bytes": policy["minimum_free_bytes"],
        "warning_free_bytes": policy["warning_free_bytes"],
        "output_headroom_multiplier": policy["output_headroom_multiplier"],
        "policy_source": "artifact-lifecycle-core/profiles/artifact-lifecycle-profiles.v1.json",
    }
    result["large_render_preflight"] = (
        "blocked_missing_estimate" if missing_estimate
        else ("allowed_with_warning" if result.get("disk", {}).get("warning_only")
              else ("allowed" if result.get("status") == "ready" else "blocked"))
    )
    result["production_mutation_commands"] = []
    return result


def plan_gc(
    manifest: dict[str, Any], *, root: Path, quarantine_root: Path,
    owner_state: str = "unknown", process_state: str = "unknown", dispatch_state: str = "unknown",
    synthetic_test_mode: bool = False, workspace_git_state: str | None = None,
    core_root: Path | str | None = None, work_root: Path | str | None = None,
    git_root: Path | str | None = None,
) -> dict[str, Any]:
    cfg = config()
    core = core_module(cfg, core_root)
    admitted = assert_admitted_root(root, cfg, synthetic_test_mode=synthetic_test_mode, work_root=work_root)
    if manifest.get("content_studio_adapter", {}).get("adapter_sha256") != _adapter_hash(core, cfg):
        raise AdapterError("ADAPTER_OR_CONFIG_DRIFT")
    gate_git = workspace_git_state or _workspace_git_state(git_root)
    if process_state == "auto":
        process_state = _process_probe()["state"]
    core_plan = core.plan_operation(
        manifest, admitted, quarantine_root.resolve(strict=True), "quarantine",
        owner_state=owner_state, process_state=process_state, dispatch_state=dispatch_state,
    )
    extra_blockers = []
    if gate_git != "clean":
        extra_blockers.append("content_studio_git_dirty_or_unknown")
    if owner_state != "idle_confirmed":
        extra_blockers.append("owner_not_idle_confirmed")
    if process_state != "idle_confirmed":
        extra_blockers.append("active_process_not_cleared")
    if dispatch_state != "none_active":
        extra_blockers.append("dispatch_not_cleared")
    for entry in core_plan["entries"]:
        if extra_blockers:
            entry["blocking_gates"] = sorted(set(entry["blocking_gates"] + extra_blockers))
            entry["eligible"] = False
    core_plan["content_studio_adapter"] = {
        "schema_version": ADAPTER_SCHEMA,
        "adapter_sha256": _adapter_hash(core, cfg),
        "root_marker_required": True,
        "workspace_git_state": gate_git,
        "filesystem_mutation_authorized": False,
    }
    return core.attach_hash(core_plan, "plan_sha256")


def verify(plan: dict[str, Any], manifest: dict[str, Any], *, root: Path, quarantine_root: Path,
           synthetic_test_mode: bool = False, core_root: Path | str | None = None,
           work_root: Path | str | None = None) -> dict[str, Any]:
    cfg = config()
    core = core_module(cfg, core_root)
    admitted = assert_admitted_root(root, cfg, synthetic_test_mode=synthetic_test_mode, work_root=work_root)
    adapter = plan.get("content_studio_adapter") or {}
    errors = []
    if adapter.get("adapter_sha256") != _adapter_hash(core, cfg):
        errors.append("adapter_or_config_drift")
    if adapter.get("filesystem_mutation_authorized") is not False:
        errors.append("plan_must_not_authorize_mutation")
    if adapter.get("workspace_git_state") != "clean":
        errors.append("content_studio_git_dirty_or_unknown")
    core_result = core.verify_plan(plan, manifest, admitted, quarantine_root.resolve(strict=True))
    errors.extend(core_result["errors"])
    return {
        "status": "ok" if not errors else "blocked",
        "ok": not errors,
        "errors": sorted(set(errors)),
        "filesystem_mutation_performed": False,
        "core_result": core_result,
    }


def explain(manifest: dict[str, Any], artifact_id: str, *, core_root: Path | str | None = None) -> dict[str, Any]:
    cfg = config()
    core = core_module(cfg, core_root)
    item = next((candidate for candidate in manifest.get("artifacts", [])
                 if candidate.get("artifact_id") == artifact_id), None)
    if not item:
        raise AdapterError("ARTIFACT_NOT_FOUND", artifact_id)
    blockers = []
    if item.get("pin"):
        blockers.append("artifact_pinned")
    if item.get("artifact_role") in PROTECTED_ROLES:
        blockers.append("protected_role")
    if item.get("referenced_by"):
        blockers.append("authoritative_or_unknown_reference")
    proof = item.get("rebuild_proof") or {}
    if not (proof.get("status") == "verified" and proof.get("command") and proof.get("input_hashes")
            and proof.get("dependency_lock") and proof.get("verification_ref")):
        blockers.append("rebuild_proof_incomplete")
    return {"status": "ok", "artifact": item, "blocking_gates": blockers,
            "authorizes_operation": False, "filesystem_mutation_performed": False}


def restore_synthetic(*, plan: dict[str, Any], receipt: dict[str, Any], root: Path, quarantine_root: Path,
                      output: Path, synthetic_test_mode: bool = False,
                      core_root: Path | str | None = None, work_root: Path | str | None = None) -> dict[str, Any]:
    """Narrow restore outlet for marked synthetic roots only; never exposed by default CLI mode."""
    cfg = config()
    if not synthetic_test_mode:
        raise AdapterError("SYNTHETIC_RESTORE_FLAG_REQUIRED")
    core = core_module(cfg, core_root)
    admitted = assert_admitted_root(root, cfg, synthetic_test_mode=True, work_root=work_root)
    return core.restore_from_receipt(receipt, plan, admitted, quarantine_root.resolve(strict=True), output)


def _emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Content Studio document-render lifecycle adapter (plan only)")
    parser.add_argument("--synthetic-test-mode", action="store_true")
    parser.add_argument("--core-root", type=Path, help="Explicit artifact-lifecycle-core source root.")
    parser.add_argument("--work-root", type=Path, help="Explicit operator work root for synthetic test copies.")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor_p = sub.add_parser("doctor")
    doctor_p.add_argument("--root", type=Path, required=True)
    doctor_p.add_argument("--operation-class", choices=["large", "non_large"], default="large")
    doctor_p.add_argument("--estimated-output-bytes", type=int)
    scan_p = sub.add_parser("scan")
    scan_p.add_argument("--root", type=Path, required=True)
    scan_p.add_argument("--closure-run-id", required=True)
    scan_p.add_argument("--output", type=Path, required=True)
    scan_p.add_argument("--checkpoint", type=Path, required=True)
    scan_p.add_argument("--max-files", type=int)
    explain_p = sub.add_parser("explain")
    explain_p.add_argument("--manifest", type=Path, required=True)
    explain_p.add_argument("--artifact-id", required=True)
    plan_p = sub.add_parser("plan-gc")
    plan_p.add_argument("--manifest", type=Path, required=True)
    plan_p.add_argument("--root", type=Path, required=True)
    plan_p.add_argument("--quarantine-root", type=Path, required=True)
    plan_p.add_argument("--output", type=Path, required=True)
    plan_p.add_argument("--owner-state", default="unknown")
    plan_p.add_argument("--process-state", default="auto")
    plan_p.add_argument("--dispatch-state", default="unknown")
    plan_p.add_argument("--git-root", type=Path)
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("--manifest", type=Path, required=True)
    verify_p.add_argument("--plan", type=Path, required=True)
    verify_p.add_argument("--root", type=Path, required=True)
    verify_p.add_argument("--quarantine-root", type=Path, required=True)
    restore_p = sub.add_parser("restore")
    restore_p.add_argument("--manifest", type=Path, required=True)
    restore_p.add_argument("--plan", type=Path, required=True)
    restore_p.add_argument("--receipt", type=Path, required=True)
    restore_p.add_argument("--root", type=Path, required=True)
    restore_p.add_argument("--quarantine-root", type=Path, required=True)
    restore_p.add_argument("--output", type=Path, required=True)
    restore_p.add_argument("--execute-synthetic-restore", action="store_true")
    args = parser.parse_args(argv)
    core_root, work_root = args.core_root, args.work_root
    try:
        if args.command == "doctor":
            result = doctor(
                args.root,
                operation_class=args.operation_class,
                estimated_output_bytes=args.estimated_output_bytes,
                synthetic_test_mode=args.synthetic_test_mode,
                core_root=core_root,
                work_root=work_root,
            )
            _emit(result)
            return 0 if result["status"] == "ready" else 2
        if args.command == "scan":
            manifest = scan(args.root, closure_run_id=args.closure_run_id, output=args.output,
                            checkpoint=args.checkpoint, max_files=args.max_files,
                            synthetic_test_mode=args.synthetic_test_mode,
                            core_root=core_root, work_root=work_root)
            _emit({"status": "ok", "manifest": str(args.output.resolve()),
                   "artifact_count": len(manifest["artifacts"]), "filesystem_mutation_performed": False})
            return 0
        if args.command == "explain":
            _emit(explain(_json(args.manifest), args.artifact_id, core_root=core_root))
            return 0
        if args.command == "plan-gc":
            plan = plan_gc(_json(args.manifest), root=args.root, quarantine_root=args.quarantine_root,
                           owner_state=args.owner_state, process_state=args.process_state,
                           dispatch_state=args.dispatch_state, synthetic_test_mode=args.synthetic_test_mode,
                           core_root=core_root, work_root=work_root, git_root=args.git_root)
            cfg = config()
            core_module(cfg, core_root).atomic_write_json(args.output.resolve(), plan)
            _emit({"status": "ok", "plan": str(args.output.resolve()),
                   "eligible": sum(bool(item["eligible"]) for item in plan["entries"]),
                   "filesystem_mutation_performed": False})
            return 0
        if args.command == "verify":
            result = verify(_json(args.plan), _json(args.manifest), root=args.root,
                            quarantine_root=args.quarantine_root,
                            synthetic_test_mode=args.synthetic_test_mode,
                            core_root=core_root, work_root=work_root)
            _emit(result)
            return 0 if result["ok"] else 2
        if args.command == "restore":
            if not args.execute_synthetic_restore:
                raise AdapterError("SYNTHETIC_RESTORE_EXECUTE_FLAG_REQUIRED")
            _emit(restore_synthetic(plan=_json(args.plan), receipt=_json(args.receipt), root=args.root,
                                    quarantine_root=args.quarantine_root, output=args.output,
                                    synthetic_test_mode=args.synthetic_test_mode,
                                    core_root=core_root, work_root=work_root))
            return 0
    except AdapterError as exc:
        _emit({"status": "blocked", "error_code": exc.code, "detail": exc.detail,
               "filesystem_mutation_performed": False})
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
