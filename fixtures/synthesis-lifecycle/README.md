# Explicitly fictional synthesis-lifecycle fixture

Every name, record, excerpt, URL and hash in this directory is fabricated for
offline contract testing. No network request, real research, real archive,
real team, real author, client, health record or publication decision is
represented.

* `upstream/public-input.json` is a `question-research-public-archive-input.v1`
  fixture. `upstream/archives/field-notes-primary.json` is a wholly fictional
  WCF-style saved capture whose `extracted_text` is the only source text.
* `upstream/reviewed-research.json` is a `research-output.v1` fixture bound to
  that capture by content hash; it models a separately reviewed native evidence
  policy and is not a claim that the fictional handbook is true.
* `upstream/consumer-index.json` pins the three upstream files.
* `editorial-plan.json` is a candidate-only plan. Its `reviewed_research` row
  binds the reviewed fixture; removing it makes `source_fact` inadmissible.

A real QRP pack is generated from `upstream/public-input.json` at test time.
The fact gate, quote check and human review remain required; a passing
synthetic test does not create a real fact, author confirmation or publication
authority.
