"""Verify the explicit shared visual projection, contract shape and source bytes.

Portability hardening of the existing first-party checker. This verifies a
declared snapshot; it does not authorize image generation and it does not
identify a trusted remote publisher merely from a version string, a package
name or a hash supplied in the lock. A caller-provided hash is snapshot data,
never a signature or consent.

The explicit source root is never guessed. It must be passed as ``shared_root``
or configured through ``SHARED_VISUAL_DESIGN_SYSTEM_ROOT``; the packaged
runtime config deliberately ships with ``shared_root: null``.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys

from studio_paths import STUDIO_ROOT

VENDOR_ROOT = STUDIO_ROOT / "vendor" / "shared-visual-design-system"
LOCK_FILENAME = "shared-visual-design-system.lock.json"
LOCK_PATH = VENDOR_ROOT / LOCK_FILENAME
SOURCE_ROOT_ENV = "SHARED_VISUAL_DESIGN_SYSTEM_ROOT"
REQUIRED_SOURCE_REFS = frozenset(
    {
        "schemas/global-visual-context.v1.schema.json",
        "schemas/data-visual-spec.v1.schema.json",
        "schemas/visual-conformance-receipt.v1.schema.json",
        "contracts/guidelines.v1.json",
        "contracts/chinese-typography.v1.json",
        "contracts/icon-registry.v1.json",
        "contracts/imagery-grammar.v1.json",
        "contracts/motion-grammar.v1.json",
        "contracts/cross-medium-conformance.v1.json",
    }
)

_HASH_PATTERN = re.compile(r"[a-f0-9]{64}")

USAGE = """usage: check_shared_visual_lock.py [-h] [--shared-root PATH]

Verify the declared shared visual design system projection against the lock.

The explicit source root is never guessed. Pass --shared-root or set
SHARED_VISUAL_DESIGN_SYSTEM_ROOT.

options:
  -h, --help          show this help message and exit
  --shared-root PATH  explicit shared visual source root
"""


def _read_bytes(path: Path) -> bytes:
    """Read a path exactly once so hashing and parsing share one byte buffer."""

    return Path(path).read_bytes()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(_read_bytes(path))


def _member(root: Path, ref: object) -> Path:
    """Resolve one canonical relative reference inside a declared root.

    Absolute paths, drive letters, backslashes, ``.``/``..`` segments, empty
    references and non-canonical spellings are refused before any file read.
    A resolved symlink that escapes the root is refused as well.
    """

    if not isinstance(ref, str) or not ref or "\\" in ref or ":" in ref:
        raise ValueError("shared reference must be a canonical relative path")
    rel = PurePosixPath(ref)
    if rel.is_absolute() or any(part in {".", ".."} for part in ref.split("/")):
        raise ValueError("shared reference must stay inside its declared root")
    if rel.as_posix() != ref:
        raise ValueError("shared reference must be a canonical relative path")
    root_resolved = Path(root).resolve()
    path = (root_resolved / ref).resolve()
    if not path.is_relative_to(root_resolved):
        raise ValueError("shared reference resolves outside its declared root")
    return path


def _load_lock_document(lock_path: Path | str | None = None) -> dict:
    """Read the lock freshly (never from a cross-root cache)."""

    lock_file = Path(lock_path) if lock_path is not None else LOCK_PATH
    if not lock_file.is_file():
        raise ValueError("shared visual design lock is missing")
    try:
        lock_bytes = _read_bytes(lock_file)
    except OSError as exc:
        raise ValueError("shared visual design lock is unreadable: " + str(exc)) from exc
    try:
        lock = json.loads(lock_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("shared visual design lock is unreadable: " + str(exc)) from exc
    if not isinstance(lock, dict):
        raise ValueError("shared visual design lock must be an object")
    return lock


def load_locked_member(
    shared_root: Path | str | None,
    ref: str,
    *,
    lock_path: Path | str | None = None,
    projection_root: Path | str | None = None,
) -> tuple[bytes, str]:
    """Consume one lock-declared source member as a pinned byte buffer.

    The reference must be the exact canonical relative key of the explicit
    lock ``files`` map. The captured source bytes and the declared projection
    bytes must both hash to that lock entry, and the returned buffer is the one
    that was compared — a later file change is refused instead of being parsed
    as though it were the pinned bytes. Additional custom members that are
    themselves declared in the lock are allowed; a file absent from the lock is
    refused.
    """

    if not isinstance(ref, str) or not ref:
        raise ValueError("locked member reference must be a non-empty canonical relative path")
    lock = _load_lock_document(lock_path)
    files = lock.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("shared visual design lock requires a non-empty files map")
    entry = files.get(ref)
    if not isinstance(entry, dict):
        raise ValueError("source member is not declared in the shared visual lock: " + ref)
    expected = entry.get("sha256")
    if not isinstance(expected, str) or not _HASH_PATTERN.fullmatch(expected):
        raise ValueError("invalid shared lock hash/entry: " + ref)

    source_value = shared_root or os.environ.get(SOURCE_ROOT_ENV, "").strip()
    if not source_value:
        raise ValueError("explicit shared source root required; pass shared_root or set " + SOURCE_ROOT_ENV)
    try:
        source_root = Path(source_value).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("shared visual source root is unusable: " + str(exc)) from exc
    if not source_root.is_dir():
        raise ValueError("shared visual source root is unavailable")
    vendor_root = Path(projection_root) if projection_root is not None else VENDOR_ROOT
    try:
        source_path = _member(source_root, ref)
        projected_path = _member(vendor_root, entry.get("projected_ref"))
    except (OSError, ValueError) as exc:
        raise ValueError("unsafe locked member reference: " + ref + ": " + str(exc)) from exc
    try:
        source_bytes = _read_bytes(source_path)
        projected_bytes = _read_bytes(projected_path)
    except OSError as exc:
        raise ValueError("locked member is unavailable: " + ref + ": " + str(exc)) from exc
    if not source_bytes or not projected_bytes:
        raise ValueError("locked member is empty: " + ref)
    if _sha256_bytes(source_bytes) != expected:
        raise ValueError("locked source hash mismatch: " + ref)
    if _sha256_bytes(projected_bytes) != expected:
        raise ValueError("locked projection hash mismatch: " + ref)
    return source_bytes, expected


def validate_lock(
    shared_root: Path | str | None = None,
    *,
    lock_path: Path | str | None = None,
    projection_root: Path | str | None = None,
) -> list[str]:
    """Return every lock/projection/source finding; an empty list means valid.

    ``lock_path`` and ``projection_root`` are optional installation/test hooks
    for an already-declared projection. They do not add storage, routing or
    trust.
    """

    lock_file = Path(lock_path) if lock_path is not None else LOCK_PATH
    vendor_root = Path(projection_root) if projection_root is not None else VENDOR_ROOT

    if not lock_file.is_file():
        return ["shared visual design lock is missing"]
    try:
        lock_bytes = _read_bytes(lock_file)
    except OSError as exc:
        return ["shared visual design lock is unreadable: " + str(exc)]
    try:
        lock = json.loads(lock_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return ["shared visual design lock is unreadable: " + str(exc)]
    if not isinstance(lock, dict):
        return ["shared visual design lock must be an object"]

    errors: list[str] = []
    if lock.get("schema_version") != "shared-visual-design-system-lock.v1":
        errors.append("shared visual lock schema mismatch")
    if lock.get("package") != "@lightcolor/shared-visual-design-system":
        errors.append("shared visual lock package mismatch")
    if lock.get("consumer") != "content-visual-studio":
        errors.append("shared visual lock consumer mismatch")
    if lock.get("package_version") != "1.1.0":
        errors.append("shared visual package version mismatch")

    files = lock.get("files")
    if not isinstance(files, dict) or not files:
        return errors + ["shared visual lock requires a non-empty files map"]
    if not REQUIRED_SOURCE_REFS <= set(files):
        errors.append("shared visual lock is missing required contract members")

    source_value = shared_root or os.environ.get(SOURCE_ROOT_ENV, "").strip()
    if not source_value:
        return errors + [
            "explicit shared source root required; pass shared_root or set " + SOURCE_ROOT_ENV
        ]
    try:
        source_root = Path(source_value).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        return errors + ["shared visual source root is unusable: " + str(exc)]
    if not source_root.is_dir():
        return errors + ["shared visual source root is unavailable"]

    try:
        vendor_resolved = vendor_root.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        return errors + ["shared visual projection root is unusable: " + str(exc)]

    for source_ref, entry in files.items():
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("sha256"), str)
            or not _HASH_PATTERN.fullmatch(entry["sha256"])
        ):
            errors.append("invalid shared file hash/entry: " + str(source_ref))
            continue
        try:
            source = _member(source_root, source_ref)
            projected = _member(vendor_resolved, entry.get("projected_ref"))
        except (OSError, ValueError) as exc:
            errors.append("unsafe shared reference: " + str(source_ref) + ": " + str(exc))
            continue
        for kind, path in (("projection", projected), ("source", source)):
            try:
                if not path.is_file():
                    errors.append("missing shared " + kind + ": " + str(path))
                    continue
                data = _read_bytes(path)
            except OSError as exc:
                errors.append(
                    "unreadable shared " + kind + ": " + str(source_ref) + ": " + str(exc)
                )
                continue
            if not data:
                # Hash-matching empty files are not a valid declared contract.
                errors.append("empty shared " + kind + ": " + str(source_ref))
                continue
            if _sha256_bytes(data) != entry["sha256"]:
                errors.append("shared " + kind + " drift: " + str(source_ref))
    return errors


def _parse_arguments(argv: list[str]) -> tuple[str, str | None]:
    shared_root: str | None = None
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument in ("-h", "--help"):
            return "help", None
        if argument == "--shared-root":
            index += 1
            if index >= len(argv):
                raise ValueError("--shared-root requires a value")
            shared_root = argv[index]
        elif argument.startswith("--shared-root="):
            shared_root = argument.split("=", 1)[1]
        else:
            raise ValueError("unrecognized argument: " + argument)
        index += 1
    return "run", shared_root


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: --help exits 0 without runtime; findings exit 1; no writes."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        action, shared_root = _parse_arguments(arguments)
    except ValueError as exc:
        print(USAGE, file=sys.stderr)
        print("error: " + str(exc), file=sys.stderr)
        return 2
    if action == "help":
        print(USAGE)
        return 0
    failures = validate_lock(shared_root)
    print(json.dumps({"status": "fail" if failures else "pass", "errors": failures}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
