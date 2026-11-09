# Static Browser QA Source Helpers

`docs/static-browser-qa-source.md` describes the optional, source-only Node.js browser diagnostics for inspecting already-rendered static HTML and SVG artifacts. These first-party utilities reside in `scripts/`, licensed under Apache-2.0. They provide dual-viewport rendering diagnostics for long-form articles (`scripts/article_browser_qa.mjs`) and targeted PNG rasterization for social card elements (`scripts/social_card_playwright_bridge.mjs`). Both share the local runtime adapter `scripts/browser_qa_runtime.mjs` alongside the public `scripts/typography_gate_collector.mjs`. Existing source collector threshold contracts are retained without new package registries, default routes, or installer distributions.

The standalone script `scripts/chinese_typography_browser_qa.mjs` is an independent diagnostic; it does not use `browser_qa_runtime.mjs`, and this document neither covers nor supersedes its usage.

## Scope and Security Model

These utilities diagnose pre-rendered static files without running an HTTP server. They operate strictly on local disk inputs:

- **Static Markup Only**: Pages are inspected with JavaScript disabled (`javaScriptEnabled: false`). Dynamic application scripts, client-side routing, and DOM hydration are not supported.
- **External Dependencies**: No browser binaries, package installations, or font assets are distributed with this repository. Operators must supply an existing Chromium executable (`--chromium`), an installed driver package manifest (`--puppeteer-package` or `--playwright-package`), and a hash-verified typography policy (`--typography-policy` with `--typography-policy-sha256`).
- **Package Loading Boundary**: The runtime loader resolves packages using `createRequire` against the supplied manifest path. Checking that `package.json` contains `"puppeteer"`, `"puppeteer-core"`, or `"playwright"` validates configuration structure only; it does not verify package integrity, supply-chain safety, or software licensing.
- **Sandboxing and Isolation Limits**: Page-level offline flags and `assetRoot` path checks intercept external URL navigation, but they do not provide OS-level process isolation, network firewalls, or TOCTOU-safe filesystem virtualization. The social-card launcher explicitly requests `chromiumSandbox: true`; the article launcher retains Puppeteer defaults without adding sandbox-disabling arguments. Actual enforcement has not been tested. The wrappers do not add `--no-sandbox`.
- **Output Safety**: The `protectOutput` helper inspects device and inode identifiers (`stat.dev`, `stat.ino`) to prevent overwriting inputs or runtime dependencies. It does not establish directory containment or guard against every alias. Destination directories must be created prior to execution.
- **Metadata and Compliance**: Local JSON reports capture inspected paths, extracted text, and layout measurements. In reports, `rights_complete` denotes the presence of required metadata fields only, not copyright clearance or clinical review.

## Quoted Placeholder Usage

Replace every placeholder, including profile IDs, with actual values from your approved policy. The repository does not supply those driver runtimes or choose an authoritative policy for you. Use distinct output paths outside the inputs and runtime files; the guard is not an output-root boundary. The multi-line commands below use POSIX shell continuation syntax.

Invoking `--help` prints required arguments and exits immediately without launching Chromium.

### Article Dual-Viewport Diagnostic

Inspects 1200x900 desktop and 390x844 mobile viewports, evaluating typography constraints and writing a structured report:

```bash
node scripts/article_browser_qa.mjs \
  --html "path/to/assets/input.html" \
  --desktop "path/to/desktop.png" \
  --mobile "path/to/mobile.png" \
  --report "path/to/report.json" \
  --chromium "path/to/chromium" \
  --puppeteer-package "path/to/puppeteer/package.json" \
  --typography-policy "path/to/typography-policy.json" \
  --typography-policy-sha256 "<lowercase-64-hex-digest>" \
  --desktop-typography-profile "<desktop-profile-in-policy>" \
  --mobile-typography-profile "<mobile-profile-in-policy>" \
  --asset-root "path/to/assets" \
  --allow-no-figures "true"
```

### Social Card Inspection

Locates a specific element index via CSS selector, measures font gate metrics, and captures a PNG screenshot:

```bash
node scripts/social_card_playwright_bridge.mjs \
  --html "path/to/assets/cards.html" \
  --output "path/to/card-0.png" \
  --selector ".social-card" \
  --card-index "0" \
  --chromium "path/to/chromium" \
  --playwright-package "path/to/playwright/package.json" \
  --typography-policy "path/to/typography-policy.json" \
  --typography-policy-sha256 "<lowercase-64-hex-digest>" \
  --typography-profile "<social-profile-in-policy>" \
  --expected-count "4" \
  --asset-root "path/to/assets"
```

## Exit Codes and Result Interpretation

- **Article Runner**: Emits a JSON summary and writes the report file. If either viewport fails layout or typography gate criteria (`!report.passed`), the process terminates with exit code `2`.
- **Social Card Runner**: Evaluates typography metrics and card overflow (>4px sets `font_gate.passed = false`). However, the social wrapper does **not** exit with a non-zero code merely because `font_gate` failed; it still captures the screenshot PNG without setting a failure exit code for that result alone. Other errors can still abort. Consumers must inspect the emitted JSON payload to verify gate compliance.
- Neither tool grants publication approval or certifies production suitability.

## Verification Status

Candidate helper tests achieved 11 passes across argument normalization, output guards, and offline context setup. Static syntax checks and `--help` options executed successfully. A prior Node.js child probe failed with `EPERM`, and no browser instance was launched afterward. No runtime retry was conducted in this batch. Live screenshots, font rendering, browser sandbox enforcement, and remote request denial remain unverified. For this source edition, the Owner reran the 11 direct helper cases (11 pass, 0 skip), three syntax checks, two no-browser help commands, and two expected missing-argument failures under Node 22.17.1. These checks do not start a browser or repeat the denied native-child probe.

To run the helper test separately, set `CONTENT_STUDIO_BROWSER_TEST_ROOT` to a new, empty, task-owned synthetic directory and invoke `node tests/test_browser_qa_runtime.mjs` directly. It writes invented HTML/text and a hardlink there; it does not use a browser or spawn another Node process. Do not reuse an existing test directory or treat those mocks as page-rendering evidence.
