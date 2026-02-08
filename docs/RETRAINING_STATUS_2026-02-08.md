# Status do Retreinamento ML - 2026-02-08

## Status Atual

### Feedbacks Coletados: 1002/1000 ✅

| Especialista | Feedbacks | Status |
|--------------|-----------|--------|
| architecture | 201 | READY |
| business | 201 | READY |
| technical | 200 | READY |
| behavior | 200 | READY |
| evolution | 200 | READY |

**Threshold de retreinamento: 100 feedbacks**

Todos os 5 especialistas atingiram o threshold e estão prontos para retreinamento.

## Pipeline de Treinamento

Localização: `/ml_pipelines/training/`

### Arquivos Principais

- `MLproject` - Definição do projeto MLflow
- `train_specialist_model.py` - Script principal de treinamento
- `train_all_specialists.sh` - Script para treinar todos
- `generate_training_datasets.py` - Geração de datasets sintéticos
- `real_data_collector.py` - Coleta de dados reais do MongoDB

### Configuração MLflow

- **Tracking URI**: `http://mlflow.mlflow.svc.cluster.local:5000` (namespace: `mlflow`)
- **Service**: ClusterIP `mlflow.mlflow.svc.cluster.local:5000`

## Modelos Atuais

| Especialista | Versão | Confiança |
|--------------|--------|-----------|
| business | v11 | ~0.5 |
| technical | v10 | ~0.5 |
| behavior | v10 | ~0.5 |
| evolution | v11 | ~0.5 |
| architecture | v10 | ~0.5 |

## Pré-requisitos para Retreinamento

1. **Código de treinamento acessível no cluster**
   - Criar ConfigMap com o pipeline
   - Ou criar imagem Docker com o código

2. **Variáveis de ambiente configuradas**
   ```bash
   MONGODB_URI=mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin
   MLFLOW_TRACKING_URI=http://mlflow.mlflow.svc.cluster.local:5000
   ```

3. **Dependências Python**
   - mlflow
   - pymongo
   - scikit-learn
   - pandas, numpy
   - structlog

## Comando de Retreinamento

```bash
# Via MLflow CLI
mlflow projects run /ml_pipelines/training \
  -P specialist_type=business \
  -P feedback_count=201 \
  -P window_days=7 \
  -P min_feedback_quality=0.5 \
  -P model_type=random_forest \
  -P hyperparameter_tuning=false \
  -P promote_if_better=true
```

## Abordagem Recomendada

### Opção 1: Criar Imagem Docker de Treinamento

```dockerfile
FROM python:3.11-slim
RUN pip install mlflow pymongo scikit-learn pandas numpy structlog
WORKDIR /app
COPY ml_pipelines/training/ .
ENTRYPOINT ["python", "train_specialist_model.py"]
```

### Opção 2: Job com ConfigMap

1. Criar ConfigMap com código de treinamento
2. Montar como volume no pod
3. Executar treinamento

### Opção 3: Script Local Executando no Cluster

```bash
# Forward MLflow UI
kubectl port-forward -n mlflow svc/mlflow 5000:5000

# Executar treinamento local conectando ao cluster
export MONGODB_URI="mongodb://..."
export MLFLOW_TRACKING_URI="http://localhost:5000"
python ml_pipelines/training/train_specialist_model.py \
  --specialist-type business \
  --feedback-count 201
```

## Próximos Passos

1. [ ] Criar imagem Docker com pipeline de treinamento
2. [ ] Testar retreinamento com 1 especialista
3. [ ] Validar métricas do novo modelo
4. [ ] Promover modelo para Production no MLflow
5. [ ] Atualizar deployments para usar novos modelos
6. [ ] Executar retreinamento para todos os especialistas

## Scripts Úteis

```bash
# Verificar status dos feedbacks
kubectl apply -f k8s/check_retraining_status.yaml

# Coletar mais feedbacks automáticos
kubectl apply -f k8s/auto-feedback-job.yaml

# Estatísticas via API
curl http://37.60.241.150:30080/api/v1/feedback/stats
```

## Monitoramento

- **MLflow UI**: `http://37.60.241.150:30500` (se exposto externamente)
- **Collection MongoDB**: `specialist_feedback`
- **Collection de Triggers**: `retraining_triggers`
