# Candidate: multi-owner editorial synthesis and document-render lifecycle

Added 2026-11-07 to the 218-file public baseline `content-visual-studio` 0.1.4.
This document is the implementation/dependency difference note for the current
`implement` stage. It is source + explicitly synthetic fixtures only: nothing was
installed, imported for behaviour, or run in this stage.

## Added files

| Path | Role |
| --- | --- |
| `scripts/original_synthesis_adapter.py` | plan → candidate article/oral script/fact card/HTML + native Main consistency receipt |
| `scripts/document_render_artifact_lifecycle.py` | Content Studio classification/admission adapter over the unchanged Artifact Lifecycle Core; plan only |
| `config/document-render-artifact-lifecycle.v1.json` | new first-party config; Core API/profile SHA-256 pinned to the supplied public Core bytes |
| `scripts/studio_assets/config/document-render-artifact-lifecycle.v1.json` | packaged copy of the same bytes (installed layout) |
| `fixtures/artifact-lifecycle/synthetic-render-root/` | marker-bound synthetic render root (marker, classification, one candidate, one protected final) |
| `scripts/studio_assets/fixtures/artifact-lifecycle/...` | packaged copy of that synthetic fixture |
| `fixtures/synthesis-lifecycle/` | new wholly fictional public-archive input, WCF-style capture, reviewed-research fixture, consumer index and editorial plan |
| `scripts/studio_assets/fixtures/synthesis-lifecycle/...` | packaged copy of the same synthetic bytes |
| `tests/test_original_synthesis_adapter.py` | plan/persistence counterexamples plus native reviewed-research negatives |
| `tests/test_document_render_artifact_lifecycle.py` | adapted lifecycle counterexamples (marker, admission, classification, Git/owner/process/dispatch, plan/verify, restore, doctor) |
| `tests/test_multi_owner_native_integration.py` | real public QRP → Main gate → Artifact Core synthetic closed loop, text-only and HTML |
| `tests/run_synthesis_lifecycle_tests.py` | serial isolated-copy runner; records command/env/exit code/first failure |
| `docs/candidate-synthesis-lifecycle.md`, `docs/candidate-synthesis-lifecycle-tests.md` | this note and the test contract |

Only `pyproject.toml` (package entries/package-data) and `README.md` change among
baseline files; every other baseline file keeps its original bytes.

## Native owner APIs checked statically

* `public-qrp` `646b3871…`: `question_research_poc.bounded_deep_loop._load_fixture`,
  `question_research_poc.offline_evidence_brief.run_offline_evidence_brief`, and the
  `bind_qrp` source/installed byte-drift check in the baseline `qrp_owner_binding.py`.
* `public-main` `fff2b6e1…`: `cross_platform_fact_consistency_gate.validate_input`,
  `create_receipt`, `write_receipt`, `validate_receipt`, `sha256_text_file`,
  `OUTPUT_ROOTS`, and `registered_self_media.load_module` / `scripts_root` registry
  identity and mixed-module-root refusal.
* `public-lifecycle` `fab23908…`: `artifact_lifecycle_core.scan_root`,
  `plan_operation`, `verify_plan`, `restore_from_receipt`, `doctor`,
  `validate_profiles`, `attach_hash`, `atomic_write_json`, `read_json`,
  `canonical_sha256`, `git_status`. Core API SHA-256
  `e0b6ad47…` and profile SHA-256 `a3067ad9…` match the supplied bytes.

No owner source, schema or threshold was copied into the candidate; no second
renderer/router/fact classifier/lifecycle implementation was added.

## `original_synthesis_adapter.py` differences from the frozen working source

The frozen working file SHA-256 is `b479ddbd…`. Preserved: the complete plan
schema/semantic guard set, quote handling (25-word total per source across both
orders, quote-type and quote-source drift, quote-in-archive), canonical claim
drift, evidence-link equality, source-type authority, number/case/platform
refusals, withheld promotion, fact-card/content-item schema validation, trace
snapshot, checkpoint/immutable-precheck/partial-resume/idempotence, cross-platform
claim/hash gate, draft-only review packet and no publication authorization.

Changed only where the frozen file depended on an unavailable sibling layout:

1. Removed `W/'self-media-creation-system/scripts'` and
   `W/'question-research-poc/src'` `sys.path` guesses. The Main gate now loads
   through the existing `registered_self_media.load_module` registry API (so the
   existing root-match and mixed-module-root refusals still apply) and QRP binds
   through the existing `qrp_owner_binding.bind_qrp` API with an explicit
   `--qrp-root`/`CONTENT_STUDIO_QRP_ROOT`.
2. QRP capture loading uses the bound `bounded_deep_loop._load_fixture` rather than
   importing a sibling path; installed/source byte drift and module-root mixing are
   rejected by `bind_qrp`.
3. Owner modules are imported lazily, so `--help`, a missing-owner report and a
   text-only contract run do not require QRP/jsonschema/markdown-it-py at import
   time. A missing or unmatchable owner raises `qrp_source_root_required`,
   `qrp_module_root_mismatch`, `registered_self_media_root_mismatch` or
   `mixed_self_media_module_root` instead of substituting a mock.
4. The fact-card schema resolves through `studio_paths.STUDIO_ROOT` (source tree or
   installed `studio_assets`) instead of a hard-coded sibling directory.
5. The common workspace root is explicit (`--workspace-root` or
   `CONTENT_STUDIO_SYNTHESIS_WORKSPACE`); an installed layout must supply one.
   Outputs stay under that root and the Main gate's own `OUTPUT_ROOTS`, and the
   adapter refuses to run when the gate's `WORKSPACE_ROOT` differs from the
   declared workspace (otherwise gate-relative receipts would be misleading).
6. `strip` of the frozen `VERSION` replaced by semantic `2.1.0`; the consumer index
   states it does not claim a repository HEAD.

Text-only and HTML are both required: the HTML path uses the unchanged
`article_visual_pipeline.render_article_html` (`editorial-field-guide` theme) and
is covered by the integration test; text-only remains an explicit flag, never the
only tested route.

## `document_render_artifact_lifecycle.py` differences from the frozen working source

The frozen working file SHA-256 is `02fa9fbb…`. The Core remains the only scan,
classification-application, plan, verify, quarantine and restore implementation;
the adapter still contributes only root admission, Content Studio classification,
Git/owner/process/dispatch blockers and explanation. There is still no production
quarantine/purge command.

Changed:

1. `CONFIG_PATH` resolves through `studio_paths.STUDIO_ROOT` (source or installed
   `studio_assets`) instead of `__file__`'s parent; `CONTENT_STUDIO_ARTIFACT_LIFECYCLE_CONFIG`
   is an explicit override.
2. The hash-pinned Core root is explicit (`--core-root` or
   `ARTIFACT_LIFECYCLE_CORE_ROOT`). The config's `default_root` is empty and the
   adapter now refuses it (`CORE_ROOT_REQUIRED`) instead of resolving the current
   working directory.
3. A synthetic test copy must live under an explicit operator work root
   (`--work-root` or `CONTENT_STUDIO_ARTIFACT_WORK_ROOT`); the previous implicit
   candidate `outputs/.test-runtime` admission is gone.
4. Disk policy is still read live from the hash-pinned shared profile; no reserve,
   warning or headroom number is mirrored in the adapter. The public config bytes
   are unchanged from the supplied reference projection and bind the public Core.
5. `_process_probe` is unchanged in behaviour: a missing platform capability
   (`OSError`, non-zero probe) yields `unknown`, which blocks a plan through the
   existing `active_process_not_cleared` gate; it is never reported as quiescent.
   No new monitoring platform was added.
6. `git_root` may be explicit for the clean-Git gate; unknown/dirty/not-a-repository
   states remain blocked, and `plan_gc` still requires `owner_state=idle_confirmed`,
   `process_state=idle_confirmed` and `dispatch_state=none_active` before any entry
   can be eligible. Generic `TOOL_ID`/`OWNER_LANE` and historical author attribution
   are retained as contract data.
7. Restore remains a narrow synthetic-only outlet (`--synthetic-test-mode` plus
   `--execute-synthetic-restore`) and is exercised only on the copied synthetic
   fixture; no input, historical output or real directory is moved or cleaned.

## Dependencies

No new third-party dependency, version bump, install or network access. Runtime
reuse only: stdlib (`argparse`, `hashlib`, `importlib`, `json`, `os`, `subprocess`,
`sys`), the already-declared `jsonschema` / `markdown-it-py` path through the
existing baseline modules, and the three external Owners loaded from explicit
roots. `pyproject.toml` adds two `py-modules`, two console entry points and the
new package-data globs only.

## Boundaries of this stage

Only text/AST/JSON/hash static checks were performed. The two modules and the
tests were **not imported or run**; the native owner loop is written as the next
stage's executable test plan. A synthetic pass would still not prove real field
work, author confirmation, publication permission, browser layout or a real
installed-package acceptance.

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
