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

SCRIPT_NAME=$(basename "$0")
CONFIG_FILE="environments/local/fluxo-b-config.yaml"
CHARTS_DIR="helm-charts"
STE_CHART="${CHARTS_DIR}/semantic-translation-engine"
OUTPUT_FILES=()

DRY_RUN=0
FORCE=0
STRICT_IMAGE_CHECK=0
KAFKA_ENDPOINT=""
NEO4J_ENDPOINT=""
MONGODB_ENDPOINT=""
REDIS_ENDPOINT=""
MLFLOW_ENDPOINT=""
OTEL_ENDPOINT=""

usage() {
  cat <<USAGE
Uso: $0 [opções]
  --dry-run                 Executa apenas validações (não gera valores)
  --force                   Sobrescreve arquivos values-local-generated existentes
  --kafka-endpoint <host>   Override manual para o bootstrap Kafka (host:port)
  --neo4j-endpoint <uri>    Override manual para o endpoint Neo4j (ex: bolt://host:7687)
  --mongodb-endpoint <uri>  Override manual para o endpoint MongoDB (ex: mongodb://host:27017)
  --redis-endpoint <host>   Override manual para o Redis cluster (host:port)
  --mlflow-endpoint <url>   Override manual para o MLflow (ex: http://host:5000)
  --otel-endpoint <url>     Override manual para o OpenTelemetry collector
  --strict-image-check      Falha se alguma imagem não estiver presente no containerd
  -h, --help                Exibe esta ajuda
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
    --neo4j-endpoint)
      NEO4J_ENDPOINT="${2:-}"
      shift 2
      ;;
    --mongodb-endpoint)
      MONGODB_ENDPOINT="${2:-}"
      shift 2
      ;;
    --redis-endpoint)
      REDIS_ENDPOINT="${2:-}"
      shift 2
      ;;
    --mlflow-endpoint)
      MLFLOW_ENDPOINT="${2:-}"
      shift 2
      ;;
    --otel-endpoint)
      OTEL_ENDPOINT="${2:-}"
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

cleanup_files=()
cleanup() {
  if [[ ${#cleanup_files[@]} -gt 0 ]]; then
    rm -f "${cleanup_files[@]}" || true
  fi
}
trap cleanup EXIT

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
  log_error "É necessário yq v4.x para manipular o YAML do Fluxo B."
  exit 1
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
  log_error "Arquivo de configuração ${CONFIG_FILE} não encontrado."
  exit 1
fi

if [[ ! -d "$STE_CHART" ]]; then
  log_error "Chart do Semantic Translation Engine não encontrado em ${STE_CHART}"
  exit 1
fi

mapfile -t SPECIALIST_NAMES < <(yq -r '.specialists[].name' "$CONFIG_FILE")
if [[ ${#SPECIALIST_NAMES[@]} -eq 0 ]]; then
  log_error "Nenhum specialist definido em ${CONFIG_FILE}"
  exit 1
fi

for specialist in "${SPECIALIST_NAMES[@]}"; do
  chart_dir="${CHARTS_DIR}/${specialist}"
  if [[ ! -d "$chart_dir" ]]; then
    log_error "Chart para ${specialist} não encontrado em ${chart_dir}"
    exit 1
  fi
done

for namespace in kafka neo4j-cluster mongodb-cluster redis-cluster mlflow observability; do
  if ! kubectl get namespace "$namespace" >/dev/null 2>&1; then
    log_error "Namespace obrigatório não encontrado: ${namespace}. Execute os guias anteriores."
    exit 1
  fi
done

log_info "Validando conectividade com o cluster Kubernetes"
kubectl cluster-info >/dev/null 2>&1 || {
  log_error "kubectl não consegue falar com o cluster."
  exit 1
}

detect_service_endpoint() {
  local namespace=$1
  local service=$2
  local port_index=$3
  local fallback=$4
  if kubectl get svc -n "$namespace" "$service" >/dev/null 2>&1; then
    kubectl get svc -n "$namespace" "$service" -o jsonpath="{.metadata.name}.{.metadata.namespace}.svc.cluster.local:{.spec.ports[$port_index].port}"
  else
    echo "$fallback"
  fi
}

DEFAULT_KAFKA="neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092"
DEFAULT_NEO4J="bolt://neo4j-bolt.neo4j-cluster.svc.cluster.local:7687"
DEFAULT_MONGODB="mongodb://mongodb.mongodb-cluster.svc.cluster.local:27017"
DEFAULT_REDIS="neural-hive-cache.redis-cluster.svc.cluster.local:6379"
DEFAULT_MLFLOW="http://mlflow.mlflow.svc.cluster.local:5000"
DEFAULT_OTEL="http://opentelemetry-collector.observability.svc.cluster.local:4317"

if [[ -z "$KAFKA_ENDPOINT" ]]; then
  log_info "Detectando endpoint Kafka"
  KAFKA_ENDPOINT=$(detect_service_endpoint kafka neural-hive-kafka-kafka-bootstrap 0 "$DEFAULT_KAFKA")
fi

if [[ -z "$NEO4J_ENDPOINT" ]]; then
  log_info "Detectando endpoint Neo4j"
  detected_bolt=$(detect_service_endpoint neo4j-cluster neo4j-bolt 0 "${DEFAULT_NEO4J#bolt://}")
  if [[ "$detected_bolt" == "${DEFAULT_NEO4J#bolt://}" ]]; then
    NEO4J_ENDPOINT="$DEFAULT_NEO4J"
  else
    NEO4J_ENDPOINT="bolt://${detected_bolt}"
  fi
fi

if [[ -z "$MONGODB_ENDPOINT" ]]; then
  log_info "Detectando endpoint MongoDB"
  detected_mongo=$(detect_service_endpoint mongodb-cluster mongodb 0 "${DEFAULT_MONGODB#mongodb://}")
  if [[ "$detected_mongo" == "${DEFAULT_MONGODB#mongodb://}" ]]; then
    MONGODB_ENDPOINT="$DEFAULT_MONGODB"
  else
    MONGODB_ENDPOINT="mongodb://${detected_mongo}"
  fi
fi

if [[ -z "$REDIS_ENDPOINT" ]]; then
  log_info "Detectando endpoint Redis"
  REDIS_ENDPOINT=$(detect_service_endpoint redis-cluster neural-hive-cache 0 "$DEFAULT_REDIS")
fi

if [[ -z "$MLFLOW_ENDPOINT" ]]; then
  log_info "Detectando endpoint MLflow"
  detected_mlflow=$(detect_service_endpoint mlflow mlflow 0 "${DEFAULT_MLFLOW#http://}")
  if [[ "$detected_mlflow" == "${DEFAULT_MLFLOW#http://}" ]]; then
    MLFLOW_ENDPOINT="$DEFAULT_MLFLOW"
  else
    MLFLOW_ENDPOINT="http://${detected_mlflow}"
  fi
fi

if [[ -z "$OTEL_ENDPOINT" ]]; then
  log_info "Detectando endpoint OpenTelemetry"
  detected_otel=$(detect_service_endpoint observability opentelemetry-collector 0 "${DEFAULT_OTEL#http://}")
  if [[ "$detected_otel" == "${DEFAULT_OTEL#http://}" ]]; then
    OTEL_ENDPOINT="$DEFAULT_OTEL"
  else
    OTEL_ENDPOINT="http://${detected_otel}"
  fi
fi

check_image_in_containerd() {
  local image=$1
  if ! command -v ctr >/dev/null 2>&1; then
    log_warning "ctr não encontrado; pulando verificação local da imagem ${image}."
    return
  fi
  if sudo ctr -n k8s.io images ls | grep -q "$image"; then
    log_success "Imagem localizada no containerd: ${image}"
  else
    local msg="Imagem ${image} não encontrada no containerd."
    if [[ $STRICT_IMAGE_CHECK -eq 1 ]]; then
      log_error "$msg"
      exit 1
    else
      log_warning "$msg Importe manualmente com sudo ctr -n k8s.io images import <arquivo.tar>"
    fi
  fi
}

CONTAINER_RUNTIME_INFO=$(kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.containerRuntimeVersion}' 2>/dev/null || echo "")
if echo "$CONTAINER_RUNTIME_INFO" | grep -qi "containerd"; then
  log_info "Runtime container é containerd; validando imagens locais"
  check_image_in_containerd "neural-hive-mind/semantic-translation-engine:1.0.0"
  check_image_in_containerd "neural-hive-mind/specialist-business:1.0.0"
  check_image_in_containerd "neural-hive-mind/specialist-technical:1.0.0"
  check_image_in_containerd "neural-hive-mind/specialist-behavior:1.0.0"
  check_image_in_containerd "neural-hive-mind/specialist-evolution:1.0.0"
  check_image_in_containerd "neural-hive-mind/specialist-architecture:1.0.0"
else
  log_warning "Runtime container não identificado como containerd; pulando verificação explícita das imagens."
fi

if [[ $DRY_RUN -eq 1 ]]; then
  log_success "Pré-requisitos verificados com sucesso (dry-run)."
  exit 0
fi

assert_pull_policy() {
  local file=$1
  local policy
  policy=$(yq -r '.image.pullPolicy // ""' "$file")
  if [[ "$policy" != "Never" ]]; then
    log_warning "Atualizando image.pullPolicy para Never em ${file}"
    yq eval -i '.image.pullPolicy = "Never"' "$file"
  fi
}

ensure_required_field() {
  local file=$1
  local query=$2
  local message=$3
  local value
  value=$(yq -r "$query // \"\"" "$file")
  if [[ -z "$value" || "$value" == "null" ]]; then
    log_error "$message"
    exit 1
  fi
}

GENERATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
CLUSTER_CONTEXT=$(kubectl config current-context 2>/dev/null || echo "unknown")

write_output() {
  local tmp_file=$1
  local output=$2
  if [[ -f "$output" && $FORCE -eq 0 ]]; then
    log_error "Arquivo ${output} já existe. Use --force para sobrescrever."
    exit 1
  fi
  mkdir -p "$(dirname "$output")"
  yq eval '.' "$tmp_file" > "$output"
  OUTPUT_FILES+=("$output")
  log_success "Arquivo gerado: ${output}"
}

generate_ste_values() {
  local tmp_file
  tmp_file=$(mktemp)
  cleanup_files+=("$tmp_file")
  yq eval '.semanticTranslationEngine' "$CONFIG_FILE" > "$tmp_file"

  yq eval -i ".config.kafka.bootstrapServers = \"$KAFKA_ENDPOINT\"" "$tmp_file"
  yq eval -i ".config.neo4j.uri = \"$NEO4J_ENDPOINT\"" "$tmp_file"
  yq eval -i ".config.mongodb.uri = \"$MONGODB_ENDPOINT\"" "$tmp_file"
  yq eval -i ".config.redis.clusterNodes = \"$REDIS_ENDPOINT\"" "$tmp_file"
  yq eval -i ".config.openTelemetry.endpoint = \"$OTEL_ENDPOINT\"" "$tmp_file"
  yq eval -i ".metadata.generated_at = \"$GENERATED_AT\"" "$tmp_file"
  yq eval -i ".metadata.generated_by = \"$SCRIPT_NAME\"" "$tmp_file"
  yq eval -i ".metadata.cluster_context = \"$CLUSTER_CONTEXT\"" "$tmp_file"
  yq eval -i '.config.kafka.securityProtocol = "PLAINTEXT"' "$tmp_file"
  yq eval -i '.config.kafka.saslMechanism = ""' "$tmp_file"

  ensure_required_field "$tmp_file" '.image.repository' "Campo image.repository ausente para o STE."
  ensure_required_field "$tmp_file" '.config.kafka.bootstrapServers' "Kafka bootstrap não definido para o STE."
  ensure_required_field "$tmp_file" '.config.kafka.plansTopic' "plansTopic não definido para o STE."

  assert_pull_policy "$tmp_file"
  write_output "$tmp_file" "${STE_CHART}/values-local-generated.yaml"
}

mongodb_uri_with_auth() {
  local base_uri=$1
  local credentials="root:local-password@"
  if [[ "$base_uri" == mongodb://* ]]; then
    echo "mongodb://${credentials}${base_uri#mongodb://}"
  else
    echo "mongodb://${credentials}${base_uri}"
  fi
}

generate_specialist_values() {
  local specialist=$1
  local chart_dir="${CHARTS_DIR}/${specialist}"
  local output="${chart_dir}/values-local-generated.yaml"

  local tmp_file
  tmp_file=$(mktemp)
  cleanup_files+=("$tmp_file")
  yq eval ".specialists[] | select(.name == \"${specialist}\")" "$CONFIG_FILE" > "$tmp_file"

  if [[ ! -s "$tmp_file" ]]; then
    log_error "Configuração não encontrada para ${specialist}"
    exit 1
  fi

  yq eval -i ".config.mongodb.uri = \"$MONGODB_ENDPOINT\"" "$tmp_file"
  yq eval -i ".config.neo4j.uri = \"$NEO4J_ENDPOINT\"" "$tmp_file"
  yq eval -i ".config.redis.clusterNodes = \"$REDIS_ENDPOINT\"" "$tmp_file"
  yq eval -i ".config.mlflow.trackingUri = \"$MLFLOW_ENDPOINT\"" "$tmp_file"
  yq eval -i ".config.otel.endpoint = \"$OTEL_ENDPOINT\"" "$tmp_file"
  yq eval -i ".metadata.generated_at = \"$GENERATED_AT\"" "$tmp_file"
  yq eval -i ".metadata.generated_by = \"$SCRIPT_NAME\"" "$tmp_file"
  yq eval -i ".metadata.cluster_context = \"$CLUSTER_CONTEXT\"" "$tmp_file"
  yq eval -i ".secrets.mongodbUri = \"$(mongodb_uri_with_auth "$MONGODB_ENDPOINT")\"" "$tmp_file"
  yq eval -i ".secrets.neo4jPassword = \"neo4j-local-password\"" "$tmp_file"
  yq eval -i ".secrets.redisPassword = \"\"" "$tmp_file"

  ensure_required_field "$tmp_file" '.image.repository' "Campo image.repository ausente para ${specialist}."
  ensure_required_field "$tmp_file" '.config.grpc.port' "Porta gRPC ausente para ${specialist}."
  ensure_required_field "$tmp_file" '.config.mongodb.opinionsCollection' "Collection MongoDB não definida para ${specialist}."

  assert_pull_policy "$tmp_file"
  write_output "$tmp_file" "$output"
}

generate_ste_values

for specialist in "${SPECIALIST_NAMES[@]}"; do
  generate_specialist_values "$specialist"
done

validate_endpoints_in_files() {
  local search=$1
  local label=$2
  for file in "${OUTPUT_FILES[@]}"; do
    if ! grep -q "$search" "$file"; then
      log_warning "Endpoint ${label} não aparece explicitamente em ${file}."
    fi
  done
}

validate_endpoints_in_files "kafka" "Kafka"
validate_endpoints_in_files "neo4j" "Neo4j"
validate_endpoints_in_files "mongodb" "MongoDB"
validate_endpoints_in_files "redis" "Redis"

cpu_to_millicores() {
  local value=$1
  if [[ -z "$value" || "$value" == "null" ]]; then
    echo 0
    return
  fi
  if [[ "$value" == *m ]]; then
    echo "${value%m}"
  else
    awk "BEGIN {printf \"%d\", $value * 1000}"
  fi
}

memory_to_mib() {
  local value=$1
  if [[ -z "$value" || "$value" == "null" ]]; then
    echo 0
    return
  fi
  if [[ "$value" == *Gi ]]; then
    local num=${value%Gi}
    awk "BEGIN {printf \"%d\", $num * 1024}"
  elif [[ "$value" == *Mi ]]; then
    echo "${value%Mi}"
  else
    echo 0
  fi
}

TOTAL_CPU_M=0
TOTAL_MEM_MI=0

accumulate_resources() {
  local query=$1
  local cpu
  local mem
  cpu=$(yq -r "${query}.resources.requests.cpu // \"0\"" "$CONFIG_FILE")
  mem=$(yq -r "${query}.resources.requests.memory // \"0Mi\"" "$CONFIG_FILE")
  TOTAL_CPU_M=$((TOTAL_CPU_M + $(cpu_to_millicores "$cpu")))
  TOTAL_MEM_MI=$((TOTAL_MEM_MI + $(memory_to_mib "$mem")))
}

accumulate_resources ".semanticTranslationEngine"
index=0
for specialist in "${SPECIALIST_NAMES[@]}"; do
  accumulate_resources ".specialists[${index}]"
  ((index++))
done

TOTAL_CPU_CORES=$(awk "BEGIN {printf \"%.2f\", ${TOTAL_CPU_M} / 1000}")
TOTAL_MEM_GI=$(awk "BEGIN {printf \"%.2f\", ${TOTAL_MEM_MI} / 1024}")

log_info "O script não verifica automaticamente a capacidade do cluster."
log_info "Revise manualmente 'kubectl top nodes' (quando metrics-server estiver disponível) e compare com os requests estimados: ${TOTAL_CPU_CORES} vCPU / ${TOTAL_MEM_GI} GiB."

log_success "Arquivos de valores gerados:"
for file in "${OUTPUT_FILES[@]}"; do
  echo "  - ${file}"
done

log_success "Endpoints detectados: Kafka=${KAFKA_ENDPOINT}, Neo4j=${NEO4J_ENDPOINT}, MongoDB=${MONGODB_ENDPOINT}, Redis=${REDIS_ENDPOINT}, MLflow=${MLFLOW_ENDPOINT}, OTEL=${OTEL_ENDPOINT}"
log_success "Recursos totais estimados (requests): ${TOTAL_CPU_CORES} vCPU / ${TOTAL_MEM_GI} GiB"
log_info "Próximo passo sugerido: executar helm upgrade --install semantic-translation-engine ... e helm upgrade --install specialist-<tipo> ... conforme guia 06-fluxo-b-deployment-manual-guide.md"
