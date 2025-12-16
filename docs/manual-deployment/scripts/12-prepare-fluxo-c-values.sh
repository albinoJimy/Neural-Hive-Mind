#!/bin/bash
set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variáveis Globais
CONFIG_FILE="$(dirname "$0")/../../../environments/local/fluxo-c-config.yaml"
CONSENSUS_CHART_DIR="$(dirname "$0")/../../../helm-charts/consensus-engine"
ORCHESTRATOR_CHART_DIR="$(dirname "$0")/../../../helm-charts/orchestrator-dynamic"
OUTPUT_FILE_CONSENSUS="${CONSENSUS_CHART_DIR}/values-local-generated.yaml"
OUTPUT_FILE_ORCHESTRATOR="${ORCHESTRATOR_CHART_DIR}/values-local-generated.yaml"

# Flags
DRY_RUN=false
FORCE=false
STRICT_IMAGE_CHECK=false
KAFKA_ENDPOINT=""
MONGODB_ENDPOINT=""
REDIS_ENDPOINT=""
TEMPORAL_ENDPOINT=""
POSTGRES_ENDPOINT=""
OTEL_ENDPOINT=""
DUMMY_IMAGES=false

# Função de ajuda
show_help() {
    echo "Uso: $0 [opções]"
    echo
    echo "Prepara os arquivos values-local-generated.yaml para o Fluxo C (Consensus Engine + Orchestrator Dynamic)."
    echo
    echo "Opções:"
    echo "  --dry-run              Executa apenas validações sem gerar arquivos"
    echo "  --force                Sobrescreve arquivos existentes sem perguntar"
    echo "  --strict-image-check   Falha se as imagens Docker não estiverem presentes no containerd"
    echo "  --dummy-images         Usa imagem nginx:alpine para simular deployment (útil se imagens reais não existirem)"
    echo "  --kafka-endpoint       Override manual do endpoint Kafka"
    echo "  --mongodb-endpoint     Override manual do endpoint MongoDB"
    echo "  --redis-endpoint       Override manual do endpoint Redis"
    echo "  --temporal-endpoint    Override manual do endpoint Temporal"
    echo "  --postgres-endpoint    Override manual do endpoint Postgres"
    echo "  --otel-endpoint        Override manual do endpoint OpenTelemetry"
    echo "  -h, --help             Mostra esta ajuda"
}

# Parse de argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        --force) FORCE=true; shift ;;
        --strict-image-check) STRICT_IMAGE_CHECK=true; shift ;;
        --dummy-images) DUMMY_IMAGES=true; shift ;;
        --kafka-endpoint) KAFKA_ENDPOINT="$2"; shift 2 ;;
        --mongodb-endpoint) MONGODB_ENDPOINT="$2"; shift 2 ;;
        --redis-endpoint) REDIS_ENDPOINT="$2"; shift 2 ;;
        --temporal-endpoint) TEMPORAL_ENDPOINT="$2"; shift 2 ;;
        --postgres-endpoint) POSTGRES_ENDPOINT="$2"; shift 2 ;;
        --otel-endpoint) OTEL_ENDPOINT="$2"; shift 2 ;;
        -h|--help) show_help; exit 0 ;;
        *) echo -e "${RED}Opção desconhecida: $1${NC}"; show_help; exit 1 ;;
    esac
done

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Validação de Configuração Obrigatória
validate_config() {
    log_info "Validando campos obrigatórios da configuração..."
    
    local errors=0
    
    # Consensus Engine - campos obrigatórios
    local ce_repo=$(yq '.consensusEngine.image.repository' "$CONFIG_FILE")
    local ce_tag=$(yq '.consensusEngine.image.tag' "$CONFIG_FILE")
    local ce_replicas=$(yq '.consensusEngine.replicas' "$CONFIG_FILE")
    local ce_cpu_req=$(yq '.consensusEngine.resources.requests.cpu' "$CONFIG_FILE")
    local ce_mem_req=$(yq '.consensusEngine.resources.requests.memory' "$CONFIG_FILE")
    
    if [[ -z "$ce_repo" || "$ce_repo" == "null" ]]; then
        log_error "Campo obrigatório ausente: consensusEngine.image.repository"
        ((errors++))
    fi
    
    if [[ -z "$ce_tag" || "$ce_tag" == "null" ]]; then
        log_error "Campo obrigatório ausente: consensusEngine.image.tag"
        ((errors++))
    fi
    
    if [[ -z "$ce_replicas" || "$ce_replicas" == "null" || ! "$ce_replicas" =~ ^[0-9]+$ ]]; then
        log_error "Campo obrigatório inválido: consensusEngine.replicas"
        ((errors++))
    fi
    
    if [[ -z "$ce_cpu_req" || "$ce_cpu_req" == "null" ]]; then
        log_error "Campo obrigatório ausente: consensusEngine.resources.requests.cpu"
        ((errors++))
    fi
    
    if [[ -z "$ce_mem_req" || "$ce_mem_req" == "null" ]]; then
        log_error "Campo obrigatório ausente: consensusEngine.resources.requests.memory"
        ((errors++))
    fi
    
    # Orchestrator Dynamic - campos obrigatórios
    local od_repo=$(yq '.orchestratorDynamic.image.repository' "$CONFIG_FILE")
    local od_tag=$(yq '.orchestratorDynamic.image.tag' "$CONFIG_FILE")
    local od_replicas=$(yq '.orchestratorDynamic.replicas' "$CONFIG_FILE")
    local od_cpu_req=$(yq '.orchestratorDynamic.resources.requests.cpu' "$CONFIG_FILE")
    local od_mem_req=$(yq '.orchestratorDynamic.resources.requests.memory' "$CONFIG_FILE")
    
    if [[ -z "$od_repo" || "$od_repo" == "null" ]]; then
        log_error "Campo obrigatório ausente: orchestratorDynamic.image.repository"
        ((errors++))
    fi
    
    if [[ -z "$od_tag" || "$od_tag" == "null" ]]; then
        log_error "Campo obrigatório ausente: orchestratorDynamic.image.tag"
        ((errors++))
    fi
    
    if [[ -z "$od_replicas" || "$od_replicas" == "null" || ! "$od_replicas" =~ ^[0-9]+$ ]]; then
        log_error "Campo obrigatório inválido: orchestratorDynamic.replicas"
        ((errors++))
    fi
    
    if [[ -z "$od_cpu_req" || "$od_cpu_req" == "null" ]]; then
        log_error "Campo obrigatório ausente: orchestratorDynamic.resources.requests.cpu"
        ((errors++))
    fi
    
    if [[ -z "$od_mem_req" || "$od_mem_req" == "null" ]]; then
        log_error "Campo obrigatório ausente: orchestratorDynamic.resources.requests.memory"
        ((errors++))
    fi
    
    if [[ $errors -gt 0 ]]; then
        log_error "Validação falhou com $errors erro(s). Corrija o arquivo $CONFIG_FILE"
        exit 1
    fi
    
    log_success "Todos os campos obrigatórios estão presentes e válidos."
}

# Cálculo e exibição do resumo de recursos
show_resource_summary() {
    log_info "Calculando footprint de recursos do Fluxo C..."
    
    local ce_cpu=$(yq '.consensusEngine.resources.requests.cpu' "$CONFIG_FILE")
    local ce_mem=$(yq '.consensusEngine.resources.requests.memory' "$CONFIG_FILE")
    local ce_replicas=$(yq '.consensusEngine.replicas' "$CONFIG_FILE")
    
    local od_cpu=$(yq '.orchestratorDynamic.resources.requests.cpu' "$CONFIG_FILE")
    local od_mem=$(yq '.orchestratorDynamic.resources.requests.memory' "$CONFIG_FILE")
    local od_replicas=$(yq '.orchestratorDynamic.replicas' "$CONFIG_FILE")
    
    echo
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Resumo de Recursos - Fluxo C${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
    echo -e "${GREEN}Consensus Engine:${NC}"
    echo "  Réplicas: $ce_replicas"
    echo "  CPU Request: $ce_cpu (por réplica)"
    echo "  Memory Request: $ce_mem (por réplica)"
    echo
    echo -e "${GREEN}Orchestrator Dynamic:${NC}"
    echo "  Réplicas: $od_replicas"
    echo "  CPU Request: $od_cpu (por réplica)"
    echo "  Memory Request: $od_mem (por réplica)"
    echo
    echo -e "${YELLOW}Total Estimado (Requests):${NC}"
    echo "  CPU: ${ce_cpu} × ${ce_replicas} + ${od_cpu} × ${od_replicas}"
    echo "  Memory: ${ce_mem} × ${ce_replicas} + ${od_mem} × ${od_replicas}"
    echo -e "${BLUE}========================================${NC}"
    echo
}

# Validações Iniciais
check_prerequisites() {
    log_info "Verificando pré-requisitos..."
    
    if ! command -v yq &> /dev/null; then
        log_error "yq (v4) não encontrado. Instale com: snap install yq"
        exit 1
    fi
    
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado."
        exit 1
    fi

    if [[ ! -f "$CONFIG_FILE" ]]; then
        log_error "Arquivo de configuração não encontrado: $CONFIG_FILE"
        exit 1
    fi

    if [[ ! -d "$CONSENSUS_CHART_DIR" ]]; then
        log_error "Diretório do chart Consensus Engine não encontrado: $CONSENSUS_CHART_DIR"
        exit 1
    fi

    if [[ ! -d "$ORCHESTRATOR_CHART_DIR" ]]; then
        log_error "Diretório do chart Orchestrator Dynamic não encontrado: $ORCHESTRATOR_CHART_DIR"
        exit 1
    fi

    log_success "Pré-requisitos atendidos."
}

# Detecção de Serviços
detect_service_endpoint() {
    local service_name=$1
    local namespace=$2
    local port=$3
    local override_var=$4
    local fallback=$5

    if [[ -n "$override_var" ]]; then
        echo "$override_var"
        return
    fi

    if kubectl get svc "$service_name" -n "$namespace" &> /dev/null; then
        echo "${service_name}.${namespace}.svc.cluster.local:${port}"
    else
        if [[ -n "$fallback" ]]; then
            echo "$fallback"
        else
            echo "detect-failed"
        fi
    fi
}

detect_endpoints() {
    log_info "Detectando endpoints dos serviços..."

    # Kafka
    KAFKA_DETECTED=$(detect_service_endpoint "neural-hive-kafka-kafka-bootstrap" "kafka" "9092" "$KAFKA_ENDPOINT" "")
    if [[ "$KAFKA_DETECTED" == "detect-failed" ]]; then
        log_error "Kafka não detectado no namespace kafka."
        exit 1
    fi
    log_info "Kafka: $KAFKA_DETECTED"

    # MongoDB
    MONGODB_DETECTED=$(detect_service_endpoint "mongodb-headless" "mongodb-cluster" "27017" "$MONGODB_ENDPOINT" "")
    if [[ "$MONGODB_DETECTED" == "detect-failed" ]]; then
        # Tenta nome alternativo comum
        MONGODB_DETECTED=$(detect_service_endpoint "mongodb" "mongodb-cluster" "27017" "$MONGODB_ENDPOINT" "")
    fi
    if [[ "$MONGODB_DETECTED" == "detect-failed" ]]; then
        log_error "MongoDB não detectado no namespace mongodb-cluster."
        exit 1
    fi
    # Ajuste para connection string
    MONGODB_URI="mongodb://${MONGODB_DETECTED}"
    log_info "MongoDB: $MONGODB_URI"

    # Redis
    REDIS_DETECTED=$(detect_service_endpoint "neural-hive-cache-headless" "redis-cluster" "6379" "$REDIS_ENDPOINT" "")
    if [[ "$REDIS_DETECTED" == "detect-failed" ]]; then
         REDIS_DETECTED=$(detect_service_endpoint "neural-hive-cache-master" "redis-cluster" "6379" "$REDIS_ENDPOINT" "")
    fi
    if [[ "$REDIS_DETECTED" == "detect-failed" ]]; then
        log_error "Redis não detectado no namespace redis-cluster."
        exit 1
    fi
    log_info "Redis: $REDIS_DETECTED"

    # OpenTelemetry
    OTEL_DETECTED=$(detect_service_endpoint "opentelemetry-collector" "observability" "4317" "$OTEL_ENDPOINT" "")
    if [[ "$OTEL_DETECTED" == "detect-failed" ]]; then
        log_warn "OpenTelemetry não detectado. Usando localhost (sem coleta)."
        OTEL_DETECTED="localhost:4317"
    fi
    log_info "OpenTelemetry: $OTEL_DETECTED"

    # Temporal (Opcional)
    TEMPORAL_DETECTED=$(detect_service_endpoint "temporal-frontend" "temporal" "7233" "$TEMPORAL_ENDPOINT" "temporal-frontend.temporal.svc.cluster.local:7233")
    log_info "Temporal: $TEMPORAL_DETECTED"

    # Postgres (Opcional - usado pelo Temporal)
    POSTGRES_DETECTED=$(detect_service_endpoint "temporal-postgresql" "temporal" "5432" "$POSTGRES_ENDPOINT" "temporal-postgresql.temporal.svc.cluster.local:5432")
    log_info "Postgres: $POSTGRES_DETECTED"
}

# Validação de Imagens
validate_images() {
    if [[ "$DUMMY_IMAGES" == "true" ]]; then
        log_warn "Modo Dummy Images ativado. Usando nginx:alpine."
        return
    fi

    log_info "Validando imagens Docker..."
    
    local ce_image=$(yq '.consensusEngine.image.repository + ":" + .consensusEngine.image.tag' "$CONFIG_FILE")
    local od_image=$(yq '.orchestratorDynamic.image.repository + ":" + .orchestratorDynamic.image.tag' "$CONFIG_FILE")
    
    local missing=false

    if ! sudo ctr -n k8s.io images ls | grep -q "$ce_image"; then
        log_warn "Imagem $ce_image não encontrada no containerd."
        missing=true
    else
        log_success "Imagem $ce_image encontrada."
    fi

    if ! sudo ctr -n k8s.io images ls | grep -q "$od_image"; then
        log_warn "Imagem $od_image não encontrada no containerd."
        missing=true
    else
        log_success "Imagem $od_image encontrada."
    fi

    if [[ "$missing" == "true" && "$STRICT_IMAGE_CHECK" == "true" ]]; then
        log_error "Imagens obrigatórias ausentes. Use --strict-image-check=false para ignorar ou importe com 'sudo ctr -n k8s.io images import ...'"
        exit 1
    fi
}

# Geração de Valores
generate_values() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "Modo Dry-Run: Pulando geração de arquivos."
        return
    fi

    if [[ -f "$OUTPUT_FILE_CONSENSUS" && "$FORCE" == "false" ]]; then
        log_error "Arquivo $OUTPUT_FILE_CONSENSUS já existe. Use --force para sobrescrever."
        exit 1
    fi
    
    if [[ -f "$OUTPUT_FILE_ORCHESTRATOR" && "$FORCE" == "false" ]]; then
        log_error "Arquivo $OUTPUT_FILE_ORCHESTRATOR já existe. Use --force para sobrescrever."
        exit 1
    fi

    log_info "Gerando values para Consensus Engine..."
    
    local ce_repo=$(yq '.consensusEngine.image.repository' "$CONFIG_FILE")
    local ce_tag=$(yq '.consensusEngine.image.tag' "$CONFIG_FILE")
    local ce_pull=$(yq '.consensusEngine.image.pullPolicy' "$CONFIG_FILE")

    if [[ "$DUMMY_IMAGES" == "true" ]]; then
        ce_repo="python"
        ce_tag="3.9-slim"
        ce_pull="IfNotPresent"
    fi

    # Consensus Engine Values
    cat <<EOF > "$OUTPUT_FILE_CONSENSUS"
# Gerado automaticamente por $(basename "$0") em $(date)
# Baseado em environments/local/fluxo-c-config.yaml

image:
  repository: $ce_repo
  tag: "$ce_tag"
  pullPolicy: $ce_pull

replicaCount: $(yq '.consensusEngine.replicas' "$CONFIG_FILE")

resources:
  requests:
    cpu: "$(yq '.consensusEngine.resources.requests.cpu' "$CONFIG_FILE")"
    memory: "$(yq '.consensusEngine.resources.requests.memory' "$CONFIG_FILE")"
  limits:
    cpu: "$(yq '.consensusEngine.resources.limits.cpu' "$CONFIG_FILE")"
    memory: "$(yq '.consensusEngine.resources.limits.memory' "$CONFIG_FILE")"

EOF

    if [[ "$DUMMY_IMAGES" == "true" ]]; then
        cat <<EOF >> "$OUTPUT_FILE_CONSENSUS"
customCommand:
  enabled: true
  command: ["/bin/sh", "-c"]
  args: ["cd /tmp && echo 'OK' > health && echo 'OK' > ready && python3 -m http.server 8000"]

livenessProbe:
  httpGet:
    path: /health
    port: 8000

readinessProbe:
  httpGet:
    path: /ready
    port: 8000
EOF
    else
        cat <<EOF >> "$OUTPUT_FILE_CONSENSUS"
customCommand:
  enabled: false
EOF
    fi

    cat <<EOF >> "$OUTPUT_FILE_CONSENSUS"

config:
  environment: "$(yq '.consensusEngine.config.environment' "$CONFIG_FILE")"
  logLevel: "$(yq '.consensusEngine.config.logLevel' "$CONFIG_FILE")"
  
  kafka:
    bootstrapServers: "$KAFKA_DETECTED"
    consumerGroupId: "$(yq '.consensusEngine.config.kafka.consumerGroupId' "$CONFIG_FILE")"
    plansTopicConsume: "$(yq '.consensusEngine.config.kafka.plansTopicConsume' "$CONFIG_FILE")"
    consensusTopicProduce: "$(yq '.consensusEngine.config.kafka.consensusTopicProduce' "$CONFIG_FILE")"
    securityProtocol: "$(yq '.consensusEngine.config.kafka.securityProtocol' "$CONFIG_FILE")"
    sasl:
      enabled: false

  specialists:
    businessEndpoint: "$(yq '.consensusEngine.config.specialists.businessEndpoint' "$CONFIG_FILE")"
    technicalEndpoint: "$(yq '.consensusEngine.config.specialists.technicalEndpoint' "$CONFIG_FILE")"
    behaviorEndpoint: "$(yq '.consensusEngine.config.specialists.behaviorEndpoint' "$CONFIG_FILE")"
    evolutionEndpoint: "$(yq '.consensusEngine.config.specialists.evolutionEndpoint' "$CONFIG_FILE")"
    architectureEndpoint: "$(yq '.consensusEngine.config.specialists.architectureEndpoint' "$CONFIG_FILE")"
    # Timeout increased to 120000ms (120 seconds) to accommodate specialist processing time of 49-66 seconds for ML inference
    grpcTimeoutMs: $(yq '.consensusEngine.config.specialists.grpcTimeoutMs' "$CONFIG_FILE")
    grpcMaxRetries: $(yq '.consensusEngine.config.specialists.grpcMaxRetries' "$CONFIG_FILE")

  mongodb:
    uri: "$MONGODB_URI"
    database: "$(yq '.consensusEngine.config.mongodb.database' "$CONFIG_FILE")"
    consensusCollection: "$(yq '.consensusEngine.config.mongodb.consensusCollection' "$CONFIG_FILE")"

  redis:
    clusterNodes: "$REDIS_DETECTED"
    sslEnabled: $(yq '.consensusEngine.config.redis.sslEnabled' "$CONFIG_FILE")
    pheromoneTtl: $(yq '.consensusEngine.config.redis.pheromoneTtl' "$CONFIG_FILE")
    pheromoneDecayRate: $(yq '.consensusEngine.config.redis.pheromoneDecayRate' "$CONFIG_FILE")

  openTelemetry:
    endpoint: "$OTEL_DETECTED"
    samplingRate: $(yq '.consensusEngine.config.openTelemetry.samplingRate' "$CONFIG_FILE")

  consensus:
    minConfidenceScore: $(yq '.consensusEngine.config.consensus.minConfidenceScore' "$CONFIG_FILE")
    maxDivergenceThreshold: $(yq '.consensusEngine.config.consensus.maxDivergenceThreshold' "$CONFIG_FILE")
    features:
      enableBayesianAveraging: $(yq '.consensusEngine.config.features.enableBayesianAveraging' "$CONFIG_FILE")
      enablePheromones: $(yq '.consensusEngine.config.features.enablePheromones' "$CONFIG_FILE")

serviceMonitor:
  enabled: $(yq '.consensusEngine.observability.serviceMonitor.enabled' "$CONFIG_FILE")
  interval: "$(yq '.consensusEngine.observability.serviceMonitor.interval' "$CONFIG_FILE")"

security:
  istio:
    enabled: $(yq '.consensusEngine.security.istio.enabled' "$CONFIG_FILE")
EOF

    log_success "Arquivo gerado: $OUTPUT_FILE_CONSENSUS"

    log_info "Gerando values para Orchestrator Dynamic..."

    local od_repo=$(yq '.orchestratorDynamic.image.repository' "$CONFIG_FILE")
    local od_tag=$(yq '.orchestratorDynamic.image.tag' "$CONFIG_FILE")
    local od_pull=$(yq '.orchestratorDynamic.image.pullPolicy' "$CONFIG_FILE")

    if [[ "$DUMMY_IMAGES" == "true" ]]; then
        od_repo="python"
        od_tag="3.9-slim"
        od_pull="IfNotPresent"
    fi

    # Orchestrator Dynamic Values
    cat <<EOF > "$OUTPUT_FILE_ORCHESTRATOR"
# Gerado automaticamente por $(basename "$0") em $(date)
# Baseado em environments/local/fluxo-c-config.yaml

image:
  repository: $od_repo
  tag: "$od_tag"
  pullPolicy: $od_pull

replicaCount: $(yq '.orchestratorDynamic.replicas' "$CONFIG_FILE")

resources:
  requests:
    cpu: "$(yq '.orchestratorDynamic.resources.requests.cpu' "$CONFIG_FILE")"
    memory: "$(yq '.orchestratorDynamic.resources.requests.memory' "$CONFIG_FILE")"
  limits:
    cpu: "$(yq '.orchestratorDynamic.resources.limits.cpu' "$CONFIG_FILE")"
    memory: "$(yq '.orchestratorDynamic.resources.limits.memory' "$CONFIG_FILE")"

EOF

    if [[ "$DUMMY_IMAGES" == "true" ]]; then
        cat <<EOF >> "$OUTPUT_FILE_ORCHESTRATOR"
customCommand:
  enabled: true
  command: ["/bin/sh", "-c"]
  args: ["cd /tmp && echo 'OK' > health && echo 'OK' > ready && python3 -m http.server 8000"]

livenessProbe:
  httpGet:
    path: /health
    port: 8000

readinessProbe:
  httpGet:
    path: /ready
    port: 8000
EOF
    else
        cat <<EOF >> "$OUTPUT_FILE_ORCHESTRATOR"
customCommand:
  enabled: false
EOF
    fi

    cat <<EOF >> "$OUTPUT_FILE_ORCHESTRATOR"

config:
  environment: "$(yq '.orchestratorDynamic.config.environment' "$CONFIG_FILE")"
  logLevel: "$(yq '.orchestratorDynamic.config.logLevel' "$CONFIG_FILE")"

  temporal:
    host: "$TEMPORAL_DETECTED"
    namespace: "$(yq '.orchestratorDynamic.config.temporal.namespace' "$CONFIG_FILE")"
    tlsEnabled: $(yq '.orchestratorDynamic.config.temporal.tlsEnabled' "$CONFIG_FILE")

  postgres:
    host: "$POSTGRES_DETECTED"
    database: "$(yq '.orchestratorDynamic.config.postgres.database' "$CONFIG_FILE")"
    sslMode: "$(yq '.orchestratorDynamic.config.postgres.sslMode' "$CONFIG_FILE")"

  kafka:
    bootstrapServers: "$KAFKA_DETECTED"
    consensusTopic: "$(yq '.orchestratorDynamic.config.kafka.consensusTopic' "$CONFIG_FILE")"
    ticketsTopic: "$(yq '.orchestratorDynamic.config.kafka.ticketsTopic' "$CONFIG_FILE")"
    consumerGroupId: "$(yq '.orchestratorDynamic.config.kafka.consumerGroupId' "$CONFIG_FILE")"
    securityProtocol: "$(yq '.orchestratorDynamic.config.kafka.securityProtocol' "$CONFIG_FILE")"
    sasl:
      enabled: false

  mongodb:
    uri: "$MONGODB_URI"
    database: "$(yq '.orchestratorDynamic.config.mongodb.database' "$CONFIG_FILE")"

  redis:
    clusterNodes: "$REDIS_DETECTED"
    sslEnabled: $(yq '.orchestratorDynamic.config.redis.sslEnabled' "$CONFIG_FILE")

  openTelemetry:
    endpoint: "$OTEL_DETECTED"

  scheduler:
    enableIntelligentScheduler: $(yq '.orchestratorDynamic.config.scheduler.enableIntelligentScheduler' "$CONFIG_FILE")
    maxParallelTickets: $(yq '.orchestratorDynamic.config.scheduler.maxParallelTickets' "$CONFIG_FILE")

  sla:
    defaultTimeoutMs: $(yq '.orchestratorDynamic.config.sla.defaultTimeoutMs' "$CONFIG_FILE")

  ml:
    trainingJob:
      enabled: false
    drift:
      enabled: false
  
  spiffe:
    enabled: false
  
  vault:
    enabled: false

serviceMonitor:
  enabled: $(yq '.orchestratorDynamic.observability.serviceMonitor.enabled' "$CONFIG_FILE")

security:
  istio:
    enabled: $(yq '.orchestratorDynamic.security.istio.enabled' "$CONFIG_FILE")
EOF

    log_success "Arquivo gerado: $OUTPUT_FILE_ORCHESTRATOR"
}

# Execução Principal
check_prerequisites
validate_config
detect_endpoints
validate_images
generate_values
show_resource_summary

log_success "Preparação concluída com sucesso!"
echo -e "${BLUE}Próximo passo:${NC} Execute o script de validação após o deployment."
