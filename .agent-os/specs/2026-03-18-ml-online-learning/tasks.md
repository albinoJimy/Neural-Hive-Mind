# Spec Tasks

## Tasks

- [ ] 1. Implementar MLflow Integration
  - [ ] 1.1 Escrever testes para MLflowClient
  - [ ] 1.2 Criar MLflowClient em `neural_hive_ml/mlflow_client.py`
  - [ ] 1.3 Implementar `log_model()` com metadados (F1, accuracy, feature_importance)
  - [ ] 1.4 Implementar `register_model()` para criar model version
  - [ ] 1.5 Implementar `get_model_version()` para buscar metadados
  - [ ] 1.6 Implementar `promote_model()` para staging → production
  - [ ] 1.7 Configurar MLflow server settings em neural_hive_ml
  - [ ] 1.8 Verificar todos os testes passam

- [ ] 2. Criar MongoDB Model Versions Repository
  - [ ] 2.1 Escrever testes para ModelVersionRepository
  - [ ] 2.2 Criar migration `m002_model_versions.py`
  - [ ] 2.3 Implementar ModelVersionRepository (CRUD)
  - [ ] 2.4 Implementar `get_active_model()` para versão atual
  - [ ] 2.5 Implementar `list_models()` com filtros (stage, is_active)
  - [ ] 2.6 Implementar `update_drift_metrics()` para drift tracking
  - [ ] 2.7 Verificar todos os testes passam

- [ ] 3. Implementar Auto-Retraining Pipeline
  - [ ] 3.1 Escrever testes para RetrainingJob
  - [ ] 3.2 Criar `RetrainingJob` service em `ml_pipelines/training/retraining_job.py`
  - [ ] 3.3 Implementar `check_threshold()` - verifica se 100+ samples disponíveis
  - [ ] 3.4 Implementar `execute_retraining()` - roda script de treino existente
  - [ ] 3.5 Implementar `validate_model()` - compara F1 com atual
  - [ ] 3.6 Implementar `register_to_mlflow()` - usa MLflowClient
  - [ ] 3.7 Implementar publicação evento `ml.model_trained` no Kafka
  - [ ] 3.8 Verificar todos os testes passam

- [ ] 4. Criar REST API de Gestão ML
  - [ ] 4.1 Escrever testes para MLManagementRouter
  - [ ] 4.2 Implementar `POST /api/v1/ml/retrain` - enfileira job
  - [ ] 4.3 Implementar `GET /api/v1/ml/retrain/{job_id}` - status do job
  - [ ] 4.4 Implementar `GET /api/v1/ml/models` - lista versões
  - [ ] 4.5 Implementar `GET /api/v1/ml/models/{version}` - detalhes
  - [ ] 4.6 Implementar `POST /api/v1/ml/models/{version}/promote` - promoção manual
  - [ ] 4.7 Implementar `GET /api/v1/ml/drift` - métricas de drift
  - [ ] 4.8 Implementar `GET /api/v1/ml/metrics` - endpoint Prometheus
  - [ ] 4.9 Integrar com ModelVersionRepository e MLflowClient
  - [ ] 4.10 Verificar todos os testes passam

- [ ] 5. Implementar Drift Detection
  - [ ] 5.1 Escrever testes para DriftDetector
  - [ ] 5.2 Criar `DriftDetector` service em `neural_hive_ml/drift_detector.py`
  - [ ] 5.3 Implementar `calculate_baseline()` - métricas dos últimos 7 dias
  - [ ] 5.4 Implementar `calculate_current()` - métricas dos últimos 7 dias
  - [ ] 5.5 Implementar `detect_drift()` - compara baseline vs current
  - [ ] 5.6 Implementar alerta via Kafka topic `ml.model_drift_detected`
  - [ ] 5.7 Verificar todos os testes passam

- [ ] 6. Implementar Canary Deployment
  - [ ] 6.1 Escrever testes para CanaryDeployer
  - [ ] 6.2 Criar `CanaryDeployer` service em `approval-service/src/services/canary_deployer.py`
  - [ ] 6.3 Implementar `start_canary()` - roteia 10% tráfego para staging
  - [ ] 6.4 Implementar `collect_canary_metrics()` - coleta por 1 hora
  - [ ] 6.5 Implementar `validate_canary()` - compara performances
  - [ ] 6.6 Implementar `promote_or_rollback()` - decisão final
  - [ ] 6.7 Verificar todos os testes passam

- [ ] 7. Criar CronJob Kubernetes
  - [ ] 7.1 Escrever manifesto CronJob `ml-retrainer-cronjob.yaml`
  - [ ] 7.2 Criar Dockerfile para ml-retrainer image
  - [ ] 7.3 Configurar schedule (0 2 * * *) e timeout
  - [ ] 7.4 Adicionar resources limits e requests
  - [ ] 7.5 Configurar service account e RBAC
  - [ ] 7.6 Testar execução do CronJob localmente

- [ ] 8. Testes E2E e Integração
  - [ ] 8.1 Escrever teste E2E: retrain → MLflow → promote
  - [ ] 8.2 Escrever teste E2E: drift detection → alert → retrain
  - [ ] 8.3 Escrever teste E2E: canary deployment → rollback
  - [ ] 8.4 Testar integração com MLflow server
  - [ ] 8.5 Testar integração Kafka events (ml.model_trained, ml.model_drift_detected)
  - [ ] 8.6 Verificar todos os testes passam

- [ ] 9. Documentação e Deploy
  - [ ] 9.1 Atualizar feature-map.md com progresso (40% → 100%)
  - [ ] 9.2 Criar relatório final de implementação
  - [ ] 9.3 Deploy MLflow server em cluster de testes
  - [ ] 9.4 Deploy CronJob em cluster de testes
  - [ ] 9.5 Validar funcionamento E2E em cluster

## Resumo de Progresso

**Status:** Planejamento Completo

**Componentes a implementar:**
- MLflow integration (client, model registry)
- MongoDB model_versions repository + migration
- Auto-retraining pipeline service
- REST API (8 endpoints)
- Drift detection service
- Canary deployment service
- Kubernetes CronJob
- Testes E2E

**Estimativa:** 9 major tasks, ~50 subtasks
