#!/usr/bin/env python3
"""Targeted synthetic-only unit test: build_human_voice_fixture.py.

Runs the candidate CLI as a child process against a fresh copy of the already
published, explicitly fictional fixtures. No TTS, model, provider, network,
service or real voice material.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "fixtures" / "case-video-script-v1"
VOICE = ROOT / "fixtures" / "synthetic-voice"
SCRIPT = SCRIPTS / "build_human_voice_fixture.py"
WORKSPACE = Path(os.environ.get("CANDIDATE_TEST_WORKSPACE", str(ROOT.parent / "synthetic")))
os.environ.setdefault("CONTENT_STUDIO_HUMAN_VOICE_ROOT", str(VOICE))
sys.path.insert(0, str(SCRIPTS))

OUTPUT_NAMES = (
    "synthetic-case-video-script.pre-voice.json",
    "synthetic-human-voice-rewrite-request.v1.json",
    "synthetic-case-video-script.v1.json",
    "synthetic-human-voice-receipt.v1.json",
    "synthetic-case-video-review-receipt.v1.json",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def published_digests() -> dict[str, str]:
    return {name: digest(FIXTURES / name) for name in OUTPUT_NAMES}


def fresh_fixture_copy(dest: Path) -> Path:
    target = dest / "case-fixtures"
    target.mkdir(parents=True)
    for source in sorted(FIXTURES.iterdir()):
        if source.is_file():
            shutil.copy2(source, target / source.name)
    return target


def run_cli(fixtures: Path, output_root: Path | None = None, voice_root: Path | None = None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SCRIPTS) + os.pathsep + env.get("PYTHONPATH", "")
    env["CONTENT_STUDIO_HUMAN_VOICE_ROOT"] = str(voice_root or VOICE)
    command = [
        sys.executable,
        str(SCRIPT),
        "--fixtures", str(fixtures),
        "--output-root", str(output_root or fixtures),
    ]
    return subprocess.run(command, cwd=str(ROOT), env=env, capture_output=True, text=True)


class BuildHumanVoiceFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        WORKSPACE.mkdir(parents=True, exist_ok=True)

    def test_regeneration_matches_published_fixture_bytes(self) -> None:
        with tempfile.TemporaryDirectory(dir=str(WORKSPACE), prefix="voice-regen-") as temp:
            fixtures = fresh_fixture_copy(Path(temp))
            proc = run_cli(fixtures)
            self.assertEqual(proc.returncode, 0, proc.stderr[-1200:])
            payload = json.loads(proc.stdout.strip())
            self.assertEqual(payload["status"], "synthetic_human_voice_fixture_built")
            self.assertEqual(
                {name: digest(fixtures / name) for name in OUTPUT_NAMES},
                published_digests(),
                "regenerated fixtures must be byte-identical to the published synthetic fixtures",
            )
            request = json.loads((fixtures / "synthetic-human-voice-rewrite-request.v1.json").read_text(encoding="utf-8"))
            receipt = json.loads((fixtures / "synthetic-human-voice-receipt.v1.json").read_text(encoding="utf-8"))
            self.assertTrue(request["synthetic_only"])
            self.assertFalse(request["boundaries"]["external_service_called"])
            self.assertEqual(payload["body_sha256"], receipt["rewritten_body_sha256"])
            self.assertEqual(payload["body_sha256"], request["read_aloud"]["body_sha256"])
            self.assertEqual(payload["body_sha256"], request["hook_input_body_sha256"])
            self.assertEqual(request["read_aloud"]["performed_by"], "synthetic-fixture-author")

    def test_repeated_generation_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(dir=str(WORKSPACE), prefix="voice-idem-") as temp:
            fixtures = fresh_fixture_copy(Path(temp))
            first = run_cli(fixtures)
            self.assertEqual(first.returncode, 0, first.stderr[-1200:])
            after_first = {name: digest(fixtures / name) for name in OUTPUT_NAMES}
            second = run_cli(fixtures)
            self.assertEqual(second.returncode, 0, second.stderr[-1200:])
            self.assertEqual(after_first, {name: digest(fixtures / name) for name in OUTPUT_NAMES})
            self.assertEqual(first.stdout.strip(), second.stdout.strip())

    def test_missing_published_source_fixture_fails_closed_before_writes(self) -> None:
        with tempfile.TemporaryDirectory(dir=str(WORKSPACE), prefix="voice-missing-") as temp:
            fixtures = fresh_fixture_copy(Path(temp))
            before = {name: digest(fixtures / name) for name in OUTPUT_NAMES}
            (fixtures / "synthetic-fact-card.json").unlink()
            proc = run_cli(fixtures)
            self.assertNotEqual(proc.returncode, 0, "a missing published input must fail closed")
            self.assertIn("missing", proc.stderr.lower())
            self.assertEqual(
                before,
                {name: digest(fixtures / name) for name in OUTPUT_NAMES},
                "no partial output may be written after a missing input",
            )

    def test_missing_synthetic_voice_document_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(dir=str(WORKSPACE), prefix="voice-doc-") as temp:
            root = Path(temp)
            fixtures = fresh_fixture_copy(root)
            voice_copy = root / "voice"
            shutil.copytree(VOICE, voice_copy)
            (voice_copy / "references" / "rulebook.md").unlink()
            proc = run_cli(fixtures, voice_root=voice_copy)
            self.assertNotEqual(proc.returncode, 0, "a missing editing document must fail closed")
            self.assertIn("missing", proc.stderr.lower())

    def test_explicit_output_root_leaves_source_fixtures_untouched(self) -> None:
        with tempfile.TemporaryDirectory(dir=str(WORKSPACE), prefix="voice-outroot-") as temp:
            root = Path(temp)
            fixtures = fresh_fixture_copy(root)
            before = {source.name: digest(source) for source in sorted(fixtures.iterdir()) if source.is_file()}
            output_root = root / "generated"
            output_root.mkdir()
            proc = run_cli(fixtures, output_root=output_root)
            self.assertEqual(proc.returncode, 0, proc.stderr[-1200:])
            self.assertEqual(before, {source.name: digest(source) for source in sorted(fixtures.iterdir()) if source.is_file()})
            self.assertEqual(
                {name: digest(output_root / name) for name in OUTPUT_NAMES},
                published_digests(),
            )

    def test_candidate_script_has_no_tts_network_or_provider_imports(self) -> None:
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        blocked = {"requests", "urllib", "http", "socket", "subprocess", "boto3", "openai", "anthropic", "pyttsx3", "gtts"}
        self.assertEqual(imported & blocked, set(), f"unexpected external integration imports: {imported & blocked}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
