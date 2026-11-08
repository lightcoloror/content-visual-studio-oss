# Portable handdraw adapters

Status: candidate implementation for host review and host execution. Tests were
authored but not executed by the model (see `IMPLEMENTATION-REVIEW.md`).

## What this is

Three minimally adapted first-party modules that expose the existing handdraw
style-brief, style-library and gallery-overlay behaviour from an installed or
source checkout of the public studio package:

| File | Role |
| --- | --- |
| `scripts/handdraw_style_brief.py` | Image-free style brief for one explicit content target; CLI plus API |
| `scripts/handdraw_style_library.py` | Pinned style/color/layout catalog and frozen-text prompt handoff |
| `scripts/handdraw_gallery_adapter.py` | Local HTML overlay writer for the three pinned gallery tabs |

They deliberately reuse the existing slot, design-direction and pinned-source
mechanism. There is no new registry, router, renderer, provider or platform.

## Configuration layout

All three modules resolve their default resource root through the existing
`studio_paths.STUDIO_ROOT`. In an installed package that root is the resource
directory (for example `studio_assets`); in a source tree it is the repository
root while `schemas/content-item.schema.json` is present. A source-tree fallback
(`Path(__file__).resolve().parents[1]`) keeps isolated source/test layouts
importable when `studio_paths` has not been copied yet; the installed package
always ships `studio_paths`.

Default resources, owned and installed by the host packaging step:

- `config/handdraw-style-brief.v1.json` (legacy brief registry and source pin)
- `config/design-directions.v1.json` (shared design directions)
- `config/handdraw-style-library.v1.json` (full library registry and source pin)
- `config/handdraw-legacy-source-manifest.v1.json` (packaged legacy manifest)
- `config/handdraw-library-source-manifest.v1.json` (packaged library manifest)

The manifests are hash metadata only. They are not upstream artwork or data.

### Explicit source roots (fail closed)

Upstream checkouts are never guessed from the current directory, sibling
directories or vendor paths. A root must come from one of:

1. an explicit API keyword: `source_root=` / `Library(config, source_root=...)`;
2. an explicit CLI flag: `--legacy-root` or `--library-root`;
3. an explicit environment variable:
   - `CONTENT_STUDIO_HANDDRAW_LEGACY_ROOT` for the legacy brief index;
   - `CONTENT_STUDIO_HANDDRAW_ROOT` for the full library;
4. a nonempty operator-supplied `local_path` in the relevant config
   (relative paths resolve against `STUDIO_ROOT`).

Packaged defaults ship `local_path: null`. Without an explicit root the modules
raise one stable `ValueError` before touching any source file, and the CLI
returns exit code 2. Nothing is downloaded, installed or auto-discovered.

The gallery writer additionally requires an explicit output root through
`gallery(output_root=...)` or `CONTENT_STUDIO_HANDDRAW_GALLERY_ROOT`. It refuses
to write inside the pinned upstream checkout or the installed resource tree.

### Manifest pinning

- Legacy brief: `source.manifest_path` resolves from `STUDIO_ROOT` and its exact
  bytes are pinned by `source.manifest_sha256`. Older explicit configs may
  instead use `source.manifest_ref` relative to the explicit checkout. When no
  manifest is configured the original `git -C <checkout> rev-parse HEAD`
  fallback is kept. The index ref is confined to the explicit checkout and the
  index hash, commit and style-index mapping checks are unchanged.
- Full library: the packaged config's `manifest_path` points at
  `STUDIO_ROOT/config/handdraw-library-source-manifest.v1.json`; old explicit
  configs without it keep the external `local-source-manifest.json` fallback.
  Manifest SHA, commit binding, asset confinement and per-file SHA checks are
  unchanged.

All pins are consumed-byte pins: manifests, library data, gallery HTML, prompt
reference assets, pinned source modules and the legacy index are read exactly
once into a byte buffer; that same buffer is hashed against the pinned entry and
then decoded or compiled. A second read is never trusted, so a path that changes
between the check and the use cannot introduce unverified bytes. The public
`checked()` path API and its errors are unchanged; `read_checked()` exposes the
already verified buffer for the adapters that decode HTML.

## API

### `handdraw_style_brief`

Existing call shapes are preserved; only keyword-only additions were made.

```python
read_json(path) -> object
verify_source(registry, *, source_root=None) -> dict[str, dict]
target_from_item(item, target_id) -> tuple[str, dict]
create_brief(item, target_id, style_id, metaphor=None, central_action=None,
             registry=None, *, source_root=None) -> dict
main(argv=None) -> int
```

`create_brief` returns the same `handdraw-style-brief.v1` candidate object as
before: `candidate-only`, `source_ref`, index SHA, `not-declared` source license
status, `unverified` upstream asset rights, `image_generated: false`,
`upstream_image_used: false`, `manual_review_required: true`, zero labels and an
explicit planning-only boundary. It never mutates the content item.

CLI (also usable through the console entry point, which exits with the returned
integer):

```text
handdraw_style_brief.py [--legacy-root DIR] [--library-root DIR] list
handdraw_style_brief.py [--library-root DIR] gallery --output-root DIR
handdraw_style_brief.py [--library-root DIR] catalog [--query TEXT]
handdraw_style_brief.py [--library-root DIR] prompt --item FILE --target-id ID --request FILE [--output FILE]
handdraw_style_brief.py [--legacy-root DIR] brief --item FILE --target-id ID --style-id ID [--metaphor TEXT] [--central-action TEXT] [--output FILE]
```

Root flags may be placed before the subcommand (global form) or on the relevant
subcommand. `--help` only needs the standard library. Success prints one JSON
document on stdout and returns 0. Controlled `ValueError`/`KeyError`/OS/subprocess
failures print `ERROR: ...` on stderr and return 2. Output files are exclusive:
an existing brief or prompt output is never overwritten.

### `handdraw_style_library`

```python
Library(config=None, *, source_root=None)
Library.checked(relative) -> Path
Library.data(name) -> object
Library.module(name) -> module
Library.gallery(output_root=None) -> dict
Library.catalog(query='') -> dict
Library.prompt(item, target_id, request) -> dict
```

`module(name)` accepts only `style_asset_paths`, `resolve_reference` and
`layout_library`; any other or path-like name fails. Each call re-checks the file
against the manifest, then compiles and executes only the hash-verified byte
buffer from that same read. It never goes through the import loader, so no
`__pycache__` or `.pyc` is written into the external upstream checkout. The
ambient `sys.modules['style_asset_paths']` entry is captured and restored
exactly, including the "was absent" case, while the pinned helper is visible to
the pinned resolver during execution.

`gallery(output_root=None)` returns
`status: local-reference-library`, the three local page paths, counts, source,
commit, attribution, license fields, `image_generated: false` and
`manual_review_required: true`.

`catalog` keeps the browse-only result shape and
`browse-or-explicit-selection; no aesthetic scoring` policy.

`prompt` keeps the `handdraw-style-prompt.v1` fields, content SHA-256,
conservative `upstream_claim_not_locally_verified; conservative_reference_required`
model calibration, exact frozen text, bilingual theme/composition/palette
handling, target role/status/design eligibility checks and no mutation of the
content item. It never calls a provider or generates an image.

### `handdraw_gallery_adapter`

```python
materialize(library, output_root) -> dict[str, str]
```

Writes a local overlay for `index`, `layouts` and `colors`:

- upstream HTML is read only through `library.checked(...)` (hash-verified) and
  is never copied into this source package;
- a `<base>` keeps relative upstream assets bound to the pinned checkout while
  the three tab links point into the overlay;
- absent custom-library and tutorial pages are disabled instead of left broken;
- the pinned copy handler gains the manual-copy dialog fallback;
- the index update check is disabled for offline use;
- a visible, HTML-escaped attribution footer is injected into every page;
- the generated signature directory and every generated page are resolved and
  checked before `mkdir`/writes: they must stay inside the explicit output root
  and outside the pinned upstream and installed resource trees, and a resolve
  alias for either the directory or a page name is refused;
- the output cache is keyed by adapter bytes, upstream HTML, source root and
  attribution; pages are created exclusively, repeat writes are byte-identical,
  and a changed existing cache (including a file that races into existence) is
  refused instead of overwritten.

No browser is opened and no server is started.

## Attribution and rights boundary

The pinned upstream at the library commit is licensed as "MIT License (with
Attribution Requirement)"; it is not plain SPDX `MIT`. The generated overlay
therefore always shows `yang0 — https://github.com/yang0/handraw-style` plus the
operator-configured `attribution` / `repository` values, HTML-escaped, with a
note that the attribution is required by the pinned upstream license. The
first-party adapter code itself remains owner-authorized Apache-2.0; no upstream
code, artwork, gallery, image or personal Skill source is redistributed here.

Third-party asset rights are not verifiable by this model. The legacy brief
keeps `license_status: not-declared` and `asset_rights_status: unverified`
because that older checkout has no declared license evidence. For the full
library, the host's independently reviewed packaged config may supply
`license_status: verified-pinned-custom-license-with-attribution`; the adapter
passes an explicit config value through, but never invents it. A
`Library(config)` with no `license_status` reports `not-declared`, and asset
rights remain `unverified-for-redistribution` whether or not a license status is
supplied. License evidence is not inferred from package name, config commit or
existing copyright strings alone. Every result keeps `image_generated: false`,
and gallery output is a local operator artifact, not a public-distribution
input.

## Tests

`tests/test_handdraw_brief_contract.py` and
`tests/test_handdraw_library_contract.py` use only the standard library and build
entirely synthetic pinned checkouts, manifests, resolver/layout helper modules,
data rows and minimal gallery HTML. All are marked `SYNTHETIC TEST ONLY`; they
patch the subprocess fallback so no real Git runs, never touch the network, and
skip a symlink check honestly when the host cannot create symlinks. Additional
deterministic cases script `Path.read_bytes`/`Path.read_text` read swaps to
require refusal (or single-read success with the unverified marker unexecuted)
before tampered bytes are consumed, mock `Path.resolve` aliases for the gallery
signature directory and page names without needing OS symlink privilege, and
exercise exclusive-creation races for brief and gallery outputs.

Suggested host command (tests were not run by the model):

```text
PYTHONPATH=<candidate>/scripts python -m unittest discover -s <candidate>/tests -v
```

The host is expected to run these specs, a real pinned-upstream runtime smoke
check without image generation or UI startup, and an isolated wheel install.
