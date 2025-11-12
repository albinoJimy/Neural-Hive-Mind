#!/bin/bash
# Deploy do Motor de Tradução Semântica
set -euo pipefail

# Variáveis
ENV=${ENV:-dev}
NAMESPACE="semantic-translation-engine"
CHART_PATH="./helm-charts/semantic-translation-engine"
VALUES_FILE="./environments/${ENV}/helm-values/semantic-translation-engine-values.yaml"

echo "Deploying Semantic Translation Engine para ambiente ${ENV}..."

# 1. Criar namespace se não existir
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# 2. Aplicar labels no namespace
if [ "${ENV}" = "production" ]; then
  kubectl label namespace ${NAMESPACE} \
    neural-hive.io/component=semantic-translation-engine \
    neural-hive.io/layer=cognitiva \
    istio-injection=enabled \
    --overwrite
else
  kubectl label namespace ${NAMESPACE} \
    neural-hive.io/component=semantic-translation-engine \
    neural-hive.io/layer=cognitiva \
    --overwrite
fi

# 3. Criar secrets (se não existirem)
if ! kubectl get secret semantic-translation-engine-secrets -n ${NAMESPACE} &> /dev/null; then
  echo "Criando secrets..."
  kubectl create secret generic semantic-translation-engine-secrets \
    --from-literal=kafka_sasl_password="${KAFKA_SASL_PASSWORD:-}" \
    --from-literal=neo4j_password="${NEO4J_PASSWORD:-}" \
    --from-literal=mongodb_password="${MONGODB_PASSWORD:-}" \
    --from-literal=redis_password="${REDIS_PASSWORD:-}" \
    -n ${NAMESPACE}
fi

# 4. Deploy via Helm
echo "Deployando Helm chart..."
helm upgrade --install semantic-translation-engine ${CHART_PATH} \
  --namespace ${NAMESPACE} \
  --values ${VALUES_FILE} \
  --wait --timeout 10m

# 5. Verificar deployment
echo "Verificando deployment..."
kubectl rollout status deployment/semantic-translation-engine -n ${NAMESPACE}

# 6. Verificar pods
kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=semantic-translation-engine

# 7. Verificar health
echo "Checando health..."
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=semantic-translation-engine \
  -n ${NAMESPACE} \
  --timeout=5m

echo "✅ Deployment concluído com sucesso!"
