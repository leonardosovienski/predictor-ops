# Post-modernization audit evidence

## Current checkout audit

Observed locally on 2026-08-26 at commit `c48b0a3` (`main`). This snapshot
supersedes the older suite counts below for the current checkout; historical
results remain preserved for release traceability.

| Gate | Environment | Result |
|---|---|---|
| Full v2 suite | Linux Python 3.14.7 | 80 passed; 87.87% total coverage; zero `ResourceWarning` |
| POSIX integration | Linux Python 3.14.7 | 1 passed |
| Redis real integration | Not configured locally | Not run; `PREDICTOR_OPS_TEST_REDIS_URL` and a real Redis service are required |
| Ruff and format | Linux Python 3.14.7 | passed |
| Pyright | Linux Python 3.14.7 | zero errors, warnings or informations |
| Pre-commit | Linux | passed |
| Lockfile and wheel | Linux | passed |
| Dependency audit | Linux | no known vulnerabilities |
| Secret scan | Linux | empty result set |
| Container smoke test | Docker | passed; non-root and read-only filesystem |
| Source provenance | Clean Git worktree | `VALIDATED` at `c48b0a3` |

No historical dataset, database, odds, model artifact, prediction ledger,
cache or report was present in the checkout. Therefore no predictive metric,
coverage estimate, confidence interval or economic-edge claim is supported by
this audit.

## Patch release 2.0.1: deterministic subprocess cleanup

Observed locally on 2026-08-02. `ResourceWarning` was promoted to an error in every pytest invocation.

| Gate | Environment | Result |
|---|---|---|
| Regression and cleanup paths | Windows Python 3.14.6 | 8 passed: success, nonzero exit, timeout, cancellation, exception, reader failure, repeated runs, and high-volume stdout/stderr |
| Full suite | Windows Python 3.14.6 | 68 passed; zero `ResourceWarning`; 86.71% coverage |
| Full suite | Windows Python 3.13.14 | 68 passed; zero `ResourceWarning` |
| Full suite | Linux Python 3.13.14 container | 68 passed; zero `ResourceWarning` |
| Signals | Linux container | real `SIGTERM` path passed; child terminated; test harness pipes explicitly drained and closed |
| Process tree | Windows | timeout and parent/child/grandchild forced termination passed |
| Redis | Redis 8.2.1 container | 3 passed with a real service |
| Repeated handles | Windows | 30 sequential `run_job` calls without process-handle accumulation |
| High-volume output | Windows | 4 MiB combined stdout/stderr drained without deadlock |
| Wheel and CLI | isolated sibling virtual environment | strict wheel provenance, version, and external job execution passed |
| Read-only container | Linux | image starts as non-root with `--read-only --tmpfs /tmp` |

The focused 2.0.1 subprocess-resource patch is `READY`. The historical repository-wide and consumer-owned blockers documented below are unchanged and remain outside this patch's scope.

Observed locally on 2026-08-01/02. These are executed results, not expected CI outcomes.

| Gate | Command / environment | Result |
|---|---|---|
| Historical inventory | `git grep -n -E '^def test_|^    def test_' HEAD -- tests` | 149 functions; 149 matrix rows; zero `BLOCKED` rows |
| Windows 3.14 suite + coverage | `python -m pytest --cov --cov-report=term-missing -q` | 60 passed; 87.02% total; runner 87%, provenance 89%, redaction 100%, Windows 100% |
| Windows 3.13 suite | `uv run --python 3.13 --all-extras python -m pytest -q` | 60 passed |
| Linux 3.13 suite | pinned `python:3.13.7-slim` test container with Git and all dev extras | 60 passed |
| Process tree, Windows | real parent → child → resistant grandchild, timeout and PID checks | passed; `taskkill /T /F` path |
| Process tree, Linux | same real tree in pinned Linux container | initially failed because resistant grandchild survived; implementation fixed to force the whole process group; passed after fix |
| Signals, Linux | real CLI subprocess plus `SIGTERM` | passed; exit 130 and child PID gone |
| Redis real | pinned Redis 8.2.1 container, DB 15, two spawned clients/processes | 3 passed: one winner, TTL/expiry/reacquire, ownership, stale owner refresh/release, key isolation, disconnect/reconnect |
| Windows Task Scheduler real | ephemeral unique task, removed by fixture finalizer | 2 passed: missing, present, never run, disabled, exit 7; discovered and fixed sentinel 267011 |
| Wheel | clean build, install in sibling venv, `python -I` strict provenance and CLI outside checkout | passed; strict wheel `RECORD` verification `VALIDATED`; CLI `SUCCEEDED` |
| Container | pinned Python 3.13.14 multi-stage build | passed; non-root image starts with `--read-only --tmpfs /tmp` |
| Dependency audit | `uv tool run pip-audit` | no known vulnerabilities |
| Secret scan | detect-secrets, tracked files, verified findings only | empty result set |
| Image scan | Trivy 0.66.0 against saved local image, HIGH/CRITICAL, ignore-unfixed | zero vulnerabilities |
| Ruff | `ruff check` and `ruff format --check` | passed |
| Pyright | standard mode, Python 3.13 | zero errors |

## Regressions found and fixed by the expanded audit

1. JSONL append lock disappeared between `FileExistsError`/`PermissionError` and `stat()` under Windows concurrency.
2. POSIX termination waited only for the leader; a resistant grandchild survived `SIGTERM`.
3. `os.kill(pid, 0)` was unsafe as a Windows liveness probe; `OpenProcess` is used instead.
4. Windows Task Scheduler sentinel `267011` was misclassified as a failure instead of never-run `WAITING`.
5. CI treated the PEP 621 `dev` extra as a nonexistent uv dependency group.
6. CLI test resolved `Scripts/Scripts` inside a uv environment.
7. Python 3.13 isolated build exposed unavailable Hatchling and a virtualenv/distlib incompatibility; Hatchling is an explicit dev dependency and the byte-tamper test uses a no-isolation build.

## Remaining formal blockers

- The GitHub-hosted workflow itself has not run for this unpushed worktree. Local Windows, Linux, Redis and container equivalents are green, but Actions/SBOM artifact publication remains unobserved.
- Consumer-owned repositories were not edited or executed by instruction. Local fixture contracts are green, but each consumer must still install the built wheel and pass its own CI before its transitional adapter and retained PowerShell rollback assets can be removed.
- Transitional PowerShell monitors/installers are isolated under `migration/windows` and excluded from the wheel. They remain rollback bridges, not approved new-deployment mechanisms.

Accordingly, repository readiness is `READY_WITH_BLOCKERS`, not `READY`.
