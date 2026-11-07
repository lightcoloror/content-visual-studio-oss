#!/usr/bin/env python3
"""Validate insurance clause explanation objects and semantic preservation gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


FORBIDDEN_OVERCLAIMS = (
    "一定赔",
    "肯定赔",
    "百分百赔",
    "百分之百赔",
    "正规医院确诊即可",
    "合同生效后第一次确诊",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def format_schema_error(error: Any) -> str:
    location = ".".join(str(part) for part in error.path) or "$"
    return f"schema_error:{location}:{error.message}"


def iter_rule_fact_refs(rule: dict[str, Any]) -> Iterable[str]:
    yield from rule.get("fact_refs", [])
    for collection in ("all_of", "any_of", "none_of"):
        for condition in rule.get(collection, []):
            yield from condition.get("fact_refs", [])
    for collection in ("amount_rules", "time_rules", "limits", "exceptions"):
        for item in rule.get(collection, []):
            yield from item.get("fact_refs", [])
    for item in rule.get("state_changes", []):
        yield from item.get("fact_refs", [])


def iter_explanation_text(explanation: dict[str, Any]) -> Iterable[str]:
    yield explanation.get("one_sentence", "")
    yield explanation.get("plain_language", "")
    for collection in ("positive_examples", "negative_examples"):
        for example in explanation.get(collection, []):
            yield example.get("scenario", "")
            yield example.get("outcome", "")
            yield example.get("reason", "")


def validate_semantics(data: dict[str, Any], source_path: Path | None = None) -> list[str]:
    errors: list[str] = []
    source = data.get("source_document", {})
    page_count = source.get("page_count", 0)

    source_file = Path(source.get("source_file", ""))
    expected_hash = str(source.get("source_sha256", "")).lower()
    if source_file.is_file() and expected_hash:
        actual_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            errors.append("source_hash_mismatch")

    clause_ids: set[str] = set()
    global_anchor_ids: set[str] = set()
    global_fact_ids: set[str] = set()

    for unit_index, unit in enumerate(data.get("clause_units", [])):
        prefix = f"clause_units[{unit_index}]"
        clause_id = unit.get("clause_id", "")
        if clause_id in clause_ids:
            errors.append(f"duplicate_clause_id:{clause_id}")
        clause_ids.add(clause_id)

        local_anchor_ids: set[str] = set()
        for anchor in unit.get("source_anchors", []):
            anchor_id = anchor.get("anchor_id", "")
            if anchor_id in global_anchor_ids:
                errors.append(f"duplicate_anchor_id:{anchor_id}")
            global_anchor_ids.add(anchor_id)
            local_anchor_ids.add(anchor_id)
            page = anchor.get("page", 0)
            if page_count and page > page_count:
                errors.append(f"anchor_page_out_of_range:{anchor_id}")
            if (
                source.get("extraction_status") == "text_layer_corrupted"
                and anchor.get("transcription_method") == "text_extract"
            ):
                errors.append(f"corrupted_text_layer_used_as_verbatim:{anchor_id}")

        local_facts: dict[str, dict[str, Any]] = {}
        for fact in unit.get("facts", []):
            fact_id = fact.get("fact_id", "")
            if fact_id in global_fact_ids:
                errors.append(f"duplicate_fact_id:{fact_id}")
            global_fact_ids.add(fact_id)
            local_facts[fact_id] = fact
            for anchor_ref in fact.get("source_anchor_ids", []):
                if anchor_ref not in local_anchor_ids:
                    errors.append(f"dangling_anchor_ref:{fact_id}:{anchor_ref}")

        rule = unit.get("normalized_rule", {})
        for fact_ref in iter_rule_fact_refs(rule):
            if fact_ref not in local_facts:
                errors.append(f"dangling_fact_ref:{prefix}:normalized_rule:{fact_ref}")

        explanation = unit.get("explanation", {})
        explanation_refs = set(explanation.get("fact_refs", []))
        for fact_ref in explanation_refs:
            if fact_ref not in local_facts:
                errors.append(f"dangling_fact_ref:{prefix}:explanation:{fact_ref}")

        critical_facts = {
            fact_id for fact_id, fact in local_facts.items() if fact.get("critical") is True
        }
        for missing in sorted(critical_facts - explanation_refs):
            errors.append(f"critical_fact_missing_from_explanation:{clause_id}:{missing}")

        critical_by_kind = {
            kind: {
                fact_id
                for fact_id, fact in local_facts.items()
                if fact.get("critical") is True and fact.get("kind") == kind
            }
            for kind in ("time", "exception", "state_change")
        }
        structured_time = {
            ref for item in rule.get("time_rules", []) for ref in item.get("fact_refs", [])
        }
        structured_exceptions = {
            ref for item in rule.get("exceptions", []) for ref in item.get("fact_refs", [])
        }
        structured_exceptions.update(
            ref for item in rule.get("none_of", []) for ref in item.get("fact_refs", [])
        )
        structured_state = {
            ref for item in rule.get("state_changes", []) for ref in item.get("fact_refs", [])
        }
        for missing in sorted(critical_by_kind["time"] - structured_time):
            errors.append(f"critical_time_not_structured:{clause_id}:{missing}")
        for missing in sorted(critical_by_kind["exception"] - structured_exceptions):
            errors.append(f"critical_exception_not_structured:{clause_id}:{missing}")
        for missing in sorted(critical_by_kind["state_change"] - structured_state):
            errors.append(f"critical_state_change_not_structured:{clause_id}:{missing}")

        reverse = unit.get("reverse_paraphrase", {})
        if reverse.get("result") == "pass" and not all(reverse.get("checks", {}).values()):
            errors.append(f"reverse_pass_with_failed_check:{clause_id}")

        combined_text = "\n".join(iter_explanation_text(explanation))
        for phrase in FORBIDDEN_OVERCLAIMS:
            if phrase in combined_text:
                errors.append(f"prohibited_overclaim:{clause_id}:{phrase}")

    if data.get("review", {}).get("status") == "reviewed":
        for unit in data.get("clause_units", []):
            if unit.get("evidence_status") != "source_verified":
                errors.append(f"reviewed_with_unverified_unit:{unit.get('clause_id', '')}")
            for anchor in unit.get("source_anchors", []):
                if anchor.get("verified_against_render") is not True:
                    errors.append(
                        f"reviewed_without_verified_anchor:{anchor.get('anchor_id', '')}"
                    )

    return errors


def validate_document(
    data: dict[str, Any], schema: dict[str, Any], source_path: Path | None = None
) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [
        format_schema_error(error)
        for error in sorted(validator.iter_errors(data), key=lambda value: list(value.path))
    ]
    errors.extend(validate_semantics(data, source_path))
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    schema = load_json(args.schema)
    Draft202012Validator.check_schema(schema)
    paths = sorted(args.root.glob("insurance-clause-explanation.*.json"))
    if not paths:
        print(f"No insurance clause explanation fixtures found under {args.root}", file=sys.stderr)
        return 1

    failures: list[str] = []
    for path in paths:
        data = load_json(path)
        for error in validate_document(data, schema, path):
            failures.append(f"{path}: {error}")

    if failures:
        print("Insurance clause explanation validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"Validated {len(paths)} insurance clause explanation fixture(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
