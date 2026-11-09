# Chinese Typography Browser QA Helper

## Overview

`scripts/chinese_typography_browser_qa.mjs` is an operator-run diagnostic tool for inspecting basic Chinese typesetting heuristics in local HTML and SVG documents using Playwright Chromium (`1280x1600` headless viewport).

The script is first-party source under [Apache-2.0](../LICENSE) (SHA256: `5a9e56e6312c2cbdba639685408fc8bc7b5abc2c037006c613507136e2c86d4d`). The project license does not cover or distribute external Playwright or Chromium binaries; these must be provided by the operator.

## Syntax Check & CLI Arguments

Verify script syntax without executing or launching a browser:
```bash
node --check scripts/chinese_typography_browser_qa.mjs
```

### Required CLI Arguments
- `--input <path>`: Local `.html` or `.svg` file. SVG files are automatically wrapped in a minimal HTML container.
- `--output <path>`: Destination path for the JSON diagnostic report. Missing parent directories are created automatically, and existing files are completely overwritten.
- `--playwright-package <path>`: Path to `playwright/package.json`. The script enforces that the metadata `name` field equals `"playwright"`, then dynamically imports Chromium.

## Invocation Example

```bash
node scripts/chinese_typography_browser_qa.mjs \
  --input examples/chinese-typography/synthetic-article.html \
  --output "<explicit-report.json>" \
  --playwright-package "<path-to-playwright-package.json>"
```

### Exit Codes & Output
- `0`: Completed successfully with `0` typography findings (`status: "pass"`).
- `2`: Completed with one or more typography findings (`status: "fail"`).
- Nonzero (uncaught): Setup failure, invalid argument, non-Playwright package, missing file, or browser crash. No cleanup or output report is guaranteed on uncaught errors.

## Diagnostic Rules (GVL-TYPE-001..006)

The script applies six heuristic layout rules:

| Diagnostic ID | Rule Condition | Source Heuristic Definition |
|---|---|---|
| `GVL-TYPE-001` | Line starts with forbidden punctuation | First character matches `，。、；：！？）》】〕〉…` |
| `GVL-TYPE-002` | Line ends with forbidden punctuation | Last character matches `（《【〔〈` |
| `GVL-TYPE-003` | Western word split across lines | ASCII word (`[A-Za-z]{2,}`) bounding rects span multiple rounded vertical coordinates |
| `GVL-TYPE-004` | Single CJK character orphan line | Line text consists solely of one CJK character (`^[\u3400-\u9fff\uf900-\ufaff]$`) |
| `GVL-TYPE-005` | Stranded heading | `h1..h4` element has no following element sibling |
| `GVL-TYPE-006` | Missing body font family | `getComputedStyle(document.body).fontFamily` trims to an empty string |

## Scope & Inspection Limitations

- **Element Filter:** Inspects only visible elements matching `h1, h2, h3, h4, p, li, figcaption, td, th, [data-qa]`. Raw SVG text nodes are not inspected unless enclosed in a matched tag or `[data-qa]`. Nested matching elements may be measured more than once.
- **Line Approximation:** Line grouping rounds text range vertical coordinates (`Math.round(top / 2) * 2`).
- **Empty Pass Caveat:** A run with no matching text can return `status: "pass"` with `line_count: 0`; this does not prove meaningful layout inspection.
- **Font & Environment:** `body_font` reflects the computed CSS property, not proof that the physical font is installed, licensed, or rendered legibly on mobile viewports.
- **No Contract Authority:** Despite GVL identifiers, the script does not load shared schema contracts or authorize publication. Human editorial review remains essential.

## Source distribution and verification

This is a checkout-source helper, not a registered gate or an installed-wheel command. Replace the example placeholders with explicit operator-selected paths. The example HTML is wholly synthetic and has no asserted pass/fail result. Font family names are CSS fallbacks, not bundled fonts or proof that any font is available.

For this source publication, Node 22.17.1 passed a syntax-only check; missing-input and wrong-package-name controls failed as expected before Playwright loading. No browser, layout, font, real manuscript or mobile review was run. External package/browser versions and provenance remain unverified.

Browser execution is not network-blocked by this script: operator-supplied HTML or SVG may load referenced external resources. JSON findings can contain words or headings from that input. No browser runtime, model, font, image or other external payload is distributed in this batch.
