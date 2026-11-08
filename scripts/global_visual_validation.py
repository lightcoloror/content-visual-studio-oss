"""Global visual context resolution and auditable conformance receipts.

Portability hardening of the existing first-party validator. Runtime resources
are resolved through the packaged ``studio_paths`` projection by default, or
through an explicit caller-provided root for installation/test use. Nothing is
guessed: when the runtime config ships ``shared_root: null`` the module refuses
with a clear blocked condition instead of probing a private or sibling root.

A returned receipt is evidence *data*. It records a tested structural gate; it
does not grant author/platform permission, publish anything, write a ledger,
authorize image generation, or claim that real semantic, typographic, clinical
or audience review happened. ``manual_only`` stays true.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator

try:  # declared mandatory dependency: an empty registry guarantees no retrieval.
    from referencing import Registry
except ImportError as exc:  # pragma: no cover - the dependency is mandatory
    raise RuntimeError(
        "global visual validation requires the declared 'referencing' dependency; "
        "refusing to fall back to a potentially retrieving JSON Schema validator"
    ) from exc

from check_shared_visual_lock import (
    LOCK_FILENAME,
    SOURCE_ROOT_ENV,
    load_locked_member,
    validate_lock,
)
from visual_asset_routing import is_ai_image_generation_authorized

from studio_paths import STUDIO_ROOT

PROJECTION_ROOT = STUDIO_ROOT / "vendor" / "shared-visual-design-system"
RUNTIME_CONFIG = STUDIO_ROOT / "config" / "global-visual-runtime.v1.json"

MATRIX_REF = "contracts/cross-medium-conformance.v1.json"
GUIDELINES_REF = "contracts/guidelines.v1.json"
ICON_REGISTRY_REF = "contracts/icon-registry.v1.json"
GLOBAL_CONTEXT_SCHEMA_NAME = "global-visual-context.v1.schema.json"
CONFORMANCE_SCHEMA_NAME = "visual-conformance-receipt.v1.schema.json"
GLOBAL_CONTEXT_SCHEMA = PROJECTION_ROOT / "schemas" / GLOBAL_CONTEXT_SCHEMA_NAME
CONFORMANCE_SCHEMA = PROJECTION_ROOT / "schemas" / CONFORMANCE_SCHEMA_NAME

_EMPTY_REGISTRY = Registry()


# ---------------------------------------------------------------------------
# Byte-accurate plumbing
# ---------------------------------------------------------------------------


def _read_bytes(path: Path) -> bytes:
    """Capture file bytes once so hashing and JSON decoding share one buffer."""

    return Path(path).read_bytes()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(_read_bytes(path))


def _decode_json(data: bytes, label: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"{label} is not valid JSON: {exc}") from exc


def _load(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_aware_datetime(value: object, *, assume_utc: bool = False) -> datetime | None:
    """Parse a date-time string; naive values are only accepted when coerced to UTC."""

    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        if not assume_utc:
            return None
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


# ---------------------------------------------------------------------------
# Runtime and path resolution (explicit, never guessed)
# ---------------------------------------------------------------------------


def _runtime_config_path(runtime_path: Path | str | None = None) -> Path:
    return Path(runtime_path) if runtime_path is not None else RUNTIME_CONFIG


def _projection_root(schema_root: Path | str | None = None) -> Path:
    if schema_root is not None:
        return Path(schema_root).expanduser().resolve()
    return PROJECTION_ROOT


def _lock_path(projection_root: Path) -> Path:
    return projection_root / LOCK_FILENAME


def _load_runtime(runtime_path: Path | str | None = None) -> dict[str, Any]:
    path = _runtime_config_path(runtime_path)
    try:
        runtime = _load(path)
    except (OSError, ValueError) as exc:
        raise ValueError(f"global visual runtime config is unavailable: {exc}") from exc
    if not isinstance(runtime, dict):
        raise ValueError("global visual runtime config must be an object")
    return runtime


def _shared_root(
    runtime: dict[str, Any] | None = None,
    *,
    runtime_path: Path | str | None = None,
    shared_root: Path | str | None = None,
) -> Path:
    """Resolve the explicit shared source root; refuse rather than probe."""

    if shared_root is not None:
        candidate = Path(shared_root).expanduser()
    else:
        value = os.environ.get(SOURCE_ROOT_ENV, "").strip()
        if not value:
            if runtime is None:
                runtime = _load_runtime(runtime_path)
            value = str(runtime.get("shared_root") or "").strip()
        if not value:
            raise ValueError(
                "no explicit shared visual source root is configured; pass shared_root or set "
                + SOURCE_ROOT_ENV
            )
        candidate = Path(value).expanduser()
    resolved = candidate.resolve()
    if not resolved.is_dir():
        raise ValueError(f"shared visual source root is unavailable: {resolved}")
    return resolved


def _source_member(root: Path, ref: object) -> Path:
    """Resolve a canonical relative source reference inside one declared root."""

    if not isinstance(ref, str) or not ref or "\\" in ref or ":" in ref:
        raise ValueError("source reference must be a canonical relative path")
    rel = PurePosixPath(ref)
    if rel.is_absolute() or any(part in {".", ".."} for part in ref.split("/")):
        raise ValueError("source reference must stay inside its declared root")
    if rel.as_posix() != ref:
        raise ValueError("source reference must be a canonical relative path")
    root_resolved = Path(root).resolve()
    path = (root_resolved / ref).resolve()
    if not path.is_relative_to(root_resolved):
        raise ValueError("source reference resolves outside its declared root")
    return path


def _resolve_declared_source_ref(shared_root: Path, ref: object) -> Path:
    """Resolve a caller-declared source reference without leaving the supplied root."""

    if not isinstance(ref, str) or not ref:
        raise ValueError("source reference must be a non-empty reference")
    if "://" in ref:
        raise ValueError("source reference must be a local file reference, not a remote URL")
    candidate = Path(ref)
    if candidate.is_absolute():
        resolved = candidate.expanduser().resolve()
        if not resolved.is_relative_to(Path(shared_root).resolve()):
            raise ValueError("source reference resolves outside the declared shared root")
        return resolved
    return _source_member(shared_root, ref)


def _canonical_ref_under_root(shared_root: Path, ref: object) -> str:
    """Map a confined declared reference to the exact canonical lock spelling."""

    resolved = _resolve_declared_source_ref(shared_root, ref)
    root = Path(shared_root).resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("source reference resolves outside the declared shared root") from exc
    canonical = relative.as_posix()
    if not canonical or canonical == "." or any(
        part in {"", ".", ".."} for part in canonical.split("/")
    ):
        raise ValueError("source reference must be a canonical relative path")
    return canonical


def _load_locked_source(
    shared_root: Path,
    ref: object,
    label: str,
    *,
    projection_root: Path,
    lock_path: Path,
) -> tuple[Any, str]:
    """Parse a source document decoded from exact lock-pinned bytes.

    The returned hash is the lock entry's declared hash, and the parsed
    document is decoded from the same captured buffer that was compared to
    both the lock entry and its declared projection. A file that is absent
    from the lock (an unlocked extra file) is refused.
    """

    canonical = _canonical_ref_under_root(shared_root, ref)
    try:
        data, declared_sha = load_locked_member(
            shared_root,
            canonical,
            lock_path=lock_path,
            projection_root=projection_root,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        raise ValueError(f"{label} is not bound to the explicit shared lock: {exc}") from exc
    if not data:
        raise ValueError(f"{label} is empty")
    return _decode_json(data, label), declared_sha


def _load_source_json(shared_root: Path, ref: object, label: str) -> Any:
    """Load the contained, unlocked synthetic authority registry.

    Findings-driving source contracts (ruleset, matrix, guidelines, icons) are
    loaded through ``_load_locked_source`` instead. Brand record files are read
    directly by the brand binding/finding paths as explicitly operator-provided
    data; they are not members of the nine-contract lock.
    """

    path = _source_member(shared_root, ref)
    try:
        data = _read_bytes(path)
    except OSError as exc:
        raise ValueError(f"{label} is unavailable: {exc}") from exc
    if not data:
        raise ValueError(f"{label} is empty")
    return _decode_json(data, label)


# ---------------------------------------------------------------------------
# JSON Schema loading (empty registry: unprovided external refs never fetch)
# ---------------------------------------------------------------------------


def _schema_path(schema_root: Path | str | None, name: str) -> Path:
    return _projection_root(schema_root) / "schemas" / name


def _load_schema(schema_root: Path | str | None, name: str) -> dict[str, Any]:
    path = _schema_path(schema_root, name)
    try:
        data = _read_bytes(path)
    except OSError as exc:
        raise ValueError(f"global visual schema {name} is unavailable: {exc}") from exc
    if not data:
        raise ValueError(f"global visual schema {name} is empty")
    schema = _decode_json(data, f"global visual schema {name}")
    if not isinstance(schema, dict):
        raise ValueError(f"global visual schema {name} must be an object")
    return schema


def _validator(schema: dict[str, Any]) -> Draft202012Validator:
    """Build a validator that can never retrieve an unprovided external reference.

    ``referencing`` is a declared mandatory dependency. Missing or unsupported
    registry capability is an explicit refusal; the code never silently drops
    the registry and creates the default potentially retrieving validator.
    """

    if _EMPTY_REGISTRY is None:
        raise RuntimeError(
            "empty referencing Registry is required for global visual schema validation; "
            "refusing a retrieval-enabled fallback validator"
        )
    try:
        return Draft202012Validator(schema, registry=_EMPTY_REGISTRY)
    except TypeError as exc:
        raise RuntimeError(
            "this jsonschema build does not support an explicit empty referencing Registry; "
            "refusing a retrieval-enabled fallback validator"
        ) from exc


def _schema_instance_errors(schema: dict[str, Any], instance: Any, label: str) -> list[str]:
    try:
        validator = _validator(schema)
        return [
            f"{'.'.join(str(part) for part in error.path) or '$'}: {error.message}"
            for error in validator.iter_errors(instance)
        ]
    except Exception as exc:  # noqa: BLE001 - unresolved/malformed schema fails closed
        return [f"{label}: schema validation could not complete: {exc}"]


# ---------------------------------------------------------------------------
# Runtime config consumers
# ---------------------------------------------------------------------------


def resolve_playwright_package(
    *,
    runtime_path: Path | str | None = None,
    package_json: Path | str | None = None,
) -> Path:
    """Resolve the already-reviewed Playwright runtime without importing or installing it.

    The packaged runtime config deliberately ships ``fallback_ref: null``. An
    operator must set the configured environment variable or supply an explicit
    ``package_json`` path; otherwise this is a clear refusal, never a probe.
    The module never imports, launches or installs a browser.
    """

    runtime = _load_runtime(runtime_path)
    config = runtime.get("playwright_package")
    if not isinstance(config, dict):
        raise ValueError("global visual runtime config requires playwright_package")
    env_name = config.get("env")
    fallback_ref = config.get("fallback_ref")
    expected_name = config.get("expected_name")
    expected_version = config.get("expected_version")

    if package_json is not None:
        reference = str(package_json)
    else:
        reference = os.environ.get(env_name, "").strip() if isinstance(env_name, str) else ""
        if not reference and fallback_ref:
            reference = str(fallback_ref).strip()
    if not reference:
        expected_env = str(env_name) if isinstance(env_name, str) and env_name else "the configured environment variable"
        raise ValueError(
            "configured Playwright package is unavailable: set "
            + expected_env
            + " or provide an explicit package_json path"
        )

    package_path = Path(reference).expanduser().resolve()
    try:
        data = _read_bytes(package_path)
    except OSError as exc:
        raise ValueError(f"configured Playwright package is unavailable: {exc}") from exc
    if not data:
        raise ValueError("configured Playwright package is empty")
    package = _decode_json(data, "configured Playwright package")
    if not isinstance(package, dict):
        raise ValueError("configured Playwright package must be an object")
    if package.get("name") != expected_name:
        raise ValueError(f"configured package must be {expected_name!r}")
    if package.get("version") != expected_version:
        raise ValueError(
            f"configured Playwright version {package.get('version')!r} does not match "
            f"{expected_version!r}"
        )
    return package_path


def is_global_visual_enabled(artifact: dict[str, Any], item: dict[str, Any]) -> bool:
    artifact_options = artifact.get("renderer_options") if isinstance(artifact, dict) else None
    if isinstance(artifact_options, dict) and artifact_options.get("global_visual_v1") is True:
        return True
    visual = item.get("visual") if isinstance(item, dict) else None
    design_system = visual.get("design_system") if isinstance(visual, dict) else None
    if isinstance(design_system, dict):
        return bool(design_system.get("global_visual"))
    return False


def _brand_authority_binding(
    shared_root: Path,
    visual_profile: str,
    visual: dict[str, Any],
    authority: dict[str, Any],
) -> dict[str, Any]:
    """Bind an operator-provided brand record structurally; this is not permission."""

    authority_root = _source_member(shared_root, authority.get("local_root"))
    if not authority_root.is_dir():
        raise ValueError("brand authority root is unavailable")
    repository = authority.get("repository")
    authority_version = authority.get("profile_version")
    if not isinstance(repository, str) or not repository:
        raise ValueError("brand authority record requires an explicit repository ref")
    if not isinstance(authority_version, str) or not authority_version:
        raise ValueError("brand authority record requires an explicit profile_version")
    tokens_path = _source_member(authority_root, authority.get("tokens_ref"))
    profile_path = _source_member(authority_root, authority.get("profile_ref"))
    receipt_path = _source_member(authority_root, authority.get("qa_receipt_ref"))
    if not profile_path.is_file():
        raise ValueError("brand authority profile is unavailable")
    try:
        tokens_bytes = _read_bytes(tokens_path)
    except OSError as exc:
        raise ValueError(f"brand authority tokens are unavailable: {exc}") from exc
    if not tokens_bytes:
        raise ValueError("brand authority tokens are empty")
    try:
        receipt_bytes = _read_bytes(receipt_path)
    except OSError as exc:
        raise ValueError(f"brand authority QA receipt is unavailable: {exc}") from exc
    if not receipt_bytes:
        raise ValueError("brand authority QA receipt is empty")
    profile_version = visual.get("visual_profile_version") or authority_version
    return {
        "profile_id": visual_profile,
        "profile_version": str(profile_version),
        "repository_ref": repository,
        "authority_version": authority_version,
        "profile_ref": str(profile_path),
        "tokens_ref": str(tokens_path),
        "projection_sha256": _sha256_bytes(tokens_bytes),
        "qa_receipt_ref": str(receipt_path),
        "qa_receipt_sha256": _sha256_bytes(receipt_bytes),
    }


def build_runtime_context(
    item: dict[str, Any],
    artifact: dict[str, Any],
    *,
    shared_root: Path | str | None = None,
    runtime_path: Path | str | None = None,
    schema_root: Path | str | None = None,
) -> dict[str, Any]:
    """Build the global visual context for one item/artifact pair.

    The shared lock is verified before a declared context is accepted, so a
    caller cannot opt out of the projection check by putting a context on the
    item.
    """

    runtime = _load_runtime(runtime_path)
    projection = _projection_root(schema_root)
    resolved_shared_root = _shared_root(
        runtime, runtime_path=runtime_path, shared_root=shared_root
    )
    lock_errors = validate_lock(
        resolved_shared_root,
        lock_path=_lock_path(projection),
        projection_root=projection,
    )
    if lock_errors:
        raise ValueError("shared visual design lock invalid: " + "; ".join(lock_errors))

    visual = item.get("visual") if isinstance(item, dict) else None
    if visual is not None and not isinstance(visual, dict):
        raise ValueError("item.visual must be an object")
    visual = visual or {}
    declared = (visual.get("design_system") or {}).get("global_visual")
    if declared:
        if not isinstance(declared, dict):
            raise ValueError("declared global visual context must be an object")
        return declared

    ruleset_ref = _canonical_ref_under_root(
        resolved_shared_root, runtime.get("ruleset_ref")
    )
    ruleset_document, ruleset_sha = _load_locked_source(
        resolved_shared_root,
        ruleset_ref,
        "global visual ruleset",
        projection_root=projection,
        lock_path=_lock_path(projection),
    )
    if not isinstance(ruleset_document, dict):
        raise ValueError("global visual ruleset must be an object")

    matrix, _matrix_sha = _load_locked_source(
        resolved_shared_root,
        MATRIX_REF,
        "cross-medium conformance matrix",
        projection_root=projection,
        lock_path=_lock_path(projection),
    )
    profiles = matrix.get("profiles") if isinstance(matrix, dict) else None
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("cross-medium conformance matrix requires a profiles map")
    media_adapter = artifact.get("media_adapter") if isinstance(artifact, dict) else None
    profile_id = next(
        (
            key
            for key, value in profiles.items()
            if isinstance(value, dict) and value.get("media_adapter") == media_adapter
        ),
        None,
    )
    if not profile_id:
        raise ValueError(f"no global visual conformance profile for {media_adapter!r}")

    visual_profile = visual.get("visual_profile", "")
    authority_registry = _load_source_json(
        resolved_shared_root,
        runtime.get("authority_registry_ref"),
        "visual authority registry",
    )
    if not isinstance(authority_registry, dict):
        raise ValueError("visual authority registry must be an object")
    brand_authorities = authority_registry.get("brand_authorities")
    if not isinstance(brand_authorities, dict):
        raise ValueError("visual authority registry requires a brand_authorities map")
    authority = (
        brand_authorities.get(visual_profile)
        if isinstance(visual_profile, str) and visual_profile
        else None
    )
    if authority is not None and not isinstance(authority, dict):
        raise ValueError("brand authority record must be an object")

    context: dict[str, Any] = {
        "schema_version": "global-visual-context.v1",
        "ruleset": {
            "ref": ruleset_ref,
            "version": runtime.get("ruleset_version"),
            "sha256": ruleset_sha,
        },
        "locale": "zh-Hans",
        "writing_mode": "horizontal-tb",
        "conformance_profile": profile_id,
        "authority_scope": "brand-bound" if authority else "global-only",
        "enforcement": {
            "p0": "blocking" if runtime.get("p0_activation") == "active" else "report-only",
            "p1": runtime.get("p1_mode"),
            "p2": runtime.get("p2_mode"),
        },
        "motion": {"mode": "none"},
    }
    if authority:
        context["brand_authority"] = _brand_authority_binding(
            resolved_shared_root, visual_profile, visual, authority
        )
    return context


# ---------------------------------------------------------------------------
# Context validation
# ---------------------------------------------------------------------------


def _exception_errors(exceptions: object, known_rules: set[str]) -> list[str]:
    if exceptions is None:
        return []
    if not isinstance(exceptions, list):
        return ["exceptions: exceptions must be an array"]
    errors: list[str] = []
    now = datetime.now(timezone.utc)
    for index, exception in enumerate(exceptions):
        if not isinstance(exception, dict):
            errors.append(f"exceptions.{index}: exception must be an object")
            continue
        rule_id = exception.get("rule_id")
        if rule_id not in known_rules:
            errors.append(f"exceptions.{index}.rule_id: unknown rule {rule_id!r}")
        expires_at = exception.get("expires_at")
        try:
            if not isinstance(expires_at, str) or not expires_at:
                raise ValueError("expires_at must be a date-time string")
            parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            errors.append(f"exceptions.{index}.expires_at: invalid date-time")
            continue
        if parsed.tzinfo is None:
            errors.append(
                f"exceptions.{index}.expires_at: invalid date-time (naive date-time is not accepted)"
            )
            continue
        if parsed <= now:
            errors.append(f"exceptions.{index}.expires_at: exception is expired")
    return errors


def validate_runtime_context(
    context: dict[str, Any],
    artifact: dict[str, Any] | None = None,
    *,
    shared_root: Path | str | None = None,
    runtime_path: Path | str | None = None,
    schema_root: Path | str | None = None,
) -> list[str]:
    """Return context findings; ruleset bytes are hashed and parsed only once."""

    errors: list[str] = []
    try:
        schema = _load_schema(schema_root, GLOBAL_CONTEXT_SCHEMA_NAME)
    except ValueError as exc:
        return [str(exc)]
    errors.extend(_schema_instance_errors(schema, context, "global visual context"))
    if not isinstance(context, dict):
        return errors + ["global visual context must be an object"]

    try:
        resolved_shared_root = _shared_root(
            runtime_path=runtime_path, shared_root=shared_root
        )
    except ValueError as exc:
        errors.append(f"ruleset: {exc}")
        return errors
    projection = _projection_root(schema_root)
    lock_path = _lock_path(projection)

    ruleset = context.get("ruleset")
    canonical_ruleset_ref: str | None = None
    ruleset_document: dict[str, Any] | None = None
    try:
        if not isinstance(ruleset, dict):
            raise ValueError("context.ruleset must be an object")
        canonical_ruleset_ref = _canonical_ref_under_root(
            resolved_shared_root, ruleset.get("ref")
        )
        data, _declared_sha = load_locked_member(
            resolved_shared_root,
            canonical_ruleset_ref,
            lock_path=lock_path,
            projection_root=projection,
        )
        actual_sha = _sha256_bytes(data)
        if ruleset.get("sha256") != actual_sha:
            errors.append("ruleset.sha256: ruleset hash mismatch")
        document = _decode_json(data, "global visual ruleset")
        if isinstance(document, dict):
            ruleset_document = document
        if not isinstance(document, dict) or document.get("version") != ruleset.get("version"):
            errors.append("ruleset.version: ruleset version mismatch")
    except (OSError, ValueError, RuntimeError) as exc:
        errors.append(f"ruleset: could not verify ruleset: {exc}")

    if artifact:
        try:
            matrix, _matrix_sha = _load_locked_source(
                resolved_shared_root,
                MATRIX_REF,
                "cross-medium conformance matrix",
                projection_root=projection,
                lock_path=lock_path,
            )
            profiles = matrix.get("profiles") if isinstance(matrix, dict) else None
            if not isinstance(profiles, dict):
                raise ValueError("cross-medium conformance matrix requires a profiles map")
            expected_profile = next(
                (
                    profile_id
                    for profile_id, profile in profiles.items()
                    if isinstance(profile, dict)
                    and profile.get("media_adapter") == artifact.get("media_adapter")
                ),
                None,
            )
            if expected_profile != context.get("conformance_profile"):
                errors.append(
                    f"conformance_profile: {context.get('conformance_profile')!r} does not match "
                    f"media adapter {artifact.get('media_adapter')!r}"
                )
        except (OSError, ValueError) as exc:
            errors.append(f"conformance_profile: could not verify profile mapping: {exc}")

    try:
        if canonical_ruleset_ref == GUIDELINES_REF and ruleset_document is not None:
            # The default ruleset is the guidelines document; reuse the exact
            # captured buffer instead of reading the same lock-pinned file twice.
            guidelines = ruleset_document
        else:
            guidelines, _guidelines_sha = _load_locked_source(
                resolved_shared_root,
                GUIDELINES_REF,
                "global visual guidelines",
                projection_root=projection,
                lock_path=lock_path,
            )
        guideline_list = guidelines.get("guidelines") if isinstance(guidelines, dict) else None
        if not isinstance(guideline_list, list):
            raise ValueError("global visual guidelines require a guidelines list")
        known_rules = {
            rule.get("guideline_id") for rule in guideline_list if isinstance(rule, dict)
        }
    except (OSError, ValueError) as exc:
        return errors + [f"ruleset could not be read: {exc}"]
    errors.extend(_exception_errors(context.get("exceptions"), known_rules))
    return errors


# ---------------------------------------------------------------------------
# Findings (P0 blocking / P1 report-only / P2 human-check retained)
# ---------------------------------------------------------------------------


def _brand_authority_is_current(authority: dict[str, Any]) -> bool:
    try:
        receipt_ref = authority.get("qa_receipt_ref")
        declared_receipt_sha = authority.get("qa_receipt_sha256")
        tokens_ref = authority.get("tokens_ref")
        declared_tokens_sha = authority.get("projection_sha256")
        profile_ref = authority.get("profile_ref")
        authority_version = authority.get("authority_version")
        if not all(
            isinstance(value, str) and value
            for value in (
                receipt_ref,
                declared_receipt_sha,
                tokens_ref,
                declared_tokens_sha,
                profile_ref,
                authority_version,
            )
        ):
            return False
        receipt_bytes = _read_bytes(Path(receipt_ref))
        if not receipt_bytes or _sha256_bytes(receipt_bytes) != declared_receipt_sha:
            return False
        receipt = _decode_json(receipt_bytes, "brand authority QA receipt")
        if not isinstance(receipt, dict):
            return False
        if receipt.get("profile_version") != authority_version:
            return False
        qa = receipt.get("qa")
        if not isinstance(qa, dict) or qa.get("status") != "pass":
            return False
        if qa.get("expires_at") is not None:
            expiry = _parse_aware_datetime(qa.get("expires_at"))
            if expiry is None or expiry <= datetime.now(timezone.utc):
                return False
        created_at = _parse_aware_datetime(receipt.get("created_at"))
        if created_at is None:
            return False
        profile_bytes = _read_bytes(Path(profile_ref))
        if not profile_bytes:
            return False
        profile = _decode_json(profile_bytes, "brand authority profile")
        meta = profile.get("meta") if isinstance(profile, dict) else None
        if not isinstance(meta, dict):
            return False
        source_updated_at = _parse_aware_datetime(
            meta.get("source_updated_at"), assume_utc=True
        )
        if source_updated_at is None:
            return False
        tokens_bytes = _read_bytes(Path(tokens_ref))
        if not tokens_bytes or _sha256_bytes(tokens_bytes) != declared_tokens_sha:
            return False
        return created_at >= source_updated_at
    except (OSError, ValueError, TypeError, KeyError):
        return False


def _authority_finding(context: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    enforcement = "blocking" if runtime.get("p0_activation") == "active" else "report-only"
    if context.get("authority_scope") == "global-only":
        return {
            "diagnostic_id": "GVL-AUTH-001",
            "rule_id": "brand-authority-conformance",
            "priority": "P0",
            "enforcement": enforcement,
            "status": "pass",
            "message": "Global-only output is bound to the shared ruleset.",
        }
    valid = _brand_authority_is_current(context.get("brand_authority") or {})
    return {
        "diagnostic_id": "GVL-AUTH-001",
        "rule_id": "brand-authority-conformance",
        "priority": "P0",
        "enforcement": enforcement,
        "status": "pass" if valid else "fail",
        "message": (
            "Brand authority receipt and projection are current."
            if valid
            else "Brand authority receipt is missing, stale, or not passing."
        ),
    }


def _typography_finding(
    artifact: dict[str, Any], typography: dict[str, Any], runtime: dict[str, Any]
) -> dict[str, Any]:
    data = typography if isinstance(typography, dict) else {}
    status = data.get("status", "needs-review")
    if status not in {"pass", "fail", "needs-review"}:
        status = "fail"
    message = data.get("message")
    if not isinstance(message, str) or not message:
        message = "Rendered Chinese typography evidence is required."
    ref = data.get("ref")
    if status == "pass" and not (isinstance(ref, str) and ref):
        status = "needs-review"
        message = "Typography pass requires a rendered evidence reference."
    finding: dict[str, Any] = {
        "diagnostic_id": "GVL-TYPE-001",
        "rule_id": "chinese-typography",
        "priority": "P0",
        "enforcement": "blocking" if runtime.get("p0_activation") == "active" else "report-only",
        "status": status,
        "message": message,
    }
    if isinstance(ref, str) and ref:
        finding["evidence_ref"] = ref
    return finding


def _data_finding(
    artifact: dict[str, Any], data_status: dict[str, Any], runtime: dict[str, Any]
) -> dict[str, Any]:
    applies = (
        artifact.get("layout_intent") == "data-chart"
        or artifact.get("output_family") == "data-chart"
    )
    if not applies:
        return {
            "diagnostic_id": "GVL-DATA-001",
            "rule_id": "data-visual-language",
            "priority": "P0",
            "enforcement": "not-applicable",
            "status": "not-applicable",
            "message": "Artifact is not a data visual.",
        }
    state = data_status if isinstance(data_status, dict) else {}
    message = state.get("message")
    if not isinstance(message, str) or not message:
        message = "New data visuals require data-visual-spec.v1."
    return {
        "diagnostic_id": "GVL-DATA-001",
        "rule_id": "data-visual-language",
        "priority": "P0",
        "enforcement": "blocking" if runtime.get("p0_activation") == "active" else "report-only",
        "status": "pass" if state.get("normalized_spec_valid") is True else "fail",
        "message": message,
    }


def _icon_findings(
    item: dict[str, Any],
    shared_root: Path,
    *,
    schema_root: Path | str | None = None,
) -> list[dict[str, Any]]:
    projection = _projection_root(schema_root)
    registry, _registry_sha = _load_locked_source(
        shared_root,
        ICON_REGISTRY_REF,
        "semantic icon registry",
        projection_root=projection,
        lock_path=_lock_path(projection),
    )
    entries = registry.get("icons") if isinstance(registry, dict) else None
    if not isinstance(entries, list):
        raise ValueError("semantic icon registry requires an icons list")
    icons = {
        entry.get("semantic_id"): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("semantic_id")
    }
    findings: list[dict[str, Any]] = []
    visual = item.get("visual") if isinstance(item, dict) else None
    semantic_maps = visual.get("semantic_visual_map") if isinstance(visual, dict) else None
    for visual_map in semantic_maps or []:
        if not isinstance(visual_map, dict):
            continue
        for binding in visual_map.get("bindings") or []:
            if not isinstance(binding, dict):
                continue
            semantic_id = binding.get("semantic_id")
            registered = icons.get(semantic_id)
            diagnostic_id = "GVL-ICON-001"
            status = "pass"
            message = "Registered semantic icon has visible copy and meaning."
            if not registered:
                status, message = "fail", f"Unregistered semantic icon: {semantic_id}"
            elif str(registered.get("status") or "").startswith("forbidden"):
                diagnostic_id = "GVL-ICON-002"
                status, message = "fail", str(registered.get("reason") or "Forbidden icon metaphor.")
            elif not binding.get("copy_anchor"):
                diagnostic_id = "GVL-ICON-003"
                status, message = "fail", "Semantic icon requires visible copy."
            elif not binding.get("meaning"):
                diagnostic_id = "GVL-ICON-004"
                status, message = "fail", "Semantic icon requires an accessible meaning."
            findings.append(
                {
                    "diagnostic_id": diagnostic_id,
                    "rule_id": "iconography-grammar",
                    "priority": "P1",
                    "enforcement": "report-only",
                    "status": status,
                    "message": message,
                }
            )
    if findings:
        return findings
    return [
        {
            "diagnostic_id": "GVL-ICON-001",
            "rule_id": "iconography-grammar",
            "priority": "P1",
            "enforcement": "not-applicable",
            "status": "not-applicable",
            "message": "No semantic icons are declared.",
        }
    ]


def _imagery_findings(item: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    visual = item.get("visual") if isinstance(item, dict) else None
    assets = visual.get("assets") if isinstance(visual, dict) else None
    for asset in assets or []:
        if not isinstance(asset, dict):
            continue
        role = asset.get("visual_role")
        diagnostic_id = "GVL-IMAGE-001"
        status, message = "pass", "Imagery role, rights and treatment are declared."
        if not role:
            status, message = (
                "fail",
                f"Asset {asset.get('asset_id') or asset.get('ref')} has no visual_role.",
            )
        elif role == "evidence-photo" and asset.get("asset_type") == "stock-photo":
            diagnostic_id = "GVL-IMAGE-002"
            status, message = "fail", "Stock photography cannot be factual evidence."
        elif asset.get("text_overlay_policy") in {"safe-area-only", "explicit-approved"} and not asset.get(
            "safe_crop"
        ):
            diagnostic_id = "GVL-IMAGE-003"
            status, message = "fail", "Text overlay requires safe_crop metadata."
        elif asset.get("fit_strategy") == "focal-cover" and not asset.get("focal_point"):
            diagnostic_id = "GVL-IMAGE-003"
            status, message = "fail", "Focal cover requires focal_point metadata."
        elif asset.get("rights_status") != "verified" or asset.get("privacy_status") not in {
            "verified",
            "not-applicable",
        }:
            diagnostic_id = "GVL-IMAGE-004"
            status, message = "fail", "Imagery rights and privacy must be verified or not applicable."
        elif asset.get("asset_type") == "generated-image" and not is_ai_image_generation_authorized(
            visual.get("ai_image_generation")
        ):
            diagnostic_id = "GVL-IMAGE-005"
            status, message = (
                "fail",
                "Generated imagery requires user-request evidence containing 模型生成图片 or AI 生图.",
            )
        elif role == "evidence-photo" and asset.get("evidence_status") not in {
            "verified",
            "user-confirmed",
        }:
            diagnostic_id = "GVL-IMAGE-002"
            status, message = "fail", "Evidence photography requires verified or user-confirmed evidence."
        elif not asset.get("evidence_status"):
            status, message = (
                "fail",
                "Imagery role, evidence status, treatment and overlay policy are all required for the new route.",
            )
        elif asset.get("evidence_status") in {"needs-review", "unknown"}:
            status, message = "needs-review", "Imagery evidence is not verified."
        elif not asset.get("treatment") or not asset.get("text_overlay_policy"):
            status, message = (
                "fail",
                "Imagery role, evidence status, treatment and overlay policy are all required for the new route.",
            )
        findings.append(
            {
                "diagnostic_id": diagnostic_id,
                "rule_id": "imagery-and-illustration-grammar",
                "priority": "P1",
                "enforcement": "report-only",
                "status": status,
                "message": message,
            }
        )
    if findings:
        return findings
    return [
        {
            "diagnostic_id": "GVL-IMAGE-001",
            "rule_id": "imagery-and-illustration-grammar",
            "priority": "P1",
            "enforcement": "not-applicable",
            "status": "not-applicable",
            "message": "No imagery assets are declared.",
        }
    ]


def _motion_finding(context: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    motion = context.get("motion", {"mode": "none"}) if isinstance(context, dict) else None
    if not isinstance(motion, dict):
        motion = {}
    mode = motion.get("mode", "none")
    if mode == "none":
        return {
            "diagnostic_id": "GVL-MOTION-001",
            "rule_id": "motion-grammar",
            "priority": "P2",
            "enforcement": "not-applicable",
            "status": "not-applicable",
            "message": "Static artifact.",
        }
    if mode != "explicit":
        return {
            "diagnostic_id": "GVL-MOTION-001",
            "rule_id": "motion-grammar",
            "priority": "P2",
            "enforcement": "human-check",
            "status": "fail",
            "message": "Motion mode must be none or explicitly declared.",
        }
    valid = (
        artifact.get("media_adapter") == "web"
        and bool(motion.get("purpose"))
        and bool(motion.get("static_fallback_ref"))
    )
    return {
        "diagnostic_id": "GVL-MOTION-001",
        "rule_id": "motion-grammar",
        "priority": "P2",
        "enforcement": "human-check",
        "status": "needs-review" if valid else "fail",
        "message": (
            "Explicit Web motion requires reduced-motion and frame review."
            if valid
            else "Motion is only allowed for explicit Web artifacts with purpose and static fallback."
        ),
    }


# ---------------------------------------------------------------------------
# Receipt construction
# ---------------------------------------------------------------------------


def _media_qa_errors(media_qa: object) -> list[str]:
    if not isinstance(media_qa, dict):
        return ["media_qa must be an object with an explicit pass or fail result"]
    result = media_qa.get("result")
    if result in {"pass", "fail"}:
        return []
    return [
        "media_qa.result: "
        + repr(result)
        + " is not a pass; missing, needs-review or unknown media evidence cannot produce a pass"
    ]


def build_conformance_receipt(
    item: dict[str, Any],
    artifact: dict[str, Any],
    output_path: Path,
    typography: dict[str, Any],
    data_status: dict[str, Any],
    media_qa: dict[str, Any],
    *,
    shared_root: Path | str | None = None,
    runtime_path: Path | str | None = None,
    schema_root: Path | str | None = None,
) -> dict[str, Any]:
    """Build one conformance receipt; returns data only, writes nothing."""

    runtime = _load_runtime(runtime_path)
    resolved_shared_root = _shared_root(
        runtime, runtime_path=runtime_path, shared_root=shared_root
    )
    context = build_runtime_context(
        item,
        artifact,
        shared_root=resolved_shared_root,
        runtime_path=runtime_path,
        schema_root=schema_root,
    )
    errors = validate_runtime_context(
        context,
        artifact,
        shared_root=resolved_shared_root,
        runtime_path=runtime_path,
        schema_root=schema_root,
    )
    if errors:
        raise ValueError("invalid global visual context: " + "; ".join(errors))
    media_errors = _media_qa_errors(media_qa)
    if media_errors:
        raise ValueError("invalid media QA receipt: " + "; ".join(media_errors))

    content_id = item.get("content_id") if isinstance(item, dict) else None
    artifact_id = artifact.get("artifact_id") if isinstance(artifact, dict) else None
    if not isinstance(content_id, str) or not content_id:
        raise ValueError("item.content_id is required")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise ValueError("artifact.artifact_id is required")

    findings = [
        _authority_finding(context, runtime),
        _typography_finding(artifact, typography, runtime),
        _data_finding(artifact, data_status, runtime),
    ]
    findings.extend(_icon_findings(item, resolved_shared_root, schema_root=schema_root))
    findings.extend(_imagery_findings(item))
    findings.append(_motion_finding(context, artifact))

    blocking_fail = media_qa.get("result") == "fail" or any(
        finding["status"] == "fail" and finding["enforcement"] == "blocking"
        for finding in findings
    )
    needs_review = any(finding["status"] == "needs-review" for finding in findings) or any(
        finding["status"] == "fail" and finding["enforcement"] == "human-check"
        for finding in findings
    )
    result = "fail" if blocking_fail else ("review-required" if needs_review else "pass")

    output_ref = Path(output_path)
    try:
        output_bytes = _read_bytes(output_ref)
    except OSError as exc:
        raise ValueError(f"artifact output is unavailable: {exc}") from exc
    if not output_bytes:
        raise ValueError("artifact output is empty")

    authority_receipts = [
        {
            "kind": "global-rules",
            "ref": context["ruleset"]["ref"],
            "schema_version": "global-visual-guidelines.v1",
            "sha256": context["ruleset"]["sha256"],
        }
    ]
    if context.get("brand_authority"):
        authority_receipts.append(
            {
                "kind": "brand-authority",
                "ref": context["brand_authority"]["qa_receipt_ref"],
                "schema_version": "authority-receipt.v1",
                "sha256": context["brand_authority"]["qa_receipt_sha256"],
            }
        )
    receipt: dict[str, Any] = {
        "schema_version": "visual-conformance-receipt.v1",
        "receipt_id": f"{content_id}.{artifact_id}.visual-conformance",
        "artifact_id": artifact_id,
        "content_id": content_id,
        "created_at": _now_iso(),
        "ruleset": context["ruleset"],
        "output": {"ref": str(output_ref), "sha256": _sha256_bytes(output_bytes)},
        "authority_receipts": authority_receipts,
        "media_qa": media_qa,
        "findings": findings,
        "result": result,
        "policy": {
            "manual_only": True,
            "candidate_only": runtime.get("p0_activation") != "active",
            "p1_mode": runtime.get("p1_mode"),
            "p2_mode": runtime.get("p2_mode"),
        },
    }
    if context.get("exceptions"):
        receipt["exceptions"] = context["exceptions"]
    receipt_schema = _load_schema(schema_root, CONFORMANCE_SCHEMA_NAME)
    receipt_errors = _schema_instance_errors(
        receipt_schema, receipt, "visual conformance receipt"
    )
    if receipt_errors:
        raise ValueError("invalid visual conformance receipt: " + "; ".join(receipt_errors))
    return receipt


def validate_global_visual_item(
    item: dict[str, Any],
    artifact: dict[str, Any],
    *,
    shared_root: Path | str | None = None,
    runtime_path: Path | str | None = None,
    schema_root: Path | str | None = None,
) -> list[tuple[str, str]]:
    """Validate one enabled item; disabled items return [] without touching dependencies."""

    if not is_global_visual_enabled(artifact, item):
        return []
    try:
        resolved_shared_root = _shared_root(
            runtime_path=runtime_path, shared_root=shared_root
        )
        context = build_runtime_context(
            item,
            artifact,
            shared_root=resolved_shared_root,
            runtime_path=runtime_path,
            schema_root=schema_root,
        )
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        return [("visual.design_system.global_visual", str(exc))]
    return [
        ("visual.design_system.global_visual", message)
        for message in validate_runtime_context(
            context,
            artifact,
            shared_root=resolved_shared_root,
            runtime_path=runtime_path,
            schema_root=schema_root,
        )
    ]
