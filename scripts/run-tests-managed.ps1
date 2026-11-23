[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RuntimePath,
    [double]$TimeoutSeconds = 1800,
    [string[]]$TestArgs = @('discover', '-s', 'tests', '-v'),
    [Parameter(Mandatory=$true)][string]$ManagedRoot,
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
$repo = $RepositoryRoot
& $RuntimePath adapter -Purpose 'content-studio-tests' -Adapter unittest -WorkingDirectory $repo -ManagedRoot $managedRoot -TimeoutSeconds $TimeoutSeconds -ArgumentsJson ($TestArgs | ConvertTo-Json -Compress)
exit $LASTEXITCODE
