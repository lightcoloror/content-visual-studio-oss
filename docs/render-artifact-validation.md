# Render artifact and immutable receipt validation

`scripts/render_artifact_validation.py` is the shared cross-file validator for
`visual.render_artifacts` entries and their render receipts. It is imported by
the render orchestrator and is not a standalone CLI.

## API

- `validate_render_artifacts(item, item_path) -> list[tuple[str, str]]`
- `resolve_local_ref(ref, item_path) -> Path`

Both signatures are unchanged from the existing module. An empty list means no
reported validation errors. That is not an exception-free guarantee: the lazy
held-backend boundary documents that import or runtime errors can propagate, so
not every failure is returned as a `(location, message)` pair.

## Public roots

Filesystem roots come from the public `scripts/studio_paths.py` module:

- `STUDIO_ROOT` for `schemas/render-receipt.v1.schema.json`,
  `config/renderer-registry.v1.json`, `config/layout-intents.v1.json` and
  `visual-contracts/schemas/visual-conformance-receipt.v1.schema.json`;
- `SOURCE_ROOT` as the documented public source root.

Relative refs are resolved under the item directory, `STUDIO_ROOT`,
`SOURCE_ROOT` and the current directory, in that order; a missing ref falls
back under `STUDIO_ROOT`. This replaces the private workspace-parent bootstrap
with a portable public root. It is a portability change only, not a sandbox or
path-security boundary: absolute paths, `..` traversal and current-directory
refs keep their existing behavior, and no new confinement gate is added.

## Lazy held data backend

The held backend module `render_data_explanations` is imported lazily inside
`validate_render_artifacts`, only when validating a data-required artifact:

- renderer `lieflat-charts`;
- renderer `ppt-master` with `renderer_options.operation == "data-native"`.

It is not imported at module load, so non-data consumers never run backend code.
If the direct module is missing, the data-required artifact receives a non-empty
validation error naming `render_data_explanations`; validation fails closed and
does not report success, skip the artifact, downgrade the renderer or fabricate a
canonical SVG. If the module is present but broken, a transitive
`ModuleNotFoundError`, an `ImportError` or any other runtime error propagates
unchanged and is not converted into a status string or false "missing" result.
The public, pure `ppt_master_data_projection` import remains required at module
load.

When the backend is present, the original data blocks run unchanged, including
`SPEC_VERSION`, `validate_spec`, `render_svg_text` and the data source, hash and
stale-SVG checks. Optional-import handling is limited to the data-required
branches; every other artifact and receipt check is unaffected.

## Preserved guards

The full existing validation body is retained: hashes, JSON schemas,
cross-receipt links, artifact/asset ids, produced status, asset rights, privacy,
media QA and human approval, global visual conformance, AI image-generation
consent, artifact dependency cycles, renderer registry pins and remote-download
restrictions. No registry, configuration system or replacement renderer is
introduced.

## Tests

`tests/test_render_artifact_validation_public.py` is an isolated synthetic suite
for the changed root and lazy-backend boundaries. It uses in-memory registry
fixtures and import blocking to cover item/absolute/`..`/fallback resolution,
no import at module load, no import for non-data renderers, the direct-missing
validation error and propagation of transitive or runtime backend errors. It is
explicitly not the original integration suite: it does not prove real schema
validation, hashing, media QA, renderer output or full-validator behavior. The
original integration tests remain unverified because they require renderer
entries, media profiles and runtime fixture files outside this source scope.

Run the file directly in a repository checkout that has the public sibling
scripts and test-support dependencies installed; it sets up its own import path
and stops at the first failure:

```text
python -X utf8 -B tests/test_render_artifact_validation_public.py
```

A missing prerequisite raises an explicit import failure; the tests do not stub
production imports or turn absence into a skip.

The repository declares Python >=3.11; versions were not individually tested.
Prerequisites include `jsonschema`, `markdown-it-py`, and the public
`studio_paths`, `slot_budget_validation`, `media_qa_validation`,
`global_visual_validation`, `ppt_master_data_projection` and
`visual_asset_routing` modules.

## Licensing

This first-party source falls under the repository license. Imported upstream and
dependency rights are not granted by this document.


## Initial validation limits

One bounded Windows command ran the 10 isolated tests successfully (0 failures,
0 skips). The actual candidate module was loaded with seven unchanged public
sibling modules from the fixed source baseline. Registries and import failures
were controlled in memory; no temporary fixture directory or real held data
backend was used. This does not establish the original 18-test integration,
real JSON-schema/hash/media-QA validation, rendering, publication, installation
or cross-machine behavior. The full original validation checks are retained;
source/AST preservation is separate evidence from runtime validation.
