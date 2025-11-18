#!/bin/bash
# Script de deployment para EKS - Neural Hive-Mind
# Versão: 1.0

set -euo pipefail

# Cores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Carregar variáveis de ambiente
if [ -f ~/.neural-hive-dev-env ]; then
    source ~/.neural-hive-dev-env
else
    log_error "Arquivo de ambiente não encontrado: ~/.neural-hive-dev-env"
    exit 1
fi

log_info "============================================"
log_info "Deployment Neural Hive-Mind no EKS"
log_info "============================================"
log_info "Cluster: ${CLUSTER_NAME}"
log_info "Region: ${AWS_REGION}"
log_info ""

# Verificar conectividade com cluster
log_info "Verificando conectividade com cluster..."
if ! kubectl cluster-info >/dev/null 2>&1; then
    log_error "Não foi possível conectar ao cluster. Verifique kubectl config."
    exit 1
fi
log_success "✓ Conectado ao cluster"

# Verificar nodes
log_info "Verificando nodes..."
NODE_COUNT=$(kubectl get nodes --no-headers 2>/dev/null | wc -l)
if [ "$NODE_COUNT" -eq 0 ]; then
    log_error "Nenhum node disponível no cluster"
    exit 1
fi
log_success "✓ $NODE_COUNT nodes disponíveis"

# Criar namespaces
log_info "Criando namespaces..."
NAMESPACES=("infrastructure" "applications" "monitoring" "specialists")
for ns in "${NAMESPACES[@]}"; do
    if kubectl get namespace "$ns" >/dev/null 2>&1; then
        log_info "  Namespace $ns já existe"
    else
        kubectl create namespace "$ns"
        log_success "  ✓ Namespace $ns criado"
    fi
done

# Deploy de infraestrutura
log_info ""
log_info "============================================"
log_info "FASE 1: Deploy de Infraestrutura"
log_info "============================================"

# Kafka
log_info "Deploying Kafka..."
if helm list -n infrastructure | grep -q kafka; then
    log_info "  Kafka já está instalado, fazendo upgrade..."
    helm upgrade kafka ./helm-charts/kafka -n infrastructure
else
    helm install kafka ./helm-charts/kafka -n infrastructure
fi
log_success "✓ Kafka deployed"

# Aguardar Kafka ficar ready
log_info "Aguardando Kafka ficar pronto..."
kubectl wait --for=condition=ready pod -l app=kafka -n infrastructure --timeout=300s || log_warning "Kafka demorou mais que esperado"

# MongoDB
log_info "Deploying MongoDB..."
if helm list -n infrastructure | grep -q mongodb; then
    helm upgrade mongodb ./helm-charts/mongodb -n infrastructure \
        --set auth.rootPassword="${MONGODB_ROOT_PASSWORD}"
else
    helm install mongodb ./helm-charts/mongodb -n infrastructure \
        --set auth.rootPassword="${MONGODB_ROOT_PASSWORD}"
fi
log_success "✓ MongoDB deployed"

# Redis
log_info "Deploying Redis..."
if helm list -n infrastructure | grep -q redis; then
    helm upgrade redis ./helm-charts/redis -n infrastructure
else
    helm install redis ./helm-charts/redis -n infrastructure
fi
log_success "✓ Redis deployed"

# Neo4j
log_info "Deploying Neo4j..."
if helm list -n infrastructure | grep -q neo4j; then
    helm upgrade neo4j ./helm-charts/neo4j -n infrastructure \
        --set neo4j.password="${NEO4J_PASSWORD}"
else
    helm install neo4j ./helm-charts/neo4j -n infrastructure \
        --set neo4j.password="${NEO4J_PASSWORD}"
fi
log_success "✓ Neo4j deployed"

# ClickHouse
log_info "Deploying ClickHouse..."
if helm list -n infrastructure | grep -q clickhouse; then
    helm upgrade clickhouse ./helm-charts/clickhouse -n infrastructure
else
    helm install clickhouse ./helm-charts/clickhouse -n infrastructure
fi
log_success "✓ ClickHouse deployed"

log_info ""
log_info "Aguardando infraestrutura ficar pronta (60s)..."
sleep 60

# Verificar imagens disponíveis no ECR
log_info ""
log_info "============================================"
log_info "FASE 2: Verificando Imagens no ECR"
log_info "============================================"

SERVICES=("consensus-engine" "memory-layer-api" "gateway-intencoes" "semantic-translation-engine")
AVAILABLE_SERVICES=()

for service in "${SERVICES[@]}"; do
    if aws ecr describe-images --repository-name "dev/${service}" --region "${AWS_REGION}" --query 'imageDetails[?imageTags[?contains(@, `latest`)]]' --output text >/dev/null 2>&1; then
        log_success "✓ $service: imagem disponível"
        AVAILABLE_SERVICES+=("$service")
    else
        log_warning "⚠ $service: imagem não encontrada no ECR"
    fi
done

# Deploy de aplicações
log_info ""
log_info "============================================"
log_info "FASE 3: Deploy de Aplicações"
log_info "============================================"

for service in "${AVAILABLE_SERVICES[@]}"; do
    log_info "Deploying $service..."

    IMAGE_URI="${ECR_REGISTRY}/${ENV}/${service}:latest"

    if helm list -n applications | grep -q "$service"; then
        helm upgrade "$service" "./helm-charts/${service}" -n applications \
            --set image.repository="${ECR_REGISTRY}/${ENV}/${service}" \
            --set image.tag="latest"
    else
        helm install "$service" "./helm-charts/${service}" -n applications \
            --set image.repository="${ECR_REGISTRY}/${ENV}/${service}" \
            --set image.tag="latest"
    fi

    log_success "✓ $service deployed"
done

# Deploy de specialists
log_info ""
log_info "============================================"
log_info "FASE 4: Deploy de Specialists"
log_info "============================================"

SPECIALISTS=("business" "technical" "behavior" "evolution" "architecture")
for spec in "${SPECIALISTS[@]}"; do
    service="specialist-${spec}"

    if aws ecr describe-images --repository-name "dev/${service}" --region "${AWS_REGION}" --query 'imageDetails[?imageTags[?contains(@, `latest`)]]' --output text >/dev/null 2>&1; then
        log_info "Deploying $service..."

        if helm list -n specialists | grep -q "$service"; then
            helm upgrade "$service" "./helm-charts/${service}" -n specialists \
                --set image.repository="${ECR_REGISTRY}/${ENV}/${service}" \
                --set image.tag="latest"
        else
            helm install "$service" "./helm-charts/${service}" -n specialists \
                --set image.repository="${ECR_REGISTRY}/${ENV}/${service}" \
                --set image.tag="latest"
        fi

        log_success "✓ $service deployed"
    else
        log_warning "⚠ $service: imagem não disponível, pulando..."
    fi
done

# Resumo final
log_info ""
log_info "============================================"
log_info "DEPLOYMENT COMPLETO"
log_info "============================================"

log_info "Verificando pods..."
echo ""
echo "=== INFRASTRUCTURE ==="
kubectl get pods -n infrastructure
echo ""
echo "=== APPLICATIONS ==="
kubectl get pods -n applications
echo ""
echo "=== SPECIALISTS ==="
kubectl get pods -n specialists
echo ""

log_info "Verificando services..."
echo "=== SERVICES ==="
kubectl get svc -n applications
echo ""

log_success "============================================"
log_success "Deployment concluído!"
log_success "============================================"
log_info ""
log_info "Próximos passos:"
log_info "  1. Verificar logs: kubectl logs -f deployment/<service> -n <namespace>"
log_info "  2. Verificar health: kubectl get pods --all-namespaces"
log_info "  3. Acessar serviços: kubectl port-forward svc/<service> 8080:80 -n applications"
log_info ""
