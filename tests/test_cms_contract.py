#!/usr/bin/env python3
"""Directed offline contract tests for scripts/validate_sveltia_config.py.

Every runtime record, schema and CMS document below is SYNTHETIC test data.
No canonical project schema or public configuration is substituted, fetched or
read from a network location. The tests never spawn a process, never start a
server and never perform a remote retrieval.

Import contract (host execution plan):
    ``validate_sveltia_config`` is imported from PYTHONPATH and the host venv
    provides the optional PyYAML/jsonschema extra.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import socket
import sys
import tempfile
import unittest
import urllib.request
import warnings
from pathlib import Path
from unittest import mock

try:  # the real optional CMS extra must exist for these tests to be meaningful
    import yaml
except ImportError:  # pragma: no cover - host venv supplies PyYAML 6.0.3
    yaml = None

from jsonschema import Draft202012Validator

from validate_sveltia_config import main as cms_main
from validate_sveltia_config import validate_config

DRAFT7 = "http://json-schema.org/draft-07/schema#"
DRAFT202012 = "https://json-schema.org/draft/2020-12/schema"

VALID_SCHEMA = {
    "$schema": DRAFT7,
    "type": "object",
    "properties": {"title": {"type": "string"}},
    "required": ["title"],
    "additionalProperties": False,
}


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@unittest.skipIf(yaml is None, "PyYAML (the declared CMS extra) is required")
class CmsConfigContractTests(unittest.TestCase):
    """Contract and security behaviour of the offline CMS validator."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.real_yaml = sys.modules.get("yaml", yaml)

    # ---------------------------------------------------------------- helpers
    def write_fixture(
        self,
        schema,
        document,
        *,
        runtime_changes=None,
        ref=None,
        schema_file="synthetic.schema.json",
    ):
        """Write a synthetic runtime/schema/document triple and return its paths."""
        schema_bytes = json.dumps(
            schema, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        schema_path = self.root / schema_file
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_bytes(schema_bytes)

        runtime = {
            "schema_version": "sveltia-runtime.v1",
            "package": "@sveltia/cms",
            "version": "0.172.4",
            "local_schema_ref": ref if ref is not None else schema_file,
            "schema_sha256": sha256_hex(schema_bytes),
        }
        if runtime_changes:
            runtime.update(runtime_changes)
        runtime_path = self.root / "sveltia-runtime.v1.json"
        runtime_path.write_text(json.dumps(runtime, indent=2), encoding="utf-8")

        config_path = self.root / "config.yml"
        if isinstance(document, str):
            config_path.write_text(document, encoding="utf-8")
        else:
            config_path.write_text(
                yaml.safe_dump(document, sort_keys=True), encoding="utf-8"
            )
        return runtime_path, config_path, self.root

    def rewrite_runtime(self, runtime_path: Path, **changes) -> None:
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime.update(changes)
        runtime_path.write_text(json.dumps(runtime, indent=2), encoding="utf-8")

    def validate(self, schema, document, **fixture_options):
        runtime_path, config_path, schema_root = self.write_fixture(
            schema, document, **fixture_options
        )
        return validate_config(runtime_path, config_path, schema_root)

    def run_cli(self, *args):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cms_main([str(argument) for argument in args])
        return code, buffer.getvalue()

    # ----------------------------------------------------------- happy paths
    def test_supported_pinned_runtime_validates_clean_config(self):
        self.assertEqual(
            self.validate(VALID_SCHEMA, {"title": "Synthetic title"}),
            [],
        )

    # ----------------------------------------------------- pin + hash guard
    def test_runtime_identity_is_pinned_exactly(self):
        cases = [
            ("schema_version", {"schema_version": "sveltia-runtime.v2"}),
            ("package", {"package": "@sveltia/cms-next"}),
            ("version", {"version": "0.172.5"}),
            ("version absent", {"version": None}),
        ]
        for label, changes in cases:
            with self.subTest(case=label):
                runtime_path, config_path, schema_root = self.write_fixture(
                    VALID_SCHEMA, {"title": "Synthetic title"}
                )
                self.rewrite_runtime(runtime_path, **changes)
                with self.assertRaisesRegex(
                    ValueError, "^unsupported_pinned_cms_runtime$"
                ):
                    validate_config(runtime_path, config_path, schema_root)

    def test_schema_hash_must_match_the_raw_schema_bytes(self):
        runtime_path, config_path, schema_root = self.write_fixture(
            VALID_SCHEMA, {"title": "Synthetic title"}
        )
        self.rewrite_runtime(runtime_path, schema_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "^cms_schema_hash_drift$"):
            validate_config(runtime_path, config_path, schema_root)

        self.rewrite_runtime(runtime_path, schema_sha256=1234)
        with self.assertRaisesRegex(ValueError, "^cms_schema_hash_drift$"):
            validate_config(runtime_path, config_path, schema_root)

        # A one-byte edit is drift even if the schema still parses as JSON.
        runtime_path, config_path, schema_root = self.write_fixture(
            VALID_SCHEMA, {"title": "Synthetic title"}
        )
        schema_path = schema_root / "synthetic.schema.json"
        schema_path.write_bytes(schema_path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "^cms_schema_hash_drift$"):
            validate_config(runtime_path, config_path, schema_root)

    # --------------------------------------------------- local schema path guard
    def test_unsafe_local_schema_references_are_rejected(self):
        cases = {
            "parent traversal": "../synthetic.schema.json",
            "nested traversal": "nested/../../synthetic.schema.json",
            "absolute path": str(self.root / "synthetic.schema.json"),
            "windows drive": "C:\\synthetic\\schema.json",
            "backslash separator": "nested\\synthetic.schema.json",
            "remote url": "https://example.invalid/synthetic.schema.json",
            "empty reference": "",
            "directory reference": ".",
        }
        for label, ref in cases.items():
            with self.subTest(case=label):
                runtime_path, config_path, schema_root = self.write_fixture(
                    VALID_SCHEMA, {"title": "Synthetic title"}, ref=ref
                )
                with self.assertRaisesRegex(
                    ValueError, "^unsafe_local_schema_ref$"
                ):
                    validate_config(runtime_path, config_path, schema_root)

        with self.subTest(case="non-string reference"):
            runtime_path, config_path, schema_root = self.write_fixture(
                VALID_SCHEMA, {"title": "Synthetic title"}
            )
            self.rewrite_runtime(runtime_path, local_schema_ref=None)
            with self.assertRaisesRegex(ValueError, "^unsafe_local_schema_ref$"):
                validate_config(runtime_path, config_path, schema_root)

    def test_schema_symlink_escape_is_rejected(self):
        schema_root = self.root / "schema-root"
        schema_root.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        schema_bytes = json.dumps(
            {"$schema": DRAFT7, "type": "object"}, separators=(",", ":")
        ).encode("utf-8")
        (outside / "escaped.schema.json").write_bytes(schema_bytes)

        link = schema_root / "link.schema.json"
        try:
            os.symlink(outside / "escaped.schema.json", link)
        except (OSError, NotImplementedError) as exc:  # OS privilege dependent
            self.skipTest(
                f"filesystem symlink creation unavailable: "
                f"{type(exc).__name__}: {exc}"
            )

        runtime_path = self.root / "sveltia-runtime.v1.json"
        runtime_path.write_text(
            json.dumps(
                {
                    "schema_version": "sveltia-runtime.v1",
                    "package": "@sveltia/cms",
                    "version": "0.172.4",
                    "local_schema_ref": "link.schema.json",
                    "schema_sha256": sha256_hex(schema_bytes),
                }
            ),
            encoding="utf-8",
        )
        config_path = self.root / "config.yml"
        config_path.write_text("{}\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "^unsafe_local_schema_ref$"):
            validate_config(runtime_path, config_path, schema_root)

    # ------------------------------------------------------------ dialects
    def test_undeclared_and_unknown_dialects_are_rejected(self):
        cases = {
            "undeclared": {
                key: value
                for key, value in VALID_SCHEMA.items()
                if key != "$schema"
            },
            "unknown": {
                "$schema": "https://example.invalid/draft/synthetic#",
                "type": "object",
            },
        }
        for label, schema in cases.items():
            with self.subTest(case=label):
                with self.assertRaisesRegex(
                    ValueError, "^unsupported_schema_dialect$"
                ):
                    self.validate(schema, {"title": "Synthetic title"})

    def test_declared_draft7_dependencies_counterexample_fails(self):
        schema = {
            "$schema": DRAFT7,
            "type": "object",
            "properties": {
                "a": {"type": "string"},
                "b": {"type": "string"},
            },
            "dependencies": {"a": ["b"]},
            "additionalProperties": False,
        }
        document = {"a": "synthetic"}
        errors = self.validate(schema, document)
        self.assertEqual(len(errors), 1, errors)
        location, _, message = errors[0].partition(": ")
        self.assertEqual(location, "$")
        self.assertIn("'b'", message)
        self.assertIn("'a'", message)
        self.assertIn("depend", message.lower())

        # Prove the counterexample really discriminates the declared dialect:
        # a lazy 2020-12 substitution ignores ``dependencies`` and would pass.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            substituted = list(Draft202012Validator(schema).iter_errors(document))
        self.assertEqual(
            substituted,
            [],
            "a Draft202012 substitution would silently accept the counterexample",
        )

    def test_declared_draft202012_schema_is_honored(self):
        schema = {
            "$schema": DRAFT202012,
            "type": "object",
            "properties": {
                "a": {"type": "string"},
                "b": {"type": "string"},
            },
            "dependentRequired": {"a": ["b"]},
            "additionalProperties": False,
        }
        runtime_path, config_path, schema_root = self.write_fixture(
            schema, {"a": "synthetic"}
        )
        errors = validate_config(runtime_path, config_path, schema_root)
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith("$: "), errors[0])
        self.assertIn("'b'", errors[0])
        self.assertIn("depend", errors[0].lower())

        config_path.write_text(
            yaml.safe_dump({"a": "synthetic", "b": "synthetic"}, sort_keys=True),
            encoding="utf-8",
        )
        self.assertEqual(
            validate_config(runtime_path, config_path, schema_root), []
        )

    # ------------------------------------------------------------ YAML safety
    def test_safe_loader_rejects_python_yaml_constructors(self):
        documents = {
            "object apply": "!!python/object/apply:os.system ['synthetic-noop']\n",
            "object name": "!!python/name:os.system ''\n",
        }
        for label, document in documents.items():
            with self.subTest(case=label):
                runtime_path, config_path, schema_root = self.write_fixture(
                    VALID_SCHEMA, document
                )
                with mock.patch.object(
                    os,
                    "system",
                    side_effect=AssertionError("a Python YAML constructor ran"),
                ) as system:
                    with self.assertRaises(yaml.constructor.ConstructorError):
                        validate_config(runtime_path, config_path, schema_root)
                    system.assert_not_called()

    # ------------------------------------------------------- remote ref guard
    def test_remote_reference_fails_closed_without_network(self):
        schema = {
            "$schema": DRAFT7,
            "type": "object",
            "properties": {
                "x": {
                    "$ref": (
                        "https://example.invalid/synthetic.schema.json"
                        "#/definitions/never"
                    )
                }
            },
        }
        runtime_path, config_path, schema_root = self.write_fixture(
            schema, {"x": "synthetic"}
        )

        raised = None
        with mock.patch.object(
            socket, "getaddrinfo", side_effect=AssertionError("name resolution")
        ), mock.patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("outbound connection"),
        ), mock.patch.object(
            urllib.request,
            "urlopen",
            side_effect=AssertionError("outbound retrieval"),
        ):
            try:
                validate_config(runtime_path, config_path, schema_root)
            except AssertionError:
                raise
            except Exception as exc:  # noqa: BLE001 - wrapper type is version specific
                raised = exc

        self.assertIsNotNone(
            raised, "an unprovided remote $ref must never validate successfully"
        )
        description = f"{type(raised).__name__} {raised}".lower()
        self.assertTrue(
            any(
                marker in description
                for marker in (
                    "referenc",
                    "resolution",
                    "unresolv",
                    "resolve",
                    "example.invalid",
                    "no such resource",
                )
            ),
            description,
        )

        code, output = self.run_cli(
            "--runtime",
            runtime_path,
            "--config",
            config_path,
            "--schema-root",
            schema_root,
        )
        self.assertEqual(code, 2)
        self.assertIn("CMS config validation blocked:", output)

    # --------------------------------------------------- diagnostics + dedupe
    def test_invalid_document_reports_deduped_dot_paths(self):
        schema = {
            "$schema": DRAFT7,
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 5},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"label": {"type": "integer"}},
                        "required": ["label"],
                        "additionalProperties": False,
                    },
                },
            },
            "allOf": [
                {"properties": {"title": {"minLength": 5}}},
                {"properties": {"title": {"minLength": 5}}},
            ],
            "additionalProperties": False,
        }
        errors = self.validate(
            schema, {"title": "ab", "items": [{"label": "not-an-integer"}]}
        )
        self.assertEqual(len(errors), 2, errors)
        self.assertTrue(errors[0].startswith("items.0.label: "), errors)
        self.assertTrue(errors[1].startswith("title: "), errors)
        self.assertIn("is not of type 'integer'", errors[0])
        self.assertIn("too short", errors[1])
        # Three identical leaf errors collapse to exactly one message.
        self.assertEqual(sum("too short" in message for message in errors), 1)
        self.assertEqual(len(set(errors)), len(errors))

    def test_errors_use_dollar_for_the_document_root(self):
        self.assertEqual(
            self.validate({"$schema": DRAFT7, "type": "object"}, []),
            ["$: [] is not of type 'object'"],
        )

    # ------------------------------------------------------------ CLI contract
    def test_cli_exit_codes_and_stdout(self):
        runtime_path, config_path, schema_root = self.write_fixture(
            VALID_SCHEMA, {"title": "Synthetic title"}
        )

        code, output = self.run_cli(
            "--runtime",
            runtime_path,
            "--config",
            config_path,
            "--schema-root",
            schema_root,
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            output.strip(),
            "Validated local config against pinned Sveltia CMS0.172.4 schema; "
            "no CMS bundle, network, login or publication executed.",
        )

        config_path.write_text(
            yaml.safe_dump({"items": []}, sort_keys=True), encoding="utf-8"
        )
        code, output = self.run_cli(
            "--runtime",
            runtime_path,
            "--config",
            config_path,
            "--schema-root",
            schema_root,
        )
        self.assertEqual(code, 1)
        self.assertTrue(output.startswith("Sveltia config validation failed:"), output)
        self.assertIn("- ", output)
        self.assertIn("'title' is a required property", output)

        self.rewrite_runtime(runtime_path, version="0.172.4-preview")
        code, output = self.run_cli(
            "--runtime",
            runtime_path,
            "--config",
            config_path,
            "--schema-root",
            schema_root,
        )
        self.assertEqual(code, 2)
        self.assertIn(
            "CMS config validation blocked: ValueError: "
            "unsupported_pinned_cms_runtime",
            output,
        )

    # ---------------------------------------------------- optional-extra import
    def test_missing_yaml_extra_blocks_without_poisoning_sys_modules(self):
        runtime_path, config_path, schema_root = self.write_fixture(
            VALID_SCHEMA, {"title": "Synthetic title"}
        )

        with mock.patch.dict(sys.modules, {"yaml": None}):
            with self.assertRaisesRegex(
                ValueError, "cms_validation_extra_required"
            ):
                validate_config(runtime_path, config_path, schema_root)

            code, output = self.run_cli(
                "--runtime",
                runtime_path,
                "--config",
                config_path,
                "--schema-root",
                schema_root,
            )
            self.assertEqual(code, 2)
            self.assertIn("CMS config validation blocked:", output)

        # The patch must be fully restored for following tests/imports.
        self.assertIs(sys.modules.get("yaml"), self.real_yaml)
        self.assertEqual(
            validate_config(runtime_path, config_path, schema_root), []
        )


if __name__ == "__main__":
    unittest.main()
