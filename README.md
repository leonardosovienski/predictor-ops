# predictor_ops

`predictor_ops` is an installable, domain-neutral operational runner for Python
3.13+. It runs on Linux, containers and Windows without relying on a workspace
layout, sibling repositories, `PYTHONPATH`, PowerShell, `pythonw`, or a directory
named `tools`.

## Install and use

```bash
pip install predictor_ops-2.0.1-py3-none-any.whl
predictor-ops validate jobs.json
predictor-ops run --config jobs.json --job example-collection
predictor-ops run --job-id adhoc --command python -m my_pipeline
```

Copy `jobs.example.json` and define operational policy outside application
code. Unknown fields, duplicate IDs, unsafe NUL arguments and incomplete Redis
configuration fail validation. `FileJobConfigSource` and the HTTPS-only,
validated `HttpJobConfigSource` implement the same typed contract.

## Runtime contract

Every run writes `<runtime-root>/<job-id>/heartbeat.json` atomically and appends
a serialized, fsynced `events.jsonl` audit record. The local backend uses an
owned filesystem lock with stale/dead-owner recovery. The optional Redis
backend (`pip install predictor-ops[redis]`) uses `SET NX PX` and transactional
compare-and-refresh/delete. Runtime files remain local even with Redis; Redis is
coordination, not an audit database.

The runner preserves bounded combined stdout/stderr, timeout, whole child-tree
termination, periodic lease refresh/heartbeat, expected-artifact checks,
provenance supplied by the consumer, and graceful `SIGINT`/`SIGTERM` shutdown.
Secrets are collected from sensitive environment keys and redacted from
arguments, output, errors, provenance, heartbeats, JSONL and JSON logs.

Operational states share one enum: `SUCCEEDED`, `PARTIAL`, `DEGRADED`,
`SOURCE_UNAVAILABLE`, `CONFIGURATION_ERROR`, `FAILED`, `SKIPPED`, `WAITING`,
`PENDING_SAMPLE`, `COLLECTION_ONLY`, `SHADOW`, `NO_GO`, and
`CLOSED_BY_HUMAN_DECISION`.

Logs are JSON on stdout. Install `predictor-ops[otel]` and call
`configure_otel()` to export OTLP traces; active trace/span IDs are included in
logs. The scheduler-independent runtime never imports the transitional
`predictor_ops.windows` adapter.

## Migration from 1.x

There is deliberately no permanent `tools` namespace shim: consumers migrate
from `tools.operational_runner` to `predictor_ops.run_job` or the installed CLI.
This repository does not edit or vendor consumers. Replace workspace-relative
health/task files with a validated jobs file supplied via deployment config.
Keep the old Windows installers only until each scheduled command invokes
`predictor-ops`; Linux should use its normal orchestrator (systemd, Kubernetes,
Nomad, cron, etc.).

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
and exercises Redis via a service container. The Docker image runs non-root;
mount `/var/lib/predictor-ops` writable while keeping the root filesystem
read-only.

Audit and transition records are versioned under `docs/`: the 149-row legacy
behavior matrix, removed-operations plan, compatibility guide, and observed
Windows/Linux/Redis/container evidence. Deprecated PowerShell rollback bridges
live only under `migration/windows` and are excluded from the wheel.
