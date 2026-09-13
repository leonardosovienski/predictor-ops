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

## Resultados de execução do candidato

Estado por escopo, sem extrapolar para instalação operacional:

| Verificação | Ambiente / revisão | Comando / percurso | Resultado | Evidência |
|---|---|---|---|---|
| Regressões antes da correção | Windows / base 4392782 | pytest test_stabilization.py | FALHOU: lock, redação, memória e descendente | regressions-before.txt; descendant-before.txt |
| Runner, concorrência, lock, risco e reexecução | Windows / candidato | python -W error::ResourceWarning -m pytest --cov | VALIDADO: 87 testes; 85,92% cobertura local | log local final-source-tests.log; CI correspondente é autoridade para revisão final |
| Matriz e wheel instalado | CI d436fcaa535f787b8c3aef0754b33c3e867bb8cc | CI 34732862130, quatro jobs originais | VALIDADO: Linux 3.13/3.14, Windows 3.13, container | jobs 103658790852, 103658790866, 103658790884, 103658790973 |
| Registry real, sem mocks | Linux / mesmos fontes e SHAs fixados no script | scripts/validate_consumers.py -> checker vigente do Ecosystem | VALIDADO: três plugins distintos, contratos válidos, capital FORBIDDEN | consumer-contracts-candidate.json; job 103658790915 |
| Crypto instalado | Windows, Crypto 1.1.0 / Ops wheel candidato 4.2.1 | jobs.main(phase1) com lock próprio; jobs.main(watchdog) com SQLite sintético | VALIDADO: SKIPPED Ops 0 / wrapper 3; SUCCEEDED 0; FAILED 1 | C:/CRIPTO/work/ops-final-20260912/probe.py e integration-full.log |
| Brasileirão instalado | Windows, 0.2.0 / Ops wheel candidato 4.2.1 | sombra_diaria.main --check, duas execuções | VALIDADO: Ops SUCCEEDED, payload AVAILABLE_NOT_EXECUTED, heartbeat e eventos | C:/BRASILEIRAO/work/ops-final-20260912/probe.py e integration.log |
| Artefato reutilizável | wheel isolado | scripts/validate_installed.py, duas execuções | VALIDADO: reutilização sem alterar conteúdo | C:/PREDICTORS/work/ops-final-20260912/wheel-validation.log |
| CAIN -> Ops direto | CAIN a495bdd / instalação 0.4.8 | inspeção src/cain/research/bundles.py e dependências | NÃO APLICÁVEL: consumidor usa research_bundle.validate/transfer; não importa nem exige Ops | inventory.json; nenhuma base real usada como fixture |
| Stocks/Core -> Ops direto | revisões em inventory.json | dependências e imports runtime | NÃO APLICÁVEL: sem dependência direta; Stocks plugin exercitado no Linux | consumer-contracts-candidate.json |

O wheel Windows inicial (fonte 81395b0) teve SHA256 c8bb4626d5e2f3ae26d72890fa10dca60c54df9749a47a1442fa47f5083b0121. A correção posterior de tipos por plataforma exige testar o artefato efetivamente publicado; esse hash local não é atribuído à release.

As instalações locais de consumidores acima têm apenas as dependências do percurso exercitado. A instalação Linux dos três consumidores usa resolução integral das dependências declaradas e o checker original de proveniência e contratos. A primeira tentativa com uv foi recusada por ausência de hashes em direct_url.json; o ensaio passou com pip, que registra o SHA256 do arquivo. O checker não foi relaxado nem substituído.

## Observação operacional passiva

- Crypto: CRIPTO.cmd aponta para pesquisa-20260909/.venv, que continua com Ops **4.2.0**, confirmado por importlib.metadata. Não foi atualizado por esta tarefa.
- Brasileirão: o instalador versionado aponta para .venv/Scripts/predictor-ops.exe, mas esse ambiente não existe no checkout canônico acessível. Instalação operacional desse percurso: BLOQUEADO por ausência do ambiente configurado. O launcher passivo não importa Ops e não foi migrado.
- CAIN: instalação principal .venv contém cain-research 0.4.8, research-bundle 1.0.0 e snapshot 1.0.1, sem Ops. Alterações preexistentes no código e no teste de contexto recente foram preservadas.
- Consulta Get-ScheduledTask pelos nomes cripto/brasileirao/garimpo/cain não encontrou operações desses domínios. Isso não prova ausência de outros agendadores ou instalações fora do escopo acessível.
- O timeout do teste original do Windows deixou sua tarefa sintética predictor-ops-ci-5fdabbfce04848c3ac3fc1b74bf8dd34. A identidade foi confirmada por ação cmd.exe /c exit 7, timestamps coincidentes com o teste e trigger de 23:51:38. Somente essa tarefa de teste foi removida; a consulta posterior confirmou ausência.

Nenhuma implantação, ativação operacional, API paga, ordem, migração ou escrita em banco real foi executada.

## Segurança e gates do GitHub

A API da branch main confirmou protected=false e nenhum required_status_check. Mesmo assim todos os gates de CI existentes foram mantidos e continuam critérios desta entrega. Dependency Review e CodeQL passaram no PR. A análise automática adicional "Code scanning AI findings" falhou no serviço com HTTP 400 "The requested model is not supported"; não produziu revisão aprovada. É uma limitação externa registrada, não um alerta de código corrigido nem um gate dispensado para conseguir merge.

## Reconciliação semântica das branches

Além de git cherry, foram conferidos os destinos: CLI provenance e testes de integridade para expose-provenance; Dockerfile sem ferramentas vulneráveis para harden-runtime-image; piso de valores sensíveis e sua regressão para ecosystem-audit; registro histórico de Crypto 4.1 para auditoria-projetos. project-testing-validation contém versão/lock 4.1 e .gitattributes idêntico: a versão vigente é superior e o changelog 4.1 permanece. architecture/complete é ancestral. Os dois commits de validation/retest-six alteram somente documentação e integram a ancestralidade da entrega, mantendo o contexto histórico.

Nenhuma branch foi removida nesta fase. Publicação 4.2.1, verificações pós-publicação e limpeza aguardam os gates da revisão consolidada.
