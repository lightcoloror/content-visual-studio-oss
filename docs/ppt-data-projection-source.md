# PPT data projection — portable source

A deterministic adapter that projects an evidence-bound chart spec into PPT
Master's native chart interface. It owns only adaptation: PPT Master remains
responsible for SVG validation, DrawingML generation, native chart/workbook
emission and package postflight checks.

Repository layout of this source candidate:

- `scripts/ppt_master_data_projection.py` — projection module
- `tests/test_ppt_master_data_projection_portable.py` — synthetic stdlib tests
- `docs/ppt-data-projection-source.md` — this guide

No dependency is bundled or installed by these files. This guide is source-only:
it describes behavior and contracts, and does not run the backend.

## Two surfaces: pure helpers vs backend-required operations

The parent renderer (`render_data_explanations`) is imported lazily, only when
materialization needs it. The module therefore has two clearly separated
surfaces.

**Pure helpers — importable and usable with the backend absent:**

- `ProjectionError`, `sha256_bytes`, `sha256_file`, `canonical_json_sha256`
- `project_native_payload(spec)` — bar/grouped-bar to zero-based native column,
  stacked scenario to stacked column, mechanism to line; returns the closed
  native payload plus an auditable source mapping
- `presentation_svg(spec, native_payload)` — deterministic slide SVG and the
  required-text contract
- `validate_projection_manifest(projection, projection_path)` — spec/fallback/
  slide hash freshness, payload digest and expected-chart divergence

**Backend-required — refuse fail-closed when the parent renderer is missing:**

- `materialize_project(spec_path, fallback_path, project_root)`
- `main()` (same CLI as before: `--spec`, `--fallback`, `--project`)

`materialize_project` reads the spec JSON, imports the backend, then calls the
original `validate_spec(spec, spec_path)` and uses the exact canonical
`render_svg_text(spec)` text for the stale-fallback comparison before it writes
the slide, the projection manifest and their hashes. `main()` turns a
`ProjectionError` into exit code 2 as before.

A missing backend (`ModuleNotFoundError` for `render_data_explanations` itself)
becomes an explicit `ProjectionError` ("parent renderer backend is not installed
... nothing was written") **before** any output directory or file is created. A
backend that is installed but broken is never disguised: any other import
failure — a missing transitive dependency or a runtime error during the
backend's import — propagates unchanged. An importable backend that lacks an
expected export also raises its own `ImportError` unchanged.

The only change from the original module is this lazy loader and its single call
site; every other definition, guard, palette constant and CLI behavior is
preserved.

## Mapping is not source verification

`project_native_payload` is deterministic adaptation of the fields a spec already
contains. It does **not** verify chart facts, sources, schema conformance or
rights, and a successful mapping is not evidence that a chart is correct. The
backend's `validate_spec` remains mandatory: materialization must not proceed
without it. `presentation_svg` and manifest validation likewise check structural
contracts (text budget, hashes, digests, expected-chart divergence), not source
truth.

## Preserved guards

- unsupported chart type, blocked render status, zero source series
- series without points, missing (`None`) values
- bool / non-numeric / non-finite (`nan`, `±inf`) values
- negative values where the native zero baseline requires non-negatives (bar,
  grouped bar, stacked); mechanism line keeps negatives by design
- multi-series bar label alignment; stacked/mechanism single-series rules
- mechanism interpolation whitelist (`none`, `linear_between_observations`)
- source-text single-slide budget; all-zero column fallback
- manifest schema/version, missing refs/files, stale hashes, payload digest and
  expected-chart divergence

## Backend contract (not bundled, not cleared)

`materialize_project` needs a module named `render_data_explanations` exposing:

- `validate_spec(spec, spec_path) -> list[str]`
- `render_svg_text(spec) -> str` (exact canonical text used for the
  stale-fallback comparison)

The dependency is **not** claimed cleared, installed or bundled. Unresolved
prior review: `render_data_explanations` is held because of actual Lieflat
source/template revision and redistribution provenance — this is not merely a
missing font file. It was not copied, rewritten, replaced, reimplemented or
distributed here. No other upstream attribution was verified; uncertainty is
reported, not resolved by assumption.

PPT Master binaries/source, fonts and assets were not provided. Font names in
the projection metadata (for example `Microsoft YaHei`) are **requests**, not
distributed fonts and not a claim that they are available. No external rights
are granted or implied.

## Synthetic tests

`tests/test_ppt_master_data_projection_portable.py` uses only the standard
library and wholly synthetic data (fictional chart id, generic category/series
labels, invented values). Direct execution, with fail-fast enabled:

```text
python -X utf8 -B tests/test_ppt_master_data_projection_portable.py
```

Coverage:

- source shape: the module parses/compiles, the private backend import is not at
  module load and lives inside one function, module-level imports are stdlib only
- pure mapping for bar / grouped bar / stacked / mechanism, including label,
  series and value preservation and the native payload digest
- each applicable blocked / unsupported / misaligned / missing / bool /
  nonfinite / negative / interpolation guard, plus presentation-SVG guards
- manifest checks with `tempfile.TemporaryDirectory` and synthetic files: clean
  manifest, relative refs, stale hash, missing file/ref, unsupported schema,
  payload digest mismatch, expected divergence
- absent-backend isolation (`sys.modules` forced to `None`): pure helpers still
  work; materialization refuses before any output; CLI returns 2 with no output
  directory
- installed-but-broken backend: the other-module `ModuleNotFoundError`
  propagates, not disguised as `ProjectionError`
- a missing-export control: an importable backend without `validate_spec`
  raises its own `ImportError`, not a missing-backend error
- a **test-only** stub backend verifies the preserved
  `validate_spec` -> `render_svg_text` -> write/verify order, stale-fallback
  refusal and validation-error refusal before writes; the stub is scaffolding
  and does not prove real canonical rendering or real backend validation
- two labeled controls: an input-data copy control (mutated spec copies fail
  closed while the original is unchanged) and a small in-memory source guard
  mutant (removing the finiteness guard makes the matching rejection assertion
  fail; expected mutant failure is a control outcome, the production file is not
  modified)

No real chart, real data, private renderer, font, Office/SVG renderer or
artifact is read, imported or produced. No network or dependency installation is
involved. The synthetic tests are provided source; they are not evidence that
the real renderer or real artifacts work.

## Existing integration coverage — NOT ported, NOT executed

The original five-test file keeps its real assertions in the parent repository.
Those intentions are existing integration coverage only:

1. real grouped-bar spec projects to a zero-based native column;
2. unsupported / misaligned / negative variants of the real spec fail closed;
3. real rendering + materialization is deterministic and detects stale fallback;
4. planned render artifacts can supply a missing SVG fallback;
5. dependency cycles and stale SVG artifacts are rejected.

They are not replaced by mocks and are not claimed to pass here. Intentions 4–5
belong to sibling artifact-validation modules that were not provided.


## Validation snapshot and remaining conditions

Non-executing Python compilation and source/AST preservation checks passed.
A Windows run of the supplied 25-method synthetic test source stopped in its
first method: writing the first synthetic JSON fixture was denied before any
assertion. Result: 0 passed, 1 error, 24 not run, 0 skipped; no rerun was made.
The in-memory guard-mutant control was also not executed.

The preserved error stack additionally shows standard-library
`TemporaryDirectory` cleanup calling `_resetperms` / `os.chmod`, which was denied.
This was automatic cleanup, not a separately issued repair command. The test
source retains standard temporary-directory behavior; it makes no guarantee of
zero permission-operation attempts. No alternate host, permission repair or
fallback test path was used for this attempt.

This is a source-only publication. Real parent-backend validation, full source
schema/fact verification, native PPT output, font availability, installation and
cross-machine execution remain unverified. The original integration tests are
not replaced by the synthetic source checks.
