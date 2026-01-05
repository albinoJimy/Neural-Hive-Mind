#!/bin/bash
# Script de Migração TLS para OpenTelemetry Exporter
# Habilita TLS gradualmente para os serviços Neural Hive-Mind
#
# Uso:
#   ./enable-tls-migration.sh [namespace] [dry-run]
#   ./enable-tls-migration.sh neural-hive false
#   ./enable-tls-migration.sh neural-hive true  # Apenas mostra o que seria feito

set -e

NAMESPACE=${1:-neural-hive}
DRY_RUN=${2:-true}
CERT_SECRET_NAME="neural-hive-otel-client-certs"
CLUSTER_ISSUER="selfsigned-cluster-issuer"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔒 Habilitando TLS para OpenTelemetry Exporter${NC}"
echo "Namespace: $NAMESPACE"
echo "Dry Run: $DRY_RUN"
echo ""

# 1. Verificar cert-manager
echo -e "${YELLOW}📋 Verificando pré-requisitos...${NC}"
if ! kubectl get crd certificates.cert-manager.io &>/dev/null; then
    echo -e "${RED}❌ cert-manager não instalado${NC}"
    echo "Instale cert-manager antes de continuar:"
    echo "  kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml"
    exit 1
fi
echo -e "${GREEN}✓ cert-manager instalado${NC}"

# Verificar ClusterIssuer
if ! kubectl get clusterissuer $CLUSTER_ISSUER &>/dev/null; then
    echo -e "${YELLOW}⚠️  ClusterIssuer '$CLUSTER_ISSUER' não encontrado${NC}"
    echo "Criando ClusterIssuer self-signed..."

    if [ "$DRY_RUN" = "false" ]; then
        kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: $CLUSTER_ISSUER
spec:
  selfSigned: {}
EOF
    else
        echo "[DRY-RUN] Criaria ClusterIssuer $CLUSTER_ISSUER"
    fi
fi
echo -e "${GREEN}✓ ClusterIssuer disponível${NC}"

# 2. Criar certificados
echo ""
echo -e "${YELLOW}📜 Criando certificados...${NC}"

if [ "$DRY_RUN" = "false" ]; then
    # Certificado para clientes
    kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: $CERT_SECRET_NAME
  namespace: $NAMESPACE
spec:
  secretName: $CERT_SECRET_NAME
  issuerRef:
    name: $CLUSTER_ISSUER
    kind: ClusterIssuer
  commonName: neural-hive-client
  duration: 8760h  # 1 ano
  renewBefore: 720h  # 30 dias antes
  usages:
  - client auth
  - digital signature
  - key encipherment
EOF
    echo -e "${GREEN}✓ Certificate criado${NC}"
else
    echo "[DRY-RUN] Criaria Certificate $CERT_SECRET_NAME no namespace $NAMESPACE"
fi

# 3. Aguardar certificado estar pronto
if [ "$DRY_RUN" = "false" ]; then
    echo -e "${YELLOW}⏳ Aguardando certificado ficar pronto...${NC}"
    if kubectl wait --for=condition=Ready certificate/$CERT_SECRET_NAME \
        -n $NAMESPACE --timeout=60s 2>/dev/null; then
        echo -e "${GREEN}✓ Certificado pronto${NC}"
    else
        echo -e "${YELLOW}⚠️  Timeout aguardando certificado. Verifique manualmente.${NC}"
    fi
fi

# 4. Listar serviços a migrar
echo ""
echo -e "${YELLOW}🔍 Identificando serviços com observability.tls configurável...${NC}"

# Lista de serviços com suporte TLS
SERVICES_WITH_TLS=(
    "gateway-intencoes"
    "queen-agent"
    "optimizer-agents"
    "service-registry"
    "worker-agents"
    "guard-agents"
    "analyst-agents"
    "code-forge"
    "self-healing-engine"
    "orchestrator-dynamic"
    "semantic-translation-engine"
    "execution-ticket-service"
    "scout-agents"
    "explainability-api"
    "mcp-tool-catalog"
    "memory-layer-api"
    "sla-management-system"
    "consensus-engine"
)

# 5. Habilitar TLS em cada serviço
echo ""
echo -e "${YELLOW}🔧 Habilitando TLS nos serviços...${NC}"

for service in "${SERVICES_WITH_TLS[@]}"; do
    # Verificar se helm release existe
    if helm list -n $NAMESPACE 2>/dev/null | grep -q "^$service"; then
        if [ "$DRY_RUN" = "false" ]; then
            echo "  Habilitando TLS em $service..."
            helm upgrade $service ./helm-charts/$service \
                --namespace $NAMESPACE \
                --set observability.tls.enabled=true \
                --set observability.tls.certSecret=$CERT_SECRET_NAME \
                --reuse-values \
                --wait \
                --timeout=5m 2>/dev/null && \
                echo -e "  ${GREEN}✓ $service${NC}" || \
                echo -e "  ${RED}✗ $service (falha no upgrade)${NC}"
        else
            echo "[DRY-RUN] Habilitaria TLS em $service"
        fi
    else
        echo -e "  ${YELLOW}⏭ $service (release não encontrada)${NC}"
    fi
done

# 6. Verificar status
echo ""
echo -e "${YELLOW}📊 Verificando status...${NC}"

if [ "$DRY_RUN" = "false" ]; then
    echo "Pods com TLS habilitado:"
    kubectl get pods -n $NAMESPACE -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | \
        while read pod; do
            if kubectl exec -n $NAMESPACE $pod -- env 2>/dev/null | grep -q "OTEL_EXPORTER_TLS_ENABLED=true"; then
                echo -e "  ${GREEN}✓ $pod${NC}"
            fi
        done
else
    echo "[DRY-RUN] Verificaria pods com OTEL_EXPORTER_TLS_ENABLED=true"
fi

echo ""
echo -e "${GREEN}✅ Migração TLS concluída!${NC}"
echo ""
echo "Próximos passos:"
echo "  1. Verificar logs: kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=<service> | grep -i tls"
echo "  2. Monitorar métricas de export no Grafana"
echo "  3. Após validar, habilitar TLS no otel-collector:"
echo "     helm upgrade neural-hive-otel-collector ./helm-charts/otel-collector \\"
echo "       --namespace neural-hive-observability \\"
echo "       --set tls.enabled=true \\"
echo "       --set tls.certSecret=otel-collector-tls \\"
echo "       --reuse-values"
