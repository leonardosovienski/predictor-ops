# Changelog

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
