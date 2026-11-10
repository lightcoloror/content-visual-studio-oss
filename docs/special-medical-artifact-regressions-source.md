# Special Medical Artifact Regressions Source Adaptation

## Operator Input Bindings & Scope
The regression suite in `tests/test_special_medical_official_artifacts.py` adapts hardcoded private fixture paths to three explicit operator environment variables:
1. `CONTENT_STUDIO_SPECIAL_MEDICAL_ITEM_PATH`: Content item JSON path.
2. `CONTENT_STUDIO_SPECIAL_MEDICAL_CONTENT_SCHEMA_PATH`: Caller-selected content schema path; receipts retain the original expected content contract version 0.2, without independently authenticating the supplied schema.
3. `CONTENT_STUDIO_SPECIAL_MEDICAL_RENDERER_PATH`: External renderer module path.

Missing variables raise ordinary `KeyError`. Repository `ROOT` continues governing relative artifact/receipt refs and public receipt schema validation; no universal relocated-artifact sandbox compatibility is claimed.

## Expected Contracts vs Non-Execution Status
The four regression tests declare static source expectations:
1. **Schema & Receipt Contracts**: The source expects supplied item/receipt validation to return no errors and checks declared review statuses, hard-check statuses and HTTPS evidence prefixes.
2. **Rendering Idempotency**: The source expects two SVG renders to match, compares SVG text to the saved output, and compares one generated PNG buffer to the saved artifact hash; these fixture-specific expectations were not executed.
3. **PNG Nonblank Thresholds**: Checks timeline PNG bounding-box difference thresholds (>70% width, >55% height).
4. **SVG CJK & Canvas Dimensions**: Asserts canvas dimensions, series label presence, and font string `"Microsoft YaHei"`.

**Execution Status**: All four original tests are **NOT RUN**. Owner non-executing compile and complete AST comparison passed: all original functions/classes, four method bodies and 24 assertion calls are unchanged except three global bindings and os import. Six isolated in-memory binding controls passed (supplied and missing value for each input); they read no actual file and changed no OS environment. Tests require third-party packages (`Pillow`, `jsonschema`) and an external renderer backend; unfulfilled imports will halt execution prior to test collection.

## Verification & Clinical Boundaries
- **Clinical & Evidence Validity**: Fixture assertions (e.g., `"verified"`, HTTPS URLs) reflect schema metadata consistency, not clinical GRADE evaluation, medical truth, or regulatory clearance.
- **External Dependencies**: The external renderer is not bundled; font and dependency rights remain uncleared (Status C). Font name references remain plain string checks, not font distribution or licensing proof.
- **Idempotency Scope**: Fixture-specific hash matching does not prove general renderer determinism.
- **Governance**: First-party Apache-2.0 distribution only; requires independent Owner authorization. No actual health records, browsers, networks, or models were accessed.


No original module, renderer, item, receipt, content schema or image was imported/read/executed by these controls. Caller schemas may have unresolved external references; this retained source is not a network sandbox. The external backend source/rights review remains separately held; the string assertion is not a Windows font distribution or availability test. No stub schema, mock backend, historical outputs or fabricated clinical evidence is supplied. Source-checkout layout and original expectations are retained, not proven portable across actual renderer/library/schema versions.
