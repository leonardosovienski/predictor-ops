[CmdletBinding()]
param([switch]$RunNow)

$ErrorActionPreference = "Stop"
$workspace = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot "operational_runner.py"
$runnerPython = (& py -3.13 -c "import sys; print(sys.executable)").Trim()
if (-not (Test-Path -LiteralPath $runnerPython) -or -not (Test-Path -LiteralPath $runner)) {
    throw "Python 3.13 ou operational_runner.py ausente"
}

function Register-CollectionOnlyTask {
    param(
        [string]$Name, [string]$Project, [string]$Python, [string]$ChildScript,
        [string[]]$ChildArgs, [string]$Schedule, [int]$TimeoutSeconds,
        [Microsoft.Management.Infrastructure.CimInstance[]]$Trigger
    )
    $root = Join-Path $workspace $Project
    $operations = Join-Path $root "logs\operations"
    $child = @('-X','utf8',('"{0}"' -f $ChildScript)) + $ChildArgs
    $runnerArgs = @(
        ('"{0}"' -f $runner), '--task', $Name, '--project', $Project,
        '--cwd', ('"{0}"' -f $root), '--log', ('"{0}"' -f (Join-Path $operations "$Name.log")),
        '--heartbeat', ('"{0}"' -f (Join-Path $operations "$Name.heartbeat.json")),
        '--event-log', ('"{0}"' -f (Join-Path $operations "$Name.events.jsonl")),
        '--lock', ('"{0}"' -f (Join-Path $operations "$Name.lock")),
        '--lock-stale-after', '900', '--timeout', [string]$TimeoutSeconds,
        '--provenance-mode', 'strict', '--', ('"{0}"' -f $Python)
    ) + $child
    $action = New-ScheduledTaskAction -Execute $runnerPython -Argument ($runnerArgs -join ' ') -WorkingDirectory $root
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds $TimeoutSeconds) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $Trigger -Settings $settings -Principal $principal -Description ("COLLECTION_ONLY via operational_runner; " + $Schedule) -Force | Out-Null
    if ($RunNow) { Start-ScheduledTask -TaskName $Name }
}

$brRoot = Join-Path $workspace "brasileirao-predictor"
$lolRoot = Join-Path $workspace "lol-predictor"
$csRoot = Join-Path $workspace "cs-predictor"
$f1Root = Join-Path $workspace "f1-predictor"
$brPython = (& py -3.13 -c "import sys; print(sys.executable)").Trim()

Register-CollectionOnlyTask -Name 'brasileirao-archival-collection' -Project 'brasileirao-predictor' -Python $brPython -ChildScript (Join-Path $brRoot 'scripts\collect_collection_only.py') -ChildArgs @() -Schedule 'daily 03:30 local, archival only' -TimeoutSeconds 300 -Trigger (New-ScheduledTaskTrigger -Daily -At '03:30')
Register-CollectionOnlyTask -Name 'lol-archival-collection' -Project 'lol-predictor' -Python (Join-Path $lolRoot '.venv\Scripts\python.exe') -ChildScript (Join-Path $lolRoot 'scripts\run_archival_collection.py') -ChildArgs @() -Schedule 'daily 03:15 local' -TimeoutSeconds 300 -Trigger (New-ScheduledTaskTrigger -Daily -At '03:15')
Register-CollectionOnlyTask -Name 'cs-archival-collection' -Project 'cs-predictor' -Python (Join-Path $csRoot '.venv\Scripts\python.exe') -ChildScript (Join-Path $csRoot 'scripts\run_archival_collection.py') -ChildArgs @('--input',('"{0}"' -f (Join-Path $csRoot 'data\collection_only\upstream_events.json'))) -Schedule 'hourly source-file check' -TimeoutSeconds 300 -Trigger (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Hours 1))
$f1Triggers = @((New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At '18:00'), (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At '18:00'))
Register-CollectionOnlyTask -Name 'f1-archival-collection' -Project 'f1-predictor' -Python (Join-Path $f1Root '.venv\Scripts\python.exe') -ChildScript (Join-Path $f1Root 'scripts\run_archival_collection.py') -ChildArgs @() -Schedule 'Friday and Sunday 18:00 local, calendar-aware' -TimeoutSeconds 300 -Trigger $f1Triggers

@('lol-market-shadow','cs-market-shadow','f1-forward-snapshot') | ForEach-Object {
    if ((Get-ScheduledTask -TaskName $_ -ErrorAction Stop).State -ne 'Disabled') {
        throw "job encerrado reativado indevidamente: $_"
    }
}
Get-ScheduledTask -TaskName 'brasileirao-archival-collection','lol-archival-collection','cs-archival-collection','f1-archival-collection' | Select-Object TaskName,State
