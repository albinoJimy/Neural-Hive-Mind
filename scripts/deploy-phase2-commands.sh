#!/bin/bash
# =============================================================================
# Neural Hive-Mind - Comandos de Implantação Fase 2
# =============================================================================
# Execute este script ou copie os comandos que deseja executar
# =============================================================================

set -e

REGISTRY="37.60.241.150:30500"
NAMESPACE="neural-hive"
BASE_DIR="/jimy/Neural-Hive-Mind"

cd "$BASE_DIR"

echo "============================================================================="
echo "FASE 2 - Build e Deploy de Serviços"
echo "============================================================================="

# =============================================================================
# STEP 1: BUILD DAS IMAGENS QUE FALTAM
# =============================================================================
echo ""
echo ">>> STEP 1: Build das imagens que faltam no registry"
echo ""

# Imagens que já existem no registry:
# - scout-agents, service-registry, analyst-agents, sla-management-system

# Imagens que precisam ser buildadas:
IMAGES_TO_BUILD=(
    "worker-agents"
    "guard-agents"
    "mcp-tool-catalog"
    "code-forge"
    "execution-ticket-service"
    "self-healing-engine"
    "queen-agent"
)

for service in "${IMAGES_TO_BUILD[@]}"; do
    echo ">>> Building $service..."
    docker build -f "services/$service/Dockerfile" -t "$REGISTRY/$service:latest" . || {
        echo "ERRO: Falha no build de $service"
        continue
    }
    echo ">>> Pushing $service..."
    docker push "$REGISTRY/$service:latest" || echo "ERRO: Falha no push de $service"
    echo ""
done

echo "Build das imagens concluído!"

# =============================================================================
# STEP 2: DEPLOY COM HELM
# =============================================================================
echo ""
echo ">>> STEP 2: Deploy dos serviços com Helm"
echo ""

# Deploy em ordem de dependência
SERVICES_ORDER=(
    "service-registry"      # Base - registro de serviços
    "execution-ticket-service"  # Gerencia tickets
    "mcp-tool-catalog"      # Catálogo de ferramentas
    "code-forge"            # Geração de código
    "scout-agents"          # Agentes exploradores
    "worker-agents"         # Agentes trabalhadores
    "guard-agents"          # Agentes de segurança
    "self-healing-engine"   # Auto-cura
    "queen-agent"           # Coordenação
)

for service in "${SERVICES_ORDER[@]}"; do
    echo ">>> Deploying $service..."

    VALUES_FILE="helm-charts/$service/values-local.yaml"
    VALUES_ARG=""
    if [ -f "$VALUES_FILE" ]; then
        VALUES_ARG="-f $VALUES_FILE"
    fi

    helm upgrade --install "$service" "helm-charts/$service" \
        --namespace "$NAMESPACE" \
        --create-namespace \
        $VALUES_ARG \
        --set image.repository="$REGISTRY/$service" \
        --set image.tag="latest" \
        --set image.pullPolicy="Always" \
        --wait \
        --timeout 5m || {
            echo "WARN: Deploy de $service falhou ou timeout - continuando..."
        }

    echo ""
done

echo "Deploy concluído!"

# =============================================================================
# STEP 3: VERIFICAÇÃO
# =============================================================================
echo ""
echo ">>> STEP 3: Verificação do status"
echo ""

kubectl get pods -n "$NAMESPACE"
echo ""
kubectl get svc -n "$NAMESPACE"

echo ""
echo "============================================================================="
echo "FASE 2 CONCLUÍDA!"
echo "============================================================================="
