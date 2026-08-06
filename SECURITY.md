# Security Policy

## Supported Versions

O projeto está em desenvolvimento ativo. Correções de segurança são aplicadas
na branch `main` e na release estável mais recente.

| Versão | Suporte |
|---|---|
| `main` | ✅ |
| release mais recente | ✅ |
| versões anteriores | ❌ |

## Reporting a Vulnerability

Não abra uma issue pública para relatar vulnerabilidades.

Use o recurso **Private vulnerability reporting** disponível na aba
**Security** deste repositório.

Inclua, quando possível:

- descrição clara do problema;
- componente ou arquivo afetado;
- passos mínimos para reprodução;
- impacto esperado;
- ambiente e sistema operacional;
- evidências sanitizadas;
- possível correção ou mitigação.

Não publique segredos, tokens, credenciais, arquivos de runtime reais ou dados
obtidos durante os testes.

## Security Scope

Estão dentro do escopo:

- execução e encerramento de processos filhos;
- validação de comandos e argumentos;
- redaction de segredos em logs, erros, argumentos e proveniência;
- arquivos de heartbeat e auditoria;
- locks locais e recuperação de locks obsoletos;
- coordenação distribuída usando Redis;
- validação de configurações locais ou remotas;
- carregamento de configurações por HTTPS;
- proteção contra SSRF e URLs inseguras;
- limites de stdout e stderr;
- timeouts e encerramento da árvore de processos;
- tratamento de sinais;
- permissões e execução do container;
- imagem Docker;
- dependências Python;
- GitHub Actions e cadeia de fornecimento;
- wheel e demais artefatos de release.

Não estão dentro do escopo:

- indisponibilidade de serviços externos;
- uso de configurações explicitamente inseguras fora do contrato documentado;
- engenharia social;
- ataques que dependam de credenciais comprometidas fora do projeto;
- vulnerabilidades já corrigidas na branch `main`;
- falhas exclusivamente em versões antigas de dependências.

## Secrets

Nunca faça commit de:

- arquivos `.env`;
- tokens de API;
- senhas;
- credenciais Redis;
- credenciais de observabilidade;
- chaves privadas;
- configurações reais com valores sensíveis;
- arquivos de runtime contendo dados reais;
- logs não sanitizados.

Caso um segredo seja exposto, removê-lo do histórico não é suficiente. Ele deve
ser imediatamente revogado ou rotacionado no sistema correspondente.

## Safe Testing

Durante testes de segurança:

- utilize somente ambientes sob seu controle;
- utilize dados e credenciais fictícios;
- não ataque serviços de terceiros;
- não provoque indisponibilidade deliberada;
- não tente acessar dados de outros usuários;
- não execute comandos destrutivos;
- não preserve dados obtidos durante a investigação;
- pare o teste assim que houver evidência suficiente.

## Response Process

Após o recebimento de um relatório:

1. o problema será analisado;
2. impacto e severidade serão avaliados;
3. uma correção será preparada quando necessária;
4. segredos comprometidos deverão ser rotacionados;
5. testes de regressão serão adicionados quando aplicável;
6. uma nova versão poderá ser publicada;
7. a divulgação pública ocorrerá somente após a correção.

Não há garantia de prazo fixo de resposta, pois este é um projeto pessoal
mantido individualmente.
