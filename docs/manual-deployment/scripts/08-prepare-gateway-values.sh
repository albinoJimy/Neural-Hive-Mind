#!/usr/bin/env bash
set -euo pipefail

GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
BLUE="\033[0;34m"
NC="\033[0m"

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERR]${NC} $1"; }

CONFIG_FILE="environments/local/gateway-config.yaml"
VALUES_OUTPUT="helm-charts/gateway-intencoes/values-local-generated.yaml"
CHART_DIR="helm-charts/gateway-intencoes"
DRY_RUN=0
FORCE=0
STRICT_IMAGE_CHECK=0
KAFKA_ENDPOINT=""
REDIS_ENDPOINT=""

usage() {
  cat <<USAGE
Uso: $0 [opções]
  --dry-run               Apenas valida dependências (não gera arquivo)
  --force                 Sobrescreve values-local-generated.yaml existente
  --kafka-endpoint <url>  Override do endpoint Kafka detectado automaticamente
  --redis-endpoint <url>  Override do endpoint Redis detectado automaticamente
  --strict-image-check    Falha se a imagem não estiver disponível no containerd
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --kafka-endpoint)
      KAFKA_ENDPOINT="${2:-}"
      shift 2
      ;;
    --redis-endpoint)
      REDIS_ENDPOINT="${2:-}"
      shift 2
      ;;
    --strict-image-check)
      STRICT_IMAGE_CHECK=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      log_error "Opção desconhecida: $1"
      usage
      exit 1
      ;;
  esac
done

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log_error "Comando obrigatório não encontrado: $1"
    exit 1
  fi
}

require_command yq
require_command kubectl
require_command uuidgen

YQ_VERSION=$(yq --version 2>/dev/null || true)
if [[ "$YQ_VERSION" != v4* && "$YQ_VERSION" != "yq (https://github.com/mikefarah/yq/) version v4"* ]]; then
  log_error "É necessário yq v4.x (instale via https://github.com/mikefarah/yq)."
  exit 1
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
  log_error "Arquivo de configuração não encontrado: $CONFIG_FILE"
  exit 1
fi

if [[ ! -d "$CHART_DIR" ]]; then
  log_error "Chart do gateway não encontrado em $CHART_DIR"
  exit 1
fi

if [[ -f "$VALUES_OUTPUT" && $FORCE -eq 0 && $DRY_RUN -eq 0 ]]; then
  log_error "Arquivo $VALUES_OUTPUT já existe. Use --force para sobrescrever."
  exit 1
fi

IMAGE_REPOSITORY_CONFIG=$(yq -r '.gateway.image.repository // ""' "$CONFIG_FILE")
IMAGE_TAG_CONFIG=$(yq -r '.gateway.image.tag // "latest"' "$CONFIG_FILE")
if [[ -z "$IMAGE_REPOSITORY_CONFIG" || "$IMAGE_REPOSITORY_CONFIG" == "null" ]]; then
  log_error "Campo gateway.image.repository não definido em $CONFIG_FILE"
  exit 1
fi

log_info "Validando namespaces kafka e redis-cluster"
if ! kubectl get namespace kafka >/dev/null 2>&1 || ! kubectl get namespace redis-cluster >/dev/null 2>&1; then
  log_error "Namespaces kafka e/ou redis-cluster não encontrados. Execute os guias anteriores."
  exit 1
fi

log_info "Verificando conectividade do kubectl"
kubectl cluster-info >/dev/null 2>&1 || {
  log_error "kubectl não consegue falar com o cluster."
  exit 1
}

detect_service_endpoint() {
  local namespace=$1
  local service=$2
  local default_value=$3
  if kubectl get svc -n "$namespace" "$service" >/dev/null 2>&1; then
    kubectl get svc -n "$namespace" "$service" -o jsonpath='{.metadata.name}.{.metadata.namespace}.svc.cluster.local:{.spec.ports[0].port}'
  else
    echo "$default_value"
  fi
}

if [[ -z "$KAFKA_ENDPOINT" ]]; then
  log_info "Detectando endpoint Kafka"
  KAFKA_ENDPOINT=$(detect_service_endpoint kafka neural-hive-kafka-kafka-bootstrap "neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092")
fi

if [[ -z "$REDIS_ENDPOINT" ]]; then
  log_info "Detectando endpoint Redis"
  REDIS_ENDPOINT=$(detect_service_endpoint redis-cluster neural-hive-cache "neural-hive-cache.redis-cluster.svc.cluster.local:6379")
fi

CONTAINER_RUNTIME_INFO=$(kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.containerRuntimeVersion}' 2>/dev/null || echo "")
log_info "Verificando imagem local ${IMAGE_REPOSITORY_CONFIG}:${IMAGE_TAG_CONFIG}"
if echo "$CONTAINER_RUNTIME_INFO" | grep -qi "containerd"; then
  if command -v ctr >/dev/null 2>&1; then
    if sudo ctr -n k8s.io images ls | grep -q "${IMAGE_REPOSITORY_CONFIG}:${IMAGE_TAG_CONFIG}"; then
      log_success "Imagem encontrada no containerd local."
    else
      MSG="Imagem ${IMAGE_REPOSITORY_CONFIG}:${IMAGE_TAG_CONFIG} não encontrada no containerd. Para ambientes locais utilize neural-hive-mind/gateway-intencoes:1.0.0; em produção use neural-hive/gateway-intencoes:latest (consulte docs/manual-deployment/04-services-build-manual-guide.md)."
      if [[ $STRICT_IMAGE_CHECK -eq 1 ]]; then
        log_error "$MSG"
        exit 1
      else
        log_warning "$MSG"
        log_info "Para importar manualmente: sudo ctr -n k8s.io images import /tmp/neural-hive-images/gateway-intencoes.tar"
      fi
    fi
  else
    log_warning "Ferramenta ctr não encontrada. Pulando verificação forçada da imagem local."
  fi
else
  log_warning "Runtime container não é containerd (ou não detectado). Pulando verificação via ctr."
fi

if [[ $DRY_RUN -eq 1 ]]; then
  log_success "Pré-requisitos validados (dry-run)."
  exit 0
fi

TMP_VALUES=$(mktemp)
yq eval '.' "$CONFIG_FILE" > "$TMP_VALUES"

update_yaml() {
  local expression=$1
  local src=$2
  local dst=$3
  yq eval "$expression" "$src" > "$dst"
}

TMP_STEP=$(mktemp)
update_yaml ".config.kafka.bootstrapServers = \"$KAFKA_ENDPOINT\"" "$TMP_VALUES" "$TMP_STEP"
mv "$TMP_STEP" "$TMP_VALUES"

TMP_STEP=$(mktemp)
update_yaml ".config.redis.clusterNodes = \"$REDIS_ENDPOINT\"" "$TMP_VALUES" "$TMP_STEP"
mv "$TMP_STEP" "$TMP_VALUES"

JWT_VALUE=$(yq -r '.secrets.jwtSecretKey // ""' "$TMP_VALUES")
if [[ -z "$JWT_VALUE" || "$JWT_VALUE" == "null" ]]; then
  NEW_SECRET=$(uuidgen | tr 'A-Z' 'a-z')
  log_info "Gerando jwtSecretKey aleatório"
  TMP_STEP=$(mktemp)
  update_yaml ".secrets.jwtSecretKey = \"$NEW_SECRET\"" "$TMP_VALUES" "$TMP_STEP"
  mv "$TMP_STEP" "$TMP_VALUES"
fi

GENERATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
CLUSTER_CONTEXT=$(kubectl config current-context 2>/dev/null || echo "unknown")
TMP_STEP=$(mktemp)
update_yaml ".metadata.generated_at = \"$GENERATED_AT\" | .metadata.generated_by = \"08-prepare-gateway-values.sh\" | .metadata.cluster_context = \"$CLUSTER_CONTEXT\"" "$TMP_VALUES" "$TMP_STEP"
mv "$TMP_STEP" "$TMP_VALUES"

mkdir -p "$(dirname "$VALUES_OUTPUT")"
FLATTENED_VALUES=$(mktemp)
yq eval '
  . as $root
  | .replicaCount = ($root.gateway.replicas // 1)
  | .image = ($root.gateway.image // {})
  | .image.pullPolicy = ($root.gateway.image.pullPolicy // "Never")
  | .resources = ($root.gateway.resources // {})
  | .service = ($root.gateway.service // {})
  | .livenessProbe = {
      "httpGet": {
        "path": "/health",
        "port": (($root.gateway.service.targetPort // 8000) | tonumber)
      },
      "initialDelaySeconds": ($root.gateway.probes.liveness.initialDelaySeconds // 90),
      "periodSeconds": ($root.gateway.probes.liveness.periodSeconds // 30),
      "timeoutSeconds": ($root.gateway.probes.liveness.timeoutSeconds // 10),
      "failureThreshold": ($root.gateway.probes.liveness.failureThreshold // 3)
    }
  | .readinessProbe = {
      "httpGet": {
        "path": "/ready",
        "port": (($root.gateway.service.targetPort // 8000) | tonumber)
      },
      "initialDelaySeconds": ($root.gateway.probes.readiness.initialDelaySeconds // 60),
      "periodSeconds": ($root.gateway.probes.readiness.periodSeconds // 10),
      "timeoutSeconds": ($root.gateway.probes.readiness.timeoutSeconds // 5),
      "failureThreshold": ($root.gateway.probes.readiness.failureThreshold // 3)
    }
  | del(.gateway)
' "$TMP_VALUES" > "$FLATTENED_VALUES"
mv "$FLATTENED_VALUES" "$VALUES_OUTPUT"
rm -f "$TMP_VALUES"

yq eval '.' "$VALUES_OUTPUT" >/dev/null

IMAGE_PULL_POLICY=$(yq -r '.image.pullPolicy // ""' "$VALUES_OUTPUT")
IMAGE_REPOSITORY=$(yq -r '.image.repository // ""' "$VALUES_OUTPUT")
CPU_REQUEST=$(yq -r '.resources.requests.cpu // ""' "$VALUES_OUTPUT")
MEM_REQUEST=$(yq -r '.resources.requests.memory // ""' "$VALUES_OUTPUT")

if [[ -z "$IMAGE_REPOSITORY" || "$IMAGE_REPOSITORY" == "null" ]]; then
  log_error "Campo image.repository não definido."
  exit 1
fi

if [[ -z "$IMAGE_PULL_POLICY" || "$IMAGE_PULL_POLICY" == "null" ]]; then
  log_error "Campo image.pullPolicy não definido após transformação."
  exit 1
fi

if [[ "$IMAGE_PULL_POLICY" != "Never" ]]; then
  log_warning "image.pullPolicy não é 'Never'. Ajustando automaticamente para evitar pulls externos."
  TMP_STEP=$(mktemp)
  update_yaml ".image.pullPolicy = \"Never\"" "$VALUES_OUTPUT" "$TMP_STEP"
  mv "$TMP_STEP" "$VALUES_OUTPUT"
  IMAGE_PULL_POLICY="Never"
fi

if [[ -n "$CPU_REQUEST" && "$CPU_REQUEST" != "null" ]]; then
  if [[ ${CPU_REQUEST%m} -lt 500 ]]; then
    log_warning "CPU request inferior a 500m. Atualizando para 500m."
    TMP_STEP=$(mktemp)
    update_yaml ".resources.requests.cpu = \"500m\"" "$VALUES_OUTPUT" "$TMP_STEP"
    mv "$TMP_STEP" "$VALUES_OUTPUT"
  fi
else
  log_warning "CPU request não definido. Definindo 500m."
  TMP_STEP=$(mktemp)
  update_yaml ".resources.requests.cpu = \"500m\"" "$VALUES_OUTPUT" "$TMP_STEP"
  mv "$TMP_STEP" "$VALUES_OUTPUT"
fi

if [[ -n "$MEM_REQUEST" && "$MEM_REQUEST" != "null" ]]; then
  MEM_VALUE=${MEM_REQUEST^^}
  if [[ "$MEM_VALUE" != *GI && "$MEM_VALUE" != *G && "$MEM_VALUE" != *GIB ]]; then
    log_warning "Memory request com formato inesperado: $MEM_REQUEST"
  fi
else
  log_warning "Memory request não definido. Definindo 1Gi."
  TMP_STEP=$(mktemp)
  update_yaml ".resources.requests.memory = \"1Gi\"" "$VALUES_OUTPUT" "$TMP_STEP"
  mv "$TMP_STEP" "$VALUES_OUTPUT"
fi

KAFKA_VALID=$(yq -r '.config.kafka.bootstrapServers' "$VALUES_OUTPUT" | grep -c "kafka") || true
REDIS_VALID=$(yq -r '.config.redis.clusterNodes' "$VALUES_OUTPUT" | grep -c "redis") || true
if [[ $KAFKA_VALID -eq 0 || $REDIS_VALID -eq 0 ]]; then
  log_error "Endpoints Kafka/Redis inválidos: verifique $VALUES_OUTPUT"
  exit 1
fi

echo ""
log_success "Arquivo gerado: $VALUES_OUTPUT"
log_success "Kafka endpoint: $KAFKA_ENDPOINT"
log_success "Redis endpoint: $REDIS_ENDPOINT"
log_success "Image pull policy: $(yq -r '.image.pullPolicy' "$VALUES_OUTPUT")"
log_success "Replicas: $(yq -r '.replicaCount // 1' "$VALUES_OUTPUT")"
log_success "Resources: $(yq -r '.resources.requests.cpu' "$VALUES_OUTPUT") CPU / $(yq -r '.resources.requests.memory' "$VALUES_OUTPUT") RAM"

echo ""
cat <<'NEXT'
Próximo passo sugerido:
helm upgrade --install gateway-intencoes helm-charts/gateway-intencoes \
  --namespace fluxo-a --create-namespace \
  -f helm-charts/gateway-intencoes/values-local-generated.yaml \
  --wait --timeout 10m
NEXT
