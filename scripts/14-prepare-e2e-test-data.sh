#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Script: 14-prepare-e2e-test-data.sh
# Descrição: Prepara dados de teste E2E para validação do Neural Hive-Mind
# Uso: ./14-prepare-e2e-test-data.sh [opções]
# ==============================================================================

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variáveis padrão
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/neural-hive-e2e-data}"
NAMESPACE_GATEWAY="${NAMESPACE_GATEWAY:-gateway-intencoes}"
NAMESPACE_KAFKA="${NAMESPACE_KAFKA:-kafka}"
NAMESPACE_MONGODB="${NAMESPACE_MONGODB:-mongodb}"
NAMESPACE_REDIS="${NAMESPACE_REDIS:-redis}"
NUM_PAYLOADS="${NUM_PAYLOADS:-3}"
VERBOSE="${VERBOSE:-false}"

# ==============================================================================
# Funções de Utilidade
# ==============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_usage() {
    cat << EOF
Uso: $0 [opções]

Opções:
  --output-dir DIR          Diretório para salvar payloads (padrão: /tmp/neural-hive-e2e-data)
  --num-payloads N          Número de payloads a gerar (padrão: 3)
  --namespace-gateway NS    Namespace do Gateway (padrão: gateway-intencoes)
  --namespace-kafka NS      Namespace do Kafka (padrão: kafka)
  --namespace-mongodb NS    Namespace do MongoDB (padrão: mongodb)
  --namespace-redis NS      Namespace do Redis (padrão: redis)
  --verbose                 Modo verboso
  -h, --help                Mostra esta mensagem

Exemplos:
  $0
  $0 --output-dir ./test-data --num-payloads 5
  $0 --verbose

EOF
}

# ==============================================================================
# Parse de Argumentos
# ==============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --num-payloads)
            NUM_PAYLOADS="$2"
            shift 2
            ;;
        --namespace-gateway)
            NAMESPACE_GATEWAY="$2"
            shift 2
            ;;
        --namespace-kafka)
            NAMESPACE_KAFKA="$2"
            shift 2
            ;;
        --namespace-mongodb)
            NAMESPACE_MONGODB="$2"
            shift 2
            ;;
        --namespace-redis)
            NAMESPACE_REDIS="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            log_error "Opção desconhecida: $1"
            show_usage
            exit 1
            ;;
    esac
done

# ==============================================================================
# Validação de Pré-requisitos
# ==============================================================================

log_info "Validando pré-requisitos..."

# Verificar ferramentas necessárias
REQUIRED_TOOLS=("kubectl" "curl" "jq" "mongosh" "redis-cli")
MISSING_TOOLS=()

for tool in "${REQUIRED_TOOLS[@]}"; do
    if ! command -v "$tool" &> /dev/null; then
        MISSING_TOOLS+=("$tool")
    fi
done

if [ ${#MISSING_TOOLS[@]} -gt 0 ]; then
    log_error "Ferramentas faltando: ${MISSING_TOOLS[*]}"
    log_info "Instale as ferramentas necessárias antes de continuar."
    exit 1
fi

log_success "Todas as ferramentas necessárias estão instaladas"

# Verificar conectividade com cluster Kubernetes
if ! kubectl cluster-info &> /dev/null; then
    log_error "Não foi possível conectar ao cluster Kubernetes"
    exit 1
fi

log_success "Conectado ao cluster Kubernetes"

# ==============================================================================
# Detectar Pods e Namespaces
# ==============================================================================

log_info "Detectando pods nos namespaces..."

# Gateway
GATEWAY_POD=$(kubectl get pod -n "$NAMESPACE_GATEWAY" -l app=gateway-intencoes -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -z "$GATEWAY_POD" ]; then
    log_error "Pod do Gateway não encontrado no namespace $NAMESPACE_GATEWAY"
    exit 1
fi
log_success "Gateway pod: $GATEWAY_POD"

# Kafka
KAFKA_POD=$(kubectl get pod -n "$NAMESPACE_KAFKA" -l app=kafka -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -z "$KAFKA_POD" ]; then
    log_error "Pod do Kafka não encontrado no namespace $NAMESPACE_KAFKA"
    exit 1
fi
log_success "Kafka pod: $KAFKA_POD"

# MongoDB
MONGODB_POD=$(kubectl get pod -n "$NAMESPACE_MONGODB" -l app=mongodb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -z "$MONGODB_POD" ]; then
    log_error "Pod do MongoDB não encontrado no namespace $NAMESPACE_MONGODB"
    exit 1
fi
log_success "MongoDB pod: $MONGODB_POD"

# Redis
REDIS_POD=$(kubectl get pod -n "$NAMESPACE_REDIS" -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -z "$REDIS_POD" ]; then
    log_error "Pod do Redis não encontrado no namespace $NAMESPACE_REDIS"
    exit 1
fi
log_success "Redis pod: $REDIS_POD"

# ==============================================================================
# Criar Diretório de Output
# ==============================================================================

log_info "Criando diretório de output: $OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# ==============================================================================
# Gerar Payloads de Teste
# ==============================================================================

log_info "Gerando $NUM_PAYLOADS payloads de teste..."

# Templates de intenções
declare -a INTENT_TEMPLATES=(
    "Analisar viabilidade técnica de implementar autenticação biométrica no aplicativo móvel"
    "Criar dashboard de métricas em tempo real para monitoramento de performance"
    "Implementar sistema de cache distribuído para melhorar latência de consultas"
    "Desenvolver API REST para integração com sistemas legados"
    "Migrar banco de dados relacional para arquitetura NoSQL"
)

for i in $(seq 1 "$NUM_PAYLOADS"); do
    # Selecionar template aleatório
    TEMPLATE_INDEX=$(( (i - 1) % ${#INTENT_TEMPLATES[@]} ))
    INTENT_TEXT="${INTENT_TEMPLATES[$TEMPLATE_INDEX]}"
    
    # Gerar correlation_id único
    CORRELATION_ID="test-e2e-$(date +%Y%m%d)-$(printf "%03d" "$i")"
    
    # Gerar payload JSON
    PAYLOAD_FILE="$OUTPUT_DIR/intent-payload-${i}.json"
    
    cat > "$PAYLOAD_FILE" << EOF
{
  "text": "$INTENT_TEXT",
  "language": "pt-BR",
  "correlation_id": "$CORRELATION_ID",
  "context": {
    "user_id": "test-user-$i",
    "session_id": "test-session-$(date +%s)-$i",
    "channel": "API",
    "environment": "e2e-testing"
  },
  # IMPORTANTE: Enums devem ser lowercase (high, normal, low, critical)
  "constraints": {
    "priority": "high",
    "timeout_ms": 30000,
    "max_specialists": 5
  },
  "metadata": {
    "test_run": "e2e-validation",
    "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "payload_number": $i
  }
}
EOF
    
    log_success "Payload $i gerado: $PAYLOAD_FILE"
    
    if [ "$VERBOSE" = true ]; then
        cat "$PAYLOAD_FILE" | jq '.'
    fi
done

# ==============================================================================
# Gerar Script de Envio
# ==============================================================================

log_info "Gerando script de envio de payloads..."

SEND_SCRIPT="$OUTPUT_DIR/send-payloads.sh"

cat > "$SEND_SCRIPT" << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATEWAY_POD="$1"
NAMESPACE_GATEWAY="${2:-gateway-intencoes}"

if [ -z "$GATEWAY_POD" ]; then
    echo "Uso: $0 <gateway-pod> [namespace]"
    exit 1
fi

echo "Enviando payloads para Gateway pod: $GATEWAY_POD"

for payload in "$SCRIPT_DIR"/intent-payload-*.json; do
    echo "Enviando: $(basename "$payload")"
    
    # Copiar payload para pod
    kubectl cp "$payload" "$NAMESPACE_GATEWAY/$GATEWAY_POD:/tmp/$(basename "$payload")"
    
    # Enviar via curl
    RESPONSE=$(kubectl exec -n "$NAMESPACE_GATEWAY" "$GATEWAY_POD" -- \
        curl -s -X POST http://localhost:8000/intentions \
        -H 'Content-Type: application/json' \
        -d @"/tmp/$(basename "$payload")")
    
    echo "Response: $RESPONSE" | jq '.'
    echo "---"
    
    # Aguardar 2 segundos entre envios
    sleep 2
done

echo "Todos os payloads foram enviados!"
EOF

chmod +x "$SEND_SCRIPT"
log_success "Script de envio criado: $SEND_SCRIPT"

# ==============================================================================
# Gerar Arquivo de Configuração de Ambiente
# ==============================================================================

log_info "Gerando arquivo de configuração de ambiente..."

ENV_FILE="$OUTPUT_DIR/e2e-env.sh"

cat > "$ENV_FILE" << EOF
#!/usr/bin/env bash
# Configuração de ambiente para testes E2E
# Source este arquivo: source $ENV_FILE

export NAMESPACE_GATEWAY="$NAMESPACE_GATEWAY"
export NAMESPACE_KAFKA="$NAMESPACE_KAFKA"
export NAMESPACE_MONGODB="$NAMESPACE_MONGODB"
export NAMESPACE_REDIS="$NAMESPACE_REDIS"

export GATEWAY_POD="$GATEWAY_POD"
export KAFKA_POD="$KAFKA_POD"
export MONGODB_POD="$MONGODB_POD"
export REDIS_POD="$REDIS_POD"

export OUTPUT_DIR="$OUTPUT_DIR"

echo "Ambiente E2E configurado:"
echo "  Gateway Pod: \$GATEWAY_POD"
echo "  Kafka Pod: \$KAFKA_POD"
echo "  MongoDB Pod: \$MONGODB_POD"
echo "  Redis Pod: \$REDIS_POD"
EOF

chmod +x "$ENV_FILE"
log_success "Arquivo de ambiente criado: $ENV_FILE"

# ==============================================================================
# Gerar README
# ==============================================================================

log_info "Gerando README..."

README_FILE="$OUTPUT_DIR/README.md"

cat > "$README_FILE" << EOF
# Dados de Teste E2E - Neural Hive-Mind

Gerado em: $(date -u +%Y-%m-%dT%H:%M:%SZ)

## Conteúdo

- **Payloads de intenção**: \`intent-payload-*.json\` ($NUM_PAYLOADS arquivos)
- **Script de envio**: \`send-payloads.sh\`
- **Configuração de ambiente**: \`e2e-env.sh\`

## Uso

### 1. Configurar ambiente

\`\`\`bash
source $ENV_FILE
\`\`\`

### 2. Enviar payloads

\`\`\`bash
$SEND_SCRIPT \$GATEWAY_POD \$NAMESPACE_GATEWAY
\`\`\`

### 3. Validar resultados

Consulte o guia de validação E2E:
- \`docs/manual-deployment/08-e2e-testing-manual-guide.md\`
- \`docs/manual-deployment/E2E_TESTING_CHECKLIST.md\`

## Pods Detectados

- Gateway: \`$GATEWAY_POD\`
- Kafka: \`$KAFKA_POD\`
- MongoDB: \`$MONGODB_POD\`
- Redis: \`$REDIS_POD\`

## Payloads Gerados

EOF

for i in $(seq 1 "$NUM_PAYLOADS"); do
    PAYLOAD_FILE="$OUTPUT_DIR/intent-payload-${i}.json"
    CORRELATION_ID=$(jq -r '.correlation_id' "$PAYLOAD_FILE")
    INTENT_TEXT=$(jq -r '.text' "$PAYLOAD_FILE")
    
    cat >> "$README_FILE" << EOF
### Payload $i
- **Arquivo**: \`intent-payload-${i}.json\`
- **Correlation ID**: \`$CORRELATION_ID\`
- **Intenção**: "$INTENT_TEXT"

EOF
done

log_success "README criado: $README_FILE"

# ==============================================================================
# Resumo Final
# ==============================================================================

echo ""
log_success "=========================================="
log_success "Preparação de dados E2E concluída!"
log_success "=========================================="
echo ""
log_info "Diretório de output: $OUTPUT_DIR"
log_info "Payloads gerados: $NUM_PAYLOADS"
echo ""
log_info "Próximos passos:"
echo "  1. source $ENV_FILE"
echo "  2. $SEND_SCRIPT \$GATEWAY_POD"
echo "  3. Validar resultados usando E2E_TESTING_CHECKLIST.md"
echo ""
