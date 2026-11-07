# Design-direction admission library

The existing first-party validator checks explicit direction, version, profile
mapping, medium, visual-route/photo-mode exclusions, theme, renderer option and
layout-intent compatibility. It uses the existing studio_paths resource locator
in source and installed layouts. Missing/incompatible contracts fail closed;
explicit contract argument takes precedence over the existing environment override.

Fifteen focused source tests pass. They are compatibility/portion-validation
tests, not a complete content-item, semantic style-fit or rendered-output review.
The contract's content_jobs metadata is not a semantic classifier in this module.
No automatic renderer/image-generation/brand selection was added, and the
existing selected Profile tokens are not replaced with a universal palette.

Two historical manuscript-reference IDs in the composition contract were
replaced by generic first-party reference IDs. No manuscript or reference image
is distributed. Route/profile/version/policy values and historical attribution
remain intact. The private shared design repository and brand assets are not
bundled; global conformance/lock consumers are a separate unfinished review.

Installed packaging and full workflow discovery are verified separately by
the release host when this library is merged into a reviewed source edition.
