# Targeted tests for the review-chain candidate

These tests are synthetic, offline and stdlib-only (plus pure Node logic). They
are shipped as source and are meant to be run from an isolated copy of the
candidate, never against the candidate tree being reviewed. No test writes to
the review candidate source; runtime scratch stays under the copy's
`outputs/.test-runtime/` (or the configured `CONTENT_STUDIO_TEST_TEMP_ROOT`).

Use the acceptance Python/Node recorded by the host contract. Do not install or
modify an environment. Set `PYTHONDONTWRITEBYTECODE=1` and a task-local
`TEMP`/`TMP`/`TMPDIR` before running.

All tests create their synthetic scratch under the copy's
`outputs/.test-runtime/` via plain directory creation (`tests/temp_workspace.py`).
The system `tempfile.mkdtemp` helper is deliberately avoided by the dependency
test: on some sandboxed Windows hosts, directories created with mode `0o700`
(mkdtemp style) cannot be accessed afterwards, which blocked the build/test step
with `WinError 5`. This is a host-environment limitation, not a permission
bypass: the plain scratch root stays inside the already-writable test copy.

## Commands

Run from the isolated copy root, one command at a time, with `scripts/` first on
the import path (each test inserts it itself):

```sh
python tests/test_human_voice_review.py
python tests/test_cue_review.py
python tests/test_video_timeline_dependency.py
python tests/test_public_video_binding.py

node tests/test_human_voice_review_js.cjs review-work/page/bundle.json

python scripts/human_voice_review.py build \
  --request fixtures/minimal-cue-review/request.json \
  --allowed-root . --output review-work/cue-page
node tests/test_cue_review_js.cjs review-work/cue-page/bundle.json review-work/cue-session.json
python scripts/human_voice_review.py apply-session \
  --bundle review-work/cue-page/bundle.json \
  --session review-work/cue-session.json \
  --allowed-root . --output review-work/cue-work
```

The first `node` line needs the bundle produced by:

```sh
python scripts/human_voice_review.py build \
  --request fixtures/minimal-review/request.json \
  --allowed-root . --output review-work/page
```

Real public-Video byte binding (independent copy of the supplied fixed public
source; no network, no install):

```sh
CONTENT_STUDIO_PUBLIC_VIDEO_ROOT=<fixed public-video root> \
  python tests/test_public_video_binding.py
```

Optional checked-source import layer (only if `ffmpeg`/`ffprobe` already exist on
PATH; still no composition or render):

```sh
CONTENT_STUDIO_PUBLIC_VIDEO_ROOT=<fixed public-video root> \
CONTENT_STUDIO_PUBLIC_VIDEO_RUNTIME=1 python tests/test_public_video_binding.py
```

## Coverage map

| Requirement | Tests |
| --- | --- |
| Immutable replay / append-only history | `test_cue_review.py`: history replay, event bytes never rewritten, undo/redo, tampered history/revision rejection |
| Duplicate events / retries | `test_cue_review.py`: retry old event, duplicate commit, partial-before-commit resume; JS: duplicate id |
| Stale hashes | `test_human_voice_review.py`: stale bundle/body/source/media; `test_cue_review.py`: duplicate-event drift; dependency: lock/implementation drift |
| Path escape | `test_human_voice_review.py`: `bound_path`, unsafe media name, media path escape; dependency: symlink/junction escape |
| Real material is read-only | `test_human_voice_review.py` and `test_cue_review.py`: candidate and track `synthetic_only=false` reject keep/modify/reject; JS equivalents |
| Dependency drift | `test_video_timeline_dependency.py`: version, file set, bytes, pyc, preload, origin, in-flight drift, missing executable |
| Public MVP real binding plan | `test_public_video_binding.py`: no vendoring, relative lock, real file set/bytes, optional checked-source import |
| Draft-only / no approval | `test_human_voice_review.py`: consumer index flags; page status; README/docs state the boundary |

## Explicitly unverified

* Browser/DOM behavior, Playwright/Puppeteer bridges and `feedback.js` backend.
* Any real render, FFmpeg execution, decoded frames, duration or media QA.
* Installed-wheel import/acceptance and real pip installation.
* Human author approval, publication permission, real materials, TTS/ASR or
  model/provider calls.
* A skipped real-binding test is not a pass; the verification receipt must
  record skips and the exact command/environment.
