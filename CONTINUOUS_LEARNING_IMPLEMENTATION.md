# Sistema de Continuous Learning com Feedback Humano - Neural Hive Mind

## 📋 Visão Geral

Sistema completo de **continuous learning** implementado para os especialistas do Neural Hive Mind, permitindo que revisores humanos forneçam feedback sobre opiniões e que o sistema re-treine automaticamente os modelos quando threshold de feedback é atingido.

## 🎯 Funcionalidades Implementadas

### 1. Coleta de Feedback Humano
- ✅ API REST para submissão de feedback via HTTP
- ✅ Validação rigorosa com Pydantic schemas
- ✅ Autenticação JWT para controle de acesso
- ✅ Persistência em MongoDB com índices otimizados
- ✅ Auditoria completa via AuditLogger
- ✅ Circuit breaker para resiliência

### 2. Trigger Automático de Re-treinamento
- ✅ Monitoramento de threshold de feedback (default: ≥100 feedbacks/semana)
- ✅ Cooldown de 24h para evitar triggers duplicados
- ✅ Integração com MLflow para disparar pipelines
- ✅ Histórico completo de triggers no MongoDB
- ✅ CronJob Kubernetes para verificação periódica

### 3. Pipeline MLflow de Treinamento
- ✅ Script Python completo de treinamento
- ✅ Enriquecimento de dataset base com feedback humano
- ✅ Suporte para múltiplos tipos de modelo (Random Forest, Gradient Boosting, Neural Network)
- ✅ Avaliação automática de performance (precision, recall, F1)
- ✅ Comparação com modelo baseline
- ✅ Promoção automática para Production se melhor

### 4. Métricas e Observabilidade
- ✅ 12 métricas Prometheus para feedback
- ✅ 6 métricas Prometheus para re-treinamento
- ✅ Integração com Prometheus Pushgateway
- ✅ Dashboards Grafana ready

## 🏗️ Arquitetura

```
┌─────────────────┐
│ Revisor Humano  │
└────────┬────────┘
         │ POST /api/v1/feedback
         ↓
┌────────────────────────────────────────┐
│   Specialist HTTP Server (FastAPI)    │
│   - specialist-technical:8000          │
│   - specialist-business:8000           │
│   - specialist-behavior:8000           │
│   - specialist-evolution:8000          │
│   - specialist-architecture:8000       │
└────────┬───────────────────────────────┘
         │
         ↓
┌────────────────────────────────────────┐
│      FeedbackCollector                 │
│   - Valida opinião existe              │
│   - Valida schema Pydantic             │
│   - Persiste no MongoDB                │
│   - Audita submissão                   │
└────────┬───────────────────────────────┘
         │
         ↓
┌────────────────────────────────────────┐
│   MongoDB: specialist_feedback         │
│   - Índices: opinion_id, specialist    │
│   - Índice composto: type + timestamp  │
└────────┬───────────────────────────────┘
         │
         ↓
┌────────────────────────────────────────┐
│   CronJob: retraining-trigger-checker  │
│   - Executa: Domingo 3h UTC            │
│   - Script: run_retraining_trigger.py  │
└────────┬───────────────────────────────┘
         │
         ↓
┌────────────────────────────────────────┐
│      RetrainingTrigger                 │
│   - Verifica threshold ≥100            │
│   - Verifica cooldown < 24h            │
│   - Dispara pipeline MLflow            │
└────────┬───────────────────────────────┘
         │
         ↓
┌────────────────────────────────────────┐
│   MLflow Training Pipeline             │
│   - Carrega dataset base               │
│   - Carrega feedbacks do MongoDB       │
│   - Enriquece dataset                  │
│   - Treina modelo                      │
│   - Avalia performance                 │
│   - Registra no Model Registry         │
└────────┬───────────────────────────────┘
         │
         ↓
┌────────────────────────────────────────┐
│   MLflow Model Registry                │
│   - Staging: modelo re-treinado        │
│   - Production: baseline atual         │
│   - Promoção se precision > base + 5%  │
└────────────────────────────────────────┘
```

## 📁 Estrutura de Arquivos

### Bibliotecas Core
```
libraries/python/neural_hive_specialists/
├── config.py                              # ✅ Configurações de feedback/retraining
├── metrics.py                             # ✅ Métricas Prometheus
├── feedback/
│   ├── __init__.py                       # ✅ Exports do módulo
│   ├── feedback_collector.py             # ✅ FeedbackCollector + FeedbackDocument
│   ├── retraining_trigger.py             # ✅ RetrainingTrigger + TriggerRecord
│   └── feedback_api.py                   # ✅ FastAPI router
├── scripts/
│   └── run_retraining_trigger.py         # ✅ Script CLI para trigger
└── tests/
    ├── test_feedback_collector.py        # ✅ Testes unitários
    ├── test_retraining_trigger.py        # ✅ Testes unitários
    └── test_feedback_api.py              # ✅ Testes de integração
```

### Serviços (Especialistas)
```
services/specialist-{type}/src/
└── http_server_fastapi.py                # ✅ Integração FeedbackAPI
```
Aplicado em: technical, business, behavior, evolution, architecture

### Pipeline MLflow
```
ml_pipelines/training/
├── MLproject                              # ✅ Definição do pipeline
├── conda.yaml                             # ✅ Ambiente conda
└── train_specialist_model.py             # ✅ Script de treinamento
```

### Infraestrutura Kubernetes
```
k8s/cronjobs/
└── retraining-trigger-job.yaml           # ✅ CronJob semanal
```

### Build e Deploy
```
Makefile                                   # ✅ Targets de continuous learning
```

## 🔧 Configuração

### Variáveis de Ambiente

```bash
# Feedback Collection
ENABLE_FEEDBACK_COLLECTION=true
FEEDBACK_MONGODB_COLLECTION=specialist_feedback
FEEDBACK_API_ENABLED=true
FEEDBACK_REQUIRE_AUTHENTICATION=true
FEEDBACK_ALLOWED_ROLES=admin,specialist_reviewer,human_expert
FEEDBACK_RATING_MIN=0.0
FEEDBACK_RATING_MAX=1.0

# Retraining Trigger
ENABLE_RETRAINING_TRIGGER=true
RETRAINING_FEEDBACK_THRESHOLD=100
RETRAINING_FEEDBACK_WINDOW_DAYS=7
RETRAINING_TRIGGER_SCHEDULE_CRON='0 3 * * 0'
RETRAINING_MLFLOW_PROJECT_URI=./ml_pipelines/training
RETRAINING_MIN_FEEDBACK_QUALITY=0.5

# Training Pipeline
TRAINING_DATASET_PATH=/data/training/specialist_{specialist_type}_base.parquet
TRAINING_VALIDATION_SPLIT=0.2
TRAINING_TEST_SPLIT=0.1
TRAINING_RANDOM_SEED=42
TRAINING_MODEL_TYPES=random_forest,gradient_boosting
TRAINING_HYPERPARAMETER_TUNING=false
TRAINING_PROMOTION_PRECISION_THRESHOLD=0.75
TRAINING_PROMOTION_RECALL_THRESHOLD=0.70
```

## 🚀 Uso

### 1. Submeter Feedback

```bash
curl -X POST http://specialist-technical:8000/api/v1/feedback \
  -H "Authorization: Bearer <jwt-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "opinion_id": "opinion-abc123",
    "human_rating": 0.9,
    "human_recommendation": "approve",
    "feedback_notes": "Análise de segurança correta e completa"
  }'
```

**Response:**
```json
{
  "feedback_id": "feedback-xyz789",
  "opinion_id": "opinion-abc123",
  "submitted_at": "2024-01-15T10:30:00Z",
  "status": "success"
}
```

### 2. Consultar Feedbacks

**Por opinião:**
```bash
curl http://specialist-technical:8000/api/v1/feedback/opinion/opinion-abc123
```

**Estatísticas:**
```bash
curl "http://specialist-technical:8000/api/v1/feedback/stats?specialist_type=technical&window_days=30"
```

### 3. Verificar Threshold (Dry-run)

```bash
make check-retraining-trigger
```

ou

```bash
cd libraries/python/neural_hive_specialists
python -m scripts.run_retraining_trigger --dry-run
```

### 4. Disparar Re-treinamento Manual

```bash
make trigger-retraining SPECIALIST_TYPE=technical
```

ou

```bash
cd libraries/python/neural_hive_specialists
python -m scripts.run_retraining_trigger --specialist-type technical --force
```

### 5. Deploy CronJob

```bash
make deploy-retraining-cronjob
```

ou

```bash
kubectl apply -f k8s/cronjobs/retraining-trigger-job.yaml
```

### 6. Executar Testes

```bash
make test-feedback
```

ou

```bash
cd libraries/python/neural_hive_specialists
pytest tests/test_feedback_collector.py \
       tests/test_retraining_trigger.py \
       tests/test_feedback_api.py \
       -v --cov=neural_hive_specialists/feedback
```

## 📊 Métricas Prometheus

### Feedback Metrics

```promql
# Total de feedbacks submetidos
neural_hive_feedback_submissions_total{specialist_type="technical"}

# Rating médio
neural_hive_feedback_avg_rating{specialist_type="technical"}

# Distribuição de ratings
neural_hive_feedback_rating_distribution{specialist_type="technical"}

# Distribuição de recomendações
neural_hive_feedback_recommendation_distribution{specialist_type="technical", human_recommendation="approve"}

# Contagem atual na janela de trigger
neural_hive_feedback_count_current{specialist_type="technical"}

# Erros na API
neural_hive_feedback_api_errors_total{specialist_type="technical", error_type="validation"}
```

### Retraining Metrics

```promql
# Total de triggers disparados
neural_hive_retraining_triggers_total{specialist_type="technical", status="success"}

# Threshold configurado
neural_hive_retraining_feedback_threshold{specialist_type="technical"}

# Último trigger
neural_hive_retraining_last_trigger_timestamp{specialist_type="technical"}

# Duração de runs MLflow
neural_hive_retraining_mlflow_run_duration_seconds{specialist_type="technical"}

# Performance do modelo re-treinado
neural_hive_retraining_model_performance{specialist_type="technical", metric_name="precision"}

# Tamanho do dataset
neural_hive_retraining_dataset_size{specialist_type="technical", dataset_type="total"}
```

## 🔐 Autenticação

### Gerar Token JWT

```python
import jwt
from datetime import datetime, timedelta

payload = {
    'sub': 'reviewer@example.com',
    'role': 'human_expert',
    'iat': datetime.utcnow(),
    'exp': datetime.utcnow() + timedelta(hours=1)
}

token = jwt.encode(payload, 'your-secret-key', algorithm='HS256')
```

### Roles Permitidos

- `admin` - Acesso completo
- `specialist_reviewer` - Revisor de especialistas
- `human_expert` - Expert humano

## 🧪 Testes

### Cobertura de Testes

```
test_feedback_collector.py:
  ✅ Validação de schema FeedbackDocument
  ✅ Submissão de feedback (success, errors)
  ✅ Validação de opinião existe
  ✅ Consulta de feedbacks
  ✅ Cálculo de estatísticas
  ✅ Auditoria de submissões

test_retraining_trigger.py:
  ✅ Verificação de threshold
  ✅ Cooldown logic
  ✅ Inicialização de MLflow run
  ✅ Trigger de re-treinamento
  ✅ Tratamento de erros
  ✅ Force mode

test_feedback_api.py:
  ✅ Endpoints REST (POST, GET)
  ✅ Validação de requests
  ✅ Autenticação JWT
  ✅ Error handling (404, 422, 503)
```

## 📈 Fluxo de Continuous Learning

### Passo a Passo

1. **Especialista gera opinião** → Persiste no ledger (`cognitive_ledger`)

2. **Revisor humano avalia opinião** → Submete feedback via API
   - `POST /api/v1/feedback`
   - Validação: opinião existe, rating válido, recomendação válida
   - Persiste em `specialist_feedback` collection

3. **CronJob semanal executa** (Domingo 3h UTC)
   - Script: `run_retraining_trigger.py`
   - Conta feedbacks dos últimos 7 dias

4. **Threshold verificado** (≥100 feedbacks)
   - Se atingido E sem cooldown → Dispara trigger
   - Se não atingido → Aguarda mais feedbacks

5. **MLflow Pipeline iniciado**
   - Carrega dataset base (Parquet)
   - Carrega feedbacks do MongoDB (últimos 30 dias, rating ≥ 0.5)
   - Enriquece dataset: base + feedback

6. **Modelo treinado**
   - Random Forest / Gradient Boosting / Neural Network
   - Split: 70% train, 20% validation, 10% test
   - Métricas calculadas: precision, recall, F1, accuracy

7. **Modelo registrado no MLflow**
   - Model Registry: `{specialist_type}-model`
   - Stage inicial: **Staging**

8. **Comparação com baseline**
   - Busca modelo atual em **Production**
   - Compara precision/recall
   - Se novo modelo melhor (precision > baseline + 5%):
     - ✅ Promove para **Production**
     - Arquiva baseline anterior
   - Senão:
     - ℹ️ Mantém em **Staging**

## 🎯 Critérios de Promoção

Para um modelo ser promovido para Production, deve atender **TODOS** os critérios:

1. **Precision** ≥ 0.75 (threshold absoluto)
2. **Recall** ≥ 0.70 (threshold absoluto)
3. **Precision** > baseline_precision + 0.05 (melhoria de 5%)

## 🛠️ Troubleshooting

### Problema: Feedback não aceito (404)

**Causa:** Opinião não encontrada no ledger

**Solução:**
```bash
# Verificar se opinião existe
mongo neural_hive
db.cognitive_ledger.findOne({opinion_id: "opinion-abc123"})
```

### Problema: Re-treinamento não dispara

**Causa 1:** Threshold não atingido

**Solução:**
```bash
# Verificar contagem de feedbacks
python -m scripts.run_retraining_trigger --dry-run
```

**Causa 2:** Cooldown ativo

**Solução:**
```bash
# Verificar último trigger
mongo neural_hive
db.retraining_triggers.find({specialist_type: "technical"}).sort({triggered_at: -1}).limit(1)

# Forçar trigger ignorando cooldown
python -m scripts.run_retraining_trigger --specialist-type technical --force
```

### Problema: Modelo não promovido

**Causa:** Performance abaixo do baseline

**Solução:**
```bash
# Verificar métricas no MLflow
mlflow ui

# Ajustar thresholds de promoção
export TRAINING_PROMOTION_PRECISION_THRESHOLD=0.70
export TRAINING_PROMOTION_RECALL_THRESHOLD=0.65
```

### Problema: CronJob não executa

**Solução:**
```bash
# Verificar CronJob
kubectl get cronjobs -n neural-hive-mind

# Verificar última execução
kubectl get jobs -n neural-hive-mind | grep retraining-trigger

# Verificar logs
kubectl logs -n neural-hive-mind -l job-name=retraining-trigger-checker-<timestamp>
```

## 🔮 Roadmap Futuro

### Funcionalidades Planejadas

- [ ] **Active Learning**: Selecionar opiniões mais incertas para feedback
- [ ] **Feedback Ponderado**: Dar mais peso a revisores experientes
- [ ] **Feedback Negativo**: Reportar erros graves com alta prioridade
- [ ] **Dashboard de Feedback**: UI web para revisores
- [ ] **Integração com Tickets**: Feedback via sistema de tickets
- [ ] **Análise de Drift**: Detectar mudanças na distribuição de feedbacks
- [ ] **Multi-Modal Feedback**: Suporte para feedback em áudio/vídeo
- [ ] **Feedback Automatizado**: Usar LLMs para gerar feedback sintético

## 📚 Referências

- [MLflow Documentation](https://mlflow.org/docs/latest/index.html)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Prometheus Metrics](https://prometheus.io/docs/concepts/metric_types/)
- [Kubernetes CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)

## ✅ Checklist de Implementação

- [x] Configuração em `config.py`
- [x] Módulo `feedback/` completo
- [x] Integração com todos os 5 especialistas
- [x] Métricas Prometheus
- [x] Script `run_retraining_trigger.py`
- [x] Pipeline MLflow `train_specialist_model.py`
- [x] Arquivos MLproject e conda.yaml
- [x] CronJob Kubernetes
- [x] Testes unitários e de integração
- [x] Makefile targets
- [x] Documentação

## 🎉 Conclusão

Sistema de **continuous learning completo e funcional** implementado para o Neural Hive Mind, permitindo:

1. ✅ Coleta estruturada de feedback humano
2. ✅ Trigger automático de re-treinamento
3. ✅ Pipeline MLflow de treinamento
4. ✅ Promoção automática de modelos
5. ✅ Observabilidade completa com Prometheus
6. ✅ Testes unitários e de integração
7. ✅ Deploy via Kubernetes CronJob

O sistema está pronto para uso em produção! 🚀
