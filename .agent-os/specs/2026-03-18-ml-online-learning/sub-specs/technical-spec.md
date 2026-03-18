# Technical Specification

This is the technical specification for the spec detailed in @.agent-os/specs/2026-03-18-ml-online-learning/spec.md

## Technical Requirements

### Auto-Retraining Pipeline
- Trigger: Quando `active_learning_queue` tem 100+ feedbacks processados
- Pipeline: Executa script `ml_pipelines/training/retrain_with_enriched_features.py`
- Validação: F1-score do novo modelo deve ser >= modelo atual + 0.05 (5% improvement)
- Se validação falha: Modelo não é deployado, alerta é enviado

### Model Registry (MLflow)
- MLflow server em `mlflow.neural-hive-mind.svc:5000`
- Cada modelo treinado registrado como `approval-model-{versao}`
- Metadados armazenados: data, F1-score, accuracy, precision, recall, confusion_matrix, feature_importance, n_samples
- Staging vs Production: Novo modelo vai para Staging, promoção manual para Production

### Drift Detection
- Métricas Prometheus: `ml_approval_prediction_confidence`, `ml_approval_approve_rate`, `ml_approval_reject_rate`
- Comparação: janela de 7 dias vs 7 dias anteriores
- Alerta se: confidence drop > 10% ou approve_rate varição > 15%
- Alerta via Kafka topic `ml.model_drift_detected`

### Canary Deployment
- Approval service roteia 10% do tráfego para novo modelo (staging)
- Métricas coletadas por 1 hora
- Se F1-production >= F1-staging - 0.05: rollback automático
- Se OK: promove para 100% do tráfego

### API de Gestão (approval-service)
- `POST /api/v1/ml/retrain` - Força retreinamento manual
- `GET /api/v1/ml/models` - Lista versões de modelos (MLflow)
- `GET /api/v1/ml/models/{version}` - Detalhes do modelo
- `POST /api/v1/ml/models/{version}/promote` - Promove modelo para produção
- `GET /api/v1/ml/drift` - Métricas de drift

### CronJob Kubernetes
- Namespace: `neural-hive-mind`
- Schedule: `0 2 * * *` (2h da manhã, todos os dias)
- Image: `ghcr.io/albinojimy/neural-hive-mind/ml-retrainer:latest`
- Timeout: 30 minutos
- Resources: 1 CPU, 2Gi memory

## External Dependencies

- **MLflow 2.x** - Model registry e tracking
  - **Justification:** Padrão de mercado para MLOps, integração com Kubernetes, permite rollback

- **Prometheus + AlertManager** - Já existe no cluster, para métricas e alertas

- **ArgoCD** - Já existe, para deploy dos manifests do CronJob

## Performance Criteria

- Retreinamento deve completar em < 30 minutos para 1000 samples
- Drift detection deve rodar a cada hora
- API de gestão deve responder em < 100ms (p95)
- Canary deployment deve completar em < 1 hora
