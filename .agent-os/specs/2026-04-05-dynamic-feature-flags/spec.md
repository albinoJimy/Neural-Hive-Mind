# Spec Requirements Document

> Spec: Dynamic Feature Flags
> Created: 2026-04-05
> Status: Planning
> Epic: INFRA-003

## Overview

Implementar sistema de Feature Flags dinâmicas com cache em Redis, API REST para gestão, rollout gradual, e integração OPA completa, permitindo ativação/desativação de features em tempo real sem deploy, segmentação por namespace/tenant, e coleta de métricas de uso.

## User Stories

### Como Platform Engineer, quero gerenciar feature flags dinamicamente

Como Platform Engineer, quero uma API REST para criar, modificar e remover feature flags em tempo real, para que eu possa ativar novas funcionalidades ou desativar bugs sem precisar fazer um novo deploy.

**Workflow:**
1. Engenheiro acessa API POST /api/v1/feature-flags com configuração da flag
2. Flag é persistida em MongoDB e cache é invalidado
3. Próxima requisição ao OPA usa nova configuração via Redis
4. Dashboard mostra status atual de todas as flags

### Como DevOps Engineer, quero rollout gradual de features

Como DevOps Engineer, quero configurar rollout gradual baseado em percentagem de tráfego ou segmentos específicos (namespace, tenant, risk_band), para que possa validar novas features em produção antes de liberar para 100%.

**Workflow:**
1. Flag é criada com rollout_strategy="gradual"
2. Configurações: percentage=10, whitelist=["tenant-123"], namespaces=["staging"]
3. OPA avalia flag baseado em input context (tenant_id, namespace)
4. Métricas mostram % de requisições com flag ativa

### Como SRE, quero monitorar uso de feature flags

Como SRE, quero métricas em tempo real de quais flags estão ativas, % de tráfego afetado, e latência da avaliação, para que possa tomar decisões baseadas em dados sobre manter ou remover flags.

**Workflow:**
1. Prometheus scrape métricas do FeatureFlagService
2. Grafana dashboard mostra toggle count, evaluation latency
3. Alertas são disparados se latência > threshold
4. Relatórios semanais mostram flags "zombies" (ativas sem dono)

## Spec Scope

1. **FeatureFlagService** - Serviço centralizado para gestão de flags com CRUD completo
2. **Redis Cache Layer** - Cache distribuído para avaliações de flags com TTL configurável
3. **RolloutStrategy Engine** - Suporte a gradual rollout, whitelist/blacklist, canary
4. **REST API** - Endpoints para gestão (CRUD), batch updates, e métricas
5. **OPA Integration** - Policy updated para consultar Redis antes de avaliar regras
6. **Metrics & Observability** - Prometheus metrics para toggle count, evaluation latency, cache hit/miss
7. **Admin UI** - Interface web básica para gestão visual (dashboard)

## Out of Scope

- Alteração das lógicas de decisão existentes em feature_flags.rego
- Interface UI avançada (apenas dashboard básico)
- Integração com A/B testing frameworks externos
- Automação de limpeza de flags zombies (apenas alertas)
- Multi-region flag replication

## Expected Deliverable

1. FeatureFlagService com CRUD completo persistindo em MongoDB
2. Redis cache com TTL de 60s e invalidação automática
3. API REST com 10+ endpoints para gestão e consulta
4. OPA policy atualizada para consultar Redis via data.external
5. Prometheus metrics expostas em /metrics
6. Dashboard Grafana para visualização de flags e métricas
7. Testes unitários (80%+) e integração (E2E com docker-compose)
8. Documentação de API (OpenAPI) e guia de operação

## Tech Stack

- **Linguagem:** Python 3.12+
- **Framework:** FastAPI
- **Persistência:** MongoDB (configuração) + Redis (cache)
- **Integração:** OPA (REST API)
- **Observabilidade:** Prometheus + Grafana
- **Testes:** pytest + pytest-asyncio
- **Deploy:** Kubernetes (Helm chart)

## Dependencies

**Novas dependências:**
- `redis` (aioredis) - Cache distribuído
- `opentelemetry-instrumentation-fastapi` - Tracing

**Serviços existentes:**
- `orchestrator-dynamic` - Integração OPA
- `opa` - Policy evaluation

## References

- `policies/rego/orchestrator/feature_flags.rego` - Base OPA existente
- `services/orchestrator-dynamic/src/config/settings.py` - Configurações atuais
- `docs/FEATURE_FLAGS_GUIDE.md` - Documentação atual
