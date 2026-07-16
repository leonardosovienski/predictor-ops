# Tools provenance contract

`operational_runner` 1.1.1 emits this additive object in every heartbeat and
terminal operational JSONL record:

```json
{
  "tools_provenance": {
    "version": "1.2.0",
    "commit": "Git HEAD of this tools checkout",
    "content_hash": "SHA-256 release fingerprint",
    "worktree_clean": true,
    "generated_at_utc": "UTC timestamp"
  }
}
```

Consumers may pass `--consumer-provenance-json` with a JSON object. It is
stored under `consumer_provenance` after the same structured redaction used by
the runner. It is intentionally opaque to tools: domain-specific metadata
such as project commit, predictor-core identity, and input hashes remains the
consumer's responsibility.

## Fail-closed behavior

Strict provenance is the default. The runner exits with its existing
configuration-error code (`3`) before launching the child when `VERSION`, Git
identity, manifest, included files, or release fingerprint cannot be
validated, or when the tools checkout is dirty. `--provenance-mode permissive`
is an explicit diagnostic compatibility mode: it preserves the actual computed
hash and `worktree_clean: false` instead of representing a dirty checkout as a
release artifact. A strict setup failure is still published as a terminal
`FAILED` heartbeat and JSONL event with `tools_provenance.status` equal to
`UNAVAILABLE`; it never launches the child or claims a validated release.

## Operational bounds

Run locks contain diagnostic ownership metadata and locks older than the
configurable `--lock-stale-after` interval (24 hours by default) may be
reclaimed. Timeout termination targets the runner-created process group/tree.
JSONL appends are serialized and fsynced. Child output is redacted while it is
drained and bounded by `--max-output-bytes` (10 MiB by default); discarded
output is never persisted. Terminal records add `output` (persisted-byte limit
and truncation state), `lock` (path and stale-lock recovery decision), and,
when relevant, `termination` (timeout process-tree termination diagnostics).

## Fingerprint

The algorithm name is `sha256-path-nul-content-nul-v1`. For each lexicographically
sorted, Git-tracked included file, it feeds its UTF-8 relative path, a NUL byte,
its raw Git-index blob, and a final NUL byte to SHA-256. This makes the
fingerprint invariant to checkout line-ending normalization; strict mode
separately rejects a dirty worktree. `VERSION` and
`TOOLS_MANIFEST.json` are excluded so the release metadata can state the hash
without self-reference. The manifest records the exact included file list,
excluded list, algorithm, version, and expected fingerprint. It contains no
secret values or absolute paths.
