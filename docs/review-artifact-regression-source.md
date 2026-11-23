# Review Artifact Regression Test Source Guide

## 1. Purpose and Scope
This document specifies the regression contracts for `BlockedRenderOutputTests` in ContentStudio under the Apache-2.0 license. The four first-party test methods express expectations about selected HTML substrings, SVG polyline/label text and vertical text coordinates in already-rendered review artifacts without bundling external JSON, HTML, SVG, fonts, or private operational histories. Unprovided inputs are not claimed to be synthetic, verified, or publicly licensed.

## 2. Test Expectations and Contract Boundaries
If run with compatible inputs, the four methods would check these selected structural and substring expectations:
- `test_policy_company_split_lane_has_no_cross_track_line`: Checks selected SVG text referenced from `content/items/data-insurance-rate-step-chart-20260801.json`, ensuring no `<polyline` elements exist and asserting literal substrings "监管上限" and "中国人寿".
- `test_concept_lane_output_has_no_slope_line_and_keeps_product_blank`: Checks selected SVG text referenced from `content/items/data-insurance-rate-concept-lanes-20260801.json`, ensuring no `<polyline` elements and asserting literal substring "未提供具体产品".
- `test_review_html_is_offline_and_has_manual_boundary`: Asserts `outputs/data-medical-payment-denominator-20260801/chart.html` contains none of the literal substrings `src="http`, `href="http`, or `<script`, and contains "manual-only".
- `test_rendered_svg_text_stays_inside_canvas`: Discovers `outputs/data-*/chart.svg`, asserting `max(text_y) <= height`. The adapted suite asserts a non-empty glob match before iterating to prevent false passes.

*Contract Clarifications*:
- Expected text tokens are literal test markers, not verified actuarial, insurance, or clinical claims.
- HTML substring checks express selected offline expectations, not complete browser security, CSP, or sandbox proofs.
- Text bounding checks assert `max(text_y) <= height`, not device rendering, glyph clipping, or readability.
- `Path(ref)` resolves from process `cwd` if relative, or externally if absolute; it is independent of `ROOT` and not an OS sandbox. Root directory existence does not imply input completeness.

## 3. Environment Resolution and Verification Status
- **Workspace Binding**: The environment variable `CONTENT_STUDIO_TEST_RENDER_WORKSPACE` is required. It strips whitespace and raises a fail-closed `ValueError` if unset, blank, non-existent, or pointing to a file. Relative paths resolve against process `cwd` without fallback.
- **Execution Limits**: All 4 original scenarios remain strictly **UNEXECUTED (NOT RUN)**. One frozen Python 3.13.5 command passed seven real module-import/root-binding controls and two extracted-method empty-glob expected-rejection controls. The old method silently passed the same empty-glob counterexample; the adapted guard rejected it. These controls did not run any complete original artifact scenario or read artifact bodies. The two empty-glob states were modeled in memory, not real missing/empty output directories. Base aligns with public commit `d129d25dc850626a8add11ace21d0c724c813de2` with no dependency on pending renderer branches. No runnable quickstart is provided.

The required external item JSON, referenced SVG and review HTML are not distributed or reconstructed here. No renderer is imported during the bounded controls. Importing the source does inspect root-directory metadata and read the Python source; it is not zero-I/O. A directory-only source input is not a compatible historical artifact fixture. This increment adds no production gate, routing, schema, database or new dependency. Source provenance is an existing first-party working snapshot, not proof of private Git-history inclusion.
