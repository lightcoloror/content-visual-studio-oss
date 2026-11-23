# PPT Master Integration Regression Test Source Guide

## 1. Purpose and Scope
This document specifies the regression source contracts for the paired PPT Master test suite under the Apache-2.0 license: `tests/test_ppt_master_adapter.py` (7 methods) and `tests/test_ppt_master_data_projection.py` (5 methods), totaling twelve methods. The source records expectations for adapter registration, template-fill gating and native chart projection. This increment bundles no external presentation template, rendering backend, font or operational dataset. Unprovided assets are not claimed to be synthetic or verified.

## 2. Source expectations (12 methods, all unexecuted)
The twelve regression tests partition into two distinct module scopes:

### PptMasterAdapterTests (7 Methods)
- **Registry and Protocol Invariants**: Expects default-off registry configuration, explicit protocol declarations, expected upstream commit pinning (`ec824aecd551a0bc2990b617a131d907a5d808ea`), and item-level fail-closed source root checks (retaining the intentional synthetic negative input `D:/unreviewed`).
- **Confirmation and Fallback Hard Checks**: Expects two-layer confirmation for template-fill operations and mandates fallback SVG dependencies alongside zero-baseline value axis constraints for native data generation.
- **Opt-In End-to-End Scenarios (3 Methods)**: All three require RUN_PPT_MASTER_INTEGRATION=1 and V4_ROOT.is_dir(); only the template-fill case additionally requires SOURCE_DECK.is_file(). Expects unified receipt output, confirmed-target template manipulation, and exact round-trip value assertions. The integration flag gates only these three scenarios, leaving module imports and baseline checks active.

### PptMasterDataProjectionTests (5 Methods)
- **Native Data Projection**: Expects projection of `grouped_bar` specifications into zero-based native column payloads preserving ordering and numerical values (`3.592132`, `3.005519`).
- **Fail-Closed Type and Value Guards**: Expects rejection of unmapped chart types (`split_lane`, `step`), mismatched series labels, and negative point values.
- **Deterministic Materialization and Cycle Prevention**: Expects checks of projection manifest hashing, detects stale SVG fallback modifications, supplies planned dependencies, and rejects circular artifact dependency graphs.

*Contract Clarifications*: Numeric values and inline gate passes are static test inputs, not real-world presentation acceptances, live fund figures, or rights clearances.

## 3. Dependencies and Verification Limits
- **Import Mechanics**: Both suites prepend `scripts` and `tests` directories to `sys.path` and load modules prior to test execution.
- **Verification Status**: All 12 test scenarios remain strictly **UNEXECUTED (NOT RUN)**. One actual frozen command successfully used stdlib ast.parse and compile on both provided source files, returned their exact hashes and 7+5 method counts, and ended with COMPILE_EXIT=0. The test modules, setup and helpers were not imported or executed; no external schema, registry manifest, fixture, spec, deck or backend body was read. No runnable quickstart is provided.

## External input and evidence boundaries

Both complete source modules are already LF and remain byte-identical to the
provided first-party working snapshots: 400 + 170 lines. This is not proof of
historical Git inclusion. No new dependency, fixture, template or renderer is
distributed. Apache-2.0 covers this first-party test glue, not unprovided inputs.

The three integration decorators do not opt out the whole adapter module.
Imports run before decorators can skip methods. The four other adapter methods
read registry and registry-referenced manifest/data inputs. All five projection
methods use setUp to read an external fund spec, and some write temporary files,
render SVG or materialize projections when actually run. Both modules prepend
scripts/tests paths; path binding is not import isolation or an OS sandbox.
Compatible ROOT/WORKSPACE layouts, schemas, briefs, fill plans, review manifests,
PPT Master runtime, source decks and other fixtures remain unprovided/unread.
Do not replace them with fabricated public inputs to manufacture passing tests.

The D:/unreviewed string is a deliberately rejected root in a negative test,
not a discovered workstation location. The v4.5 pin
ec824aecd551a0bc2990b617a131d907a5d808ea, thirteen logical groups,
one confirmed fill target and numerical values 3.592132/3.005519 are historical
case expectations, not current upstream, financial or runtime facts. Inline
fact/rights/privacy pass fields are test input, not actual clearance.

Importing or calling render_data_explanations/Lieflat from a regression test
does not distribute or clear that separately held implementation. Its actual
adopted source revision and redistribution provenance remain unresolved.
No Office, browser, rendering, font, media or real-data acceptance was performed.
The Gemini guide review received the full projection source and adapter
header/decorators plus prior-review facts, not the entire adapter body; Owner
reused the hash-matched earlier complete review and checked this frozen range.
