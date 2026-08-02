# Saude das tarefas agendadas do ecossistema: exit code + atraso.
#
# Por que existe: o monitor_predictor_gates.ps1 JA detectava exit code diferente
# de zero, e teria pegado o lol-ratings-semanal em PARTIAL (exit 10) no dia 1.
# Ele nao falhou em detectar -- falhou em AVISAR. Escrevia um JSON em logs/ e
# saia com codigo 1, e ninguem olha nem o JSON nem o exit code do monitor. O
# problema passou 6 dias invisivel (B-10).
#
# A diferenca aqui: quando algo esta errado, este script CRIA um arquivo
# ALERTA_TAREFAS.txt na RAIZ do workspace, em texto puro. Quando tudo esta bem,
# ele APAGA esse arquivo. A presenca do arquivo e o sinal -- nao e preciso abrir
# nada nem lembrar de conferir exit code.
#
# Tambem cobre o que o monitor de gates nao cobre: a lista de tarefas e
# descoberta por padrao (nao ha 7 nomes fixos que envelhecem) e detecta tarefa
# ATRASADA, isto e, que deveria ter rodado e nao rodou -- falha que exit code
# nenhum revela, porque a tarefa simplesmente nao executou.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File tools\monitor_task_health.ps1
#   ... -WhatIf   (so relata, nao escreve nem apaga o alerta)

[CmdletBinding()]
param(
    [string]$AlertPath = "",
    [string]$HistoryPath = "",
    [int]$OverdueHours = 2,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$workspace = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($AlertPath)) {
    $AlertPath = Join-Path $workspace "ALERTA_TAREFAS.txt"
}
if ([string]::IsNullOrWhiteSpace($HistoryPath)) {
    $HistoryPath = Join-Path $PSScriptRoot "logs\task_health.log"
}

# Padrao de descoberta: qualquer tarefa do ecossistema. Preferido a uma lista
# fixa de nomes, que foi como o monitor de gates ficou desatualizado (nao cobria
# archival-collection nem closing-snapshot).
$padrao = 'brasileirao|cs-|lol-|f1-|Garimpo|cripto|predictor-gate'

# Tarefas desabilitadas DE PROPOSITO. Nao alertar sobre elas; alertar sobre uma
# tarefa desabilitada que deveria estar ativa e trabalho para humano, nao para
# heuristica.
$desabilitadasEsperadas = @(
    'f1-forward-snapshot',                 # H8 encerrado por decisao humana
    'GarimpoInvestimentos-ColetaDiaria'    # legada, substituida
)

$agora = [DateTime]::UtcNow
$problemas = New-Object System.Collections.Generic.List[string]
$linhas = New-Object System.Collections.Generic.List[string]

$tarefas = Get-ScheduledTask | Where-Object { $_.TaskName -match $padrao } | Sort-Object TaskName
foreach ($t in $tarefas) {
    $nome = $t.TaskName
    $info = Get-ScheduledTaskInfo -TaskName $nome -ErrorAction SilentlyContinue
    if ($null -eq $info) {
        $problemas.Add("SEM_INFO      $nome (tarefa existe mas nao devolve info)")
        continue
    }
    $resultado = [int]$info.LastTaskResult
    $ultima = $info.LastRunTime
    $proxima = $info.NextRunTime
    $estado = [string]$t.State

    $linhas.Add(("{0,-34} {1,-9} exit={2,-8} ultima={3}" -f $nome, $estado, $resultado,
        $(if ($ultima -and $ultima.Year -gt 2000) { $ultima.ToString("yyyy-MM-dd HH:mm") } else { "nunca" })))

    if ($estado -eq 'Disabled') {
        if ($desabilitadasEsperadas -notcontains $nome) {
            $problemas.Add("DESABILITADA  $nome (nao esta na lista de desabilitadas esperadas)")
        }
        continue
    }
    if ($estado -eq 'Running') { continue }

    # 267011 = "a tarefa ainda nao rodou". Nao e falha.
    if ($resultado -ne 0 -and $resultado -ne 267011) {
        $problemas.Add(("EXIT={0,-8}  {1} (ultima execucao em {2})" -f $resultado, $nome,
            $(if ($ultima -and $ultima.Year -gt 2000) { $ultima.ToString("yyyy-MM-dd HH:mm") } else { "nunca" })))
    }

    # Atrasada: deveria ter rodado e nao rodou. Exit code nenhum pega isso.
    if ($proxima -and $proxima.Year -gt 2000) {
        $atraso = ($agora.ToLocalTime() - $proxima).TotalHours
        if ($atraso -gt $OverdueHours) {
            $problemas.Add(("ATRASADA      {0} (deveria ter rodado ha {1:N1}h, em {2})" -f `
                $nome, $atraso, $proxima.ToString("yyyy-MM-dd HH:mm")))
        }
    }
}

$stamp = $agora.ToString("yyyy-MM-ddTHH:mm:ssZ")
$resumo = "$stamp tarefas=$($tarefas.Count) problemas=$($problemas.Count)"

if (-not $WhatIf) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $HistoryPath) | Out-Null
    Add-Content -LiteralPath $HistoryPath -Value $resumo -Encoding utf8
    foreach ($p in $problemas) { Add-Content -LiteralPath $HistoryPath -Value "    $p" -Encoding utf8 }
}

if ($problemas.Count -eq 0) {
    # Tudo certo: o alerta some. A AUSENCIA do arquivo e' o sinal de saude.
    if (-not $WhatIf -and (Test-Path -LiteralPath $AlertPath)) {
        Remove-Item -LiteralPath $AlertPath -Force
    }
    Write-Output "OK - $($tarefas.Count) tarefas, nenhum problema"
    $linhas | ForEach-Object { Write-Output "  $_" }
    exit 0
}

$texto = @()
$texto += "ALERTA DE TAREFAS AGENDADAS"
$texto += "gerado em $stamp (UTC)"
$texto += ""
$texto += "$($problemas.Count) problema(s) em $($tarefas.Count) tarefas do ecossistema:"
$texto += ""
foreach ($p in $problemas) { $texto += "  $p" }
$texto += ""
$texto += "Estado completo:"
foreach ($l in $linhas) { $texto += "  $l" }
$texto += ""
$texto += "Este arquivo e apagado sozinho quando tudo voltar ao normal."
$texto += "Historico: tools\logs\task_health.log"

if (-not $WhatIf) {
    Set-Content -LiteralPath $AlertPath -Value ($texto -join "`r`n") -Encoding utf8
}
$texto | ForEach-Object { Write-Output $_ }
exit 1

