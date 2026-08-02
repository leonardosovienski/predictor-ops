# Compatibility and deprecation guide

Version 2.0 intentionally does not ship a `tools` namespace. Migration is explicit and reversible.

| 1.x | 2.x |
|---|---|
| `from tools.operational_runner import run` | `from predictor_ops import run_job` with `JobConfig` |
| `from tools.secret_redaction import safe_redact_text` | `from predictor_ops.redaction import redact_text` |
| `from tools.secret_redaction import safe_redact_mapping` | `from predictor_ops.redaction import redact` |
| `from tools.tools_provenance import collect_tools_provenance` | `from predictor_ops.provenance import collect_provenance` |
| `python tools/operational_runner.py run --task NAME -- ...` | `predictor-ops run --config jobs.json --job NAME` |
| workspace-root `HEALTH_TASKS.json` | deployment-owned validated `JobsFile` |
| `--task` / `--project` | one stable `JobConfig.id`; project names belong in consumer provenance |
| `--cwd`, `--timeout`, `--max-output-bytes` | `cwd`, `timeout_seconds`, `max_output_bytes` in job config |
| `--consumer-provenance-json` | typed `provenance` object in job config |
| `--provenance-mode` | `provenance_mode` in job config |
| explicit heartbeat/log/lock paths | `runtime.root / job.id` contract |

Do not add the repository root to `PYTHONPATH`, create a local `tools` directory, or copy `predictor_ops` into a consumer. Install the wheel. Rollback consists of restoring the archived scheduler action and 1.3.6 environment; 2.x audit artifacts are additive and must not be rewritten or deleted.

Consumer migration is complete only after its local fixture and its own CI both pass against the built wheel. Until then, the relevant matrix rows remain `TRANSITIONAL` or `BLOCKED`.
