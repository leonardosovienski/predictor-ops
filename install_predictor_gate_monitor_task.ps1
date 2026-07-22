[CmdletBinding()]
param([switch]$RunNow)

$ErrorActionPreference = "Stop"
$name = "predictor-gate-monitor"
$script = Join-Path $PSScriptRoot "monitor_predictor_gates.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"{0}`"" -f $script)
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Minutes 30)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Read-only health and gate progress monitor for CS, LoL, F1 and Brasileirao" -Force | Out-Null
if ($RunNow) { Start-ScheduledTask -TaskName $name }
Write-Output "Installed $name"
