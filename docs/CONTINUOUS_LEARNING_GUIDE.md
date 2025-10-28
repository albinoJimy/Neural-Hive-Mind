# Guia de Continuous Learning com Feedback Humano

## Visão Geral

O sistema de Continuous Learning do Neural Hive Mind permite que os especialistas melhorem continuamente através de feedback humano. Este guia documenta a arquitetura, uso e operação do sistema.

## Arquitetura

### Componentes Principais

```
┌─────────────────────┐
│  Especialista AI    │
│   (FastAPI)         │
│  ┌──────────────┐   │
│  │ POST /feedback│◄──┼────┐
│  └──────────────┘   │    │
│  ┌──────────────┐   │    │  1. Submissão de Feedback
│  │GET /feedback/ │   │    │
│  │  stats        │   │    │
│  └──────────────┘   │    │
└─────────┬───────────┘    │
          │                │
          │ 2. Persiste    │
          ▼                │
┌─────────────────────┐    │
│  FeedbackCollector  │    │
│    (MongoDB)        │    │
│                     │    │
│  • feedback_notes   │    │
│    (anonimizado)    │    │
│  • human_rating     │    │
│  • recommendation   │    │
└─────────┬───────────┘    │
          │                │
          │ 3. Monitora    │
          ▼                │
┌─────────────────────┐    │
│ RetrainingTrigger   │    │
│                     │    │
│ • Verifica threshold│    │
│ • Cooldown (24h)    │    │
│ • Dispara MLflow    │    │
└─────────┬───────────┘    │
          │                │
          │ 4. Inicia      │
          ▼                │
┌─────────────────────┐    │
│   MLflow Project    │    │
│                     │    │
│ • Enriquece dataset │    │
│ • Treina modelo     │    │
│ • Avalia performance│    │
│ • Promove se melhor │    │
└─────────┬───────────┘    │
          │                │
          │ 5. Notifica    │
          ▼                │
┌─────────────────────┐    │
│ Monitor Script      │    │
│  (CronJob 5min)     │    │
│                     │    │
│ • Atualiza status   │    │
│ • Emite métricas    │    │
│ • Libera cooldown   │    │
└─────────────────────┘    │
                           │
       Revisor Humano ─────┘
```

### Fluxo de Dados

1. **Submissão de Feedback**
   - Revisor humano avalia opinião do especialista
   - Submete rating (0.0-1.0) e recomendação (approve/reject/review_required)
   - Feedback notes são anonimizados via PIIDetector (Presidio)
   - Persistido no MongoDB com metadados

2. **Monitoramento de Threshold**
   - RetrainingTrigger conta feedbacks na janela de tempo (ex: 7 dias)
   - Quando atinge threshold (ex: 100 feedbacks):
     - Verifica cooldown (24h desde último trigger)
     - Dispara pipeline MLflow se elegível

3. **Pipeline MLflow**
   - Extrai feedbacks do MongoDB
   - Enriquece dataset de treinamento
   - Treina novos modelos
   - Avalia métricas (precision, recall, F1)
   - Promove modelo se performance melhorar

4. **Monitoramento de Runs**
   - Script executa periodicamente (CronJob)
   - Verifica status de runs assíncronos
   - Atualiza registros de trigger
   - Emite métricas Prometheus
   - Libera cooldown após conclusão

## API de Feedback

### Autenticação

Todos os endpoints requerem JWT Bearer token (exceto se `FEEDBACK_REQUIRE_AUTHENTICATION=false`):

```bash
curl -H "Authorization: Bearer <jwt-token>" \
  https://specialist-technical/api/v1/feedback
```

**Roles permitidos** (configurável via `FEEDBACK_ALLOWED_ROLES`):
- `human_expert`
- `reviewer`
- `admin`

### Endpoints

#### POST /api/v1/feedback

Submete feedback sobre uma opinião.

**Request:**
```json
{
  "opinion_id": "opinion-abc123",
  "human_rating": 0.85,
  "human_recommendation": "approve",
  "feedback_notes": "Análise correta e bem fundamentada",
  "submitted_by": "revisor@example.com"
}
```

**Response:**
```json
{
  "feedback_id": "feedback-xyz789",
  "opinion_id": "opinion-abc123",
  "submitted_at": "2025-10-11T14:30:00Z",
  "status": "success"
}
```

**Status Codes:**
- `201`: Feedback criado com sucesso
- `400`: Validação falhou
- `401`: Token JWT ausente ou inválido
- `403`: Role sem permissão
- `404`: Opinião não encontrada
- `503`: Serviço indisponível (circuit breaker aberto)

#### GET /api/v1/feedback/opinion/{opinion_id}

Busca feedbacks de uma opinião específica.

**Response:**
```json
{
  "feedbacks": [
    {
      "feedback_id": "feedback-xyz789",
      "opinion_id": "opinion-abc123",
      "human_rating": 0.85,
      "human_recommendation": "approve",
      "feedback_notes": "Análise correta",
      "submitted_by": "revisor@example.com",
      "submitted_at": "2025-10-11T14:30:00Z"
    }
  ],
  "count": 1
}
```

#### GET /api/v1/feedback/stats

Retorna estatísticas agregadas de feedback.

**Query Parameters:**
- `specialist_type`: Tipo do especialista
- `window_days`: Janela de tempo em dias (default: 30)

**Response:**
```json
{
  "count": 150,
  "avg_rating": 0.82,
  "distribution": {
    "approve": 120,
    "reject": 20,
    "review_required": 10
  },
  "specialist_type": "technical",
  "window_days": 30,
  "min_rating": 0.35,
  "max_rating": 0.98
}
```

## Trigger de Re-Treinamento

### Configuração

Variáveis de ambiente:

```bash
# Habilitar trigger automático
ENABLE_RETRAINING_TRIGGER=true

# Threshold de feedbacks para disparar
RETRAINING_FEEDBACK_THRESHOLD=100

# Janela de tempo para contar feedbacks (dias)
RETRAINING_FEEDBACK_WINDOW_DAYS=7

# Qualidade mínima de feedback para incluir no dataset
RETRAINING_MIN_FEEDBACK_QUALITY=0.5

# URI do projeto MLflow
RETRAINING_MLFLOW_PROJECT_URI=./ml_pipelines/training

# URI do tracking server
MLFLOW_TRACKING_URI=http://mlflow-server:5000
```

### Comportamento do Trigger

1. **Verificação de Threshold**
   - Conta feedbacks na janela de tempo
   - Se `count >= threshold`, continua verificação

2. **Cooldown**
   - Previne triggers duplicados
   - Default: 24 horas desde último trigger bem-sucedido
   - Inclui triggers em execução (`running`) e completados (`completed`)

3. **Disparo do MLflow**
   - Cria registro de trigger no MongoDB
   - Inicia `mlflow.projects.run()` assíncrono
   - Status: `pending` → `running`
   - Emite métricas Prometheus

4. **Monitoramento de Execução**
   - Script `monitor_retraining_runs.py` verifica status
   - Atualiza registro quando run termina
   - Status: `running` → `completed`/`failed`
   - Libera cooldown

### Forçar Trigger Manual

```python
from neural_hive_specialists.feedback import RetrainingTrigger

trigger = RetrainingTrigger(config, feedback_collector, metrics=metrics)

# Ignorar cooldown e threshold
trigger_id = trigger.check_and_trigger(
    specialist_type='technical',
    force=True
)
```

## Pipeline MLflow

### Estrutura do Projeto

```
ml_pipelines/training/
├── MLproject                 # Definição do projeto
├── conda.yaml                # Ambiente conda
├── train.py                  # Script principal
├── data/
│   ├── fetch_feedback.py     # Busca feedbacks do MongoDB
│   └── enrich_dataset.py     # Enriquece dataset base
├── models/
│   ├── train_model.py        # Treina modelos
│   └── evaluate_model.py     # Avalia performance
└── promote/
    └── promote_model.py      # Promove se melhor
```

### Parâmetros Aceitos

- `specialist_type`: Tipo do especialista (ex: technical, business)
- `feedback_count`: Quantidade de feedbacks disponíveis
- `window_days`: Janela de tempo dos feedbacks
- `min_feedback_quality`: Rating mínimo para incluir
- `model_type`: Tipo de modelo a treinar
- `hyperparameter_tuning`: `true`/`false`
- `promote_if_better`: `true`/`false`

### Execução Manual

```bash
mlflow run ./ml_pipelines/training \
  -P specialist_type=technical \
  -P feedback_count=150 \
  -P window_days=7 \
  -P min_feedback_quality=0.5 \
  -P model_type=random_forest \
  -P hyperparameter_tuning=true \
  -P promote_if_better=true
```

## Métricas Prometheus

### Métricas de Feedback

```promql
# Total de submissões por role
neural_hive_feedback_submissions_total{specialist_type="technical", submitted_by_role="human_expert"}

# Distribuição de ratings
neural_hive_feedback_rating_distribution{specialist_type="technical"}

# Distribuição de recomendações
neural_hive_feedback_recommendation_distribution{specialist_type="technical", human_recommendation="approve"}

# Contagem atual na janela de trigger
neural_hive_feedback_count_current{specialist_type="technical"}

# Rating médio
neural_hive_feedback_avg_rating{specialist_type="technical"}

# Erros na API
neural_hive_feedback_api_errors_total{specialist_type="technical", error_type="validation"}
```

### Métricas de Retraining

```promql
# Triggers disparados
neural_hive_retraining_triggers_total{specialist_type="technical", status="success"}

# Threshold configurado
neural_hive_retraining_feedback_threshold{specialist_type="technical"}

# Timestamp do último trigger
neural_hive_retraining_last_trigger_timestamp{specialist_type="technical"}

# Duração de runs MLflow
neural_hive_retraining_mlflow_run_duration_seconds{specialist_type="technical"}

# Performance do modelo re-treinado
neural_hive_retraining_model_performance{specialist_type="technical", metric_name="precision"}

# Tamanho do dataset
neural_hive_retraining_dataset_size{specialist_type="technical", dataset_type="total"}
```

### Métricas de PII

```promql
# Entidades PII detectadas
neural_hive_compliance_pii_entities_detected_total{specialist_type="technical", entity_type="PERSON"}

# Anonimizações aplicadas
neural_hive_compliance_pii_anonymization_total{specialist_type="technical", strategy="replace"}

# Erros de detecção
neural_hive_compliance_pii_detection_errors_total{specialist_type="technical", error_type="anonymization_failed"}
```

## Monitoramento via Script

### Instalação do CronJob

**Kubernetes CronJob:**

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: monitor-retraining-runs
  namespace: neural-hive-mind
spec:
  schedule: "*/5 * * * *"  # A cada 5 minutos
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: monitor
            image: neural-hive/specialist:latest
            command:
            - python3
            - /app/libraries/python/neural_hive_specialists/scripts/monitor_retraining_runs.py
            - --mongodb-uri
            - mongodb://neural-hive-mongodb:27017
            - --mongodb-database
            - neural_hive
            - --mlflow-tracking-uri
            - http://mlflow-server:5000
            - --max-run-age-hours
            - "24"
            env:
            - name: MONGODB_URI
              valueFrom:
                secretKeyRef:
                  name: mongodb-credentials
                  key: uri
          restartPolicy: OnFailure
```

**Cron tradicional:**

```bash
# /etc/cron.d/monitor-retraining

*/5 * * * * neural-hive \
  cd /app && \
  python3 libraries/python/neural_hive_specialists/scripts/monitor_retraining_runs.py \
  --mongodb-uri mongodb://localhost:27017 \
  --mongodb-database neural_hive \
  --mlflow-tracking-uri http://localhost:5000 \
  >> /var/log/monitor-retraining.log 2>&1
```

### Execução Manual

```bash
python3 libraries/python/neural_hive_specialists/scripts/monitor_retraining_runs.py \
  --mongodb-uri mongodb://localhost:27017 \
  --mongodb-database neural_hive \
  --mlflow-tracking-uri http://localhost:5000 \
  --max-run-age-hours 24
```

**Opções:**
- `--dry-run`: Executar sem atualizar database
- `--max-run-age-hours`: Idade máxima antes de timeout (default: 24)

**Saída:**
```
=== Resumo do Monitoramento ===
Triggers verificados: 5
Completados: 3
Falhados: 1
Timeout: 0
Ainda em execução: 1
Erros: 0
```

## Dashboard Grafana

Ver `monitoring/dashboards/continuous-learning-dashboard.json` para dashboard completo.

**Painéis principais:**
1. **Submissões de Feedback**: Taxa de submissão ao longo do tempo
2. **Distribuição de Ratings**: Histograma de ratings
3. **Threshold Progress**: Contagem atual vs threshold
4. **Triggers Disparados**: Linha do tempo de triggers
5. **Performance de Modelos**: Precision, Recall, F1 ao longo do tempo
6. **PII Detection**: Entidades detectadas e anonimizadas

## Alertas Prometheus

Ver `monitoring/alerts/continuous-learning-alerts.yaml` para regras completas.

**Alertas críticos:**

- **LowFeedbackSubmissionRate**: < 10 submissões/dia por 3 dias
- **RetrainingTriggerFailed**: Trigger falhou
- **MLflowRunStuckRunning**: Run em execução > 24h
- **HighPIIDetectionErrorRate**: > 10% de erros PII
- **FeedbackAPIHighErrorRate**: > 5% de erros na API

## Troubleshooting

### Problema: Trigger não dispara

**Sintomas:**
- Contagem de feedback atinge threshold
- Trigger não é disparado

**Verificações:**
1. Check se trigger está habilitado:
   ```bash
   echo $ENABLE_RETRAINING_TRIGGER  # Deve ser 'true'
   ```

2. Verificar cooldown:
   ```python
   from pymongo import MongoClient
   client = MongoClient('mongodb://localhost:27017')
   db = client['neural_hive']

   # Buscar último trigger
   last_trigger = db.retraining_triggers.find_one(
       {'specialist_type': 'technical'},
       sort=[('triggered_at', -1)]
   )
   print(last_trigger)
   ```

3. Forçar trigger manual:
   ```python
   trigger_id = trigger.check_and_trigger('technical', force=True)
   ```

### Problema: Run MLflow fica preso em "running"

**Sintomas:**
- Run iniciado há mais de 24h
- Status permanece `running`

**Solução:**
1. Verificar run no MLflow UI
2. Executar script de monitoramento manualmente:
   ```bash
   python3 monitor_retraining_runs.py
   ```
3. Se run realmente travou, marcar como failed:
   ```python
   db.retraining_triggers.update_one(
       {'trigger_id': 'trigger-xyz'},
       {'$set': {
           'status': 'failed',
           'completed_at': datetime.utcnow(),
           'metadata.error_message': 'Manual intervention - run stuck'
       }}
   )
   ```

### Problema: PII detection falha

**Sintomas:**
- Logs mostram: "Falha ao carregar modelos spaCy"

**Solução:**
```bash
# Instalar modelos spaCy
python -m spacy download pt_core_news_sm
python -m spacy download en_core_web_sm

# Verificar instalação
python -c "import spacy; nlp = spacy.load('pt_core_news_sm'); print('OK')"
```

### Problema: Circuit breaker aberto

**Sintomas:**
- HTTP 503 em `/feedback`
- Logs: "Circuit breaker open"

**Causas:**
- MongoDB indisponível
- 5+ falhas consecutivas

**Solução:**
1. Verificar conectividade MongoDB:
   ```bash
   mongosh mongodb://localhost:27017/neural_hive --eval "db.stats()"
   ```

2. Aguardar reset automático (60 segundos)

3. Verificar métricas:
   ```promql
   neural_hive_circuit_breaker_state{client_name="feedback_mongo"}
   ```

## Roadmap

### Fase 1 (Atual)
- ✅ API de feedback com autenticação
- ✅ Trigger automático de re-treinamento
- ✅ Pipeline MLflow básico
- ✅ Métricas Prometheus
- ✅ PII detection/anonymization

### Fase 2 (Próxima)
- [ ] Dashboard Grafana automatizado
- [ ] Notificações Slack/Email
- [ ] A/B testing de modelos
- [ ] Análise de feedback sentiment
- [ ] Export de dados para análise

### Fase 3 (Futuro)
- [ ] Active learning (sugestão de amostras)
- [ ] Feedback loop automático
- [ ] Multi-language support completo
- [ ] Integração com ferramentas de annotation

## Referências

- [MLflow Projects](https://mlflow.org/docs/latest/projects.html)
- [Presidio PII Detection](https://microsoft.github.io/presidio/)
- [Prometheus Client Python](https://github.com/prometheus/client_python)
- [PyBreaker Circuit Breaker](https://pypi.org/project/pybreaker/)
