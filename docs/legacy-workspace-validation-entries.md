# Legacy Workspace Validation Entries Source Guide

## 1. Purpose and Scope
This document specifies the source contracts for two legacy PowerShell automation scripts (`sync-fixtures.ps1` and `validate.ps1`) under the Apache-2.0 license. The scripts provide first-party entry points for staging shadow content fixtures and executing the original sequential validation pipeline. This increment adds no schemas, configurations, test fixtures, fonts, or third-party code; unprovided assets are not claimed to be synthetic, verified, or rights-cleared.

## 2. Layout and Staging Contract (`sync-fixtures.ps1`)
The script resolves relative monorepo boundaries where `$Root` is the parent of `$PSScriptRoot` and `$Workspace` is the parent of `$Root`:
- Copies non-recursive `*.json` files from `$Workspace\docs\content-creation-system\shadow-imports` into `$Root\content\items` using `Copy-Item -Force`.
- **Operational Caveats**: Each source file is passed to the same destination path with Copy-Item -Force. If that destination already is a directory, matching basenames can be overwritten. The script does not validate or create the destination as a directory, back it up or isolate ownership. Handling of a missing or incorrectly typed destination is unverified. This is an active filesystem copy, not a dry-run or read-only staging operation.

## 3. Validation Chain Contract (`validate.ps1`)
The script sets PYTHONDONTWRITEBYTECODE=1 in the PowerShell process environment for subsequent Python children and uses ambient python from PATH without activating a virtual environment. It retains this sequential chain and its nonzero-child-status propagation:
1. Item validation against `content-item.schema.json`
2. Profile reference validation against `profile-registry.json`
3. Content visualization routing validation (`-X utf8`)
4. Data explanation chart validation (`-X utf8 --validate-only`)
5. Insurance clause explanation validation (`-X utf8` with schema)
6. Sveltia configuration validation (`-X utf8`)
7. Standard unit test discovery with python -m unittest discover, -s set to Join-Path $Root 'tests', and -p 'test_*.py'

Each step checks `$LASTEXITCODE -ne 0` and immediately halts execution on non-zero exit. Note that `--validate-only` applies solely to the chart validator; the remaining scripts are not guaranteed side-effect-free.

## 4. Verification Status and Limits
PowerShell syntax parsing and script execution remain strictly **UNEXECUTED (NOT RUN)**. Verification is limited to static full-source reading and line/hash review. Running these workflows requires external monorepo schemas and runtime dependencies not provided here; no runnable quickstart command is supplied.

The complete source lines, original child arguments, ordering and all seven nonzero-exit guards are retained. sync-fixtures.ps1 already used LF and remains byte-identical; validate.ps1 changes only CRLF to LF. These are current first-party working snapshots, not historical Git-inclusion evidence. No original item, fixture, schema, profile, test directory or renderer body was read, and no inference that a public path exists establishes compatible legacy behavior. Prior blocked PowerShell parser acceptance remains unverified; this batch did not retry it.
