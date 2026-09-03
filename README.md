# predictor_ops

> **Estado no ecossistema em 2026-09-01:** versão 4.0.0. Brasileirão e cripto
> declaram esta linha; Stocks ainda não depende de Ops. Gates de edge pertencem
> aos domínios. Ops executa `SHADOW_DECISION`, idempotência, risco e reconciliação,
> mas nunca promove lucro nem autoriza capital por inferência.

`predictor_ops` is an installable, domain-neutral operational runner for Python
3.13+. It runs on Linux, containers and Windows without relying on a workspace
layout, sibling repositories, `PYTHONPATH`, PowerShell, `pythonw`, or a directory
named `tools`.

## Install and use

```bash
pip install predictor_ops-4.0.0-py3-none-any.whl
predictor-ops validate jobs.json
predictor-ops provenance
predictor-ops run --config jobs.json --job example-collection
predictor-ops run --job-id adhoc --command python -m my_pipeline
```

Copy `jobs.example.json` and define operational policy outside application
code. Unknown fields, duplicate IDs and unsafe NUL arguments fail validation.
`FileJobConfigSource` and the HTTPS-only,
validated `HttpJobConfigSource` implement the same typed contract.

## Reliable operational execution (schema v2)

Schema v2 separates eight job types: sports and market collection, forecast
generation, shadow decision, execution, settlement, reconciliation and risk
monitoring. Only `EXECUTION` may set `capital_permission`; the runner never
interprets whether a forecast or hypothesis is profitable.

Every v2 job supplies an economic key composed of `domain`, `event_id`,
`market`, `decision_stage` and timezone-aware `logical_time`. Its SHA-256
identity is used for locking and durable attempt records. A completed operation
is not run twice. An execution attempt that finishes ambiguously is also held
and marked `requires_reconciliation` instead of being automatically submitted
again.

Execution jobs fail closed without a risk snapshot. Configurable kill-switch
limits and health flags stop new positions for daily loss, drawdown, settlement
health, internal/external balance divergence, degraded odds, unknown model or
dataset, latency, drift and correlated exposure. `retry_action()` maps order
states explicitly; API timeouts and unknown submissions require an external
state query, never blind retry.

`predictor-ops provenance` verifies the installed wheel against its `RECORD` and
prints deterministic JSON. It fails closed for editable, incomplete, or modified
installations. For development checkouts, `--source-root PATH` accepts only a clean
Git worktree with a resolvable commit. This command is suitable for an early CI
supply-chain gate and does not contact the network.

## Runtime contract

Every run writes `<runtime-root>/<job-id>/heartbeat.json` atomically and appends
a serialized, fsynced `events.jsonl` record. The deliberately local-only backend
uses an owned filesystem lock with stale/dead-owner recovery.

The runner preserves bounded combined stdout/stderr, timeout, whole child-tree
termination, periodic lease refresh/heartbeat, expected-artifact checks,
provenance supplied by the consumer, and graceful `SIGINT`/`SIGTERM` shutdown.
Secrets are collected from sensitive environment keys and redacted from
arguments, output, errors, provenance, heartbeats, JSONL and JSON logs.

`RunStatus` contains operational states only: `SUCCEEDED`, `PARTIAL`,
`DEGRADED`, `SOURCE_UNAVAILABLE`, `CONFIGURATION_ERROR`, `FAILED`, `SKIPPED`
and `WAITING`. Consumers may attach an opaque `scientific_state` to a job; the
runner persists and transports it without interpreting scientific semantics.

Logs are JSON on stdout. Install `predictor-ops[otel]` and call
`configure_otel()` to export OTLP traces; active trace/span IDs are included in
logs. The scheduler-independent runtime never imports the transitional
`predictor_ops.windows` adapter.

## Migration from 1.x

There is deliberately no permanent `tools` namespace shim: consumers migrate
from `tools.operational_runner` to `predictor_ops.run_job` or the installed CLI.
This repository does not edit or vendor consumers. Replace workspace-relative
health/task files with a validated jobs file supplied via deployment config.
Windows and Linux use their normal scheduler to invoke the same installed CLI.
Runtime, failure, monitoring and consumer ownership are consolidated in the
[Ops 4 contract](docs/OPERATIONS_CONTRACT.md).

## Development and release

```bash
uv sync --all-extras
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest --cov --cov-report=term-missing
uv build
```

CI tests Python 3.13 on Linux and Windows, Python 3.14 experimentally, builds a
wheel, installs it into a clean environment outside the checkout, runs the CLI,
The Docker image runs non-root;
mount `/var/lib/predictor-ops` writable while keeping the root filesystem
read-only.

Audit and transition records are versioned under `docs/`: the 149-row legacy
behavior matrix, removed-operations plan, compatibility guide, and observed
Windows/Linux/container evidence. Version 4 removes deprecated compatibility,
vendor-audit, hash-chain and Redis coordination surfaces.
