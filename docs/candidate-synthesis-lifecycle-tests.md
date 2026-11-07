# Targeted tests: synthesis adapter and document-render lifecycle

These tests are source-only in this stage. Run them from an isolated **copy** of
the candidate, never against the reviewed tree, with `PYTHONDONTWRITEBYTECODE=1`
and task-local `TEMP`/`TMP`/`TMPDIR`. Nothing is installed and no venv is changed.

## Explicit roots

Both new adapters refuse an implicit machine root. The test runner requires:

| Variable | Meaning |
| --- | --- |
| `CONTENT_STUDIO_PUBLIC_OWNERS_ROOT` | directory containing `public-qrp/`, `public-main/`, and (by default) `public-lifecycle/` |
| `ARTIFACT_LIFECYCLE_CORE_ROOT` | explicit public artifact-lifecycle-core root (defaults to `<owners>/public-lifecycle` in the runner) |

The tests copy the supplied public owner bytes into their own throw-away
workspace before any gate writes, and assert the copies still match the public
bytes. A missing owner root is an explicit skip in the unit classes and a
blocked result in the runner; a skip is not a pass.

## Runner

```
python -B tests/run_synthesis_lifecycle_tests.py \
  --owners-root <public owner input dir> \
  --core-root <public-lifecycle root> \
  --receipt <candidate-copy>/outputs/.test-runtime/test-receipt.json
```

The runner copies the candidate to `outputs/.test-runtime/runner-*`, runs the
three modules **serially** with `sys.executable -B`, writes one log per module
and records argv, selected environment keys, exit code, first `FAIL:`/`ERROR:`
line, duration and explicit skips in the receipt.

Individual modules (same environment, run from the candidate copy root):

```
python -B tests/test_original_synthesis_adapter.py
python -B tests/test_document_render_artifact_lifecycle.py
python -B tests/test_multi_owner_native_integration.py
```

## Coverage map

| Requirement | Test |
| --- | --- |
| Plan version/authority, duplicates, unknown claims/units | `test_original_synthesis_adapter.py` plan guards |
| Numbers/cases/platform samples never become facts | `test_invented_number`, `test_unsourced_case`, `test_platform_claim_promoted` |
| Quote type/source/archive/drift and 25-word total | `test_quote_retyped_as_inference`, `test_quote_text_drift`, `test_quote_length_limit_counts_both_orders` |
| Reviewed research binding; complete capture alone is not a fact | `ReviewedOwnerTests` claim/source/evidence/capture cases |
| Fact-card/content schema + canonical claim identity | native run in `test_multi_owner_native_integration.py` |
| Render drift against actual prose | `test_rendered_copy_drift` |
| Checkpoint/immutable precheck/partial resume/idempotence | `PersistenceTests` |
| Real QRP → Main gate → text/HTML closed loop | `test_text_only_and_html_runs`, `test_main_gate_rejects_cross_platform_claim_hash_drift` |
| Missing/mixed owner blocks | `test_missing_gate_owner_blocks`, `test_missing_owner_roots_block` |
| Plan/pack hash and output scope prechecks | `test_plan_and_pack_hashes_are_enforced_before_writes`, `test_output_must_stay_inside_explicit_workspace` |
| Marker, admission, classification traversal, unknown-path pin | `test_document_render_artifact_lifecycle.py` |
| Git/owner/process/dispatch unknown blocks | `test_dirty_workspace_owner_process_and_dispatch_all_block` |
| Core hash pin, shared absolute disk policy, doctor estimate | `test_core_api_hash_drift_blocks`, `test_doctor_uses_shared_absolute_disk_policy_and_requires_large_estimate`, `test_two_gib_warning…` |
| Plan-only/verify/explain/no purge outlet | `test_plan_verify_and_artifact_drift`, `test_production_cli_has_no_quarantine_or_purge_outlet` |
| Synthetic-only restore round-trip | `test_synthetic_restore_requires_marker_and_round_trips` |
| Real Artifact Core scan/plan/verify over the synthetic render root | `test_lifecycle_scan_plan_verify_on_synthetic_render_root` |

## Explicitly unverified in this stage

* No module was imported or executed yet; the current static receipt says so.
* No real research, field team, client, manuscript, archive or human reviewer.
* No author confirmation, fact lock, publication authorization, browser layout,
  media render, model/provider/TTS/ASR call, wheel build or pip install.
* Unit mocks of the process probe/disk usage are never reported as native
  owner integration; the native integration test uses the copied public owners.
* A plan that is internally valid or `verified` is still not execution authority:
  entries may be blocked by real owner/process/dispatch/git state.

## Subsequent independent host acceptance

The static-only statements above describe the original producer stage. The
release host subsequently ran 21 synthesis, 21 lifecycle, 7 real public-owner
integration and 3 CLI/Git boundary tests, all passing without skips. The synthesis
console callable was repaired; missing/timed-out Git and process probes remain
unknown. Git evidence is retained without permission changes or cleanup. The
serial runner now refuses to label skipped owner tests as passed. The unchanged
public QRP/Main/Artifact owners produced fresh fictional text/HTML and plan-only
receipts; caller-declared idle states are synthetic test inputs. There is no real
research verification, fact lock, author confirmation or publication authority.
Fresh installed acceptance is separately recorded in SYNTHESIS-ACCEPTANCE.md.
