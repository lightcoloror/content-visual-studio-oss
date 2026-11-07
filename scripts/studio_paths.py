"""Resolve source or installed resources without probing a private workspace."""
from __future__ import annotations
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_ROOT = HERE.parent
STUDIO_ROOT = SOURCE_ROOT if (SOURCE_ROOT / "schemas/content-item.schema.json").is_file() else HERE / "studio_assets"
HUMAN_VOICE_ROOT = Path(os.environ.get("CONTENT_STUDIO_HUMAN_VOICE_ROOT", str(Path.cwd() / "skills/human-voice-editor"))).expanduser().resolve()

def research_schema_path():
    # The installed public QRP owns this contract. An exact provenance-recorded
    # copy is retained for offline source inspection and tests.
    from question_research_poc.research_output import research_output_schema_path
    return research_output_schema_path()
