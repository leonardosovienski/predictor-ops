# Changelog

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
