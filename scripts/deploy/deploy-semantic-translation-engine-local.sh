#!/bin/bash
# Script de deploy do Semantic Translation Engine para ambiente local (Minikube)
set -euo pipefail

# Cores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para log
log_info() {
  echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
  echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Variáveis
ENV=local
NAMESPACE="semantic-translation-engine"
IMAGE_TAG=local
CHART_PATH="./helm-charts/semantic-translation-engine"
VALUES_FILE="./helm-charts/semantic-translation-engine/values-local.yaml"
SERVICE_DIR="./services/semantic-translation-engine"

log_info "=========================================="
log_info "Deploy do Semantic Translation Engine"
log_info "Ambiente: ${ENV}"
log_info "Namespace: ${NAMESPACE}"
log_info "=========================================="

# 1. Validação de Pré-requisitos
log_info "Passo 1/7: Validando pré-requisitos..."

# Verificar Minikube
if ! minikube status &> /dev/null; then
  log_error "Minikube não está rodando. Execute: minikube start"
  exit 1
fi
log_info "✓ Minikube está rodando"

# Verificar kubectl
if ! kubectl cluster-info &> /dev/null; then
  log_error "kubectl não está configurado corretamente"
  exit 1
fi
log_info "✓ kubectl configurado"

# Verificar helm
if ! command -v helm &> /dev/null; then
  log_error "helm não está instalado"
  exit 1
fi
log_info "✓ helm instalado"

# Verificar infraestrutura deployada
log_info "Verificando dependências de infraestrutura..."

# Kafka
if ! kubectl get pods -n neural-hive-kafka -l app.kubernetes.io/name=kafka &> /dev/null; then
  log_error "Kafka não está deployado. Execute o deploy da infraestrutura primeiro."
  exit 1
fi
log_info "✓ Kafka deployado"

# Neo4j
if ! kubectl get pods -n neo4j &> /dev/null; then
  log_warning "Neo4j pode não estar deployado corretamente"
fi

# MongoDB
if ! kubectl get pods -n mongodb-cluster &> /dev/null; then
  log_warning "MongoDB pode não estar deployado corretamente"
fi

# Redis
if ! kubectl get pods -n redis-cluster &> /dev/null; then
  log_warning "Redis pode não estar deployado corretamente"
fi

# 2. Build da Imagem Docker
log_info "Passo 2/7: Construindo imagem Docker..."

# Configurar Docker para usar daemon do Minikube
log_info "Configurando Docker para usar daemon do Minikube..."
eval $(minikube docker-env)

# Build da imagem a partir da raiz do repositório
log_info "Executando docker build..."

if docker build -f services/semantic-translation-engine/Dockerfile -t neural-hive-mind/semantic-translation-engine:${IMAGE_TAG} .; then
  log_info "✓ Imagem construída com sucesso"
else
  log_error "Falha no build da imagem Docker"
  exit 1
fi

# Verificar imagem
if docker images neural-hive-mind/semantic-translation-engine:${IMAGE_TAG} | grep -q "${IMAGE_TAG}"; then
  log_info "✓ Imagem verificada no registry local"
else
  log_error "Imagem não encontrada no registry local"
  exit 1
fi

# 3. Criar Namespace
log_info "Passo 3/7: Criando namespace..."

if kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f - &> /dev/null; then
  log_info "✓ Namespace ${NAMESPACE} criado/atualizado"
fi

# Aplicar labels
kubectl label namespace ${NAMESPACE} \
  neural-hive.io/component=semantic-translator \
  neural-hive.io/layer=cognitiva \
  --overwrite &> /dev/null

# 4. Criar Secrets
log_info "Passo 4/7: Preparando secrets..."

if ! kubectl get secret semantic-translation-engine-secrets -n ${NAMESPACE} &> /dev/null; then
  log_info "Criando secrets com valores padrão para ambiente local..."
  kubectl create secret generic semantic-translation-engine-secrets \
    --from-literal=kafka_sasl_password="" \
    --from-literal=neo4j_password="neo4j" \
    --from-literal=mongodb_password="" \
    --from-literal=redis_password="" \
    -n ${NAMESPACE}
  log_info "✓ Secrets criados"
else
  log_info "✓ Secrets já existem"
fi

# 5. Deploy via Helm
log_info "Passo 5/7: Deployando via Helm..."

if ! test -f "${VALUES_FILE}"; then
  log_error "Arquivo de valores não encontrado: ${VALUES_FILE}"
  exit 1
fi

log_info "Executando helm upgrade..."
if helm upgrade --install semantic-translation-engine ${CHART_PATH} \
  --namespace ${NAMESPACE} \
  --values ${VALUES_FILE} \
  --set image.tag=${IMAGE_TAG} \
  --set image.pullPolicy=IfNotPresent \
  --wait --timeout 10m; then
  log_info "✓ Helm deployment concluído"
else
  log_error "Falha no deployment do Helm"
  log_info "Verificando logs do pod..."
  kubectl logs -n ${NAMESPACE} -l app.kubernetes.io/name=semantic-translation-engine --tail=50 || true
  exit 1
fi

# 6. Validação Pós-Deploy
log_info "Passo 6/7: Validando deployment..."

# Verificar rollout
log_info "Aguardando rollout do deployment..."
if kubectl rollout status deployment/semantic-translation-engine -n ${NAMESPACE} --timeout=5m; then
  log_info "✓ Deployment rollout concluído"
else
  log_error "Rollout falhou"
  exit 1
fi

# Verificar pod está Running
log_info "Verificando status do pod..."
POD_STATUS=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=semantic-translation-engine -o jsonpath='{.items[0].status.phase}')
if [ "${POD_STATUS}" == "Running" ]; then
  log_info "✓ Pod está Running"
else
  log_error "Pod não está Running (status: ${POD_STATUS})"
  kubectl describe pod -n ${NAMESPACE} -l app.kubernetes.io/name=semantic-translation-engine
  exit 1
fi

# Aguardar 5 segundos para inicialização
log_info "Aguardando inicialização do serviço..."
sleep 5

# Verificar logs iniciais
log_info "Verificando logs iniciais..."
kubectl logs -n ${NAMESPACE} -l app.kubernetes.io/name=semantic-translation-engine --tail=20

# Testar health endpoint
log_info "Testando health endpoint..."
POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=semantic-translation-engine -o jsonpath='{.items[0].metadata.name}')

if kubectl exec -n ${NAMESPACE} ${POD_NAME} -- wget -q -O- http://localhost:8000/health &> /dev/null; then
  log_info "✓ Health endpoint respondendo"
else
  log_warning "Health endpoint não está respondendo ainda"
fi

# 7. Output de Informações Úteis
log_info "Passo 7/7: Deploy concluído!"

echo ""
log_info "=========================================="
log_info "DEPLOYMENT CONCLUÍDO COM SUCESSO!"
log_info "=========================================="
echo ""
log_info "Namespace: ${NAMESPACE}"
log_info "Pod: ${POD_NAME}"
echo ""
log_info "Comandos úteis:"
echo ""
echo "  # Ver logs em tempo real:"
echo "  kubectl logs -n ${NAMESPACE} -l app.kubernetes.io/name=semantic-translation-engine -f"
echo ""
echo "  # Port-forward para health checks:"
echo "  kubectl port-forward -n ${NAMESPACE} svc/semantic-translation-engine 8000:8000"
echo ""
echo "  # Port-forward para métricas:"
echo "  kubectl port-forward -n ${NAMESPACE} svc/semantic-translation-engine 8080:8080"
echo ""
echo "  # Verificar readiness:"
echo "  curl http://localhost:8000/ready"
echo ""
echo "  # Ver métricas Prometheus:"
echo "  curl http://localhost:8080/metrics"
echo ""
echo "  # Reiniciar deployment:"
echo "  kubectl rollout restart deployment/semantic-translation-engine -n ${NAMESPACE}"
echo ""
log_info "=========================================="
log_info "Próximo passo: Executar testes"
log_info "  ./tests/test-semantic-translation-engine-local.sh"
log_info "=========================================="
