# Otimizações de Performance do Specialist

Este documento descreve as otimizações de performance implementadas para os especialistas do Neural Hive Mind.

## Visão Geral

As otimizações focam em reduzir a latência de avaliação de planos cognitivos para atingir a meta de **p95 < 10 segundos**.

## Otimizações Implementadas

### 1. Feature Cache (Redis)

Cache de features extraídas em Redis para evitar reprocessamento de planos já avaliados.

**Configuração:**
```yaml
config:
  featureCacheEnabled: true
  featureCacheTtlSeconds: 3600  # 1 hora
```

**Variáveis de ambiente:**
- `FEATURE_CACHE_ENABLED`: Habilitar/desabilitar cache
- `FEATURE_CACHE_TTL_SECONDS`: TTL do cache em segundos

**Ganho esperado:** 30-40% redução de latência para planos repetidos

**Trade-offs:**
- Uso de memória Redis (~1KB por plano)
- Possível invalidação necessária ao atualizar modelo

### 2. Batch Inference

Processamento otimizado de múltiplos planos em batch usando `BatchEvaluator`.

**Configuração:**
```yaml
config:
  enableBatchInference: true
  batchInferenceSize: 32
  batchInferenceMaxWorkers: 8
```

**Variáveis de ambiente:**
- `ENABLE_BATCH_INFERENCE`: Habilitar/desabilitar batch inference
- `BATCH_INFERENCE_SIZE`: Tamanho máximo do batch
- `BATCH_INFERENCE_MAX_WORKERS`: Workers paralelos para processamento

**Ganho esperado:** 50-70% redução de latência para múltiplos planos

**Uso:**
Quando `enable_batch_inference=true`, o método `evaluate_plans_batch()` automaticamente
utiliza `evaluate_plans_batch_optimized()` que aproveita:
- Feature extraction paralela
- Inferência em batch do modelo
- Otimizações de memória

### 3. GPU Acceleration

Aceleração de geração de embeddings usando CUDA.

**Configuração:**
```yaml
config:
  enableGpuAcceleration: false  # Requer CUDA
  gpuDevice: "auto"  # 'auto', 'cuda', ou 'cpu'
```

**Variáveis de ambiente:**
- `ENABLE_GPU_ACCELERATION`: Habilitar/desabilitar GPU
- `GPU_DEVICE`: Dispositivo a usar ('auto', 'cuda', 'cpu')

**Ganho esperado:** 60-80% redução de latência para embedding generation

**Trade-offs:**
- Requer nodes Kubernetes com GPU NVIDIA
- Overhead de transferência de dados CPU<->GPU
- Custo adicional de infraestrutura

**Pré-requisitos:**
- CUDA toolkit instalado
- Driver NVIDIA compatível
- CuPy ou PyTorch com suporte CUDA

### 4. Profiling por Etapa

Instrumentação detalhada de métricas por etapa de avaliação.

**Métrica Prometheus:**
```
neural_hive_specialist_step_duration_seconds{specialist_type="business", step="feature_extraction"}
neural_hive_specialist_step_duration_seconds{specialist_type="business", step="inference"}
neural_hive_specialist_step_duration_seconds{specialist_type="business", step="post_processing"}
```

**Etapas monitoradas:**
- `feature_extraction`: Extração de features do plano
- `inference`: Inferência do modelo ML
- `post_processing`: Geração de explicabilidade
- `workflow_analysis`: Análise de workflow (Business Specialist)
- `kpi_analysis`: Análise de KPIs (Business Specialist)
- `cost_analysis`: Análise de custos (Business Specialist)
- `risk_calculation`: Cálculo de risco
- `reasoning_generation`: Geração de narrativas

## Metas de Latência

| Métrica | Meta | Descrição |
|---------|------|-----------|
| p50 | < 3s | Latência mediana |
| p95 | < 10s | Latência 95º percentil |
| p99 | < 15s | Latência 99º percentil |

## Benchmark

Execute o benchmark para validar performance:

```bash
cd /home/jimy/NHM/Neural-Hive-Mind
python ml_pipelines/optimization/benchmark_optimizations.py [NUM_PLANS] [TASKS_PER_PLAN]
```

**Parâmetros:**
- `NUM_PLANS`: Número de planos para testar (default: 30)
- `TASKS_PER_PLAN`: Tarefas por plano (default: 10)

O benchmark valida automaticamente se p95 está abaixo de 10 segundos e falha se exceder.

## Combinação Recomendada para Produção

```yaml
config:
  # Feature Cache: Sempre habilitar
  featureCacheEnabled: true
  featureCacheTtlSeconds: 3600

  # Batch Inference: Sempre habilitar
  enableBatchInference: true
  batchInferenceSize: 32
  batchInferenceMaxWorkers: 8

  # GPU: Habilitar apenas se carga justificar custo
  enableGpuAcceleration: false
  gpuDevice: "auto"
```

## Monitoramento

### Dashboards Grafana

Métricas importantes para monitorar:

1. **Latência por etapa:**
   ```promql
   histogram_quantile(0.95, rate(neural_hive_specialist_step_duration_seconds_bucket[5m]))
   ```

2. **Cache hit ratio:**
   ```promql
   neural_hive_specialist_cache_hit_ratio{specialist_type="business"}
   ```

3. **Throughput de batch:**
   ```promql
   rate(neural_hive_specialist_batch_evaluations_total[5m])
   ```

### Alertas Sugeridos

```yaml
- alert: SpecialistP95LatencyHigh
  expr: histogram_quantile(0.95, rate(neural_hive_specialist_evaluation_duration_seconds_bucket[5m])) > 10
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Specialist p95 latency exceeds 10s target"
```

## Troubleshooting

### Latência alta em feature extraction
1. Verificar se feature cache está habilitado
2. Verificar conectividade com Redis
3. Considerar aumentar TTL do cache

### Latência alta em inference
1. Verificar se modelo está carregado corretamente
2. Considerar habilitar GPU acceleration
3. Verificar recursos do pod (CPU/Memory)

### Batch processing lento
1. Verificar `batchInferenceMaxWorkers`
2. Ajustar `batchInferenceSize` para carga
3. Verificar contenção de recursos
