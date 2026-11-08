# Offline CMS and diagram syntax contracts

These existing adapters are usable from source or the installed public package.
They validate local syntax/structure only. They do not render diagrams, fetch a
CMS bundle, start a server/browser, authenticate or publish content.

## CMS

Install this package's optional `cms` extra (PyYAML) in your own environment.
Run `content-studio-cms` or `python scripts/validate_sveltia_config.py`.
Explicit overrides: `--runtime`, `--config`, `--schema-root`.
The bundled runtime pins Sveltia CMS 0.172.4's schema by SHA-256. The schema's
declared Draft 7 is respected. Unprovided references fail with an empty Registry;
there is no automatic remote schema retrieval. YAML uses `safe_load`.
The placeholder repository in `admin/config.yml` is not a live account binding.
Exit codes: 0 valid, 1 structurally invalid, 2 blocked/error. A passing result
proves neither CMS bundle integrity nor actual content/review/publishing behavior.

## AntV syntax and slot budgets

Supply your own existing `@antv/infographic` runtime. No npm install or upstream
JavaScript is bundled or automatically downloaded by these adapters. The tested
optional parser version is 0.2.11; other versions are unverified.

```
node scripts/inspect_antv_input.mjs --module-root /path/to/infographic-cli --input fixtures/offline-contracts/antv/sequence.ifgc
```

Alternatively use `--package-root /path/to/@antv/infographic`; choose exactly one
root. The package name is checked before importing its parser. An operator-
supplied JavaScript runtime is executable code: package identity is not a code
trust/signature guarantee. Use a runtime you independently trust.

Python consumers import `slot_budget_validation` and call
`validate_antv_budget(path, template, layout_intent)`. Set
`CONTENT_STUDIO_ANTV_MODULE_ROOT` explicitly; `CONTENT_STUDIO_NODE` optionally
selects an existing Node executable. Missing runtime, parser failure or invalid
JSON is a blocked operation, never an empty success. The subprocess has a
30-second timeout. The shared layout/budget registries retain their original
eight template limits, recursive-count rules and depth limits. Marp copy checks
remain local. PPT values are metadata-only; no PPT validator is distributed.

The eight `.ifgc` examples are wholly invented first-party test inputs. Parsing
them is not renderer, typography, reading-time, visual or audience acceptance.
Python/Node unit tests with fake parsers are also distinguished from the separate
real optional-parser check in the release receipt.
