# HANDOFF — predictor-ops

**Estado corrente: 2026-09-01 — versão 4.0.0.**

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
