# Changelog

## 3.1.0

- Adiciona schema v2 com chave econômica canônica e oito tipos isolados de job.
- Restringe permissão de capital a jobs de execução e aplica kill switch
  fail-closed antes de abrir posições.
- Persiste claims idempotentes; tentativas de execução ambíguas exigem
  reconciliação e nunca são reenviadas automaticamente.
- Adiciona política explícita por estado de ordem e trilha append-only com IDs,
  hashes encadeados e validação da sequência operacional por ciclo.
- Mede o timeout a partir da criação do processo e tolera bloqueios transitórios
  do Windows sem abandonar a substituição atômica de arquivos.

## 3.0.0

- `RunStatus` agora contém apenas resultados e estados operacionais: `WAITING`,
  `SUCCEEDED`, `PARTIAL`, `DEGRADED`, `SOURCE_UNAVAILABLE`,
  `CONFIGURATION_ERROR`, `FAILED` e `SKIPPED`.
- `JobConfig.scientific_state` transporta uma string opaca definida e validada
  pelo consumidor/core. O runner persiste esse valor, mas nunca o interpreta.
- Removidos `OperationalState` e `consumer_status`. Migre decisões operacionais
  para `RunStatus`; migre `COLLECTION_ONLY`, `PENDING_SAMPLE`, `SHADOW`, `NO_GO`
  e `CLOSED_BY_HUMAN_DECISION` para `scientific_state`.
- Um processo pode, por exemplo, terminar com `run_status=SUCCEEDED` e transportar
  `scientific_state=COLLECTION_ONLY` simultaneamente.

## 2.0.1

- Deterministically reap every spawned job process and explicitly close all
  owned stdin, stdout and stderr streams after output draining completes.
- Join output-reader threads on success, failure, timeout, cancellation and
  exceptional setup paths; force cleanup of a still-running process tree.
- Treat output-reader failures as observable operational failures instead of
  silently losing the reader thread.
- Add ResourceWarning, repeated handle/file-descriptor, large output, reader
  failure and post-Popen exception regression coverage.

## 2.0.0

- Replace the workspace-bound `tools` tree with the installable `predictor_ops` package.
- Add the `predictor-ops` CLI and validated declarative job configuration.
- Add portable local and optional Redis coordination backends.
- Preserve owned locks, stale recovery, heartbeats, durable JSONL, bounded redacted output,
  timeouts, process-tree termination, provenance, and graceful shutdown.
- Add JSON/OpenTelemetry observability, Linux/container support, and a transitional Windows adapter.
- Remove sibling-repository contracts, workspace-root configuration, domain names, and PowerShell schedulers.

The 1.x flat-module API is intentionally not shipped in the wheel. Consumers must migrate explicitly;
there is no implicit `tools` namespace or `sys.path` shim.
