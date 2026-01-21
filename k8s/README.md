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
kubectl create secret generic mongodb-secret \
  --from-literal=uri="mongodb://root:dev-password@mongodb:27017/neural_hive?authSource=admin" \
  -n mlflow

kubectl create secret generic model-monitor-secrets \
  --from-literal=slack-webhook-url="https://hooks.slack.com/services/XXX/YYY/ZZZ" \
  --from-literal=smtp-password="dev-password" \
  -n mlflow

# ConfigMaps e PVCs (usar templates diretamente)
kubectl apply -f k8s/configmaps/mlflow-config.yaml
kubectl apply -f k8s/storage/ml-training-data-pvc.yaml
```

### Producao (External Secrets Operator)

```bash
# Aplicar SecretStore
kubectl apply -f k8s/external-secrets/secret-store-aws.yaml

# Aplicar ExternalSecrets (sincronizam de AWS Secrets Manager)
kubectl apply -f k8s/external-secrets/mongodb-ml-secret-external.yaml
kubectl apply -f k8s/external-secrets/model-monitor-secrets-external.yaml

# ConfigMaps e Storage
kubectl apply -f k8s/configmaps/
kubectl apply -f k8s/storage/
```

## Validacao

```bash
# Verificar secrets
kubectl get secrets -n mlflow
kubectl get secrets -n neural-hive-mind

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
```

## Troubleshooting

### Secret not found

```bash
# Verificar se secret existe no namespace correto
kubectl get secret mongodb-secret -n mlflow

# Se usando External Secrets, verificar status
kubectl get externalsecret -n mlflow
kubectl describe externalsecret mongodb-ml-secret -n mlflow
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
