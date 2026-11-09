# Repository-Local Test Workspace Helper

`docs/repository-local-test-workspace.md` documents the optional, source-only test workspace helper in `tests/temp_workspace.py` and its regression suite in `tests/test_temp_workspace.py`, licensed under Apache-2.0.

## Execution and Environment

Run the unit tests from the public source checkout using existing Python:

```bash
python -X utf8 -B tests/test_temp_workspace.py -f -v
```

Owner verification under CPython 3.13.5 confirmed 8 passes (0 skips), covering 6 baseline isolation tests and 2 targeted prefix validation methods.

## Helper Behavior and Prefix Validation

`isolated_test_directory` checks the configured root and validates a run-specific prefix before creating scratch directories:

- **Root Confinement**: Defaults to `outputs/.test-runtime/temp`. Any explicit root or `CONTENT_STUDIO_TEST_TEMP_ROOT` override must resolve within the project tree. The helper supplies its directory explicitly; it does not choose an OS-global `TEMP`/`TMP` fallback.
- **Fail-Closed Prefix Guard**: When the context manager is entered, before preparing the root or invoking filesystem actions, `_validate_prefix` ensures the prefix is a non-empty, single-component string. It rejects `.`, `..`, path separators (`/`, `\`, `:`), and C0/DEL/C1 control characters. It does not sanitize or rewrite invalid input. Ordinary Chinese characters and hyphens are supported.
- **Pre-Filesystem Sentinel**: 22 invalid prefix subcases patch `prepare_test_temp_root` with an assertion sentinel and confirm rejection before that function is called. A separate bad copy removed only the new guard call; the same targeted method then failed in all 22 subcases at the mock sentinel, without attempting an escaping filesystem operation.
- **Scoped Teardown**: Cleans only the created run-specific directory; parent scaffolding is preserved.
- **Concurrency & Residue**: Tests verify multithreaded allocation (4 threads, 8 unique jobs) and stale sibling isolation.

## Security and Verification Boundaries

Prefix validation verifies basic path syntax only. It does not constitute an OS sandbox, TOCTOU protection, symlink/junction defense, or ACL enforcement. The OS-global temp failure in the original suite is a mocked `gettempdir` PermissionError; the file-marker negative case is FileExistsError, not a real ACL denial. Actual permission errors produce a controlled error; stop and report them without changing ACLs, modes or paths to retry. Benign caller-controlled prefixes are supported; no arbitrary OS-name sanitization is claimed. Installed-wheel packaging, other platforms and full workflows remain unverified.
