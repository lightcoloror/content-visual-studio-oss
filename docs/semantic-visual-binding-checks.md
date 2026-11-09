# Semantic Visual Binding Checks

## Purpose
`scripts/semantic_visual_validation.py` provides standalone structural validation for HTML-based infographics. It verifies contracts between content item metadata (`visual.semantic_visual_map`) and static HTML output files, checking declared explanatory visual references and copy anchors inside parser-collected semantic containers (`data-semantic-id`).

## Module Import
The public module is located at `scripts/semantic_visual_validation.py`. Consumers can import it via `importlib` or by adding the `scripts/` directory to `sys.path` in standalone scripts:

```python
# Option 1: Dynamic import via importlib (recommended for isolated test suites)
import importlib.util
from pathlib import Path

module_path = Path("scripts/semantic_visual_validation.py").resolve()
spec = importlib.util.spec_from_file_location("semantic_visual_validation", module_path)
semantic_visuals = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(semantic_visuals)

# Option 2: Module search path addition (manual shell / script usage)
import sys
from pathlib import Path
sys.path.insert(0, str(Path("scripts").resolve()))
import semantic_visual_validation as semantic_visuals
```

## API Specification
### `validate_semantic_visual_map(item: dict[str, Any], item_path: Path) -> list[tuple[str, str]]`
Inspects the supplied item dictionary against static HTML files selected by its output references. No browser rendering is performed.

- **Parameters:**
  - `item`: Python dictionary containing the parsed content item JSON.
  - `item_path`: `pathlib.Path` pointing to the item file location. Relative `output_ref` paths in `semantic_visual_map` resolve relative to `item_path.parent`.
- **Return Value:**
  - List of `(location, message)` tuples detailing contract violations. An empty list `[]` means no errors from these implemented structural checks; it is not full content/schema or release approval.

## Contract Rules & Trigger Conditions
1. **Required vs Optional Maps:**
   - Semantic visual maps are required if and only if both conditions match:
     - `visual.route` is in `{"data_visualization", "explanatory_illustration"}`
     - `visual.render_recipe.renderer` is in `{"html-playwright"}`
   - If required and `visual.semantic_visual_map` is missing or falsy, validation reports:
     `("visual.semantic_visual_map", "HTML infographic routes require semantic visual bindings; decorative assets alone are insufficient")`.
   - For all other route and renderer combinations, `semantic_visual_map` is optional. If absent, validation returns `[]`. If present, the same implemented binding checks are applied; this is not comprehensive schema validation.
2. **Cognitive Anchor Coverage:**
   - Every variant in `semantic_visual_map` must include at least one `explanatory` visual binding.
   - All cognitive anchors defined in `visual.cognitive_anchors` (indices `0` through `len(cognitive_anchors) - 1`) must be covered by at least one `explanatory` binding in each variant.
   - `explanatory` visual bindings must not use `placement: "background"`.
3. **Copy-Anchor Text Matching:**
   - Extracted container text is collapsed with whitespace normalization (`" ".join(data.split())`).
   - A nonempty normalized `copy_anchor` on a non-decorative binding must be a substring of the container's collected text. This is parser text, not a visible-text or meaning check.
4. **Asset Basename Matching:**
   - The expected `visual_ref` uses `Path(expected_ref).name.casefold()`. Actual HTML `img` src values have the query suffix stripped before basename comparison. This does not compare full paths, URLs or content hashes.
   - The validator does NOT inspect image files, verify filesystem presence, or render image bytes.

## Execution & Verification
Run the standalone unittest suite from the repository root:
```bash
python tests/test_semantic_visual_map.py
```
> Owner acceptance used an existing CPython 3.13.5 venv: all four original test scenarios passed, no failures or skips, and ten boundary controls passed. A private bad copy with the required-map guard disabled ran the same four tests and failed exactly the missing-map case as expected (three pass, one expected fail). Product source stayed unchanged. The first receipt parser incorrectly expected the status word FAILURES instead of unittest's FAILED; actual logs already showed the expected result and were reconciled without rerunning the unittest suites.

## Limitations & Operational Boundaries
- **No Confinement Sandbox:** `_path_from_ref` resolves relative paths from `item_path.parent` or accepts arbitrary absolute paths. It does not sanitize path traversal or enforce chroot boundaries against malicious input paths.
- **Structural Containment vs Rendered Layout:** The validator verifies DOM containment (`data-semantic-id`) via Python's standard library `HTMLParser`. It does NOT verify rendered layout coordinates, CSS visibility (`display: none`, opacity), viewport clipping, or visual co-location in a browser engine.
- **No Asset Existence or Content Verification:** Image existence on disk, pixel dimensions, file formats, and semantic visual fidelity are not verified by this check. Missing referenced images do not fail this validator if the matching `src` attribute basename is present.
- **Duplicate ID Behavior:** If multiple elements share identical `data-semantic-id` attributes, `SemanticContainerParser` aggregates text and images across all matching elements. It does not enforce uniqueness or compute cryptographic content hashes.
- **Source-checkout Scope:** The module imports only the Python standard library and does not itself launch browsers, models or HTTP clients. It opens the paths supplied by the caller; do not interpret this as network/filesystem confinement. This batch used only the synthetic local files. No installed-package, browser, provider or real-content acceptance was performed.
- **Provenance & Licensing:** The validator module `scripts/semantic_visual_validation.py` is copied unchanged from an existing local working snapshot. The bundled test fixtures use synthetic tutorial data (toy blocks) replacing private historical items. Root repository Apache-2.0 applies.

## Bundled synthetic fixture and provenance

The three files in `tests/fixtures/semantic-visual-map/` are minimal parser inputs for a fictional toy-block tutorial, not complete schema-certified content items. The two HTML files deliberately refer to absent SVG files: matching image src names are enough for this checker, and no image assets are distributed or rendered. The original four test names are retained for continuity; they now refer to this synthetic fixture, not a current personal or medical manuscript.

The existing validator is preserved unchanged, including its original attribution state; its local working-snapshot SHA-256 is `7bdb3781120558c5f62f6edf866d315c4866ecf2f54fc893dece109aaa52ddae`. No historical Git commit is claimed for that snapshot. The existing tests were adapted only for public module/fixture paths and one negative asset reference. No private item, output image, clinical record or historical runtime evidence was opened or bundled.

This first-party source increment follows the existing repository Apache-2.0 license. Its only imports are Python standard-library interfaces; no upstream font, image, software bundle or binary is redistributed. This source review is not a blanket rights determination for caller-provided inputs.

The check does not assess factual or clinical quality, accessibility, image meaning, full content schema conformance or publication permission. Relative and absolute HTML paths are accepted without containment restrictions; filesystem/parse errors may propagate. Use reviewed input references. Duplicate HTML marker aggregation and same-basename matches can pass even when real rendered co-location or image identity is absent. Keep visual inspection and factual review in the existing content workflow.
