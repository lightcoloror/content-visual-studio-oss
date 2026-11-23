[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE = '1'
$Root = Split-Path -Parent $PSScriptRoot
$Workspace = Split-Path -Parent $Root
$ItemValidator = Join-Path $Workspace 'scripts\validate-content-creation-items.py'
$ProfileValidator = Join-Path $Workspace 'scripts\validate-content-profile-refs.py'
$RoutingValidator = Join-Path $Workspace 'scripts\validate-content-visualization-routing.py'
$ChartValidator = Join-Path $Root 'scripts\render_data_explanations.py'
$InsuranceClauseValidator = Join-Path $Root 'scripts\validate_insurance_clause_explanations.py'
$SveltiaValidator = Join-Path $Root 'scripts\validate_sveltia_config.py'
$Schema = Join-Path $Workspace 'docs\content-creation-system\content-item.schema.json'
$InsuranceClauseSchema = Join-Path $Workspace 'docs\content-creation-system\adapters\insurance-clause-explanation.schema.json'
$Profiles = Join-Path $Workspace 'docs\content-creation-system\profiles\profile-registry.json'
$Items = Join-Path $Root 'content\items'
$Fixtures = Join-Path $Root 'fixtures'

python $ItemValidator --root $Items --schema $Schema
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python $ProfileValidator --root $Items --profiles $Profiles
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -X utf8 $RoutingValidator
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -X utf8 $ChartValidator --validate-only
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -X utf8 $InsuranceClauseValidator --root $Fixtures --schema $InsuranceClauseSchema
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -X utf8 $SveltiaValidator
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m unittest discover -s (Join-Path $Root 'tests') -p 'test_*.py'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
