# Chart Specification Regression Test Source Guide

## 1. Purpose and Scope
This document provides the reference regression specification for the data explanation chart suite in ContentStudio under the Apache-2.0 license. The complete source defines fourteen methods in tests/test_data_explanation_specs.py for chart input, validator expectations, rendering contracts and evidence-binding checks. This increment bundles no renderer, chart-spec bodies, fonts or clinical records and does not claim execution of the original scenarios.

## 2. Source Coverage Categories (14 Methods)
The complete existing suite retains fourteen methods. This describes source
expectations, not executed results or independently verified policy facts:

- One method enumerates *.json files and calls the existing validator for
  each. A new nonempty-list assertion prevents zero-loop false passes.
- Three rate-chart methods cover exact effective_start values, split-lane
  categories and rejection of linear interpolation for regulatory-ceiling data.
  They do not independently establish legal requirements or real rate values.
- One method expects rejection of an unknown top-level field; another expects
  all HTML/SVG/PNG review output references. These do not prove a complete
  schema implementation, concurrent rendering or synchronized artifact bytes.
- Eight special-medical scenario methods expect evidence-binding fields,
  dangling-reference/stale/conflicting/scope-mismatch/unknown-value rejection,
  a timeline-note budget, and deterministic SVG/canvas dimensions/content.
  These are historical scenario assertions, not clinical findings or evidence
  verification results. The thirteen other method bodies and load() remain
  unchanged, including all original basenames, assertions and geometry checks.

## 3. Environment and Directory Input Semantics
The regression runner eliminates hardcoded repository path assumptions by resolving test specifications through an explicit environment variable:
- **`CONTENT_STUDIO_TEST_CHART_SPEC_ROOT`**:
  The suite requires this environment variable to be explicitly configured. Leading and trailing whitespace is stripped. If the variable is unset, empty, whitespace-only, or points to a non-existent directory, the loader immediately raises a fail-closed `ValueError`.
- **Path Resolution**: Relative paths are expanded and resolved against the invoking process's current working directory (`cwd`) via `Path.expanduser().resolve()`. No fallback defaults are assumed.
- **Discovery Guard**: `SPEC_ROOT.glob("*.json")` is sorted and checked for non-zero count; zero matched fixtures cause an immediate assertion failure.

## 4. C-Held Backend and Intellectual Property Boundaries
- **Dynamic Module Loading**: The harness dynamically imports `scripts/render_data_explanations.py` using `importlib.util`. This backend module represents an unbundled, C-held component with unresolved third-party Lieflat reference payload licensing rights. This increment neither includes nor approves that renderer and makes no license grant for its referenced or copied payload. The held module is not a prerequisite to distributing the independent first-party test source; it remains a dependency for running the original scenarios.
- **Unprovided Scenario Inputs**: No original chart-spec bodies were supplied, read or fabricated. Their filenames and expected strings in the source do not establish that all inputs are synthetic, provenance-verified or rights-cleared. Actual scenario tests require compatible authorized specifications; arbitrary JSON is not an equivalent replacement, and source assertions are not medical/actuarial advice or verified clinical evidence.

## 5. Actual Checks and Limits
The Owner compiled the complete candidate without importing it, compared all
other module AST and thirteen unchanged methods/load(), and ran one bounded
stdlib probe: seven directory-binding controls and two expected-failure
controls over the extracted adapted enumeration method. An existing task
source directory containing no chart JSON and a nonexistent path both reject
before renderer access. The nonchart directory is a negative input, not a
fabricated chart fixture. No original chart scenario ran; one adapted method
body was exercised twice in that isolated negative-control context.

No renderer import, chart JSON reading, canvas/font/image operation, fixture or
temporary-file creation, network, model, service, browser, installation or
knowledge-base write occurred in the probe. The prior PowerShell-parser and
filesystem-suite refusals were not retried. Directory resolution is not an OS
sandbox, file integrity check, dataset validation or rights/clinical clearance.
This is a test-input precondition, not a new production or publication gate.
There is no turnkey test command here because the original inputs and held
renderer are not supplied or verified. Actual scenario validation remains a
separate task under existing runtime and authorization procedures.
