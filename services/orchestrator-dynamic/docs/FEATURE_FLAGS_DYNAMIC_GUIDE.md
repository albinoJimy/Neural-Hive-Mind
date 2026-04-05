# Feature Flags Dinâmicas - Guia Completo

Guia para uso de Feature Flags Dinâmicas no Neural-Hive-Mind Orchestrator.

## Visão Geral

O sistema de Feature Flags Dinâmicas permite ativação/desativação de funcionalidades em tempo real sem necessidade de deploy, com suporte a:

- **Cache distribuído em Redis** para avaliações de baixa latência
- **Persistência em MongoDB** para configuração centralizada
- **Estratégias de rollout** (gradual, whitelist, canary)
- **Avaliação baseada em contexto** (tenant_id, namespace, risk_band)
- **Integração OPA** para políticas de autorização
- **Métricas Prometheus** para monitoramento

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Feature Flags Flow                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Admin UI / REST API                                                        │
│       │                                                                    │
│       ▼                                                                    │
│  FeatureFlagService ──┬─► MongoDB (configuração)                           │
│       │               │                                                     │
│       ▼               │                                                     │
│  FeatureFlagCache ────┘─► Redis (cache com TTL)                            │
│       │                                                                    │
│       ▼                                                                    │
│  RolloutStrategy Engine (avaliação baseada em contexto)                    │
│       │                                                                    │
│       ▼                                                                    │
│  Resultado (enabled/disabled)                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## API REST

### Endpoints

#### Criar Feature Flag

```http
POST /api/v1/feature-flags
Content-Type: application/json

{
  "flag_name": "enable_intelligent_scheduler",
  "description": "Habilita scheduler inteligente baseado em ML",
  "enabled": true,
  "rollout_strategy": "gradual",
  "rollout_config": {
    "percentage": 50,
    "whitelist": ["tenant-premium"],
    "namespaces": ["staging", "beta"],
    "canary_list": []
  },
  "created_by": "platform-team",
  "owner": "orchestrator-team",
  "tags": ["scheduler", "ml", "performance"]
}
```

#### Listar Feature Flags

```http
GET /api/v1/feature-flags?enabled=true&limit=100
```

#### Obter Feature Flag

```http
GET /api/v1/feature-flags/{flag_name}
```

#### Atualizar Feature Flag

```http
PUT /api/v1/feature-flags/{flag_name}
Content-Type: application/json

{
  "enabled": false,
  "rollout_config": {
    "percentage": 75
  }
}
```

#### Deletar Feature Flag

```http
DELETE /api/v1/feature-flags/{flag_name}
```

#### Toggle Feature Flag

```http
POST /api/v1/feature-flags/{flag_name}/toggle
```

#### Avaliar Feature Flag

```http
POST /api/v1/feature-flags/{flag_name}/evaluate
Content-Type: application/json

{
  "tenant_id": "tenant-123",
  "namespace": "staging",
  "risk_band": "high"
}
```

#### Batch Update

```http
POST /api/v1/feature-flags/batch-update
Content-Type: application/json

{
  "updates": [
    {"flag_name": "flag_1", "enabled": true},
    {"flag_name": "flag_2", "rollout_config": {"percentage": 75}}
  ]
}
```

## Estratégias de Rollout

### 1. Immediate (All)

Libera para todos os usuários sem restrições.

```json
{
  "rollout_strategy": "all",
  "rollout_config": {}
}
```

### 2. Gradual (Percentage)

Libera para X% dos usuários baseado em hash determinístico do tenant_id.

```json
{
  "rollout_strategy": "gradual",
  "rollout_config": {
    "percentage": 50
  }
}
```

**Características:**
- Hash determinístico: mesmo tenant sempre tem mesmo resultado
- Distribuição uniforme baseada em percentage
- Consistente entre requisições

### 3. Whitelist

Libera apenas para tenants específicos.

```json
{
  "rollout_strategy": "whitelist",
  "rollout_config": {
    "whitelist": ["tenant-premium", "tenant-beta"]
  }
}
```

### 4. Canary

Libera para usuários específicos (early adopters).

```json
{
  "rollout_strategy": "canary",
  "rollout_config": {
    "canary_list": ["user-123", "user-456"]
  }
}
```

### 5. Namespace Filter

Filtra por namespace (comum a todas estratégias).

```json
{
  "rollout_strategy": "gradual",
  "rollout_config": {
    "percentage": 50,
    "namespaces": ["staging", "beta"]
  }
}
```

## Condições de Avaliação

As condições são avaliadas com lógica AND (todas devem ser verdadeiras).

### Whitelist Condition

```python
{
  "type": "whitelist",
  "values": ["tenant-1", "tenant-2"],
  "attribute": "tenant_id"
}
```

### Percentage Condition

```python
{
  "type": "percentage",
  "percentage": 50,
  "attribute": "tenant_id"
}
```

### Attribute Condition

```python
{
  "type": "attribute",
  "attribute": "risk_band",
  "operator": "in",
  "value": ["critical", "high"]
}
```

**Operadores disponíveis:**
- `equals`: Valor é igual
- `not_equals`: Valor é diferente
- `in`: Valor está na lista
- `not_in`: Valor não está na lista
- `greater_than`: Valor é maior que
- `less_than`: Valor é menor que
- `greater_than_or_equal`: Valor é maior ou igual
- `less_than_or_equal`: Valor é menor ou igual

## Cache Redis

### Configuração

```python
# Cache TTL em segundos
CACHE_TTL = 60

# Prefixo de chaves
CACHE_KEY_PREFIX = "feature_flag:"
```

### Comportamento

1. **Cache Hit**: Flag retornada do Redis (< 1ms)
2. **Cache Miss**: Flag carregada do MongoDB e cache populada
3. **Invalidação**: Cache invalidado na atualização/deleção
4. **TTL**: Cache expira após 60 segundos (configurável)

### Chaves Redis

```
feature_flag:{flag_name}     → Flag individual
feature_flags:all             → Snapshot de todas (usado pelo OPA)
```

## Métricas Prometheus

### Métricas Disponíveis

| Métrica | Tipo | Labels | Descrição |
|---------|------|--------|-----------|
| `feature_flag_toggles_total` | Counter | flag_name, action, user | Total de toggles |
| `feature_flag_evaluation_duration_seconds` | Histogram | flag_name, result | Latência de avaliação |
| `feature_flag_cache_hits_total` | Counter | cache_level, flag_name | Cache hits |
| `feature_flag_cache_misses_total` | Counter | cache_level, flag_name | Cache misses |
| `feature_flag_evaluations_total` | Counter | flag_name, result | Total de avaliações |
| `feature_flag_rollout_percentage` | Gauge | flag_name, strategy | Percentual configurado |
| `feature_flags_active` | Gauge | owner, environment | Flags ativas |

### Queries Prometheus

**Hit Ratio do Cache:**
```promql
rate(feature_flag_cache_hits_total[5m]) /
(rate(feature_flag_cache_hits_total[5m]) + rate(feature_flag_cache_misses_total[5m]))
```

**Latência P95 de Avaliação:**
```promql
histogram_quantile(0.95, rate(feature_flag_evaluation_duration_seconds_bucket[5m]))
```

**Flags Ativas por Owner:**
```promql
feature_flags_active{owner="orchestrator-team"}
```

## Integração OPA

### Política OPA

```rego
package neuralhive.orchestrator.feature_flags

import data.external.flags

default is_enabled = false

is_enabled {
    flag_name := input.flag_name
    all_flags := flags.get_all()
    flag := all_flags[flag_name]

    flag.enabled == true
    eval_conditions(flag.conditions, input.context)
    eval_rollout_strategy(flag, input.context)
}
```

### Configuração data.external

```yaml
# OPA config.yaml
services:
  feature_flags:
    url: http://feature-flag-service:8080/api/v1/feature-flags
    headers:
      Accept:
        - application/json
```

## Exemplos de Uso

### Rollout Gradual em Fases

**Fase 1: 10% para staging**
```json
{
  "flag_name": "new_workflow_engine",
  "enabled": true,
  "rollout_strategy": "gradual",
  "rollout_config": {
    "percentage": 10,
    "namespaces": ["staging"]
  }
}
```

**Fase 2: 50% para staging**
```json
{
  "rollout_config": {
    "percentage": 50
  }
}
```

**Fase 3: 100% para production**
```json
{
  "rollout_strategy": "all",
  "rollout_config": {
    "namespaces": ["production", "staging"]
  }
}
```

### Rollback Emergencial

```bash
# Desabilitar flag imediatamente
curl -X POST http://feature-flag-service:8080/api/v1/feature-flags/enable_intelligent_scheduler/toggle
```

### A/B Testing

```json
{
  "flag_name": "experiment_ui_redesign",
  "enabled": true,
  "rollout_strategy": "gradual",
  "rollout_config": {
    "percentage": 50
  },
  "tags": ["ab-test", "ui"]
}
```

## Troubleshooting

### Flag não está sendo avaliada

1. Verificar se flag está `enabled: true`
2. Verificar se namespace do contexto está permitido
3. Verificar se tenant_id está na whitelist (se aplicável)
4. Verificar se condições de atributo estão satisfeitas
5. Verificar cache do Redis (pode estar desatualizado)

### Cache desatualizado

```bash
# Invalidar cache específico
redis-cli DEL "feature_flag:minha_flag"

# Limpar todo o cache de flags
redis-cli --scan --pattern "feature_flag:*" | xargs redis-cli DEL
```

### Métricas não aparecendo

1. Verificar se serviço está expondo `/metrics`
2. Verificar configuração do Prometheus scrape
3. Verificar labels das métricas (podem ter mudado)

### Alta latência de avaliação

1. Verificar hit ratio do cache (deve ser > 90%)
2. Verificar latência do Redis (deve ser < 5ms)
3. Verificar latência do MongoDB (se cache miss)
4. Aumentar TTL do cache se avaliação é consistente

## Runbook de Operação

### Criar Nova Feature Flag

1. Planejar estratégia de rollout
2. Criar flag via API com `enabled: false`
3. Configurar condições e rollout_config
4. Testar avaliação com contexto de teste
5. Habilitar flag quando pronto
6. Monitorar métricas de avaliação

### Atualizar Feature Flag

1. Avaliar impacto da mudança
2. Atualizar via API (PUT /toggle)
3. Cache é invalidado automaticamente
4. Verificar nova configuração via GET
5. Monitorar métricas após mudança

### Remover Feature Flag

1. Verificar se flag ainda está em uso
2. Remover referências no código
3. Deletar flag via API (DELETE)
4. Limpar cache do Redis se necessário

### Rollback de Feature Flag

1. **Toggle rápido**: `POST /{flag_name}/toggle`
2. **Atualização**: `PUT /{flag_name}` com `enabled: false`
3. **Remoção**: `DELETE /{flag_name}` (se bug crítico)

## Boas Práticas

1. **Nomear flags de forma descritiva**: `enable_intelligent_scheduler` não `flag1`
2. **Definir owner**: Responsável pela manutenção da flag
3. **Usar tags**: Para organizar e filtrar flags
4. **Documentar flag**: Descrição clara do propósito
5. **Planejar remoção**: Flags devem ser temporárias
6. **Monitorar métricas**: Hit ratio, latência, uso
7. **Testar antes de habilitar**: Avaliar com contexto de teste
8. **Rollout gradual**: Começar com porcentagem baixa
9. **Alertar em caso de falha**: Latência alta, cache miss
10. **Limpar flags zombies**: Remover flags não utilizadas

## Flags Padrão do Sistema

### Scheduler
- `enable_intelligent_scheduler`: Scheduler inteligente baseado em ML
- `enable_burst_capacity`: Capacidade burst para tenants premium
- `enable_predictive_allocation`: Alocação preditiva de recursos

### Workflow
- `enable_new_workflow_engine`: Novo motor de workflows
- `enable_parallel_execution`: Execução paralela de tarefas
- `enable_workflow_optimization`: Otimização automática de workflows

### ML
- `enable_ml_predictions": Predições de ML para scheduling
- `enable_drift_detection": Detecção de drift em modelos
- `enable_auto_retraining": Retreinamento automático de modelos

### Experimental
- `enable_experimental_features`: Features experimentais
- `enable_beta_features`: Features em beta
- `enable_canary_releases": Releases canary

## Variáveis de Ambiente

```bash
# Redis
REDIS_CLUSTER_NODES=redis-cluster:6379
REDIS_PASSWORD=***
REDIS_SSL_ENABLED=true
REDIS_CACHE_TTL_SECONDS=60

# MongoDB
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/feature_flags
MONGODB_DATABASE=feature_flags

# Serviço
FEATURE_FLAG_SERVICE_PORT=8080
LOG_LEVEL=INFO

# OPA
OPA_URL=http://opa:8181
OPA_POLICY_PATH=neuralhive/orchestrator/feature_flags
```

## Referências

- [OpenAPI Spec](http://feature-flag-service:8080/docs)
- [Prometheus Metrics](http://feature-flag-service:8080/metrics)
- [OPA Integration Guide](./OPA_INTEGRATION_GUIDE.md)
- [Feature Flags Original](./FEATURE_FLAGS_GUIDE.md)
