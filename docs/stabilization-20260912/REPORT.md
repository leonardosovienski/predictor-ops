# Ops stabilization — 2026-09-12

Status: VALIDADO — 4.2.1 published, installed integrations passed and Git cleanup completed. Only main remains among active local and remote Ops branches. This report supersedes current-state claims in earlier dated handoffs without rewriting historical evidence.

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

## Delivery gates — historical pre-publication checkpoint

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

## Reconciliação semântica das branches — registro anterior à publicação

Além de git cherry, foram conferidos os destinos: CLI provenance e testes de integridade para expose-provenance; Dockerfile sem ferramentas vulneráveis para harden-runtime-image; piso de valores sensíveis e sua regressão para ecosystem-audit; registro histórico de Crypto 4.1 para auditoria-projetos. project-testing-validation contém versão/lock 4.1 e .gitattributes idêntico: a versão vigente é superior e o changelog 4.1 permanece. architecture/complete é ancestral. Os dois commits de validation/retest-six alteram somente documentação e integram a ancestralidade da entrega, mantendo o contexto histórico.

Nenhuma branch foi removida nesta fase. Publicação 4.2.1, verificações pós-publicação e limpeza aguardam os gates da revisão consolidada.

## Entrega publicada e conferida

- **Engenharia Ops: VALIDADO.** PR #23 integrado sem reescrever main. Fonte da release: `ddd91444282569ae8282e7c96e0ec372ef4e5144`; tag anotada `v4.2.1`. CI da main 34733345409 aprovou todos os cinco jobs (Linux 3.13/3.14, Windows 3.13, container e consumidores). Suíte: 87 testes em cada plataforma; cobertura Linux 80,41%, Windows 85,85%, mantendo o piso 80%. POSIX: 1 integração; Windows Scheduler: 2 integrações aprovadas na CI.
- **Publicação: VALIDADO.** Release 34733366187 aprovou build, publicação e os três jobs de verificação pós-publicação. Wheel `predictor_ops-4.2.1-py3-none-any.whl`, 26093 bytes, SHA256 `da4fa540703879669caba919521ec7d3c33734b5d57781122823df8817346f0e`. Sdist SHA256 `a9e5652c1b3177403f8302567c1e11dfe9db76220d70a027b11789c30fe254a5`. Download e jobs completos repetidos localmente com esse mesmo hash; origem site-packages e RECORD estrito validados.
- **Consumidores: VALIDADO nos percursos descritos.** Os probes locais Crypto e Brasileirão foram repetidos após instalar o wheel efetivamente publicado, com saída zero dos probes. Windows do launcher passivo independente: teste original copiado para ambiente isolado, 2 testes passaram, incluindo árvore real com timeout. Ele continua independente do Ops.
- **Pins e entregas mínimas nos consumidores:** Crypto main `59f6cf80d4a95153efa159c8b6e0d7d5e7f540ff`; Brasileirão main `0f69ba8a1da744eb4239b680fc0389f9dc631987`. Somente fontes de dependência, lock, CI/containers, expectativas de versão/hash e handoff foram atualizados. Nenhum módulo de domínio ou protocolo foi alterado. As versões dos consumidores continuam 1.1.0 e 0.2.0, pois não se publicou novo pacote consumidor; os pins de build/CI agora consomem a nova release Ops.
- **CI dos consumidores:** Crypto 34733559933 e integração instalada CAIN 34733559905 aprovadas em todos os jobs; quality 1505 passed e 7 skips existentes. Brasileirão 34733595774, 34733595772 e exportador CAIN 34733595771 aprovados; Python 3.13 teve 2090 passed, 1 skip exclusivo Windows, 30 deselected na primeira seleção e 30 testes de integração executados na seleção seguinte. Nenhum skip foi introduzido para aprovar esta atualização; a regressão Windows omitida no Linux passou localmente.
- **Ecosystem:** o verificador online comprovou uma divergência real, registry 4.2.0 versus main 4.2.1. Registries ativos foram reconciliados com o SHA/hash publicados e os pins de Crypto/Brasileirão. `check_ecosystem_drift.py` passou OFFLINE+ONLINE e `check_architecture_manifest.py` passou. A fonte atual do exportador inclui testes BundleV1; a CI inicialmente falhou por ausência de research_bundle no ambiente de transporte. Foi acrescentado o build/instalação do contrato já existente, sem retirar testes ou mudar seus critérios. Revisão: `96da7bfeb8493f0d80032ede7e9e02560f0eb953`; CI final é registrada no recibo de fechamento.
- **CAIN/Core/Stocks:** sem alteração por esta tarefa. Integrações CAIN dos consumidores passaram em ambientes sintéticos de CI; isso não é implantação no CAIN principal. O runtime principal e seu trabalho preexistente permaneceram intocados.

Receitas e resultados por job/step estão em `delivery-ci.json`; a aceitação do wheel publicado pelos plugins está em `published-consumer-contracts.json`; o download local e jobs completos em `published-wheel-validation.txt`. Recibos de CI usam SHAs, não inferem aprovação por nome da branch. Commits posteriores de documentação não alteram código/dependências do wheel da tag: a identidade distribuída continua vinculada a ddd9144, sem sobrescrever artefatos.

A consulta de operação permanece separada: Crypto usa Ops 4.2.0 na .venv operacional; Brasileirão sem ambiente configurado acessível; CAIN sem dependência Ops. Os checkouts de fonte dos consumidores foram avançados por fast-forward, mas isso não instalou bibliotecas neles.

Backup pré-limpeza: `C:/PREDICTORS/work/ops-final-20260912/ops-pre-cleanup.bundle`, SHA256 `d9ad942062704a80a59a27f44b0b2815513454e47731298e5502674bd82b3b3c`. Verificação, clone espelho em `recovery-final.git` e fsck passaram. Contém todas as 23 referências Git relevantes da fase de release, incluindo as pontas das branches e a tag nova. Os espelhos de recuperação mantêm referências históricas deliberadamente; não são checkouts de desenvolvimento a limpar.

## Fechamento Git e CI — 2026-09-13

**Consolidação: VALIDADO.** A main `7266a20583e08c6c6e121882c03c9c2bd17c5d4f` passou nos cinco jobs da CI [34734192456](https://github.com/leonardosovienski/predictor-ops/actions/runs/34734192456) e no CodeQL antes da limpeza. Ecosystem `96da7bfeb8493f0d80032ede7e9e02560f0eb953` passou nos onze jobs da CI [34734098243](https://github.com/leonardosovienski/ecosystem-predictor/actions/runs/34734098243) e na regressão de segurança do histórico [34734098235](https://github.com/leonardosovienski/ecosystem-predictor/actions/runs/34734098235). SHAs e jobs constam de `closing-ci.json`.

Oito branches remotas removidas: `agent/expose-provenance-verification`, `agent/harden-runtime-image`, `architecture/complete-20260911`, `claude/auditoria-projetos-esr8na`, `claude/predictor-ecosystem-audit-srpwl3`, `claude/project-testing-validation-6p6nt1`, `validation/retest-six-20260911` e `stabilization/final-20260912`. Três branches locais removidas com `git branch -d`: architecture, validation e stabilization acima. Cada ponta remota foi consultada novamente e comparada ao SHA revisado; a exclusão usou lease explícita no SHA para recusar mudanças concorrentes. Nenhuma main foi forçada; nenhuma tag/release foi removida.

`git-cleanup.json` registra ponta, decisão, comparação com a main, referência recuperável e saída zero de cada exclusão. A consulta posterior `git ls-remote --heads origin` retornou somente `refs/heads/main`; `git branch` retornou somente main. O worktree candidato continua preservado em HEAD destacado `ddd91444282569ae8282e7c96e0ec372ef4e5144`, assim como os dois bundles e espelhos históricos. Os espelhos conservam branches para recuperação, não como desenvolvimento ativo. Não se excluíram pastas nem trabalho local.

**Limite da repetição online:** o drift OFFLINE+ONLINE passou na reconciliação dos registries. Uma repetição posterior foi BLOQUEADA por HTTP 403 de rate limit na API GitHub ao consultar Core; isso não é novo desvio semântico nem aprovação dessa repetição. A checagem OFFLINE foi repetida no checkout final e passou. Os jobs de compatibilidade, plugins reais e seis wheels publicados do Ecosystem final também passaram.

O commit que publica este recibo altera apenas documentação. Sua CI deve ser consultada pelo SHA da main entregue; o resultado final e a igualdade local/remoto são conferidos após o push. A identidade imutável do pacote permanece na tag v4.2.1, fonte ddd9144 e hash integral acima. Operação continua sem implantação; nenhuma conclusão econômica ou científica decorre destes gates de engenharia.
