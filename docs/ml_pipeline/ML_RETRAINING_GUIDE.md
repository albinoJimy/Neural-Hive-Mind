# ML Retraining Pipeline - Neural Hive-Mind

## Visão Geral

Pipeline completo de retreinamento de modelos ML para especialistas do Neural Hive-Mind, integrando:
- Coleta de dados de produção
- Feature engineering avançada
- Treinamento com MLflow
- Validação de modelos
- A/B Testing automático
- Monitoramento de Drift
- Deployment seguro

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ML RETRAINING PIPELINE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐      │
│  │  Production Data │ -> │ Feature Eng.     │ -> │   MLflow Train   │      │
│  │    Collector     │    │  (Enhanced)      │    │                  │      │
│  └──────────────────┘    └──────────────────┘    └────────┬─────────┘      │
│                                                         │                  │
│                                                         v                  │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐      │
│  │  Model Validator │ <- │   A/B Testing    │ <- │  MLflow Deployer │      │
│  │                  │    │   Framework      │    │                  │      │
│  └────────┬─────────┘    └────────┬─────────┘    └──────────────────┘      │
│           │                      │                                          │
│           v                      v                                          │
│  ┌──────────────────┐    ┌──────────────────┐                              │
│  │   Promote to     │    │  Drift Monitor   │                              │
│  │   Production     │    │   (Auto-retrain) │                              │
│  └──────────────────┘    └──────────────────┘                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Componentes

### 1. Production Data Collector

**Arquivo:** `ml_pipelines/training/collect_production_data.py`

Coleta dados de produção para retreinamento:
- Kafka topic `intentions.audit` (90 dias de retenção)
- MongoDB `cognitive_plans` collection
- Filtro: confidence >= 0.7
- Mínimo: 10k amostras por especialista

```bash
# Coletar dados para todos os especialistas
python ml_pipelines/training/collect_production_data.py \
    --specialist all \
    --min-samples 10000 \
    --output-dir /data/ml_training_data \
    --min-confidence 0.7 \
    --days 90

# Coletar para especialista específico
python ml_pipelines/training/collect_production_data.py \
    --specialist business \
    --min-samples 10000
```

### 2. Enhanced Feature Engineering

**Arquivo:** `ml_pipelines/training/generate_training_datasets.py`

Features avançadas adicionadas no Passo 5.2:

#### Task Complexity Features
- `task_depth_max`: Profundidade máxima do DAG
- `branching_factor_avg`: Fator de ramificação médio
- `critical_path_length`: Tamanho do caminho crítico

#### Dependency Features
- `has_cyclic_dependencies`: Detecta dependências cíclicas
- `weak_dependency_ratio`: Razão de dependências fracas

#### Temporal Features
- `duration_variance`: Variância das durações estimadas
- `duration_coefficient_of_variation`: CV das durações
- `parallelization_potential`: Potencial de paralelização

#### Resource/Capability Features
- `capability_diversity`: Diversidade de capabilities
- `workload_distribution_score`: Distribuição de workload (Gini)

#### Risk-Adjusted Features
- `risk_complexity_product`: Produto risco × complexidade
- `risk_adjusted_duration_estimate`: Duração ajustada por risco

### 3. Model Validator

**Arquivo:** `ml_pipelines/training/validate_models.py`

Valida modelos treinados com métricas mínimas:

```python
MIN_METRICS = {
    'confidence_mean': 0.70,      # Confiança média mínima
    'f1_score': 0.65,              # F1 score mínimo
    'precision_min': 0.60,         # Precisão mínima por classe
    'recall_min': 0.60,            # Recall mínimo por classe
    'accuracy_min': 0.65           # Acurácia mínima
}
```

```bash
# Validar modelo específico
python -m ml_pipelines.training.validate_models \
    --models-dir /data/models \
    --test-data-dir /data/test_data \
    --output-dir /tmp/model_validation \
    --specialist business
```

### 4. A/B Testing Framework

**Arquivo:** `ml_pipelines/training/ab_testing.py`

Framework completo de A/B testing para ML models:

#### Funcionalidades
- Roteamento de tráfego por porcentagem
- Coleta de métricas (confidence, accuracy)
- Critérios de aprovação automática
- Expansão gradual de tráfego
- Integração com MLflow

#### Estratégia de Expansão
1. **10% → 25%**: após 24h se métricas estáveis
2. **25% → 50%**: após 48h se métricas positivas
3. **50% → 100%**: após 72h se teste passou
4. **Rollback**: se métricas negativas

```bash
# Iniciar teste A/B
python -m ml_pipelines.training.ab_testing \
    --action start \
    --specialist business \
    --new-version v12 \
    --baseline-version Production \
    --traffic 10.0

# Verificar status
python -m ml_pipelines.training.ab_testing \
    --action check \
    --test-id business_v12_20240212_143000

# Expandir tráfego
python -m ml_pipelines.training.ab_testing \
    --action expand \
    --test-id business_v12_20240212_143000 \
    --traffic 50.0
```

### 5. MLflow Deployer

**Arquivo:** `ml_pipelines/training/mlflow_deployer.py`

Gerencia deployment de modelos no MLflow:

```bash
# Registrar modelo
python ml_pipelines/training/mlflow_deployer.py \
    --register \
    --model-path /data/models/business_model.pkl \
    --model-type business \
    --run-id abc123 \
    --metrics '{"accuracy": 0.85, "f1": 0.82}'

# Promover para produção
python ml_pipelines/training/mlflow_deployer.py \
    --promote \
    --model-type business \
    --model-version 12 \
    --target-stage Production

# Listar modelos
python ml_pipelines/training/mlflow_deployer.py \
    --list \
    --model-type business

# Rollback
python ml_pipelines/training/mlflow_deployer.py \
    --rollback \
    --model-type business \
    --target-version 11

# Criar alias para A/B test
python ml_pipelines/training/mlflow_deployer.py \
    --alias \
    --model-type business \
    --alias ab-test-v12 \
    --model-version 12
```

### 6. Drift-Triggered Retraining

**Arquivo:** `ml_pipelines/training/drift_triggered_retraining.py`

Monitora drift e dispara retreinamento automático (Passo 5.7):

#### Integração com A/B Testing
Após retreinamento bem-sucedido:
1. Cria teste A/B automaticamente (10% tráfego)
2. Monitora métricas continuamente
3. Expande tráfego gradualmente
4. Promove para 100% se aprovado
5. Rollback automático se falhar

```bash
# Verificação única
python ml_pipelines/training/drift_triggered_retraining.py \
    --check-once

# Loop contínuo
python ml_pipelines/training/drift_triggered_retraining.py

# Dry-run (simulação)
python ml_pipelines/training/drift_triggered_retraining.py \
    --check-once \
    --dry-run
```

## Fluxo Completo de Retreinamento

```bash
#!/bin/bash
# fluxo_retreinamento_completo.sh

# 1. Coletar dados de produção
echo "Coletando dados de produção..."
python ml_pipelines/training/collect_production_data.py \
    --specialist all \
    --min-samples 10000 \
    --output-dir /data/ml_training_data

# 2. Gerar datasets com features avançadas
echo "Gerando datasets..."
for specialist in business technical behavior evolution architecture; do
    python ml_pipelines/training/generate_training_datasets.py \
        --specialist-type $specialist \
        --num-samples 5000 \
        --output-path /data/ml_training_data/${specialist}_enhanced.parquet
done

# 3. Treinar modelos
echo "Treinando modelos..."
python ml_pipelines/training/train_specialist_model.py \
    --specialist-type all \
    --data-dir /data/ml_training_data

# 4. Validar modelos
echo "Validando modelos..."
python -m ml_pipelines.training.validate_models \
    --models-dir /data/models \
    --test-data-dir /data/test_data \
    --specialist all

# 5. Registrar no MLflow
echo "Registrando no MLflow..."
for specialist in business technical behavior evolution architecture; do
    python ml_pipelines/training/mlflow_deployer.py \
        --register \
        --model-path /data/models/${specialist}_model.pkl \
        --model-type $specialist \
        --run-id $(cat /data/runs/${specialist}_run_id.txt)
done

# 6. Iniciar A/B testing
echo "Iniciando A/B testing..."
python -m ml_pipelines.training.ab_testing \
    --action start \
    --specialist all \
    --new-version v12 \
    --traffic 10.0

echo "Pipeline concluído! Monitore os testes A/B."
```

## Métricas de Sucesso

### Métricas de Modelo
- **Confidence Mean**: >= 0.70 (threshold mínimo)
- **F1 Score**: >= 0.65
- **Accuracy**: >= 0.65
- **Precision/Recall**: >= 0.60 por classe

### Métricas de A/B Testing
- **Improvement**: >= 2% sobre baseline
- **Duration**: 72 horas mínimo
- **Samples**: 1000 mínimo por modelo

### Métricas de Drift
- **Drift Score**: threshold = 0.2
- **Check Interval**: 60 minutos
- **Retention Window**: 90 dias

## Variáveis de Ambiente

```bash
# MLflow
export MLFLOW_TRACKING_URI=http://mlflow.mlflow.svc.cluster.local:5000
export MLFLOW_EXPERIMENT_NAME=specialist_training

# MongoDB
export MONGODB_URI=mongodb://localhost:27017

# A/B Testing
export AB_TESTING_ENABLED=true
export AB_TEST_DEFAULT_TRAFFIC=10.0

# Drift Monitoring
export DRIFT_THRESHOLD=0.2
export DRIFT_CHECK_INTERVAL_MINUTES=60

# Data Collection
export KAFKA_BOOTSTRAP_SERVERS=neural-hive-kafka-bootstrap:9092
export DATA_COLLECTION_DAYS=90
export MIN_CONFIDENCE=0.7
```

## Troubleshooting

### Modelos com baixa confiança (~0.5)
**Causa**: Dados sintéticos de treinamento
**Solução**: Coletar mais dados reais de produção

### A/B test não criado
**Causa**: Módulo ab_testing não disponível
**Solução**: Verificar import e instalar dependências

### Drift não detectado
**Causa**: Threshold muito alto ou dados insuficientes
**Solução**: Ajustar DRIFT_THRESHOLD ou aumentar janela de coleta

## Próximos Passos

1. **Coletar dados reais**: Executar collect_production_data.py
2. **Treinar com dados reais**: Usar datasets enriquecidos
3. **Configurar monitoramento**: Deploy de drift_triggered_retraining.py
4. **Validar E2E**: Testar pipeline completo
