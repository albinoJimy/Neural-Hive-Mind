# Recursos Kubernetes - Neural Hive Mind

Guia de aplicacao de recursos Kubernetes para diferentes ambientes.

## Estrutura de Diretorios

```
k8s/
├── secrets/              # Secrets (templates com placeholders)
├── configmaps/           # ConfigMaps de configuracao
├── cronjobs/             # CronJobs de retraining e manutencao
├── storage/              # PersistentVolumeClaims
├── namespaces/           # Definicoes de namespaces
├── external-secrets/     # Exemplos de External Secrets Operator
└── infrastructure/       # StorageClasses e recursos de infra
```

## Namespaces

| Namespace | Proposito |
|-----------|-----------|
| `mlflow` | MLflow e operacoes de ML |
| `neural-hive-mind` | Aplicacao core |
| `neural-hive-specialists` | Especialistas |
| `semantic-translation-engine` | Semantic Translation Engine com Context Layer |
| `orchestrator-dynamic` | Orchestrator Dynamic com Context Layer |
| `gateway` | Gateway Intencoes com Context Layer |

## Context Layer Deployment

O Context Layer fornece classificacao de workflow, deteccao de PII e gerenciamento de contexto para decisoes de roteamento.

### Manifests Disponiveis

| Manifest | Descricao |
|----------|-----------|
| `context-layer-configmap.yaml` | ConfigMap compartilhado do Context Layer |
| `semantic-translation-engine-deployment.yaml` | STE com Context Layer (enrich_context, workflow_type) |
| `orchestrator-dynamic-deployment.yaml` | Orchestrator com Context Layer (routing dinamico C↔G) |
| `gateway-intencoes-context-layer-deployment.yaml` | Gateway com Context Layer (PII detection) |
| `context-layer-example-deployment.yaml` | Exemplo de integracao do Context Layer |

### Deploy do Context Layer

```bash
# 1. Validar manifests
./k8s/validate-context-layer.sh

# 2. Aplicar todos os manifests do Context Layer
./k8s/context-layer-deploy.sh

# Ou aplicar individualmente:
kubectl apply -f k8s/context-layer-configmap.yaml
kubectl apply -f k8s/semantic-translation-engine-deployment.yaml
kubectl apply -f k8s/orchestrator-dynamic-deployment.yaml
kubectl apply -f k8s/gateway-intencoes-context-layer-deployment.yaml
```

### Verificacao do Deploy

```bash
# Verificar pods
kubectl get pods -n semantic-translation-engine
kubectl get pods -n orchestrator-dynamic
kubectl get pods -n gateway

# Verificar ConfigMaps
kubectl get configmap -A | grep context-layer

# Verificar se neural_hive_context foi instalado
kubectl exec -n semantic-translation-engine deployment/semantic-translation-engine -- python -c "import neural_hive_context; print(neural_hive_context.__version__)"
```

### Troubleshooting Context Layer

```bash
# Verificar logs do initContainer
kubectl logs -n semantic-translation-engine deployment/semantic-translation-engine -c install-neural-hive-context

# Verificar PYTHONPATH
kubectl exec -n semantic-translation-engine deployment/semantic-translation-engine -- env | grep PYTHONPATH

# Verificar se neural_hive_context foi importado
kubectl exec -n semantic-translation-engine deployment/semantic-translation-engine -- python -c "from neural_hive_context.services import MultiSignalWorkflowClassifier; print('OK')"

# Verificar eventos do pod
kubectl get events -n semantic-translation-engine --sort-by='.lastTimestamp'
```

## Ordem de Aplicacao

```bash
# 1. Namespaces
kubectl apply -f k8s/namespaces/

# 2. StorageClasses (se necessario)
kubectl apply -f k8s/infrastructure/storageclass-*.yaml

# 3. Secrets
kubectl apply -f k8s/secrets/

# 4. ConfigMaps
kubectl apply -f k8s/configmaps/

# 5. Storage (PVCs)
kubectl apply -f k8s/storage/

# 6. CronJobs
kubectl apply -f k8s/cronjobs/
```

## Aplicacao por Ambiente

### Desenvolvimento Local

```bash
# Criar secrets com valores de desenvolvimento
# IMPORTANTE: mongodb-secret deve existir em AMBOS namespaces (mlflow e neural-hive-mind)

# Secret para namespace mlflow (usado por specialist-retraining-job)
kubectl create secret generic mongodb-secret \
  --from-literal=uri="mongodb://root:dev-password@mongodb:27017/neural_hive?authSource=admin" \
  -n mlflow

# Secret para namespace neural-hive-mind (usado por retraining-trigger-job)
kubectl create secret generic mongodb-secret \
  --from-literal=uri="mongodb://root:dev-password@mongodb:27017/neural_hive?authSource=admin" \
  -n neural-hive-mind

kubectl create secret generic model-monitor-secrets \
  --from-literal=slack-webhook-url="https://hooks.slack.com/services/XXX/YYY/ZZZ" \
  --from-literal=smtp-password="dev-password" \
  -n mlflow

# ConfigMaps e PVCs
kubectl apply -f k8s/configmaps/mlflow-config.yaml

# Para desenvolvimento local, usar overlay Kustomize com local-path storage
kubectl apply -k k8s/kustomize/overlays/dev
# OU aplicar diretamente (requer StorageClass local-path ou alterar para efs-sc)
# kubectl apply -f k8s/storage/ml-training-data-pvc.yaml
```

### Staging (External Secrets Operator)

```bash
# Staging usa External Secrets Operator similar a producao,
# mas com secrets separados no provedor externo.

# Aplicar SecretStore (mesmo de producao ou especifico para staging)
kubectl apply -f k8s/external-secrets/secret-store-aws.yaml

# Aplicar ExternalSecrets para namespace mlflow
kubectl apply -f k8s/external-secrets/mongodb-ml-secret-external.yaml
kubectl apply -f k8s/external-secrets/model-monitor-secrets-external.yaml

# Aplicar ExternalSecret para namespace neural-hive-mind
kubectl apply -f k8s/external-secrets/mongodb-neural-hive-mind-secret-external.yaml

# ConfigMaps e Storage
kubectl apply -f k8s/configmaps/
kubectl apply -f k8s/storage/

# Diferencas de staging vs producao:
# - Pode usar valores de retraining-threshold menores no ConfigMap (ex: 50 vs 100)
# - Pode usar retraining-cooldown-hours menor (ex: 12 vs 24)
# - Recomendado criar secrets separados no AWS Secrets Manager:
#   - neural-hive/staging/mongodb-uri (staging)
#   - neural-hive/ml/mongodb-uri (producao)
```

### Producao (External Secrets Operator)

```bash
# Aplicar SecretStore
kubectl apply -f k8s/external-secrets/secret-store-aws.yaml

# Aplicar ExternalSecrets para namespace mlflow
kubectl apply -f k8s/external-secrets/mongodb-ml-secret-external.yaml
kubectl apply -f k8s/external-secrets/model-monitor-secrets-external.yaml

# Aplicar ExternalSecret para namespace neural-hive-mind
kubectl apply -f k8s/external-secrets/mongodb-neural-hive-mind-secret-external.yaml

# ConfigMaps e Storage
kubectl apply -f k8s/configmaps/
kubectl apply -f k8s/storage/
```

## Validacao

```bash
# Verificar secrets em ambos namespaces
kubectl get secrets -n mlflow
kubectl get secrets -n neural-hive-mind

# Verificar se mongodb-secret existe em ambos namespaces (IMPORTANTE!)
kubectl get secret mongodb-secret -n mlflow
kubectl get secret mongodb-secret -n neural-hive-mind

# Verificar ConfigMaps
kubectl get configmaps -n neural-hive-mind

# Verificar PVCs
kubectl get pvc -n mlflow

# Verificar CronJobs
kubectl get cronjobs -n mlflow
kubectl get cronjobs -n neural-hive-mind

# Testar CronJob manualmente
kubectl create job --from=cronjob/specialist-models-retraining test-retrain -n mlflow
kubectl logs -n mlflow job/test-retrain -f

# Testar retraining-trigger-checker manualmente
kubectl create job --from=cronjob/retraining-trigger-checker test-trigger -n neural-hive-mind
kubectl logs -n neural-hive-mind job/test-trigger -f
```

## Troubleshooting

### Secret not found

```bash
# Verificar se mongodb-secret existe em AMBOS namespaces
kubectl get secret mongodb-secret -n mlflow
kubectl get secret mongodb-secret -n neural-hive-mind

# Se usando External Secrets, verificar status em ambos namespaces
kubectl get externalsecret -n mlflow
kubectl get externalsecret -n neural-hive-mind
kubectl describe externalsecret mongodb-ml-secret -n mlflow
kubectl describe externalsecret mongodb-neural-hive-mind-secret -n neural-hive-mind
```

### PVC Pending

```bash
# Verificar StorageClass
kubectl get storageclass

# Ver eventos do PVC
kubectl describe pvc ml-training-data-pvc -n mlflow

# Verificar se provisioner esta rodando
kubectl get pods -n kube-system | grep -E "(efs|ebs|local-path)"
```

### CronJob Failed

```bash
# Ver logs do job
kubectl logs -n mlflow job/<nome-do-job>

# Verificar eventos
kubectl describe job <nome-do-job> -n mlflow

# Verificar se secrets/configmaps estao montados
kubectl get pod -n mlflow -l job-name=<nome-do-job> -o yaml | grep -A20 env
```

## Referencias

- [Guia de Gerenciamento de Secrets](../docs/SECRETS_MANAGEMENT_GUIDE.md)
- [External Secrets Operator](https://external-secrets.io/)
- [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets)
- [AWS EFS CSI Driver](https://github.com/kubernetes-sigs/aws-efs-csi-driver)
