# Synthetic Editorial Evidence Tests

`docs/editorial-evidence-tests.md` documents the optional, source-only synthetic test suite in `tests/test_human_voice_editorial_evidence.py`, licensed under Apache-2.0. The suite exercises the public `human_voice_gate` module without changing packaging, production APIs, or project dependencies.

## Execution and Environment

Run tests directly from the repository root using existing Python dependencies:

```powershell
$env:CONTENT_STUDIO_HUMAN_VOICE_ROOT = (Resolve-Path -LiteralPath "./fixtures/synthetic-voice").Path
python -X utf8 -B tests/test_human_voice_editorial_evidence.py
```

The explicit voice-root setting selects the existing inert `fixtures/synthetic-voice/SKILL.md` and `references/rulebook.md`. These are synthetic test inputs, not an installed Skill or a personal voice profile. The default real-operation path can be absent; missing source fails closed. Use the interpreter with your existing project dependencies. No installation or real author material is required.

Tests import `tests/temp_workspace.py` and load fixtures from `fixtures/case-video-script-v1`. Test isolation relies on a task-owned working copy that creates and cleans synthetic JSON files during teardown; this directory is not read-only. Workspace scratch paths honor `CONTENT_STUDIO_TEST_TEMP_ROOT` if explicitly defined, defaulting to `outputs/.test-runtime/temp` within the source checkout.

## Suite Structure and Contracts

The suite implements 5 `unittest.TestCase` methods covering structural and hash-bound validation:

- **Idempotence & Semantic Repair**: Verifies deterministic receipt generation across repeated executions when lexical match diagnoses return zero hits.
- **Unchanged Pass-Through**: Confirms unchanged synthetic scripts retain matching input and output body hashes under `review_without_rewrite`.
- **Negative Contract Mutations**: Evaluates 8 subtest mutations (missing review blocks, hash mismatches, unmatched text spans, blocked checks, duplicate IDs, and hook drifts), asserting `HumanVoiceGateError`.
- **Disguised Edit Rejection**: Prohibits rewrite operations submitted under unchanged review mode.
- **Fact and Claim Guardrails**: Uses 2 drift subtests to verify fail-closed rejections against invented fixtures containing unauthorized numeric additions (`费用是30万元。`) or absolute payout claims (`这次一定能赔。`).

## Operational Limitations

The gate validates structural schemas, SHA-256 body/receipt bindings and declared text-span correspondence. It does not evaluate prose fluency, conduct real audio read-aloud, or collect human author approvals. Owner verification used the existing CPython 3.13.5 environment and an isolated copy of the public source: all 5 methods passed, 0 skipped, with the original assertions unchanged. The first run had 3 passing methods and 2 source-missing errors because the Owner omitted the documented voice-root setting; that failure is retained. Binding the already-public synthetic voice directory resolved the configuration issue using the same interpreter, temp root and test source. No permission refusal, security change, private Skill substitute, browser, model or audio operation was involved.

The 8 mutation subtests mostly assert the exception type, so they do not independently prove each precise rejection reason. The synthetic positive cases and the two exact-code drift/guarantee checks are narrower contract evidence; they are not semantic truth or a naturalness score. This remains an optional checkout-source test, not an installed wheel runner or new registered workflow gate.
