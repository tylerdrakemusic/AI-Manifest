#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Python = 'C:\G\python.exe',
    [string]$TaskName = 'AI-Manifest-DatabaseBackup'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$launcher = Join-Path $ProjectRoot 'tools\run_database_backup.ps1'
$inventory = Join-Path $ProjectRoot 'src\config\database_backup_inventory.json'
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`" -Python `"$Python`" -Inventory `"$inventory`" -ProjectRoot `"$ProjectRoot`""
$action = New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Daily -At '02:00'
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType InteractiveToken -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Description 'AI-Manifest canonical SQLCipher database backup' -Force | Out-Null