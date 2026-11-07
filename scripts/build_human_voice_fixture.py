#!/usr/bin/env python3
"""Regenerate the synthetic human-voice case fixture deterministically.

Adaptation for the public edition (source-only path fix):

* fixture roots resolve through ``studio_paths.STUDIO_ROOT`` instead of a
  hard-coded ``__file__`` parent, and can be redirected with ``--fixtures`` /
  ``--output-root`` or ``CONTENT_STUDIO_CASE_FIXTURE_DIR`` so a test copy never
  mutates the published fixtures;
* the documented ``CONTENT_STUDIO_HUMAN_VOICE_ROOT`` contract is bound, before
  importing the gate, to the inert explicitly fictional editing documents that
  ship with the public edition. An operator-supplied root always wins.
* a preflight rejects any missing published input before the first write.

Only published, explicitly fictional JSON fixtures are read. No TTS, voice
recording, model, provider, network request, browser or real media is used.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def _default_voice_root() -> Path:
    """Locate the published synthetic editing documents in either layout."""
    here = Path(__file__).resolve().parent
    for candidate in (
        here.parent / "fixtures" / "synthetic-voice",
        here / "studio_assets" / "fixtures" / "synthetic-voice",
    ):
        if (candidate / "SKILL.md").is_file():
            return candidate
    return here.parent / "fixtures" / "synthetic-voice"


# human_voice_gate and case_video_script_adapter bind this documented public env
# contract when studio_paths is first imported. Binding it here keeps fixture
# regeneration offline and explicitly fictional; real material must never be
# silently substituted, so an existing operator value is never overwritten.
os.environ.setdefault("CONTENT_STUDIO_HUMAN_VOICE_ROOT", str(_default_voice_root()))

from studio_paths import STUDIO_ROOT  # noqa: E402

import case_video_script_adapter as case_adapter  # noqa: E402
import human_voice_gate  # noqa: E402
import research_output_adapter as research_adapter  # noqa: E402


ROOT = STUDIO_ROOT
FIXTURE_ENV = "CONTENT_STUDIO_CASE_FIXTURE_DIR"
FIXTURE_NAMES = {
    "SCRIPT": "synthetic-case-video-script.v1.json",
    "BASE": "synthetic-case-video-script.pre-voice.json",
    "REQUEST": "synthetic-human-voice-rewrite-request.v1.json",
    "VOICE": "synthetic-human-voice-receipt.v1.json",
    "INITIAL_REVIEW": "synthetic-initial-draft-review.v1.json",
    "FINAL_REVIEW": "synthetic-case-video-review-receipt.v1.json",
    "FACT": "synthetic-fact-card.json",
}


def resolve_fixture_root(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env_value = os.environ.get(FIXTURE_ENV, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    return (STUDIO_ROOT / "fixtures" / "case-video-script-v1").resolve()


def fixture_paths(root: Path) -> dict[str, Path]:
    return {key: root / name for key, name in FIXTURE_NAMES.items()}


FIXTURES = resolve_fixture_root()
SCRIPT = FIXTURES / FIXTURE_NAMES["SCRIPT"]
BASE = FIXTURES / FIXTURE_NAMES["BASE"]
REQUEST = FIXTURES / FIXTURE_NAMES["REQUEST"]
VOICE = FIXTURES / FIXTURE_NAMES["VOICE"]
INITIAL_REVIEW = FIXTURES / FIXTURE_NAMES["INITIAL_REVIEW"]
FINAL_REVIEW = FIXTURES / FIXTURE_NAMES["FINAL_REVIEW"]
FACT = FIXTURES / FIXTURE_NAMES["FACT"]

AIISH_TEXT = {
    "segment-01": "这不是一张保单，而是一份家庭安全感。也就是说，真正重要的不是产品，而是底层逻辑。如果你也认同，欢迎收藏。",
    "segment-02": "保险不只是合同，更是陪伴式服务。这说明专业价值决定了最后的结果。如果你也认同，欢迎收藏。",
    "segment-03": "与此同时，我们进一步形成服务闭环。此外，我们用全生命周期方案赋能家庭，由此可见，这是一套完整的方法论。",
    "segment-04": "本质上，风险管理抓手体现的是价值交付。总结来说，这就是专业价值，这就是我们想说的。",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _preflight(source: dict[str, Path]) -> None:
    """Fail closed before the first write if any published input is missing."""
    for key in ("SCRIPT", "INITIAL_REVIEW", "FINAL_REVIEW", "FACT"):
        if not source[key].is_file():
            raise FileNotFoundError(f"required published synthetic fixture is missing: {source[key]}")
    voice_root = Path(os.environ.get("CONTENT_STUDIO_HUMAN_VOICE_ROOT", ""))
    for relative in ("SKILL.md", "references/rulebook.md"):
        if not (voice_root / relative).is_file():
            raise FileNotFoundError(
                f"required published synthetic editing document is missing: {voice_root / relative}"
            )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=None,
        help="directory holding the published synthetic-* case fixtures (default: STUDIO_ROOT/fixtures/case-video-script-v1)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="directory receiving the regenerated fixtures (default: the --fixtures directory)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_root = resolve_fixture_root(args.fixtures)
    output_root = Path(args.output_root).expanduser().resolve() if args.output_root else source_root
    source = fixture_paths(source_root)
    output = fixture_paths(output_root)
    _preflight(source)

    final_template = _load(source["SCRIPT"])
    desired_text = {row["segment_id"]: row["spoken_text"] for row in final_template["segments"]}
    base = copy.deepcopy(final_template)
    base["inputs"].pop("human_voice_receipt_ref", None)
    for row in base["segments"]:
        row["spoken_text"] = AIISH_TEXT[row["segment_id"]]
    base["skill_stage_receipts"] = []
    base["provenance"]["adapter_version"] = "pre-voice-fixture"
    _write(output["BASE"], base)
    initial_review = _load(source["INITIAL_REVIEW"])
    initial_review_ref = case_adapter._artifact_ref(
        initial_review,
        ("review_id",),
        "initial-draft-review",
    )

    rewritten_preview = copy.deepcopy(base)
    for row in rewritten_preview["segments"]:
        row["spoken_text"] = desired_text[row["segment_id"]]
    rewritten_preview["hook_candidates"] = copy.deepcopy(final_template["hook_candidates"])
    rewritten_preview["selected_hook_id"] = final_template["selected_hook_id"]
    rewritten_preview["body_status"] = "stable"
    output_body_sha = research_adapter.sha256_value(case_adapter.stable_body_payload(rewritten_preview))
    request = {
        "schema_version": "case-video-human-voice-request.v1",
        "request_id": "voice-request-synthetic-case-001",
        "script_id": base["script_id"],
        "content_id": base["content_id"],
        "synthetic_only": True,
        "initial_draft_review_ref": initial_review_ref,
        "rewrite_operations": [
            {
                "segment_id": row["segment_id"],
                "before_text_sha256": _text_hash(row["spoken_text"]),
                "replacement_text": desired_text[row["segment_id"]],
                "reason": "移除对称口号、统一 CTA、解释过满、翻译腔和抽象服务话术，恢复本人可朗读口吻。",
            }
            for row in base["segments"]
        ],
        "dbs_content_diagnosis": {
            "status": "passed_to_local_rewrite",
            "issue_codes": ["symmetric-slogan", "uniform-cta", "over-explained", "translation-register", "abstract-service-language"],
            "note": "合成诊断只用于验证 Content Studio 本地门禁，不代表真实 Skill 运行。",
        },
        "dbs_ai_check_diagnosis": {
            "status": "passed_to_local_rewrite",
            "issue_codes": ["ai-trace"],
            "note": "合成诊断发现整齐节奏、过度解释和抽象表达；不上传任何材料。",
        },
        "read_aloud": {
            "status": "completed",
            "performed_by": "synthetic-fixture-author",
            "body_sha256": output_body_sha,
            "completed_at": "2026-08-11T20:30:00+08:00",
            "notes": ["合成朗读回执；未使用真实作者录音。", "逐段读完，无阻碍口语表达。"],
        },
        "author_confirmation": {
            "status": "confirmed",
            "performed_by": "synthetic-fixture-author",
            "body_sha256": output_body_sha,
            "confirmed_at": "2026-08-11T20:31:00+08:00",
            "voice_match": True,
            "facts_preserved": True,
        },
        "post_freeze_hooks": copy.deepcopy(final_template["hook_candidates"]),
        "post_freeze_selected_hook_id": final_template["selected_hook_id"],
        "hook_input_body_sha256": output_body_sha,
        "boundaries": {
            "local_only": True,
            "external_service_called": False,
            "raw_sensitive_media_included": False,
            "would_publish": False,
        },
    }
    _write(output["REQUEST"], request)
    human_voice_gate.apply_human_voice_gate(
        base_script_path=output["BASE"],
        initial_draft_review_path=source["INITIAL_REVIEW"],
        request_path=output["REQUEST"],
        fact_card_path=source["FACT"],
        output_script_path=output["SCRIPT"],
        output_receipt_path=output["VOICE"],
    )

    script = _load(output["SCRIPT"])
    voice = _load(output["VOICE"])
    review = _load(source["FINAL_REVIEW"])
    review["inputs"] = {
        "case_video_script": case_adapter._artifact_ref(script, ("script_id",), "case-video-script"),
        "research_output": script["inputs"]["research_output_ref"],
        "content_item": script["inputs"]["content_item_ref"],
        "fact_card": script["inputs"]["fact_card_ref"],
        "route_card": script["inputs"]["route_card_ref"],
        "human_voice_receipt": case_adapter._artifact_ref(voice, ("receipt_id",), "human-voice-receipt"),
        "interview_receipts": [],
    }
    review["subject_sha256"] = research_adapter.sha256_value(case_adapter.review_subject_payload(script))
    _write(output["FINAL_REVIEW"], review)
    print(json.dumps({"status": "synthetic_human_voice_fixture_built", "body_sha256": output_body_sha}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
