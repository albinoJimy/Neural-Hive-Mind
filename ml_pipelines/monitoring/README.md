# Model Performance Monitoring & Auto-Retrain

Sistema automatizado de monitoramento de performance de modelos e retreinamento baseado em degradação detectada.

## Visão Geral

Este sistema monitora continuamente a performance dos modelos specialists através de:
- **Métricas MLflow**: Precision, Recall, F1 Score de runs de treinamento
- **Feedback Humano**: Avaliações e ratings de usuários no MongoDB
- **Score Agregado**: Combinação ponderada de MLflow (70%) e feedback (30%)
- **Auto-Retrain**: Retreinamento automático quando degradação é detectada

### Componentes

1. **ModelPerformanceMonitor** (`model_performance_monitor.py`)
   - Consulta métricas do MLflow
   - Consulta estatísticas de feedback do MongoDB
   - Calcula score agregado de performance
   - Detecta degradação baseado em thresholds
   - Exporta métricas para Prometheus

2. **AutoRetrainOrchestrator** (`auto_retrain.py`)
   - Detecta degradação usando ModelPerformanceMonitor
   - Gera novos datasets com AI (LLM-powered)
   - Executa pipeline de treinamento via MLflow
   - Monitora conclusão e promove modelo se melhor
   - Envia notificações Slack/Email em caso de falha

3. **Kubernetes CronJob** (`k8s/model-monitor-cronjob.yaml`)
   - Execução automatizada a cada 6 horas
   - Isolation e resources dedicados
   - RBAC e ServiceAccount configurados

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│                     K8s CronJob (Every 6h)                          │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│              ModelPerformanceMonitor                                │
│  ┌──────────────────┐        ┌──────────────────┐                  │
│  │  Query MLflow    │        │  Query MongoDB   │                  │
│  │  Metrics         │        │  Feedback Stats  │                  │
│  │  (P, R, F1)      │        │  (Avg Rating)    │                  │
│  └────────┬─────────┘        └────────┬─────────┘                  │
│           │                           │                             │
│           └───────────┬───────────────┘                             │
│                       ▼                                             │
│           Calculate Aggregate Score                                 │
│           (MLflow 70% + Feedback 30%)                               │
│                       │                                             │
│                       ▼                                             │
│           Detect Degradation?                                       │
└───────────────────────┬─────────────────────────────────────────────┘
                        │
            ┌───────────┴───────────┐
            │ Performance OK        │ Performance Degraded
            ▼                       ▼
    ┌───────────────┐      ┌────────────────────────────────────┐
    │  Log Status   │      │  AutoRetrainOrchestrator           │
    │  Exit         │      │                                    │
    └───────────────┘      │  1. Generate Datasets (LLM)        │
                           │  2. Merge with Feedback Data       │
                           │  3. Trigger MLflow Training        │
                           │  4. Monitor Completion             │
                           │  5. Compare Metrics                │
                           │  6. Promote if Better              │
                           │  7. Send Notifications             │
                           └────────────────────────────────────┘
```

## Como Funciona

### Performance Monitoring Flow

1. **Query MLflow Metrics**: Busca últimos 100 runs do specialist no MLflow
   - Filtra por experiment: `{specialist_type}-specialist`
   - Prioriza runs em Production, senão pega o mais recente
   - Extrai: precision, recall, f1_score, accuracy

2. **Query Feedback Statistics**: Busca feedback dos últimos 30 dias no MongoDB
   - Usa `FeedbackCollector.get_feedback_statistics()`
   - Extrai: avg_rating, total_count, distribuição (positive/negative/neutral)

3. **Calculate Aggregate Score**:
   ```
   aggregate_score = (mlflow_f1 * 0.7) + (feedback_avg * 0.3)
   ```

4. **Detect Degradation**: Retorna True se qualquer condição:
   - Precision < 0.75
   - Recall < 0.70
   - F1 Score < 0.72
   - Feedback Average < 0.6
   - Aggregate Score < 0.65

### Auto-Retrain Flow

Quando degradação é detectada:

1. **Generate Datasets**: Executa `generate_training_datasets.py`
   - Usa LLM (Ollama/OpenAI/Anthropic) para gerar 1000 amostras
   - Timeout: 30 minutos
   - Valida arquivo Parquet gerado

2. **Merge with Feedback**: Combina novos datasets com feedback recente
   - Query últimos 1000 feedbacks do MongoDB
   - Converte feedback para formato de dataset
   - Concatena usando pandas

3. **Trigger Training**: Usa `RetrainingTrigger` existente
   - Executa via MLflow Projects
   - Parâmetro `promote_if_better=True`
   - Tracking via MLflow Run ID

4. **Monitor Completion**: Aguarda conclusão do treinamento
   - Timeout: 1 hora
   - Status: FINISHED (sucesso) ou FAILED (falha)

5. **Compare Metrics**: Compara novo modelo com baseline
   - Baseline: modelo atual em Production
   - Comparação: F1 Score do novo vs. baseline
   - `improved = new_f1 > baseline_f1`

6. **Promote**: Automático se `improved=True` (handled by MLflow)

7. **Notifications**: Slack + Email
   - Success: Informa Run ID e se houve improvement
   - Failed: Informa erro e ações necessárias

## Thresholds

| Métrica | Threshold | Descrição |
|---------|-----------|-----------|
| **Precision** | ≥ 0.75 | Proporção de predições positivas corretas |
| **Recall** | ≥ 0.70 | Proporção de casos positivos identificados |
| **F1 Score** | ≥ 0.72 | Média harmônica de Precision e Recall |
| **Feedback Avg** | ≥ 0.6 | Rating médio de usuários (0.0-1.0) |
| **Aggregate Score** | ≥ 0.65 | Score combinado (MLflow 70% + Feedback 30%) |

### Configuração de Thresholds

Ajustar via ConfigMap `model-monitor-config`:

```yaml
data:
  PRECISION_THRESHOLD: "0.75"
  RECALL_THRESHOLD: "0.70"
  F1_THRESHOLD: "0.72"
  FEEDBACK_AVG_THRESHOLD: "0.6"
```

## Uso

### Execução Manual

#### 1. Verificar Performance

```bash
# Check performance de um specialist
python ml_pipelines/monitoring/model_performance_monitor.py \
  --specialist-type technical

# Formato JSON
python ml_pipelines/monitoring/model_performance_monitor.py \
  --specialist-type technical \
  --output-format json

# Exportar métricas para Prometheus
python ml_pipelines/monitoring/model_performance_monitor.py \
  --specialist-type technical \
  --export-metrics http://prometheus-pushgateway:9091
```

**Output Exemplo**:
```
============================================================
RELATÓRIO DE PERFORMANCE - technical
============================================================

Timestamp: 2025-11-23T10:30:00
Score Agregado: 0.685
Status: ✅ OK

MLflow Metrics:
  - Precision: 0.812
  - Recall: 0.743
  - F1 Score: 0.776
  - Run ID: abc123def456

Feedback Stats:
  - Média: 0.68
  - Total: 245
  - Positivo: 180
  - Negativo: 65

Recomendações:
  - Performance dentro dos thresholds esperados
  - Continuar monitoramento regular
```

#### 2. Trigger Auto-Retrain

```bash
# Auto-retrain para um specialist
python ml_pipelines/monitoring/auto_retrain.py \
  --specialist-type technical

# Todos os specialists
python ml_pipelines/monitoring/auto_retrain.py \
  --specialist-type all

# Forçar retreinamento (ignora thresholds)
python ml_pipelines/monitoring/auto_retrain.py \
  --specialist-type technical \
  --force

# Usar datasets existentes (não gerar novos)
python ml_pipelines/monitoring/auto_retrain.py \
  --specialist-type technical \
  --skip-dataset-generation

# Dry-run (simular sem executar)
python ml_pipelines/monitoring/auto_retrain.py \
  --specialist-type technical \
  --dry-run

# Customizar canais de notificação
python ml_pipelines/monitoring/auto_retrain.py \
  --specialist-type technical \
  --notification-channels slack,email
```

### Execução Automatizada (K8s CronJob)

#### 1. Deploy

```bash
# Aplicar todos os recursos
kubectl apply -f ml_pipelines/k8s/model-monitor-rbac.yaml
kubectl apply -f ml_pipelines/k8s/model-monitor-configmap.yaml
kubectl apply -f ml_pipelines/k8s/model-monitor-cronjob.yaml

# Verificar CronJob
kubectl get cronjobs -n ml-pipelines

# Verificar histórico de jobs
kubectl get jobs -n ml-pipelines -l app=model-performance-monitor
```

#### 2. Logs

```bash
# Logs do job mais recente
kubectl logs -n ml-pipelines \
  -l app=model-performance-monitor \
  --tail=100

# Logs de um job específico
kubectl logs -n ml-pipelines \
  job/model-performance-monitor-1700000000

# Seguir logs em tempo real
kubectl logs -n ml-pipelines \
  -l app=model-performance-monitor \
  -f
```

#### 3. Trigger Manual

```bash
# Criar job a partir do CronJob
kubectl create job \
  --from=cronjob/model-performance-monitor \
  model-monitor-manual-$(date +%s) \
  -n ml-pipelines

# Acompanhar execução
kubectl get jobs -n ml-pipelines -w
```

## Configuração

### Variáveis de Ambiente

#### Core
- `MONGODB_URI`: Connection string do MongoDB
- `MLFLOW_TRACKING_URI`: URL do MLflow server (default: `http://mlflow.mlflow:5000`)
- `PROMETHEUS_PUSHGATEWAY_URL`: URL do Pushgateway (optional)

#### Thresholds
- `PRECISION_THRESHOLD`: Threshold mínimo de precision (default: 0.75)
- `RECALL_THRESHOLD`: Threshold mínimo de recall (default: 0.70)
- `F1_THRESHOLD`: Threshold mínimo de F1 (default: 0.72)
- `FEEDBACK_AVG_THRESHOLD`: Threshold mínimo de feedback médio (default: 0.6)

#### Dataset Generation
- `DATASET_NUM_SAMPLES`: Número de amostras a gerar (default: 1000)
- `LLM_PROVIDER`: Provider do LLM - `local`, `openai`, `anthropic` (default: local)
- `LLM_MODEL`: Nome do modelo (default: llama2)
- `LLM_BASE_URL`: URL do Ollama se local (default: `http://ollama.default:11434`)
- `LLM_TEMPERATURE`: Temperatura para geração (default: 0.7)

#### Notifications
- `NOTIFICATION_CHANNELS`: Canais separados por vírgula (default: slack)
- `SLACK_WEBHOOK_URL`: URL do webhook Slack
- `SLACK_CHANNEL`: Canal Slack (default: #ml-alerts)
- `SMTP_HOST`: Host SMTP para email
- `SMTP_PORT`: Porta SMTP (default: 587)
- `SMTP_USER`: Usuário SMTP
- `SMTP_PASSWORD`: Senha SMTP
- `EMAIL_RECIPIENTS`: Destinatários separados por vírgula

### LLM Provider Configuration

#### Local (Ollama)
```bash
export LLM_PROVIDER=local
export LLM_MODEL=llama2
export LLM_BASE_URL=http://ollama.default:11434
```

#### OpenAI
```bash
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4
export OPENAI_API_KEY=sk-...
```

#### Anthropic
```bash
export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-3-opus-20240229
export ANTHROPIC_API_KEY=sk-ant-...
```

## Monitoramento & Alertas

### Grafana Dashboard

**Dashboard**: "Continuous Learning - Feedback & Retraining"

**Painéis Adicionados**:
1. **Model Performance Score by Specialist** (ID 16)
   - Timeseries do score agregado por specialist
   - Thresholds visuais (red < 0.6, yellow 0.6-0.75, green > 0.75)

2. **Model Degradation Alerts** (ID 17)
   - Stat mostrando specialists com degradação detectada
   - Background vermelho se degraded

3. **MLflow Metrics - Precision/Recall/F1** (ID 18)
   - Gráfico com 3 séries (Precision, Recall, F1)
   - Linhas de threshold horizontais
   - Alertas inline

4. **Auto-Retrain Triggers** (ID 19)
   - Tabela com histórico de triggers
   - Colunas: Specialist, Reason, Status, Count

5. **Dataset Generation Duration** (ID 20)
   - Histograma de duração (P50, P95)
   - Identifica timeouts

**Acessar**:
```bash
# Port-forward Grafana
kubectl port-forward -n monitoring svc/grafana 3000:80

# Browser
open http://localhost:3000/d/continuous-learning
```

### Prometheus Alerts

**Arquivo**: `monitoring/alerts/model-performance-alerts.yaml`

**Alertas Críticos** (severity: critical, oncall: true):
- `AutoRetrainFailed`: Falha no retreinamento automático
- `DatasetGenerationFailed`: Falha na geração de datasets
- `MongoDBCircuitBreakerOpen`: Circuit breaker do MongoDB aberto
- `MLflowConnectionFailed`: Falhas consecutivas de conexão com MLflow

**Alertas de Warning** (severity: warning):
- `ModelPerformanceDegraded`: Performance abaixo de 60%
- `ModelPrecisionBelowThreshold`: Precision < 0.75
- `ModelRecallBelowThreshold`: Recall < 0.70
- `ModelF1BelowThreshold`: F1 < 0.72
- `FeedbackAverageBelowThreshold`: Feedback médio < 0.6
- `AutoRetrainDurationHigh`: Retreinamento demorando > 1h

**Alertas Informativos** (severity: info):
- `ModelNotRetrainedRecently`: Modelo sem retrain há 60+ dias

**Aplicar Alertas**:
```bash
kubectl apply -f monitoring/alerts/model-performance-alerts.yaml
```

### Métricas Exportadas

| Métrica | Tipo | Descrição |
|---------|------|-----------|
| `neural_hive_model_performance_score` | Gauge | Score agregado de performance |
| `neural_hive_model_degradation_detected` | Gauge | 1 se degradado, 0 se OK |
| `neural_hive_mlflow_model_precision` | Gauge | Precision do modelo |
| `neural_hive_mlflow_model_recall` | Gauge | Recall do modelo |
| `neural_hive_mlflow_model_f1` | Gauge | F1 Score do modelo |
| `neural_hive_auto_retrain_triggered_total` | Counter | Total de auto-retrains triggered |
| `neural_hive_auto_retrain_duration_seconds` | Gauge | Duração do auto-retrain |
| `neural_hive_auto_retrain_success_total` | Counter | Total de auto-retrains bem-sucedidos |
| `neural_hive_dataset_generation_duration_seconds` | Histogram | Duração da geração de datasets |
| `neural_hive_dataset_generation_errors_total` | Counter | Erros na geração de datasets |

## Troubleshooting

### Problemas Comuns

#### 1. MLflow Connection Failures

**Sintomas**: Erro ao query métricas do MLflow

**Debug**:
```bash
# Verificar status do MLflow
kubectl get pods -n mlflow

# Verificar conectividade
curl http://mlflow.mlflow:5000/health

# Verificar variável de ambiente
echo $MLFLOW_TRACKING_URI

# Logs do MLflow
kubectl logs -n mlflow -l app=mlflow
```

**Solução**:
- Verificar se MLflow está running
- Validar `MLFLOW_TRACKING_URI` no ConfigMap
- Verificar network policies

#### 2. Dataset Generation Timeouts

**Sintomas**: `dataset_generation_timeout` nos logs

**Debug**:
```bash
# Verificar LLM provider
curl http://ollama.default:11434/api/tags  # se local

# Verificar API keys
echo $OPENAI_API_KEY  # se OpenAI
echo $ANTHROPIC_API_KEY  # se Anthropic

# Verificar prompts
ls -la /app/training/prompts/
```

**Solução**:
- Aumentar timeout: `DATASET_GENERATION_TIMEOUT=3600`
- Reduzir amostras: `DATASET_NUM_SAMPLES=500`
- Verificar quotas de API (se provider externo)
- Verificar recursos do pod (CPU/memória)

#### 3. MongoDB Circuit Breaker Open

**Sintomas**: `mongodb_circuit_breaker_state=open`

**Debug**:
```bash
# Verificar MongoDB
kubectl get pods -n mongodb-cluster

# Verificar connectivity
mongo --eval 'db.runCommand({ping: 1})'

# Verificar logs
kubectl logs -n mongodb-cluster mongodb-0
```

**Solução**:
- Aguardar circuit breaker auto-recuperar (30s)
- Verificar se MongoDB tem recursos suficientes
- Validar `MONGODB_URI` no Secret
- Verificar network policies

#### 4. Notification Delivery Failures

**Sintomas**: `slack_notification_failed` ou `email_notification_failed`

**Debug**:
```bash
# Verificar Slack webhook
curl -X POST $SLACK_WEBHOOK_URL \
  -H 'Content-Type: application/json' \
  -d '{"text":"Test"}'

# Verificar SMTP
telnet $SMTP_HOST $SMTP_PORT
```

**Solução**:
- Validar `SLACK_WEBHOOK_URL` no Secret
- Validar credenciais SMTP
- Verificar firewall/network policies
- Testar manualmente com curl/telnet

#### 5. Training Não Promove Modelo

**Sintomas**: Novo modelo trained mas não vai para Production

**Debug**:
```bash
# Verificar métricas do novo modelo
mlflow runs describe <run_id>

# Verificar baseline
mlflow models list --experiment-name technical-specialist

# Comparar F1 scores
mlflow metrics compare <run_id_new> <run_id_baseline>
```

**Solução**:
- Verificar se `new_f1 > baseline_f1`
- Validar parâmetro `promote_if_better=True`
- Revisar logs de treinamento
- Considerar ajuste de hiperparâmetros

## Integração com Sistemas Existentes

### FeedbackCollector
- Reusa `get_feedback_statistics()` para query MongoDB
- Reusa `get_recent_feedback()` para merge com datasets
- Circuit breaker herdado automaticamente

### RetrainingTrigger
- Reusa `trigger_retraining()` para MLflow orchestration
- Reusa `monitor_run_status()` para acompanhar completion
- Cooldown period (24h) aplicado automaticamente

### generate_training_datasets.py
- Integra via subprocess call
- Passa env vars: `LLM_PROVIDER`, `LLM_MODEL`, `LLM_BASE_URL`
- Timeout configurável (default: 30min)

### train_specialist_model.py
- Executado via MLflow Projects (gerenciado por RetrainingTrigger)
- Auto-promoção via `promote_if_better=True`
- Tracking de métricas automático

## Best Practices

### Frequência de Execução
- **Recomendado**: A cada 6 horas
- **Razão**: Balance entre responsiveness e uso de recursos
- **Configurar**: Ajustar `schedule` no CronJob

### Cooldown Period
- **Recomendado**: 24 horas entre retrains do mesmo specialist
- **Razão**: Evitar retreinamentos excessivos
- **Configurar**: `RETRAINING_COOLDOWN_HOURS=24` no ConfigMap

### Dry-Run Testing
- **Sempre** testar mudanças em dry-run primeiro:
  ```bash
  python ml_pipelines/monitoring/auto_retrain.py \
    --specialist-type technical \
    --dry-run
  ```

### Notification Monitoring
- **Configurar** Slack/Email mesmo em dev/staging
- **Testar** regularmente entrega de notificações
- **Revisar** mensagens semanalmente para detectar padrões

### Dashboard Review
- **Revisar** dashboard Grafana semanalmente
- **Identificar** trends de degradação antes de alertas críticos
- **Ajustar** thresholds se necessário

### Resource Limits
- **Sempre** configurar limits no CronJob:
  ```yaml
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: 1000m
      memory: 2Gi
  ```

### Dataset Cleanup
- Auto-retrain executa cleanup automático (datasets > 90 dias)
- **Verificar** periodicamente uso de storage:
  ```bash
  kubectl exec -n ml-pipelines <pod> -- du -sh /data/training
  ```

## Melhorias Futuras

### Planejadas
1. **A/B Testing**: Comparar múltiplos modelos em paralelo
2. **Drift Detection**: Detectar mudanças na distribuição de features
3. **Automated Hyperparameter Tuning**: Otimizar hiperparâmetros automaticamente
4. **Multi-Model Ensemble**: Avaliar ensembles de modelos
5. **Explainability Integration**: Integrar SHAP/LIME para interpretabilidade
6. **Custom Metrics**: Permitir métricas customizadas por specialist
7. **Gradual Rollout**: Canary deployment de novos modelos
8. **Cost Tracking**: Rastrear custos de retreinamento e LLM calls

### Contribuindo
Ver [CONTRIBUTING.md](../../CONTRIBUTING.md) para guidelines.

## Suporte

- **Issues**: [GitHub Issues](https://github.com/neural-hive-mind/issues)
- **Slack**: #ml-ops-support
- **Email**: ml-ops@neural-hive-mind.io
- **Runbooks**: https://docs.neural-hive-mind.io/runbooks/
