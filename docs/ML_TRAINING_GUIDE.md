# Guia de Treinamento dos Modelos ML (orchestrator-dynamic)

## Visão Geral
- Infraestrutura completa já implementada: DurationPredictor (RandomForest), AnomalyDetector (IsolationForest) e LoadPredictor (heurístico).
- MLflow Model Registry integrado para versionamento/promoção.
- Pipeline de treinamento com feature engineering, detecção de drift e backfill de erros.
- Objetivo: treinar modelos com dados reais do MongoDB `execution_tickets` e promover para `Production`.

## Pré-requisitos
- MongoDB populado com `execution_tickets` (`status=COMPLETED`, `actual_duration_ms > 0`).
- MLflow acessível em `http://mlflow.mlflow.svc.cluster.local:5000`.
- Mínimo de 100 tickets completados para treinar.
- ConfigMap `orchestrator-ml-training-config` aplicado no cluster.

## Treinamento Manual
```bash
kubectl run ml-training-manual \
  --image=<orchestrator-image>:<tag> \
  --restart=Never \
  --namespace=neural-hive-orchestration \
  --env="MONGODB_URI=mongodb://..." \
  --env="MLFLOW_TRACKING_URI=http://mlflow.mlflow:5000" \
  --command -- python3 /app/scripts/train_models_production.py \
    --window-days=540 \
    --min-samples=100 \
    --backfill-errors
```
- Monitorar logs: `kubectl logs -f ml-training-manual -n neural-hive-orchestration`
- Verificar modelos no MLflow (experimento `orchestrator-predictive-models`).

## Critérios de Promoção
- DurationPredictor: MAE < 15% da média de duração.
- AnomalyDetector: Precision > 0.75.
- Promoção automática via `ModelRegistry.promote_model` quando métricas superam os thresholds.

## Drift Detection
- Baseline de features salvo após treinamento via `DriftDetector.save_feature_baseline`.
- Verificação periódica (7 dias) usando `DriftDetector.run_drift_check`.
- Thresholds: PSI > 0.25 (feature drift) e MAE ratio > 1.5 (prediction drift).

## Troubleshooting
- **Dados insuficientes**: aguardar mais tickets ou reduzir `ML_MIN_TRAINING_SAMPLES`.
- **MAE alto**: validar `estimated_duration_ms` e features; retreinar com janela maior.
- **Precision baixa**: revisar heurísticas/labels de anomalia; checar contaminação.
- **Drift detectado**: retreinar com dados recentes; avaliar mudanças de workload.

## Rollback
- Desabilitar ML: `enable_ml_enhanced_scheduling=false` no Helm values.
- Reverter modelo: `mlflow models transition-model-version-stage --name <model> --version <old_version> --stage Production`.
- Reimplantar o orchestrator após ajustes.
