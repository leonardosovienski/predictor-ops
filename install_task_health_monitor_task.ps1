# Instalador da tarefa predictor-task-health.
#
# Por que este arquivo existe: a tarefa foi registrada a mao em 2026-07-26 e
# ficou SEM instalador versionado -- o unico artefato agendado do ecossistema
# nessa situacao. Consequencia pratica: ela nasceu executando powershell.exe
# sob LogonType Interactive, o defeito nao estava em lugar nenhum para ser
# revisado, e so apareceu quando o dono viu janelas de console abrindo na tela.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File tools\install_task_health_monitor_task.ps1
#   ... -RunNow   (dispara uma vez logo apos instalar)

[CmdletBinding()]
param([switch]$RunNow)

$ErrorActionPreference = "Stop"
$name = "predictor-task-health"
$script = Join-Path $PSScriptRoot "monitor_task_health.ps1"
$launcher = Join-Path $PSScriptRoot "run_hidden.py"

# `pythonw.exe` + run_hidden.py em vez de powershell.exe direto -- ver o
# comentario longo em install_predictor_gate_monitor_task.ps1. Resumo: sob
# LogonType Interactive o console host abre janela em C:\Windows\System32 a
# cada disparo, `-WindowStyle Hidden` nao impede, e trocar para S4U exige
# elevacao. O lancador propaga o exit code, que aqui tambem importa.
$pythonw = & py -3 -c "import os, sys; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"
if (-not $pythonw -or -not (Test-Path $pythonw)) {
    throw "pythonw.exe nao encontrado (resolvido como '$pythonw'); sem ele a tarefa volta a abrir janela"
}

$arguments = '"{0}" powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{1}"' -f $launcher, $script
$action = New-ScheduledTaskAction -Execute $pythonw -Argument $arguments
# Diario as 07:00, por decisao do dono em 2026-07-26 (era de 6 em 6 horas).
# Este e o monitor que escreve o ALERTA_TAREFAS.txt na raiz -- o arquivo que o
# dono LE. As 07:00 ele ja esta pronto quando o dia comeca, refletindo a noite
# inteira de coleta. `-StartWhenAvailable` (abaixo) recupera o disparo se a
# maquina estiver desligada, que agora e a unica chance do dia.
$trigger = New-ScheduledTaskTrigger -Daily -At "07:00"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Exit code and overdue monitor for every ecosystem scheduled task; writes/removes ALERTA_TAREFAS.txt" -Force | Out-Null
if ($RunNow) { Start-ScheduledTask -TaskName $name }
Write-Output "Installed $name"
