> Historical core 0.1.0 acceptance, retained unchanged below. See CAPTURE_ACCEPTANCE.md for the 0.1.1 increment.

# Public core acceptance

2026-11-07, Codex (exact runtime model not independently verified).

This is a reviewed core edition, not a claim that every module in the private
ContentStudio workbench has completed release review. Remaining source and
integration review is tracked separately by the maintainer.

- Windows, isolated CPython 3.13.5; no system-site packages.
- Core suite: 116 passed, 54 subtests passed, 7 skipped, 7 upstream mock warnings.
- Five skipped tests need the MVP owner entry; two need the self-media Story Card
  owner entry. These integrations remain unverified and their assertions remain.
- Gateway tests use only loopback mocks. External connections are disabled and
  proxy environment variables are removed in test scope. No real provider runs.
- Installed wheel: 12 commands checked from a new working directory. Two expected
  failures verify candidate opt-in and the missing author-source boundary.
- Fresh installed QRP -> hash-bound candidate -> Markdown -> HTML passed. The fact
  gate stays blocked, verified facts stay empty and human review stays required.
- A separate verified synthetic research fixture produced four hashed draft
  artifacts. It does not represent verified real-world evidence.
- Installed initial review, synthetic human-voice replacement and case candidate
  contracts passed. Fictional read-aloud/author receipts are not real approvals.
- No renderer, browser, video, CMS, Office, model or platform publication acceptance
  is implied. HTML structure and artifact hashes do not prove visual quality.

The installer used exact locally built wheels matching the reviewed public QRP
source, plus public PyPI dependencies. Resolving the pinned Git URL through pip was
not separately exercised on this restricted Windows host. Build used the existing
setuptools wheel exit and emitted its setup.py-install deprecation warning.

Source transformations retain all semantic gate functions except the existing
binding helper's resource locations. All first-party source and fixture origins,
working-tree distinctions and final hashes are recorded in PROVENANCE.json.
The normal release process separately freezes and scans the complete file tree.
