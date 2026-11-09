# Article Visual Validation Regression Tests

`docs/article-visual-validation-tests.md` documents the optional, source-only unit test suite in `tests/test_article_visual_validation.py`, licensed under Apache-2.0. The suite verifies schema integrity and fail-closed visual planning rules across 14 test methods, using existing public files (`scripts/article_visual_validation.py`, `schemas/content-item.schema.json`, `config/visual-source-registry.json`, and `fixtures/wechat-article-format-v1/content-item.synthetic.json`).

## Execution and Environment

Run the tests directly from the public source checkout using existing project dependencies (`jsonschema`):

```bash
python -X utf8 -B tests/test_article_visual_validation.py
```

Owner AST comparison confirmed preservation of all 14 method names and 17 assertion calls. A separate directed runtime run passed all 14 methods with 0 skips (existing CPython 3.13.5 venv, jsonschema 4.26.0). The run used a minimal copy of the unchanged public dependencies; it did not install packages, build an environment or request network downloads. Other installations need the existing project dependencies available.

## Test Methods and Validation Rules

The 14 `unittest.TestCase` methods enforce structural constraints on article visual plans:

- **Schema and Score Bounds**: Validates design system versioning and ensures review scores (0–10) fail closed on out-of-bounds values.
- **Source Registry Parity**: Confirms exact identifier parity between schema search enums and `config/visual-source-registry.json`.
- **Rights and Role Guards**: Rejects unverified asset rights, disallows stock photos as factual evidence, and checks the explicit opt-in declaration for generated-image metadata.
- **Photo-Led Mode**: Enforces photo requirements in `editorial-photo-mix` plans, rejecting icon-only plans.
- **Provenance and Slot Integrity**: Disallows discovery aggregators (e.g., Openverse) as terminal stock sources, enforces required attribution text, and prohibits duplicate slot IDs.

## Verification Boundaries

The shared seed and in-memory test cases are fictional. Real font names (`Microsoft YaHei`) and external service/license URLs appear only as metadata strings; no corresponding fonts, photographs or licensed media are bundled or downloaded. Tests validate JSON declarations only; they do not perform asset licensing clearance, medical evaluation, image rendering, or real user consent. Local schema references only; installed wheel packaging and end-to-end workflows remain unverified.
