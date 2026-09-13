# Implantação local Ops 4.2.1 — 13/09/2026

**VALIDADO:** após a publicação e estabilização, o dono solicitou `implanta`. O pacote foi instalado nos ambientes locais de Cripto e Brasileirão. Esta etapa supera a observação anterior de Ops 4.2.0 no Cripto e ambiente ausente no Brasileirão. Não ativou jobs, serviços ou agendadores, nem utilizou APIs, credenciais ou bases operacionais como fixtures.

## Artefato

- Release: https://github.com/leonardosovienski/predictor-ops/releases/tag/v4.2.1
- Fonte imutável: `ddd91444282569ae8282e7c96e0ec372ef4e5144`.
- Wheel: `predictor_ops-4.2.1-py3-none-any.whl`.
- SHA256: `da4fa540703879669caba919521ec7d3c33734b5d57781122823df8817346f0e`.
- Cripto: download conferido pelo SHA256 antes da instalação. Brasileirão: URL e hash fixados no `uv.lock`, instalado com `--frozen`. Integridade RECORD estrita validada em ambos após instalação.

## Cripto

Destino: `C:/CRIPTO/pesquisa-20260909/.venv`, Python 3.13.14, consumidor 1.1.0 editável no checkout `59f6cf80d4a95153efa159c8b6e0d7d5e7f540ff`. Entrada existente `C:/CRIPTO/CRIPTO.cmd` preservada.

Comando: `C:/CRIPTO/CRIPTO.cmd uv pip install --python C:/CRIPTO/pesquisa-20260909/.venv/Scripts/python.exe --no-deps C:/CRIPTO/work/ops-deploy-20260913/predictor_ops-4.2.1-py3-none-any.whl`.

Comparação dos 81 pacotes antes/depois confirmou uma única mudança: Ops 4.2.0 para 4.2.1. `uv pip check` passou antes e depois. O executável existente respondeu `predictor-ops 4.2.1`.

Backup anterior: `C:/CRIPTO/work/ops-deploy-20260913/ops420-before.zip`, SHA256 `e518625344997a45854fe60f65f599b0ef05bc9bf32b7db90be63ec21da8111b`, 21 entradas; CRC e presença de módulo, metadata 4.2.0 e executável conferidos. Inclui arquivos do Ops, não o ambiente inteiro nem dados operacionais. Recuperação preferencial do pacote: instalar somente Ops 4.2.0 com `--no-deps` pela release preservada; o ZIP conserva os arquivos exatos anteriores para recuperação manual em manutenção. Nenhuma recuperação foi necessária.

## Brasileirão

Destino criado: `C:/BRASILEIRAO/brasileirao-predictor/.venv`, exatamente o caminho esperado pelo instalador versionado. Python próprio 3.13.15 em `C:/BRASILEIRAO/work/managed-python`; consumidor 0.2.0 instalado como wheel local não editável da fonte `0f69ba8a1da744eb4239b680fc0389f9dc631987`.

Comando no checkout: `uv sync --frozen --no-dev --no-editable --extra providers --extra kernel --python 3.13`. Cache, runtime gerenciado e temporários dentro de C:/BRASILEIRAO. Foram instalados 40 pacotes; `uv pip check` passou. Core 3.2.1 e Ops 4.2.1; executável `.venv/Scripts/predictor-ops.exe` respondeu 4.2.1. Não havia ambiente anterior a substituir. O ambiente novo pode permanecer preservado e sem uso em caso de reversão; nenhum caminho de agendador ou configuração privada foi alterado.

## Verificação após instalação

Todos os comandos de validação terminaram com código zero. `scripts/validate_installed.py` foi copiado para a área work de cada projeto e executado com seu Python operacional: identidade wheel estrita, origem site-packages, sucesso 0, parcial 2, falha 9, timeout 124, interrupção 130, heartbeats/eventos, liberação de locks e reutilização de artefato duas vezes. Os casos de falha são resultados esperados de fixtures, não falhas da implantação.

Cripto: probe chama os jobs reais com raiz sintética separada. Lock ocupado: Ops SKIPPED/0 e wrapper/3; watchdog com SQLite sintético saudável: SUCCEEDED/0; fixture em quarentena: FAILED/1. No ambiente operacional o consumidor é editável; o probe exige sua origem no checkout correto, e o Ops continua exigido em site-packages.

Brasileirão: probe instalado chama `sombra_diaria.main --check` duas vezes, com SQLite e diretórios sintéticos; Ops SUCCEEDED e payload AVAILABLE_NOT_EXECUTED. Nenhum percurso de aquisição foi ativado. A validação do ambiente novo foi executada em Python 3.13.15; não se atribui a ele retrospectivamente a CI anterior feita em outro patch Python.

Logs, probes, inventários de pacotes e saída da validação estão em `C:/CRIPTO/work/ops-deploy-20260913` e `C:/BRASILEIRAO/work/ops-deploy-20260913`. Recibos locais: `C:/CRIPTO/operacao/relatorios/OPS_DEPLOYMENT_20260913.md` e `C:/BRASILEIRAO/AUDITORIA/OPS_DEPLOYMENT_20260913.md`.

**Limites:** implantação das bibliotecas e ambiente local validada; execução operacional recorrente, instalação de agendamentos, homologação dos dados reais e validação econômica NÃO EXECUTADAS. CAIN, Core e Stocks não receberam alterações nesta implantação. Os testes de dependência existentes do Cripto passaram sem atualizar seus demais pacotes.
