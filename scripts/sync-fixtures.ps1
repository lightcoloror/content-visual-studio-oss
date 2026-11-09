[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Workspace = Split-Path -Parent $Root
$Source = Join-Path $Workspace 'docs\content-creation-system\shadow-imports'
$Destination = Join-Path $Root 'content\items'

Get-ChildItem -LiteralPath $Source -Filter '*.json' -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $Destination -Force
}

Write-Host "Synced shadow fixtures from $Source"
