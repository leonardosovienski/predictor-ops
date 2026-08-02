# Removed operations migration plan

This plan controls the 1.x to 2.x transition. Removal from the wheel does not imply that an operational capability may be removed from a deployment. Consumer repositories are intentionally outside this change.

| Removed item | Old function / known consumers | 2.x replacement | Equivalent command | Differences and migration | Rollback | Transition / test / removal condition |
|---|---|---|---|---|---|---|
| `install_collection_only_tasks.ps1` | Registered four consumer-specific collection jobs | Deployment-owned scheduler plus validated `jobs.json` | `predictor-ops run --config jobs.json --job ID` | Export each old action/cadence, validate config, install wheel, switch one task at a time | Point the scheduled action back to the preserved 1.3.6 checkout | TRANSITIONAL; consumer contract fixtures; remove old task after two successful cadences |
| `install_predictor_gate_monitor_task.ps1` | Registered the gate monitor | Orchestrator schedule invoking a consumer-owned health job; deprecated script retained under `migration/windows` | `predictor-ops run --config jobs.json --job gate-monitor` | Scheduling moves out of the library; scientific states remain consumer output | Run the retained migration script | TRANSITIONAL until the consumer monitor command is packaged and its contract passes |
| `install_task_health_monitor_task.ps1` | Registered Windows health monitor | `predictor_ops.windows.inspect_scheduled_task` plus deployment health job | Deployment-specific health command | Typed fail-closed query replaces embedded installation policy | Re-enable old task | TRANSITIONAL; unit and Windows integration tests; remove after Windows task migration |
| `monitor_predictor_gates.ps1` | Read-only domain gate aggregation | Consumer-owned aggregator executed by runner; deprecated script retained under `migration/windows` | `predictor-ops run ...` | Domain names and scientific interpretation cannot live in the generic library | Run the retained migration script without changing gates | TRANSITIONAL; requires consumer fixture/contract before retirement |
| `monitor_task_health.ps1` | Scheduler, lateness and heartbeat assessment | `predictor_ops.windows` and JSON heartbeat contract | Python health adapter | Cross-platform records; Windows query remains transitional | Restore 1.3.6 monitor | TRANSITIONAL; `test_windows_adapter.py`, `windows_integration/test_windows_real.py` |
| `ecosystem_health.py` | Loaded workspace-root task file and queried scheduler | Typed jobs file and `inspect_scheduled_task` | `predictor-ops validate jobs.json` plus health adapter | No sibling/workspace paths; scheduling policy is deployment configuration | Run old CLI read-only against preserved config | TRANSITIONAL; removal after health report parity tests are complete |
| `tools_provenance.py` | Git/manifest identity for runner | `predictor_ops.provenance` | Automatic during `run`; strict via `provenance_mode: strict` | Wheel `RECORD` hashes are canonical; editable installs fail strict | Use 1.3.6 runner in strict mode | REPLACED; wheel tamper/dirty/permissive tests |
| `release_manifest.py` | Generated self-referential checkout manifest | Wheel `RECORD`, `uv.lock`, CI wheel smoke | `uv build` | Installed bytes, rather than checkout topology, are verified | Re-run old manifest check for 1.x only | REPLACED; provenance wheel tests |
| `release_check.py` | Workspace and isolated clone preflight | CI quality, wheel, external CLI, container and scan jobs | `uv run pytest ... && uv build` | No sibling repositories; consumer contracts are fixtures | Run historical preflight for 1.x release only | REPLACED when all CI jobs are green |
| `core_provenance.py` / probe | Detected vendored-core import identity | Consumer provenance payload, wheel identity and contract fixtures | Set `provenance` in job config | The library stores/redacts opaque consumer identity; it no longer inspects sibling vendors | Transitional generic byte audit | TRANSITIONAL until all consumer-owned contracts prove their provenance payload |
| `vendor_byte_audit.py` | Byte-compared vendored core across siblings | Generic read-only `predictor_ops.compat.vendor_audit` | Consumer CI contract or compatibility audit | Vendoring is forbidden in target architecture; adapter never knows consumer names | Run the generic compatibility audit | TRANSITIONAL until each known consumer no longer vendors core |
| `run_hidden.py` | `CREATE_NO_WINDOW` wrapper and exit propagation | Runner Windows process group plus `CREATE_NO_WINDOW` | `predictor-ops run ...` | One installed CLI replaces PythonW/PowerShell chain | Restore wrapper for an unmigrated task | TRANSITIONAL; Windows tests; remove after no task invokes wrapper |
| `_win32_compat.py` | Constant shim | `getattr(subprocess, "CREATE_NO_WINDOW", 0)` in isolated adapter/runner | N/A | No flat-module fallback | Restore only with 1.x checkout | REPLACED by platform tests |

## Operational migration sequence

1. Archive the current task XML/action and retain the 1.3.6 wheel/checkout for rollback.
2. Install the 2.x wheel in an isolated environment and validate the deployment jobs file.
3. Run one shadow invocation and compare exit code, redacted heartbeat, terminal JSONL and provenance.
4. Change only the scheduled executable/action; do not change scientific command, cadence or policy.
5. Observe at least two successful cadences, then disable—not delete—the old task.
6. Delete the old task and compatibility files only after the consumer-owned wheel contract is green.

Any future item marked `BLOCKED` prevents `READY`; transitional items remain release gates until their stated conditions are met.
