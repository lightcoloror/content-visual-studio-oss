# Five-medium visual acceptance source

This optional source adapts the existing acceptance runner for article HTML, social-card HTML, infographic SVG, PPTX and web HTML. It operates on source copies, retaining existing schema validation, PPT text-fidelity/overflow evidence checks, typography failure handling, required media checks, P0 finding filtering, protected-content before/after hash comparison, and the combined candidate/manual/no-publication boundary.

## Explicit inputs

From a source checkout, an intentionally authorized operator can invoke:

    python scripts/run_global_visual_acceptance.py --input-map path/to/input-map.json

The input map must be an object. `sources` must contain five file paths: `article`, `social-card`, `infographic`, `pptx`, `web`. Other required paths are `ppt_receipt`, `protected_baseline_manifest`, `protected_root`, `data_visual_spec_schema`, `runtime_config`, `normalized_data_fixture`, `typography_script`, and `output_dir`. `personal_brand_root` is required when protected brand entries need it. `runner_identity` is optional caller-supplied metadata and defaults to `unknown`; it is not independently authenticated. Relative paths resolve from the invocation working directory. No private workspace or historical asset is auto-discovered.

The protection manifest retains the existing `content_items`, `acceptance_artifacts` and `personal_brand_authority` hash maps; the historical brand `qa-report.json` exclusion is retained. Supply genuine intended resources and evidence. This increment does not ship historical manuscripts, schemas/receipts invented to make a workflow pass, protected brand assets or real case files.

Preflight is read-only: required inputs must exist; an existing output must be a directory. Output cannot equal or contain an input file, including the input map, and cannot equal, contain or sit inside either protected root. Keep output and protected input roots separate. Resolved paths detect ordinary symlink-based overlap, but this is not an OS sandbox or a TOCTOU/concurrent replacement guarantee. Output creation occurs only after preflight succeeds. Later runtime failure may leave partial copies/receipts; no cleanup or transactional rollback is added.

The supplied runtime_config is forwarded both to Playwright-package resolution and conformance receipt construction, and is also used in the combined summary. Existing public shared/schema defaults remain unchanged. Full compatibility of a caller's runtime, schemas, receipts and assets remains unverified.

## Dependencies and checks

The script imports existing public `global_visual_validation` and `media_qa_validation`, plus `jsonschema` and BeautifulSoup/lxml. BeautifulSoup/lxml are not declared in the current package metadata; they were not installed or tested here. Node and the reviewed Playwright runtime are required for real typography QA. No browser, font, Office component, renderer, runtime configuration, dependency binary or upstream asset is distributed or installed by this increment. This is source-checkout code, not a newly packaged CLI or an installation guarantee.

To run only the extracted path checks with existing Python, choose a fresh workspace:

    python tests/test_global_visual_precheck.py --candidate scripts/run_global_visual_acceptance.py --workspace path/to/new-synthetic-workspace

The driver extracts `_resolve`, `precheck_inputs` and the source-key constant as AST data; it never imports the runner or its production modules. Ten synthetic path/purity controls passed. Its tiny resource files are presence-test data, not validated schemas, PPTX or business receipts. The same `--assert-pure-valid` checker exited 0 for the candidate and 1 for a separate bad copy reintroducing directory creation. Existing workspace evidence is refused and never cleaned or overwritten.

Seven unchanged definitions were independently AST-compared with the original. Runtime argument forwarding and ordering were checked statically. Original peer checks and failures are retained separately; none are promoted into a five-medium runtime acceptance claim. Main, production imports, schema execution, typography/browser, PPT handling, web cleanup and conformance generation were not run. Python syntax passed. The original five-medium semantics and resource compatibility are source-reviewed, not a completed media workflow.

## Claims and exit boundaries

Runtime returns 0 after its acceptance path and 2 for handled precheck/RuntimeError failures. Other parse, I/O, dependency or validation exceptions may propagate nonzero; a structured failure receipt is not guaranteed for every exception. Technical flags for fact/rights/privacy are inherited fixed True values, not real reviews. Source hashes and PPT receipt fields are integrity references, not proof of authenticity or author confirmation. Web cleanup removes selected script/source references only; it does not guarantee safe/offline HTML. No real content review, clinical evidence, publication permission or deployment is established.
