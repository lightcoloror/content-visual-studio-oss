# Article typography regression source

Existing browser-regression source for the ContentStudio article typography hard gate, prepared for the Apache-2.0 source edition. This directory contains the adapted test plus five explicit synthetic text fixtures under `fixtures/typography-gate/`. It intentionally does not duplicate the already-public `scripts/article_browser_qa.mjs`, `scripts/typography_gate_collector.mjs` or `tests/temp_workspace.py`.

## External runtime selection

The test reads exactly two explicit environment settings once at module import:

| Setting | Meaning |
| --- | --- |
| `CONTENT_STUDIO_TEST_ARTICLE_PUPPETEER_PACKAGE` | Path to a local `puppeteer`/`puppeteer-core` `package.json` |
| `CONTENT_STUDIO_TEST_ARTICLE_CHROMIUM` | Path to a local Chromium/Chrome executable |

An unset or blank setting means `None`. A supplied value is wrapped with `pathlib` and resolved to an absolute path, so a relative explicit path is interpreted relative to the test invocation working directory and normalized before `run_qa` starts the child with `cwd=ROOT`. The test does not scan `HOME` or `PATH` for a browser, expand user profiles, download one, or auto-discover a cache. There is no default runtime path and no fallback browser.

## Existing dependencies

- `node` on `PATH` (retained from the original test).
- The existing public `tests/temp_workspace.py` helper (`isolated_test_directory`), which writes under an explicit repository-local test temp root.
- The existing public `scripts/article_browser_qa.mjs` and `scripts/typography_gate_collector.mjs` CLI and collector, unchanged.
- A browser runtime and Puppeteer package supplied only through the two settings above.

The class-level dependency skip requires `node` plus both supplied settings to point to files. A skip is not a pass.

## What the two test methods intend to check (five intended CLI invocations)

1. `test_positive_article_passes_both_viewports` — one `article_browser_qa` invocation on `article-positive.html`. Intends to require exit code 0, a passing report, and for both viewport roles that the typography gate passes and its text nodes carry exactly the `primary_headline` and `body` roles.
2. `test_low_font_unknown_missing_role_and_hash_drift_fail_closed` — four invocations: three negative fixtures (`font-below-role-minimum`, `unclassified-reading-node`, `missing-required-roles:primary_headline`) each intend to exit 2 with the named failure, plus the positive fixture with a deliberate 64-zero wrong policy hash. The pinned public implementation rejects that hash in its preflight check (exit 2, `typography policy hash mismatch` on stderr) and writes no report or screenshots.

Invocations intended: positive 1, negative fixtures 3, bad hash 1. The bad-hash invocation never reaches the browser.

The policy hash is generated from `synthetic-policy.json` bytes unless a deliberate wrong digest is passed. In the pinned public `scripts/article_browser_qa.mjs`, both typography-policy bindings are validated before Puppeteer is loaded and before any report is written: a mismatch throws `typography policy hash mismatch` (supplied public blob lines 166-167), which the top-level catch turns into exit code 2 plus stderr, so no `report.json`, `desktop.png` or `mobile.png` is produced. The adapted `run_qa` therefore takes an optional keyword-only `expect_report: bool = True`. Normal invocations keep the original subprocess argv, capture, hash generation, temporary helper, report assertion and report loading. Only the deliberate bad-hash invocation passes `expect_report=False`: it asserts that the report and both screenshots do not exist and returns the process exit code with the actual stderr/stdout, so the test asserts exit code 2 and the exact message. File absence alone is never treated as a pass.

## Fail-fast operator command

From the repository root, with both settings pointing at a local browser runtime:

```text
python -m unittest discover -s tests -p test_article_typography_gate.py -v -f
```

This is ordinary opt-in execution. It assumes the existing public source and an installed local browser runtime; this document intentionally prescribes no policy bypasses, installation steps or permission repair.

## Status and limits

The two browser-regression methods have not been executed. Source syntax, 12 isolated path/wrapper/guard controls using in-memory doubles, and one actual Node CLI wrong-hash preflight were checked. The preflight exited 2 with the expected error and produced no report or screenshots; synthetic JSON placeholders were supplied instead of a browser/package runtime, so this did not run a browser or verify typography rendering. The complete browser cases, collector behavior and installed runtime remain unverified. Missing dependencies or skips are not passes.

The font-size policy is synthetic and test-only. It does not prove actual readability, human typographic quality or platform publication, and a font-family name is a font request rather than evidence of a shipped font or license. No network operation is needed or performed.
