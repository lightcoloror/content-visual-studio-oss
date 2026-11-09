# render_content_artifacts.py public-source guide

Source-only port of the existing first-party content-artifact orchestrator
`scripts/render_content_artifacts.py`, full original SHA-256
`94ab8ec32991cf575f177ea82858c3e9feba56b92f003bcca35357b6975fc165`.
No renderer, platform, router, configuration system, database or provider was
added. This guide describes the bounded portability changes and the limits of
what has actually been verified.

## Provenance and dependency boundary

- Original logical source: `scripts/render_content_artifacts.py`, 2241 lines,
  SHA-256 `94ab8ec32991cf575f177ea82858c3e9feba56b92f003bcca35357b6975fc165`.
- Candidate: the public-source form of that same module, `render_content_artifacts.py`.
- Published validator dependency: `render_artifact_validation.py`, accepted
  public source SHA-256
  `0c81cc98940a2a1c7b4e2459113e80a002c35b883a6cf61bb48a9923a1043a9d`.
  It is reused unchanged from this repository's published validator branch; this
  increment does not copy or modify it.

Private review provenance, task receipts and verification logs are kept
separately and are not part of this public source guide.

## Scope of change

Only roots, explicit runtime discovery and the held-backend import boundary
changed. Every original function, API, renderer branch, media-QA profile,
retry cap (`MAX_RENDER_RETRIES = 2`) and retryable-check whitelist
(`RETRYABLE_QA_CHECKS`), source/hash/receipt binding, consent/rights/privacy/fact
gate, manual-approval boundary and receipt field was retained. No unsupported
renderer branch was deleted and no toy replacement was substituted.

The published `config/renderer-registry.v1.json` snapshot is unchanged. That
snapshot describes only `antv-infographic`; availability of the other historical
renderer modes is unverified and is not claimed.

## Root resolution

- Imports `STUDIO_ROOT` / `SOURCE_ROOT` from the published `studio_paths`
  module; the private `parents[1]` workspace bootstrap and
  `WORKSPACE_ROOT`/`WORKSPACE_SCRIPTS` probe were removed.
- `STUDIO_SCRIPTS` is the module's own public scripts directory.
- `SCHEMA_PATH` → `STUDIO_ROOT/schemas/content-item.schema.json`.
- `_global_visual_data_status` → `STUDIO_ROOT/visual-contracts/schemas/data-visual-spec.v1.schema.json`
  instead of the private `design-system` tree.
- Relative/cwd/absolute input resolution reuses the accepted public validator's
  `resolve_local_ref`; no new path-security policy was written. Moving paths is
  not a license, fact-safety or rights conclusion.

## Explicit runtimes (fail closed)

- `_discover_chromium` returns only
  `resolve_external_file_from_env("PLAYWRIGHT_CHROMIUM_EXECUTABLE", …)`.
- `_discover_primary_runtime_python` returns only
  `resolve_external_file_from_env("CODEX_PRIMARY_RUNTIME_PYTHON", …)`.
- The automatic `Path.home()/AppData/Local/ms-playwright` glob,
  `~/.cache/codex-runtimes/.../python.exe` fallback and bundled-runtime search
  were removed. No new env alias, PATH/system discovery, permission workaround
  or install was added.
- An unset or missing explicit file raises `ArtifactError`
  (`SocialCardRuntimeError` alias), which `main()` reports as CLI exit code 2.
  Paths are resolved before any child `cwd` change. Existing caller
  package-name/hash/policy allowlists are untouched; no fake runtime identity
  is produced.

## Deferred held backend

`render_data_explanations` (`SPEC_VERSION`, `html_document`, `render_canvas`,
`render_svg_text`, `validate_spec`) is imported **inside**
`_render_data_explanation` only, where data chart rendering actually needs it.
There is no module-level import, no module-level `try`, and no broad
`except`/status flag. Inside that function:

- an exact direct `ModuleNotFoundError` for `render_data_explanations` becomes a
  clear `ArtifactError` before inputs are resolved or any output is written;
- a transitive `ModuleNotFoundError` (`exc.name` ≠ the backend) and any other
  backend import/runtime error propagate unchanged.

When the backend is present, the original `render_svg_text` /
`data_explanation_html` / `render_data_canvas` / `validate_spec` behaviour, the
`schema_version == SPEC_VERSION` selection and the `==` version check are
unchanged. Nothing is copied, rewritten or bundled, and no private upstream
source is referenced.

## Metadata classification

`DATA_SPEC_VERSION` at module level is the existing first-party format
identifier `data-explanation-chart-spec.v1` (the identifier already embedded in
this module's original error text). It is used only by
`_receipt_evidence_metadata` to classify JSON payloads into the existing
`contract_versions` entry. That path imports no backend and performs no fact or
schema verification. Within `_render_data_explanation` the backend's real
`SPEC_VERSION` shadows the name locally, so the runtime legacy-spec filter keeps
the original exact-equality behaviour. Evidence ids, refs, statuses
(`unknown`/`unverified` defaults), labels, `checked_at` and
`contract_versions` semantics are preserved.

## Prerequisites and verification boundary

`jsonschema`, `markdown-it-py`, `PyYAML` and Pillow remain real runtime
prerequisites where the original imports require them (`PyYAML` and Pillow are
not declared in the published `pyproject.toml`; this was not changed and is not
faked). Public first-party dependencies and the published
`render_artifact_validation` module are imported, not stubbed. Their presence
and version compatibility were **not** verified in this source stage, and this
guide does not claim that any dependency is installed.

The accompanying isolated test file is synthetic, fail-fast boundary coverage
for:

- no held-backend import at module load or during metadata classification;
- function-local held import, direct-missing rejection before any output path,
  and propagation of transitive/broken backend errors;
- metadata classification/status defaults using in-memory payloads;
- explicit/missing/relative behaviour of both runtime helpers under a
  controlled environment, with no home/cache probe;
- public root/`SCHEMA_PATH` composition and reuse of the published resolver;
- re-executing the actual candidate file under a held-backend-only import
  finder without recording a held import.

The import finder intercepts only the held backend; no production dependency
module is replaced by a fake. The tests do not render, run subprocess renderers/QA, generate
images/PPTX, drive a browser, call services or write output files. They are
boundary evidence only, not a full original suite, hash/schema/media-QA/output
proof, or runtime capability proof.

## What is not verified

- No candidate import, dependency-availability check, test execution, renderer
  run, subprocess/QA run, browser/Node/Python runtime check, image/PPTX
  generation, install or publication was performed in this source stage.
- Full integration, every historical renderer, installation and real rendering
  remain unverified. Source-only delivery: no real content/assets/data/cache,
  live service, clinical, business or publication outcome is claimed.

## Isolated verification result

One bounded command completed all 12 synthetic public-boundary tests with exit
0, no failed cases, no skips and empty stderr. It imported the actual candidate
and fixed public prerequisite modules. Controlled import hooks simulated only
held-backend failures; environment and in-memory payload patches were isolated
test controls, not production module replacements. No renderer, subprocess,
browser, Office, media output, installation or service was run.
The source-stage non-execution statements above describe that earlier stage;
this later isolated pass adds no full-integration or publishing claim.
