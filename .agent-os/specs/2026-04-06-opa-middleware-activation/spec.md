# Spec Requirements Document

> Spec: Middleware OPA Authorization Activation
> Created: 2026-04-06
> Status: Planning
> Epic: INFRA-005

## Overview

Ativar o `OPAAuthorizationMiddleware` já implementado na biblioteca `neural_hive_opa` no serviço `orchestrator-dynamic`, adicionando autorização centralizada via OPA para todas as requisições HTTP da API REST, complementando a validação OPA já existente nas activities Temporal.

## User Stories

### Como Platform Engineer, quero autorização centralizada via OPA

Como Platform Engineer, quero ativar o middleware de autorização OPA na API HTTP do orchestrator-dynamic, para que todas as requisições sejam validadas contra políticas centralizadas antes de serem processadas.

**Workflow:**
1. Middleware intercepta todas as requisições HTTP (exceto paths públicos)
2. Extrai contexto de autenticação (user_id, tenant_id, role) dos headers
3. Consulta OPA com input contendo method, path, headers, body
4. Permite ou nega acesso baseado na decisão do OPA
5. Cache de decisões por 5 minutos para reduzir latência

### Como Security Architect, quero fail-closed por padrão

Como Security Architect, quero que o sistema negue acesso quando OPA estiver indisponível, para garantir que nenhuma requisição não autorizada passe por falha do serviço de políticas.

**Workflow:**
1. Configuração `fail_open=False` (padrão)
2. Se OPA retornar erro ou timeout, request é negado com HTTP 503
3. Métrica `opa_middleware_unavailable` incrementada
4. Alerta criado se taxa de falhas > 10%

## Spec Scope

1. **Ativação do Middleware** — Adicionar `OPAAuthorizationMiddleware` em `main.py` com configuração apropriada
2. **Configurações** — Adicionar campos em `settings.py` para `enable_opa_authorization`, `opa_authorization_policy_path`, etc.
3. **Política OPA HTTP** — Criar política `neuralhive/orchestrator/authz` para autorização de endpoints REST
4. **Testes de Integração** — Validar autorização, negação, cache, circuit breaker
5. **Documentação** — Atualizar README e guias de operação

## Out of Scope

- Modificação das políticas OPA existentes usadas nas activities Temporal
- Implementação de autenticação JWT (considerado middleware separado)
- Rate limiting baseado em usuário (já coberto por Token Bucket)
- Autorização granular por recurso (apenas endpoint-level nesta fase)

## Expected Deliverable

1. Middleware ativo em `main.py` com flag `enable_opa_authorization`
2. Configurações em `settings.py` com defaults seguros
3. Política OPA `neuralhive/orchestrator/authz` implementada
4. Testes validando: allow, deny, cache hit, circuit breaker, fail-closed
5. Métricas Prometheus expostas: `opa_middleware_decisions`, `opa_middleware_latency`, `opa_middleware_cache_hits`
6. Documentação de deploy e operação

## Tech Stack

- **Linguagem:** Python 3.12+
- **Biblioteca:** `neural_hive_opa` (já implementada)
- **Framework:** FastAPI (middleware já existe)
- **Policy Engine:** OPA (Open Policy Agent)
- **Observabilidade:** Prometheus metrics

## Dependencies

**Bibliotecas existentes:**
- `neural_hive_opa` - Middleware e cliente OPA com circuit breaker
- `orchestrator-dynamic` - Serviço onde middleware será ativado

**Serviços existentes:**
- `opa` - Policy Engine em execução no cluster

## References

- `libraries/python/neural_hive_opa/src/neural_hive_opa/middleware.py` - Middleware implementado
- `services/orchestrator-dynamic/src/main.py` - Ponto de ativação
- `services/orchestrator-dynamic/src/config/settings.py` - Configurações
- `policies/rego/orchestrator/feature_flags.rego` - Exemplo de políticas
