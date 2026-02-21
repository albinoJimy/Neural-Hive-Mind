#!/bin/bash
# Script de deploy de serviços em ordem de dependência
# Uso: ./deploy-services-ordered.sh [ambiente]

set -e

ENV="${1:-local}"
HELM_VALUES="helm-values-eks-complete.yaml"

if [[ ! -f "${HELM_VALUES}" ]]; then
  echo "ERRO: Arquivo ${HELM_VALUES} não encontrado."
  exit 1
fi

echo "=== Deploy de Serviços Neural Hive-Mind - ${ENV} ==="
echo "Valores Helm: ${HELM_VALUES}"

# Função para aguardar pod pronto
wait_for_ready() {
  local ns=$1
  local label=$2
  local timeout=${3:-300}
  echo "  Aguardando ${ns}/${label} (timeout: ${timeout}s)..."
  kubectl wait --for=condition=ready pod -l ${label} -n ${ns} --timeout=${timeout}s
}

# Camada 1: Fundação de Serviços
echo "[Camada 1/6] Deploy de fundação de serviços..."
helm install service-registry helm-charts/service-registry/ \
  -n neural-hive-system --create-namespace -f ${HELM_VALUES} --wait
wait_for_ready neural-hive-system app=service-registry

helm install memory-layer-api helm-charts/memory-layer-api/ \
  -n neural-hive-memory --create-namespace -f ${HELM_VALUES} --wait
wait_for_ready neural-hive-memory app=memory-layer-api

# Camada 2: Orquestração
echo "[Camada 2/6] Deploy de orquestração..."
helm install orchestrator-dynamic helm-charts/orchestrator-dynamic/ \
  -n neural-hive-orchestration --create-namespace -f ${HELM_VALUES} --wait
wait_for_ready neural-hive-orchestration app=orchestrator-dynamic

helm install consensus-engine helm-charts/consensus-engine/ \
  -n neural-hive-cognition --create-namespace -f ${HELM_VALUES} --wait
wait_for_ready neural-hive-cognition app=consensus-engine

helm install execution-ticket-service helm-charts/execution-ticket-service/ \
  -n neural-hive-execution --create-namespace -f ${HELM_VALUES} --wait
wait_for_ready neural-hive-execution app=execution-ticket-service

# Validar comunicação gRPC
scripts/validation/validate-grpc-ticket-service.sh

# Camada 3: Processamento Cognitivo
echo "[Camada 3/6] Deploy de processamento cognitivo..."
helm install semantic-translation-engine helm-charts/semantic-translation-engine/ \
  -n neural-hive-cognition -f ${HELM_VALUES} --wait
wait_for_ready neural-hive-cognition app=semantic-translation-engine

# Specialists em paralelo
for specialist in business technical architecture behavior evolution; do
  helm install specialist-${specialist} helm-charts/specialist-${specialist}/ \
    -n neural-hive-specialists --create-namespace -f ${HELM_VALUES} --wait &
done
wait
kubectl wait --for=condition=ready pod -l specialist-type=all -n neural-hive-specialists --timeout=600s

# Validar specialists
scripts/validation/validate-specialists.sh

# Camada 4: Coordenação de Agentes
echo "[Camada 4/6] Deploy de coordenação de agentes..."
helm install queen-agent helm-charts/queen-agent/ \
  -n neural-hive-orchestration -f ${HELM_VALUES} --wait
wait_for_ready neural-hive-orchestration app=queen-agent

helm install worker-agents helm-charts/worker-agents/ \
  -n neural-hive-execution -f ${HELM_VALUES} --wait
wait_for_ready neural-hive-execution app=worker-agents

# Scout, Guard, Analyst, Optimizer em paralelo
for agent in scout guard analyst optimizer; do
  helm install ${agent}-agents helm-charts/${agent}-agents/ \
    -n neural-hive-execution -f ${HELM_VALUES} --wait &
done
wait

# Validar agentes
scripts/validation/validate-worker-agents-integrations.sh

# Camada 5: Serviços de Suporte
echo "[Camada 5/6] Deploy de serviços de suporte..."
helm install code-forge helm-charts/code-forge/ \
  -n neural-hive-code-forge --create-namespace -f ${HELM_VALUES} --wait
wait_for_ready neural-hive-code-forge app=code-forge

helm install mcp-tool-catalog helm-charts/mcp-tool-catalog/ \
  -n neural-hive-mcp --create-namespace -f ${HELM_VALUES} --wait
wait_for_ready neural-hive-mcp app=mcp-tool-catalog

helm install approval-service helm-charts/approval-service/ \
  -n neural-hive-orchestration -f ${HELM_VALUES} --wait
wait_for_ready neural-hive-orchestration app=approval-service

helm install sla-management-system helm-charts/sla-management-system/ \
  -n neural-hive-orchestration -f ${HELM_VALUES} --wait
wait_for_ready neural-hive-orchestration app=sla-management-system

helm install self-healing-engine helm-charts/self-healing-engine/ \
  -n neural-hive-system -f ${HELM_VALUES} --wait
wait_for_ready neural-hive-system app=self-healing-engine

# Camada 6: Gateways e APIs
echo "[Camada 6/6] Deploy de gateways e APIs..."
helm install gateway-intencoes helm-charts/gateway-intencoes/ \
  -n gateway-intencoes --create-namespace -f ${HELM_VALUES} --wait
wait_for_ready gateway-intencoes app=gateway-intencoes

helm install explainability-api helm-charts/explainability-api/ \
  -n neural-hive-observability -f ${HELM_VALUES} --wait
wait_for_ready neural-hive-observability app=explainability-api

# Validar gateway
scripts/validation/validate-gateway-integration.sh

echo ""
echo "=== Deploy de Serviços Completo ==="
echo "Validar com:"
echo "  scripts/validation/validate-cluster-health.sh"
echo "  tests/run-tests.sh --type e2e"
