# Ops stabilization — 2026-09-12

Status: candidate 4.2.1; final CI, release, installed-consumer validation and Git cleanup are pending. This report supersedes current-state claims in earlier dated handoffs without rewriting historical evidence.

## Base and preservation

Main observed: `0aa803fcaf0656061d9e251a85cbf0cf55071066`. Initial clean checkout: `4392782b231364a9394dae04a57cad2c0bf73ef1`, branch `validation/retest-six-20260911`. Eight remote branches observed. Full metadata is in inventory.json and branches.json.

Recoverable Git backup: `C:/PREDICTORS/work/ops-final-20260912/ops-before.bundle`, SHA256 `54b654df24ab2d80461ecb75a8e67d7a8cc2ed739ee5fc4d55e01146506dad29`. `git bundle verify`, mirror clone to `recovery.git`, and `git fsck --full` succeeded. Initial Ops tracked/untracked status was clean; ignored caches were left in place, not included in the Git backup. No runtime databases or operational installation were changed. The separate candidate worktree preserves the original checkout. Scope of discovery: canonical roots on C:, their visible clones and Git worktree inventories; no claim about inaccessible disks.

## Baseline

Windows, CPython 3.13.14, frozen uv.lock, uv sync --frozen --all-extras. Ruff check, format check, Pyright, build passed. Existing suite: 76 passed, 88.07% coverage (80% gate). Windows scheduler integration: first test passed, next test timed out at 30 seconds; FALHOU in this environment, not waived. Local WSL unavailable and Docker not found. Linux 3.13/3.14 and container gates require CI. Original CI matrix and security gates retained; installed wheel and container jobs strengthened beyond --version. Branch protection read via connector returned HTTP 403; protections are not bypassed.

## Reproduced defects and corrections

Contract: docs/OPERATIONS_CONTRACT.md and README runtime guarantees.

- Lock: injected preflight persistence error left the owned lease acquired. Outer finally now spans all work after acquisition. Regression failed before correction.
- Secrets: kill-switch SKIPPED persisted synthetic environment secret in input_reference/scientific_state. Redact the base, previous-attempt metadata, every heartbeat and persisted job identity. Regression failed before correction.
- Capture: 8 MiB newline-free fixture with 1 KiB retention allocated 16,777,290 bytes. Read bounded chunks, retain only configured capacity plus secret lookahead, redact before exposing output. Memory regression failed before correction; capture-boundary secret test included.
- Descendants: parent exit with inherited stdout took 12.43 seconds despite a completed command. On Windows, suspend the child until assigned to an owned Job Object; terminate owned descendants and close handles at completion. On POSIX retain the owned process-group ID after leader exit. Regression checks bounded completion and survival of an unrelated synthetic process.

Windows design references: https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects and https://learn.microsoft.com/en-us/windows/win32/toolhelp/snapshots-of-the-system . Controlled process tests do not exercise economic operations.

Existing artifact behavior remains an existence contract; permitted reuse is tested without forcing timestamp changes. Domain validity/identity must be checked by the consumer. Added risk tests prove no file effect for absent/incomplete/stale/future risk and incomplete limits; ambiguous execution preserves reconciliation bytes and refuses a second effect.

## Integration boundaries under verification

Crypto: real GarimpoInvestimentos.jobs calls Ops, SUCCEEDED -> 0, PARTIAL -> 1, all remaining statuses -> exit_code or 3. SKIPPED with Ops zero therefore means wrapper 3. Preserve this fail-closed scheduler signal until consumer policy explicitly changes it.

Brasileirao: dependency and sombra_diaria operational CLI use Ops; run_passive_task is a separate allowlisted subprocess launcher and remains independent. Installed dependency alone does not prove all jobs use Ops.

CAIN, Core and Stocks: no direct Ops import observed in inspected runtime source/dependency configuration. CAIN consumes domain research bundles independently; no artificial Ops dependency introduced. Ecosystem supplies registry/contracts and installed distribution checks; no gateway or scheduler recreated.

Operational installation: not updated. Isolated package validation is not deployment, scientific validation or authorization to use capital.

## Delivery gates

Do not delete branches while any mandatory final gate or required published-artifact validation remains pending. No branch has been removed. Git main publication and exact SHA verification remain pending until candidate validation.
