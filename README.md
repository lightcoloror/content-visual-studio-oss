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

## Optional local WeChat format adapter

`content-studio-wechat-format render --help` exposes the existing synthetic and
explicit-public-review modes. Supply a separate, clean Ryan WeChat Publisher
checkout through the explicit `--source-root` option; its exact
commit and origin are checked. No checkout, installation, upload, platform draft
or publishing is performed. The upstream package declares ISC, but its code and
dependencies are not distributed here; review their notices independently.

Public-review mode requires an exact Markdown hash and the existing explicit
public-material/privacy/blocked-state checks. It produces body, preview and dark
preview HTML plus native render receipts. Author review stays required and
unresolved content gates stay unresolved. A technical render is not permission
to publish, actual device review, or platform-paste acceptance.

The local JS wrapper is bundled both for source and installed use. It preserves
the existing external renderer and validation scripts; no second renderer is
introduced. Two actual-render tests require the explicitly supplied external
checkout; rejection tests run without it. Test seeds are wholly fictional.

For the source tests only, `RYAN_WECHAT_PUBLISHER_SOURCE` locates an already
supplied external checkout. Runtime CLI calls use `--source-root`.

## Additional offline source utilities (0.1.3 candidate)

The existing first-party hallmark-report adapter, media-QA receipt validator,
social-card input guards, typography collector and insurance-clause explanation
validator are exposed without a new renderer or workflow. The clause validator
still requires an explicitly supplied `--schema`; this package does not invent
or bundle the private canonical insurance contract. No browser bridge, font,
model, audio or CMS binary is added. A mock DOM test is not browser QA.

`python -m build_human_voice_fixture --output-root EXISTING_EMPTY_DIRECTORY`
regenerates only the bundled fictional case JSON. It is a synthetic text/editing
contract fixture, not voice cloning, TTS, real author confirmation or publication.
Its published synthetic inputs are also included in the installed package.
An explicitly configured human-voice resource directory takes precedence.

The typography collector is included at
`studio_assets/scripts/typography_gate_collector.mjs` for explicit local use.
Its real browser bridges and canonical policy must be supplied and reviewed
separately. The media-QA registry is a receipt-level contract; passing it does
not establish that actual media or clinical/insurance statements are correct.

## Local review drafts and cue decisions (candidate 0.1.3)

`content-studio-review` projects the existing `human_voice_gate` contract into a
local, draft-only review bundle and captures cue decisions as an append-only
event history:

```sh
content-studio-review build --request fixtures/minimal-review/request.json \
  --allowed-root . --output review-work/page
content-studio-review apply --bundle review-work/page/bundle.json --draft draft.json \
  --allowed-root . --output review-work
content-studio-review decide --bundle review-work/page/bundle.json --event event.json \
  --allowed-root . --output review-work
content-studio-review render-cues --bundle review-work/page/bundle.json \
  --decisions review-work --track track.json --cache review-work/cache \
  --output review-work/render --video-source /explicit/video/project/root
```

All writes stay inside the review work root: set
`CONTENT_STUDIO_REVIEW_WORKSPACE` to a writable directory. In the installed
package the default would point at `studio_assets`, so it is refused; no review
artifact, revision, draft or render is ever written into site-packages. The
source checkout keeps its historical default. Sources remain constrained by the
explicit `--allowed-root`, and every artifact, body, media, timeline and
dependency input is bound by SHA-256 before use.

The packaged `admin/review.html`, `review.css`, `review.js` and `feedback.js`
assets are the existing local review page. A built page is
`built_pending_browser_validation`: no browser, DOM or human acceptance is
claimed, and the optional `feedback.js` backend is not part of this package.
The browser page only creates local draft state; the decision history and cue
rendering above remain the reviewed source of truth.

`render-cues` delegates rendering to the unchanged Video Owner
`audio_timeline.compose` API. There is no implicit checkout, installed-package
or "same version" fallback: an explicit `--video-source` root is required and its
`pyproject.toml` plus complete runtime package must match the reviewed
`config/video-timeline-runtime.v1.lock.json` byte-for-byte. That lock binds the
fixed public `video-creation-pipeline` 0.8.1 source; the Video code is not
vendored or copied into this package. `ffmpeg`/`ffprobe` are required only when
an actual synthetic render is requested. Real materials stay read-only, and no
publication or human approval is created by any command.

Targeted tests are stdlib `unittest` / pure Node scripts; see
`docs/candidate-review-tests.md`. The real public-Video byte binding test is an
explicit skip unless `CONTENT_STUDIO_PUBLIC_VIDEO_ROOT` points at the supplied
fixed public source.

## Review/cue adapters (0.1.4)

This release packages the existing draft review and immutable cue-decision
adapters with source/installed static resources. `content-studio-review --help`
describes the entry point. Set `CONTENT_STUDIO_REVIEW_WORKSPACE` to an explicit
local output root when using the installed package; `--allowed-root` still
bounds input reads. The required Video source is explicit and byte-locked to
the separate public MVP owner. No Video runtime or external binary is bundled.
See `REVIEW-CHAIN-PROVENANCE.json` and `REVIEW-CHAIN-ACCEPTANCE.md` for actual
synthetic/native checks and the pending browser/backend/human boundaries.

## Multi-owner synthesis and document-render lifecycle (candidate 2026-11-07)

`content-studio-synthesis` compiles an explicit hash-pinned editorial plan
through the unchanged QRP candidate pack, fact-card, content-item, cross-platform
consistency gate and HTML renderer. The QRP source root is explicit
(`--qrp-root`/`CONTENT_STUDIO_QRP_ROOT`), the Main gate loads only through the
registered `content-creation-system` record (`--tool-registry` or the existing
environment), and the common workspace root must be explicit
(`--workspace-root`/`CONTENT_STUDIO_SYNTHESIS_WORKSPACE`). A missing, mixed or
drifted owner blocks; it is never mocked. Text-only and HTML are both supported.
The review packet stays `pending_human_review`, the fact card stays `draft`, and
no publication authority is created.

`content-studio-artifacts` exposes only the Content Studio admission and
classification layer over the unchanged Artifact Lifecycle Core. The Core root
is explicit (`--core-root`/`ARTIFACT_LIFECYCLE_CORE_ROOT`) and hash-pinned to the
public Core API and profile. Test copies require an explicit operator work root
(`--work-root`/`CONTENT_STUDIO_ARTIFACT_WORK_ROOT`); no candidate `outputs`
directory is admitted implicitly. Plans remain immutable, non-authorizing and
plan-only: there is no production quarantine or purge command, and a valid plan
is not permission to execute it. See `docs/candidate-synthesis-lifecycle.md`
and `docs/candidate-synthesis-lifecycle-tests.md`.

## Editorial synthesis, artifact plans and design directions (0.1.5)

`content-studio-synthesis --help` compiles a hash-bound editorial plan and QRP
pack into draft text, fact cards and optional HTML. Supply explicit public QRP
and registered Main roots; installed use requires an explicit common workspace.
`content-studio-artifacts --help` exposes synthetic-root scan/explain/plan/verify
through the separate hash-pinned Artifact Core. A valid plan never authorizes
cleanup; there is no production quarantine/purge command.
`design_direction_validation` checks explicit direction/profile/medium/route
combinations using packaged first-party contracts; it does not classify content
or judge visual quality. No new rendering, research or routing engine is added.
See SYNTHESIS-PROVENANCE.json and SYNTHESIS-ACCEPTANCE.md for scope and evidence.

## Synthetic feedback and bounded preview (0.1.6)

Use `content-studio-feedback --help` or `content-studio-preview --help`; neither
starts a service. Install the optional `feedback` dependencies for native metric
intake/live resource monitoring. The Main Owner is separate, explicit and loaded
through its existing registry contract; no private sibling is guessed.

For feedback preparation supply `--workspace-root` and optionally `--tool-registry`,
and set `CONTENT_STUDIO_REVIEW_WORKSPACE` to the explicit permitted review output
root. `prepare` accepts only synthetic candidate bundles and named synthetic CSV
templates. It writes immutable candidate review records, never publication/CRM/
outcome ledgers. Unknown effort remains unknown; account-day data is not assigned
to a content item.

Starting `serve-synthetic` is an explicit finite loopback service action. The
standalone preview likewise requires `--root` pointing to the generated synthetic
site, never a whole checkout. Do not treat the supplied handler tests as a live
service/browser or production-account acceptance. See FEEDBACK-PROVENANCE.json
and FEEDBACK-ACCEPTANCE.md for scope and unverified parts.

## Local CMS and diagram contracts

The optional CMS command and explicit-runtime AntV syntax/budget adapters are
documented in [offline contracts](docs/OFFLINE_CONTRACTS.md). These are structural
checks; they do not start a CMS/browser or grant publication approval.

## Optional handdraw style planning

`content-studio-handdraw --help` exposes the existing style-brief/catalog/prompt/
local-gallery interface. Supply a trusted pinned upstream root explicitly;
there is no bundled upstream asset, automatic download, provider call or image
generation. [Adapter guide](docs/HANDDRAW_ADAPTERS.md). Upstream credit:
[yang0 / handraw-style](https://github.com/yang0/handraw-style), under its actual
attribution license; the older index's rights remain unverified.

## Generic shared visual contract checks

The existing shared-lock and global conformance APIs now use installed resources
and explicit roots. `content-studio-visual-lock --help` describes the read-only
check. [Generic contract guide](docs/GLOBAL_VISUAL_CONTRACTS.md). The9 generic
first-party contracts and empty synthetic authority sample contain no private
brand registry/tokens/assets. A structural receipt or recorded opt-in metadata
does not execute a renderer or establish human/source/privacy/publishing consent.

## Optional theme source assets

The public source tree also includes three first-party CSS source records under
`themes/`: `cover-photo-overlay.css`, `section-photo-overlay.css` and
`insurance-observational-advisor.css`. They document portrait cover and section
overlay styling at 1080 by 1350 pixels plus the associated `--ioa-*` token
projection. These are source records only, not selectable by the article HTML theme loader.
`content-studio-visual render-html` does not load them; the top-level `themes/`
tree is not installed by the wheel; and no external consumer or renderer setup
is supplied or verified. The overlay files retain an `@import "default"`
reference whose base stylesheet is not included, and the token source and
generator configuration are not included. See
[the theme asset notes](docs/THEME-ASSETS.md) for scope and limits.

### Chinese Typography Browser QA

The repository includes `scripts/chinese_typography_browser_qa.mjs` for inspecting Chinese typography heuristics in local HTML and SVG files using Playwright. It evaluates line punctuation, word splitting, CJK orphans, stranded headings, and font families (`GVL-TYPE-001..006`) within a 1280x1600 viewport.

This is a source-only checkout utility under Apache-2.0; external Playwright packages and browsers are operator-supplied and unverified. See [docs/chinese-typography-browser-qa.md](docs/chinese-typography-browser-qa.md) and [examples/chinese-typography/synthetic-article.html](examples/chinese-typography/synthetic-article.html) for CLI parameters, heuristic limitations, and synthetic usage.

### Static Browser QA Source Helpers

The repository includes optional source-only Node.js diagnostics in `scripts/` (`article_browser_qa.mjs` and `social_card_playwright_bridge.mjs`) sharing `browser_qa_runtime.mjs` and `typography_gate_collector.mjs`. These inspect static HTML/SVG desktop/mobile layouts and social cards using operator-supplied Chromium, driver packages, and hash-verified typography policies. Browsers, runtime dependencies, and fonts are not bundled. Dynamic application scripts and `--no-sandbox` flags are not supported. Full configuration details, placeholder commands, exit codes, and verification limits are documented in [docs/static-browser-qa-source.md](docs/static-browser-qa-source.md).

### Synthetic Editorial Evidence Tests

Optional source-only synthetic unit tests in `tests/test_human_voice_editorial_evidence.py` validate schema and hash-bound contracts for `human_voice_gate`. Running via direct Python invocation, the 5 test methods verify idempotent repairs, unchanged passes, and fail-closed rejections without modifying production dependencies. Real author approval, audio review, and prose naturalness evaluation are excluded. See [docs/editorial-evidence-tests.md](docs/editorial-evidence-tests.md).

### Synthesis Generalization Tests

Optional source-only unit tests in `tests/test_original_synthesis_generalization.py` validate 10 topic-isolation and plan-compilation rules adapted to the public Question-Research-PoC (QRP) interface. Requiring an explicit `$env:CONTENT_STUDIO_QRP_ROOT` and existing dependencies, tests run in isolated scratch workspaces without network, browser, or LLM execution. Compiled outputs remain synthetic candidates. See [docs/synthesis-generalization-tests.md](docs/synthesis-generalization-tests.md).

### Interview Review Category Coverage Tests

Optional source-only unit tests in `tests/test_interview_review_category_coverage.py` validate schema compliance for four required review categories in `schemas/case-interview-guide-review.v1.schema.json`. Running in-memory with existing dependencies, the 7 test methods enforce category coverage and fail-closed rejections without assessing question quality or granting publication authority. See [docs/interview-review-category-tests.md](docs/interview-review-category-tests.md).

### Article Visual Validation Tests

Optional source-only unit tests in `tests/test_article_visual_validation.py` validate 14 visual planning and schema constraints using existing public schemas and registry configurations. Running via direct Python invocation, the suite checks declared rights, attribution, and role bounds on synthetic metadata without rendering images or clearing licenses. See [docs/article-visual-validation-tests.md](docs/article-visual-validation-tests.md).

### AI Image Opt-In Record Tests

Optional stdlib-only unit tests in `tests/test_ai_image_generation_opt_in.py` validate 5 trigger-matching and opt-in record consistency rules for AI image routing. Tests use fictional metadata without invoking models, generating assets, or certifying authentic user intent. See [docs/ai-image-optin-record-tests.md](docs/ai-image-optin-record-tests.md).

### Repository-Local Test Workspace

The test helper in `tests/temp_workspace.py` checks repository-local scratch roots and creates per-run directories under `outputs/.test-runtime/temp` with strict single-component prefix validation. Regression tests in `tests/test_temp_workspace.py` verify multithreaded cleanup, residue isolation, and pre-filesystem rejection of invalid separators or control characters without relying on OS temp directories. See [docs/repository-local-test-workspace.md](docs/repository-local-test-workspace.md).


### Original Handdraw Regression Test Sources

The explicit integration entries `tests/handdraw_style_brief_integration.py` (20 methods) and `tests/handdraw_style_library_integration.py` (16 methods), plus two fictional JSON fixtures, complement the existing self-contained contract suites. They require operator-supplied upstream trees and are outside standard default discovery patterns; no cases are marked skipped or passed here. The library gallery tests use temporary output outside the pinned and installed resource trees; production guards and all assertions remain intact. External pinned checkouts are operator-supplied and not redistributed. Full-suite execution and asset rights remain unverified. See [the source-only guide](docs/handdraw-original-regression-tests.md).


### HTML semantic visual binding checks

- [Semantic Visual Binding Checks](docs/semantic-visual-binding-checks.md): Standalone structural verification of HTML `data-semantic-id` container bindings, copy anchors, and image asset basename co-location without browser rendering or image existence guarantees.


### Social-card typography regression source

[Source and explicit runtime/canonical-binding guide](docs/social-card-typography-regression-source.md): the existing eight test intentions and seven first-party synthetic fixtures, with configured browser paths and faithful early hash refusal. Six core method bodies and fixture bytes are preserved. Source-only: 17 controlled helper checks and one real Node hash-preflight negative control passed; zero browser methods or real canonical policies were executed. The operator-supplied canonical binding remains required for that case; the public registry is unchanged.


### Deterministic PPT chart projection source

The [PPT data projection adapter](docs/ppt-data-projection-source.md) exposes
standard-library chart-to-native-payload mapping and slide-SVG text construction.
Materialization still requires the separately supplied, provenance-held parent
renderer and fails closed when it is absent. No renderer source, PPT runtime,
font files or real chart data is bundled; synthetic checks do not prove actual
PPT rendering or source-fact verification.


### Optional pinned CMS entry source

[CMS entry HTML and boundaries](docs/cms-entry-source.md) documents an optional
network-capable loader for the pinned Sveltia CMS script. Opening the HTML
requests its CDN script; no CMS bundle is distributed and schema-only offline
validation does not prove CMS UI, authentication or publishing functionality.


## Legacy medical artifact regression source

See [the four original artifact assertions, explicit input bindings and execution limits](docs/special-medical-artifact-regressions-source.md). Source and extracted bindings are checked; real medical content, renderer execution and third-party assets are not included or verified.
