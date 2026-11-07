# Four-module review chain — release acceptance

2026-11-07. Codex independent review; exact runtime model not independently verified.

Four related first-party review/cue adapters and their necessary static assets
are included. Existing human approval, immutable decision/replay, source/hash,
path, checked-source loader and explicit Video owner boundaries are retained.
The previous public baseline is retained; existing gate/studio_paths behavior
and dependencies are unchanged. The package adds four modules and one CLI.

Independent host regression: 66 Python checks pass, no skip. Peer execution:
20 Node pure-logic checks pass, CLI draft build/apply works. The original failed
test, Windows temporary-directory build failures and toolchain visibility block
were preserved privately. An exact pre-existing interpreter/FFmpeg toolchain
resolved the native block without installation or global setting changes.

A real but entirely synthetic native sample exercised cue edit -> immutable
decision -> derived binding -> unchanged public MVP audio_timeline -> MP4.
Host FFprobe verified 2 seconds, 320x180, 20 frames. All three native execution
receipt hashes, bound artifacts and admitted resource limits were verified.
The existing composer burns ASS; the edited cue and ASS sidecar were verified.
No SRT artifact is emitted or claimed, and no new subtitle renderer was added.

The peer wheel extraction/import is a package projection test, not pip install.
The release host separately validates a fresh offline wheel installation and
installed entry/resource behavior before publication.

No real voice/footage, browser/DOM, feedback backend, author approval, audience
response, platform behavior or content publication was tested. Generated pages
remain built_pending_browser_validation and revisions remain draft-only.
No private task data or synthetic rendered media is distributed with this source.

Release-host fresh installation: existing reviewed wheels/cache only, independent
Python 3.13.5 venv, system packages disabled, dependency check exits 0. Seventeen
isolated installed checks pass, including all 29 module origins, 12 CLI helps,
explicit installed output root, real synthetic draft/page generation, stale
draft/output escape rejection and exact public MVP byte-lock validation.
All 84 distributed package files match source, wheel and site-packages bytes.
No source-tree PYTHONPATH or browser/service/model call was used for these
installed checks; they do not establish the excluded human/platform outcomes.
