# Visual Profile Registry Regression Test Source Guide

## 1. Purpose and Scope
This document specifies the regression source contracts for `VisualProfileRegistryTests` in `tests/test_visual_profile_registry.py` under the Apache-2.0 license. The source expresses expectations for selected profile values, token/text matching, CMS exposure, semantic color roles and an external validator response. This increment adds no font, profile body, theme file, fixture or third-party binary.

## 2. Five Source Expectation Categories
The five unchanged regression methods express these source expectations, not executed scenario results:

- **Default Profile Pinning**: Asserts the default broker visual profile maps strictly to `visual/insurance-observational-advisor` pinned at version `0.2.0`.
- **Exact Token Palette and CSS Alignment**: Validates an exact five-color token dictionary (`ink: #243238`, `brand_teal: #245B5A`, `human_accent: #AD4E3D`, `paper: #F7F8F5`, `mist: #DDEBE9`) and checks case-insensitive literal occurrence within the theme CSS.
- **Admin Configuration Exposure**: Verifies that the Sveltia admin configuration explicitly references the profile identifier.
- **Non-Risk Semantic Role Constraints**: Asserts contract semantics explicitly declare `human_accent` as "不自动表示风险" (not automatically indicating risk) with matching cautionary usage rules.
- **Validator Subprocess Contrast Rejection**: If run, the final scenario would execute a child subprocess against `validate-content-profile-refs.py` with an invalid low-contrast fixture, asserting process exit code `1` and stderr output containing `"below 4.50:1"`.

*Note*: These assertions expect selected dictionary values and text/regex relationships; they do not independently verify a complete profile schema, computed contrast, physical colorimetry, accessibility, device displays or financial/clinical facts. The exact palette applies only to the named historical 0.2.0 case, not a universal IP palette or replacement for object/data color meanings.

## 3. Environment Resolution and Legacy Layout
To eliminate hardcoded root assumptions, the suite resolves workspace paths via `CONTENT_STUDIO_TEST_VISUAL_PROFILE_WORKSPACE`:
- The variable is stripped and validated; unset, blank, or non-directory paths raise a fail-closed `ValueError`.
- Relative paths resolve against the process current working directory (`cwd`) using `Path.expanduser().resolve()` without implicit fallback defaults.
- Preserves explicit legacy layout targets relative to root: `docs/content-creation-system/profiles/profile-registry.json`, `content-studio-poc/admin/config.yml`, `content-studio-poc/themes/insurance-observational-advisor.css`, `scripts/validate-content-profile-refs.py`, and `content-studio-poc/tests/fixtures/invalid-low-contrast-profile-registry.json`.

## 4. Verification Status and Limits
- **Module Import Behavior**: Importing the test module loads standard libraries, defines classes, and constructs path objects; it checks root-directory metadata but does not invoke setUpClass, read registry/admin/theme/fixture bodies, or spawn the external validator during the controlled import.
- **Execution Status**: All 5 test methods remain strictly **UNEXECUTED (NOT RUN)**.
- **Audit Boundaries**: Review includes the complete original 86-line source, preserved five-method/class-setup/other-module AST, and the root-binding change. Directory existence alone does not establish a complete or compatible legacy workspace. No validator subprocesses, browser rendering, contrast calculation engines, or network operations have been executed. No runnable quickstart command is provided due to decoupled legacy workspace dependencies.

## Actual bounded import controls
One frozen Python 3.13.5 command passed seven controls: unset, blank, missing
directory and a file value reject; absolute, relative and whitespace-trimmed
existing directory values import the real candidate and bind the expected
ROOT and five derived paths. The supplied directory contains test source, not
registry or contrast fixtures. No original scenario or class setup ran. The
test's future validator subprocess has not been exercised here; its expected
exit code/stderr are not measured color or accessibility results.

The original compatible registry/config/theme/validator/fixture bodies remain
external and were not supplied, read, reconstructed or claimed synthetic. No
quickstart or new production/review gate is introduced. Process/path binding
is not an OS sandbox, data-authority grant, fixture-completeness check or rights
clearance. No private historical workspace was rebuilt for source publication.
