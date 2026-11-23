# Handdraw Gallery Runner Source Guide

## 1. Purpose and Scope
This document specifies the regression source contracts for the first-party UI acceptance runner under the Apache-2.0 license. The source defines intended automated headless Chromium checks for handdraw gallery pages without bundling gallery HTML, images, fonts, Playwright libraries, or browser binaries. Unprovided external assets are not claimed to be synthetic or verified.

## 2. CLI Invocation and Lifecycle
The runner requires four ordered positional arguments:
1. `galleryRoot`: Path to local gallery HTML (`index.html`, `layouts.html`, `colors.html`).
2. `outputRoot`: Directory for `ui-report.json` and PNG screenshots (overwriting fixed filenames).
3. `chrome`: Executable path for headless Chromium.
4. `playwrightPackage`: Package anchor resolved via `createRequire(path.resolve(...))('playwright')`.

The package anchor is explicitly resolved with path.resolve; gallery URL conversion and filesystem output paths use process cwd for relative paths. The chrome argument is passed as provided to Playwright; its runtime resolution is unverified. No root confinement or complete input preflight is added. Module loading, directory creation, and browser launch execute before the main `try/finally` block; early launch failures throw before report creation or browser cleanup.

## 3. Test Cases and Transport Guards
Six planned cases evaluate desktop (1440x1000) and mobile (390x844) viewports across three pages:
- **Visual Checks**: Expects image loading for images with a source (`naturalWidth > 0`), no horizontal overflow, exact category filter counts, size switching (`1x`), modal dialog bounds, Escape dismissal, language toggling (`en`), and zero page errors.
- **In-Page Clipboard**: Replaces clipboard operations with an in-page buffer (`window.__copied`). Synthetic denial accepts a recorded manual dialog, a fallback element, or a button label that does not claim copying succeeded. It does not require fallback display in every accepted case and tests page mechanics rather than OS clipboard acceptance.
- **Request Routing**: Aborts requests outside `file:`, `data:`, and `blob:`, recording external URLs in `blocked_external`. This provides client-level request interception, not an OS sandbox. If execution reaches the final report check, recorded failures set process.exitCode = 2; earlier uncaught exceptions can terminate before that code or a completed report.

## 4. Verification Status and Limits
All UI scenarios remain strictly **UNEXECUTED (NOT RUN)**. Full source inspection and one actual node --check invocation completed with SYNTAX_EXIT=0. The binary used reports ProductVersion 22.17.1 in host file metadata. Syntax parsing did not execute the module, launch a browser, resolve Playwright or open the gallery. Source bytes remained identical; no syntax check was rerun. No runnable quickstart is provided.

All 106 source lines, browser options, selectors, assertions, report writes, try/finally blocks and exit logic are preserved byte-for-byte. Original and staged copies already used LF; no normalization change was necessary. This is a first-party working source snapshot, not historical Git-inclusion evidence. No new runtime, framework, router or production gate is introduced, and no rights clearance for external gallery assets follows from source publication.
