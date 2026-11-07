"""Thin Content Studio adapter for the mandatory self-media step handoff."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path


def _agent():
    from registered_self_media import load_module
    return load_module('self_media_agent')


def consume_step_handoff(handoff: Path):
    """Require the registered execution validator; inspection-only handoffs are rejected."""
    return _agent().validate_step_handoff(handoff, expected_tool_id="content-studio-poc")


def main(argv=None):
    import argparse
    import json
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(consume_step_handoff(args.handoff)["status"])
    except (OSError, ValueError) as error:
        print(json.dumps({'status':'blocked','error_code':getattr(error,'code','handoff_invalid'),
                          'message':str(error)},ensure_ascii=False),file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
