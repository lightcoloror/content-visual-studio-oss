#!/usr/bin/env python3
"""Run the synthetic case-script slice through Content Studio and MVP Video dry-run."""

from __future__ import annotations
from studio_paths import STUDIO_ROOT

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import case_video_script_adapter as case_adapter
import human_voice_gate
import research_output_adapter as research_adapter


ROOT = STUDIO_ROOT
WORKSPACE = ROOT.parent
FIXTURE_ROOT = ROOT / "fixtures/case-video-script-v1"
DEFAULT_MVP_ROOT = WORKSPACE / "mvp-video-pipeline"


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _expected_output_files(research: dict[str, Any], script: dict[str, Any]) -> set[str]:
    input_sha256 = research_adapter.sha256_value(research)
    content_id = (
        "research-"
        + research_adapter.stable_suffix(
            research["research_id"],
            input_sha256,
            research_adapter.ADAPTER_VERSION,
            length=24,
        )
    )
    script_id = script["script_id"]
    return {
        "case-video-e2e-receipt.json",
        f"voice/{script_id}.human-voice-receipt.json",
        f"voice/{script_id}.rewritten.json",
        f"case/{script_id}.content-video-brief.json",
        f"case/{script_id}.manifest.json",
        f"content/{content_id}.article.html",
        f"content/{content_id}.article.md",
        f"content/{content_id}.content-item.json",
        f"content/{content_id}.content-video-brief.json",
        f"content/{content_id}.manifest.json",
    }


def _validate_recoverable_output_root(
    output_root: Path,
    research: dict[str, Any],
    script: dict[str, Any],
) -> None:
    if output_root.exists() and not output_root.is_dir():
        raise case_adapter.CaseScriptError(
            "output_root_not_directory",
            f"output root is not a directory: {output_root}",
        )
    if not output_root.exists():
        return
    expected = _expected_output_files(research, script)
    present: set[str] = set()
    for path in output_root.rglob("*"):
        if path.is_symlink():
            raise case_adapter.CaseScriptError(
                "output_root_symlink_blocked",
                f"output root contains a symlink: {path}",
            )
        if path.is_file():
            present.add(path.relative_to(output_root).as_posix())
    unexpected = sorted(present - expected)
    if unexpected:
        raise case_adapter.CaseScriptError(
            "output_root_unmanaged",
            f"output root contains unmanaged files: {unexpected}",
        )


def run_e2e(output_root: Path, mvp_root: Path = DEFAULT_MVP_ROOT) -> dict[str, Any]:
    output_root = output_root.resolve()
    mvp_root = mvp_root.resolve()
    mvp_entrypoint = mvp_root / "scripts/content_video.py"
    if not mvp_root.is_dir() or not mvp_entrypoint.is_file():
        raise case_adapter.CaseScriptError(
            "downstream_dependency_missing",
            f"MVP Video dry-run entrypoint is unavailable: {mvp_entrypoint}",
        )
    content_root = output_root / "content"
    case_root = output_root / "case"
    voice_root = output_root / "voice"
    research_path = FIXTURE_ROOT / "synthetic-research-output.v1.json"
    fixture_script = research_adapter.load_json(FIXTURE_ROOT / "synthetic-case-video-script.v1.json")
    script_path = voice_root / f"{fixture_script['script_id']}.rewritten.json"
    voice_receipt_path = voice_root / f"{fixture_script['script_id']}.human-voice-receipt.json"
    research_schema = WORKSPACE / "question-research-poc/schemas/research-output.v1.schema.json"
    content_schema = WORKSPACE / "docs/content-creation-system/content-item.schema.json"
    video_schema = ROOT / "schemas/content-video-brief.v1.schema.json"

    research = research_adapter.load_json(research_path)
    script = fixture_script
    _validate_recoverable_output_root(output_root, research, script)

    voice_result = human_voice_gate.apply_human_voice_gate(
        base_script_path=FIXTURE_ROOT / "synthetic-case-video-script.pre-voice.json",
        initial_draft_review_path=FIXTURE_ROOT / "synthetic-initial-draft-review.v1.json",
        request_path=FIXTURE_ROOT / "synthetic-human-voice-rewrite-request.v1.json",
        fact_card_path=FIXTURE_ROOT / "synthetic-fact-card.json",
        output_script_path=script_path,
        output_receipt_path=voice_receipt_path,
    )

    research_result = research_adapter.adapt_research_output(
        research_path,
        content_root,
        research_schema,
        content_schema,
        video_schema,
    )
    content_item_path = next(content_root.glob("*.content-item.json"))
    case_result = case_adapter.adapt_case_video_script(
        script_path=script_path,
        research_path=research_path,
        content_item_path=content_item_path,
        fact_card_path=FIXTURE_ROOT / "synthetic-fact-card.json",
        route_card_path=FIXTURE_ROOT / "synthetic-route-card.json",
        voice_receipt_path=Path(voice_result["output_receipt"]),
        interview_receipt_paths=[],
        review_receipt_path=FIXTURE_ROOT / "synthetic-case-video-review-receipt.v1.json",
        output_dir=case_root,
        script_schema_path=ROOT / "schemas/case-video-script.v1.schema.json",
        research_schema_path=research_schema,
        content_schema_path=content_schema,
        video_schema_path=video_schema,
    )

    try:
        downstream = subprocess.run(
            [
                sys.executable,
                str(mvp_entrypoint),
                "dry-run",
                "--brief",
                case_result["brief"],
                "--schema",
                str(video_schema),
                "--research-output",
                str(research_path),
                "--research-schema",
                str(research_schema),
                "--case-handoff-manifest",
                case_result["manifest"],
                "--case-handoff-sha256",
                case_result["manifest_sha256"],
                "--require-case-handoff",
                "--output-root",
                str(output_root / "mvp-dry-run"),
                "--max-age-hours",
                "1000000",
            ],
            cwd=mvp_root,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise case_adapter.CaseScriptError(
            "downstream_mvp_timeout",
            "MVP Video dry-run exceeded the 30 second boundary",
        ) from error
    if downstream.returncode != 0:
        raise case_adapter.CaseScriptError(
            "downstream_mvp_dry_run_blocked",
            downstream.stderr.strip() or downstream.stdout.strip() or "MVP Video dry-run failed",
        )
    downstream_receipt = json.loads(downstream.stdout)
    if downstream_receipt.get("status") != "candidate_plan_ready":
        raise case_adapter.CaseScriptError(
            "downstream_mvp_dry_run_blocked",
            f"unexpected MVP Video status: {downstream_receipt.get('status')}",
        )

    artifacts = []
    for path in sorted([*content_root.iterdir(), *case_root.iterdir(), *voice_root.iterdir()]):
        artifacts.append(
            {
                "path": path.relative_to(output_root).as_posix(),
                "sha256": _file_sha256(path),
            }
        )
    receipt = {
        "schema": "case-video-script-e2e-receipt.v1",
        "status": "synthetic_e2e_passed",
        "content_id": research_result["content_id"],
        "script_id": case_result["script_id"],
        "artifacts": artifacts,
        "verification": {
            "research_adapter": research_result["status"],
            "case_adapter": case_result["status"],
            "human_voice_gate": voice_result["status"],
            "case_handoff_sha256": case_result["manifest_sha256"],
            "case_handoff_verified": downstream_receipt.get("case_handoff_verified"),
            "mvp_video": downstream_receipt["status"],
            "mvp_blockers": downstream_receipt["blockers"],
            "would_execute_ffmpeg": downstream_receipt["would_execute_ffmpeg"],
            "would_call_provider": downstream_receipt["would_call_provider"],
            "would_upload": downstream_receipt["would_upload"],
            "would_publish": downstream_receipt["would_publish"],
        },
        "boundaries": {
            "synthetic_only": True,
            "draft_only": True,
            "candidate_only": True,
            "manual_only": True,
        },
    }
    _write_json(output_root / "case-video-e2e-receipt.json", receipt)
    return receipt


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--mvp-root", type=Path, default=DEFAULT_MVP_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        receipt = run_e2e(args.output_root, args.mvp_root)
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (case_adapter.CaseScriptError, research_adapter.AdapterError, OSError, ValueError) as error:
        code = getattr(error, "code", "synthetic_e2e_blocked")
        print(
            json.dumps({"status": code, "message": str(error)}, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
