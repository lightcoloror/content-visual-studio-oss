"""Synthetic contract tests for check_shared_visual_lock.py.

Everything here is invented test data under a TemporaryDirectory. No real
studio package, brand asset, network or private workspace is read. The three
previously observed false-pass shapes are carried forward as regressions:

* an empty ``files`` map (and hash-matching empty member files),
* a wrong lock ``schema_version`` / package identity,
* a ``../`` reference whose invented outside bytes have a matching hash.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_SYNTHETIC_STUDIO_TMP: tempfile.TemporaryDirectory | None = None


def _ensure_studio_paths() -> None:
    """Use the host studio_paths when present; otherwise use a synthetic one."""

    global _SYNTHETIC_STUDIO_TMP
    try:
        import studio_paths  # noqa: F401

        return
    except ImportError:
        pass
    if "studio_paths" in sys.modules:
        return
    _SYNTHETIC_STUDIO_TMP = tempfile.TemporaryDirectory(prefix="synthetic-studio-paths-")
    module = types.ModuleType("studio_paths")
    module.__file__ = str(_SCRIPTS / "studio_paths.py")
    module.HERE = _SCRIPTS
    module.SOURCE_ROOT = _SCRIPTS.parent
    module.STUDIO_ROOT = Path(_SYNTHETIC_STUDIO_TMP.name)
    module.HUMAN_VOICE_ROOT = module.STUDIO_ROOT / "skills" / "human-voice-editor"
    module.research_schema_path = lambda: module.STUDIO_ROOT / "schemas" / "research-output.schema.json"
    sys.modules["studio_paths"] = module


_ensure_studio_paths()

import check_shared_visual_lock as lock_module  # noqa: E402

REQUIRED_REFS = sorted(lock_module.REQUIRED_SOURCE_REFS)
LOCK_SCHEMA = "shared-visual-design-system-lock.v1"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _document_bytes(ref: str) -> bytes:
    return json.dumps({"synthetic_test_only": True, "member_ref": ref}, sort_keys=True).encode("utf-8")


class LockFixture:
    """A synthetic source/projection pair plus its synthetic lock."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.source = base / "source"
        self.projection = base / "projection"
        for root in (self.source, self.projection):
            (root / "schemas").mkdir(parents=True, exist_ok=True)
            (root / "contracts").mkdir(parents=True, exist_ok=True)
        self.lock_path = self.projection / lock_module.LOCK_FILENAME
        for ref in REQUIRED_REFS:
            self.write_member(ref, _document_bytes(ref))
        self.baseline_lock = self.make_lock()
        self.write_lock(self.baseline_lock)

    def make_lock(self) -> dict:
        files = {}
        for ref in REQUIRED_REFS:
            files[ref] = {
                "sha256": _sha((self.source / ref).read_bytes()),
                "projected_ref": ref,
            }
        return {
            "schema_version": LOCK_SCHEMA,
            "package": "@lightcolor/shared-visual-design-system",
            "consumer": "content-visual-studio",
            "package_version": "1.1.0",
            "files": files,
        }

    def write_member(self, ref: str, data: bytes) -> None:
        for root in (self.source, self.projection):
            path = root / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def write_lock(self, lock: dict) -> None:
        self.lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")

    def validate(self, shared_root=None) -> list[str]:
        root = self.source if shared_root is None else shared_root
        return lock_module.validate_lock(
            root,
            lock_path=self.lock_path,
            projection_root=self.projection,
        )


class LockContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="shared-visual-lock-test-")
        self.base = Path(self._tmp.name)
        self.fixture = LockFixture(self.base)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -- positive -----------------------------------------------------------

    def test_valid_declared_snapshot_passes(self) -> None:
        self.assertEqual(self.fixture.validate(), [])

    def test_main_help_returns_zero_without_runtime(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            code = lock_module.main(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("usage", output.getvalue().lower())

    def test_main_passes_and_reports_findings(self) -> None:
        original_lock = lock_module.LOCK_PATH
        original_vendor = lock_module.VENDOR_ROOT
        try:
            lock_module.LOCK_PATH = self.fixture.lock_path
            lock_module.VENDOR_ROOT = self.fixture.projection
            output = StringIO()
            with redirect_stdout(output):
                code = lock_module.main(["--shared-root", str(self.fixture.source)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "pass")

            lock = copy.deepcopy(self.fixture.baseline_lock)
            lock["files"] = {}
            self.fixture.write_lock(lock)
            output = StringIO()
            with redirect_stdout(output):
                code = lock_module.main(["--shared-root=" + str(self.fixture.source)])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output.getvalue())["status"], "fail")
        finally:
            lock_module.LOCK_PATH = original_lock
            lock_module.VENDOR_ROOT = original_vendor

    def test_main_refuses_unknown_argument(self) -> None:
        with redirect_stderr(StringIO()), redirect_stdout(StringIO()):
            self.assertEqual(lock_module.main(["--bogus"]), 2)
        with redirect_stderr(StringIO()), redirect_stdout(StringIO()):
            self.assertEqual(lock_module.main(["--shared-root"]), 2)

    # -- false-pass counterexamples ----------------------------------------

    def test_empty_files_map_is_not_a_pass(self) -> None:
        lock = copy.deepcopy(self.fixture.baseline_lock)
        lock["files"] = {}
        self.fixture.write_lock(lock)
        errors = self.fixture.validate()
        self.assertIn("shared visual lock requires a non-empty files map", errors)

    def test_hash_matching_empty_member_files_are_not_a_pass(self) -> None:
        for ref in REQUIRED_REFS:
            self.fixture.write_member(ref, b"")
        lock = self.fixture.make_lock()
        for ref in REQUIRED_REFS:
            lock["files"][ref]["sha256"] = _sha(b"")
        self.fixture.write_lock(lock)
        errors = self.fixture.validate()
        self.assertTrue(any(error.startswith("empty shared projection") for error in errors))
        self.assertTrue(any(error.startswith("empty shared source") for error in errors))

    def test_wrong_lock_identity_fails(self) -> None:
        cases = [
            ("schema_version", "shared-visual-design-system-lock.v2"),
            ("package", "@example.invalid/not-the-shared-system"),
            ("consumer", "another-consumer"),
            ("package_version", "9.9.9"),
        ]
        for field, value in cases:
            with self.subTest(field=field):
                lock = copy.deepcopy(self.fixture.baseline_lock)
                lock[field] = value
                self.fixture.write_lock(lock)
                self.assertTrue(self.fixture.validate())

    def test_escape_reference_with_matching_outside_hash_never_reads_outside(self) -> None:
        outside = self.base / "outside" / "invented.json"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_bytes(b'{"invented": "outside the declared root"}')
        lock = copy.deepcopy(self.fixture.baseline_lock)
        lock["files"]["../outside/invented.json"] = {
            "sha256": _sha(outside.read_bytes()),
            "projected_ref": "schemas/global-visual-context.v1.schema.json",
        }
        self.fixture.write_lock(lock)

        recorded: list[Path] = []
        real_read = lock_module._read_bytes

        def recording(path):
            recorded.append(Path(path))
            return real_read(path)

        with mock.patch.object(lock_module, "_read_bytes", side_effect=recording):
            errors = self.fixture.validate()
        self.assertTrue(any("unsafe shared reference" in error for error in errors))
        self.assertNotIn(outside.resolve(), recorded)

    # -- required members and drift ----------------------------------------

    def test_each_required_member_is_required(self) -> None:
        for ref in REQUIRED_REFS:
            with self.subTest(ref=ref):
                lock = copy.deepcopy(self.fixture.baseline_lock)
                del lock["files"][ref]
                self.fixture.write_lock(lock)
                errors = self.fixture.validate()
                self.assertIn("shared visual lock is missing required contract members", errors)

    def test_all_required_members_are_hash_bound(self) -> None:
        for ref in REQUIRED_REFS:
            with self.subTest(ref=ref):
                baseline = (self.fixture.source / ref).read_bytes()
                self.fixture.write_member(ref, baseline + b" ")
                errors = self.fixture.validate()
                self.assertIn("shared source drift: " + ref, errors)
                self.assertIn("shared projection drift: " + ref, errors)
                self.fixture.write_member(ref, baseline)

    def test_missing_and_directory_members_fail(self) -> None:
        ref = "contracts/icon-registry.v1.json"
        original = (self.fixture.source / ref).read_bytes()

        (self.fixture.source / ref).unlink()
        errors = self.fixture.validate()
        self.assertTrue(any("missing shared source" in error for error in errors))

        self.fixture.write_member(ref, original)
        projection_path = self.fixture.projection / ref
        projection_path.unlink()
        projection_path.mkdir()
        errors = self.fixture.validate()
        self.assertTrue(any("missing shared projection" in error for error in errors))

        projection_path.rmdir()
        self.fixture.write_member(ref, original)
        self.assertEqual(self.fixture.validate(), [])

    def test_invalid_lock_entries_fail_closed(self) -> None:
        cases = []
        lock = copy.deepcopy(self.fixture.baseline_lock)
        lock["files"][REQUIRED_REFS[0]] = "not-an-object"
        cases.append(lock)

        lock = copy.deepcopy(self.fixture.baseline_lock)
        lock["files"][REQUIRED_REFS[0]] = {"sha256": "A" * 64, "projected_ref": REQUIRED_REFS[0]}
        cases.append(lock)

        lock = copy.deepcopy(self.fixture.baseline_lock)
        lock["files"][REQUIRED_REFS[0]] = {"sha256": "", "projected_ref": REQUIRED_REFS[0]}
        cases.append(lock)

        lock = copy.deepcopy(self.fixture.baseline_lock)
        lock["files"][REQUIRED_REFS[0]] = {"projected_ref": REQUIRED_REFS[0]}
        cases.append(lock)

        for index, lock in enumerate(cases):
            with self.subTest(case=index):
                self.fixture.write_lock(lock)
                errors = self.fixture.validate()
                self.assertTrue(
                    any("invalid shared file hash/entry" in error for error in errors),
                    errors,
                )

    # -- path containment ---------------------------------------------------

    def test_noncanonical_source_references_are_refused(self) -> None:
        bad_refs = [
            "",
            "./schemas/global-visual-context.v1.schema.json",
            "schemas//global-visual-context.v1.schema.json",
            "contracts/../contracts/guidelines.v1.json",
            "/invented.json",
            "C:/invented.json",
            "contracts\\guidelines.v1.json",
        ]
        for bad_ref in bad_refs:
            with self.subTest(ref=bad_ref):
                lock = copy.deepcopy(self.fixture.baseline_lock)
                lock["files"][bad_ref] = {
                    "sha256": "0" * 64,
                    "projected_ref": "schemas/global-visual-context.v1.schema.json",
                }
                self.fixture.write_lock(lock)
                errors = self.fixture.validate()
                self.assertTrue(
                    any("unsafe shared reference" in error for error in errors), errors
                )

    def test_outside_projected_references_are_refused(self) -> None:
        for bad_projected in ("", "../invented.json", "/invented.json", "C:/invented.json"):
            with self.subTest(projected_ref=bad_projected):
                lock = copy.deepcopy(self.fixture.baseline_lock)
                lock["files"]["schemas/extra.json"] = {
                    "sha256": "0" * 64,
                    "projected_ref": bad_projected,
                }
                self.fixture.write_lock(lock)
                errors = self.fixture.validate()
                self.assertTrue(
                    any("unsafe shared reference" in error for error in errors), errors
                )

    def test_symlink_escape_is_refused_before_read(self) -> None:
        outside = self.base / "outside" / "victim.json"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_bytes(b'{"victim": true}')
        link = self.fixture.source / "schemas" / "escape.json"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is not available in this environment")

        lock = copy.deepcopy(self.fixture.baseline_lock)
        lock["files"]["schemas/escape.json"] = {
            "sha256": _sha(outside.read_bytes()),
            "projected_ref": "schemas/global-visual-context.v1.schema.json",
        }
        self.fixture.write_lock(lock)

        recorded: list[Path] = []
        real_read = lock_module._read_bytes

        def recording(path):
            recorded.append(Path(path))
            return real_read(path)

        with mock.patch.object(lock_module, "_read_bytes", side_effect=recording):
            errors = self.fixture.validate()
        self.assertTrue(any("resolves outside" in error for error in errors), errors)
        self.assertNotIn(outside.resolve(), recorded)

    # -- explicit roots and lock file failures ------------------------------

    def test_explicit_source_root_is_required(self) -> None:
        with mock.patch.dict(os.environ, {lock_module.SOURCE_ROOT_ENV: ""}):
            errors = lock_module.validate_lock(
                None,
                lock_path=self.fixture.lock_path,
                projection_root=self.fixture.projection,
            )
        self.assertTrue(any("explicit shared source root required" in error for error in errors))

    def test_unavailable_source_root_fails(self) -> None:
        errors = lock_module.validate_lock(
            self.base / "missing-root",
            lock_path=self.fixture.lock_path,
            projection_root=self.fixture.projection,
        )
        self.assertIn("shared visual source root is unavailable", errors)

    def test_missing_lock_file_fails(self) -> None:
        self.fixture.lock_path.unlink()
        self.assertIn("shared visual design lock is missing", self.fixture.validate())

    def test_unreadable_or_non_object_lock_fails(self) -> None:
        self.fixture.lock_path.write_text("{not json", encoding="utf-8")
        self.assertTrue(
            any("unreadable" in error for error in self.fixture.validate())
        )
        self.fixture.lock_path.write_text("[]", encoding="utf-8")
        self.assertIn("shared visual design lock must be an object", self.fixture.validate())

    # -- lock-pinned member consumption -------------------------------------

    def test_locked_member_loader_pins_exact_buffer_and_refuses_unlocked(self) -> None:
        fixture = self.fixture
        ref = "contracts/guidelines.v1.json"
        data, declared = lock_module.load_locked_member(
            fixture.source,
            ref,
            lock_path=fixture.lock_path,
            projection_root=fixture.projection,
        )
        self.assertEqual(data, (fixture.source / ref).read_bytes())
        self.assertEqual(_sha(data), declared)

        fixture.write_member("contracts/unlocked.json", b'{"version": "1.0.0"}')
        with self.assertRaises(ValueError) as caught:
            lock_module.load_locked_member(
                fixture.source,
                "contracts/unlocked.json",
                lock_path=fixture.lock_path,
                projection_root=fixture.projection,
            )
        self.assertIn("not declared", str(caught.exception))

        source_path = fixture.source / ref
        original_source = source_path.read_bytes()
        source_path.write_bytes(b'{"version": "1.0.0"}')
        with self.assertRaises(ValueError) as caught:
            lock_module.load_locked_member(
                fixture.source,
                ref,
                lock_path=fixture.lock_path,
                projection_root=fixture.projection,
            )
        self.assertIn("locked source hash mismatch", str(caught.exception))

        source_path.write_bytes(original_source)
        projection_path = fixture.projection / ref
        original_projection = projection_path.read_bytes()
        projection_path.write_bytes(b'{"version": "1.0.0"}')
        with self.assertRaises(ValueError) as caught:
            lock_module.load_locked_member(
                fixture.source,
                ref,
                lock_path=fixture.lock_path,
                projection_root=fixture.projection,
            )
        self.assertIn("locked projection hash mismatch", str(caught.exception))
        projection_path.write_bytes(original_projection)

        data, declared = lock_module.load_locked_member(
            fixture.source,
            ref,
            lock_path=fixture.lock_path,
            projection_root=fixture.projection,
        )
        self.assertEqual(declared, _sha(data))

    def test_locked_member_loader_allows_custom_locked_member(self) -> None:
        fixture = self.fixture
        custom = b'{"version": "2.0.0", "synthetic": true}'
        fixture.write_member("contracts/custom.json", custom)
        lock = copy.deepcopy(fixture.baseline_lock)
        lock["files"]["contracts/custom.json"] = {
            "sha256": _sha(custom),
            "projected_ref": "contracts/custom.json",
        }
        fixture.write_lock(lock)
        data, declared = lock_module.load_locked_member(
            fixture.source,
            "contracts/custom.json",
            lock_path=fixture.lock_path,
            projection_root=fixture.projection,
        )
        self.assertEqual(data, custom)
        self.assertEqual(declared, _sha(custom))
        self.assertEqual(fixture.validate(), [])


if __name__ == "__main__":
    unittest.main()
