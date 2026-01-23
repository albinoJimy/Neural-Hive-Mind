# Shadow Mode para Deployment de Modelos ML

## Visão Geral

Shadow Mode é uma estratégia de deployment que permite validar novos modelos ML executando predições em paralelo com o modelo de produção, sem afetar as decisões do sistema.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                        Request                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ShadowModeRunner                              │
│  ┌───────────────────┐     ┌───────────────────┐                │
│  │  Production Model │     │   Shadow Model    │                │
│  │    (síncrono)     │     │   (assíncrono)    │                │
│  └─────────┬─────────┘     └─────────┬─────────┘                │
│            │                          │                          │
│            ▼                          ▼                          │
│    Retorna resultado         Executa em background               │
│                                       │                          │
│                                       ▼                          │
│                            Calcula Agreement                     │
│                                       │                          │
│                                       ▼                          │
│                           Persiste Comparação                    │
│                              (MongoDB)                           │
└─────────────────────────────────────────────────────────────────┘
```

## Componentes

### ShadowModeRunner

Classe principal que coordena execução de predições shadow:

- Executa modelo de produção de forma síncrona
- Dispara modelo shadow em background (fire-and-forget)
- Calcula taxa de concordância entre modelos
- Persiste comparações para análise posterior
- Utiliza circuit breaker para falhas do modelo shadow

### Integração com ModelPromotionManager

O `ModelPromotionManager` gerencia o ciclo de vida de promoção de modelos:

```
PENDING → VALIDATING → SHADOW_MODE → CANARY → ROLLING_OUT → COMPLETED
```

Durante a fase `SHADOW_MODE`, o runner é criado automaticamente e as predições
passam a ser executadas em paralelo.

## Configuração

### Variáveis de Ambiente

```bash
# Habilitar Shadow Mode
ML_SHADOW_MODE_ENABLED=true

# Duração do período de shadow (minutos)
ML_SHADOW_MODE_DURATION_MINUTES=10080  # 7 dias

# Número mínimo de predições para validação
ML_SHADOW_MODE_MIN_PREDICTIONS=1000

# Threshold de agreement para aprovação (0.0 - 1.0)
ML_SHADOW_MODE_AGREEMENT_THRESHOLD=0.90

# Taxa de amostragem (0.0 - 1.0)
ML_SHADOW_MODE_SAMPLE_RATE=1.0

# Persistir comparações no MongoDB
ML_SHADOW_MODE_PERSIST_COMPARISONS=true

# Habilitar circuit breaker
ML_SHADOW_MODE_CIRCUIT_BREAKER_ENABLED=true
```

## Métricas Prometheus

### Contadores

| Métrica | Labels | Descrição |
|---------|--------|-----------|
| `neural_hive_shadow_predictions_total` | model_name, model_version, status | Total de predições shadow executadas |
| `neural_hive_shadow_comparison_errors_total` | model_name, error_type | Erros em comparações shadow |

### Gauges

| Métrica | Labels | Descrição |
|---------|--------|-----------|
| `neural_hive_shadow_agreement_rate` | model_name, model_version, agreement_type | Taxa de concordância atual |
| `neural_hive_shadow_circuit_breaker_state` | model_name | Estado do circuit breaker (0=closed, 1=open, 2=half-open) |

### Histogramas

| Métrica | Labels | Descrição |
|---------|--------|-----------|
| `neural_hive_shadow_latency_seconds` | model_name, model_version | Latência das predições shadow |

## MongoDB Indexes

Execute o script para criar indexes otimizados:

```bash
cd services/orchestrator-dynamic
python scripts/create_shadow_mode_indexes.py --action create
```

### Indexes Criados

1. **timestamp_ttl**: TTL de 30 dias para expiração automática
2. **model_name_timestamp**: Queries por modelo ordenadas por tempo
3. **model_name_version_agreement**: Análise de agreement por versão
4. **predictor_type_timestamp**: Queries por tipo de predictor

## Cálculo de Agreement

### Para DurationPredictor

Considera concordância se a diferença relativa for menor que 15%:

```python
diff_pct = abs(prod_result - shadow_result) / prod_result
agreement = diff_pct < 0.15
```

### Para AnomalyDetector

Considera concordância se ambos concordam no resultado (is_anomaly):

```python
agreement = prod_result['is_anomaly'] == shadow_result['is_anomaly']
```

## Fluxo de Promoção

1. **Modelo candidato registrado** no MLflow
2. **Validação inicial** de métricas (MAE, RMSE, etc.)
3. **Shadow Mode iniciado** - modelo executa em paralelo
4. **Monitoramento** de agreement rate por 7 dias
5. Se agreement >= 90% com mínimo de 1000 predições:
   - **Canary deployment** iniciado (5% do tráfego)
6. Se canary bem sucedido:
   - **Rolling deployment** para produção

## Circuit Breaker

O circuit breaker protege o sistema de falhas do modelo shadow:

- **Threshold**: 5 falhas consecutivas
- **Recovery timeout**: 60 segundos
- **Estado monitorado** via métrica Prometheus

Quando aberto, predições shadow são puladas mas produção continua normalmente.

## Dashboard Grafana

### Queries Recomendadas

**Taxa de Agreement (últimas 24h)**:
```promql
neural_hive_shadow_agreement_rate{model_name=~"$model"}
```

**Volume de Predições Shadow**:
```promql
rate(neural_hive_shadow_predictions_total{model_name=~"$model"}[5m])
```

**Latência P95**:
```promql
histogram_quantile(0.95, rate(neural_hive_shadow_latency_seconds_bucket{model_name=~"$model"}[5m]))
```

**Estado do Circuit Breaker**:
```promql
neural_hive_shadow_circuit_breaker_state{model_name=~"$model"}
```

## Troubleshooting

### Agreement Rate Baixo

1. Verificar se modelo shadow foi treinado com dados recentes
2. Analisar distribuição de features nas comparações
3. Verificar se há drift nos dados de entrada

### Circuit Breaker Abrindo Frequentemente

1. Verificar logs de erro do modelo shadow
2. Verificar memória/CPU disponível
3. Analisar tempo de inferência do modelo

### Comparações Não Sendo Persistidas

1. Verificar conexão MongoDB
2. Verificar config `ML_SHADOW_MODE_PERSIST_COMPARISONS`
3. Verificar logs de erro de inserção

## Exemplo de Uso

```python
from src.ml.shadow_mode import ShadowModeRunner
from src.ml.model_promotion import ModelPromotionManager

# Criar runner
runner = ShadowModeRunner(
    model_name='duration-predictor',
    production_model=prod_model,
    shadow_model=candidate_model,
    config=config,
    mongodb_client=mongodb,
    metrics=metrics
)

# Executar predição com shadow
result = await runner.predict_with_shadow(features)

# Obter estatísticas
stats = runner.get_agreement_stats()
print(f"Agreement rate: {stats['agreement_rate']:.2%}")
```
