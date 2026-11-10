# ContentStudio Sveltia Pin Regressions Source Adaptation

## Environment Bindings & Operator Requirements
The regression test suite in `tests/test_sveltia_pin.py` adapts hardcoded paths to two explicit operator environment variables:
1. `CONTENT_STUDIO_SVELTIA_RUNTIME_PATH`: Points to operator-supplied full runtime JSON metadata.
2. `CONTENT_STUDIO_SVELTIA_BUNDLE_PATH`: Points to an independently acquired local Sveltia CMS bundle (`sveltia-cms.js`).

Missing bindings raise ordinary `KeyError`. No fallback, mock, or fake runtime is provided. The public repository configuration `config/sveltia-runtime.v1.json` remains strictly schema-only and lacks `cdn_url`, `sri`, `bundle_sha256`, and `local_workflow_boundary`. Operators must provide complete metadata and authentic bundles separately without bundle distribution. Current public `admin/index.html` exists with pinned 0.172.4 CDN and SRI; prior unsubmitted packets lacking HTML are historical.

## Expected Contracts vs Execution Status
The four original test bodies declare these expectations (not observed original-suite results):
1. Equality of caller-provided CDN URL/SRI with public admin script attributes, plus the original crossorigin assertion. Current public HTML is pinned to 0.172.4; the source test does not independently authenticate the metadata.
2. Local bundle SHA-256 and SHA-384 SRI equal caller-provided metadata. The historical method name says verified npm, but no independent npm origin proof was established here.
3. The config header contains the supplied schema URL and the original public validate_config() result is expected to be empty.
4. Local workflow boundary constraints governing manual directory authorization and automatable editing.

**Execution Status**: Source-only with no execution authorization; intended original 4 tests run = 0 (NOT RUN). The original four tests, module imports/collection, browser, CDN, runtime download, service and Office paths were not run. Owner non-executing compile and complete AST comparison passed; four extracted in-memory path-binding controls matched expectations (each provided value selects that Path; each missing variable raises its original KeyError). These read no actual input files and did not alter the OS environment. Actual inputs and targeted execution must be authorized separately.

## Source Boundaries & Verification Limitations
- **Provenance & Integrity**: Hash and SRI consistency demonstrate internal file agreement, not authenticated upstream origin proof.
- **Workflow State**: Declared boundary strings do not verify live browser permission enforcement, filesystem saving, or publication mechanics.
- **Validator Scope**: `validate_config()` validates against static schema defaults distinct from full runtime metadata; static signature inspection implies neither module compatibility nor runtime linkage.
- **Licensing & Scope**: Governed by first-party Apache-2.0 licensing; third-party CMS bundle distribution and licensing are not inferred. Distinguishes old static review from current check.


This is source-checkout regression code, not installed-wheel compatibility proof. The full metadata and bundle remain external; none is synthesized, downloaded or distributed. Hash agreement, local fixture boundary strings and a passing schema assertion would still not establish trusted upstream provenance or actual account/browser authorization. The public schema-only runtime and validator source remain unchanged.
