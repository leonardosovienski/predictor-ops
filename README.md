# tools

Shared, stdlib-first operational tooling for the quantitative workspace.

Contents: observable process runner, secret redaction, ecosystem health,
vendored-core byte audit, and runtime provenance verification. This is not a
published package and must be invoked from the workspace as documented by its
consumers. Python 3.13+ is supported; tests run with `python -m pytest tests -q`
from the workspace root so `tools` is importable.

Compatibility: the public CLI/module file names are stable in 1.x. Consumers
record the `VERSION`, Git commit, and content fingerprint in newly created
operational artifacts; historical artifacts are not rewritten.

The clone-local test suite runs utility tests directly. Consumer entrypoint
contract tests run automatically only when sibling projects are present in the
workspace; they are explicitly skipped in an isolated clone.
