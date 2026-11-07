# Formatter increment acceptance

Version 0.1.2 retains the public 0.1.1 core and adds the existing first-party
WeChat formatting adapter and its local review wrapper. Python resource lookup
supports source and installed use; the original gate, hash, origin, commit,
privacy, manual-publication and blocked-state checks remain in force.

- Source suite: 144 passed, 6 skipped, 62 subtests passed; exit 0.
- Skips: five optional full-MVP integrations and one optional Gateway import.
- Installed package: 13 checks passed, including real local synthetic rendering,
  installed origins/resources, pending review retention, hash/privacy/source-pin
  rejection, existing-output preservation, absent publishing actions and pip check.
- All 20 flat runtime modules and the packaged JS helper match wheel bytes.
- Main framework composition with this candidate: 811 passed, 44 skipped,
  284 subtests passed; exit 0. Unavailable full-MVP and private-runtime checks
  remain unverified; this is not a full-project or production acceptance claim.

The existing separately supplied formatter was tested at fixed commit
561e3e736ef8d161247c70c30e694814e898ef59 with Node 22.22.2 and Python 3.13.5.
No external renderer source, presets, assets, node_modules or binaries are bundled.
Its package metadata declares ISC and has no standalone LICENSE; this edition
does not grant rights over that runtime or its transitive dependencies.

All new test material is fictional. Pending fact, compliance, rights and author
review states remain pending. No platform, browser, actual paste, device,
provider/model, real study, customer material, author approval or publishing
execution is established by these tests. Other workbench scripts remain under
separate review. See FORMATTER-PROVENANCE.json and THIRD_PARTY_NOTICES.md.

The first installed-test harness invocation used the wrong Python main signature
and failed before business execution. Correcting the harness produced the stated
results; the original failure is retained privately. No runtime assertion was
weakened to obtain a pass.
