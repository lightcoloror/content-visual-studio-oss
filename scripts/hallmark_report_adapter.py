#!/usr/bin/env python3
"""Convert Hallmark audit findings to a report-only Keep/Fix/Quick Wins review."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token


SEVERITY_BUCKET = {
    "critical": "fix",
    "major": "fix",
    "minor": "quick_wins",
    "pass": "keep",
    "strength": "keep",
    "keep": "keep",
}
BUCKETS = ("keep", "fix", "quick_wins")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plain_inline(token: Token) -> str:
    if token.children:
        parts = []
        for child in token.children:
            if child.type in {"text", "code_inline", "html_inline"}:
                parts.append(child.content)
            elif child.type in {"softbreak", "hardbreak"}:
                parts.append(" ")
        return "".join(parts).strip()
    return token.content.strip()


def _normalize_severity(value: str) -> str:
    lowered = value.strip().casefold()
    for severity in SEVERITY_BUCKET:
        if lowered.startswith(severity):
            return severity
    return lowered or "major"


def _normalize_finding(raw: dict[str, Any], index: int) -> dict[str, str]:
    severity = _normalize_severity(str(raw.get("severity") or raw.get("level") or "major"))
    explicit_bucket = str(raw.get("bucket") or raw.get("category") or "").casefold().replace("-", "_")
    bucket = explicit_bucket if explicit_bucket in BUCKETS else SEVERITY_BUCKET.get(severity, "fix")
    title = str(raw.get("title") or raw.get("tell") or raw.get("finding") or "Untitled finding").strip()
    return {
        "finding_id": str(raw.get("finding_id") or raw.get("id") or f"finding-{index:03d}"),
        "bucket": bucket,
        "severity": severity,
        "title": title,
        "where": str(raw.get("where") or raw.get("location") or "").strip(),
        "recommendation": str(raw.get("recommendation") or raw.get("fix") or "").strip(),
        "evidence": str(raw.get("evidence") or "").strip(),
    }


def parse_hallmark_json(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_findings = payload if isinstance(payload, list) else payload.get("findings", [])
    if not isinstance(raw_findings, list):
        raise ValueError("Hallmark JSON must be a list or contain a findings list")
    return [_normalize_finding(raw, index) for index, raw in enumerate(raw_findings, 1)]


def parse_hallmark_markdown(path: Path) -> list[dict[str, str]]:
    tokens = MarkdownIt("commonmark").enable("table").parse(path.read_text(encoding="utf-8"))
    findings: list[dict[str, str]] = []
    severity = "major"
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == "heading_open" and token.tag == "h3" and index + 1 < len(tokens):
            severity = _normalize_severity(_plain_inline(tokens[index + 1]))
        if token.type != "table_open":
            index += 1
            continue

        row: list[str] = []
        in_header = False
        while index < len(tokens) and tokens[index].type != "table_close":
            current = tokens[index]
            if current.type == "thead_open":
                in_header = True
            elif current.type == "thead_close":
                in_header = False
            elif current.type in {"th_open", "td_open"} and index + 1 < len(tokens):
                inline = tokens[index + 1]
                if inline.type == "inline":
                    row.append(_plain_inline(inline))
            elif current.type == "tr_close":
                if not in_header and len(row) >= 4 and row[0].strip().isdigit():
                    findings.append(
                        _normalize_finding(
                            {
                                "id": f"hallmark-{row[0].strip()}",
                                "severity": severity,
                                "tell": row[1],
                                "where": row[2],
                                "fix": row[3],
                                "evidence": f"Markdown table row {row[0].strip()}",
                            },
                            len(findings) + 1,
                        )
                    )
                row = []
            index += 1
        index += 1
    return findings


def build_report(path: Path) -> dict[str, Any]:
    before = sha256(path)
    if path.suffix.casefold() == ".json":
        findings = parse_hallmark_json(path)
        source_format = "json"
    elif path.suffix.casefold() in {".md", ".markdown"}:
        findings = parse_hallmark_markdown(path)
        source_format = "markdown"
    else:
        raise ValueError("Hallmark report input must be JSON or Markdown")
    after = sha256(path)
    if before != after:
        raise RuntimeError("report-only boundary violated: source changed during conversion")

    grouped = {bucket: [] for bucket in BUCKETS}
    for finding in findings:
        grouped[finding["bucket"]].append(finding)
    return {
        "schema_version": "hallmark-review-adapter.v1",
        "created_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "source": {"ref": str(path), "format": source_format, "sha256": before},
        "policy": {
            "mode": "report-only",
            "automatic_design_changes": False,
            "source_mutation": False,
            "human_review_required": True,
        },
        "summary": {bucket: len(grouped[bucket]) for bucket in BUCKETS},
        **grouped,
    }


def render_markdown(report: dict[str, Any]) -> str:
    labels = {"keep": "Keep", "fix": "Fix", "quick_wins": "Quick Wins"}
    lines = [
        "# Hallmark Design Review",
        "",
        "> Report-only conversion. No source or design file was modified.",
        "",
        f"- Source: `{report['source']['ref']}`",
        f"- SHA-256: `{report['source']['sha256']}`",
        "- Human review: required",
    ]
    for bucket in BUCKETS:
        lines.extend(["", f"## {labels[bucket]}", ""])
        findings = report[bucket]
        if not findings:
            lines.append("No findings.")
            continue
        for finding in findings:
            location = f" ({finding['where']})" if finding["where"] else ""
            lines.append(f"- **[{finding['severity'].upper()}] {finding['title']}**{location}")
            if finding["recommendation"]:
                lines.append(f"  Recommendation: {finding['recommendation']}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    return parser.parse_args()


def write_report(source: Path, output: Path, output_format: str = "json") -> dict[str, Any]:
    source = source.resolve()
    output = output.resolve()
    if source == output:
        raise ValueError("report-only adapter refuses to overwrite its source")
    report = build_report(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif output_format == "markdown":
        output.write_text(render_markdown(report), encoding="utf-8")
    else:
        raise ValueError(f"unsupported Hallmark report format {output_format!r}")
    return report


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    write_report(args.input, output, args.format)
    print(f"Wrote report-only Hallmark review to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
