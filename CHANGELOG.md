# Changelog

## 4.1.0

- Adiciona o contrato de proveniência operacional: `JobConfig` aceita
  `config_version`, `input_reference`, `output_reference`, `retry_count` e
  `host_or_environment`, e o registro de auditoria do runner passa a emitir esses
  campos (com `host_or_environment` derivado do host quando não declarado).
- Todos os campos são opcionais e têm padrão; jobs escritos para 4.0.0 continuam
  válidos sem alteração.

Este bump corrige uma divergência de identidade: as mudanças acima já estavam em
`main` sob a versão `4.0.0`, a mesma da wheel publicada em
`v4.0.0` — que não as contém. `predictor-ops==4.0.0` passava a designar dois
conteúdos diferentes conforme a origem da instalação.

## 4.0.0

- **Breaking:** reduz o pacote ao runtime operacional genérico e remove a camada de
  compatibilidade 1.x, auditoria de vendors, backend Redis e assets PowerShell de
  migração. O backend suportado nesta linha é local; scheduling permanece externo.
- Remove `monitor_predictor_gates.ps1`, `monitor_task_health.ps1` e seus instaladores.
  A saúde de execução/heartbeat fica nos contratos portáveis `predictor_ops.health`
  e `predictor_ops.windows`; interpretação e promoção de gates científicos pertencem
  aos repositórios de domínio e não ao Ops.
- Remove consumers e nomes de domínio do runtime. Jobs passam a usar apenas identidade
  econômica neutra, locking local, heartbeat, log durável e idempotência.
- Mantém kill-switch fail-closed para jobs `EXECUTION`, reconciliação obrigatória para
  resultado ambíguo, término de árvore de processos e proveniência da wheel/código.
- Atualiza o mínimo para Python 3.13 e restringe `RuntimeConfig.backend` a `local`.

Consumidores devem instalar a wheel 4.0.0, configurar cron/Task Scheduler externamente,
observar saúde operacional pela API tipada e manter a avaliação científica no domínio.

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
