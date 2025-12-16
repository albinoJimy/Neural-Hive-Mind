# Runbook: Retreinamento de Emergência de Modelos ML

## Quando Usar
- Drift crítico detectado (PSI > 0.25, MAE ratio > 1.5)
- MAE > 20% ou Precision < 70% por mais de 1h
- Mudança significativa no padrão de workload

## Pré-requisitos
- Acesso kubectl ao cluster
- Permissões para criar Jobs no namespace neural-hive-orchestration

## Procedimento

### 1. Verificar Status Atual
```bash
# Verificar métricas atuais
kubectl exec -it deployment/orchestrator-dynamic -n neural-hive-orchestration -- \
  python3 /app/scripts/validate_ml_models.py

# Verificar drift
kubectl logs deployment/orchestrator-dynamic -n neural-hive-orchestration | grep drift_detected
```

### 2. Executar Retreinamento Manual
```bash
# Criar Job de retreinamento
kubectl create job ml-retrain-emergency-$(date +%s) \
  --from=cronjob/orchestrator-ml-training \
  -n neural-hive-orchestration

# Monitorar progresso
kubectl logs -f job/ml-retrain-emergency-<timestamp> -n neural-hive-orchestration
```

### 3. Validar Novos Modelos
```bash
# Verificar modelos no MLflow
kubectl port-forward svc/mlflow 5000:5000 -n mlflow
# Acessar http://localhost:5000, verificar experimento orchestrator-predictive-models

# Validar métricas
kubectl exec -it deployment/orchestrator-dynamic -n neural-hive-orchestration -- \
  python3 /app/scripts/validate_ml_models.py
```

### 4. Rollback se Necessário
```bash
# Desabilitar ML temporariamente
helm upgrade orchestrator-dynamic ./helm-charts/orchestrator-dynamic \
  --set config.scheduler.enable_ml_enhanced_scheduling=false \
  -n neural-hive-orchestration

# Reverter modelo no MLflow (via UI ou CLI)
mlflow models transition-model-version-stage \
  --name ticket-duration-predictor \
  --version <old_version> \
  --stage Production
```

### 5. Notificar Equipe
- Atualizar incident no PagerDuty/Slack
- Documentar causa raiz e ações tomadas
- Agendar post-mortem se necessário

## Tempo Estimado
- Retreinamento: 15-30 minutos (depende do volume de dados)
- Validação: 5 minutos
- Rollback: 2 minutos
