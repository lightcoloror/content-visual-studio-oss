# Render Receipt Regression Test Source Guide

## 1. Purpose and Scope
This document specifies the regression source contracts for the 18 test methods in `tests/test_render_artifact_validation.py` under the Apache-2.0 license. The source asserts schema invariants, receipt hash consistency, QA field completeness, declared image-generation policy and remote asset rejection for ContentStudio artifacts without bundling rendering engines, fonts, or operational assets.

## 2. Test Contract Expectations (18 Methods)
The 18 original methods express expectations in four areas:
- **Receipt and Input Hashing**: Asserts rendered status requires output files and valid receipts; rejects SHA-256 output mismatches and invalidates receipts when hashed input files mutate.
- **Reference Integrity**: Rejects duplicate artifact or asset IDs, dangling asset and brand references, undeclared design directions, and unregistered legacy output recipes.
- **QA Gate Compliance**: Mandates inclusion of all media profile hard checks, enforces exact equality between `needs_review_count` and actual findings, and expects validation errors when approved flags coexist with failed hard checks. No actual workflow state transition is exercised.
- **Policy and Remote Asset Guards**: Enforces explicit opt-in text triggers ("模型生成图片" or "AI 生图") in declared test inputs while rejecting generic phrases; rejects remote HTTP asset references (`example.com` literals) before rendering.

## 3. Prerequisite and Verification Limits
- **Prerequisites**: Validation requires `render_artifact_validation.py` available in `codex/shared-render-validation-source-20261109` commit `b54a141afd2c96163a3c26a07177c9f826e79d1c` (absent on base `d129`).
- **Execution Status**: One isolated fail-fast invocation actually ran on Python 3.13.5 with jsonschema 4.25.1 and markdown-it-py 4.2.0: **0 passed, 1 failed, 0 skipped, 17 not run**, exit 1. The first alphabetic method, `test_baoyu_local_markdown_plan_is_valid`, expected no validation errors, but the fixed public renderer registry registers only AntV. It lacks `baoyu-md`, its pinned theme and remote-download policy, yielding three validation messages. The suite imported successfully and generated/removed synthetic test files; that does not establish full dependency compatibility. No assertion, registry or policy was changed to force a pass; no retry occurred. This is a source-only candidate with a known baseline-registration mismatch. A future, separately scoped compatible Baoyu registration and policy integration is required before rerunning unchanged assertions; no dummy registration should be used to manufacture success. No browser, image decoding, rendering or network call ran.

## Synthetic data boundary
Tests create and remove inline Markdown, dummy HTML, JSON receipts and arbitrary bytes named asset.jpg under outputs/.test-runtime. No image is decoded. Passing gates, rights and QA flags and quoted image-generation requests are test data, not established rights, truthful evidence or authority to call a model. example.com URLs are rejection literals. No pending render orchestrator is included or needed by this suite. A test result does not establish production evidence, real privacy or rights, visual quality, rendering, actual approval transitions or publication permission. Only first-party test source is distributed; no font, asset, model or private history is included.
