# Content Visual Studio

An offline, file-based evidence-to-content and case-review toolkit. The public
edition retains the current feature working-source core and its fact, privacy,
author/read-aloud and compliance boundaries. It includes no real manuscripts,
clients, recordings, personal voice profile, platform receipts or private history.

```sh
python -m venv .venv
# Activate using your platform's normal command.
python -m pip install -e ".[test]"
content-studio-research --check-contract-only
python -m pytest -q
```

QRP is pinned to an available public commit. Schema, optional CSS themes, review
contracts and generic discovery configuration are included in the wheel.

Verified research can be converted to a content object, article Markdown/HTML,
video brief and hash manifest using `content-studio-research --research-output
<research-output.json> --output-dir <new-output-directory>`. Candidate research
is rejected by default. `--allow-unverified-draft` is an explicit review-only
route that retains blocked fact gates and does not turn candidates into facts.
`qrp_candidate_adapter.convert_pack` additionally verifies the public QRP offline
pack's receipts, byte hashes and candidate boundaries before projection.

Case scripts retain their separate review inputs. `content-studio-case`,
`content-studio-initial-review`, `content-studio-human-voice` and
`content-studio-final-cut` expose their existing bounded CLIs. A pass validates
the declared contract and bindings; it does not prove evidence truth, clinical
appropriateness, author identity, audience response or publication permission.

No personal editing source is distributed. A real human-voice operation requires
the operator's own trusted `SKILL.md` and `references/rulebook.md` directory in
`CONTENT_STUDIO_HUMAN_VOICE_ROOT`. Missing files fail closed. Tests use inert,
explicitly fictional editing documents and fictional author/read-aloud receipts;
these are not an installed Skill or real author confirmations.

MVP dry-run and owner Story Design Card validation are optional external-owner
integrations. Their actual runtimes are not copied into this repository. A missing
owner must block; it is not silently replaced. The optional E2E runner does not
prove a rendered video or authorize rendering. See the review receipt for the
specific locally tested and untested integrations.

Image search is an optional explicit command in `article_visual_pipeline.py`.
Offline tests never use it. Registry entries are discovery metadata and require
asset-specific current rights review; no image, font, music or license clearance
is supplied. Generated HTML is for trusted, human-reviewed local content.

The package does not run a background service, CMS login, model, platform publisher
or knowledge-base write. The public source and working-snapshot distinctions are
recorded in `PROVENANCE.json`. License and dependency notices are separate from
content rights. All examples and acceptance data are synthetic.

## Fresh synthetic handoff

1. Run the installed QRP `research-poc run-offline-evidence-brief` with
   `--fixture examples/synthetic-readiness-question.v1.json`, a new
   `--output-root` and an explicit `--closure-run-id`.
2. Retain the producer's emitted manifest SHA-256. Pass the pack path and that
   exact hash to `content-studio-candidate --pack <pack.json>
   --expected-pack-sha256 <reviewed-hash> --allow-unverified-draft
   --output-dir <new-directory>`.
3. Run `content-studio-visual render-html --article <new-directory>/article.md
   --output <new-directory>/article.html --title "Synthetic candidate review"`.
4. Read the candidate and the unresolved evidence/contradiction fields locally.
   The fact gate remains blocked and human review remains required. The example
   does not supply a real human decision or a publication approval.

All source/archive statements in this example are fictional fixture metadata.
No real paper, policy, web page, customer material or medical fact is researched.
The installer smoke uses this fresh producer-to-consumer chain and separately
tests a canonical verified synthetic fixture. Browser layout and audience
response are not implied by an HTML file or a passing contract.

## Saved capture handoff 0.1.1

[Capture, selected delivery and registry boundaries](docs/saved-capture-handoff.md). No new acquisition, source verification or publication authority is granted.
