# Capture to research candidate

2026-10-03, Codex.

Intent: expose the existing topic-driven research chain and candidate consumer
through one stable offline entry rather than sample-specific glue. Decision:
reuse WCF capture JSON, QRP's five-stage receipt chain and observation contracts,
ARW's quality projection and the existing Content Studio adapter. New code only
binds these stages and imports saved captures. Reason: a prepared list of claims
is not evidence that topic-driven research has happened.

```
python -B -X utf8 scripts/capture_research_candidate.py --topic topic.json --captures captures.json --output-dir new-output
```

topic.json contains question, audience and budgets (an empty budgets object uses
QRP's bounded defaults). It contains no prefilled claims, evidence or subtopics.
captures.json is an explicit inventory of existing public or fictional WCF JSON:

```json
{"captures": [{"url": "https://example.org/page", "path": "page.json", "sha256": "<SHA256 of page.json bytes>"}]}
```

Capture paths must stay beneath the inventory directory. The command binds topic
and inventory bytes, verifies source hashes on every invocation and serializes
writers with filelock. An unknown URL never falls back to network. It does not
call models, start browsers, fetch new pages or manufacture a live HTTP result.
For real use, supply existing WCF capture metadata, not fixture HTTP fields.

An awaiting_observation result is an intentional research checkpoint (CLI exit
2), not a completed candidate. Read research.observation_contract and its basis
artifact, then invoke the same command with --observation observation.json.
Use its exact stage and basis_artifact_sha256. Existing QRP operations are:

- source_admission: reads containing URLs from the capture inventory.
- evidence_analysis: subquestions with subquestion_id, text, depth,
  basis_source_id and exact basis_quote; followup reads bind subquestion_id.
- guarded_synthesis: claims with subquestion_id, text and evidence containing
  source_id, exact text and relation. These remain candidate interpretations.

The Agent supplies these observations after reading each actual stage. This is
not a new model engine or an assertion of unattended fact checking. Missing
captures can be collected separately under the applicable authorization; changed
input inventories require a new output directory rather than silent rebinding.

After the final research stage, candidate generation runs automatically. The
result points to research-output.v1 and HTML/Markdown/review candidate files.
Repeat invocation verifies and reuses existing outputs. A candidate-stage failure
does not rerun completed research stages. The original saved-research entry is
retained for callers that already have that material. No publication is enabled.

2026-10-07, Codex (requested GPT-6 Astra / ultra; actual runtime not independently
exposed): `--auto-observations` optionally delegates the three observation
handoffs to QRP's saved-excerpt adapter. It is mutually exclusive with
`--observation`. The default manual mode is unchanged. Automatic output includes
a review bundle and explicit incomplete/semantic-analysis-not-run status;
candidate exit 0 does not imply research completion. See
`question-research-poc/docs/evidence-autoflow.md` in the workspace for bounds,
provenance, stopping and recovery details.

Evidence: two fictional themes use real WCF extraction, QRP and ARW code, then
the real content adapter. Tests check no cross-theme content, source/receipt
binding, missing-capture refusal, repeated output reuse and candidate-failure
recovery without changing completed research artifacts. Separate QRP regression:
31 passed. Scope: offline captured evidence, not new online acquisition, verified
facts, real user acceptance or a Git release.

## Optional HowToLiveBetter lead intake

2026-10-12 | Codex (runtime model not independently exposed). Reuse this entry;
there is no new collector, database, research engine or routing contract.

When a selected saved page is used as a HowToLiveBetter lead, include the following
optional object alongside `captures` in the existing inventory. URLs below are
fictional examples; they are not upstream content or verified primary sources.

```json
{
  "reference_intake": {
    "provider": "HowToLiveBetter",
    "lead_url": "https://example.org/synthetic/lead",
    "recorded_at": "2026-10-12T00:00:00Z",
    "lead_claim": "An unverified proposal to investigate, not a fact.",
    "author_rating": "A",
    "rating_system": "author_defined_not_clinical_GRADE",
    "original_sources": [
      {"url": "https://example.org/synthetic/original", "kind": "official_policy"}
    ]
  }
}
```

The lead must have a hash-bound saved capture. `author_rating` accepts A/B/C or
`not_recorded`; it describes the author's label only. An absent original citation
is represented by `original_sources: []` and stays `needs_source`. `kind` accepts
`original_paper` or `official_policy`. These are **declared roles, not proof** of
identity, publication design, authority, currency, applicability or clinical GRADE.
Save the selected page's date, exact proposal and cited URLs; do not bulk ingest.

Use the same CLI and staged observations above. No URL is fetched by this entry.
Missing original captures are reported explicitly; requesting an unsaved URL
still fails without a network fallback. Changed inventories require a new run.
Every resulting claim must cite supporting evidence from a declared original
source before candidate projection; the lead cannot serve as its own original.
Having a primary-looking URL or an exact excerpt is not semantic fact review.

The output adds `reference_intake` requirements and, at synthesis, these files:

- `reference-fact-card.json`: existing `content-fact-card.v0`, revisioned, draft,
  candidate claims excluded, fact gate blocked; no automatic confirmation.
- `reference-handoff.json`: exact fact-card revision/hash and synthesis path/hash,
  optional existing candidate/research-output paths, `story_drafting_allowed=false`.
- Existing `workflow-state.json`: the combined result. Repeat invocation reuses
  it; changed fact-card/handoff data fails rather than silently overwriting.

The content candidate's `verified_facts` remains empty and its fact gate blocked.
The normal verified research-output adapter rejects this research; the existing
unverified-draft option creates review artifacts only, not a publishable script.
For an eventual usable fact card, review original identity, methods/policy scope,
region, effective date, population, exact support, causal limits, contrary evidence
and rights through [QRP](../../question-research-poc/AGENT_DISCOVERY.md) /
[ARW](../../ai-research-workflow/integrations/AGENT_DISCOVERY.md). Then create a new
reviewed fact-card revision using the existing content-fact-card Skill and pass the
existing content gates. This optional intake never fabricates a review receipt.

Offline regression: `python -B -X utf8 -m pytest tests/test_reference_intake.py -q`.
The fixtures are original synthetic text, not downloaded HowToLiveBetter pages,
real papers, policies or health records. They prove contract behavior only.

Design and video options remain discoverable in the existing
[reference intake](../../docs/content-creation-system/source-intakes/creative-and-research-references-20261011.md).
Yovoice remains deferred.

## Delivery selection connection (2026-10-29)

Optional `--work-request <existing-self-media-work-request.json>` is supported by
both capture and saved-research entrypoints, including `--auto-observations`.
It resolves the registered self-media entry and requires the adopted topic to
match the research question. Form, platform and exact request hash are retained
in the existing state binding. Changing them cannot overwrite a completed run.

Without this argument, the export requests `guarded_answer`. Any draft produced
by the existing content adapter is explicitly an `intermediate_research_draft`;
its shape does not adopt a topic, choose article delivery or select WeChat.
Existing completed outputs are reused and labelled as intermediate in the
returned result without rewriting their old files.

With an explicit article selection, the selected platform is retained. With a
different output form, the existing research export finishes and returns
`needs_format_adapter` plus the original self-media resolve command; the article
consumer is not invoked. This does not claim that unimplemented platform
producers now exist. No collection, model, author decision or publication is
performed by this connection.

Intent/decision: reuse existing request and QRP export instead of choosing a
format implicitly. Reason: research drafts are not platform decisions.
Evidence: `test_research_delivery_connection.py` and scoped capture regressions.
Scope: optional bound delivery and truthful legacy intermediate labels only.
Tool: Codex; exact runtime model not independently verified.
