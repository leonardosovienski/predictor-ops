> **Implantação local em 13/09/2026:** Ops 4.2.1 instalado e validado nos ambientes de Cripto e Brasileirão. [Recibo, testes e recuperação](docs/DEPLOYMENT_20260913.md). Agendamentos não ativados.

> **Fechamento em 13/09/2026:** branches ativas do Ops consolidadas em `main`; oito remotas e três locais removidas com backups verificados. [Recibo e CI](docs/stabilization-20260912/REPORT.md#fechamento-git-e-ci--2026-09-13).

> **Ops 4.2.1 publicado e validado.** [Release](https://github.com/leonardosovienski/predictor-ops/releases/tag/v4.2.1), [evidências atuais e limites operacionais](docs/stabilization-20260912/REPORT.md). Fonte da release: `ddd91444282569ae8282e7c96e0ec372ef4e5144`. Os registros datados abaixo são históricos; instalação operacional não foi atualizada.

# HANDOFF — predictor-ops

<!-- DOC-SYNC-20260912 -->
> **Estado de publicação em 12/09/2026:** leia [a continuidade atual](PUBLICATION_STATUS_20260912.md). Branch `validation/retest-six-20260911`. Este projeto não recebeu alterações de código na remediação CAIN Supply. Esta rodada atualiza somente documentação; versões e validações anteriores conservam seu escopo. Afirmações anteriores de “sem push” descrevem a etapa histórica anterior à autorização.
<!-- /DOC-SYNC-20260912 -->


## Entrega arquitetural publicada — 11/09/2026

Versão **4.2.0** publicada: [release e artefatos](https://github.com/leonardosovienski/predictor-ops/releases/tag/v4.2.0). [CI de engenharia aprovada](https://github.com/leonardosovienski/predictor-ops/actions/runs/34628184138) para a fonte `e804ac8b5173156737e2212d9bd47cd3f2072700`. Consulte [ARCHITECTURE_IMPLEMENTATION.md](ARCHITECTURE_IMPLEMENTATION.md) para comportamento, migração e limites. Este registro atualiza a entrega de software; estados científicos e registros datados abaixo conservam sua autoridade e contexto histórico.

**Estado corrente: 2026-09-06 — versão 4.1.0.**

> Não instale `predictor_ops==4.0.0`: essa versão designa dois conteúdos
> diferentes conforme a origem (wheel `v4.0.0` sem o contrato de proveniência,
> `main` com ele). O 4.1.0 existe para desfazer essa ambiguidade — ver CHANGELOG.

`predictor-ops` é o runner operacional neutro do ecossistema. O schema v2 separa
coleta, forecast, shadow decision, execução, settlement, reconciliação e monitoramento
de risco. Somente jobs `EXECUTION` podem declarar `capital_permission=true`, sempre
com risk snapshot e kill switches; o runner não interpreta edge ou veredito científico.

Consumidores canônicos observados:

- Brasileirão e cripto declaram Ops 4.x;
- Stocks ainda não declara Ops;
- gates econômicos e sizing permanecem nos domínios;
- jobs dos gates atuais devem ser `SHADOW_DECISION`, nunca `EXECUTION`.

Validação local:

```bash
uv sync --frozen --extra dev
uv run python -m pytest
uv run ruff check .
uv run pyright
```

Não editar repositórios consumidores a partir deste projeto. Integrações são feitas
por configuração do consumidor e wheel publicado.


## Implementação arquitetural local — 2026-09-11

As alterações candidatas, seus limites, verificações e rollback estão em [ARCHITECTURE_IMPLEMENTATION.md](ARCHITECTURE_IMPLEMENTATION.md). Esta implementação local não publica releases, não atualiza automaticamente os consumidores e não altera os vereditos científicos históricos.
