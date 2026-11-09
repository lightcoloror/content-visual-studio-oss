# Insurance Clause Explanation Regression Test Source Guide

## 1. Purpose and Scope
This document specifies the regression source contracts for the thirteen test methods in `InsuranceClauseExplanationTests` under the Apache-2.0 license. The source expresses selected schema/error expectations, negative mutations and an optional PDF hash check for structured clause explanations. This increment adds no external schema, policy PDF, validator backend or customer record. Unprovided assets are not claimed to be synthetic or rights-cleared.

## 2. Test Coverage Groups (13 Methods)
The suite groups thirteen regression methods into three compact functional categories:
- **Golden Baseline Validation (1 Method)**:
  `test_golden_fixture_is_valid` asserts that an unmutated golden clause fixture produces zero validation errors against the canonical schema.
- **Negative Mutation and Structural Guards (10 Methods)**:
  These methods expect rejection of selected corrupted, omitted or contradictory inputs; the underlying validator and inputs were not exercised here:
  - Requires explicit negative examples and rejects duplicate clause IDs.
  - Rejects dangling fact references, omitted critical facts, destructured exceptions, and unmodeled state changes.
  - Forbids passing reverse-paraphrase status when constituent checks fail.
  - Rejects prohibited plain-language overclaims (such as absolute payout guarantees).
  - Flags `reviewed` status without render-verified anchors and prevents corrupted text layers from supplying verbatim source text.
- **Fact Stability and PDF Integrity (2 Methods)**:
  - `test_product_specific_golden_facts_are_stable` checks literal fixture values (e.g., 180-day waiting period, accident exceptions, birth diagnosis terms, zero cash value). These represent static source expectations, NOT verified current policy terms, medical conclusions, or legal/financial advice.
  - `test_source_hash_matches_user_pdf_when_present` checks `source_document.source_file`, skipping if the file is absent or verifying SHA-256 if present. The path can resolve outside `ROOT` without sandbox containment.

## 3. Path Dependencies and Verification Limits
- **Import and Setup**: The module dynamically executes `validate_insurance_clause_explanations.py` at import time; `setUp` loads schema and fixture files from relative workspace locations.
- **Execution Status**: All 13 scenarios remain strictly **UNEXECUTED (NOT RUN)**. One actual frozen command successfully used stdlib `ast.parse` and `compile` checks. The test and validator modules were not imported or executed, and no schema/fixture JSON or PDF body was read. No runnable quickstart is provided.

The compile-only result identified 13 methods and returned COMPILE_EXIT=0.
All 156 source lines and the complete AST are preserved after CRLF-to-LF
normalization. There were no original-scenario runs; the optional PDF skip was
not triggered or counted as success. A present fixture-specified PDF would be
read without an additional opt-in flag if the original final test were invoked.
No product-specific input was replaced by a fabricated public fixture.
Compatible external schema, product fixture and validator remain required for
the real tests, with their data rights and correctness unverified. The source
is a first-party working snapshot, not historical Git-inclusion evidence.
