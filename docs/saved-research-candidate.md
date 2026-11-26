# Saved research candidate entry

2026-10-03. Tool: Codex.

Intent: replace the one-off, topic/path-specific investigation projection with a
reusable offline command. Decision: reuse QRP native project import/export and
the existing research-output adapter. No second evidence schema or writer engine.

```
python -B scripts/saved_research_candidate.py --input <saved-synthesis.json> --capture-root <capture-directory> --output-dir <new-output-directory> --qrp-root <question-research-poc>
```

Input is the existing QRP public-archive material or a synthesis containing
derived_material. Capture byte hashes and exact excerpts are validated with the
existing QRP validator. Topic, source names, IDs, source status and output location
come from input, not a fixed sample. Sources retain generic web attribution and
candidate review status; no automatic fact or publication promotion occurs.

Reason: the investigation script hardcoded paths and assumed every capture was
partial. The supported entry records the actual capture status and separately
binds extracted-body and capture-JSON hashes. Existing filelock serializes writers.
The QRP root needs the saved-DOM compatibility repair and existing dependencies;
this command adds filelock to its runtime requirements (no installation performed).

Recovery: a completed native import is checkpointed before export. Completed
export is reused after a consumer failure. An interrupted partial import is
retained in an isolated attempt, never appended to on retry. Publication of the
local result pointer uses an atomic state-file replacement. A repeat validates
artifact hashes and returns the same candidate; changed input requires a new
output directory. No attempt folders are automatically deleted.

Evidence: four tests passed using two fictional topics, idempotent repetition,
consumer failure/resume and changed-input rejection. Real CLI invocation also
consumed the already-saved public research, generated five candidate artifacts,
and returned reused=true on a second invocation. Initial fixture failures from a
missing HTTP status were corrected in test input, not bypassed in validation.

Scope/remaining: this is the saved-research-to-candidate segment, not yet the
complete capture-to-research-to-candidate front door. Further integration and
malformed-state, interruption, concurrency and compatibility tests remain before
calling the broader task complete. No new acquisition, live account, provider,
service, removable-disk access, article publication or Git push was performed.

## Recovery boundary hardening (2026-10-03, Codex)

Intent: prevent a malformed checkpoint from redirecting native QRP commands
outside the selected output directory. Decision: resolve saved project and hash
paths under that root, reject empty hash inventories and non-object input, and
require the saved project to have covered files. Reason: the checkpoint is data,
not authority to choose another workspace. Evidence: 10 tests passed, including
path escape before native invocation, malformed input, empty inventory and
changed completed artifacts. The initial sandbox test attempt failed on temp
directory ACLs; a new isolated test directory passed with approved escalation.
Scope: offline projection and its checkpoint only. This is not authentication
against an attacker rewriting all checkpoint hashes, nor full front-door proof.
