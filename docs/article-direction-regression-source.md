# Article-direction regression suites — source reference

Status: **source candidate; limited Python checks completed, full suites not run.** This overlay publishes a portable copy of two
existing first-party regression suites for the `editorial-field-guide` and
`reflective-personal-essay` article directions. It is an integration/source
reference, not a product reimplementation. It does not supply the external
source catalog, full registries, editor configuration or complete fixtures the
suites read, and it does not claim that all 18 methods can run or have passed.

License: Apache-2.0 first-party test code. No fonts, third-party article text,
imagery or other external reference material is bundled.

## Suites

`tests/test_editorial_field_guide.py` — 10 methods, carried by the owner with
exact bytes unchanged:

1. `test_reference_provenance_and_method_boundary_are_portable`
2. `test_direction_is_explicit_and_inherits_visual_profile`
3. `test_theme_without_direction_fails_closed`
4. `test_data_and_photo_led_routes_are_not_eligible`
5. `test_unmapped_visual_profile_fails_closed`
6. `test_social_card_requires_explicit_renderer_option_and_allowed_intent`
7. `test_renderer_builds_structured_responsive_article_without_remote_fonts`
8. `test_unknown_article_theme_is_rejected`
9. `test_editor_and_renderer_expose_versioned_direction`
10. `test_missing_or_incompatible_contract_fails_closed`

`tests/test_reflective_personal_essay.py` — 8 existing methods, adapted with one
portable expectation change (see below):

1. `test_reference_provenance_and_reuse_boundary_are_portable`
2. `test_direction_is_explicit_and_route_bounded`
3. `test_wrong_social_card_theme_or_intent_fails_closed`
4. `test_article_renderer_builds_paced_sections_with_local_fonts`
5. `test_explicit_section_tones_are_validated`
6. `test_social_card_source_is_local_script_free_and_direction_bound`
7. `test_registry_editor_and_bridge_expose_the_direction`
8. `test_external_runtime_configuration_is_explicit_and_fail_closed`

All original method names, assertions, synthetic item dictionaries/title text,
whole fixture reads and negative/failing branches are retained. The single
source change is in method 7: the host-specific absolute typography-policy path
literal is replaced by an explicit, hash-bound, environment-configured
expectation. No production module, schema, registry, contract, policy or fixture
is edited.

## Imports and dependencies

Both suites define `ROOT = Path(__file__).resolve().parents[1]` and are meant to
sit at `<source-root>/tests/`, so `ROOT` resolves to the source root. They load
the renderer modules directly by path with `importlib.util.spec_from_file_location`:

- `scripts/article_visual_pipeline.py`
- `scripts/design_direction_validation.py`
- `scripts/social_card_runtime.py` (reflective suite only)

They also import `from temp_workspace import isolated_test_directory`, which
requires the adjacent `tests/temp_workspace.py`. Runtime inputs include the
source repository's `config/design-directions.v1.json`,
`config/renderer-registry.v1.json`, `admin/config.yml`, the two theme CSS files,
`config/design-direction-sources.v1.json` for both suites, plus (reflective only)
`fixtures/reflective-personal-essay/article.md` and
`fixtures/reflective-personal-essay/social-deck.html`.

Those registry, editor and fixture files are requirements for the suites; they
are not supplied or verified by this overlay. The existing public base already contains
`fixtures/typography-gate/synthetic-policy.json`, explicitly synthetic/test-only.
A limited checksum-binding probe may read that existing file; it does not
replace the suite's actual external policy or prove a formal typography gate.

## Portable env/path/hash binding

The only adaptation is the top-level helper `expected_typography_policy(gate)`
in the reflective suite. It:

1. requires `gate["policy_sha256"]` to be an actual string matching
   `^[0-9a-f]{64}$` **before** resolving anything, raising the existing
   `SocialCardRuntimeError` for a missing, empty, non-string or malformed hash;
2. resolves the test-only environment variable
   `CONTENT_STUDIO_TEST_REFLECTIVE_TYPOGRAPHY_POLICY` through the existing public
   `social_runtime.resolve_external_file_from_env`, passing the exact
   `policy_sha256`, so an unset variable, missing file or checksum drift also
   fails closed with `SocialCardRuntimeError`.

The reflective suite then asserts that the resolved file path equals the
registry's `policy_path` normalized to an absolute path under `ROOT` when it is
relative. The original `profile_id` (`social_card_1080x1440`) and lowercase
64-hex `policy_sha256` assertions are preserved. There is no skip, fallback,
dummy hash or trust-any-policy branch, and no extra helper framework, validator
or registry is introduced.

An operator must point the environment variable at the actual external
typography-policy file whose digest matches the registry value. Matching a hash
format or even a digest is an identity/checksum binding only; it is not proof of
historical authorship, provenance or rights clearance.

## Not supplied, not fabricated, not run

This is an integration/source reference that requires the real external source
catalog and matching public/operator-owned contracts and fixtures. Those inputs
are not supplied here, so they are not fabricated or declared verified, and the
source-catalog/reference-ID and hash assertions are kept exactly as they are.
No sample catalog, substitute article, substitute social deck or fabricated SHA
is introduced to make a method pass.

Presence of public renderer/validation/social-runtime/theme sources does not mean
every private or operator registry, admin configuration or full fixture matches
this historical suite; it also does not prove the runtime is absent.

No browser, Playwright, font, model, HTTP, FFmpeg, Office, install, build or full
unittest execution was performed, and no new service was created. In particular,
`test_external_runtime_configuration_is_explicit_and_fail_closed` remains
included and **NOTRUN**: its filesystem/temp-directory behavior is not skipped,
weakened or converted to a green check. A separate bounded, read-only/in-memory probe was subsequently run as
recorded below. It does not establish the original 18-test result, integration,
fixture compatibility, provenance, license correctness or publication readiness.

## Recorded limited verification

Python 3.13.5 imported the real assembled test, renderer and resolver modules;
paths and source hashes were verified. One command ran eight read-only binding
checks: missing digest, non-string digest, invalid hex, uppercase digest, unset
environment variable, missing file, an existing file with the correct digest,
and checksum drift. The existing public synthetic policy was used only for
file identity/checksum behavior. It was not substituted into a formal renderer
registry or promoted into the suite's actual external policy.

Three unchanged original methods also passed: editorial responsive HTML-string
sections, unknown-theme rejection, and reflective explicit-section-tone checks.
There were no failures or skips in these selected checks. Fifteen original
methods remain unrun, including full registry/catalog/editor/reflective-fixture
integration and filesystem/temp-directory behavior. All eighteen methods remain
in the source; no missing fixture was invented and no assertion was removed to
obtain this limited result. No browser rendering, font loading, media processing,
network/provider/service operation or publication was tested.
