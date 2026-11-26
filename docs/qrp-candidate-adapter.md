# QRP candidate conversion

Updated: 2026-09-11 23:45:00 +08:00. Acting tool/model: Codex (GPT-6 Astra).

`scripts/qrp_candidate_adapter.py` consumes the existing QRP offline evidence pack
version 1.0.0, its five stage receipts, candidate brief, research-output evidence
bundle and review packet. The caller supplies a reviewed pack file SHA256 and
explicit `--allow-unverified-draft`. This is a separate candidate-only entry;
`research_output_adapter.py` retains its verified-answer default unchanged.

```powershell
python -B scripts/qrp_candidate_adapter.py --pack <offline-evidence-brief.v1.json> --expected-pack-sha256 <reviewed-file-sha256> --output-dir <candidate-directory> --allow-unverified-draft
```

The adapter reuses the existing unverified-draft semantic validator, section
builder, deterministic Markdown formatter and content object builder. It does
not run the HTML renderer, model, browser, service or upstream executor. An
unavailable model does not prevent conversion of already recorded evidence.
Incomplete or changed evidence/receipts stop conversion; no model fallback occurs.

Output is `content-item.v0.2` with root status `candidate` and channel status
`draft` (the channel enum has no `candidate`). Fact review remains blocked;
privacy, compliance and rights remain unreviewed; human review remains required.
Source admission is mapped conservatively to `unverified`, since the sourceRef
enum has no `candidate`. The exact upstream status snapshot, brief, review packet,
contradictions, unknowns, closure_run_id and original fixture input_sha256 remain
in channel platform metadata. Verified facts are empty. Visual renderer and
output format are `none`, with no rendered artifact references.

The conversion manifest binds the original input_sha256 separately from the
pack file hash and evidence bundle canonical-payload hash. QRP stage receipt
hashes are canonical JSON hashes; projection receipts and artifact hashes are
file-byte hashes. They must not be interchanged. The manifest is written last;
identical partial outputs can resume. Existing conflicting output fails before
any new write. The adapter does not clean up or overwrite artifacts.

Intent: make the producer's candidate brief usable without inventing facts.
Decision: add a thin entry and focused acceptance tests; leave the original
adapter, shared Schema, catalog and external policies unchanged.
Reason: facade labels alone are insufficient and synthetic source review must
not become factual verification. Evidence: this dispatch's pinned five-stage
pack, exact receipt/source checks and retained positive/negative conversions.
Scope: private Content Studio development overlay only; no public promotion.
Rollback: after confirming these three newly added files have no subsequent
edits, an authorized owner can remove this module, its focused test and this
guide; no existing project file or shared catalog requires restoration.

The focused acceptance module reads only the pinned fictional closeout pack.
Set `CONTENT_CANDIDATE_TEST_ROOT` to a new retained directory and run
`python -B -m unittest discover -s tests -p test_qrp_candidate_adapter.py -v`.
Tests use one thread and retain their explicitly indexed synthetic copies. This
dispatch forbids deletion/ACL changes, so they deliberately do not invoke the
managed runtime's cleanup lifecycle or use TemporaryDirectory.
