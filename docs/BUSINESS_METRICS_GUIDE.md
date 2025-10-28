# Guia de Business Metrics

## Visão Geral

O sistema de Business Metrics do Neural Hive Mind correlaciona opiniões dos especialistas com decisões finais do consenso para calcular métricas de qualidade pós-consenso: precisão, recall, F1-score, taxas de falsos positivos/negativos, e valor de negócio gerado.

### Arquitetura

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│ Ledger          │      │ Consensus Engine │      │ Execution Ticket│
│ (Opiniões)      │─────▶│ (Decisões)       │─────▶│ API (Resultados)│
└─────────────────┘      └──────────────────┘      └─────────────────┘
        │                         │                         │
        │                         │                         │
        └─────────────────────────┴─────────────────────────┘
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │ BusinessMetricsCollector │
                    │ (Correlaciona e calcula) │
                    └──────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
          ┌──────────────────┐      ┌──────────────────┐
          │ AnomalyDetector  │      │ Prometheus       │
          │ (Isolation Forest│      │ (Métricas)       │
          └──────────────────┘      └──────────────────┘
                    │                         │
                    └─────────────┬───────────┘
                                  ▼
                         ┌──────────────────┐
                         │ Grafana Dashboard│
                         │ + Alertmanager   │
                         └──────────────────┘
```

## Definições de Métricas

### Confusion Matrix

As decisões dos especialistas são classificadas em quatro categorias ao comparar com a decisão final do consenso:

- **True Positive (TP)**: Especialista aprovou **E** consenso aprovou
- **True Negative (TN)**: Especialista rejeitou **E** consenso rejeitou
- **False Positive (FP)**: Especialista aprovou **MAS** consenso rejeitou
- **False Negative (FN)**: Especialista rejeitou **MAS** consenso aprovou

> **Nota**: Recomendações `review_required` e `conditional` são **ignoradas** na classificação (categoria `unknown`).

### Métricas Derivadas

#### Agreement Rate (Taxa de Concordância)
```
agreement_rate = (TP + TN) / (TP + TN + FP + FN)
```
Porcentagem de vezes que o especialista concordou com a decisão final do consenso.

- **Ideal**: ≥ 0.85 (85%)
- **Alerta Warning**: < 0.70 (70%)
- **Alerta Critical**: < 0.50 (50%)

#### False Positive Rate
```
fp_rate = FP / (FP + TN)
```
Proporção de aprovações incorretas (especialista aprovou mas consenso rejeitou).

- **Ideal**: ≤ 0.10 (10%)
- **Alerta**: > 0.20 (20%)

#### False Negative Rate
```
fn_rate = FN / (FN + TP)
```
Proporção de rejeições incorretas (especialista rejeitou mas consenso aprovou).

- **Ideal**: ≤ 0.10 (10%)
- **Alerta**: > 0.20 (20%)

#### Precision (Precisão)
```
precision = TP / (TP + FP)
```
Quando o especialista aprova, qual a probabilidade de estar correto?

- **Ideal**: ≥ 0.80 (80%)
- **Alerta**: < 0.70 (70%)

#### Recall (Revocação)
```
recall = TP / (TP + FN)
```
Dos planos que deveriam ser aprovados, quantos o especialista capturou?

- **Ideal**: ≥ 0.80 (80%)
- **Alerta**: < 0.70 (70%)

#### F1 Score
```
f1_score = 2 * (precision * recall) / (precision + recall)
```
Média harmônica entre precision e recall (balanceamento geral).

- **Ideal**: ≥ 0.80 (80%)
- **Alerta**: < 0.70 (70%)

### Business Value (Valor de Negócio)

Conta aprovações corretas (TP) que resultaram em **tickets executados com sucesso** (status `COMPLETED`):

```
business_value = Σ { 1.0 | category == TP AND execution_status == COMPLETED }
```

## Fluxo de Dados

### 1. Coleta de Dados (BusinessMetricsCollector)

O `BusinessMetricsCollector` executa periodicamente (via CronJob) e:

1. **Busca opiniões** do ledger (`specialist_opinions` collection) nas últimas N horas
2. **Busca decisões** de consenso (`consensus_decisions` collection) no mesmo período
3. **Correlaciona** via `opinion_id` presente nos `specialist_votes` da decisão
4. **Classifica** cada par opinião-decisão em TP/TN/FP/FN
5. **Calcula métricas derivadas** por `specialist_type`
6. **Atualiza Prometheus** com gauges e counters
7. **(Opcional)** Busca status de execução dos tickets para calcular business value

### 2. Detecção de Anomalias (AnomalyDetector)

O `AnomalyDetector` usa **Isolation Forest** para identificar comportamento anômalo:

1. **Treinamento** (executado offline):
   - Coleta histórico de métricas (mínimo 100 amostras)
   - Treina Isolation Forest com `contamination=0.1`
   - Salva modelo versionado em `/data/models/`

2. **Detecção** (executada a cada coleta):
   - Normaliza métricas atuais com StandardScaler
   - Calcula anomaly score (< 0 = anômalo)
   - Classifica severidade:
     - **Info**: score > -0.3
     - **Warning**: -0.5 < score ≤ -0.3
     - **Critical**: score ≤ -0.5
   - Identifica features anômalas (z-score > 2.0)
   - Atualiza métrica `neural_hive_anomaly_detected_total`

## Configuração

### Variáveis de Ambiente

```yaml
# Habilitar business metrics
ENABLE_BUSINESS_METRICS: "true"

# Janela de tempo para coleta (em horas)
BUSINESS_METRICS_WINDOW_HOURS: "24"

# MongoDB URIs
MONGODB_URI: "mongodb://neural-hive-mongodb:27017"
CONSENSUS_MONGODB_URI: "mongodb://neural-hive-mongodb:27017"

# Collections
MONGODB_OPINIONS_COLLECTION: "specialist_opinions"
CONSENSUS_COLLECTION_NAME: "consensus_decisions"
CONSENSUS_TIMESTAMP_FIELD: "timestamp"

# Business Value Tracking (opcional)
ENABLE_BUSINESS_VALUE_TRACKING: "true"
EXECUTION_TICKET_API_URL: "http://execution-ticket-service:8080"

# Anomaly Detection
ENABLE_ANOMALY_DETECTION: "true"
ANOMALY_CONTAMINATION: "0.1"
ANOMALY_N_ESTIMATORS: "100"
ANOMALY_MODEL_PATH: "/data/models/anomaly_detector_{specialist_type}.pkl"
ANOMALY_ALERT_THRESHOLD: "-0.3"
```

### Flags no Config

```python
config = {
    'enable_business_metrics': True,
    'business_metrics_window_hours': 24,
    'enable_business_value_tracking': True,
    'execution_ticket_api_url': 'http://execution-ticket-api:8080',
    'enable_anomaly_detection': True,
    'anomaly_contamination': 0.1,
    'anomaly_n_estimators': 100,
    'anomaly_model_path': '/data/models/anomaly_detector_{specialist_type}.pkl',
    'anomaly_alert_threshold': -0.3
}
```

## Como Executar

### CronJob de Coleta (Kubernetes)

O CronJob `business-metrics-collector` executa a cada hora:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: business-metrics-collector
spec:
  schedule: "0 * * * *"  # A cada hora
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: collector
            image: neural-hive/business-metrics-collector:latest
            env:
            - name: ENABLE_BUSINESS_METRICS
              value: "true"
            - name: BUSINESS_METRICS_WINDOW_HOURS
              value: "24"
```

**Verificar logs:**
```bash
kubectl logs -l component=business-metrics -n neural-hive-mind --tail=100
```

### Script de Coleta Manual

```python
from neural_hive_specialists.observability.business_metrics_collector import BusinessMetricsCollector

# Inicializar
collector = BusinessMetricsCollector(config, metrics_registry)

# Coletar métricas para últimas 24h
result = collector.collect_business_metrics(window_hours=24)

print(f"Status: {result['status']}")
print(f"Opiniões processadas: {result['opinions_processed']}")
print(f"Decisões processadas: {result['decisions_processed']}")
print(f"Correlações criadas: {result['correlations_created']}")
```

### Treinamento do Anomaly Detector

```python
from neural_hive_specialists.observability.anomaly_detector import AnomalyDetector

# Inicializar
detector = AnomalyDetector(config)

# Coletar histórico de métricas (mínimo 100 amostras)
metrics_history = fetch_metrics_history()  # Seu método de coleta

# Treinar e salvar modelo
success = detector.train_on_historical_data(
    metrics_history,
    specialist_type='technical'
)

if success:
    print("Modelo treinado e salvo com sucesso")
else:
    print("Falha no treinamento (dados insuficientes?)")
```

## Queries PromQL

### Agreement Rate por Especialista
```promql
neural_hive_business_consensus_agreement_rate{specialist_type="technical"}
```

### Agreement Rate Médio de Todos os Especialistas
```promql
avg(neural_hive_business_consensus_agreement_rate)
```

### Taxa de Falsos Positivos > 20%
```promql
neural_hive_business_false_positive_rate > 0.2
```

### F1 Score Abaixo do Threshold
```promql
neural_hive_business_f1_score < 0.7
```

### Confusion Matrix - Total de TPs
```promql
sum(neural_hive_business_true_positives_total{specialist_type="business"})
```

### Business Value Gerado (Taxa por Hora)
```promql
rate(neural_hive_business_value_generated_total[1h])
```

### Anomalias Críticas nas Últimas 24h
```promql
increase(neural_hive_anomaly_detected_total{severity="critical"}[24h])
```

### Métricas Desatualizadas (> 2 horas)
```promql
(time() - neural_hive_business_metrics_last_update_timestamp) > 7200
```

## Dashboard Grafana

O dashboard `business-metrics-dashboard.json` inclui:

### Painéis Principais

1. **Gauges**: Agreement Rate, Precision, Recall, F1 Score
2. **Stat Panels**: TP/TN/FP/FN totais por especialista
3. **Timeseries**: Agreement rate, FP/FN rates ao longo do tempo
4. **Bar Charts**: Precision/Recall/F1 por especialista
5. **Counters**: Business value gerado (total e taxa)
6. **Anomaly Timeline**: Anomalias detectadas com severidade

### Template Variables

- `$specialist_type`: Filtra por tipo de especialista (multi-select)
- `$environment`: Filtra por ambiente (dev, staging, prod)

### Importar Dashboard

```bash
# Via UI do Grafana
1. Acessar Grafana → Dashboards → Import
2. Upload do arquivo monitoring/dashboards/business-metrics-dashboard.json
3. Selecionar datasource Prometheus
4. Clicar em Import

# Via API
curl -X POST http://grafana:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @monitoring/dashboards/business-metrics-dashboard.json
```

## Alertas

Os alertas estão configurados em `monitoring/alerts/business-metrics-alerts.yaml` e são roteados por `specialist_type`.

### Alertas de Concordância

#### `LowConsensusAgreementRate`
- **Trigger**: Agreement rate < 70% por 1 hora
- **Severidade**: Warning
- **Ação**: Revisar modelo e heurísticas

#### `VeryLowConsensusAgreement`
- **Trigger**: Agreement rate < 50% por 30 minutos
- **Severidade**: Critical (PagerDuty)
- **Ação**: Revisão urgente do especialista

### Alertas de FP/FN

#### `HighFalsePositiveRate`
- **Trigger**: FP rate > 20% por 1 hora
- **Severidade**: Warning
- **Causa**: Especialista muito permissivo
- **Ação**: Revisar thresholds de aprovação

#### `HighFalseNegativeRate`
- **Trigger**: FN rate > 20% por 1 hora
- **Severidade**: Warning
- **Causa**: Especialista muito restritivo
- **Ação**: Revisar critérios de rejeição

### Alertas de Qualidade

#### `LowPrecisionScore`
- **Trigger**: Precision < 70% por 1 hora
- **Severidade**: Warning
- **Causa**: Muitos falsos positivos

#### `LowRecallScore`
- **Trigger**: Recall < 70% por 1 hora
- **Severidade**: Warning
- **Causa**: Muitos falsos negativos

#### `LowF1Score`
- **Trigger**: F1 < 70% por 1 hora
- **Severidade**: Warning
- **Causa**: Desbalanceamento entre precision e recall

### Alertas de Anomalias

#### `MetricsAnomalyDetected`
- **Trigger**: Anomalia detectada (severity=warning)
- **Severidade**: Warning
- **Ação**: Investigar métricas no Grafana

#### `MetricsCriticalAnomalyDetected`
- **Trigger**: Anomalia crítica detectada (severity=critical)
- **Severidade**: Critical (PagerDuty)
- **Ação**: Revisão urgente do especialista

### Alertas de Infraestrutura

#### `BusinessMetricsStale`
- **Trigger**: Métricas não atualizadas há > 2 horas
- **Severidade**: Warning
- **Causa**: CronJob não executando ou falhas no collector
- **Ação**: Verificar logs do CronJob

#### `BusinessMetricsCollectionFailing`
- **Trigger**: Job de coleta falhando ou não concluindo
- **Severidade**: Warning
- **Ação**: Verificar logs e conectividade com MongoDB

### Roteamento de Alertas

Alertas são roteados via Alertmanager com base no `specialist_type`:

```yaml
routes:
  - match:
      neural_hive_component: business-metrics
    receiver: business-metrics-team
    continue: true

  - match:
      severity: critical
      pagerduty: "true"
    receiver: pagerduty-critical
```

## Troubleshooting

### Problema: Métricas Desatualizadas

**Sintoma**: `neural_hive_business_metrics_last_update_timestamp` > 2 horas atrás

**Diagnóstico**:
```bash
# Verificar status do CronJob
kubectl get cronjob business-metrics-collector -n neural-hive-mind

# Verificar jobs executados
kubectl get jobs -l component=business-metrics -n neural-hive-mind

# Ver logs do último job
kubectl logs job/business-metrics-collector-XXXXX -n neural-hive-mind
```

**Causas Comuns**:
1. CronJob suspenso ou não agendado
2. Falhas de conectividade com MongoDB
3. Timeout ao processar grandes volumes de dados
4. Falta de recursos (CPU/memória)

**Solução**:
```bash
# Forçar execução manual
kubectl create job business-metrics-manual --from=cronjob/business-metrics-collector

# Verificar recursos
kubectl describe cronjob business-metrics-collector

# Aumentar timeout se necessário
# Editar spec.jobTemplate.spec.activeDeadlineSeconds
```

### Problema: Agreement Rate Baixo

**Sintoma**: `neural_hive_business_consensus_agreement_rate` < 70%

**Diagnóstico**:
1. Verificar confusion matrix: altos FP ou FN?
2. Comparar com métricas de outros especialistas
3. Verificar logs do especialista para padrões

**Possíveis Causas**:
- **Altos FP**: Modelo muito permissivo → Aumentar threshold de confiança
- **Altos FN**: Modelo muito restritivo → Reduzir threshold de risco
- **Dados de treinamento desatualizados**: Re-treinar modelo
- **Heurísticas desalinhadas**: Revisar lógica de avaliação

**Ações**:
```python
# Analisar distribuição de recomendações
specialist_votes = get_specialist_votes('technical')
print(Counter([v['recommendation'] for v in specialist_votes]))

# Verificar confidence scores
confidence_scores = [v['confidence_score'] for v in specialist_votes if v['recommendation'] == 'approve']
print(f"Mean: {np.mean(confidence_scores)}, Std: {np.std(confidence_scores)}")
```

### Problema: Anomalias Frequentes

**Sintoma**: Múltiplas `MetricsAnomalyDetected` alerts

**Diagnóstico**:
1. Verificar `anomalous_features` no resultado da detecção
2. Comparar métricas atuais com histórico
3. Verificar se houve deploy recente de modelo

**Possíveis Causas**:
- Deploy de novo modelo causando mudança de comportamento
- Mudança no padrão de entrada (dados diferentes)
- Modelo de anomalia desatualizado (treinado com dados antigos)

**Ações**:
```python
# Re-treinar modelo de anomalia com dados recentes
detector = AnomalyDetector(config)
recent_metrics = fetch_metrics_history(days=30)
detector.train_on_historical_data(recent_metrics, specialist_type='technical')
```

### Problema: Business Value Baixo

**Sintoma**: `rate(neural_hive_business_value_generated_total[1h])` próximo de zero

**Diagnóstico**:
1. Verificar se planos estão sendo aprovados (TPs > 0)
2. Verificar status de execução dos tickets
3. Verificar conectividade com Execution Ticket API

**Possíveis Causas**:
- Poucos planos aprovados pelo consenso
- Tickets falhando na execução
- Execution Ticket API indisponível
- `ENABLE_BUSINESS_VALUE_TRACKING` desabilitado

**Ações**:
```bash
# Testar conectividade com Execution Ticket API
kubectl exec -it deployment/business-metrics-collector -- \
  curl http://execution-ticket-service:8080/api/v1/health

# Verificar execuções recentes
curl http://execution-ticket-service:8080/api/v1/tickets?status=COMPLETED&limit=10
```

### Problema: Modelo de Anomalia Não Carrega

**Sintoma**: Logs mostram "Model file not found"

**Diagnóstico**:
```bash
# Verificar se modelo existe
kubectl exec -it deployment/specialist-technical -- \
  ls -lh /data/models/

# Verificar permissões
kubectl exec -it deployment/specialist-technical -- \
  ls -lhd /data/models/
```

**Solução**:
```bash
# Treinar modelo manualmente
python3 scripts/train_anomaly_detector.py --specialist-type technical

# Verificar volume montado corretamente
kubectl describe pod specialist-technical-XXX | grep Mounts -A 10
```

## Referências

### Código-Fonte

- `libraries/python/neural_hive_specialists/observability/business_metrics_collector.py`
- `libraries/python/neural_hive_specialists/observability/anomaly_detector.py`
- `libraries/python/neural_hive_specialists/metrics.py`

### Testes

- `libraries/python/neural_hive_specialists/tests/test_business_metrics_collector.py`
- `libraries/python/neural_hive_specialists/tests/test_anomaly_detector.py`

### Configuração

- `monitoring/alerts/business-metrics-alerts.yaml`
- `monitoring/dashboards/business-metrics-dashboard.json`

### Documentação Adicional

- [Isolation Forest Paper](https://cs.nju.edu.cn/zhouzh/zhouzh.files/publication/icdm08b.pdf)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/)
- [Grafana Dashboard Best Practices](https://grafana.com/docs/grafana/latest/best-practices/)
