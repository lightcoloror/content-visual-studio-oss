# Social Card Font-Gate Receipt Contract Guide

## 1. Purpose and Scope
This document specifies the regression contracts for the three first-party tests in `SocialCardTypographyReceiptTests` under Apache-2.0. The source expresses evidence-binding expectations for social-card font-gate receipts without bundling third-party fonts, external rendering engine code, or operational assets. All test definitions, assertions, and dictionaries remain strictly identical to source (with LF line endings normalized).

## 2. Source Expectations (Not Executed)
The unchanged regression methods assert three explicit expectations:

- `test_font_gate_is_a_required_hard_check`:
  Verifies that querying `required_hard_checks` for artifact configuration `qa_profile: "social-card-html.v1"` includes `"font-size-gate"`. This inspects profile QA configuration requirements; it does not perform font measurement or layout rendering.
- `test_passed_font_gate_is_preserved_in_receipt`:
  Confirms that `_attach_renderer_receipt_evidence` binds an explicit `font_gate` dictionary into `receipt["font_gate"]`. The inline fields (`passed: True`, `font_px: 60`, generic policy/profile IDs) are mock test inputs; the helper passes through `details.get("font_gate")` without verifying policy hashes, text geometry, visual readability, or intellectual property rights.
- `test_missing_font_gate_evidence_is_explicitly_failed`:
  Verifies that when `details` is empty (`{}`), the helper records `passed: False` and `failures: ["missing-font-gate-evidence"]`. This asserts receipt recording behavior; it does not prove downstream publication pipelines actively block release.

## 3. Dependency Boundaries and Verification Status
- **Format Scope**: Covers only the `social-card` artifact type; it does not claim universal coverage, audio/BGM, subtitles, or generalized canvas geometry.
- **Dynamic Dependency**: The module dynamically imports `scripts/render_content_artifacts.py` via `importlib.util` at top level. The complete renderer is a separate pending component (`edf75b6`) that is not approved, bundled, or published here. File presence does not guarantee runtime compatibility.
- **Execution Limits**: All 3 test methods are strictly **UNEXECUTED (NOT RUN)**. Verification is restricted to owner compile-only syntax checks, AST equality verification, and inspection of the complete 54-line test source plus two exact callee bodies, not a full renderer audit. No fonts, browsers, network calls, or runnable quickstart commands are provided.
