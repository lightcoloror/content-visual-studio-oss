# Managed Test Entry Wrapper Source Guide

## 1. Purpose and Scope
This document specifies the regression source contracts for the first-party PowerShell test wrapper under the Apache-2.0 license. The wrapper parameterizes invocation of an unbundled external test runtime adapter, eliminating legacy hardcoded private paths without bundling runtime dependencies or operational test data.

## 2. Parameter Contract and Declaration Ordering
To maintain positional binding stability under default `CmdletBinding`, the parameter block preserves the relative declaration order of original parameters before appending new inputs:
- **`$RuntimePath`**: Mandatory string identifying the external runtime entry invoked by the wrapper through &; no runtime binary or implementation is included.
- **`$TimeoutSeconds`**: Retained optional double defaulting to `1800`.
- **`$TestArgs`**: Retained optional string array defaulting to `@('discover', '-s', 'tests', '-v')`.
- **`$ManagedRoot`**: Appended mandatory string passed to the adapter as `-ManagedRoot`.
- **`$RepositoryRoot`**: Appended optional string defaulting to `(Split-Path -Parent $PSScriptRoot)`, assigned to `$repo` and passed as `-WorkingDirectory`.

Mandatory parameters may prompt interactively or raise binding errors if omitted. Requiring `$ManagedRoot` means callers must update invocations.

## 3. Adapter Delegation and External Boundaries
The wrapper keeps original invocation syntax, defaults, and error handling:
- Preserves `$ErrorActionPreference = 'Stop'`, JSON pipeline compression `($TestArgs | ConvertTo-Json -Compress)`, and exit code propagation `exit $LASTEXITCODE`.
- Invokes `& $RuntimePath adapter -Purpose 'content-studio-tests' -Adapter unittest ...`.
- Directory isolation, output lifecycle, and resource governance depend entirely on the unbundled external adapter and have not been audited. Argument serialization compatibility across arbitrary parameter cardinalities remains unverified.

## 4. Verification Status and Limits
The candidate (SHA256: `d95f72c9310889ddcc1a1d1aa4699d9a4e1dd791239f7c1183a88d18dd27255b`) was verified strictly via static 12-line source review and hash validation. PowerShell syntax parsing and execution remain **UNEXECUTED (NOT RUN)**. No runnable quickstart or runtime execution claims are provided.

The first three declarations retain RuntimePath, TimeoutSeconds and TestArgs in
their original order; new fields follow them. This avoids repurposing those
automatic positions under the documented default, but requiring ManagedRoot
still changes the caller input contract. See the [PowerShell positional-binding
rule](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_functions_cmdletbindingattribute?view=powershell-7.5#positionalbinding).
This is source reasoning, not an executed parameter-binding check. Actual
adapter exit behavior, runtime compatibility and resource/directory semantics
remain unverified. Source provenance is an existing first-party working snapshot,
not historical Git inclusion or a rights clearance for unbundled dependencies.
