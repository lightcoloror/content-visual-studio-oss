# Protected Content Regression Test Source Guide

## 1. Purpose and Scope
This document specifies the regression source contracts for `WoundAcceptanceProtectionTests` (3 methods) under the Apache-2.0 license. The source expresses expectations for chosen JSON serialization hashes and before/after snapshot dictionary comparison in an acceptance workflow; those expectations were not executed in this batch. All original source lines and the complete AST are retained, with CRLF normalized to LF. This increment includes no runner code, historical JSON payload or medical record.

## 2. Test Method Contracts
The suite defines three explicit regression contracts:
- `test_committed_protected_content_matches_canonical_contract`: Evaluates `_assert_protected_content()` against runner-declared JSON references and expected hashes. The referenced files and runner are unbundled; missing inputs prevent runtime execution rather than source redistribution.
- `test_canonical_hash_ignores_json_formatting_and_line_endings`: Verifies that `_canonical_json_value_sha256` yields identical digests across compact and indented CRLF formatting for an inline dictionary (`{"title": "敷料观察", "signals": ["湿透", "松脱"]}`). This asserts formatting independence for the same explicit parsed payload, not arbitrary key-order differences, universal semantic equivalence or standardized JSON canonicalization.
- `test_runtime_byte_guard_detects_any_in_run_change`: Confirms that `_assert_protected_bytes_unchanged` accepts identical dictionaries and raises `RuntimeError` on mismatched values. This checks snapshot dictionary equality, not continuous OS filesystem monitoring, TOCTOU race protection, or detection of reverted changes.

## 3. Dependencies and Verification Limits
- **External Dependencies**: The module imports the entire run_wound_visual_e2e.py at module scope; that first-party runner and its rendering dependency are absent from this public parent and not included here. It also expects historical protected inputs which are not distributed. Even the two pure-looking methods cannot be claimed independently runnable; no environment rebuild or runnable quickstart is provided.
- **Verification Status**: All 3 test methods remain strictly **UNEXECUTED (NOT RUN)**. Verification is limited to static source reading and AST compilation. Inline strings are synthetic test literals, not clinical or patient records.

Reading and compiling source does not establish actual preservation of a file, real source truth, privacy, rights, rendered quality or publication permission. No original test/module import, protected input/hash operation, renderer, browser, media processing, network request, model generation, installation or service ran. Historical expected hashes and fixture strings grant no execution authority.
