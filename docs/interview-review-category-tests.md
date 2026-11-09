# Case Interview Guide Review Category Coverage Tests

`docs/interview-review-category-tests.md` documents the optional, source-only test suite in `tests/test_interview_review_category_coverage.py`, licensed under Apache-2.0. The suite validates structural category coverage against the bundled `schemas/case-interview-guide-review.v1.schema.json`.

## Invocation and Environment

Run the tests directly from the source checkout using existing Python project dependencies (`jsonschema`, `referencing`, and `rfc3339-validator`):

```bash
python -X utf8 -B tests/test_interview_review_category_coverage.py
```

The test reads one existing schema file, builds synthetic dictionary records in memory, and validates them via `Draft202012Validator` with an empty `referencing.Registry()` and a `FormatChecker`. The test source requests no temporary-file writes, network access, application or model operations. This is not an operating-system isolation certificate.

## Test Methods and Schema Invariants

The 7 `unittest.TestCase` methods evaluate schema containment across four mandatory categories: `non_leading_questions`, `privacy`, `fact_premises`, and `spoken_clarity`.

- **Coverage Rules**: All 4 categories must appear; permutations and duplicate check items are valid.
- **Fail-Closed Rejections**: Duplicate padding cannot compensate for an omitted category. Unknown categories, malformed check objects, or unauthorized decision/authority values are rejected even if coverage is otherwise complete.
- **Revision Record Shape**: Confirms `return_for_revision` validly accepts multiple checks with `blocked` status.

## Verification Boundaries

Coverage checks verify JSON Schema shape only. They do not evaluate question quality, verify factual premises, assess real privacy risks, or provide medical/insurance guidance. `approved_questions_only` and 64-character SHA-256 strings represent schema enum and pattern matches, not cryptographic bindings, author confirmation, or recording/publication consent. Owner verification under the existing CPython 3.13.5 environment passed all 7 methods, 0 skipped, against the exact already-public schema, with test and schema unchanged. A separate bad copy removed only the first category-coverage `contains` clause; the targeted missing-category method then failed in 5 subtests as expected. That bad schema is not distributed. The test detects this specific guard regression; it does not prove all possible schema weaknesses or a real review state transition.
