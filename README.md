# tools

Shared, stdlib-first operational tooling for the quantitative workspace.

Contents: observable process runner, secret redaction, ecosystem health,
vendored-core byte audit, and runtime provenance verification. This is not a
published package and must be invoked from the workspace as documented by its
consumers. Python 3.13+ is supported; tests run with `python -m pytest tests -q`
from the workspace root so `tools` is importable.

Compatibility: the public CLI/module file names are stable in 1.x. Since 1.1,
the runner natively writes a validated `tools_provenance` object to each new
heartbeat and operational JSONL record. Existing invocations remain valid;
new optional flags are `--provenance-mode {strict,permissive}` and
`--consumer-provenance-json '{...}'`. Strict is the default and rejects an
unidentifiable, dirty, or manifest-mismatched tools checkout. Permissive mode
must be explicitly requested and reports the real dirty state for diagnostic
compatibility. Historical artifacts are never rewritten.

Since 1.2.0, strict setup failures are published as terminal failed records,
stale run locks are recoverable after a configurable interval, timeouts end
the child process tree, JSONL appends are serialized and durable, and persisted
child output is bounded by the optional `--max-output-bytes` flag. Terminal
records also expose additive output, lock, and timeout-termination diagnostics.

Since 1.3.1, a run that loses the lock race no longer writes its `SKIPPED`
record to the shared heartbeat (which could overwrite the lock owner's state,
"last writer wins") — it writes to a `<name>.skipped.json` sidecar next to the
heartbeat and, as before, to the serialized JSONL event log. The main heartbeat
belongs exclusively to the lock owner.

`ecosystem_health.py` loads its task list from the workspace-level
`HEALTH_TASKS.json`; callers may pass a separate declarative file through
`--tasks-file`. Run
`python tools/release_check.py` from the workspace root to verify workspace
tests, a clean isolated clone, and strict clone provenance before a release.
The CI job installs test-only coverage tooling and requires at least 80% line
coverage; runtime remains stdlib-only.

The clone-local test suite runs utility tests directly. Consumer entrypoint
contract tests run automatically only when sibling projects are present in the
workspace; they are explicitly skipped in an isolated clone.

See [PROVENANCE.md](PROVENANCE.md) for the artifact contract and release
fingerprint algorithm. `TOOLS_MANIFEST.json` describes the current release;
it is intentionally excluded from its own content hash, along with `VERSION`,
to avoid a circular release fingerprint. See [HANDOFF.md](HANDOFF.md) for
operational continuity (current test count, recent hardening, pending
items).

## Public API

Consumers must import via the package form — `from tools import X` or
`python -m tools.X` — not the bare/flat form (`import X`) that `tools/`'s own
test suite uses internally. The two forms create independent module objects
in the same process (see `tests/test_import_split_brain.py`); package form is
the one every real consumer actually uses today, and the one this contract
covers.

Supported (stable within 1.x — may gain optional parameters, won't change
existing behavior without a MAJOR bump):

| Symbol | Module | Notes |
|---|---|---|
| `write_heartbeat`, `run`, `main` | `operational_runner` | CLI entrypoint (`run --task ... -- <command>`) and its heartbeat helper |
| `collect_sensitive_values`, `safe_redact_text`, `safe_redact_mapping` | `secret_redaction` | The redaction entrypoints; never raise — degrade to `REDACTION_FAILED` |
| `collect_tools_provenance`, `ToolsProvenanceError` | `tools_provenance` | Runtime self-identity check for a `tools/` checkout |

Everything else that's importable without a leading underscore
(`content_hash`, `redact_mapping`, `build_manifest`, `inspect_core_provenance`,
`audit_consumer`, `payload_entries`, `load_tasks`, and similar) is
**INTERNAL in practice**: no external consumer imports it today (confirmed by
grep across all 5 live consumers, 2026-07-17 audit), it has no compatibility
guarantee, and it may change shape without a version bump. It is not
underscore-prefixed only because these modules predate a formal public/
internal split; treat the absence of `_` as an implementation detail, not an
invitation. The CLIs (`core_provenance.py`, `vendor_byte_audit.py`,
`release_manifest.py`, `ecosystem_health.py`, `release_check.py`) are
supported as command-line tools (their `--flags` are the contract); their
Python-level functions are not.

## Monitoramento dos gates

`monitor_predictor_gates.ps1` produz um relatório somente-leitura para CS,
LoL, F1 e Brasileirão: agenda do Windows, resultado da última execução e
progresso dos gates de sombra. Estados `WAITING` e `PENDING_SAMPLE` não são
falhas; tarefas ausentes, falhas de execução e relatórios inválidos fazem o
monitor retornar código 1 para aparecer no Agendador. Ele nunca cria aposta,
altera critérios ou autoriza capital.

Para instalar a verificação recorrente a cada 30 minutos:

```powershell
powershell -File install_predictor_gate_monitor_task.ps1 -RunNow
```
