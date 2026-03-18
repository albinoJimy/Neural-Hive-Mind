# Neural Hive ML - Biblioteca de Machine Learning

Biblioteca centralizada para modelos ML preditivos, online learning e MLOps para o Neural Hive Mind.

## Funcionalidades

### Modelos Preditivos
- **SchedulingPredictor**: Previsão de duração e recursos de tickets
- **LoadPredictor**: Previsão de carga do sistema
- **AnomalyDetector**: Detecção de anomalias em tempo real

### MLOps
- **MLflowClient**: Integração com MLflow para tracking e registry
- **ModelVersionRepository**: Histórico de versões no MongoDB
- **RetrainingJob**: Pipeline automatizado de retreino
- **DriftDetector**: Detecção de model drift
- **CanaryDeployer**: Deploy canary de novos modelos

## Instalação

```bash
pip install neural-hive-ml
```

## Configuração

### Variáveis de Ambiente

```bash
# MLflow
export MLFLOW_TRACKING_URI="http://localhost:5000"
export MLFLOW_EXPERIMENT_NAME="approval-models"

# Online Learning
export ONLINE_LEARNING_RETRAIN_THRESHOLD=100
export ONLINE_LEARNING_MIN_F1_IMPROVEMENT=0.05

# MongoDB
export MONGODB_URL="mongodb://localhost:27017/neural_hive_mind"

# Kafka
export KAFKA_BOOTSTRAP_SERVERS="localhost:9092"
```

## Uso

### Detectar Model Drift

```python
from neural_hive_ml import DriftDetector
from motor.motor_asyncio import AsyncIOMotorClient

mongo_client = AsyncIOMotorClient("mongodb://localhost:27017")
detector = DriftDetector(
    mongo_client=mongo_client,
    kafka_producer=kafka_producer,
    confidence_threshold=0.10
)

# Detecta drift comparando baseline (7 dias) com current (24h)
result = await detector.detect_drift(window_hours=168)

if result["drift_detected"]:
    print(f"Drift detectado! {len(result['alerts'])} alertas")
```

### Job de Retreino Automático

```python
from neural_hive_ml import RetrainingJob, ModelVersionRepository, MLflowClient

model_repo = ModelVersionRepository(db=mongo_db)
mlflow_client = MLflowClient(tracking_uri="http://localhost:5000")

retraining_job = RetrainingJob(
    mlflow_client=mlflow_client,
    model_repo=model_repo,
    kafka_producer=kafka_producer,
    retrain_threshold=100
)

# Verifica se há samples suficientes
threshold = await retraining_job.check_threshold()
if threshold["has_enough_samples"]:
    # Executa retreino
    result = await retraining_job.run_retraining(force=True)
    print(f"Novo modelo {result['new_version']} treinado!")
```

### Canary Deployment

```python
from neural_hive_ml import CanaryDeployer

canary = CanaryDeployer(
    model_repo=model_repo,
    kafka_producer=kafka_producer,
    canary_duration_minutes=60,
    canary_traffic_percentage=10
)

# Inicia canary
start_result = await canary.start_canary(version="v9", target_version="v8")

# Coleta métricas
metrics = await canary.collect_canary_metrics(start_result["canary_id"])

# Valida e promove
validation = await canary.validate_canary(start_result["canary_id"])
if validation["should_promote"]:
    final = await canary.promote_or_rollback(start_result["canary_id"], should_promote=True)
```

### API REST (approval-service)

A approval-service expõe endpoints para gestão ML:

```
POST   /api/v1/ml/retrain                    Força retreino
GET    /api/v1/ml/retrain/{job_id}           Status do job
GET    /api/v1/ml/models                      Lista versões
GET    /api/v1/ml/models/{version}           Detalhes da versão
POST   /api/v1/ml/models/{version}/promote   Promove versão
GET    /api/v1/ml/drift                       Métricas de drift
GET    /api/v1/ml/metrics                     Métricas Prometheus
```

## Deploy

### CronJob Kubernetes

CronJobs para retreino agendado são provisionados via manifests em `k8s/`:

```bash
# Aplicar CronJob diário (2h da manhã)
kubectl apply -f k8s/ml-retraining-cronjob.yaml

# Gerenciar CronJobs
./k8s/manage_cronjobs.sh status        # Status dos jobs
./k8s/manage_cronjobs.sh trigger      # Execução manual
./k8s/manage_cronjobs.sh logs        # Logs do último job
```

## Testes

```bash
# Unit tests
pytest tests/

# E2E tests
pytest tests/integration/

# Com coverage
pytest --cov=neural_hive_ml tests/
```

## Estrutura

```
neural_hive_ml/
├── __init__.py                 # Exportações públicas
├── config.py                    # Configurações Pydantic
├── mlflow_client.py             # Cliente MLflow
├── model_version_repository.py  # Repositório MongoDB
├── retraining_job.py            # Pipeline de retreino
├── drift_detector.py            # Detecção de drift + CanaryDeployer
├── predictive_models/           # Modelos preditivos
│   ├── __init__.py
│   ├── scheduling_predictor.py
│   ├── load_predictor.py
│   └── anomaly_detector.py
├── migrations/                  # Migrations MongoDB
│   ├── m001_model_versions.py
│   └── m002_drift_metrics.py
├── k8s/                         # Manifests Kubernetes
│   ├── ml-retraining-cronjob.yaml
│   └── manage_cronjobs.sh
└── tests/                       # Testes
    ├── test_mlflow_client.py
    ├── test_model_version_repository.py
    ├── test_retraining_job.py
    ├── test_drift_detector.py
    ├── test_canary_deployer.py
    ├── test_cronjob_manifests.py
    └── integration/
        └── test_online_learning_e2e.py
```

## Licença

MIT
