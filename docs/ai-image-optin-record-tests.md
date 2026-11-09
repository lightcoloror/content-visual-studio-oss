# AI Image Opt-In Record Consistency Tests

`docs/ai-image-optin-record-tests.md` documents the optional, source-only unit test suite in `tests/test_ai_image_generation_opt_in.py`, licensed under Apache-2.0. The suite validates deterministic keyword triggers and audit-record consistency for AI image routing via `scripts/visual_asset_routing.py`, using the existing fictional echo-garden fixture.

## Execution and Environment

Run the tests directly from the public source checkout using Python 3.10+ standard library:

```bash
python -X utf8 -B tests/test_ai_image_generation_opt_in.py
```

Owner AST comparison confirmed preservation of all 5 methods, 7 assertion calls and request lists. A separate directed run under an existing CPython 3.13.5 venv passed all 5 methods with 0 skips. This suite uses only the standard library and does not need a new environment or package installation. It reads the unchanged public module and `fixtures/wechat-article-format-v1/content-item.synthetic.json`; it requests no network access.

## Test Methods and Invariants

The 5 `unittest.TestCase` methods evaluate opt-in record consistency:

- **Trigger Filtering**: Denies 7 general visual requests while matching 3 explicit generation phrases.
- **Declared Record Consistency**: Rejects generated-image assets lacking request evidence, requiring exact quote records and `explicit_user_request=True`.
- **Recommendation Isolation**: Rejects a generated-image metadata record whose only support is a recommendation without the required request declaration.

## Operational Boundaries

Tests verify metadata strings only. `assets/synthetic-generated.png` is a synthetic reference, not a disk file. Caller-supplied text and flags can be fabricated. Keyword matches and legacy allow/authorize names do not authenticate a native user, comprehensively handle negations or grant permission for generation tools, spending or publication. Installed-wheel packaging, other platforms and the full workflow remain unverified. Real image generation models were not executed.
