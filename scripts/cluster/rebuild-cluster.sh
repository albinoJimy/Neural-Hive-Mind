#!/bin/bash
# Script de reconstrução completa do cluster Neural Hive-Mind
# Uso: ./rebuild-cluster.sh <ambiente> <backup-dir>

set -e

ENV="${1:-local}"
BACKUP_DIR="${2}"

echo "=== Reconstrução Neural Hive-Mind - ${ENV} ==="

# 3.1 Provisionar Infraestrutura Base (Terraform)
echo "[Fase 1/6] Provisionando infraestrutura base..."
if [[ -d "infrastructure/terraform" ]]; then
  cd infrastructure/terraform
  terraform init -backend-config="../../environments/${ENV}/backend.hcl"
  terraform apply -target=module.network \
    -var-file="../../environments/${ENV}/terraform.tfvars -auto-approve
  terraform apply -target=module.k8s-cluster \
    -var-file="../../environments/${ENV}/terraform.tfvars -auto-approve
  terraform apply -target=module.container-registry \
    -var-file="../../environments/${ENV}/terraform.tfvars -auto-approve
  aws eks update-kubeconfig --name neural-hive-${ENV} --region ${AWS_REGION}
  cd ../..
  kubectl get nodes
else
  echo "AVISO: Terraform não encontrado, pulando infraestrutura base."
fi

# 3.2 Aplicar Bootstrap Kubernetes
echo "[Fase 2/6] Aplicando bootstrap Kubernetes..."
mkdir -p .tmp/bootstrap-manual
docs/manual-deployment/scripts/01-prepare-bootstrap-manifests.sh

kubectl apply -f .tmp/bootstrap-manual/namespaces.yaml
kubectl apply -f .tmp/bootstrap-manual/data-governance-crds.yaml
kubectl apply -f .tmp/bootstrap-manual/rbac.yaml
kubectl apply -f .tmp/bootstrap-manual/network-policies.yaml
kubectl apply -f .tmp/bootstrap-manual/pod-security-standards.yaml

scripts/validation/validate-bootstrap-phase.sh

# 3.3 Deploy de Infraestrutura de Dados
echo "[Fase 3/6] Deploy de infraestrutura de dados..."
mkdir -p .tmp/infrastructure-values
docs/manual-deployment/scripts/02-prepare-infrastructure-values.sh all

# Instalar operators
helm repo add strimzi https://strimzi.io/charts/
helm repo update
helm install strimzi-kafka-operator strimzi/strimzi-kafka-operator -n kafka --create-namespace
helm install redis-operator ot-helm/redis-operator -n redis-operator --create-namespace
helm install mongodb-operator mongodb/community-operator -n mongodb-operator --create-namespace
helm install clickhouse-operator altinity/clickhouse-operator -n clickhouse-operator --create-namespace

# Aguardar operators
kubectl wait --for=condition=Ready pod -l name=strimzi-cluster-operator -n kafka --timeout=300s
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=redis-operator -n redis-operator --timeout=300s
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=mongodb-kubernetes-operator -n mongodb-operator --timeout=300s
kubectl wait --for=condition=Ready pod -l app=clickhouse-operator -n clickhouse-operator --timeout=300s

# Deploy de bancos de dados
helm install kafka-topics helm-charts/kafka-topics/ -n kafka \
  -f environments/${ENV}/kafka-values.yaml --wait
helm install redis-cluster helm-charts/redis-cluster/ -n redis-cluster --create-namespace \
  -f .tmp/infrastructure-values/redis-values-local.yaml --wait
helm install mongodb helm-charts/mongodb/ -n mongodb-cluster --create-namespace \
  -f .tmp/infrastructure-values/mongodb-values-local.yaml --wait
helm install neo4j helm-charts/neo4j/ -n neo4j-cluster --create-namespace \
  -f .tmp/infrastructure-values/neo4j-values-local.yaml --wait
helm install clickhouse helm-charts/clickhouse/ -n clickhouse-cluster --create-namespace \
  -f .tmp/infrastructure-values/clickhouse-values-local.yaml --wait

# Validar infraestrutura
docs/manual-deployment/scripts/03-validate-infrastructure.sh --verbose

# 3.4 Restaurar Dados dos Backups
if [[ -n "${BACKUP_DIR}" && -d "${BACKUP_DIR}" ]]; then
  echo "[Fase 4/6] Restaurando dados dos backups..."
  scripts/cluster/restore-all-data.sh "${BACKUP_DIR}"
else
  echo "[Fase 4/6] Restore pulado (nenhum backup especificado)."
fi

# 3.5 Deploy de Segurança e Service Mesh
echo "[Fase 5/6] Deploy de segurança e service mesh..."
scripts/deploy/deploy-vault-ha.sh
scripts/security.sh vault init
scripts/security.sh vault populate --mode static --environment ${ENV}

scripts/deploy/deploy-spire.sh
scripts/security.sh spire deploy --namespace spire-system
scripts/security.sh spire register --service all

# Istio
helm repo add istio https://istio-release.storage.googleapis.com/charts
helm repo update
helm install istio-base istio/base -n istio-system --create-namespace --wait
helm install istiod istio/istiod -n istio-system \
  -f helm-charts/istio-base/values.yaml \
  -f environments/${ENV}/helm-values/istio-values.yaml --wait
kubectl apply -f helm-charts/istio-base/templates/

# OPA Gatekeeper
helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts
helm install gatekeeper gatekeeper/gatekeeper -n gatekeeper-system --create-namespace \
  -f helm-charts/opa-gatekeeper/values.yaml --wait
kubectl wait --for=condition=ready pod -l gatekeeper.sh/operation=webhook \
  -n gatekeeper-system --timeout=180s
kubectl apply -f policies/constraint-templates/
sleep 15
kubectl apply -f policies/constraints/

# Validar segurança
scripts/security.sh validate all

# 3.6 Deploy de Observabilidade
echo "[Fase 6/6] Deploy de observabilidade..."
helm install prometheus-stack helm-charts/prometheus-stack/ \
  -n neural-hive-observability --create-namespace \
  -f environments/${ENV}/helm-values/prometheus-values.yaml --wait
helm install grafana helm-charts/grafana/ \
  -n neural-hive-observability \
  -f environments/${ENV}/helm-values/grafana-values.yaml --wait
helm install jaeger helm-charts/jaeger/ \
  -n neural-hive-observability \
  -f environments/${ENV}/helm-values/jaeger-values.yaml --wait
helm install otel-collector helm-charts/otel-collector/ \
  -n neural-hive-observability \
  -f environments/${ENV}/helm-values/otel-values.yaml --wait

# Temporal
helm install temporal helm-charts/temporal/ \
  -n temporal --create-namespace \
  -f environments/${ENV}/helm-values/temporal-values.yaml --wait

# Validar observabilidade
scripts/observability.sh validate

echo ""
echo "=== Reconstrução Base Completa ==="
echo "Prosseguir para deploy de serviços com:"
echo "  scripts/cluster/deploy-services-ordered.sh ${ENV}"
