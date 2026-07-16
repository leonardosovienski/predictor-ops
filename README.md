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

`ecosystem_health.py` loads its task list from `HEALTH_TASKS.json`; callers may
pass a separate declarative file through `--tasks-file`. Run
`python tools/release_check.py` from the workspace root to verify workspace
tests, a clean isolated clone, and strict clone provenance before a release.

The clone-local test suite runs utility tests directly. Consumer entrypoint
contract tests run automatically only when sibling projects are present in the
workspace; they are explicitly skipped in an isolated clone.

See [PROVENANCE.md](PROVENANCE.md) for the artifact contract and release
fingerprint algorithm. `TOOLS_MANIFEST.json` describes the current release;
it is intentionally excluded from its own content hash, along with `VERSION`,
to avoid a circular release fingerprint.
