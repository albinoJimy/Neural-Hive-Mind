# Spec Requirements Document

> Spec: Token Bucket Rate Limiting
> Created: 2026-04-05
> Status: Planning

## Overview

Implementar rate limiting hierárquico usando algoritmo Token Bucket no Orchestrator Dynamic para substituir a dependência do OPA em cenários simples de throttling, proporcionando controle granular de requisições por tenant, usuário e endpoint com suporte a bursts temporários e métricas Prometheus integradas.

## User Stories

### Proteção contra Sobrecarga

Como **operador de infraestrutura**, quero **limitar requisições por tenant**, para que **tenantes com uso excessivo não afetem a disponibilidade do sistema para outros**.

**Fluxo de trabalho:**
1. Administrador configura limites globais por tenant (ex: 1000 req/min para tenant-premium, 100 req/min para tenant-basic)
2. Sistema rastreia consumo de tokens em Redis (cluster-distributed)
3. Quando limite é excedido, requisições recebem HTTP 429 com header `Retry-After`
4. Métricas Prometheus registram throttling por tenant para alertas
5. Dashboards mostram consumo em tempo real por tenant

### Controle Granular por Endpoint

Como **desenvolvedor de API**, quero **limitar requisições por usuário e endpoint específico**, para que **operações custosas (como ML prediction) não sejam abusadas**.

**Fluxo de trabalho:**
1. Configuro limites específicos: `POST /api/v1/predict` tem limite de 10 req/min por usuário
2. Endpoint `GET /api/v1/health` mantém limite mais alto (100 req/min)
3. Sistema usa chave composta: `tenant:{tenant_id}:user:{user_id}:endpoint:{endpoint_path}`
4. Bursts de até 2x capacity são permitidos para lidar com retried requests
5. Logs estruturados registram throttling events com contexto completo

### Observabilidade e Debugging

Como **SRE**, quero **métricas detalhadas de rate limiting**, para que **possa identificar padrões de abuso e otimizar limites**.

**Fluxo de trabalho:**
1. Métricas Prometheus expõem: `rate_limit_requests_total{service,tenant,endpoint,status}`
2. Histogram `rate_limit_wait_duration_seconds` mostra latência adicionada
3. Gauge `rate_limit_tokens_remaining` permite visualização em tempo real
4. Logs estruturados contêm: tenant_id, user_id, endpoint, tokens_before/after
5. Dashboard Grafana consolida visualização de todos os tenants

## Spec Scope

1. **TokenBucketRateLimiter Hierárquico** - Integração do `neural_hive_resilience.TokenBucketRateLimiter` com backend Redis distribuído, suportando chaves compostas tenant > user > endpoint.

2. **Middleware FastAPI** - Implementação de middleware que intercepta requisições, extrai contexto de autenticação (tenant/user) e aplica rate limiting antes do handler.

3. **Configurações Dinâmicas** - Sistema de configurações via Pydantic Settings para definir limites globais, por tier (premium/basic) e por endpoint específico, com suporte a feature flags.

4. **Métricas Prometheus Integradas** - Exposição de métricas nativas (Counter, Histogram, Gauge) para requisições permitidas/denegadas, tempo de espera e tokens restantes.

5. **Burst Control** - Implementação de capacidade de burst (tokens excedendo refill_rate) para lidar com picos legítimos de tráfego e retried requests.

## Out of Scope

- Integração com OPA para políticas complexas de autorização (OPA continua usado para authorization, não rate limiting)
- Rate limiting baseado em IP address (considerado para próxima fase)
- Rate limiting distribuído cross-region (requer replicação Redis global)
- Interface administrativa para configuração de limites (via configuração/arquivos nesta fase)
- Rate limiting adaptativo baseado em load do sistema (considerado para roadmap futura)

## Expected Deliverable

1. **Middleware Funcional** - Requests ao Orchestrator Dynamic são interceptadas e limitadas conforme hierarquia tenant > user > endpoint, retornando HTTP 429 quando excedido.

2. **Métricas Prometheus Visíveis** - Endpoint `/metrics` expõe `rate_limit_*` com breakdown por service, tenant e endpoint, consultável via Prometheus.

3. **Testes E2E Passando** - Suíte de testes valida: limites tenant-level, user-level, endpoint-level, burst behavior, e reject com Retry-After header.

4. **Documentação de Deploy** - Guide contendo: variáveis de ambiente, exemplo de configuração por tier, e comandos para verificar métricas em produção.
