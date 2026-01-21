# Configuracao de Gradual Rollout

## Visao Geral

O gradual rollout permite promover modelos ML de forma progressiva, validando metricas em cada estagio antes de avancar. Isso reduz o risco de degradacao em producao.

## Configuracao

### Variaveis de Ambiente

```bash
# Habilitar gradual rollout (default: true)
ML_GRADUAL_ROLLOUT_ENABLED=true

# Estagios de rollout (percentuais de trafego)
ML_ROLLOUT_STAGES=0.25,0.50,0.75,1.0

# Duracao de cada checkpoint em minutos (default: 30)
ML_CHECKPOINT_DURATION_MINUTES=30

# Threshold de aumento de MAE para rollback (default: 20%)
ML_CHECKPOINT_MAE_THRESHOLD_PCT=20.0

# Threshold de error rate para rollback (default: 0.1%)
ML_CHECKPOINT_ERROR_RATE_THRESHOLD=0.001
```

### Arquivo de Configuracao (config.yaml)

```yaml
ml:
  gradual_rollout:
    enabled: true
    stages: [0.25, 0.50, 0.75, 1.0]
    checkpoint_duration_minutes: 30
    checkpoint_mae_threshold_pct: 20.0
    checkpoint_error_rate_threshold: 0.001
```

## Fluxo de Rollout

```
                    +-------------+
                    |  Validation |
                    +------+------+
                           |
                           v
                    +-------------+
                    | Shadow Mode |
                    +------+------+
                           |
                           v
                    +-------------+
                    |   Canary    |
                    +------+------+
                           |
           +---------------+---------------+
           |                               |
           v                               v
    +-------------+                 +-------------+
    |  Stage 25%  |---Checkpoint--->|  Stage 50%  |
    +------+------+     OK          +------+------+
           |                               |
           |                               |
           v                               v
    +-------------+                 +-------------+
    |  Stage 75%  |---Checkpoint--->| Production  |
    +------+------+     OK          +-------------+
           |
           | Degradacao
           v
    +-------------+
    | Rolled Back |
    +-------------+
```

## Criterios de Degradacao

Em cada checkpoint, o sistema verifica:

1. **MAE (Mean Absolute Error)**
   - Aumento > 20% em relacao ao baseline -> Rollback

2. **Error Rate**
   - Taxa de erro > 0.1% -> Rollback

3. **Sample Count**
   - Minimo de 10 amostras para validacao

## Metricas Prometheus

- `neural_hive_rollout_stage`: Estagio atual (1-4)
- `neural_hive_rollout_traffic_pct`: Percentual de trafego atual
- `neural_hive_rollout_checkpoint_total`: Total de checkpoints executados
- `neural_hive_rollout_degradation_total`: Total de degradacoes detectadas

### Exemplos de Queries PromQL

```promql
# Estagio atual de rollout por modelo
neural_hive_rollout_stage{model_name="duration-predictor"}

# Percentual de trafego atual
neural_hive_rollout_traffic_pct{model_name="duration-predictor"}

# Taxa de checkpoints bem-sucedidos
sum(rate(neural_hive_rollout_checkpoint_total{status="success"}[1h])) /
sum(rate(neural_hive_rollout_checkpoint_total[1h]))

# Degradacoes por motivo
sum by (reason) (rate(neural_hive_rollout_degradation_total[24h]))
```

## Desabilitar Gradual Rollout

Para desabilitar e usar promocao direta (comportamento legado):

```bash
ML_GRADUAL_ROLLOUT_ENABLED=false
```

Ou via API:

```python
await promotion_manager.promote_model(
    model_name="duration_predictor",
    version="v2.0",
    config_overrides={'gradual_rollout_enabled': False}
)
```

## Troubleshooting

### Rollout Travado em Estagio

**Sintoma:** Rollout nao avanca para proximo estagio

**Diagnostico:**
```bash
# Verificar metricas de checkpoint
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic | grep rollout_checkpoint

# Verificar continuous validator
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic | grep continuous_validator
```

**Resolucao:**
- Verificar se `continuous_validator` esta ativo
- Verificar se ha amostras suficientes (min: 10)

### Rollback Frequente

**Sintoma:** Rollback automatico em todos os estagios

**Diagnostico:**
```bash
# Verificar threshold de MAE
echo $ML_CHECKPOINT_MAE_THRESHOLD_PCT

# Verificar metricas baseline vs checkpoint
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic | grep rollout_mae_degradation
```

**Resolucao:**
- Aumentar threshold de MAE (ex: 30%)
- Aumentar duracao de checkpoint para coletar mais amostras
- Revisar qualidade do modelo candidato

### Metricas Nao Aparecendo no Prometheus

**Sintoma:** Metricas `neural_hive_rollout_*` nao aparecem

**Diagnostico:**
```bash
# Verificar se rollout esta ativo
curl localhost:9090/api/v1/query?query=neural_hive_rollout_stage

# Verificar se promocao foi iniciada
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic | grep starting_gradual_rollout
```

**Resolucao:**
- Iniciar uma promocao de modelo
- Verificar se ServiceMonitor esta configurado corretamente

## Integracao com Alerting

### Alertas Recomendados

```yaml
groups:
  - name: ml-rollout
    rules:
      - alert: RolloutDegradationDetected
        expr: increase(neural_hive_rollout_degradation_total[1h]) > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Degradacao detectada durante rollout de modelo"
          description: "Modelo {{ $labels.model_name }} teve degradacao no estagio {{ $labels.stage }}"

      - alert: RolloutStuckInStage
        expr: neural_hive_rollout_stage > 0 and changes(neural_hive_rollout_stage[2h]) == 0
        for: 2h
        labels:
          severity: warning
        annotations:
          summary: "Rollout travado em estagio"
          description: "Modelo {{ $labels.model_name }} esta no estagio {{ $value }} ha mais de 2h"
```

## Arquitetura

### Sequencia de Promocao com Gradual Rollout

```
PromotionManager          ContinuousValidator          ModelRegistry            Prometheus
      |                          |                          |                        |
      |--Coletar baseline------->|                          |                        |
      |<--{mae_pct: 10.0}--------|                          |                        |
      |                          |                          |                        |
      |--set_rollout_stage(1)-------------------------------------------------->|
      |--set_rollout_traffic_pct(25%)------------------------------------------>|
      |                          |                          |                        |
      |        [Aguarda checkpoint_duration]                |                        |
      |                          |                          |                        |
      |--Coletar checkpoint----->|                          |                        |
      |<--{mae_pct: 10.5}--------|                          |                        |
      |                          |                          |                        |
      |--[Verificar degradacao]  |                          |                        |
      |--record_rollout_checkpoint(success)------------------------------------>|
      |                          |                          |                        |
      |        [Repetir para estagios 50%, 75%]             |                        |
      |                          |                          |                        |
      |--set_rollout_stage(4)-------------------------------------------------->|
      |--set_rollout_traffic_pct(100%)----------------------------------------->|
      |                          |                          |                        |
      |--promote_model----------------------------------------->|                  |
      |<--OK-----------------------------------------------------|                  |
      |                          |                          |                        |
```

## Referencias

- [Model Promotion Pipeline](./model-promotion-guide.md)
- [Shadow Mode Deployment](../services/orchestrator-dynamic/docs/SHADOW_MODE_DEPLOYMENT.md)
- [ML Operations Guide](./ML_OPERATIONS_GUIDE.md)
