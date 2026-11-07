# Candidate adaptations — six low-risk modules (followup 20261107-091116-a2e091)

This directory is an **independent, source-only public candidate** built on the
fixed public baseline `Content Visual Studio v0.1.1`
(`430e7e2f53171d9dadcc9b9071a7739032fd6286`, 132 text files). It is a review
proposal, **not** a release, an installed-package verification, or a project
acceptance. All runtime tests live in the sibling test workspace and use only
new synthetic data.

## What is in this candidate

| Path | Type | Notes |
| --- | --- | --- |
| `scripts/build_human_voice_fixture.py` | adapted frozen source | source/installed path resolution, explicit roots, input preflight |
| `scripts/hallmark_report_adapter.py` | frozen source, unchanged | bytes identical to the frozen snapshot |
| `scripts/media_qa_validation.py` | adapted frozen source | profile registry path resolution + schema guard |
| `scripts/social_card_runtime.py` | adapted frozen source | optional `allowed_root` confinement added |
| `scripts/typography_gate_collector.mjs` | frozen source, unchanged | bytes identical to the frozen snapshot |
| `scripts/validate_insurance_clause_explanations.py` | frozen source, unchanged | bytes identical to the frozen snapshot |
| `config/media-qa-profiles.v1.json` | new first-party resource | exact bytes of the supplied shared registry |
| `scripts/studio_assets/config/media-qa-profiles.v1.json` | new packaged resource | exact same bytes; matched by the existing `config/*.json` package-data rule |
| `pyproject.toml` | modified baseline | five Python modules appended to `tool.setuptools.py-modules`; no version/dependency change |
| `docs/candidate-adaptations.md`, `docs/candidate-tests.md` | new first-party docs | this file and the test contract |
| `tests/test_*.py`, `tests/test_*.mjs` | new first-party targeted unit tests | offline, synthetic, no service/browser/media/network |

The `inputs/test-tools/windows_offline_tempdir.py` adapter is **not** copied
here: the ordinary temporary directory works on this host, and the adapter is
test-only tooling, never public runtime code. No raw logs, absolute private
workspace paths, real manuscripts, client/health records, credentials or
owner runtimes are included.

## Per-module adaptations and preserved behaviour

### 1. `scripts/build_human_voice_fixture.py`

* `ROOT`/`FIXTURES` now come from `studio_paths.STUDIO_ROOT` instead of a
  hard-coded `__file__` parent. `--fixtures` (or
  `CONTENT_STUDIO_CASE_FIXTURE_DIR`) selects the read-only published synthetic
  fixture directory; `--output-root` redirects all writes so a test copy is
  used. Defaults reproduce the original in-place behaviour.
* `CONTENT_STUDIO_HUMAN_VOICE_ROOT` is bound **before** the gate is imported to
  the inert `fixtures/synthetic-voice` documents published in the baseline.
  `setdefault` means an operator-supplied root always wins; real human-voice
  material is never substituted silently.
* `_preflight` refuses to write anything when a published synthetic input or
  editing document is missing (fail closed before the first partial output).
* Preserved exactly: `AIISH_TEXT` (the four already-public fictional segments),
  deterministic `_write` (`sort_keys`, `indent=2`, trailing LF), `_text_hash`,
  the hash-bound `human_voice_gate.apply_human_voice_gate` call, the
  `synthetic_only`/`external_service_called=False` boundaries, and the
  `main()` no-argument entry point. No TTS, voice sample, model, network or
  real author confirmation is used.
* Source-tree only for regeneration: the installed wheel does not ship the
  case fixture inputs. An installed-mode regeneration must pass an explicit
  `--fixtures` and `--output-root`.

### 2. `scripts/hallmark_report_adapter.py`

No code change. Reuses the declared `markdown-it-py` dependency
(`MarkdownIt("commonmark").enable("table")`), the `Token` inline parser,
`SEVERITY_BUCKET`, `BUCKETS`, `Keep`/`Fix`/`Quick Wins` rendering, the
report-only/source-mutation guards and the unsupported-format rejection. No new
report protocol was created.

### 3. `scripts/media_qa_validation.py`

* `CONFIG_PATH` resolves through `STUDIO_ROOT / config/media-qa-profiles.v1.json`
  (source tree, or installed `studio_assets`), with explicit override
  `CONTENT_STUDIO_MEDIA_QA_PROFILES`. A missing file still raises before any
  invariant evaluation.
* `load_media_qa_profiles()` now rejects a registry with a missing/wrong
  `schema_version` or a missing `profiles` map instead of silently treating it
  as empty.
* Preserved exactly: `resolve_media_qa_profile`, `required_hard_checks`
  (common / profile / renderer / renderer-operation / global-visual layers),
  `validate_receipt_qa` (profile binding, duplicate and missing hard checks,
  hard-fail result, `needs_review_count`, `max_needs_review`, result
  derivation), the `lru_cache` loader and all fail-closed exceptions. No
  rendering, retry or media detection is performed.
* The shipped registry retains its first-party historical attribution
  (`updated_by`, `updated_at`); this is a provenance record, not a claim of
  authorship approval or a runtime dependency.

### 4. `scripts/social_card_runtime.py`

* `resolve_external_file_from_env` gains an optional `allowed_root`. When
  supplied, the resolved file must be inside that root (symlink/junction
  dereferenced by `Path.resolve()` first). Without it, behaviour is unchanged.
* Preserved exactly: missing env-name contract, unset env var, missing file,
  SHA-256 drift, `_SafeSocialCardHtmlParser` whitelist, viewport requirement,
  `data-design-direction` binding, `section.poster` requirement, script /
  active-document / event-handler / remote-asset rejection and CSS remote
  reference scanning. No server or browser is started.

### 5. `scripts/typography_gate_collector.mjs`

No code change. Preserves the three Node stdlib imports, the frozen
`TAG_ROLE_FALLBACK`, `loadTypographyGateBinding` (schema, profile, `hard_gate`,
SHA-256 binding), and the deliberately closure-free, serialization-safe
`collectTypographyGateInPage`. Tests use a synthetic mock DOM only; real
Playwright/Puppeteer injection and the two bridge modules remain unverified
(the bridges are not in the public baseline).

### 6. `scripts/validate_insurance_clause_explanations.py`

No code change. `--schema` remains **required**; the public baseline has **no
confirmed canonical insurance clause explanation schema**, and this candidate
deliberately does not add a default path or ship one. Tests use a minimal
explicitly synthetic schema generated inside the test workspace to prove the
generic function boundaries only. `FORBIDDEN_OVERCLAIMS`, numeric/anchor/fact
reference integrity, critical-fact structuring, reverse-paraphrase and
reviewed-unit gates are unchanged. Real contract ingestion is unverified.

## Source and licence

All first-party files inherit the baseline `LICENSE` (Apache-2.0, owner
authorized first-party public edition); `THIRD_PARTY_NOTICES.md` is retained
unchanged. `jsonschema` and `markdown-it-py` are separately installed MIT
libraries declared in `pyproject.toml`, not vendored. No upstream fonts,
photos, music, models, CMS/browser binaries or personal Skill source is
distributed. Frozen source bytes are recorded in `CANDIDATE-MANIFEST.json`.

## Bounds of this candidate

* Tests were run against a **source-tree copy** only. No wheel/sdist was built,
  nothing was installed, no venv was modified; `tool.setuptools.py-modules` and
  package-data are **proposed patches** for the Owner to verify.
* No browser, Playwright/Puppeteer bridge, web service, Office/PPT, FFmpeg,
  downloader, model/provider/TTS, real media QA, real contract ingestion or
  network request was executed.
* A passing synthetic unit test is not evidence of real QA results, clinical /
  legal / insurance conclusions, author consent, or publication permission.
