#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""

# Script de Validação da Fase 2 - Kubernetes
# Neural Hive-Mind

set -euo pipefail
source "$(dirname "$0")/common-validation-functions.sh"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

echo -e "${BLUE}"
cat << 'EOF'
╔═══════════════════════════════════════════════════════════════╗
║         NEURAL HIVE-MIND - VALIDAÇÃO FASE 2                   ║
║                  Infraestrutura Kubernetes                    ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Contadores
CHECKS_TOTAL=0
CHECKS_PASSED=0
CHECKS_FAILED=0

track_check() {
    CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
    if [ "$1" -eq 0 ]; then
        CHECKS_PASSED=$((CHECKS_PASSED + 1))
        return 0
    else
        CHECKS_FAILED=$((CHECKS_FAILED + 1))
        return 1
    fi
}

# 1. Verificar Cluster Kubernetes
log_info "Verificando cluster Kubernetes..."
if kubectl cluster-info &> /dev/null; then
    track_check 0
    log_success "Cluster Kubernetes respondendo"
    KUBE_VERSION=$(kubectl version 2>/dev/null | grep -i "Server Version" | awk '{print $3}' || echo "v1.29.15")
    echo "   Versão: $KUBE_VERSION"
else
    track_check 1
    log_error "Cluster Kubernetes não está acessível"
    exit 1
fi

# 2. Verificar Nodes
log_info "Verificando nodes..."
NODES_READY=$(kubectl get nodes --no-headers | grep -c "Ready" || echo "0")
if [ "$NODES_READY" -gt 0 ]; then
    track_check 0
    log_success "Nodes ready: $NODES_READY"
else
    track_check 1
    log_error "Nenhum node ready"
fi

# 3. Verificar Namespaces
log_info "Verificando namespaces..."
for NS in redis-cluster mongodb-cluster; do
    if kubectl get namespace "$NS" &> /dev/null; then
        track_check 0
        log_success "Namespace $NS existe"
    else
        track_check 1
        log_error "Namespace $NS não encontrado"
    fi
done

# 4. Verificar Redis
log_info "Verificando Redis..."
REDIS_PODS=$(kubectl get pods -n redis-cluster --no-headers 2>/dev/null | grep -c "Running" || echo "0")
if [ "$REDIS_PODS" -gt 0 ]; then
    track_check 0
    log_success "Redis pods running: $REDIS_PODS"

    # Testar conectividade
    log_info "Testando conectividade Redis..."
    REDIS_POD=$(kubectl get pods -n redis-cluster -o name | head -1)
    if kubectl exec -n redis-cluster $REDIS_POD -- redis-cli ping &> /dev/null; then
        track_check 0
        log_success "Redis PING OK"

        # Testar SET/GET
        kubectl exec -n redis-cluster $REDIS_POD -- redis-cli SET test:validation "OK" &> /dev/null
        RESULT=$(kubectl exec -n redis-cluster $REDIS_POD -- redis-cli GET test:validation 2>/dev/null)
        if [ "$RESULT" = "OK" ]; then
            track_check 0
            log_success "Redis SET/GET OK"
        else
            track_check 1
            log_error "Redis SET/GET falhou"
        fi
    else
        track_check 1
        log_error "Redis não respondeu ao PING"
    fi
else
    track_check 1
    log_error "Redis não está rodando"
fi

# 5. Verificar MongoDB
log_info "Verificando MongoDB..."
MONGODB_PODS=$(kubectl get pods -n mongodb-cluster --no-headers 2>/dev/null | grep -c "Running" || echo "0")
if [ "$MONGODB_PODS" -gt 0 ]; then
    track_check 0
    log_success "MongoDB pods running: $MONGODB_PODS"

    # Testar conectividade
    log_info "Testando conectividade MongoDB..."
    MONGODB_POD=$(kubectl get pods -n mongodb-cluster -o name | grep mongodb | head -1 | sed 's/pod\///')
    if kubectl exec -n mongodb-cluster $MONGODB_POD -- mongosh mongodb://localhost:27017 -u root -p local_dev_password --authenticationDatabase admin --eval "db.adminCommand('ping')" &> /dev/null; then
        track_check 0
        log_success "MongoDB PING OK"
    else
        track_check 1
        log_error "MongoDB não respondeu ao PING"
    fi
else
    track_check 1
    log_error "MongoDB não está rodando"
fi

# 6. Verificar Persistent Volumes
log_info "Verificando persistent volumes..."
PV_COUNT=$(kubectl get pv --no-headers 2>/dev/null | wc -l)
if [ "$PV_COUNT" -gt 0 ]; then
    track_check 0
    log_success "Persistent volumes: $PV_COUNT"
else
    track_check 1
    log_error "Nenhum persistent volume encontrado"
fi

# 7. Verificar Storage Class
log_info "Verificando storage class..."
if kubectl get storageclass local-path &> /dev/null; then
    track_check 0
    log_success "Storage class local-path configurado"
else
    track_check 1
    log_error "Storage class não encontrado"
fi

# Sumário
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}                    RESUMO DA VALIDAÇÃO${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo "Total de verificações: $CHECKS_TOTAL"
echo -e "Aprovadas: ${GREEN}$CHECKS_PASSED${NC}"
echo -e "Falhadas: ${RED}$CHECKS_FAILED${NC}"

SUCCESS_RATE=$((CHECKS_PASSED * 100 / CHECKS_TOTAL))
echo ""
echo -e "Taxa de sucesso: ${GREEN}${SUCCESS_RATE}%${NC}"

if [ "$CHECKS_FAILED" -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ VALIDAÇÃO APROVADA${NC}"
    echo "Todos os componentes da Fase 2 estão operacionais!"
    exit 0
else
    echo ""
    echo -e "${YELLOW}⚠️  VALIDAÇÃO COM RESSALVAS${NC}"
    echo "$CHECKS_FAILED verificação(ões) falharam"
    exit 1
fi
