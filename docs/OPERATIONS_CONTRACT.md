# Predictor Ops 4 runtime contract

State: `maintenance_state=ACTIVE`, `research_state=FROZEN`,
`commercial_state=NOT_A_PRODUCT`.

## Runtime and failure contract

Ops owns process execution, one-owner locking, stale/dead-owner recovery, atomic
heartbeat replacement, serialized fsynced JSONL events, economic idempotency, bounded
output, redaction, process-tree termination and explicit operational status. It fails
closed when a lock cannot be acquired, strict provenance is invalid, configuration is
invalid, an execution has no risk snapshot, a kill-switch condition is true, an
economic attempt is already claimed, or an ambiguous execution needs reconciliation.

Every terminal record includes run/job identity, start/end/status, library and consumer
provenance, config/input/output references, host/environment, retry count, failure
details and output metadata. Optional references remain consumer-supplied because Ops
cannot invent domain dataset or artifact identity. Retries are scheduled externally;
`retry_count` records that external attempt number, while `retry_action` prevents blind
resubmission after ambiguous order states.

## Scheduler and monitoring contract

The scheduler is external: cron, Windows Task Scheduler, a container runtime or an
equivalent existing service invokes the installed CLI. Ops is the execution/control
layer and does not schedule jobs.

| Responsibility | Owner/component |
|---|---|
| Job execution and heartbeat freshness | `predictor_ops.health.assess` |
| Windows scheduled-task state | `predictor_ops.windows.query_task` |
| Event/data freshness semantics | consumer policy using heartbeat/result |
| Service health | external service manager plus typed health result |
| Scientific gate interpretation/promotion | Core/evidence contract and domain |

The removed `monitor_predictor_gates.ps1` combined scheduled-task snapshots with direct
calls to domain scientific-status scripts. Commit `6b695ea` removed it in the 4.0 scope
boundary. Its operational portion is covered by `health`/`windows`; its scientific
portion was intentionally removed from Ops. Classification: `INTENTIONALLY_REMOVED`.

## Consumer map

| Consumer | Declared usage | Critical | State |
|---|---|---|---|
| brasileirao-predictor | Ops 4 execution, shadow/idempotency/risk contracts | yes | declared by ecosystem handoff; consumer CI remains consumer-owned |
| previsao-cripto | Ops 4 execution, shadow/idempotency/risk contracts | yes | declared by ecosystem handoff; consumer CI remains consumer-owned |
| stocks-predictor | none | no | not an Ops consumer |

The package makes no current-runtime claims for historical CS, LoL or F1 tasks. Their
names existed only in removed Windows migration assets.
