# Saved capture and selected delivery

This increment reuses QRP 0.1.2, the current research-output adapter and the
existing self-media authority registry. It adds no crawler, router or database.
The first-party code is Apache-2.0; no HowToLiveBetter source text, images, papers,
music, author corpus or other upstream media is bundled.

Install the `capture` extra for mechanical passage observations. The base package
supports saved-material candidate projection and manual stage observations.
QRP and optional ARW dependencies point at fixed public commits. Supply an explicit
QRP source clone with `--qrp-root` or `CONTENT_STUDIO_QRP_ROOT`. Source mode must
use that owner; installed mode must match every source/resource file in it.
A version string alone cannot admit a stale or mixed QRP root.

```text
content-studio-saved-candidate --input material.json --capture-root captures --qrp-root question-research-poc --output-dir new-candidate
content-studio-capture --topic topic.json --captures captures/index.json --qrp-root question-research-poc --output-dir new-research --auto-observations
```

No source is fetched by these commands. Missing saved sources cannot trigger a
network fallback. Mechanical passage ordering is lexical, not semantic analysis,
truth, source authenticity, confidence, clinical GRADE or permission to publish.
Completed imports/output are hash-bound. Changed inputs or output bytes block
reuse; partial stages keep original identities instead of duplicating writes.

An optional `--work-request` must be a current, adopted self-media selection
whose topic matches the research question. Set `SELF_MEDIA_TOOL_REGISTRY` to your
explicit local registry. Its `self_media_path` and
`runtime_main.repositories.self.path` must refer to the same existing framework.
The generic public configurator emits both aliases from one owner. No private
workstation registry or fallback checkout is bundled.

A selected article keeps its selected platform. A selected non-article produces
`needs_format_adapter` and no article fallback. Without a work request, an export
is intermediate material; any article-shaped preview does not select a topic,
platform or publishing plan. Every preview stays candidate-only, with fact and
human-review requirements preserved.

Optional HowToLiveBetter lead constraints require distinct original-paper or
official-policy captures and exact candidate support. A/B/C is author-defined,
never clinical GRADE. The fact-card handoff keeps unreviewed claims excluded,
blocks story drafting and denies publication. Declared primary roles are not
independently verified merely by satisfying this structure.

`content-studio-context --handoff ...` delegates to the existing registered
execution validator. It rejects inspection-only handoffs. Current inspection,
hash-drift and delegation tests do not claim completion of a production managed
recipe, actual author confirmation or real verified research.
