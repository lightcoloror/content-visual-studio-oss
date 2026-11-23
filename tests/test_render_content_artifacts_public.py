#!/usr/bin/env python3
"""Isolated public-boundary tests for ``render_content_artifacts.py``.

Run directly, for example::

    python -X utf8 -B tests/test_render_content_artifacts_public.py

The harness is intentionally fail-fast and dependency-honest: if a real public
prerequisite is absent, the import fails and this file reports a failure rather
than skipping. Everything here is synthetic and isolated. These tests do not
render artifacts, run subprocess renderers, start a browser, call a service, or
write output files, and they are not evidence of full-suite integration.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path

CANDIDATE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "render_content_artifacts.py"
HELD_BACKEND = "render_data_explanations"
EXPECTED_DATA_SPEC_LITERAL = "data-explanation-chart-spec.v1"


class _HeldBackendImportFinder:
    """Isolated meta-path hook that observes only the held backend.

    It never records the candidate module being loaded or reloaded and never
    injects or fakes a production module; it only simulates absence or a broken
    held backend for boundary assertions.
    """

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.attempts: list[str] = []

    def find_spec(self, fullname: str, path: object = None, target: object = None) -> object:
        if fullname != HELD_BACKEND and not fullname.startswith(HELD_BACKEND + "."):
            return None
        self.attempts.append(fullname)
        if self.mode == "record":
            return None
        if self.mode == "missing":
            raise ModuleNotFoundError(f"No module named {fullname!r}", name=fullname)
        if self.mode == "transitive":
            raise ModuleNotFoundError(
                "No module named 'isolated_transitive_dependency'",
                name="isolated_transitive_dependency",
            )
        if self.mode == "broken":
            raise RuntimeError("held data backend failed while importing")
        raise AssertionError(f"unknown finder mode {self.mode!r}")


@contextmanager
def _simulated_backend(mode: str):
    """Temporarily hide any cached held backend and install the isolated finder."""
    cached = {
        name: module
        for name, module in list(sys.modules.items())
        if name == HELD_BACKEND or name.startswith(HELD_BACKEND + ".")
    }
    for name in cached:
        del sys.modules[name]
    finder = _HeldBackendImportFinder(mode)
    sys.meta_path.insert(0, finder)
    try:
        yield finder
    finally:
        sys.meta_path.remove(finder)
        for name in [
            name
            for name in sys.modules
            if name == HELD_BACKEND or name.startswith(HELD_BACKEND + ".")
        ]:
            del sys.modules[name]
        sys.modules.update(cached)


@contextmanager
def _environment(name: str, value: str | None):
    previous = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


@contextmanager
def _patched(module: object, **attributes: object):
    sentinel = object()
    previous = {name: getattr(module, name, sentinel) for name in attributes}
    for name, value in attributes.items():
        setattr(module, name, value)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is sentinel:
                delattr(module, name)
            else:
                setattr(module, name, value)


def _load_candidate() -> object:
    spec = importlib.util.spec_from_file_location("render_content_artifacts_public", CANDIDATE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load candidate module from {CANDIDATE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _candidate_source(module: object) -> str:
    return Path(module.__file__).read_text(encoding="utf-8")


def test_module_load_does_not_import_held_backend(module: object, finder: _HeldBackendImportFinder) -> None:
    assert finder.attempts == [], f"module load must not touch the held backend: {finder.attempts}"
    assert module.DATA_SPEC_VERSION == EXPECTED_DATA_SPEC_LITERAL


def test_held_backend_import_is_function_local(module: object, finder: _HeldBackendImportFinder) -> None:
    tree = ast.parse(_candidate_source(module))
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert node.module != HELD_BACKEND, "held backend must not be imported at module level"
        elif isinstance(node, ast.Import):
            assert all(alias.name != HELD_BACKEND for alias in node.names)
    data_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_render_data_explanation"
    ]
    assert len(data_functions) == 1, "the data-explanation renderer must be preserved exactly once"
    function = data_functions[0]
    held_imports = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.ImportFrom) and node.module == HELD_BACKEND
    ]
    assert held_imports, "the held backend import must live inside the data-explanation renderer"
    assert function.lineno <= held_imports[0].lineno <= function.end_lineno


def test_metadata_uses_existing_literal_not_backend(module: object, finder: _HeldBackendImportFinder) -> None:
    source = _candidate_source(module)
    tree = ast.parse(source)
    assignments = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "DATA_SPEC_VERSION" for target in node.targets)
    ]
    assert len(assignments) == 1, "module-level DATA_SPEC_VERSION must be the metadata literal"
    literal = assignments[0].value
    assert isinstance(literal, ast.Constant) and literal.value == EXPECTED_DATA_SPEC_LITERAL
    assert finder.attempts == [], "metadata classification must not import the held backend"


def test_receipt_evidence_metadata_defaults(module: object, finder: _HeldBackendImportFinder) -> None:
    payloads = {
        "chart-spec.json": {
            "schema_version": module.DATA_SPEC_VERSION,
            "evidence_binding_version": "evidence-binding.v1",
            "checked_at": "2026-11-01T08:00:00+08:00",
            "source_refs": [
                {"ref": "evidence/a.md"},
                {
                    "ref": "evidence/b.md",
                    "evidence_id": "ev-2",
                    "evidence_status": "verified",
                    "label": "B",
                },
            ],
        },
        "visual-spec.json": {
            "schema_version": "data-visual-spec.v1",
            "updated_at": "2026-11-05T09:00:00+08:00",
            "sources": [{"ref": "data/c.csv", "source_id": "src-1"}],
        },
    }

    def fake_resolve(ref: str, item_path: Path) -> Path:
        return Path(item_path).parent / str(ref)

    def fake_load(path: Path) -> dict:
        return payloads[Path(path).name]

    artifact = {"input_refs": ["chart-spec.json", "visual-spec.json"]}
    with _patched(module, resolve_local_ref=fake_resolve, _load_json=fake_load):
        evidence_refs, checked_at, contract_versions = module._receipt_evidence_metadata(
            {"schema_version": "0.2"}, CANDIDATE_PATH, artifact
        )

    assert contract_versions == {
        "content_item": "0.2",
        "render_receipt": "render-receipt.v1",
        "data_visual_spec": "data-visual-spec.v1",
        "chart_spec": module.DATA_SPEC_VERSION,
        "evidence_binding": "evidence-binding.v1",
    }
    assert evidence_refs == [
        {
            "evidence_id": "source-1",
            "ref": "evidence/a.md",
            "evidence_status": "unverified",
            "label": "",
        },
        {
            "evidence_id": "ev-2",
            "ref": "evidence/b.md",
            "evidence_status": "verified",
            "label": "B",
        },
        {
            "evidence_id": "src-1",
            "ref": "data/c.csv",
            "evidence_status": "unknown",
            "label": "",
        },
    ]
    assert checked_at == "2026-11-05T09:00:00+08:00"
    assert finder.attempts == [], "receipt metadata classification must stay backend-free"


def test_missing_backend_rejects_before_output(module: object, finder: _HeldBackendImportFinder) -> None:
    resolved: list[str] = []

    def spy_resolve(ref: str, item_path: Path) -> Path:
        resolved.append(str(ref))
        return Path(item_path).parent / str(ref)

    artifact = {"input_refs": ["chart-spec.json"], "ref": "out.svg", "format": "svg"}
    with _simulated_backend("missing"), _patched(module, resolve_local_ref=spy_resolve):
        try:
            module._render_data_explanation({}, CANDIDATE_PATH, artifact, {})
        except module.ArtifactError as exc:
            assert HELD_BACKEND in str(exc)
        else:
            raise AssertionError("missing held backend must raise ArtifactError")
    assert resolved == [], "missing backend must reject before resolving inputs or outputs"


def test_transitive_missing_error_remains_visible(module: object, finder: _HeldBackendImportFinder) -> None:
    artifact = {"input_refs": ["chart-spec.json"], "ref": "out.svg", "format": "svg"}
    with _simulated_backend("transitive"):
        try:
            module._render_data_explanation({}, CANDIDATE_PATH, artifact, {})
        except ModuleNotFoundError as exc:
            assert exc.name == "isolated_transitive_dependency"
        else:
            raise AssertionError("transitive ModuleNotFoundError must propagate")


def test_broken_backend_error_remains_visible(module: object, finder: _HeldBackendImportFinder) -> None:
    artifact = {"input_refs": ["chart-spec.json"], "ref": "out.svg", "format": "svg"}
    with _simulated_backend("broken"):
        try:
            module._render_data_explanation({}, CANDIDATE_PATH, artifact, {})
        except RuntimeError as exc:
            assert "held data backend" in str(exc)
        else:
            raise AssertionError("broken backend error must propagate")


def test_runtime_helpers_require_explicit_environment(module: object, finder: _HeldBackendImportFinder) -> None:
    candidate_file = Path(module.__file__).resolve()
    helpers = (
        ("PLAYWRIGHT_CHROMIUM_EXECUTABLE", module._discover_chromium),
        ("CODEX_PRIMARY_RUNTIME_PYTHON", module._discover_primary_runtime_python),
    )
    for env_name, helper in helpers:
        with _environment(env_name, str(candidate_file)):
            assert helper() == candidate_file
        with _environment(env_name, os.path.relpath(candidate_file, Path.cwd())):
            assert helper() == candidate_file
        with _environment(env_name, None):
            try:
                helper()
            except module.ArtifactError as exc:
                assert env_name in str(exc)
            else:
                raise AssertionError(f"{env_name} absence must fail closed with ArtifactError")
        with _environment(env_name, str(candidate_file) + ".absent"):
            try:
                helper()
            except module.ArtifactError:
                pass
            else:
                raise AssertionError(f"{env_name} must reject a missing explicit file")


def test_public_root_contract(module: object, finder: _HeldBackendImportFinder) -> None:
    assert module.SCHEMA_PATH == module.STUDIO_ROOT / "schemas" / "content-item.schema.json"
    assert module.RENDERER_REGISTRY_PATH == module.STUDIO_ROOT / "config" / "renderer-registry.v1.json"
    non_data = module._global_visual_data_status(
        {"layout_intent": "editorial-text", "output_family": "editorial-text"}, CANDIDATE_PATH
    )
    assert non_data == {"normalized_spec_valid": True, "message": "Artifact is not a data visual."}


def test_no_private_runtime_or_workspace_probe(module: object, finder: _HeldBackendImportFinder) -> None:
    source = _candidate_source(module)
    for forbidden in (
        "Path.home",
        "AppData",
        "ms-playwright",
        "codex-runtimes",
        "WORKSPACE_ROOT",
        "WORKSPACE_SCRIPTS",
        "content-creation-system",
        "design-system",
    ):
        assert forbidden not in source, f"private/ambient path probe must stay removed: {forbidden}"


def test_resolver_reuses_accepted_public_validator(module: object, finder: _HeldBackendImportFinder) -> None:
    validator = importlib.import_module("render_artifact_validation")
    assert module.resolve_local_ref is validator.resolve_local_ref
    candidate_file = Path(module.__file__).resolve()
    item_path = CANDIDATE_PATH.parent / "synthetic-item.json"
    assert module.resolve_local_ref(str(candidate_file), item_path) == candidate_file
    assert module.resolve_local_ref(CANDIDATE_PATH.name, item_path) == candidate_file
    missing = "definitely-absent-public-ref.json"
    assert module.resolve_local_ref(missing, item_path) == (module.STUDIO_ROOT / missing).resolve()


def test_finder_records_only_held_backend(module: object, finder: _HeldBackendImportFinder) -> None:
    before = list(finder.attempts)
    # Execute the actual candidate file again through its existing spec loader.
    # A synthetic module name cannot be rediscovered by importlib.reload(), and a
    # fake production module would weaken the assertion, so re-run the real file.
    reexecuted = _load_candidate()
    assert Path(reexecuted.__file__).resolve() == CANDIDATE_PATH
    assert finder.attempts == before, "re-executing the actual candidate must not attempt a held-backend import"


def main() -> int:
    finder = _HeldBackendImportFinder("record")
    sys.meta_path.insert(0, finder)
    try:
        module = _load_candidate()
        assert finder.attempts == [], f"candidate load imported the held backend: {finder.attempts}"
        tests = (
            test_module_load_does_not_import_held_backend,
            test_held_backend_import_is_function_local,
            test_metadata_uses_existing_literal_not_backend,
            test_receipt_evidence_metadata_defaults,
            test_missing_backend_rejects_before_output,
            test_transitive_missing_error_remains_visible,
            test_broken_backend_error_remains_visible,
            test_runtime_helpers_require_explicit_environment,
            test_public_root_contract,
            test_no_private_runtime_or_workspace_probe,
            test_resolver_reuses_accepted_public_validator,
            test_finder_records_only_held_backend,
        )
        for test in tests:
            print(f"[isolated] {test.__name__}")
            test(module, finder)
        print(f"PASS: {len(tests)} isolated public-boundary tests")
        return 0
    except Exception:
        traceback.print_exc()
        print("FAIL: isolated public-boundary tests stopped at the first failure")
        return 1
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)


if __name__ == "__main__":
    raise SystemExit(main())
