"""Isolated synthetic tests for the public render-artifact validation source.

The suite covers only the two changed boundaries: public root resolution and the
lazy held-data-backend import. It uses in-memory registry fixtures and does not
exercise real schema validation, hashing, media QA, renderer execution or the
original 18-test integration suite.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Public sibling scripts and test-support dependencies are prerequisites: a
# missing import fails explicitly instead of being skipped.
import render_artifact_validation as validation  # noqa: E402


BACKEND = "render_data_explanations"

_REGISTRIES = {
    "renderer-registry.v1.json": {
        "renderers": {
            "html-playwright": {"enabled": True, "formats": ["html"]},
            "lieflat-charts": {"enabled": True, "formats": ["svg"]},
            "ppt-master": {
                "enabled": True,
                "formats": ["pptx"],
                "operations": {
                    "allowed": ["generate", "template-fill", "data-native"],
                },
                "protocol": "pinned",
                "external_provider_required": False,
                "remote_downloads_enabled": False,
                "visual_validation_required": True,
            },
        }
    },
    "layout-intents.v1.json": {"intents": {}},
}


def _fake_load_json(path: Path):
    try:
        return _REGISTRIES[path.name]
    except KeyError as exc:
        raise AssertionError(f"unexpected registry read: {path}") from exc


class _RecordingFinder(importlib.abc.MetaPathFinder):
    def __init__(self) -> None:
        self.backend_requests: list[str] = []

    def find_spec(self, fullname, path=None, target=None):
        if fullname == BACKEND or fullname.startswith(f"{BACKEND}."):
            self.backend_requests.append(fullname)
        return None


class _MissingBackendFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == BACKEND:
            raise ModuleNotFoundError(f"No module named {BACKEND!r}", name=BACKEND)
        return None


class _RaisingLoader(importlib.abc.Loader):
    def __init__(self, error: BaseException) -> None:
        self.error = error

    def create_module(self, spec):
        return None

    def exec_module(self, module) -> None:
        raise self.error


class _FakeBackendFinder(importlib.abc.MetaPathFinder):
    def __init__(self, error: BaseException) -> None:
        self.error = error

    def find_spec(self, fullname, path=None, target=None):
        if fullname == BACKEND:
            return importlib.util.spec_from_loader(BACKEND, _RaisingLoader(self.error))
        return None


@contextmanager
def _backend_import_state(finder: importlib.abc.MetaPathFinder):
    saved = sys.modules.pop(BACKEND, None)
    sys.meta_path.insert(0, finder)
    try:
        yield finder
    finally:
        sys.meta_path.remove(finder)
        sys.modules.pop(BACKEND, None)
        if saved is not None:
            sys.modules[BACKEND] = saved


class IsolatedCandidateBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.item_path = Path(__file__).resolve()

    def _validate(self, artifact: dict) -> list[tuple[str, str]]:
        item = {
            "content_id": "synthetic-candidate",
            "visual": {"render_artifacts": [artifact]},
        }
        with mock.patch.object(validation, "_load_json", side_effect=_fake_load_json), \
             mock.patch.object(validation, "validate_budget_registry_coverage", return_value=[]), \
             mock.patch.object(validation, "required_hard_checks", return_value=None):
            return validation.validate_render_artifacts(item, self.item_path)

    @staticmethod
    def _artifact(**overrides) -> dict:
        artifact = {
            "artifact_id": "candidate-artifact",
            "renderer": "html-playwright",
            "format": "html",
            "status": "planned",
        }
        artifact.update(overrides)
        return artifact

    # public root boundary: portability only, not path confinement
    def test_resolve_local_ref_prefers_item_directory(self) -> None:
        resolved = validation.resolve_local_ref(Path(__file__).name, self.item_path)
        self.assertEqual(resolved, Path(__file__).resolve())

    def test_resolve_local_ref_keeps_absolute_and_parent_traversal(self) -> None:
        absolute = Path(__file__).resolve()
        self.assertEqual(validation.resolve_local_ref(str(absolute), self.item_path), absolute)
        relative_up = f"../{absolute.parent.name}/{absolute.name}"
        self.assertEqual(validation.resolve_local_ref(relative_up, self.item_path), absolute)

    def test_resolve_local_ref_uses_portability_fallback(self) -> None:
        resolved = validation.resolve_local_ref("synthetic-missing-ref.txt", self.item_path)
        self.assertEqual(resolved, (validation.STUDIO_ROOT / "synthetic-missing-ref.txt").resolve())

    # lazy held-backend import boundary
    def test_module_load_does_not_import_held_backend(self) -> None:
        finder = _RecordingFinder()
        with _backend_import_state(finder):
            reloaded = importlib.reload(validation)
        self.assertEqual(finder.backend_requests, [])
        self.assertTrue(callable(reloaded.validate_render_artifacts))

    def test_non_data_artifact_does_not_import_held_backend(self) -> None:
        finder = _RecordingFinder()
        with _backend_import_state(finder):
            messages = [message for _, message in self._validate(self._artifact())]
        self.assertEqual(messages, [])
        self.assertEqual(finder.backend_requests, [])

    def test_ppt_master_generate_does_not_import_held_backend(self) -> None:
        finder = _RecordingFinder()
        with _backend_import_state(finder):
            messages = [message for _, message in self._validate(
                self._artifact(
                    renderer="ppt-master",
                    format="pptx",
                    renderer_options={
                        "operation": "generate",
                        "ppt_master_protocol": "pinned",
                    },
                )
            )]
        self.assertEqual(finder.backend_requests, [])
        self.assertTrue(any("exactly one structured brief input" in message for message in messages))

    def test_lieflat_charts_missing_direct_backend_returns_validation_error(self) -> None:
        with _backend_import_state(_MissingBackendFinder()):
            messages = [message for _, message in self._validate(
                self._artifact(renderer="lieflat-charts", format="svg")
            )]
        self.assertTrue(messages)
        self.assertTrue(any(BACKEND in message for message in messages))

    def test_ppt_master_data_native_missing_direct_backend_returns_validation_error(self) -> None:
        with _backend_import_state(_MissingBackendFinder()):
            messages = [message for _, message in self._validate(
                self._artifact(
                    renderer="ppt-master",
                    format="pptx",
                    renderer_options={
                        "operation": "data-native",
                        "ppt_master_protocol": "pinned",
                    },
                )
            )]
        self.assertTrue(messages)
        self.assertTrue(any(BACKEND in message for message in messages))

    def test_transitive_missing_dependency_propagates(self) -> None:
        error = ModuleNotFoundError("No module named 'lieflat.chart'", name="lieflat.chart")
        with _backend_import_state(_FakeBackendFinder(error)):
            with self.assertRaises(ModuleNotFoundError) as caught:
                self._validate(self._artifact(renderer="lieflat-charts", format="svg"))
        self.assertEqual(caught.exception.name, "lieflat.chart")

    def test_backend_runtime_error_propagates(self) -> None:
        with _backend_import_state(_FakeBackendFinder(RuntimeError("backend exploded"))):
            with self.assertRaises(RuntimeError):
                self._validate(self._artifact(renderer="lieflat-charts", format="svg"))


if __name__ == "__main__":
    unittest.main(failfast=True)
