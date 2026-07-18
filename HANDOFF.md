# HANDOFF — tools/

Verificado em: 2026-07-18. Commit-base: `2732713` (branch `main`).

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

8 módulos, 100% stdlib (`pyproject.toml` declara `dependencies = []`),
**137 testes passed, 1 skipped** (verificado 2026-07-18, cache limpo).
`TOOLS_MANIFEST.json` em sincronia (`--check` retorna OK). API pública
documentada em `README.md`. Nenhum bug de código conhecido em aberto.

## 4. Branch, versão e commit-base

Branch única `main` (nunca houve branch paralela nesta camada).
`VERSION` = `1.3.0`. Commit-base desta verificação: `2732713`.

## 5. Estado Git

Working tree limpo. Nenhum remoto configurado — nada foi ou pode ser
publicado por push. Nenhuma tag criada nesta linha do tempo.

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
Resultado esperado: `137 passed, 1 skipped`. Ver `RUNBOOK_TESTS.md` para
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

Ver `PENDENCIAS_ABERTAS.md` seções 3 e 6 (OP-1, OP-3, OP-5, OP-6, DEBT-1,
DEBT-5) — nenhuma bloqueante, todas `CORRECTLY_DEFERRED` ou
`OPEN_DOCUMENTATION_GAP` de baixo risco.

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
