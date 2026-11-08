# Global visual contracts — portable validation and evidence-qualified receipts

Status: reworked after independent host review (result-2). The model authored
all files and regressions but did **not** execute the suites; `tests_run=false`.
The host runs and audits them. Host first-run evidence: the lock suite ran 19
methods with 18 passes and 1 Windows symlink-privilege skip; the global suite
fail-fast at method 29 exposed a test-helper defect (an explicit `media_qa=None`
was replaced by the default passing fixture) and two verified source gaps
(unlocked declared ruleset consumption; optional registry fallback). Those were
fixed in these same seven files. No live service, real brand asset, network
call, browser, generation or publication was involved.

Task: `global-visual-contracts-20261108-01`.
Scope of this document: the three candidate modules and two synthetic test
suites under `outputs/candidate/`.

## 1. What this is

A small portability and fail-closed hardening of the existing first-party
shared/global visual validation:

| Module | Responsibility |
| --- | --- |
| `scripts/check_shared_visual_lock.py` | Verify an explicitly declared shared-visual projection against its lock (schema id, package identity, required members, canonical paths, byte hashes, non-empty content). Also exposes `load_locked_member()` so consumed source JSON is parsed only from lock-pinned bytes. |
| `scripts/global_visual_validation.py` | Resolve a global visual context from packaged resources, validate it, and build one auditable conformance receipt as returned data. Ruleset, matrix, guidelines and icon JSON are consumed only as lock-declared members. |
| `scripts/visual_asset_routing.py` | Reused pure helper for caller-recorded AI-image opt-in metadata. |

It deliberately does **not** recreate a design system, router, renderer,
database, authority, research platform or brand theme. Brand registry/tokens/
assets are not copied or bundled.

No color or palette decisions were introduced. The modules only preserve
declared ruleset/authority semantics and diagnostic IDs; brand color tokens are
never bundled or recolored.

## 2. Packaged resource layout

All defaults derive from the existing public path helper
`studio_paths.STUDIO_ROOT`; the modules never infer a private or sibling root.

```
<STUDIO_ROOT>/
  config/global-visual-runtime.v1.json          # shared_root: null by design
  vendor/shared-visual-design-system/           # packaged projection + lock
    shared-visual-design-system.lock.json
    schemas/
      global-visual-context.v1.schema.json
      data-visual-spec.v1.schema.json
      visual-conformance-receipt.v1.schema.json
    contracts/
      guidelines.v1.json
      chinese-typography.v1.json
      icon-registry.v1.json
      imagery-grammar.v1.json
      motion-grammar.v1.json
      cross-medium-conformance.v1.json
  visual-contracts/                             # same nine generic source contracts
  studio_assets/...                             # installed-layout mirror (studio_paths decides)
```

- The lock file lists the nine required source references and a
  `projected_ref` for each; both source and projection bytes are hashed.
- The empty synthetic authority sample lives at
  `visual-contracts/contracts/authority-registry.v1.json` and is **not** part
  of the nine-file lock; it is operator-visible synthetic data only.
- The generic schema `$id`s are `example.invalid` symbolic IDs. Nothing
  resolves them over the network.

### Explicit source root only

`config/global-visual-runtime.v1.json` ships `"shared_root": null`. The shared
source root must be supplied explicitly, in this order:

1. keyword `shared_root=...` on the public functions,
2. `SHARED_VISUAL_DESIGN_SYSTEM_ROOT` in the environment,
3. the runtime config value (null in the public package).

If none is present the modules raise a clear blocked condition
(`no explicit shared visual source root is configured...`). There is no probing
guess of `visual-contracts/`, a sibling checkout or a private workspace.

## 3. `check_shared_visual_lock.py`

### Reused hardening (unchanged in intent)

- `REQUIRED_SOURCE_REFS` with all nine contract/schema members.
- Lock identity: `shared-visual-design-system-lock.v1`,
  `@lightcolor/shared-visual-design-system`, consumer `content-visual-studio`,
  package version `1.1.0`.
- Non-empty `files` map; per-entry `sha256` must be 64 lowercase hex.
- Canonical relative references: rejects empty, `..`, `.`, absolute,
  drive/colon, backslash and non-canonical spellings *before* reading.
- Resolved-symlink containment check before any read.
- Both projected and source files hashed; missing/malformed/directory/hash
  mismatch fail closed.

### Portability and closed-failure changes

- `validate_lock(shared_root=None) -> list[str]` is preserved. Optional
  keyword-only `lock_path=` / `projection_root=` are installation/test hooks;
  they add no storage, route or trust.
- Every read goes through `_read_bytes()`; a single captured byte buffer is
  used for hashing and for the lock JSON decode. There is no
  check-then-reread substitution.
- Empty member bytes are refused even when the supplied hash matches the empty
  bytes (`empty shared source/projection`). This closes the previously observed
  hash-matching-empty-file false pass.
- `main(argv=None) -> int` was added for the existing CLI: `--shared-root`
  optional, `--help` returns 0 without needing runtime/shared state, valid
  snapshot returns 0, findings return 1, argument errors return 2, no writes.
- A caller-provided hash is snapshot data, not a signature, publisher identity
  or consent. The public lock says only “local owner-authorized projection”;
  no provenance is forged.

### Lock-pinned consumption (`load_locked_member`)

`load_locked_member(shared_root, ref, *, lock_path=None, projection_root=None)`
returns the exact source byte buffer together with the lock entry's declared
hash. It reads:

1. the lock freshly (never a global cross-root cache);
2. the canonical source path and the entry's declared `projected_ref`;
3. the source and projected bytes, each of which must hash to the lock entry.

The reference must be the exact canonical key of the lock `files` map. A file
present in the source root but absent from the lock is refused; a file changed
after an earlier lock check is refused on hash comparison. Custom *additional*
members that are themselves lock-declared remain usable. The returned buffer is
the one that was compared, so no later read can be substituted for parsing.

### The three carried-forward false-pass counterexamples

The synthetic suite asserts each of these is refused:

1. an empty `files` map **and** hash-matching zero-byte member files;
2. a wrong lock schema/package/consumer/version identity;
3. a `../` escape whose invented outside bytes have a matching hash — refused
   before the outside file is read (a read-recording test proves it).

## 4. `global_visual_validation.py`

### Preserved public API (positional signatures unchanged)

| Symbol | Preserved call shape | Added keyword-only overrides |
| --- | --- | --- |
| `resolve_playwright_package()` | no positional args | `runtime_path`, `package_json` |
| `is_global_visual_enabled(artifact, item)` | 2 positional | — |
| `build_runtime_context(item, artifact)` | 2 positional | `shared_root`, `runtime_path`, `schema_root` |
| `validate_runtime_context(context, artifact=None)` | 2 positional | `shared_root`, `runtime_path`, `schema_root` |
| `build_conformance_receipt(item, artifact, output_path, typography, data_status, media_qa)` | 6 positional | `shared_root`, `runtime_path`, `schema_root` |
| `validate_global_visual_item(item, artifact)` | 2 positional | `shared_root`, `runtime_path`, `schema_root` |

Internal helpers `_authority_finding`, `_typography_finding`,
`_data_finding`, `_icon_findings`, `_imagery_findings`, `_motion_finding`,
`_load`, `_sha256`, `_now_iso` keep their call shapes. `_shared_root` is an
internal resolver and now accepts explicit keywords. `WORKSPACE_SCRIPTS` and
the sibling `sys.path` injection were removed; the installed local helper is
imported directly (`visual_asset_routing`) together with the shared lock module.

`schema_root` is the packaged projection root (the directory containing the
lock, `schemas/` and the generic contracts). It exists so installation and
tests can point at an explicit packed projection; it grants no authority.

### Resolution and validation behaviour

- Runtime config and default schemas are read through the packaged projection.
  A missing lock, schema, contract or runtime config is a blocked condition,
  never an empty success.
- An explicitly enabled item cannot bypass the shared lock by declaring its
  own `visual.design_system.global_visual` context: the lock is verified before
  a declared context is accepted. Declared contexts are still schema-checked,
  and their ruleset reference must resolve inside the explicitly supplied
  shared root.
- **Lock-bound source consumption.** The ruleset, cross-medium conformance
  matrix, guidelines and icon registry are the source JSON that drives context
  and findings. Each is consumed only through `load_locked_member()`: its
  canonical reference must be an exact `files` key of the explicit lock, and
  the captured bytes parsed must hash to that entry and its declared
  projection. A caller-declared context therefore cannot point `ruleset.ref`
  at an unlocked extra file and pass merely because its own `sha256` matches
  those bytes. Custom *additional* lock-declared members are allowed; unlocked
  files are refused. Because the lock entry is the reference hash, a file
  changed after a stale lock check is refused rather than parsed as pinned
  bytes, and the same captured buffer is used for hash comparison and JSON
  decode. `schema_root`/projection overrides are honored wherever a lock or
  projection path is resolved.
- Relative refs are confined to the supplied root, absolute refs must also
  resolve inside it, and `scheme://` remote refs are refused. No fetch.
- JSON Schema validation uses `jsonschema` `Draft202012Validator` with an
  empty `referencing` `Registry`. `referencing` is a declared mandatory
  dependency: a missing import, a missing empty registry, or a constructor
  that does not accept the registry argument is an explicit refusal. The code
  never silently creates the default potentially retrieving validator. An
  unprovided external `$ref` fails closed, while internal `$defs`/local `$ref`
  resolution still works. A schema that cannot complete validation becomes an
  error string, not a success.
- The synthetic authority registry and explicitly operator-provided brand
  record files are not members of the nine-contract lock; they remain
  path-confined operator data used only for global-vs-brand scope and QA
  binding. They are not findings-driving locked contracts.
- `validate_global_visual_item` returns `[]` for a disabled item without
  touching any dependency (root, lock, schema or browser runtime) and returns
  `(field, message)` tuples for enabled items.

### Playwright

- Resolution uses only the configured environment variable
  (`PLAYWRIGHT_PACKAGE_JSON`) or an explicit `package_json` keyword. The
  package config ships `fallback_ref: null`, which is a clear refusal.
- The resolved `package.json` must be non-empty and match `name=playwright`
  and `version=1.61.1` exactly.
- The module never imports, launches, downloads or installs a browser.

### Brand authority

- `authority_scope` defaults to `global-only`; an empty authority registry
  therefore yields global-only. Topic, account or narration never imply brand
  authority.
- A brand-bound record is accepted only for the exact `visual.visual_profile`
  key and only from operator-provided registry data. The record must give
  explicit `local_root`, `profile_ref`, `tokens_ref`, `qa_receipt_ref`,
  `repository` and `profile_version`; there is no hardcoded private token path
  and no fallback root. Record paths are confined to the explicitly supplied
  shared root and its declared local authority root.
- The binding is structural/hash-bound QA data, not permission. The receipt
  finds fail closed for a missing/unreadable/non-passing/expired/naive-dated
  brand receipt, profile-version mismatch, receipt/token hash drift, or a
  receipt older than the profile `source_updated_at`.
- The brand profile JSON has no hash field in the existing contract schema, so
  it is read for dates only; this is recorded as a residual limitation below.

### Evidence-qualified outcomes

Findings keep the existing diagnostic IDs and P0/P1/P2 distinction:

| Priority | Enforcement | Effect on `result` |
| --- | --- | --- |
| P0 | `blocking` when `p0_activation=active`, else `report-only` | a `fail` produces `result="fail"` when blocking |
| P1 | always `report-only` | a `fail` is reported but does not block |
| P2 | `human-check` | a `fail`/`needs-review` produces `result="review-required"` |

Additional evidence rules:

- `typography` accepts `pass`/`fail`/`needs-review`; any other status is
  treated as `fail`, and a `pass` without a rendered evidence `ref` is
  downgraded to `needs-review`.
- Data charts (`layout_intent`/`output_family == "data-chart"`) pass only when
  `normalized_spec_valid is True`; non-chart artifacts are `not-applicable`.
- Imagery never calls missing evidence “verified”: rights must be `verified`,
  privacy must be `verified` or `not-applicable`, evidence photography needs
  `verified`/`user-confirmed` evidence, and `unknown`/`needs-review` evidence is
  surfaced as `needs-review`. Stock photos cannot be factual evidence, text
  overlay needs `safe_crop`, focal cover needs `focal_point`, and generated
  imagery needs recorded opt-in metadata.
- `media_qa` must carry an explicit `result` of `pass` or `fail`. Missing,
  `needs-review`, `unknown` or invalid media-QA states raise a clear refusal
  instead of producing an overall pass.
- Exception dates are parsed strictly. Unknown rules, expired dates and naive
  or unparsable date-times produce errors; they never crash into success.
- A P0 `pass` means only that the tested structural gate passed. It is not a
  claim that real semantic, typographic, clinical or audience review happened.
- Receipts are returned data. Nothing writes a ledger, publishes, saves state
  or invokes image generation; `policy.manual_only` stays `true`.

## 5. `visual_asset_routing.py`

The supplied first-party pure helper is reused unchanged in behaviour and
signatures. Only docstrings were clarified: `request_text`,
`explicit_user_request` and `matched_trigger` are **caller-provided record
consistency**. Matching a quoted trigger phrase is not proof of a native user's
consent and is never permission to execute a protected tool, publish, spend
money or generate an image. The module performs no generation, model call,
network request or write.

## 6. Tests (authored, NOT RUN)

Two complete portable `unittest` suites:

| File | Focus |
| --- | --- |
| `tests/test_shared_visual_lock_contract.py` | synthetic source/projection/lock; all nine required members; schema/package/consumer/version identity; empty files map and empty file contents; wrong schema; `../` escape with matching outside hash and no outside read; canonical/absolute/backslash/drive/empty refs; source and projection drift/missing/directory; symlink skip when privileges are missing; explicit/missing root; CLI `--help`/valid/findings/argument errors; `load_locked_member` pinned-buffer return, unlocked-file refusal, source/projection read-swap refusal, and custom lock-declared member acceptance. |
| `tests/test_global_visual_contract.py` | synthetic nine-contract fixture with labelled synthetic schemas; global-only context/receipt and output hash; declared context cannot bypass the lock; ruleset hash/version/ref/malformed/remote refs; **unlocked declared ruleset refusal with a caller hash that matches the bytes**; **changed-source read-swap refusal after a simulated stale lock check**; **custom lock-declared ruleset acceptance**; media/profile mapping; known/unknown/future/expired/naive/invalid exceptions; brand positive, hash drift, stale source date, naive/expired receipt, profile mismatch, missing/invalid receipt, missing token ref, path escape, no implicit authority; typography, data chart, icon, imagery and motion outcomes; media-QA pass/fail and non-passing refusals including an explicit `None`; Playwright refusal/identity; no network/subprocess; **missing/unsupported referencing capability refusal with no fallback construction/urlopen/DNS**; internal `$defs` validation; external-`$ref` no-fetch; captured-byte read counts; missing/empty output; routing record-consistency boundary. |

All files, contracts, schemas, brand records, receipts and artifact bytes in
the suites are invented under `tempfile.TemporaryDirectory()`. The embedded
`global-visual-context` and `conformance-receipt` schemas are clearly labelled
`SYNTHETIC TEST ONLY` and are *not* canonical-contract proof; the host verifies
the actual packaged nine contracts separately. `studio_paths` is used when the
host provides it; otherwise the tests install an in-process synthetic
`studio_paths` module so the suite stays portable and never touches a private
package.

The receipt fixture uses a distinct omitted-argument sentinel: an explicitly
passed `media_qa=None` reaches `build_conformance_receipt` and must be refused
rather than being replaced by the default passing metadata. The tests never
loosen the implementation guard to accept an unrelated error.

Suggested host command (from `outputs/candidate`):

```
python -m unittest discover -s tests -p "test_*.py" -v
```

Requirements: Python 3.10+, `jsonschema` 4.18+ (with `referencing`).
The model did not run this command; `tests_run=false`.

## 7. Boundaries and non-claims

- No request for wider sandbox, permission or approval; no access to Codex
  profiles, other workspaces, GUI, network, installs, commits or subagents.
- No live validation of the real packaged nine schemas, a real brand authority,
  a real artifact or a real Playwright runtime.
- No claim that a structural pass completes human/clinical/typographic/audience
  review, grants author/platform permission, or makes the artifact publishable.
- Known residual limits:
  - the brand profile file has no hash field in the existing schema, so it is
    date-checked but not byte-bound;
  - the synthetic authority registry and operator brand records are not lock
    members (they are explicit operator/caller data, path-confined but
    unlocked); only ruleset/matrix/guidelines/icons are lock-bound;
  - receipts contain absolute output refs (existing behaviour);
  - Windows hosts without symlink privilege skip only the symlink regression;
  - synthetic test schemas intentionally do not prove the packaged schemas;
  - `referencing` is mandatory; an environment without it now refuses at
    import/validation instead of degrading to a retrieving validator.
