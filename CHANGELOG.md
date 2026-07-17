# Changelog

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
