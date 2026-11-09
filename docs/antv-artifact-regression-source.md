# AntV Artifact Pipeline Regression Test Source Guide

## 1. Purpose and Scope
This guide specifies the regression source contracts for `AntvArtifactPipelineTests` under the Apache-2.0 license. This increment retains every line and the complete AST of the first-party source, with CRLF normalized to LF. Its two methods express budget/fixture and optional Chinese PNG expectations for eight templates. The increment adds no renderer, external font, config or fixture. Unprovided inputs are not claimed to be synthetic or verified.

## 2. Test Method Expectations (Two Methods)
The suite defines exactly two test methods covering eight template configurations:
- `test_every_allowlisted_template_has_a_budget_and_fixture`:
  Asserts that `validate_budget_registry_coverage()` returns no errors, confirms exactly eight template budgets exist in `config/slot-budgets.v1.json`, ensures each `fixtures/antv/<template>.ifgc` exists, and validates each template against its declared layout intent with zero budget errors.
- `test_eight_chinese_templates_render_to_nonblank_chromium_png`:
  Gated by `@unittest.skipUnless(os.environ.get("RUN_VISUAL_INTEGRATION") == "1", ...)`. For each of the eight templates, it expects an 800x1000 PNG output, a `"Microsoft YaHei"` font-family text marker in SVG, absence of external `"assets.antv.antgroup.com"` asset substrings, presence of CJK characters (`\u4e00`–`\u9fff`), and an image non-blank ratio >= 0.01.

*Contract Clarifications*:
These criteria represent structural source expectations, not physical rendering fidelity, typography readability, complete network isolation guarantees, or font licensing clearances.

## 3. Import Lifecycle, Cleanup, and Verification Limits
- **Import Mechanics**: The module prepends `scripts` to `sys.path`, loads Pillow and rendering backends, and reads JSON configs at import time before `skipUnless` evaluates. At public base `d129d25dc850626a8add11ace21d0c724c813de2`, the slot-budget validator and two named config paths exist, while render_content_artifacts.py and fixtures/antv are absent. Name presence does not establish API, version or fixture compatibility; the pending renderer is not included in this increment.
- **Fixed Runtime Cleanup**: When visual integration runs, the method creates a fixed directory at `outputs/.test-runtime/antv-eight-templates` and unlinks each immediate child for which is_file() is true and then attempts to remove the directory in finally. Operators must account for this lack of concurrency isolation.
- **Verification Status**: Both test scenarios remain strictly **UNEXECUTED (NOT RUN)**. One frozen Python compile-only command actually passed ast.parse and compile on the byte-identical CRLF peer source, with COMPILE_EXIT=0. Owner separately confirmed the LF public source has the same complete AST and source lines. The module was not imported, no original scenario ran, and no render or cleanup was exercised. No runnable quickstart is provided.

The skip flag does not suppress import-time backend/config work or the first test. Neither fixture provenance nor third-party/font redistribution rights follow from filenames, expected text or a successful syntax check. No dependency installation, fixture substitution, historical environment reconstruction or new production gate was added.
