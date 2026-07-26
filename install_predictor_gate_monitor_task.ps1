[CmdletBinding()]
param([switch]$RunNow)

$ErrorActionPreference = "Stop"
$name = "predictor-gate-monitor"
$script = Join-Path $PSScriptRoot "monitor_predictor_gates.ps1"
$launcher = Join-Path $PSScriptRoot "run_hidden.py"

# Por que nao `-Execute powershell.exe` direto:
#
# Com `LogonType Interactive` a tarefa ganha a area de trabalho do dono, e o
# console host do Windows ABRE UMA JANELA a cada disparo -- de 30 em 30
# minutos, na tela dele. Como a acao nao define WorkingDirectory, o console
# abre em C:\Windows\System32 e parece que "o System32 abriu sozinho".
# `-WindowStyle Hidden` NAO evita isso: e argumento do PowerShell, e quem cria
# a janela e o conhost, antes de o PowerShell comecar.
#
# A correcao canonica seria `LogonType S4U` (roda sem area de trabalho), que e
# o principal ja usado por GarimpoV3Daily e cripto-watchdog-coleta. Mas trocar
# o principal exige ELEVACAO: `Set-ScheduledTask` e `Register-ScheduledTask
# -Force` devolvem "Acesso negado" sem admin (verificado em 2026-07-26).
#
# Entao usamos o mesmo padrao de todas as outras tarefas do ecossistema:
# `pythonw.exe`, do subsistema GUI, que nunca cria console. Ele executa
# `run_hidden.py`, que lanca o PowerShell com CREATE_NO_WINDOW e **propaga o
# exit code** -- requisito, nao detalhe: este monitor sai com 1 quando ha
# tarefa degradada, e o monitor_task_health.ps1 le esse LastTaskResult.
#
# Se um dia isto for reinstalado COM elevacao, trocar o principal para
# `-LogonType S4U` e apontar o Execute direto para powershell.exe e igualmente
# correto e dispensa o lancador.

$pythonw = & py -3 -c "import os, sys; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"
if (-not $pythonw -or -not (Test-Path $pythonw)) {
    throw "pythonw.exe nao encontrado (resolvido como '$pythonw'); sem ele a tarefa volta a abrir janela"
}

$arguments = '"{0}" powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{1}"' -f $launcher, $script
$action = New-ScheduledTaskAction -Execute $pythonw -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Minutes 30)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Read-only health and gate progress monitor for CS, LoL, F1 and Brasileirao" -Force | Out-Null
if ($RunNow) { Start-ScheduledTask -TaskName $name }
Write-Output "Installed $name"
