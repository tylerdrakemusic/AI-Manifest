#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Python = 'C:\G\python.exe',
    [Parameter(Mandatory = $true)][string]$Inventory,
    [Parameter(Mandatory = $true)][string]$ProjectRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

foreach ($name in @('WORKSPACE_BACKUP_VOLUME', 'WORKSPACE_BACKUP_VOLUME_ID', 'WORKSPACE_BACKUP_MANIFEST_KEY', 'MANIFEST_TODOS_DB_KEY')) {
    $value = [Environment]::GetEnvironmentVariable($name, 'Process')
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = [Environment]::GetEnvironmentVariable($name, 'User')
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            Set-Item -Path ('Env:' + $name) -Value $value
        }
    }
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Missing required environment variable: $name"
    }
}

$volume = [IO.Path]::GetFullPath($env:WORKSPACE_BACKUP_VOLUME)
if (-not (Test-Path -LiteralPath $volume -PathType Container)) {
    throw "Backup volume is unavailable: $volume"
}
$marker = Join-Path $volume '.backup-volume-identity'
if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
    throw "Trusted backup volume marker is absent: $marker"
}
if ((Get-Content -LiteralPath $marker -Raw).Trim() -cne $env:WORKSPACE_BACKUP_VOLUME_ID) {
    throw 'Trusted backup volume marker does not match WORKSPACE_BACKUP_VOLUME_ID.'
}

& $Python (Join-Path $PSScriptRoot 'run_database_backup.py') `
    '--inventory' $Inventory `
    '--project-root' $ProjectRoot `
    '--volume-root' $volume
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }