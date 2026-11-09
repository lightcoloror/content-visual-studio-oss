from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import temp_workspace
from temp_workspace import (
    DEFAULT_TEMP_ROOT,
    PROJECT_ROOT,
    TestTempRootError,
    isolated_test_directory,
    prepare_test_temp_root,
)


class TestTempWorkspaceTests(unittest.TestCase):
    def test_default_root_is_writable_and_repository_contained(self) -> None:
        root = prepare_test_temp_root()
        self.assertTrue(root.is_relative_to(PROJECT_ROOT))
        with isolated_test_directory("writable") as work:
            work.joinpath("probe.txt").write_text("ok", encoding="utf-8")
            self.assertTrue(work.is_relative_to(root))
            self.assertTrue(work.is_dir())
        self.assertFalse(work.exists())

    def test_concurrent_and_repeated_runs_are_isolated(self) -> None:
        def run(index: int) -> tuple[Path, str]:
            with isolated_test_directory("parallel") as work:
                value = f"worker-{index}"
                work.joinpath("worker.txt").write_text(value, encoding="utf-8")
                return work, work.joinpath("worker.txt").read_text(encoding="utf-8")

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(run, range(8)))
        paths = [path for path, _ in results]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual([value for _, value in results], [f"worker-{i}" for i in range(8)])
        self.assertTrue(all(not path.exists() for path in paths))

    def test_exception_still_cleans_current_directory(self) -> None:
        work: Path | None = None
        with self.assertRaisesRegex(RuntimeError, "intentional"):
            with isolated_test_directory("exception") as work:
                raise RuntimeError("intentional")
        self.assertIsNotNone(work)
        self.assertFalse(work.exists())

    def test_residue_does_not_affect_next_run(self) -> None:
        sandbox = DEFAULT_TEMP_ROOT / f"residue-fixture-{uuid.uuid4().hex}"
        residue = sandbox / "stale-sibling"
        try:
            residue.mkdir(parents=True)
            residue.joinpath("marker.txt").write_text("stale", encoding="utf-8")
            with isolated_test_directory("fresh", root=sandbox) as work:
                self.assertNotEqual(work, residue)
                self.assertTrue(residue.is_dir())
            self.assertFalse(work.exists())
            self.assertTrue(residue.is_dir())
        finally:
            shutil.rmtree(sandbox, ignore_errors=False)

    def test_system_temp_lookup_is_not_required(self) -> None:
        with patch.object(
            tempfile,
            "gettempdir",
            side_effect=PermissionError("system temp unavailable"),
        ):
            with isolated_test_directory("no-system-temp") as work:
                self.assertTrue(work.is_dir())

    def test_unwritable_or_unsafe_override_fails_with_controlled_error(self) -> None:
        unsafe = Path.home() / "outside-content-studio"
        with self.assertRaisesRegex(TestTempRootError, "must stay inside"):
            prepare_test_temp_root(unsafe)

        marker = DEFAULT_TEMP_ROOT / f"not-a-directory-{uuid.uuid4().hex}"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("file", encoding="utf-8")
        try:
            with self.assertRaisesRegex(TestTempRootError, "not writable"):
                prepare_test_temp_root(marker)
        finally:
            marker.unlink()

    def test_invalid_prefix_is_rejected_before_filesystem_action(self) -> None:
        invalid_prefixes: list[object] = [
            "",
            None,
            123,
            b"bytes",
            Path("component"),
            ".",
            "..",
            "../escape",
            "..\\escape",
            "dir/subdir",
            "dir\\subdir",
            "/absolute",
            "\\absolute",
            "C:",
            "C:/temp",
            "\\\\server\\share",
            "name:stream",
            "name\x00nul",
            "name\x01control",
            "name\x1fcontrol",
            "name\x7fcontrol",
            "name\x85control",
        ]
        for prefix in invalid_prefixes:
            with self.subTest(prefix=prefix):
                with patch.object(
                    temp_workspace,
                    "prepare_test_temp_root",
                    side_effect=AssertionError(
                        "prepare_test_temp_root must not be called for an invalid prefix"
                    ),
                ) as mocked_prepare:
                    with self.assertRaisesRegex(TestTempRootError, "single path component"):
                        with isolated_test_directory(prefix):
                            pass
                    mocked_prepare.assert_not_called()

    def test_chinese_and_hyphen_prefix_works_and_is_cleaned(self) -> None:
        root = prepare_test_temp_root()
        with isolated_test_directory("测试-工作-01", root=root) as work:
            self.assertTrue(work.is_relative_to(root))
            self.assertTrue(work.name.startswith("测试-工作-01-"))
            marker = work.joinpath("标记.txt")
            marker.write_text("ok", encoding="utf-8")
            self.assertEqual(marker.read_text(encoding="utf-8"), "ok")
        self.assertFalse(work.exists())


if __name__ == "__main__":
    unittest.main()
