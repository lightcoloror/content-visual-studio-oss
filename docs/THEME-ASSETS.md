# Optional theme asset sources (not loaded at runtime)

This edition includes three first-party CSS source records under the top-level
`themes/` directory. They document the styling of portrait cover and section
overlays sized 1080 by 1350 pixels and the custom-property token projection for
the related visual profile. They are source assets only. They are not runtime
themes, not selectable themes, and not registered with the supplied article HTML theme loader.
No consumer integration for these three assets is supplied or verified here.

## Files

| Path | Role |
|---|---|
| `themes/cover-photo-overlay.css` | Portrait cover overlay source. Declares `/* @theme cover-photo-overlay */` and `/* @size content-portrait 1080px 1350px */`. |
| `themes/section-photo-overlay.css` | Portrait section overlay source. Declares `/* @theme section-photo-overlay */` and the same 1080px by 1350px size directive. |
| `themes/insurance-observational-advisor.css` | Generated `--ioa-*` custom-property token projection for the same visual profile, under `:root` and `[data-visual-theme="insurance-observational-advisor"]`. |

The two overlay files contain ordinary CSS rules for a slide-shaped `section`
element: dark background, light text, spacing, and a restrained accent. The token
file declares custom properties on `:root` and its attribute selector; it does
not by itself set layout properties such as width or display.

## Source and attribution

These are first-party CSS sources distributed under the project's Apache-2.0
license. No font, photograph, image, or other binary is distributed. Font
families appear only as ordinary `font-family` names with generic fallbacks; no
font file is included. The source reference is commit
`10ede0534b4282eea8ff13216a0585449cc956c2`.

`themes/insurance-observational-advisor.css` retains its generated header
verbatim. The header names Style Dictionary 5.5.1 and the source
`design-system/tokens/insurance-observational-advisor.tokens.json`, and says the
file should not be edited directly. The token source JSON and the generator
configuration are not included in this edition. The header is retained as
written; it is not independent proof that the same input and configuration would
reproduce these bytes.

## Runtime and consumer status

- `content-studio-visual render-html` does not load these files. Its `--theme`
  option accepts only `default`, `editorial-field-guide`, and
  `reflective-personal-essay`; any other name is rejected. These three sources
  are not among the accepted themes and do not add a new one.
- The top-level `themes/` directory is source-tree content only. The wheel is
  rooted at `scripts/`, so the top-level `themes/` copies are not installed. No
  package or loader change is proposed or made.
- The overlay files retain the string-form `@import "default";` directive
  exactly as written. String-form `@import` takes a stylesheet reference.
  Whether an external setup resolves that reference as a relative stylesheet
  named `default`, through some theme resolver, or in another way was not
  established here, and this edition supplies no `default` base stylesheet. No
  claim is made that only one kind of renderer can resolve it, or that it has no
  dependencies.
- How an external consumer would load these files, apply the directives, and
  provide the imported base is the operator's responsibility. No setup, adapter,
  or worked example is supplied or verified, and this edition does not require
  building a new renderer or completing full integration in order to publish
  the source.
- The token sheet uses standard CSS custom-property declarations on `:root` and
  the attribute selector above. This edition supplies no token pipeline, theme
  switcher, or runtime registration.

## Not verified

The presence of these source files does not verify or imply any of the
following:

- that any renderer, browser, or layout engine renders them as intended;
- that the `@import "default"` reference resolves in any particular environment;
- that a packaged or installed wheel contains, exposes, or selects these files;
- that fonts, photographs, images, or other media are available, licensed, or
  checked; no media is distributed;
- contrast, legibility, mobile or small-screen appearance, or compatibility with
  external tooling;
- runtime support, external-consumer support, publication approval, or rights
  clearance for third-party material.

These files are optional source records. They are not a supported runtime
feature, and the supplied article HTML theme selector does not offer them.
