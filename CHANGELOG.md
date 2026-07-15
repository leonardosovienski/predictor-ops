# Changelog

## 1.1.0 — 2026-07-15

Adds native, validated tools provenance to operational heartbeats and JSONL
records. New fields are additive; lock, timeout, redaction, exit code, and
existing CLI behavior are unchanged. The release manifest and stdlib-only
provenance helper make the fingerprint reproducible in a clean clone.

## 1.0.0 — 2026-07-15

First versioned workspace release. Captures the existing operational runner,
redaction, health, vendor-byte-audit and core-provenance utilities without
changing their imports or consumer behavior.
