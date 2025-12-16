# ML Feedback Loop Architecture

## 📋 Visão Geral

O feedback loop ML do Orchestrator Dynamic permite treinamento contínuo de modelos de predição de duração e otimização de alocação via Reinforcement Learning (RL).

## 🔄 Fluxo End-to-End

### 1. **Predição (Scheduler)**
- **Onde:** `intelligent_scheduler.py` → `_enrich_ticket_with_predictions()`
- **Quando:** Durante alocação de recursos (C3)
- **O que faz:**
  - Chama `scheduling_predictor.predict_duration()` → retorna `{duration_ms, confidence}`
  - Chama `anomaly_detector.detect_anomaly()` → retorna `{is_anomaly, score, type}`
  - Adiciona campo `predictions` ao ticket
  - Usa predições para boost de prioridade (20% se `duration_ratio > 1.5` ou anomalia detectada)

### 2. **Enriquecimento de Allocation Metadata (Scheduler)**
- **Onde:** `intelligent_scheduler.py` → `schedule_ticket()`
- **Quando:** Após seleção de worker
- **O que faz:**
  - Adiciona ao `allocation_metadata`:
    - `predicted_duration_ms`: Duração prevista pelo modelo
    - `anomaly_detected`: Boolean
    - `predicted_queue_ms`: Queue time previsto (de `SchedulingOptimizer`)
    - `predicted_load_pct`: Carga prevista do worker
    - `ml_enriched`: Flag indicando uso de ML

### 3. **Execução (Worker Agents)**
- **Onde:** worker-agents (fora do orchestrator)
- **Quando:** Após consumo do ticket do Kafka
- **O que faz:**
  - Executa task
  - Registra `actual_duration_ms` no ticket
  - Atualiza status para `COMPLETED`

### 4. **ML Error Tracking (Result Consolidation)**
- **Onde:** `result_consolidation.py` → `compute_and_record_ml_error()`
- **Quando:** Durante consolidação de resultados (C5)
- **O que faz:**
  - Calcula erro: `error_ms = actual_duration_ms - predicted_duration_ms`
  - Registra em Prometheus: `ml_prediction_error` (Histogram)
  - Atualiza acurácia em `ml_model_accuracy` (Gauge) via `record_ml_prediction_accuracy`
  - Log estruturado com `error_pct`
  - **Fail-open:** Não bloqueia se falhar

### 5. **Allocation Outcome Feedback (Result Consolidation)**
- **Onde:** `result_consolidation.py` → `record_allocation_outcome_for_ticket()`
- **Quando:** Durante consolidação de resultados (C5), após ML error tracking
- **O que faz:**
  - Extrai dados de `allocation_metadata`: agent_id, predicted_queue_ms, predicted_load_pct
  - Chama `scheduling_optimizer.record_allocation_outcome(ticket, worker, actual_duration_ms)`
  - Publica outcome no Kafka `ml.allocation_outcomes` para treinamento RL
  - Registra métricas:
    - `scheduler_allocation_quality_score`: Score de qualidade (0-1)
    - `scheduler_queue_prediction_error_ms`: Erro de predição de queue
  - **Fail-open:** Não bloqueia se falhar

### 6. **Treinamento Offline (Optimizer Agents)**
- **Onde:** optimizer-agents (serviço separado)
- **Quando:** Periodicamente (CronJob) ou por drift detection
- **O que faz:**
  - Consome outcomes do Kafka `ml.allocation_outcomes`
  - Retreina modelos:
    - **DurationPredictor:** RandomForest com features históricas
    - **RL Policy:** Q-learning para recomendações de alocação
  - Promove modelos para Production no MLflow
  - Scheduler carrega novos modelos automaticamente (cache TTL)

## 📊 Métricas Prometheus

### Predição de Duração
- `orchestration_ml_prediction_error` (Histogram): Erro absoluto em ms
- `orchestration_ml_model_accuracy` (Gauge): Acurácia do modelo (MAE%, R²)
- `orchestration_ml_predictions_total` (Counter): Total de predições

### Allocation Quality
- `orchestration_scheduler_allocation_quality_score` (Histogram): Score 0-1
- `orchestration_scheduler_queue_prediction_error_ms` (Histogram): Erro de queue time
- `orchestration_scheduler_predicted_queue_time_ms` (Histogram): Queue times preditos

### Anomalias
- `orchestration_ml_anomalies_detected_total` (Counter): Anomalias por tipo

## 🔧 Configuração

### Variáveis de Ambiente

```yaml
ML_PREDICTIONS_ENABLED: true
ML_ALLOCATION_OUTCOMES_ENABLED: true
ML_ALLOCATION_OUTCOMES_TOPIC: ml.allocation_outcomes
MLFLOW_TRACKING_URI: http://mlflow:5000
ML_TRAINING_WINDOW_DAYS: 540  # 18 meses
ML_DURATION_ERROR_THRESHOLD: 0.15  # 15%
```

### Feature Flags (OPA)
- `enable_intelligent_scheduler`: Habilitar scheduler com ML
- `enable_optimizer_integration`: Usar optimizer-agents remoto

## 🚨 Fail-Safe Design

### Fail-Open em Todos os Pontos
1. **Predição falha:** Usa `estimated_duration_ms` do ticket
2. **Anomaly detection falha:** Assume `is_anomaly=False`
3. **Error tracking falha:** Log warning, não bloqueia consolidação
4. **Outcome recording falha:** Log warning, não bloqueia consolidação
5. **Optimizer remoto indisponível:** Fallback para LoadPredictor local
6. **SLA desabilitado:** Tracking de erro e outcomes continua ativo (não depende de SLA monitoring)

### Validações
- `actual_duration_ms` deve ser > 0
- `predicted_duration_ms` deve existir em `allocation_metadata`
- `agent_id` deve existir para feedback

## 🧪 Testes

### Testes de Integração
- `tests/integration/test_ml_feedback_loop_integration.py`: End-to-end do feedback loop
- Valida que outcomes são registrados corretamente
- Valida fail-open em erros

### Testes Unitários
- `tests/unit/test_ml_prediction_integration.py`: Predições e priority boosting
- Valida cálculos de boost
- Valida estrutura de `predictions` e `allocation_metadata`

## 📈 Monitoramento

### Dashboards Grafana
1. **ML Prediction Accuracy:**
   - MAE% por modelo
   - Distribuição de erros
   - Confidence scores
2. **Allocation Quality:**
   - Quality scores ao longo do tempo
   - Erro de predição de queue
   - Taxa de uso de ML vs fallback
3. **Anomaly Detection:**
   - Anomalias detectadas por tipo
   - Taxa de falsos positivos

### Alertas
- MAE% > 20%: Modelo degradado, retreinar
- Allocation quality < 0.5: Investigar alocações ruins
- Anomaly rate > 10%: Possível drift de dados

## 🔗 Referências

- `intelligent_scheduler.py`: Predições e priority boosting
- `result_consolidation.py`: Error tracking e feedback loop
- `scheduling_optimizer.py`: Publicação de outcomes no Kafka
- `duration_predictor.py`: Modelo de predição de duração
- `metrics.py`: Métricas Prometheus
