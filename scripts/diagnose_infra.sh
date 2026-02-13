#!/bin/bash
# =============================================================================
# Script de Diagnóstico de Infraestrutura - Neural Hive-Mind
# =============================================================================
# Verifica status de Redis Cluster e Schema Registry
# Uso: ./scripts/diagnose_infra.sh [--redis] [--schema-registry] [--all]
# =============================================================================

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Argumentos
CHECK_REDIS=false
CHECK_SCHEMA_REGISTRY=false

for arg in "$@"; do
    case $arg in
        --redis) CHECK_REDIS=true ;;
        --schema-registry) CHECK_SCHEMA_REGISTRY=true ;;
        --all)
            CHECK_REDIS=true
            CHECK_SCHEMA_REGISTRY=true
            ;;
    esac
done

# Se nenhum argumento, checar tudo
if [ "$CHECK_REDIS" = false ] && [ "$CHECK_SCHEMA_REGISTRY" = false ]; then
    CHECK_REDIS=true
    CHECK_SCHEMA_REGISTRY=true
fi

# =============================================================================
# Funções de Diagnóstico Redis
# =============================================================================

diagnose_redis() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}🔍 DIAGNÓSTICO: REDIS CLUSTER${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    # 1. Verificar namespace
    echo -e "${YELLOW}1️⃣ Verificando namespace redis-cluster...${NC}"
    if kubectl get namespace redis-cluster &>/dev/null; then
        echo -e "${GREEN}   ✓ Namespace redis-cluster existe${NC}"
    else
        echo -e "${RED}   ✗ Namespace redis-cluster NÃO existe${NC}"
        echo -e "${YELLOW}   💡 Criar namespace: kubectl create namespace redis-cluster${NC}"
        return 1
    fi
    echo ""

    # 2. Verificar pods
    echo -e "${YELLOW}2️⃣ Verificando pods Redis...${NC}"
    REDIS_PODS=$(kubectl get pods -n redis-cluster -l app=redis -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$REDIS_PODS" ]; then
        echo -e "${GREEN}   ✓ Pods Redis encontrados:${NC}"
        kubectl get pods -n redis-cluster -l app=redis
        for pod in $REDIS_PODS; do
            STATUS=$(kubectl get pod -n redis-cluster "$pod" -o jsonpath='{.status.phase}')
            if [ "$STATUS" = "Running" ]; then
                echo -e "${GREEN}   ✓ $pod: $STATUS${NC}"
            else
                echo -e "${RED}   ✗ $pod: $STATUS${NC}"
            fi
        done
    else
        echo -e "${RED}   ✗ Nenhum pod Redis encontrado${NC}"
        echo -e "${YELLOW}   💡 Deploy: kubectl apply -f k8s/redis-local.yaml${NC}"
    fi
    echo ""

    # 3. Verificar serviço
    echo -e "${YELLOW}3️⃣ Verificando serviço Redis...${NC}"
    if kubectl get svc -n redis-cluster neural-hive-cache &>/dev/null; then
        echo -e "${GREEN}   ✓ Serviço neural-hive-cache existe${NC}"
        kubectl get svc -n redis-cluster neural-hive-cache
    else
        echo -e "${RED}   ✗ Serviço neural-hive-cache NÃO existe${NC}"
    fi
    echo ""

    # 4. Testar conectividade
    echo -e "${YELLOW}4️⃣ Testando conectividade Redis...${NC}"
    REDIS_POD=$(kubectl get pod -n redis-cluster -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$REDIS_POD" ]; then
        echo -e "${BLUE}   Executando: redis-cli ping${NC}"
        if kubectl exec -n redis-cluster "$REDIS_POD" -- redis-cli ping &>/dev/null; then
            echo -e "${GREEN}   ✓ Redis PONG - conexão funcionando!${NC}"
        else
            echo -e "${RED}   ✗ Falha no ping${NC}"
        fi

        echo -e "${BLUE}   Verificando INFO stats...${NC}"
        kubectl exec -n redis-cluster "$REDIS_POD" -- redis-cli INFO stats | head -5
    else
        echo -e "${YELLOW}   ⚠ Nenhum pod para teste de conectividade${NC}"
    fi
    echo ""

    # 5. Verificar secrets
    echo -e "${YELLOW}5️⃣ Verificando secrets Redis...${NC}"
    if kubectl get secret -n redis-cluster redis-password &>/dev/null; then
        echo -e "${GREEN}   ✓ Secret redis-password existe${NC}"
    else
        echo -e "${RED}   ✗ Secret redis-password NÃO existe${NC}"
        echo -e "${YELLOW}   💡 Criar: kubectl create secret generic redis-password -n redis-cluster --from-literal=password=\$(openssl rand -base64 32)${NC}"
    fi
    echo ""

    # 6. Verificar ConfigMaps dos serviços
    echo -e "${YELLOW}6️⃣ Verificando ConfigMaps dos serviços...${NC}"
    echo -e "${BLUE}   Configuração Redis no orchestrator-dynamic:${NC}"
    kubectl get configmap -n neural-hive-execution orchestrator-dynamic-config -o jsonpath='{.data.REDIS_CLUSTER_NODES}' 2>/dev/null || echo "   (não definido no ConfigMap)"
    echo ""
}

# =============================================================================
# Funções de Diagnóstico Schema Registry
# =============================================================================

diagnose_schema_registry() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}🔍 DIAGNÓSTICO: SCHEMA REGISTRY${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    # 1. Verificar namespace kafka
    echo -e "${YELLOW}1️⃣ Verificando namespace kafka...${NC}"
    if kubectl get namespace kafka &>/dev/null; then
        echo -e "${GREEN}   ✓ Namespace kafka existe${NC}"
    else
        echo -e "${RED}   ✗ Namespace kafka NÃO existe${NC}"
        echo -e "${YELLOW}   💡 Criar namespace: kubectl create namespace kafka${NC}"
        return 1
    fi
    echo ""

    # 2. Verificar pods Schema Registry
    echo -e "${YELLOW}2️⃣ Verificando pods Schema Registry...${NC}"
    SR_PODS=$(kubectl get pods -n kafka -l app=schema-registry -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$SR_PODS" ]; then
        echo -e "${GREEN}   ✓ Pods Schema Registry encontrados:${NC}"
        kubectl get pods -n kafka -l app=schema-registry
        for pod in $SR_PODS; do
            STATUS=$(kubectl get pod -n kafka "$pod" -o jsonpath='{.status.phase}')
            if [ "$STATUS" = "Running" ]; then
                echo -e "${GREEN}   ✓ $pod: $STATUS${NC}"
            else
                echo -e "${RED}   ✗ $pod: $STATUS${NC}"
            fi
        done
    else
        echo -e "${RED}   ✗ Nenhum pod Schema Registry encontrado${NC}"
        echo -e "${YELLOW}   💡 Deploy: kubectl apply -f k8s/apicurio-registry-deployment.yaml${NC}"
    fi
    echo ""

    # 3. Verificar serviço
    echo -e "${YELLOW}3️⃣ Verificando serviço Schema Registry...${NC}"
    if kubectl get svc -n kafka schema-registry &>/dev/null; then
        echo -e "${GREEN}   ✓ Serviço schema-registry existe${NC}"
        kubectl get svc -n kafka schema-registry
    else
        echo -e "${RED}   ✗ Serviço schema-registry NÃO existe${NC}"
    fi
    echo ""

    # 4. Verificar certificados TLS
    echo -e "${YELLOW}4️⃣ Verificando certificados TLS...${NC}"
    if kubectl get secret -n kafka schema-registry-tls-secret &>/dev/null; then
        echo -e "${GREEN}   ✓ Secret schema-registry-tls-secret existe${NC}"

        # Verificar validade do certificado
        CERT_DATA=$(kubectl get secret -n kafka schema-registry-tls-secret -o jsonpath='{.data.tls\.crt}' 2>/dev/null || echo "")
        if [ -n "$CERT_DATA" ]; then
            echo "$CERT_DATA" | base64 -d | openssl x509 -noout -dates 2>/dev/null || echo "   (não foi possível verificar validade)"
        fi
    else
        echo -e "${RED}   ✗ Secret schema-registry-tls-secret NÃO existe${NC}"
        echo -e "${YELLOW}   💡 Verificar se cert-manager está instalado${NC}"
        echo -e "${YELLOW}   💡 Deploy: kubectl apply -f k8s/schema-registry-tls.yaml${NC}"
    fi
    echo ""

    # 5. Verificar cert-manager
    echo -e "${YELLOW}5️⃣ Verificando cert-manager...${NC}"
    if kubectl get namespace cert-manager &>/dev/null; then
        echo -e "${GREEN}   ✓ Namespace cert-manager existe${NC}"
        kubectl get pods -n cert-manager 2>/dev/null || echo "   (pods não acessíveis)"
    else
        echo -e "${YELLOW}   ⚠ Namespace cert-manager NÃO existe${NC}"
        echo -e "${YELLOW}   💡 Instalar: kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml${NC}"
    fi
    echo ""

    # 6. Testar endpoint
    echo -e "${YELLOW}6️⃣ Testando endpoint Schema Registry...${NC}"
    SR_POD=$(kubectl get pod -n kafka -l app=schema-registry -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$SR_POD" ]; then
        POD_STATUS=$(kubectl get pod -n kafka "$SR_POD" -o jsonpath='{.status.phase}')
        if [ "$POD_STATUS" = "Running" ]; then
            echo -e "${BLUE}   Executando: curl -k https://schema-registry.kafka.svc.cluster.local:8081/subjects${NC}"
            RESULT=$(kubectl exec -n kafka "$SR_POD" -- curl -k -s https://localhost:8081/subjects 2>&1 || echo "Falha na conexão")
            if echo "$RESULT" | grep -q "\["; then
                echo -e "${GREEN}   ✓ Schema Registry respondendo!${NC}"
                echo -e "   Subjects: $RESULT"
            else
                echo -e "${RED}   ✗ Schema Registry não respondeu corretamente${NC}"
                echo -e "   Result: $RESULT"
            fi
        else
            echo -e "${YELLOW}   ⚠ Pod não está Running (status: $POD_STATUS)${NC}"
        fi
    else
        echo -e "${YELLOW}   ⚠ Nenhum pod para teste de endpoint${NC}"
    fi
    echo ""

    # 7. Verificar configuração Kafka
    echo -e "${YELLOW}7️⃣ Verificando conexão com Kafka...${NC}"
    KAFKA_PODS=$(kubectl get pods -n kafka -l app=strimzi -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$KAFKA_PODS" ]; then
        echo -e "${GREEN}   ✓ Kafka pods encontrados${NC}"
    else
        echo -e "${YELLOW}   ⚠ Nenhum pod Kafka encontrado (verificar instalação do Strimzi)${NC}"
    fi
    echo ""
}

# =============================================================================
# Execução Principal
# =============================================================================

if [ "$CHECK_REDIS" = true ]; then
    diagnose_redis
fi

if [ "$CHECK_SCHEMA_REGISTRY" = true ]; then
    diagnose_schema_registry
fi

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Diagnóstico concluído!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
