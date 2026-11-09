# Original Synthesis Generalization Tests

`docs/synthesis-generalization-tests.md` documents the optional, source-only unit test suite in `tests/test_original_synthesis_generalization.py`, licensed under Apache-2.0. The suite exercises topic isolation and schema compilation rules across 10 synthetic test methods, adapting the test calls to existing synthesis adapters (`scripts/original_synthesis_adapter.py`, `scripts/qrp_owner_binding.py`, and `qrp_candidate_adapter`) and their public Question-Research-PoC (QRP) interface. Production code and dependencies are unchanged.

## Execution and Environment

Run the tests from a task-owned isolated working copy of ContentStudio using existing Python dependencies:

```powershell
$env:CONTENT_STUDIO_QRP_ROOT = (Resolve-Path -LiteralPath "<existing-public-qrp-checkout>").Path
python -X utf8 -B tests/test_original_synthesis_generalization.py
```

- **QRP Source Binding**: `$env:CONTENT_STUDIO_QRP_ROOT` must point to an operator-supplied public `question-research-poc` repository containing `src/question_research_poc/bounded_deep_loop.py`. The `bind_qrp` helper verifies that imported modules match the source tree and rejects mismatched installed distributions; it never falls back silently.
- **Isolated Workspace**: Per-test scratch directories are managed by `isolated_test_directory`, which creates and tears down synthetic files (the suite is not read-only). Scratch files use `CONTENT_STUDIO_TEST_TEMP_ROOT` if configured, defaulting to `outputs/.test-runtime/temp` within the source checkout. Bare `TEST_TMP_ROOT` is not required.
- **Standalone Scope**: These 10 unit tests require no Main owner environment, tool registry, or execution history.

## Test Methods and Verification Boundaries

The 10 `unittest.TestCase` methods evaluate structural compile invariants: topic ID separation, canvas-free multi-claim formatting, trace preservation, preflight rejection and partial-file persistence recovery, and fail-closed rejections for drifted quotes (`quote_source_drift`), unverified facts (`source_fact_not_admitted`), missing evidence (`evidence_link_drift`), unauthorized authority promotion (`authority_escalation`), unknown claims (`unknown_claim`), and a declared incomplete capture (`source_fact_requires_complete_capture`).

All research inputs, quotations, and editorial plans are synthetic fixtures. Synthesized outputs remain candidate drafts requiring human review. Structural topic separation, metadata hashes, and quotation matches do not prove semantic writing quality, prose naturalness, factual truth, or copyright clearance. No LLMs, network calls, browser sessions, audio generation, or publication pipelines are run. Owner verification used CPython 3.13.5, an isolated copy of ContentStudio at `797d4cce`, and the actual public QRP source at `a9cb1ac4`: 10 methods passed, 0 skipped, with all 27 original assertion calls and exact rejection-code assertions retained. Two separate configuration controls failed as expected before any methods ran (exit 5): missing owner environment and nonexistent owner source. No missing-owner case was skipped or replaced by a mock. AST parsing and source comparison covered the adapted test; this was not a full project regression or installed-wheel check.

The selected owner supplies executable Python and its existing source/schema checks; choosing a path does not establish code trust or evidence truth. No Main registry, history recreation, QRP checkout writes, new runtime installation, or product-code changes were required.
