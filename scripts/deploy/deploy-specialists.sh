#!/bin/bash
set -euo pipefail

# Variáveis
ENV=${ENV:-dev}
SPECIALISTS=("business" "technical" "behavior" "evolution" "architecture")

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --local)
      ENV="local"
      shift
      ;;
    --env)
      ENV="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--local] [--env ENV]"
      exit 1
      ;;
  esac
done

# Redirect to local deploy script if ENV=local
if [ "$ENV" = "local" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  exec "$SCRIPT_DIR/deploy-specialists-local.sh"
fi

echo "Deploying Neural Specialists to ${ENV}..."

# 1. Criar namespaces
for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

  # Aplicar labels
  kubectl label namespace ${NAMESPACE} \
    neural-hive.io/component=${specialist}-specialist \
    neural-hive.io/layer=cognitiva \
    istio-injection=enabled \
    --overwrite
done

# 2. Criar secrets (se não existirem)
for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"

  if ! kubectl get secret specialist-secrets -n ${NAMESPACE} &> /dev/null; then
    echo "Creating secrets for ${specialist}..."
    kubectl create secret generic specialist-secrets \
      --from-literal=mlflow_tracking_uri="${MLFLOW_TRACKING_URI:-}" \
      --from-literal=mongodb_uri="${MONGODB_URI:-}" \
      --from-literal=neo4j_password="${NEO4J_PASSWORD:-}" \
      --from-literal=redis_password="${REDIS_PASSWORD:-}" \
      -n ${NAMESPACE}
  fi
done

# 3. Deploy via Helm
for specialist in "${SPECIALISTS[@]}"; do
  echo "Deploying ${specialist} specialist..."
  NAMESPACE="specialist-${specialist}"
  CHART_PATH="./helm-charts/specialist-${specialist}"
  VALUES_FILE="./environments/${ENV}/helm-values/specialist-${specialist}-values.yaml"

  helm upgrade --install specialist-${specialist} ${CHART_PATH} \
    --namespace ${NAMESPACE} \
    --values ${VALUES_FILE} \
    --wait --timeout 10m
done

# 4. Verificar deployments
echo "Verifying deployments..."
for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  kubectl rollout status deployment/specialist-${specialist} -n ${NAMESPACE}
done

# 5. Verificar pods
echo "Checking pods..."
for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=specialist-${specialist}
done

# 6. Verificar health
echo "Checking health..."
for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  kubectl wait --for=condition=ready pod \
    -l app.kubernetes.io/name=specialist-${specialist} \
    -n ${NAMESPACE} \
    --timeout=5m
done

echo "All specialists deployed successfully!"
