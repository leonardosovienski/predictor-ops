# HANDOFF — tools/

## Estado compartilhado final — 2026-07-25

### COLLECTION_ONLY

As quatro tarefas operacionais usam exclusivamente `operational_runner.py`, com `--provenance-mode strict`, lock, timeout, redação de segredos, heartbeat atômico e event log:

- `brasileirao-archival-collection` — diário, `brasileirao-predictor`.
- `lol-archival-collection` — diário, `lol-predictor`.
- `cs-archival-collection` — horário, `cs-predictor`.
- `f1-archival-collection` — sexta/domingo, orientado pelo calendário.

Os artefatos de operação ficam fora dos repositórios em `%LOCALAPPDATA%\predictor-tools\runtime\<project>\<job_id>\` (logs, heartbeats, JSONL de eventos, locks, temporários e status estruturado). Cópias históricas preservadas antes da migração não são destinos das Actions atuais.

Os jobs encerrados permanecem **Disabled**: `lol-market-shadow`, `cs-market-shadow` e `f1-forward-snapshot`. Nenhuma Action COLLECTION_ONLY executa diretamente um script de consumidor.

### Estado operacional conhecido

- Brasileirão, LoL e F1 completaram a janela observacional anterior sem reabrir hipóteses, trials, gates ou closures.
- CS está bloqueado por dependência externa: o contrato exige o export esportivo oficial `data/collection_only/upstream_events.json`, mas não há produtor configurado no workspace. Não criar scraper, fonte paralela ou backfill.
- Arquivo CS ausente ou inválido produz `SOURCE_UNAVAILABLE`, com motivo sanitizado (`UPSTREAM_INPUT_MISSING` ou `UPSTREAM_INPUT_INVALID`), `accepted=0`, provenance e status no heartbeat/event log. JSON válido vazio produz `NO_UPSTREAM_EVENTS`.
- Beyond Market continua `CLOSED_BY_HUMAN_DECISION`; o hash permanece `B86023DEE82BA186FC9E89B1F6A1A153131ECDBA879B4D189C770A3D7A21A284`.

### Evidência mais recente

- `release_manifest.py --check`: OK (tools 1.3.4).
- Suíte tools: `141 passed, 1 skipped` com `PYTHONPATH=<workspace>;<workspace>/lol-predictor`.
- Vendor audit: Brasileirão, LoL, CS e F1 `IDENTICAL`, 46/46 cada.
- CS COLLECTION_ONLY: `tests/test_archival_collection.py` — `4 passed`.

Único bloqueio restante: disponibilizar, fora deste repositório e por decisão operacional, o export esportivo oficial do CS no contrato acima. Isso não é falha do runner nem autorização para reabrir o NO_GO científico.

Verificado em: 2026-07-22. Commit-base anterior: `2ed64e4` (`main`).

## 1. Identidade

Camada operacional canônica do ecossistema preditivo local. Não é um domínio
de previsão — é infraestrutura compartilhada: execução controlada, locks,
provenance, redação de segredos, manifests de release.

## 2. Finalidade

Prover a 5 consumidores vivos (brasileirao-predictor, cs-predictor,
f1-predictor, lol-predictor, previsao-cripto) primitivas operacionais
genéricas sem nenhuma lógica de domínio ou científica. Ver `README.md` para
a lista de não-objetivos completa.

## 3. Estado atual

8 módulos Python + 2 scripts PowerShell, 100% stdlib (`pyproject.toml` declara `dependencies = []`),
**139 testes passed, 1 skipped** (verificado 2026-07-20).
`TOOLS_MANIFEST.json` em sincronia (`--check` retorna OK). API pública
documentada em `README.md`. Nenhum bug de código conhecido em aberto.

## 4. Branch, versão e commit-base

Branch atual `main`. `VERSION` e `pyproject.toml` = `1.3.2`.

## 5. Estado Git

Antes desta manutenção, working tree limpo. Remoto `origin` configurado para
`tools-predictor`; nenhum push ou tag foi feito nesta manutenção.

## 6. Arquitetura

`operational_runner.py` (execução com lock/heartbeat/timeout/redação),
`secret_redaction.py` (redação determinística), `tools_provenance.py`
(fingerprint do próprio checkout), `core_provenance.py` (verifica se um
consumidor importa o vendor esperado do `predictor_core`),
`vendor_byte_audit.py` (auditoria byte-a-byte de vendors),
`release_manifest.py` (gerador/validador do `TOOLS_MANIFEST.json`),
`ecosystem_health.py` (leitura read-only do Task Scheduler),
`release_check.py` (release preflight: testes do workspace + clone isolado
+ sonda de provenance estrita).

## 7. Fluxo de execução

Consumidores importam via `from tools import X` (forma de pacote — a única
usada pelos 5 vivos hoje; a forma flat `import X` só é usada internamente
pelos próprios testes de `tools/`, ver `tests/test_import_split_brain.py`).
Não há instalação via `pip` — consumo é por `sys.path` compartilhado do
workspace-raiz, deliberadamente (ver `pyproject.toml`, comentário de
topo).

## 8. Integrações

Consumido por operational_runner nos 5 vivos (scripts agendados),
`tools_provenance`/`core_provenance` por cs-predictor e f1-predictor,
`secret_redaction` por brasileirao-predictor, previsao-cripto, e
internamente pelo próprio `operational_runner`. `tools/` não importa nada
de `predictor_core` nem de nenhum domínio.

## 9. Contratos

API pública estável documentada em `README.md`, seção "Public API":
`write_heartbeat`/`run`/`main` (operational_runner),
`collect_sensitive_values`/`safe_redact_text`/`safe_redact_mapping`
(secret_redaction), `collect_tools_provenance`/`ToolsProvenanceError`
(tools_provenance). Todo o resto é interno-na-prática (classificado, não
renomeado — ver README).

## 10. Decisões importantes

- **PredictionPoint/lógica científica nunca entra aqui** — decisão
  arquitetural permanente, reforçada em toda auditoria.
- **Sem instalação via pacote** — decisão consciente, não lacuna; nunca
  testado, então nunca declarado suportado (`pyproject.toml`).
- **Split-brain flat/package não foi eliminado, só travado com tripwire** —
  eliminar exigiria remover a forma flat que os próprios testes internos
  usam; avaliado como não valer o custo hoje (`FINAL_FORENSIC_REVIEW.md`
  seção 16).

## 11. Correções recentes

Ver `FINAL_FORENSIC_REVIEW.md` (revisão independente, commit `cca60f0`)
para verificação detalhada de cada uma:
- OP-1 fechado (1.3.1, 2026-07-19): perdedor do lock não escreve mais no
  heartbeat compartilhado — `SKIPPED` vai para o sidecar
  `skipped_heartbeat_path()` + event log; heartbeat principal é exclusivo do
  dono do lock.
- ReDoS em `secret_redaction.ASSIGNMENT` (backtracking catastrófico) —
  commit `9082c4e`.
- Race de heartbeat concorrente no Windows (`os.replace` retry) — commit
  `03393cb`.
- `release_check.py` ganhou 10 testes (não tinha nenhum) — commit `60b02a8`.
- Split-brain de imports travado por tripwire — commit `60b02a8`.
- `pyproject.toml` mínimo, honesto (sem instalação/licença fabricadas) —
  commits `9b689ea`, `60b02a8`.

## 12. Testes e validações

```
cd <workspace-raiz>
python -m pytest tools/ -q
```
Resultado esperado: `139 passed, 1 skipped`. Ver `RUNBOOK_TESTS.md` para
comandos completos de todos os repos e `RUNBOOK_RELEASE.md` para o release
preflight.

## 13. Automação

`tools/` em si não tem automação agendada — é biblioteca consumida por
automações de outros projetos (ver `RUNBOOK_CRYPTO_AUTOMATION.md` para o
único consumidor com tarefas do Windows Task Scheduler hoje).

## 14. Artefatos

`TOOLS_MANIFEST.json` (manifest de release, git-tracked). Nenhum artefato
científico — `tools/` não produz dado, só infraestrutura.

## 15. Segurança

`secret_redaction.py` é o mecanismo canônico de redação usado por todo o
ecossistema — ver `SECURITY.md` para a política completa. Nenhum incidente
de segurança pertence a `tools/` diretamente (o incidente conhecido é do
previsao-cripto, que CONSOME `tools.secret_redaction` — ver
`SECURITY_INCIDENT_SECRET_ROTATION.md`).

## 16. Pendências

Ver `PENDENCIAS_ABERTAS.md` seções 3 e 6 (OP-5, OP-6, DEBT-1, DEBT-5) —
nenhuma bloqueante, todas `CORRECTLY_DEFERRED`. OP-1 resolvido em 1.3.1;
OP-3 resolvido por `GLOSSARIO_STATUS.md` no workspace-raiz.

## 17. Riscos

Nenhum risco de código conhecido sem mitigação. Ver `PENDENCIAS_ABERTAS.md`
para a lista completa de riscos residuais documentados.

## 18. O que não fazer

Não adicionar lógica científica ou de domínio. Não adicionar dependência
externa sem necessidade comprovada e autorização. Não remover a forma flat
de import sem medir o custo de migrar os testes internos. Não declarar
suporte a `pip install` sem testá-lo primeiro.

## 19. Condições para reabrir decisões

Split-brain: reabre se um módulo ganhar estado mutável de módulo (o
tripwire detecta isso automaticamente, ver `tests/test_import_split_brain.py`).
Instalação via pacote: reabre se a topologia de deploy mudar (hoje é
sys.path compartilhado local).

## 20. Próxima ação legítima

Nenhuma pendente que exija ação imediata. Rodar `RUNBOOK_TESTS.md` antes de
qualquer mudança futura para confirmar baseline.
