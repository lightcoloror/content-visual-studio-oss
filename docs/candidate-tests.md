# Targeted unit tests (synthetic, offline)

These tests are shipped with the candidate as source, and are executed against a
**copy** of the candidate in the sibling `test-workspace/`. Every test creates
its own fresh synthetic directory; no test writes into the candidate tree.

Run one command at a time from the test copy root, with its `scripts/` first on
the import path. The public acceptance `capture-venv` Python (jsonschema,
markdown-it-py, QRP already present) and the host Node runtime are used; nothing
is installed and no venv is modified.

```
python tests/test_build_human_voice_fixture.py
python tests/test_hallmark_report_adapter.py
python tests/test_media_qa_validation.py
python tests/test_social_card_runtime.py
node  tests/test_typography_gate_collector.mjs
python tests/test_validate_insurance_clause_explanations.py
```

`CANDIDATE_TEST_WORKSPACE` may point at an existing synthetic scratch root; by
default it is the sibling `synthetic/` directory of the test copy. All runtime
data (copied fixtures, synthetic config/schema/policy files, generated JSON)
stays in that scratch root; the candidate remains source, schema, config,
documentation and explicitly synthetic fixtures only.

Required env contract for regeneration (already documented by the baseline
README and `tests/conftest.py`): `CONTENT_STUDIO_HUMAN_VOICE_ROOT` points at the
inert published `fixtures/synthetic-voice` directory. Each test sets it
explicitly before importing or spawning the candidate modules.

Not covered here (explicitly unverified): installed-wheel acceptance, browser
injection, the two typography bridge modules, real media QA, real insurance
contract ingestion, author consent and publication permission.
