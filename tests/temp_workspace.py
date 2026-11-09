from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMP_ROOT = PROJECT_ROOT / "outputs" / ".test-runtime" / "temp"
TEMP_ROOT_ENV = "CONTENT_STUDIO_TEST_TEMP_ROOT"


class TestTempRootError(RuntimeError):
    """Raised when the explicit repository-local test temp root is unusable."""


def _validate_prefix(prefix: object) -> None:
    """Require one ordinary path component; reject separators and control text."""

    if (
        not isinstance(prefix, str)
        or not prefix
        or prefix in {".", ".."}
        or any(ch in {"/", "\\", ":"} or ord(ch) < 32 or 127 <= ord(ch) <= 159 for ch in prefix)
    ):
        raise TestTempRootError(
            f"Invalid test directory prefix (must be a single path component): {prefix!r}"
        )


def _is_within_project(path: Path) -> bool:
    try:
        path.relative_to(PROJECT_ROOT)
    except ValueError:
        return False
    return True


def prepare_test_temp_root(
    root: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return a verified, repository-contained temp root without using TEMP/TMP."""

    environment = os.environ if environ is None else environ
    configured = root or environment.get(TEMP_ROOT_ENV) or DEFAULT_TEMP_ROOT
    candidate = Path(configured).expanduser().resolve()
    if not _is_within_project(candidate):
        raise TestTempRootError(
            f"{TEMP_ROOT_ENV} must stay inside the Content Studio repository: {candidate}"
        )

    try:
        candidate.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=candidate, prefix="write-probe-", delete=True):
            pass
    except OSError as exc:
        raise TestTempRootError(
            f"Content Studio test temp root is not writable: {candidate}"
        ) from exc
    return candidate


@contextmanager
def isolated_test_directory(
    prefix: str,
    *,
    root: str | Path | None = None,
) -> Iterator[Path]:
    """Create an isolated directory under the explicit local test temp root."""

    _validate_prefix(prefix)
    parent = prepare_test_temp_root(root)
    temporary: Path | None = None
    for _ in range(16):
        candidate = parent / f"{prefix}-{os.getpid()}-{uuid.uuid4().hex}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        except OSError as exc:
            raise TestTempRootError(
                f"Could not create an isolated test directory under: {parent}"
            ) from exc
        temporary = candidate
        break
    if temporary is None:
        raise TestTempRootError(
            f"Could not allocate a unique test directory under: {parent}"
        )

    try:
        yield temporary
    finally:
        try:
            shutil.rmtree(temporary)
        except OSError as exc:
            raise TestTempRootError(
                f"Could not clean isolated test directory: {temporary}"
            ) from exc
