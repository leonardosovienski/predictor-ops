# Tools provenance contract

`operational_runner` 1.1 emits this additive object in every heartbeat and
terminal operational JSONL record:

```json
{
  "tools_provenance": {
    "version": "1.1.0",
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
release artifact.

## Fingerprint

The algorithm name is `sha256-path-nul-content-nul-v1`. For each lexicographically
sorted, Git-tracked included file, it feeds its UTF-8 relative path, a NUL byte,
its raw bytes, and a final NUL byte to SHA-256. `VERSION` and
`TOOLS_MANIFEST.json` are excluded so the release metadata can state the hash
without self-reference. The manifest records the exact included file list,
excluded list, algorithm, version, and expected fingerprint. It contains no
secret values or absolute paths.
