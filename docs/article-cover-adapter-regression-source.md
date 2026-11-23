# Article & Vertical Cover Adapter Regression Source Reference Guide

Destination: `docs/article-cover-adapter-regression-source.md`
License: Apache-2.0

## 1. Purpose
This document provides reference documentation for two first-party regression test suites in ContentStudio:
- `tests/test_baoyu_adapter.py` (Baoyu article layout regression, 3 methods)
- `tests/test_marp_adapter.py` (Marp vertical slide-cover regression, 3 methods)

Together, these 6 test methods define adapter-level contracts for explicit renderer opt-in, remote image download rejection, title character budgets, deterministic cache generation, and vertical cover geometry (`1080x1350`). The suite is preserved as generic Apache-2.0 test source with minimal input path adaptation, avoiding reliance on historical private assets or uncommitted local caches.

## 2. Two-File Regression Specification Table

| Source File | Method Count | Test Method Names | Source Assertions (Not Executed) |
|---|---|---|---|
| `tests/test_baoyu_adapter.py` | 3 methods | 1. `test_baoyu_remains_explicit_item_only`<br>2. `test_remote_markdown_image_is_rejected`<br>3. `test_static_blocks_and_deterministic_cache` | • Enforces `explicit_adapter: True`; fails closed with `off by default` when disabled.<br>• Rejects remote Markdown images (`remote image downloads are disabled`).<br>• Verifies deterministic caching for Mermaid diagrams and AntV infographics across repeated runs.<br>• Asserts complete HTML output structure, stripped raw code fences, `review-required` QA status, and hard checks passage. |
| `tests/test_marp_adapter.py` | 3 methods | 1. `test_marp_budget_rejects_long_title`<br>2. `test_marp_remains_explicit_item_only`<br>3. `test_renders_vertical_cover_and_receipt` | • Enforces copy budgets; rejects titles exceeding 22 Chinese characters (`title exceeds`).<br>• Enforces `explicit_adapter: True`; fails closed when disabled.<br>• Verifies vertical cover rendering at fixed geometry (`1080x1350`).<br>• Supplies safe_crop/focal_point data in the inline item; directly asserts output dimensions, generated files and review-required receipts. The source does not independently assert rendered focal positioning. |

## 3. Environment Input Variable Specification

To remove hardcoded historical file paths without introducing fragile auto-discovery, the test `setUp` logic resolves three explicit environment variables via `resolve_external_file_from_env`:

| Environment Variable | Target Consumer | Expected Asset Characteristic | Fail-Closed Behavior |
|---|---|---|---|
| `CONTENT_STUDIO_TEST_BAOYU_PHOTO` | `BaoyuAdapterTests.setUp` | Authorized local photo compatible with the original scenario and renderer; copied as photo.jpg without format conversion or identity/semantic certification. | Fails immediately in `setUp` if unset, empty, or pointing to a nonexistent file. |
| `CONTENT_STUDIO_TEST_BAOYU_INFOGRAPHIC` | `BaoyuAdapterTests.setUp` | Local AntV infographic specification (`.ifgc`) read as UTF-8 text. | Fails immediately in `setUp` if unset, empty, or pointing to a nonexistent file. |
| `CONTENT_STUDIO_TEST_MARP_PHOTO` | `MarpAdapterTests.setUp` | Local background photo file used for vertical cover overlay. | Fails immediately in `setUp` if unset, empty, or pointing to a nonexistent file. |

**Operational Rules**:
- Operators must supply explicit, authorized local files. No default fallback directories, automatic downloads, or synthetic asset fabrication are permitted.
- The path resolver verifies file existence; it does **not** assert cryptographic image hashes, copyright clearance, or patient consent.

## 4. Setup, Teardown, and I/O Boundaries
- **Predictable local runtime paths, not a sandbox**: Both suites use outputs/.test-runtime/<testMethodName>/. Baoyu setUp/tearDown use recursive removal; Marp removes immediate files then the directory. Pre-existing files at these predictable paths may be removed. Input resolution occurs after some setup writes/cleanup; missing env/file rejection does not prove no prior filesystem effects. None of this was executed here.
- **Baoyu File Operations**: In `setUp`, `CONTENT_STUDIO_TEST_BAOYU_PHOTO` is copied via `shutil.copyfile` to `photo.jpg`, and synthetic Markdown text is written to `wound-article.md` embedding the photo reference, a Mermaid flowchart, and the infographic text.
- **Marp File Operations**: In `setUp`, `cover.md` is initialized with synthetic text, and `photo_path` references `CONTENT_STUDIO_TEST_MARP_PHOTO` for overlay compositing.
- **Content Disclaimer**: The wound-care copy in the test fixtures is a generic synthetic mock for layout testing; it does not constitute clinical guidance, patient data, or medical advice.

## 5. Execution Status and Verification Scope
- **Execution State**: **0 of the 6 test methods were executed in this documentation batch.** No test passes or runtime certifications are claimed.
- **Integration Decorators**:
  - `BaoyuAdapterTests.test_static_blocks_and_deterministic_cache` is gated by `@unittest.skipUnless(os.environ.get("RUN_BAOYU_INTEGRATION") == "1", ...)`.
  - `MarpAdapterTests.test_renders_vertical_cover_and_receipt` is gated by `@unittest.skipUnless(os.environ.get("RUN_MARP_INTEGRATION") == "1", ...)`.
  - These decorators represent source-level preconditions, not an actual skip/pass result in this increment.
- **Resolver Checks vs. Suite Execution**: Checking explicit file resolution with the actual public resolver does not validate image decoding, Marp layout rendering, or end-to-end adapter execution.

## 6. Renderer, External Runtime, and License Boundaries
- **Renderer Candidate**: Both suites load `scripts/render_content_artifacts.py` dynamically via `importlib.util`. The full renderer implementation (`edf75b6`) is a separate pending candidate and is not assumed published or bundled here.
- **External Dependencies**: Full rendering requires external CLI engines and parsers (Marp CLI, Mermaid, AntV) not bundled in this repository.
- **Synthetic Gate Statuses**: Inline flags (`fact: pass`, `rights: pass`, `privacy: pass`) and `human_review: {status: required}` are declared mock inputs, whose presence does not independently validate downstream metadata serialization, not real-world rights clearances or regulatory approvals.
- **Licensing**: First-party test source code is licensed under Apache-2.0. Third-party runtime engines retain their respective upstream licenses.

## Narrow input-binding check
The Owner performed 15 read-only/in-memory controls over the three extracted
candidate resolver call expressions and the actual existing public resolver:
unset, blank, nonexistent-file and directory inputs reject; an existing task
text file resolves to its exact path. This proves only these file-resolution
conditions. The text file was not an image/infographic fixture or a replacement
for the original scenarios. All six original methods remain NOT RUN. No
copyfile, image decoding, infographic parsing, setup/cleanup or render ran.
The test sources have all original methods and other AST intact; only three
setUp input bindings changed. External input rights, API compatibility and full
integration remain unverified. No new workflow/publication gate is introduced.
