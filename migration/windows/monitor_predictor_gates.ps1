[CmdletBinding()]
param(
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $PSScriptRoot "logs\predictor-gate-monitor.latest.json"
}

function Get-TaskSnapshot([string]$Name) {
    $task = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($null -eq $task) { return @{ name = $Name; status = "MISSING" } }
    $info = Get-ScheduledTaskInfo -TaskName $Name
    return @{
        name = $Name; status = "PRESENT"; state = [string]$task.State
        last_run_time = $info.LastRunTime.ToUniversalTime().ToString("o")
        last_task_result = [int]$info.LastTaskResult
        next_run_time = $info.NextRunTime.ToUniversalTime().ToString("o")
    }
}

# Terminal scientific states a gate probe may declare while exiting non-zero.
# A declared closure is a RESULT, not a malfunction: cs-predictor's
# market_shadow_status.py exits 3 precisely to report
# CLOSED_BY_HUMAN_DECISION, and the previous "any non-zero exit is ERROR"
# rule turned that expected end state into a permanent degraded signal,
# which in turn masked a real failure (lol-ratings-semanal LastTaskResult=10)
# behind an alert that was already on.
$script:TerminalScientificStatus = @("CLOSED_BY_HUMAN_DECISION")

function Invoke-JsonCommand([string]$Python, [string]$Script, [string[]]$Arguments = @()) {
    $raw = & $Python -X utf8 $Script @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    $text = (@($raw) -join "`n")
    $payload = $null
    try { $payload = ($text | ConvertFrom-Json) } catch { $payload = $null }
    # Unparseable output is always an error, whatever the exit code says.
    if ($null -eq $payload) {
        return @{ status = "ERROR"; exit_code = $exitCode; output = $text }
    }
    if ($exitCode -eq 0) {
        return @{ status = "OK"; exit_code = 0; payload = $payload }
    }
    # Non-zero exit WITH parseable output: only an explicitly declared
    # terminal state is accepted as expected.  Anything else stays ERROR with
    # the exit code preserved: this is deliberately not a blanket amnesty for
    # non-zero exits.
    if ($script:TerminalScientificStatus -contains [string]$payload.scientific_status) {
        return @{ status = "CLOSED"; exit_code = $exitCode; payload = $payload }
    }
    return @{ status = "ERROR"; exit_code = $exitCode; output = $text }
}

$root = Split-Path -Parent $PSScriptRoot
$cs = Join-Path $root "cs-predictor"
$lol = Join-Path $root "lol-predictor"
$br = Join-Path $root "brasileirao-predictor"
$brPython = (& py -3.13 -c "import sys; print(sys.executable)").Trim()
if (-not $brPython -or -not (Test-Path $brPython)) {
    throw "Python 3.13 global nao esta disponivel para brasileirao-predictor"
}

$result = [ordered]@{
    schema_version = "predictor-gate-monitor/v1"
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    scope = "read-only; no capital authorization; WAITING/PENDING_SAMPLE are expected scientific states; gate status CLOSED is a declared terminal result, not a failure"
    tasks = @(
        (Get-TaskSnapshot "cs-ratings-semanal"),
        (Get-TaskSnapshot "cs-market-shadow"),
        (Get-TaskSnapshot "lol-ratings-semanal"),
        (Get-TaskSnapshot "lol-market-shadow"),
        (Get-TaskSnapshot "f1-forward-snapshot"),
        (Get-TaskSnapshot "brasileirao-sombra-manha"),
        (Get-TaskSnapshot "brasileirao-sombra-noite")
    )
    gates = [ordered]@{
        cs = Invoke-JsonCommand (Join-Path $cs ".venv\Scripts\python.exe") (Join-Path $cs "scripts\market_shadow_status.py")
        lol = Invoke-JsonCommand (Join-Path $lol ".venv\Scripts\python.exe") (Join-Path $lol "scripts\market_shadow_status.py")
        brasileirao = Invoke-JsonCommand $brPython (Join-Path $br "scripts\report_shadow_mode.py") @("--json")
    }
}

$degraded = @($result.tasks | Where-Object {
    $_.status -ne "PRESENT" -or
    ($_.state -ne "Running" -and $_.last_task_result -ne 0)
}).Count -gt 0
$degraded = $degraded -or @($result.gates.Values | Where-Object { $_.status -notin @("OK", "CLOSED") }).Count -gt 0

$directory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $directory | Out-Null
$temporary = Join-Path $directory ("." + [IO.Path]::GetFileName($OutputPath) + ".tmp")
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding utf8
Move-Item -LiteralPath $temporary -Destination $OutputPath -Force

if ($degraded) { exit 1 }

