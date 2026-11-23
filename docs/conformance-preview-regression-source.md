# Conformance & Preview Regression Source Reference Guide

Destination: `docs/conformance-preview-regression-source.md`
License: Apache-2.0

## 1. Purpose
This document provides operator reference documentation for two complete first-party Python regression test suites:
- `tests/test_global_visual_language.py` (7 test methods)
- `tests/test_obsidian_preview_adapter.py` (3 test methods)

Together, these 10 test methods define the regression contract for global visual conformance receipts, media QA bridges, and fail-closed preview adapter boundaries. This documentation establishes a generic source-only reference under Apache-2.0; it does not claim that these test suites constitute a standalone runnable package on current `main`, nor does it assert past or present runtime passes.

## 2. Regression Source Specification Table

| Source File | Method Count | Source Assertions (Not Executed) | Dependencies & Import Architecture | I/O & Isolation Conditions |
|---|---|---|---|---|
| `tests/test_global_visual_language.py` | 7 methods | • Locked runtime context (`authority_scope: "global-only"`, `conformance_profile: "article.v1"`)<br>• Rejection of unknown rules, expired exceptions, and ruleset SHA-256 hash drift<br>• P0 blocking failures prevent approval; P1 failures report without blocking<br>• Sveltia CMS integration keeps authority read-only<br>• Conformance receipt hashes and media QA bridges enforced | • `PyYAML`<br>• `global_visual_validation.py` (present on approved `main`)<br>• `render_artifact_validation.py` (located on the separately published shared-validator feature branch (commit `b54a141`), not on current `main`)<br>• **Import Architecture**: Prepends `ROOT/scripts` then `WORKSPACE/scripts` to `sys.path`. Parent workspace directories can shadow root scripts; this is a monorepo path convention, not an import sandbox. | • `setUp` writes synthetic `output.html` under `outputs/.test-runtime/<testMethodName>/`; `item.json` is a path reference, not a setup-created file. The receipt-link method also writes two JSON receipts; `tearDown` removes local files and the test directory.<br>• Uses synthetic item/QA/receipt dictionaries, including declared pass flags. These are test inputs, not real-world rights, factual, clinical or human review clearances. |
| `tests/test_obsidian_preview_adapter.py` | 3 methods | • Adapter requires explicit opt-in (`explicit_adapter: True`); fails closed when off<br>• Source asserts adapter rejection of one synthetic `.obsidian/plugins/` target<br>• Deterministic zip archive generation and listing (`BUILD_RECEIPT.json`, `LICENSE`, `main.js`, `manifest.json`, `styles.css`)<br>• Enforces license metadata review (`package_json: MIT` vs `LICENSE: ISC` triggers `license_metadata.review_required: True`) | • Dynamically imports `ROOT/scripts/render_content_artifacts.py` via `importlib.util`. That renderer candidate (`edf75b6`) is a local pending candidate, not approved or published on current `main`. | • `setUp`/`tearDown` creates and removes `outputs/.test-runtime/<testMethodName>/`<br>• The source constructs a synthetic path for the refusal assertion; that assertion has not been executed here; no actual Obsidian vault, desktop application, or external file system was accessed or modified. |

### Complete Method Inventory (10 Methods)
1. `GlobalVisualLanguageTests.test_runtime_context_is_locked_and_matches_medium`
2. `GlobalVisualLanguageTests.test_wrong_medium_unknown_rule_and_expired_exception_are_rejected`
3. `GlobalVisualLanguageTests.test_ruleset_hash_drift_is_rejected`
4. `GlobalVisualLanguageTests.test_active_p0_failure_blocks_approval`
5. `GlobalVisualLanguageTests.test_p1_icon_imagery_and_ai_failures_are_reported`
6. `GlobalVisualLanguageTests.test_sveltia_exposes_new_fields_and_keeps_authority_read_only`
7. `GlobalVisualLanguageTests.test_conformance_link_hash_and_media_qa_bridge_are_enforced`
8. `ObsidianPreviewAdapterTests.test_preview_remains_explicit_item_only`
9. `ObsidianPreviewAdapterTests.test_preview_refuses_vault_destination`
10. `ObsidianPreviewAdapterTests.test_builds_deterministic_review_only_package`

## 3. Execution Model & Local Opt-In Reality
These tests represent developer regression contracts rather than zero-configuration public test suites:
- **Dependency Split**: Current `main` (`d129`) provides `global_visual_validation.py` and `admin/config.yml`. However, executing `test_global_visual_language.py` requires `render_artifact_validation.py` (available on the shared-validator feature branch `codex/shared-render-validation-source-20261109` at commit `b54a141`). Executing `test_obsidian_preview_adapter.py` requires an operator-supplied compatible renderer corresponding to `scripts/render_content_artifacts.py`.
- **Selective Integration Opt-In**: The third preview method, `test_builds_deterministic_review_only_package`, is gated by the decorator `@unittest.skipUnless(os.environ.get("RUN_OBSIDIAN_PREVIEW_INTEGRATION") == "1", ...)`. Without this explicit environment variable, the integration test is skipped by default.
- **No Turnkey Command / No Execution Claim**: This documentation does not present a turnkey execution command or claim test execution passes. The tests were not run during this documentation increment; Owner verification is restricted to non-executing AST, syntax, and diff inspection.

## 4. Source, Licensing, and Verification Limits
- **First-Party Licensing**: Both test files and their documentation are licensed under Apache-2.0.
- **Obsidian Package License Discrepancy**: In `test_builds_deterministic_review_only_package`, the test specifically verifies that an internal discrepancy between package metadata (`MIT`) and license text (`ISC`) generates a `review_required: True` flag. This assertion tests discrepancy detection; it is not a grant of third-party rights, an endorsement of shipping pre-built plugins, or a relicensing of first-party code.
- **Security & Sandbox Boundaries**:
  - The `sys.path` manipulation in `test_global_visual_language.py` prepends the parent workspace's `scripts` directory after prepending the local one, so the parent directory can shadow local scripts. It is not an isolated sandbox.
  - The source test expects an adapter rejection of its constructed path. This documentation step neither executed the check nor establishes how the compatible adapter implements it; no operating-system boundary is proven.
- **Verification Limits**: No external packages, Obsidian instances, browsers, fonts, or network services were executed, installed, or cleared. Synthetic gate values (`fact: pass`, `rights: pass`, `privacy: pass`) remain mock data. All runtime behaviors remain unverified.
## Source-only verification record

The global-visual source is byte-identical to its reviewed snapshot. The preview source differs only by CRLF-to-LF normalization; its full AST, assertions and integration decorator are unchanged. The original snapshot and first diff-check error are retained outside the public range.
Non-executing Python AST parsing confirms all ten original methods remain in
the source. No Python statement or assertion was rewritten, and the original integration
decorator is unchanged. All ten methods are NOT RUN in this increment: no
module import, setup, teardown, filesystem write/cleanup, vault access or
plugin packaging was attempted. A default opt-in decorator is not a runtime
skip result for this increment. These historical source assertions do not
establish current policy calibration or add a new workflow/publication gate.
