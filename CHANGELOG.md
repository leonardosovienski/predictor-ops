# Changelog

## Unreleased

- Make the operational-entrypoint contract tests runnable off Windows. Both
  `test_cs_operational_entrypoint` and `test_lol_operational_entrypoint`
  asserted `.endswith("data\\ratings.json")`, hardcoding the Windows path
  separator, so they could never pass on a POSIX checkout. They now compare
  path *components* (`Path(...).parts[-2:] == ("data", "ratings.json")`),
  asserting the same thing on either platform.

- Skip the two lol entrypoint tests when the lol-predictor runtime artifacts
  are absent, instead of failing. `atualiza_semanal.py` aborts in its
  provenance guard without all four of `runtime_manifest.ARTIFACTS`, and those
  are gitignored ingestion output.

  These are deliberately NOT covered by a synthetic seed the way f1-predictor
  and brasileirao-predictor are. `data/calibration.json` is not an inert
  artifact -- it is a mode switch: `src/model.py::_kills_calibration` falls back
  to the config.yaml global baseline when the file is absent, but starts
  *requiring* `--kills-league` once it exists. A fabricated calibration.json
  breaks 9 real tests in lol-predictor itself (verified). A fixture must not
  change production semantics to accommodate itself.

- Fix `vendor_byte_audit.py` reporting `MANIFEST_MISMATCH` for a vendor tree
  that is byte-for-byte identical to the canonical core.  The aggregate was
  recomputed as `sha256(...).hexdigest()[:16]`, the truncated form used by
  `sync_core` before predictor_core 2.0.0; that release moved the manifest
  aggregate to the full SHA-256 and the audit was never updated.  Both call
  sites (`aggregate()` and the declared-hash recomputation) now use the full
  digest, so a synced consumer reports `IDENTICAL` and exit code 0 instead of
  two spurious `manifest_issues`.

  Observed on 2026-07-31 against cripto-predictor and brasileirao-predictor
  freshly synced from core 2.0.1: `files=47/47 identical=47 changed=0` and
  still `MANIFEST_MISMATCH` -- the audit contradicted its own file comparison.

- Stop the gate monitor from reporting a declared scientific closure as a
  probe error.  A gate probe that exits non-zero while emitting parseable
  output declaring a terminal state (today only `CLOSED_BY_HUMAN_DECISION`)
  is now recorded as `CLOSED` and does not degrade the run.  Non-zero exits
  that are unparseable, or that declare no terminal state, remain `ERROR`
  with the exit code preserved -- this is deliberately not a blanket amnesty
  for non-zero exits.

  Observed live on 2026-07-25: cs-predictor's `market_shadow_status.py` exited
  3 to report `CLOSED_BY_HUMAN_DECISION`, the monitor classified it as
  `ERROR`, and the resulting permanent alert masked a real failure
  (`lol-ratings-semanal` `LastTaskResult=10`).  By 2026-07-28 the CS cohort
  had been reopened by a separate decision and that probe exits 0 again
  (`PENDING_SETTLEMENT`, 29/50 matured), so the specific false positive is no
  longer reproducible; the classification rule is kept because any gate probe
  may declare a terminal state this way, and the `lol-ratings-semanal`
  failure it was hiding is real and still open.

- Stop the two PowerShell monitors (`predictor-gate-monitor`,
  `predictor-task-health`) from opening a console window on the owner's
  desktop at every trigger — every 30 minutes in the gate monitor's case.
  Under `LogonType Interactive` the Windows console host creates the window
  *before* PowerShell starts, so the `-WindowStyle Hidden` already present in
  the arguments never had a chance; and because the action set no
  `WorkingDirectory`, the console opened in `C:\Windows\System32`. Switching
  the principal to `S4U` is the canonical fix but requires elevation
  (`Set-ScheduledTask` and `Register-ScheduledTask -Force` both return access
  denied). Instead the tasks now run `pythonw.exe` — GUI subsystem, never
  creates a console — against the new `run_hidden.py`, which launches the real
  command with `CREATE_NO_WINDOW` and **propagates the child exit code**. The
  propagation is a requirement, not a detail: the gate monitor exits 1 on a
  degraded task and `monitor_task_health.ps1` reads that `LastTaskResult`.

- Add `install_task_health_monitor_task.ps1`. `predictor-task-health` had been
  registered by hand and was the only scheduled task in the ecosystem without
  a versioned installer, which is why its principal was never reviewed.

- Move both monitors to a single daily run, by the owner's decision:
  `predictor-task-health` at **07:00** (it writes the `ALERTA_TAREFAS.txt` the
  owner actually reads, so it should be ready when the day starts) and
  `predictor-gate-monitor` at **00:00** (after the whole night collection
  chain — 21:30, 22:00, 22:30, 23:00 — so its snapshot covers a full day).
  Previously every 6h and every 30min. `-StartWhenAvailable` was already set
  and matters more now that each has one chance per day instead of 4 and 48.
  The overdue check in `monitor_task_health.ps1` compares against each task's
  own `NextRunTime`, not a fixed interval, so daily cadence raises no false
  "atrasada".

- Regenerate `TOOLS_MANIFEST.json` after `monitor_task_health.ps1` was added
  without it, and add a regression test that validates the **real** checked-in
  manifest. Every existing manifest test used a synthetic repository in
  `tmp_path`, so the suite stayed green while `collect_tools_provenance` raised
  and `operational_runner` returned exit 3 fail-closed for every scheduled task
  in the ecosystem. One real run (`cs-archival-collection`, 15:22) failed
  inside the 34-minute window before it was caught.

- Declare `pythonpath = [".."]` for pytest. The suite required
  `PYTHONPATH=<workspace>` passed by hand; without it four modules failed to
  collect. The sys.path consumption contract is unchanged — only declared where
  pytest reads it.

- Move COLLECTION_ONLY runner artifacts from consumer repositories to the
  per-user LOCALAPPDATA runtime root, preserving legacy evidence separately.

- Route the four consumer COLLECTION_ONLY scheduled jobs through the strict
  operational runner, including project-specific locks, timeouts, heartbeats
  and structured events.  Closed scientific jobs remain disabled.

- Add a read-only 30-minute gate monitor for CS, LoL, F1 and Brasileirão.
  It records scheduler health and each available shadow-sample status, treats
  expected waiting states as non-errors, and never authorizes capital.

- Reconcile the PEP 621 project version with `VERSION` at 1.3.1 and add a
  regression test that requires both declarations to match.

## 1.3.1 — 2026-07-19

Closes OP-1 (`PENDENCIAS_ABERTAS.md`): a runner instance that loses the lock
race no longer writes `SKIPPED` to the shared heartbeat — where it raced the
lock owner's writes and could overwrite the winner's RUNNING/final state — and
instead publishes to a `<name>.skipped.json` sidecar
(`operational_runner.skipped_heartbeat_path`) plus the serialized JSONL event
log, unchanged. No live consumer read `SKIPPED` from the main heartbeat
(verified by grep across the 5 live consumers). The Windows
`os.replace` retry remains as a defense for two simultaneous losers colliding
on the sidecar.

## 1.3.0 — 2026-07-17

Adds `release_manifest.py`, a canonical generator/validator for
`TOOLS_MANIFEST.json` (`--check` / `--write`), reusing
`tools_provenance.content_hash`/`_tracked_files` as the single source of the
fingerprint algorithm rather than duplicating it. Removes the
provider-specific `x-cg-demo-api-key` literal from `secret_redaction.py`'s
sensitive-key patterns; coverage is unaffected (the generic `api[_-]?key`
fragment already matches it). Discovered during ecosystem reintegration:
`TOOLS_MANIFEST.json` had no documented way to regenerate itself after a
legitimate content change, which left strict provenance permanently unable
to MATCH following any normal edit.

## 1.2.3 — 2026-07-16

Raises the validated CI coverage gate to 80% after adding health and redaction
CLI regression tests. Ignores local coverage databases. The active workspace
health configuration is backed up as `audit/task_backups/HEALTH_TASKS.1.2.3.json`.

## 1.2.2 — 2026-07-16

Corrects the CI coverage threshold to 75%, validated against the current
77% baseline, so the new gate protects against regression without rejecting
the release it is intended to verify.

## 1.2.1 — 2026-07-16

Moves the default health task configuration to the workspace boundary, keeping
the tools repository domain-agnostic. Adds a test-only CI coverage gate at 80%
without adding a runtime dependency, and documents the intentionally null
release-commit field in the self-describing manifest.

## 1.2.0 — 2026-07-16

Adds additive terminal diagnostics for output truncation, run-lock recovery,
and timeout process-tree termination. Moves health task metadata into a
validated declarative JSON file with an optional override, and adds a
read-only release verifier for workspace tests, isolated-clone tests, and
strict clone provenance. Corrects the provenance documentation example.

## 1.1.1 — 2026-07-16

Makes strict provenance/setup failures observable through terminal heartbeat
and JSONL records without weakening fail-closed behavior. Adds bounded,
streamed redacted output; process-tree termination on timeout; recoverable
stale locks; and serialized, fsynced JSONL appends. Health handling now treats
an invalid Scheduler result as `UNKNOWN` instead of crashing. All additions
preserve existing CLI calls and record fields.

## 1.1.0 — 2026-07-15

Adds native, validated tools provenance to operational heartbeats and JSONL
records. New fields are additive; lock, timeout, redaction, exit code, and
existing CLI behavior are unchanged. The release manifest and stdlib-only
provenance helper make the fingerprint reproducible in a clean clone.

## 1.0.0 — 2026-07-15

First versioned workspace release. Captures the existing operational runner,
redaction, health, vendor-byte-audit and core-provenance utilities without
changing their imports or consumer behavior.
