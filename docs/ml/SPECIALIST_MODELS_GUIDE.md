# Guia de Modelos de Especialistas - Neural Hive Mind

## 📋 Visão Geral

Este guia documenta o processo completo de treinamento, validação e deployment de modelos ML para os 5 especialistas do Neural Hive Mind.

## 🏗️ Arquitetura

### Componentes

- **MLflow Tracking Server**: `http://mlflow.mlflow.svc.cluster.local:5000`
- **Model Registry**: 5 modelos registrados (`{type}-evaluator`)
- **Training Pipeline**: `ml_pipelines/training/train_specialist_model.py`
- **Validation Script**: `ml_pipelines/training/validate_models_loaded.sh`
- **CronJob**: `k8s/cronjobs/specialist-retraining-job.yaml`

### Fluxo de Treinamento

```mermaid
sequenceDiagram
    participant CronJob
    participant TrainingScript
    participant MLflow
    participant MongoDB
    participant Specialists
    
    CronJob->>TrainingScript: Trigger semanal (domingos 2h UTC)
    TrainingScript->>MongoDB: Carregar feedbacks (últimos 30 dias)
    TrainingScript->>TrainingScript: Gerar dataset sintético (fallback)
    TrainingScript->>TrainingScript: Treinar 5 modelos (RandomForest)
    TrainingScript->>TrainingScript: Avaliar métricas (P, R, F1)
    TrainingScript->>MLflow: Registrar modelos
    
    alt Métricas ≥ Thresholds
        TrainingScript->>MLflow: Promover para Production
        TrainingScript->>Specialists: Trigger rollout restart
        Specialists->>MLflow: Carregar novos modelos
    else Métricas < Thresholds
        TrainingScript->>MLflow: Manter em Staging
    end
```

## 🚀 Operações

### Treinamento Manual

#### Pré-requisitos
- Cluster Kubernetes com namespace `mlflow`
- MLflow deployado e acessível
- MongoDB deployado (opcional, para feedbacks)

#### Executar Treinamento

```bash
# Opção 1: Via Job Kubernetes
kubectl apply -f k8s/jobs/train-specialist-models-job.yaml
kubectl wait --for=condition=complete --timeout=600s job/train-specialist-models -n mlflow
kubectl logs -n mlflow job/train-specialist-models

# Opção 2: Via script local
cd ml_pipelines/training
export MLFLOW_TRACKING_URI=http://mlflow.mlflow.svc.cluster.local:5000
export MONGODB_URI=mongodb://mongodb.mongodb-cluster.svc.cluster.local:27017
./train_all_specialists.sh
```

### Validação de Modelos

```bash
cd ml_pipelines/training
export NAMESPACE=semantic-translation
export MLFLOW_URI=http://mlflow.mlflow.svc.cluster.local:5000
./validate_models_loaded.sh
```

**Saída esperada**:
```
✅ 5/5 especialistas carregaram modelos com sucesso

Specialist: technical
   Model Loaded: true
   MLflow Connected: true
   Status: SERVING
...
```

### Retreinamento Automático

O CronJob `specialist-models-retraining` executa semanalmente aos domingos às 2h UTC.
Ele chama o pipeline real (`ml_pipelines/training/train_all_specialists.sh`) e registra/promove versões no MLflow para `{specialist}-evaluator`, respeitando os thresholds de métricas definidos no Python.

#### Verificar Status

```bash
# Listar execuções recentes
kubectl get jobs -n mlflow -l component=specialist-retraining

# Ver logs da última execução
kubectl logs -n mlflow -l component=specialist-retraining --tail=100
```

#### Executar Manualmente

```bash
kubectl create job --from=cronjob/specialist-models-retraining \
  specialist-retraining-manual-$(date +%Y%m%d%H%M%S) -n mlflow
```

### Rollout de Novos Modelos

Após treinamento bem-sucedido, reiniciar pods de especialistas:

```bash
kubectl rollout restart deployment -n semantic-translation \
  -l app.kubernetes.io/component=specialist

kubectl rollout status deployment -n semantic-translation \
  -l app.kubernetes.io/component=specialist
```

## 📊 Métricas e Monitoramento

### Métricas de Treinamento

| Métrica | Threshold | Descrição |
|---------|-----------|-----------|
| **Precision** | ≥ 0.75 | Proporção de predições positivas corretas |
| **Recall** | ≥ 0.70 | Proporção de positivos reais identificados |
| **F1 Score** | ≥ 0.72 | Média harmônica de Precision e Recall |
| **Accuracy** | - | Proporção de predições corretas (informativo) |

### Alertas Prometheus

- **SpecialistRetrainingJobFailed**: Job de retreinamento falhou (severity: critical)
- **SpecialistRetrainingJobTookTooLong**: Job rodando há mais de 2 horas (severity: warning)
- **SpecialistModelNotPromoted**: Menos de 5 modelos em Production (severity: warning)

### Dashboards Grafana

Acessar MLflow UI:
```bash
kubectl port-forward -n mlflow svc/mlflow 5000:5000
# Abrir http://localhost:5000
```

## 🔧 Troubleshooting

### Problema: Modelo não carrega no especialista

**Sintomas**:
- `validate_models_loaded.sh` retorna `model_loaded: false`
- Logs do pod mostram erro ao carregar modelo

**Diagnóstico**:
```bash
# Verificar se modelo existe no MLflow
curl http://mlflow.mlflow.svc.cluster.local:5000/api/2.0/mlflow/registered-models/get?name=technical-evaluator

# Verificar logs do especialista
kubectl logs -n semantic-translation -l app=specialist-technical --tail=50
```

**Soluções**:
1. Verificar se modelo está em stage Production
2. Verificar conectividade MLflow (endpoint `/health`)
3. Verificar compatibilidade de versão sklearn (1.5.x)
4. Forçar reload: `kubectl rollout restart deployment -n semantic-translation specialist-technical`

### Problema: Treinamento falha com métricas baixas

**Sintomas**:
- Modelo não promovido para Production
- Métricas abaixo dos thresholds

**Diagnóstico**:
```bash
# Ver logs do job de treinamento
kubectl logs -n mlflow job/specialist-models-retraining-<timestamp>
```

**Soluções**:
1. Verificar qualidade do dataset (sintético vs real)
2. Habilitar hyperparameter tuning: `HYPERPARAMETER_TUNING=true`
3. Aumentar tamanho do dataset (>1000 amostras)
4. Incorporar feedbacks humanos do MongoDB

### Problema: CronJob não executa

**Sintomas**:
- Nenhum Job criado após schedule

**Diagnóstico**:
```bash
# Verificar CronJob
kubectl get cronjob -n mlflow specialist-models-retraining -o yaml

# Verificar eventos
kubectl get events -n mlflow --sort-by='.lastTimestamp'
```

**Soluções**:
1. Verificar schedule syntax (cron format)
2. Verificar `startingDeadlineSeconds` não expirou
3. Verificar `concurrencyPolicy: Forbid` não está bloqueando
4. Executar manualmente para testar: `kubectl create job --from=cronjob/...`

## 📚 Referências

### Arquivos-Chave

- **Training Pipeline**: `ml_pipelines/training/train_specialist_model.py`
- **Orchestration Script**: `ml_pipelines/training/train_all_specialists.sh`
- **Validation Script**: `ml_pipelines/training/validate_models_loaded.sh`
- **Dataset Generation**: `ml_pipelines/training/generate_training_datasets.py`
- **CronJob Manifest**: `k8s/cronjobs/specialist-retraining-job.yaml`
- **Job Manifest**: `k8s/jobs/train-specialist-models-job.yaml`
- **MLflow Deployment**: `k8s/mlflow-deployment.yaml`

### Documentação Relacionada

- **Validação Técnica**: `docs/VALIDACAO_TREINAMENTO_MODELOS.md`
- **Modelos Preditivos**: `docs/ml/PREDICTIVE_MODELS_GUIDE.md`
- **Specialists Implementation**: `docs/SPECIALISTS-IMPLEMENTATION.md`

### Schemas Avro

- **Cognitive Plan**: `schemas/cognitive-plan/cognitive-plan.avsc`
- **Specialist Opinion**: `schemas/specialist-opinion/specialist-opinion.avsc`

## 🔐 Segurança

### Secrets Management

Modelos e credenciais são gerenciados via Kubernetes Secrets:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mongodb-secret
  namespace: mlflow
type: Opaque
stringData:
  uri: "mongodb://user:password@mongodb.mongodb-cluster.svc.cluster.local:27017"
```

### RBAC

CronJob usa ServiceAccount com permissões mínimas:
- `get`, `list` em pods e configmaps
- `get` em secrets

## 📈 Roadmap

### Curto Prazo (1-2 meses)
- [ ] Gerar datasets reais com LLM (OpenAI/Anthropic)
- [ ] Habilitar hyperparameter tuning
- [ ] Integrar feedbacks humanos do MongoDB

### Médio Prazo (3-6 meses)
- [ ] Implementar A/B testing de modelos
- [ ] Adicionar monitoramento de drift
- [ ] Criar dashboard Grafana para métricas ML

### Longo Prazo (6-12 meses)
- [ ] Online learning com feedback contínuo
- [ ] Multi-model ensemble
- [ ] AutoML para seleção de modelos
