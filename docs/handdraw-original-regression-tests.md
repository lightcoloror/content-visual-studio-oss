# Handdraw regression test source

The two first-party suites remain generic working test snapshots. Only the library suite's gallery fixture output was adapted: its two gallery methods now use `tempfile.TemporaryDirectory(prefix='handdraw-test-')` without a project-local `dir=`, and the now-unused `setUpClass` that created `ROOT/outputs` was removed. The adjusted file is `tests/handdraw_style_library_integration.py`; production modules are unchanged. Original working copies are retained privately; the brief suite and both wholly synthetic JSON fixtures are included unchanged.

This is a functional output-placement correction, not a permission workaround. The platform default temporary directory is expected outside the source and resource trees; no TEMP/TMP value, ACL, tempfile mode, hash/overwrite/source guard, assertion, test method, threshold or helper changed. The candidate keeps all 16 library methods and the 280-style assertion.

Upstream conditions stay explicit. The brief suite needs `CONTENT_STUDIO_HANDDRAW_LEGACY_ROOT`, for example:

```powershell
$env:CONTENT_STUDIO_HANDDRAW_LEGACY_ROOT = ".\operator-checkouts\handraw-style-70bf51d6"
```

That relative path must be an operator-owned existing checkout of pin `70bf51d6b4c301805dd6c083355a2ad18db1023b`, whose styles.json matches the supplied hash-bound manifest. The legacy pin's license is not-declared and asset rights remain unverified.

The library suite needs `CONTENT_STUDIO_HANDDRAW_ROOT`, for example:

```powershell
$env:CONTENT_STUDIO_HANDDRAW_ROOT = ".\operator-checkouts\handraw-style-39a602d8"
```

That path must be an existing checkout of pin `39a602d82df93e3321ad71aad4d2cd15adc27c3a`. The existing configuration records the newer pin with custom-MIT attribution; no new license review was performed here, and asset redistribution remains unverified. Operator-supplied upstream resolver and layout Python is trusted task input, not a sandbox.

These explicit integration entry files are `tests/handdraw_style_brief_integration.py` and `tests/handdraw_style_library_integration.py`. They require separately supplied upstream trees and are named outside standard pytest/unittest auto-discovery patterns. Existing self-contained contract suites retain their discovery behavior; these 36 cases are not reported as skipped or passed. The tests still fail normally if required roots or assets are missing when explicitly invoked.

Source-only command examples, not executed by this batch, using an already prepared Python environment containing `jsonschema`:

```powershell
python -B tests/handdraw_style_brief_integration.py
python -B tests/handdraw_style_library_integration.py
```

No install, download, image-generation call, runtime service/browser or full-suite execution was performed for this batch. Code review used an AI collaborator; that does not establish renderer or test-suite execution. Owner checks covered AST/byte preservation and four synthetic path cases using the published gallery-root predicate, plus an in-memory bad-copy control. These checks do not establish the 36 tests passing or real gallery behavior. Actual upstream suites, assets, resolver/layout behavior and gallery HTML behavior remain unverified; the default temp location must also lie outside the eventual source and resource trees. The existing public contract suites (25/35 methods) and their earlier 59-pass/1-Windows-link-skip result are distinct and are not evidence for these tests.
