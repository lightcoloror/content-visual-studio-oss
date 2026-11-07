# Public Video MVP binding plan

The Content review chain renders only through the already-public Video Owner
implementation. This document records exactly what the candidate binds, what it
deliberately does not copy, and what remains unverified.

## Fixed public source

| Field | Value |
| --- | --- |
| Distribution | `video-creation-pipeline` |
| Version | `0.8.1` |
| Declared fixed public commit | `9f55b12864df642f08fcbd96df15acb0f97652d5` |
| Interface | `audio_timeline.compose/v1` |
| Lock | `config/video-timeline-runtime.v1.lock.json` (and packaged copy) |
| Bound entries | `pyproject.toml` + complete `src/video_creation_pipeline` file set, 182 files |

The lock stores SHA-256 for every bound file and records the declared source
repository/commit. The per-file bytes are authoritative: this candidate does not
claim that an unverified git HEAD or historical tree contains them, and it does
not label a "same version" copy as the same source.

The candidate does **not** vendor the Video package. There is no
`src/video_creation_pipeline`, no copied `audio_timeline.py`, and no installed
fallback. `tests/test_public_video_binding.py` enforces the no-vendoring rule
without any environment setup.

## How the binding is used

1. The operator supplies an explicit `--video-source <root>` (or the equivalent
   API argument). `None` fails with `video_dependency_required`; there is no
   automatic checkout or installed-package lookup.
2. `video_timeline_dependency` reads the reviewed lock (source tree, installed
   `studio_assets`, or `CONTENT_STUDIO_VIDEO_TIMELINE_LOCK` override).
3. It verifies `pyproject.toml` name/version, the exact file set, and every
   per-file SHA-256 before importing anything. Missing/extra files, version
   mismatch, changed bytes, symlink/junction escapes, pre-imported Video modules
   and unverified pyc provenance fail closed.
4. Imports execute the checked source bytes with a pinned loader
   (`dont_inherit=True`); import origins are re-verified. After composition the
   runtime is verified again; in-flight drift quarantines the cache and keeps
   failed-attempt evidence.
5. `cue_timeline_adapter.render_revision` passes only hash-checked, snapshotted
   inputs to `audio_timeline.compose`. No compose call is made by the tests or by
   this stage; a real synthetic render belongs to the separately authorized
   verification stage and remains bounded by the host's small-media limits.

## Real binding checks

`tests/test_public_video_binding.py` provides three layers:

* Always: candidate contains no vendored Video package; the shipped lock is a
  relative, private-path-free byte binding with the expected identity and no
  unverified `git_head` claim.
* With `CONTENT_STUDIO_PUBLIC_VIDEO_ROOT=<fixed public source root>`: the full
  real file set and every byte are compared against the shipped lock, and the
  declared commit is checked.
* With `CONTENT_STUDIO_PUBLIC_VIDEO_RUNTIME=1` as well, and existing
  `ffmpeg`/`ffprobe` on PATH: the checked-source loader imports the real runtime
  and its evidence is compared with the lock. This is an import check only, not
  a render or installed-package acceptance.

Without those variables the corresponding checks are explicit skips. A skipped
binding check is not evidence that the real package was bound; the task receipt
must record the actual status and command.

## Unverified boundaries

* No real render, FFmpeg execution, decoded frame, duration or media-QA receipt
  is produced or claimed by the candidate source.
* No installed-wheel import of the real Video package is claimed; the host runs
  installation acceptance separately.
* Browser review-page behavior, Playwright/Puppeteer bridges, feedback backend,
  human approval, publication permission and real author material remain
  unverified by this plan.
