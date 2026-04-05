# Feature Flags Guide

Guia para configuração e uso de feature flags no Neural-Hive-Mind Orchestrator.

## Visão Geral

O Neural-Hive-Mind possui dois sistemas de Feature Flags:

1. **Feature Flags Dinâmicas**: Sistema gerenciável via API com cache Redis
2. **Feature Flags Estáticas**: Configuradas via políticas OPA (legado)

### Feature Flags Dinâmicas (Novo)

Sistema gerenciável via API REST com:
- Cache distribuído em Redis para baixa latência
- Persistência em MongoDB para configuração centralizada
- API REST para gestão CRUD
- Estratégias de rollout (gradual, whitelist, canary)
- Integração com OPA para autorização
- Métricas Prometheus para monitoramento

**Documentação:** Ver [FEATURE_FLAGS_DYNAMIC_GUIDE.md](./FEATURE_FLAGS_DYNAMIC_GUIDE.md)

### Feature Flags Estáticas (Legado)

Controladas via políticas OPA em `policies/rego/orchestrator/feature_flags.rego`.

## Feature Flags Estáticas Disponíveis

- `enable_intelligent_scheduler`: habilita o scheduler inteligente baseado em ML.
- `enable_burst_capacity`: ativa burst capacity para tenants premium ou risk_band crítico.
- `enable_predictive_allocation`: habilita alocação preditiva quando a acurácia do modelo > 0.85.
- `enable_auto_scaling`: habilita auto-scaling baseado em profundidade de fila e janelas de negócio.
- `enable_experimental_features`: libera features experimentais para namespaces de desenvolvimento ou tenants early access.

## Feature Flags Dinâmicas - Guia Rápido

### API REST

```bash
# Listar todas as flags
curl http://feature-flag-service:8080/api/v1/feature-flags

# Criar nova flag
curl -X POST http://feature-flag-service:8080/api/v1/feature-flags \
  -H "Content-Type: application/json" \
  -d '{
    "flag_name": "minha_nova_feature",
    "description": "Descrição da feature",
    "enabled": true,
    "rollout_strategy": "gradual",
    "rollout_config": {"percentage": 50},
    "created_by": "meu-nome",
    "owner": "meu-time"
  }'

# Avaliar flag
curl -X POST http://feature-flag-service:8080/api/v1/feature-flags/minha_nova_feature/evaluate \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "tenant-123", "namespace": "staging"}'

# Toggle flag
curl -X POST http://feature-flag-service:8080/api/v1/feature-flags/minha_nova_feature/toggle
```

### Estratégias de Rollout

- **all**: Libera para todos (sem restrições)
- **gradual**: Libera para X% baseado em hash do tenant_id
- **whitelist**: Libera apenas para tenants específicos
- **canary**: Libera para usuários específicos

### Cache

As flags são cacheadas em Redis com TTL de 60 segundos. Ao atualizar uma flag, o cache é invalidado automaticamente.

## Como Configurar (Feature Flags Dinâmicas)

Usar a API REST para criar/atualizar flags:

```bash
# Atualizar rollout de 50% para 75%
curl -X PUT http://feature-flag-service:8080/api/v1/feature-flags/minha_feature \
  -H "Content-Type: application/json" \
  -d '{"rollout_config": {"percentage": 75}}'
```

Ou usar o Admin UI: `http://feature-flag-service:8080/admin/feature-flags`

## Como Configurar (Feature Flags Estáticas)

Edite `policies/rego/orchestrator/feature_flags.rego` para ajustar regras por namespace, tenant ou métricas.

Ajuste variáveis de entrada:
- `flags.intelligent_scheduler_enabled`, `flags.burst_capacity_enabled`
- `flags.predictive_allocation_enabled`, `flags.auto_scaling_enabled`
- `flags.scheduler_namespaces`, `flags.premium_tenants`
- `flags.scaling_threshold`, `flags.burst_threshold`

Teste localmente:
```bash
opa eval -d feature_flags.rego -i input.json "data.neuralhive.orchestrator.feature_flags.result"
```

## Exemplos de Uso

### Dinâmicas (Recomendado)

1. **Rollout Gradual em Fases**
   - Fase 1: 10% para staging
   - Fase 2: 50% para staging
   - Fase 3: 100% para production

2. **A/B Testing**
   - 50% dos usuários veem UI nova
   - Métricas comparadas entre grupos

3. **Rollback Emergencial**
   - Desabilitar feature instantaneamente via `/toggle`

### Estáticas

1. Habilitar intelligent scheduler apenas em `production`/`staging`.
2. Habilitar burst capacity somente para tenants premium com `current_load < burst_threshold`.
3. Habilitar predictive allocation quando `model_accuracy > 0.85` em namespaces `staging`/`beta`.
4. Habilitar auto-scaling apenas durante business hours com `queue_depth > scaling_threshold`.
5. Habilitar experimental features para tenants em early access ou namespaces `dev`/`staging`.

## Integração com Código

### Feature Flags Dinâmicas

As flags são avaliadas via API REST ou usando o `FeatureFlagService`:

```python
from src.services.feature_flag_service import FeatureFlagService

# Avaliar flag
service = FeatureFlagService(mongodb, redis)
result = await service.evaluate_flag(
    "minha_feature",
    context={"tenant_id": "tenant-123", "namespace": "staging"}
)
```

### Feature Flags Estáticas

Feature flags são avaliadas em `ticket_generation.allocate_resources` e retornadas em `policy_decisions['feature_flags']`.

Flags são usadas para decidir uso do `IntelligentScheduler` (ex.: `enable_intelligent_scheduler`) e capacidades como burst ou auto-scaling.

As decisões são anexadas em `ticket['metadata']['policy_decisions']['feature_flags']` para downstream.

## Monitoramento

### Métricas Dinâmicas

- `feature_flag_toggles_total`: Total de toggles
- `feature_flag_evaluation_duration_seconds`: Latência de avaliação
- `feature_flag_cache_hits_total`: Cache hits
- `feature_flag_cache_misses_total`: Cache misses
- `feature_flags_active`: Flags ativas

Acessar em: `http://feature-flag-service:8080/metrics`

### Dashboards

- **Feature Flags Overview**: Visão geral de flags ativas/inativas
- **Performance**: Latência de avaliação e cache hit ratio
- **Usage**: Top flags mais avaliadas

## Troubleshooting

### Flag Dinâmica Não Funciona

1. Verificar se flag está `enabled: true`
2. Verificar se namespace do contexto está permitido
3. Verificar cache Redis: `redis-cli GET "feature_flag:NOME_DA_FLAG"`
4. Verificar logs: `kubectl logs deployment/feature-flag-service`

### Flag Estática Não Funciona

1. Verificar política OPA: `opa eval -d feature_flags.rego`
2. Verificar input enviado para OPA
3. Verificar logs do OPA

## Migração de Estáticas para Dinâmicas

Para migrar flags estáticas para dinâmicas:

1. Criar flag dinâmica com mesma configuração
2. Atualizar código para usar API REST em vez de OPA
3. Validar comportamento idêntico
4. Remover configuração estática do OPA

## Referências

- [Feature Flags Dinâmicas - Guia Completo](./FEATURE_FLAGS_DYNAMIC_GUIDE.md)
- [Feature Flags - Runbook de Operação](./FEATURE_FLAGS_RUNBOOK.md)
- [OpenAPI Spec](http://feature-flag-service:8080/docs)
- [OPA Integration Guide](./OPA_INTEGRATION_GUIDE.md)
