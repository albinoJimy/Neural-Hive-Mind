#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
################################################################################
# Script: execute-e2e-validation-v1.0.9.sh
# Propósito: Executar validação E2E completa do pipeline Neural Hive-Mind v1.0.9
# Autor: Neural Hive-Mind Team
# Versão: 1.0.0
# Data: 2025-11-10
################################################################################

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variáveis de configuração
NAMESPACE_GATEWAY="${NAMESPACE_GATEWAY:-gateway-intencoes}"
NAMESPACE_SEMANTIC="${NAMESPACE_SEMANTIC:-semantic-translation-engine}"
NAMESPACE_CONSENSUS="${NAMESPACE_CONSENSUS:-default}"
NAMESPACE_SPECIALISTS="${NAMESPACE_SPECIALISTS:-neural-hive}"
NAMESPACE_MEMORY="${NAMESPACE_MEMORY:-memory-layer-api}"

VALIDATION_ID="e2e-v1.0.9-$(date +%s)"
CORRELATION_ID="validation-v1.0.9-$(date +%s)"
OUTPUT_DIR="logs/validation-e2e-v1.0.9-$(date +%Y%m%d-%H%M%S)"

# Contadores
TOTAL_STEPS=8
PASSED_STEPS=0
FAILED_STEPS=0
PARTIAL_STEPS=0

################################################################################
# Função: kubectl_curl
# Propósito: Executar curl dentro do cluster usando pod temporário
################################################################################
kubectl_curl() {
    local url="$1"
    local method="${2:-GET}"
    local data="${3:-}"
    local headers="${4:-}"
    local namespace="${5:-default}"
    local pod_name="curl-validation-$(date +%s)-$$"

    local curl_cmd="curl -s -X $method"

    if [[ -n "$headers" ]]; then
        curl_cmd="$curl_cmd $headers"
    fi

    if [[ -n "$data" ]]; then
        curl_cmd="$curl_cmd -d '$data'"
    fi

    curl_cmd="$curl_cmd '$url'"

    kubectl run "$pod_name" \
        --rm -i --restart=Never \
        --image=curlimages/curl:latest \
        -n "$namespace" \
        --timeout=30s \
        -- sh -c "$curl_cmd" 2>/dev/null || echo "{\"error\": \"curl failed\"}"
}

################################################################################
# Função: log
# Propósito: Logar mensagens com timestamp e cor
################################################################################
log() {
    local level=$1
    shift
    local message=$@
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case $level in
        INFO)
            echo -e "${BLUE}[${timestamp}] [INFO]${NC} ${message}"
            ;;
        SUCCESS)
            echo -e "${GREEN}[${timestamp}] [SUCCESS]${NC} ${message}"
            ;;
        WARN)
            echo -e "${YELLOW}[${timestamp}] [WARN]${NC} ${message}"
            ;;
        ERROR)
            echo -e "${RED}[${timestamp}] [ERROR]${NC} ${message}"
            ;;
        *)
            echo "[${timestamp}] ${message}"
            ;;
    esac

    echo "[${timestamp}] [${level}] ${message}" >> "$OUTPUT_DIR/validation.log"
}

################################################################################
# Função: check_prerequisites
# Propósito: Validar pré-requisitos para execução
################################################################################
check_prerequisites() {
    log INFO "Verificando pré-requisitos..."

    # Verificar kubectl
    if ! command -v kubectl &> /dev/null; then
        log ERROR "kubectl não encontrado. Instale kubectl para continuar."
        exit 1
    fi

    # Verificar jq
    if ! command -v jq &> /dev/null; then
        log ERROR "jq não encontrado. Instale jq para continuar."
        exit 1
    fi

    # Verificar curl
    if ! command -v curl &> /dev/null; then
        log ERROR "curl não encontrado. Instale curl para continuar."
        exit 1
    fi

    # Verificar bc (usado para cálculos numéricos)
    if ! command -v bc &> /dev/null; then
        log ERROR "bc não encontrado. Instale bc para continuar."
        log ERROR "Ubuntu/Debian: sudo apt-get install bc"
        log ERROR "RHEL/CentOS: sudo yum install bc"
        exit 1
    fi

    # Verificar conectividade com cluster
    if ! kubectl cluster-info &> /dev/null; then
        log ERROR "Não foi possível conectar ao cluster Kubernetes."
        exit 1
    fi

    log SUCCESS "Pré-requisitos validados com sucesso."
}

################################################################################
# Função: create_output_dir
# Propósito: Criar diretório de output para artefatos
################################################################################
create_output_dir() {
    log INFO "Criando diretório de output: $OUTPUT_DIR"
    mkdir -p "$OUTPUT_DIR"

    # Criar arquivo de log
    touch "$OUTPUT_DIR/validation.log"

    # Criar arquivo de correlation IDs
    cat > "$OUTPUT_DIR/correlation-ids.txt" <<EOF
# Correlation IDs - Validação E2E v1.0.9
# Data: $(date)
VALIDATION_ID=$VALIDATION_ID
CORRELATION_ID=$CORRELATION_ID
EOF

    log SUCCESS "Diretório de output criado: $OUTPUT_DIR"
}

################################################################################
# Função: detect_pods
# Propósito: Detectar pods necessários para validação
################################################################################
detect_pods() {
    log INFO "Detectando pods do sistema..."

    # Gateway
    GATEWAY_POD=$(kubectl get pods -n "$NAMESPACE_GATEWAY" -l app=gateway-intencoes -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [[ -z "$GATEWAY_POD" ]]; then
        log WARN "Pod do Gateway não encontrado em namespace $NAMESPACE_GATEWAY"
        # Tentar namespace alternativo
        NAMESPACE_GATEWAY="neural-hive"
        GATEWAY_POD=$(kubectl get pods -n "$NAMESPACE_GATEWAY" -l app=gateway-intencoes -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    fi

    # Semantic Translation
    STE_POD=$(kubectl get pods -n "$NAMESPACE_SEMANTIC" -l app=semantic-translation-engine -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [[ -z "$STE_POD" ]]; then
        log WARN "Pod do Semantic Translation não encontrado em namespace $NAMESPACE_SEMANTIC"
    fi

    # Consensus Engine - tentar múltiplos namespaces
    CE_PODS=$(kubectl get pods -n "$NAMESPACE_CONSENSUS" -l app=consensus-engine -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
    if [[ -z "$CE_PODS" ]]; then
        log WARN "Pods do Consensus Engine não encontrados em namespace $NAMESPACE_CONSENSUS, tentando consensus-engine..."
        NAMESPACE_CONSENSUS="consensus-engine"
        CE_PODS=$(kubectl get pods -n "$NAMESPACE_CONSENSUS" -l app=consensus-engine -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
    fi
    if [[ -z "$CE_PODS" ]]; then
        log WARN "Pods do Consensus Engine não encontrados em namespace consensus-engine, buscando em todos os namespaces..."
        CE_PODS=$(kubectl get pods -A -l app=consensus-engine -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
        if [[ -n "$CE_PODS" ]]; then
            NAMESPACE_CONSENSUS=$(kubectl get pods -A -l app=consensus-engine -o jsonpath='{.items[0].metadata.namespace}' 2>/dev/null || echo "default")
            log INFO "Consensus Engine encontrado em namespace: $NAMESPACE_CONSENSUS"
        fi
    fi

    # Specialists
    for specialist in business technical behavior evolution architecture; do
        POD=$(kubectl get pods -n "specialist-$specialist" -l "app=specialist-$specialist" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
        if [[ -z "$POD" ]]; then
            log WARN "Pod do specialist-$specialist não encontrado"
        else
            eval "SPECIALIST_${specialist^^}_POD=$POD"
        fi
    done

    # Memory Layer API
    ML_POD=$(kubectl get pods -n "$NAMESPACE_MEMORY" -l app=memory-layer-api -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [[ -z "$ML_POD" ]]; then
        log WARN "Pod do Memory Layer API não encontrado em namespace $NAMESPACE_MEMORY"
        # Tentar namespace alternativo
        NAMESPACE_MEMORY="neural-hive"
        ML_POD=$(kubectl get pods -n "$NAMESPACE_MEMORY" -l app=memory-layer-api -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    fi

    log SUCCESS "Detecção de pods concluída."
}

################################################################################
# PASSO 1: Gateway Health Check
################################################################################
step1_gateway_health() {
    log INFO "═══════════════════════════════════════════════════════════"
    log INFO "PASSO 1: Gateway Health Check"
    log INFO "═══════════════════════════════════════════════════════════"

    if [[ -z "$GATEWAY_POD" ]]; then
        log ERROR "[PASSO 1] Gateway pod não encontrado. FAIL"
        echo "[PASSO 1] Gateway Health: FAIL - Pod não encontrado" >> "$OUTPUT_DIR/validation.log"
        FAILED_STEPS=$((FAILED_STEPS + 1))
        return 1
    fi

    # Executar health check
    log INFO "Executando health check no gateway..."

    # Obter ClusterIP do serviço
    GATEWAY_SVC_IP=$(kubectl get svc -n "$NAMESPACE_GATEWAY" gateway-intencoes -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")

    if [[ -z "$GATEWAY_SVC_IP" ]]; then
        log WARN "ClusterIP do gateway não encontrado, tentando via pod..."
        # Fallback para exec dentro do pod
        kubectl exec -n "$NAMESPACE_GATEWAY" "$GATEWAY_POD" -- curl -s http://localhost:8000/health > "$OUTPUT_DIR/01-gateway-health.json" 2>/dev/null || {
            log ERROR "[PASSO 1] Health check falhou. FAIL"
            echo "[PASSO 1] Gateway Health: FAIL - Health check falhou" >> "$OUTPUT_DIR/validation.log"
            FAILED_STEPS=$((FAILED_STEPS + 1))
            return 1
        }
    else
        # Usar kubectl run curl
        kubectl_curl "http://${GATEWAY_SVC_IP}:8000/health" "GET" "" "" "$NAMESPACE_GATEWAY" > "$OUTPUT_DIR/01-gateway-health.json" || {
            log ERROR "[PASSO 1] Health check falhou. FAIL"
            echo "[PASSO 1] Gateway Health: FAIL - Health check falhou" >> "$OUTPUT_DIR/validation.log"
            FAILED_STEPS=$((FAILED_STEPS + 1))
            return 1
        }
    fi

    # Validar response
    STATUS=$(jq -r '.status // "unknown"' "$OUTPUT_DIR/01-gateway-health.json")

    if [[ "$STATUS" == "healthy" ]]; then
        log SUCCESS "[PASSO 1] Gateway Health: PASS"
        echo "[PASSO 1] Gateway Health: PASS" >> "$OUTPUT_DIR/validation.log"
        PASSED_STEPS=$((PASSED_STEPS + 1))
        return 0
    else
        log ERROR "[PASSO 1] Gateway status: $STATUS. FAIL"
        echo "[PASSO 1] Gateway Health: FAIL - Status: $STATUS" >> "$OUTPUT_DIR/validation.log"
        FAILED_STEPS=$((FAILED_STEPS + 1))
        return 1
    fi
}

################################################################################
# PASSO 2: Enviar Intent de Teste
################################################################################
step2_send_intent() {
    log INFO "═══════════════════════════════════════════════════════════"
    log INFO "PASSO 2: Enviar Intent de Teste"
    log INFO "═══════════════════════════════════════════════════════════"

    if [[ -z "$GATEWAY_POD" ]]; then
        log ERROR "[PASSO 2] Gateway pod não encontrado. FAIL"
        echo "[PASSO 2] Gateway Process: FAIL - Pod não encontrado" >> "$OUTPUT_DIR/validation.log"
        FAILED_STEPS=$((FAILED_STEPS + 1))
        return 1
    fi

    # Gerar payload de teste
    PAYLOAD=$(cat <<EOF
{
  "text": "Implementar autenticação multifator no sistema de acesso com verificação biométrica e tokens temporários",
  "language": "pt-BR",
  "correlation_id": "$CORRELATION_ID"
}
EOF
)

    log INFO "Enviando intent de teste..."
    log INFO "Payload: $PAYLOAD"

    # Enviar usando kubectl run curl ou fallback para exec
    if [[ -n "$GATEWAY_SVC_IP" ]]; then
        kubectl_curl "http://${GATEWAY_SVC_IP}:8000/intentions" "POST" "$PAYLOAD" "-H 'Content-Type: application/json'" "$NAMESPACE_GATEWAY" > "$OUTPUT_DIR/02-gateway-response.json" || {
            log ERROR "[PASSO 2] Envio de intent falhou. FAIL"
            echo "[PASSO 2] Gateway Process: FAIL - Envio falhou" >> "$OUTPUT_DIR/validation.log"
            FAILED_STEPS=$((FAILED_STEPS + 1))
            return 1
        }
    else
        kubectl exec -n "$NAMESPACE_GATEWAY" "$GATEWAY_POD" -- curl -s -X POST http://localhost:8000/intentions \
            -H "Content-Type: application/json" \
            -d "$PAYLOAD" > "$OUTPUT_DIR/02-gateway-response.json" 2>/dev/null || {
            log ERROR "[PASSO 2] Envio de intent falhou. FAIL"
            echo "[PASSO 2] Gateway Process: FAIL - Envio falhou" >> "$OUTPUT_DIR/validation.log"
            FAILED_STEPS=$((FAILED_STEPS + 1))
            return 1
        }
    fi

    # Extrair IDs críticos
    INTENT_ID=$(jq -r '.intent_id // empty' "$OUTPUT_DIR/02-gateway-response.json")
    DOMAIN=$(jq -r '.domain // empty' "$OUTPUT_DIR/02-gateway-response.json")
    CONFIDENCE=$(jq -r '.confidence // 0' "$OUTPUT_DIR/02-gateway-response.json")
    PROCESSING_TIME=$(jq -r '.processing_time_ms // 0' "$OUTPUT_DIR/02-gateway-response.json")

    # Salvar IDs de correlação
    cat >> "$OUTPUT_DIR/correlation-ids.txt" <<EOF

# Gateway Response
INTENT_ID=$INTENT_ID
DOMAIN=$DOMAIN
CONFIDENCE=$CONFIDENCE
PROCESSING_TIME_MS=$PROCESSING_TIME
EOF

    # Validar response
    if [[ -z "$INTENT_ID" ]]; then
        log ERROR "[PASSO 2] Intent ID não retornado. FAIL"
        echo "[PASSO 2] Gateway Process: FAIL - Intent ID ausente" >> "$OUTPUT_DIR/validation.log"
        FAILED_STEPS=$((FAILED_STEPS + 1))
        return 1
    fi

    if (( $(echo "$CONFIDENCE < 0.7" | bc -l) )); then
        log WARN "[PASSO 2] Confidence baixo: $CONFIDENCE (esperado > 0.7)"
    fi

    if (( PROCESSING_TIME > 5000 )); then
        log WARN "[PASSO 2] Processing time alto: ${PROCESSING_TIME}ms (esperado < 5000ms)"
    fi

    log SUCCESS "[PASSO 2] Gateway Process: PASS"
    log INFO "Intent ID: $INTENT_ID"
    log INFO "Domain: $DOMAIN"
    log INFO "Confidence: $CONFIDENCE"
    log INFO "Processing Time: ${PROCESSING_TIME}ms"

    echo "[PASSO 2] Gateway Process: PASS - Intent ID: $INTENT_ID" >> "$OUTPUT_DIR/validation.log"
    PASSED_STEPS=$((PASSED_STEPS + 1))
    return 0
}

################################################################################
# PASSO 3: Verificar Logs do Gateway
################################################################################
step3_gateway_logs() {
    log INFO "═══════════════════════════════════════════════════════════"
    log INFO "PASSO 3: Verificar Logs do Gateway"
    log INFO "═══════════════════════════════════════════════════════════"

    if [[ -z "$GATEWAY_POD" ]]; then
        log ERROR "[PASSO 3] Gateway pod não encontrado. FAIL"
        echo "[PASSO 3] Gateway Logs: FAIL - Pod não encontrado" >> "$OUTPUT_DIR/validation.log"
        FAILED_STEPS=$((FAILED_STEPS + 1))
        return 1
    fi

    # Aguardar logs serem escritos
    sleep 5

    log INFO "Capturando logs do gateway..."
    kubectl logs -n "$NAMESPACE_GATEWAY" "$GATEWAY_POD" --tail=100 --since=30s > "$OUTPUT_DIR/03-gateway-logs.txt" 2>/dev/null || {
        log WARN "[PASSO 3] Falha ao capturar logs"
    }

    # Filtrar logs relevantes
    grep -E "$INTENT_ID|$CORRELATION_ID|Kafka|producer|intent" "$OUTPUT_DIR/03-gateway-logs.txt" > "$OUTPUT_DIR/03-gateway-logs-filtered.txt" 2>/dev/null || {
        log WARN "[PASSO 3] Nenhum log relevante encontrado"
        echo "" > "$OUTPUT_DIR/03-gateway-logs-filtered.txt"
    }

    # Validar presença de logs esperados
    HAS_KAFKA=$(grep -c "Kafka\|producer\|publicado" "$OUTPUT_DIR/03-gateway-logs.txt" || echo "0")
    HAS_ERROR=$(grep -icE "ERROR|error=|level=error|Exception|Failed|StatusCode\.(4|5)" "$OUTPUT_DIR/03-gateway-logs.txt" || echo "0")

    if (( HAS_KAFKA > 0 )) && (( HAS_ERROR == 0 )); then
        log SUCCESS "[PASSO 3] Gateway Logs: PASS"
        echo "[PASSO 3] Gateway Logs: PASS - Kafka logs: $HAS_KAFKA, Errors: $HAS_ERROR" >> "$OUTPUT_DIR/validation.log"
        PASSED_STEPS=$((PASSED_STEPS + 1))
        return 0
    elif (( HAS_ERROR > 0 )); then
        log ERROR "[PASSO 3] Gateway Logs: FAIL - Errors detectados: $HAS_ERROR"
        echo "[PASSO 3] Gateway Logs: FAIL - Kafka logs: $HAS_KAFKA, Errors: $HAS_ERROR" >> "$OUTPUT_DIR/validation.log"
        FAILED_STEPS=$((FAILED_STEPS + 1))
        return 1
    else
        log WARN "[PASSO 3] Gateway Logs: PARTIAL - Kafka logs: $HAS_KAFKA, Errors: $HAS_ERROR"
        echo "[PASSO 3] Gateway Logs: PARTIAL - Kafka logs: $HAS_KAFKA, Errors: $HAS_ERROR" >> "$OUTPUT_DIR/validation.log"
        PARTIAL_STEPS=$((PARTIAL_STEPS + 1))
        return 0
    fi
}

################################################################################
# PASSO 4: Verificar Semantic Translation Engine
################################################################################
step4_semantic_translation() {
    log INFO "═══════════════════════════════════════════════════════════"
    log INFO "PASSO 4: Verificar Semantic Translation Engine"
    log INFO "═══════════════════════════════════════════════════════════"

    if [[ -z "$STE_POD" ]]; then
        log ERROR "[PASSO 4] Semantic Translation pod não encontrado. FAIL"
        echo "[PASSO 4] Semantic Translation: FAIL - Pod não encontrado" >> "$OUTPUT_DIR/validation.log"
        FAILED_STEPS=$((FAILED_STEPS + 1))
        return 1
    fi

    # Aguardar processamento
    log INFO "Aguardando processamento (10s)..."
    sleep 10

    log INFO "Capturando logs do Semantic Translation Engine..."
    kubectl logs -n "$NAMESPACE_SEMANTIC" "$STE_POD" --tail=200 --since=60s > "$OUTPUT_DIR/04-semantic-logs.txt" 2>/dev/null || {
        log WARN "[PASSO 4] Falha ao capturar logs"
    }

    # Filtrar logs relevantes
    grep -E "$INTENT_ID|Intent parsed|DAG gerado|Plan publicado|plan_id|duration_ms|processing_time" "$OUTPUT_DIR/04-semantic-logs.txt" > "$OUTPUT_DIR/04-semantic-logs-filtered.txt" 2>/dev/null || {
        log WARN "[PASSO 4] Nenhum log relevante encontrado"
        echo "" > "$OUTPUT_DIR/04-semantic-logs-filtered.txt"
    }

    # Extrair plan_id
    PLAN_ID=$(grep -oP 'plan_id[=:]\s*\K[a-f0-9-]{36}' "$OUTPUT_DIR/04-semantic-logs.txt" | head -1 || echo "")

    # Extrair latência do Semantic Translation
    SEMANTIC_LATENCY_MS=$(grep -oP 'duration_ms[=:]\s*\K\d+' "$OUTPUT_DIR/04-semantic-logs.txt" | head -1 || echo "0")

    if [[ -z "$PLAN_ID" ]]; then
        log WARN "[PASSO 4] Plan ID não encontrado nos logs"
        # Tentar formato alternativo
        PLAN_ID=$(grep -oP '"plan_id"\s*:\s*"\K[a-f0-9-]{36}' "$OUTPUT_DIR/04-semantic-logs.txt" | head -1 || echo "")
    fi

    # Salvar plan_id e latência
    if [[ -n "$PLAN_ID" ]]; then
        cat >> "$OUTPUT_DIR/correlation-ids.txt" <<EOF

# Semantic Translation Response
PLAN_ID=$PLAN_ID
SEMANTIC_LATENCY_MS=$SEMANTIC_LATENCY_MS
EOF
        log INFO "Plan ID: $PLAN_ID"
        log INFO "Semantic Latency: ${SEMANTIC_LATENCY_MS}ms"
    fi

    # Validar
    HAS_PLAN=$(grep -c "Plan publicado\|plan_id" "$OUTPUT_DIR/04-semantic-logs.txt" || echo "0")
    HAS_ERROR=$(grep -c "ERROR\|Exception\|Failed" "$OUTPUT_DIR/04-semantic-logs.txt" || echo "0")

    if (( HAS_PLAN > 0 )) && (( HAS_ERROR == 0 )); then
        log SUCCESS "[PASSO 4] Semantic Translation: PASS"
        echo "[PASSO 4] Semantic Translation: PASS - Plan logs: $HAS_PLAN" >> "$OUTPUT_DIR/validation.log"
        PASSED_STEPS=$((PASSED_STEPS + 1))
        return 0
    elif (( HAS_ERROR > 0 )); then
        log ERROR "[PASSO 4] Semantic Translation: FAIL - Errors detectados: $HAS_ERROR"
        echo "[PASSO 4] Semantic Translation: FAIL - Plan logs: $HAS_PLAN, Errors: $HAS_ERROR" >> "$OUTPUT_DIR/validation.log"
        FAILED_STEPS=$((FAILED_STEPS + 1))
        return 1
    else
        log WARN "[PASSO 4] Semantic Translation: PARTIAL - Plan logs: $HAS_PLAN, Errors: $HAS_ERROR"
        echo "[PASSO 4] Semantic Translation: PARTIAL - Plan logs: $HAS_PLAN, Errors: $HAS_ERROR" >> "$OUTPUT_DIR/validation.log"
        PARTIAL_STEPS=$((PARTIAL_STEPS + 1))
        return 0
    fi
}

################################################################################
# PASSO 5: Verificar Consensus Engine
################################################################################
step5_consensus_engine() {
    log INFO "═══════════════════════════════════════════════════════════"
    log INFO "PASSO 5: Verificar Consensus Engine"
    log INFO "═══════════════════════════════════════════════════════════"

    if [[ -z "$CE_PODS" ]]; then
        log ERROR "[PASSO 5] Consensus Engine pods não encontrados. FAIL"
        echo "[PASSO 5] Consensus Engine: FAIL - Pods não encontrados" >> "$OUTPUT_DIR/validation.log"
        FAILED_STEPS=$((FAILED_STEPS + 1))
        return 1
    fi

    # Aguardar invocação de specialists
    log INFO "Aguardando invocação de specialists (15s)..."
    sleep 15

    log INFO "Capturando logs do Consensus Engine..."

    # Capturar logs de todos os pods
    for pod in $CE_PODS; do
        kubectl logs -n "$NAMESPACE_CONSENSUS" "$pod" --tail=300 --since=90s > "$OUTPUT_DIR/05-consensus-$pod-logs.txt" 2>/dev/null || {
            log WARN "[PASSO 5] Falha ao capturar logs do pod $pod"
        }
    done

    # Consolidar logs filtrados
    cat "$OUTPUT_DIR"/05-consensus-*-logs.txt 2>/dev/null | grep -E "$PLAN_ID|Invocando especialistas|EvaluatePlan|gRPC|specialist|Pareceres coletados|Mensagem processada" > "$OUTPUT_DIR/05-consensus-logs-filtered.txt" 2>/dev/null || {
        log WARN "[PASSO 5] Nenhum log relevante encontrado"
        echo "" > "$OUTPUT_DIR/05-consensus-logs-filtered.txt"
    }

    # Contar specialists que responderam
    # Extrair num_opinions do log "Pareceres coletados"
    NUM_OPINIONS_LINE=$(grep "Pareceres coletados" "$OUTPUT_DIR"/05-consensus-*-logs.txt 2>/dev/null | tail -1 || echo "")
    if [[ -n "$NUM_OPINIONS_LINE" ]]; then
        SPECIALISTS_RESPONDED=$(echo "$NUM_OPINIONS_LINE" | grep -oP 'num_opinions[=:]\s*\K\d+' || echo "0")
    else
        # Fallback: contar mensagens de sucesso por specialist nos logs individuais
        SPECIALISTS_RESPONDED=0
        for specialist in business technical behavior evolution architecture; do
            if [[ -f "$OUTPUT_DIR/06-specialist-$specialist-logs.txt" ]]; then
                HAS_RESPONSE=$(grep -c "Received EvaluatePlan\|EvaluatePlan completed" "$OUTPUT_DIR/06-specialist-$specialist-logs.txt" 2>/dev/null || echo "0")
                if (( HAS_RESPONSE > 0 )); then
                    SPECIALISTS_RESPONDED=$((SPECIALISTS_RESPONDED + 1))
                fi
            fi
        done
    fi

    TIMEOUTS=$(grep -c "Timeout ao invocar especialista\|gRPC.*timeout" "$OUTPUT_DIR"/05-consensus-*-logs.txt 2>/dev/null || echo "0")
    TYPEERRORS=$(grep -c "TypeError\|AttributeError.*evaluated_at" "$OUTPUT_DIR"/05-consensus-*-logs.txt 2>/dev/null || echo "0")
    GRPC_ERRORS=$(grep -c "Erro gRPC ao invocar especialista" "$OUTPUT_DIR"/05-consensus-*-logs.txt 2>/dev/null || echo "0")
    UNHANDLED_ERRORS=$(grep -c "Exceção não tratada ao invocar especialista" "$OUTPUT_DIR"/05-consensus-*-logs.txt 2>/dev/null || echo "0")

    # Extrair latência do Consensus Engine (timestamp do log "Mensagem processada com sucesso")
    # Calcular a diferença entre o timestamp de "Invocando especialistas" e "Mensagem processada"
    CONSENSUS_START_TS=$(grep "Invocando especialistas" "$OUTPUT_DIR"/05-consensus-*-logs.txt 2>/dev/null | head -1 | grep -oP '\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}' || echo "")
    CONSENSUS_END_TS=$(grep "Mensagem processada com sucesso" "$OUTPUT_DIR"/05-consensus-*-logs.txt 2>/dev/null | head -1 | grep -oP '\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}' || echo "")

    CONSENSUS_LATENCY_MS=0
    if [[ -n "$CONSENSUS_START_TS" ]] && [[ -n "$CONSENSUS_END_TS" ]]; then
        # Converter para epoch seconds
        START_EPOCH=$(date -d "$CONSENSUS_START_TS" +%s 2>/dev/null || echo "0")
        END_EPOCH=$(date -d "$CONSENSUS_END_TS" +%s 2>/dev/null || echo "0")
        if (( START_EPOCH > 0 )) && (( END_EPOCH > 0 )); then
            CONSENSUS_LATENCY_MS=$(( (END_EPOCH - START_EPOCH) * 1000 ))
        fi
    fi

    log INFO "Specialists responderam: $SPECIALISTS_RESPONDED"
    log INFO "Timeouts: $TIMEOUTS"
    log INFO "TypeErrors: $TYPEERRORS"
    log INFO "gRPC Errors: $GRPC_ERRORS"
    log INFO "Unhandled Errors: $UNHANDLED_ERRORS"
    log INFO "Consensus Latency: ${CONSENSUS_LATENCY_MS}ms"

    # Salvar métricas
    cat >> "$OUTPUT_DIR/correlation-ids.txt" <<EOF

# Consensus Engine Metrics
SPECIALISTS_RESPONDED=$SPECIALISTS_RESPONDED
TIMEOUTS=$TIMEOUTS
TYPEERRORS=$TYPEERRORS
GRPC_ERRORS=$GRPC_ERRORS
UNHANDLED_ERRORS=$UNHANDLED_ERRORS
CONSENSUS_LATENCY_MS=$CONSENSUS_LATENCY_MS

# E2E Latency Calculation
# Gateway + Semantic + Consensus
E2E_LATENCY_MS=$((PROCESSING_TIME + SEMANTIC_LATENCY_MS + CONSENSUS_LATENCY_MS))
EOF

    # Validar - CRITÉRIO: 5/5 specialists com 0 erros
    TOTAL_ERRORS=$((TYPEERRORS + GRPC_ERRORS + UNHANDLED_ERRORS + TIMEOUTS))

    if (( SPECIALISTS_RESPONDED == 5 )) && (( TOTAL_ERRORS == 0 )); then
        log SUCCESS "[PASSO 5] Consensus Engine: PASS"
        echo "[PASSO 5] Consensus Engine: PASS - Specialists: $SPECIALISTS_RESPONDED/5, Errors: $TOTAL_ERRORS" >> "$OUTPUT_DIR/validation.log"
        PASSED_STEPS=$((PASSED_STEPS + 1))
        return 0
    else
        log ERROR "[PASSO 5] Consensus Engine: FAIL - Specialists: $SPECIALISTS_RESPONDED/5, TypeErrors: $TYPEERRORS, gRPC: $GRPC_ERRORS, Unhandled: $UNHANDLED_ERRORS, Timeouts: $TIMEOUTS"
        echo "[PASSO 5] Consensus Engine: FAIL - Specialists: $SPECIALISTS_RESPONDED/5, Errors: $TOTAL_ERRORS (TypeErrors: $TYPEERRORS, gRPC: $GRPC_ERRORS, Unhandled: $UNHANDLED_ERRORS, Timeouts: $TIMEOUTS)" >> "$OUTPUT_DIR/validation.log"
        FAILED_STEPS=$((FAILED_STEPS + 1))
        return 1
    fi
}

################################################################################
# PASSO 6: Verificar Specialists Individuais
################################################################################
step6_specialists() {
    log INFO "═══════════════════════════════════════════════════════════"
    log INFO "PASSO 6: Verificar Specialists Individuais"
    log INFO "═══════════════════════════════════════════════════════════"

    SPECIALISTS_PROCESSED=0

    for specialist in business technical behavior evolution architecture; do
        VAR_NAME="SPECIALIST_${specialist^^}_POD"
        POD="${!VAR_NAME:-}"

        if [[ -z "$POD" ]]; then
            log WARN "Pod do specialist-$specialist não encontrado"
            continue
        fi

        log INFO "Capturando logs do specialist-$specialist..."
        kubectl logs -n "specialist-$specialist" "$POD" --tail=100 --since=120s > "$OUTPUT_DIR/06-specialist-$specialist-logs.txt" 2>/dev/null || {
            log WARN "Falha ao capturar logs do specialist-$specialist"
            continue
        }

        # Verificar processamento
        HAS_EVAL=$(grep -c "Received EvaluatePlan\|EvaluatePlan completed" "$OUTPUT_DIR/06-specialist-$specialist-logs.txt" 2>/dev/null || echo "0")

        if (( HAS_EVAL > 0 )); then
            SPECIALISTS_PROCESSED=$((SPECIALISTS_PROCESSED + 1))
            log SUCCESS "Specialist-$specialist: OK"
        else
            log WARN "Specialist-$specialist: Sem logs de processamento"
        fi
    done

    # Consolidar logs filtrados
    cat "$OUTPUT_DIR"/06-specialist-*-logs.txt 2>/dev/null | grep -E "$PLAN_ID|Received EvaluatePlan|evaluated_at|timestamp|EvaluatePlan completed" > "$OUTPUT_DIR/06-specialists-logs-filtered.txt" 2>/dev/null || {
        echo "" > "$OUTPUT_DIR/06-specialists-logs-filtered.txt"
    }

    log INFO "Specialists processaram: $SPECIALISTS_PROCESSED/5"

    # Salvar métrica
    cat >> "$OUTPUT_DIR/correlation-ids.txt" <<EOF

# Specialists Individual Metrics
SPECIALISTS_PROCESSED=$SPECIALISTS_PROCESSED
EOF

    # Validar - CRITÉRIO: 5/5 specialists processaram
    if (( SPECIALISTS_PROCESSED == 5 )); then
        log SUCCESS "[PASSO 6] Specialists: PASS"
        echo "[PASSO 6] Specialists: PASS - $SPECIALISTS_PROCESSED/5 processaram" >> "$OUTPUT_DIR/validation.log"
        PASSED_STEPS=$((PASSED_STEPS + 1))
        return 0
    else
        log ERROR "[PASSO 6] Specialists: FAIL - $SPECIALISTS_PROCESSED/5 processaram (esperado: 5/5)"
        echo "[PASSO 6] Specialists: FAIL - $SPECIALISTS_PROCESSED/5 processaram (esperado: 5/5)" >> "$OUTPUT_DIR/validation.log"
        FAILED_STEPS=$((FAILED_STEPS + 1))
        return 1
    fi
}

################################################################################
# PASSO 6.5: Verificar Persistência MongoDB
################################################################################
step6_5_mongodb_persistence() {
    log INFO "═══════════════════════════════════════════════════════════"
    log INFO "PASSO 6.5: Verificar Persistência MongoDB"
    log INFO "═══════════════════════════════════════════════════════════"

    if [[ -z "$CE_PODS" ]]; then
        log ERROR "[PASSO 6.5] Consensus Engine pods não encontrados. FAIL"
        echo "[PASSO 6.5] MongoDB Persistence: FAIL - Pods não encontrados" >> "$OUTPUT_DIR/validation.log"
        FAILED_STEPS=$((FAILED_STEPS + 1))
        return 1
    fi

    log INFO "Verificando logs de persistência..."

    # Buscar logs de MongoDB
    cat "$OUTPUT_DIR"/05-consensus-*-logs.txt 2>/dev/null | grep -E "$PLAN_ID|MongoDB|save_consensus_decision|Decisao salva no ledger|ledger" > "$OUTPUT_DIR/06.5-mongodb-persistence.txt" 2>/dev/null || {
        log WARN "[PASSO 6.5] Nenhum log de MongoDB encontrado"
        echo "" > "$OUTPUT_DIR/06.5-mongodb-persistence.txt"
    }

    # Validar - procurar pelo log específico "Decisao salva no ledger"
    HAS_SAVE=$(grep -c "Decisao salva no ledger\|save_consensus_decision.*success" "$OUTPUT_DIR/06.5-mongodb-persistence.txt" 2>/dev/null || echo "0")

    # Extrair decision_id se disponível
    DECISION_ID=$(grep -oP 'decision_id[=:]\s*\K[a-f0-9-]{36}' "$OUTPUT_DIR/06.5-mongodb-persistence.txt" | head -1 || echo "")

    # Salvar métrica
    cat >> "$OUTPUT_DIR/correlation-ids.txt" <<EOF

# MongoDB Persistence
MONGODB_SAVE_COUNT=$HAS_SAVE
DECISION_ID=$DECISION_ID
EOF

    if (( HAS_SAVE > 0 )); then
        log SUCCESS "[PASSO 6.5] MongoDB Persistence: PASS - Decision ID: ${DECISION_ID:-N/A}"
        echo "[PASSO 6.5] MongoDB Persistence: PASS - Saves: $HAS_SAVE, Decision ID: $DECISION_ID" >> "$OUTPUT_DIR/validation.log"
        PASSED_STEPS=$((PASSED_STEPS + 1))
        return 0
    else
        log WARN "[PASSO 6.5] MongoDB Persistence: FAIL - Nenhuma evidência de persistência"
        echo "[PASSO 6.5] MongoDB Persistence: FAIL - Saves: $HAS_SAVE" >> "$OUTPUT_DIR/validation.log"
        FAILED_STEPS=$((FAILED_STEPS + 1))
        return 1
    fi
}

################################################################################
# PASSO 7: Verificar Memory Layer API
################################################################################
step7_memory_layer() {
    log INFO "═══════════════════════════════════════════════════════════"
    log INFO "PASSO 7: Verificar Memory Layer API"
    log INFO "═══════════════════════════════════════════════════════════"

    if [[ -z "$ML_POD" ]]; then
        log ERROR "[PASSO 7] Memory Layer pod não encontrado. FAIL"
        echo "[PASSO 7] Memory Layer API: FAIL - Pod não encontrado" >> "$OUTPUT_DIR/validation.log"
        FAILED_STEPS=$((FAILED_STEPS + 1))
        return 1
    fi

    # Aguardar indexação
    log INFO "Aguardando indexação de dados (20s)..."
    sleep 20

    # Obter ClusterIP do Memory Layer
    ML_SVC_IP=$(kubectl get svc -n "$NAMESPACE_MEMORY" memory-layer-api -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")

    # Health check
    log INFO "Executando health check..."
    if [[ -n "$ML_SVC_IP" ]]; then
        kubectl_curl "http://${ML_SVC_IP}:8000/health" "GET" "" "" "$NAMESPACE_MEMORY" > "$OUTPUT_DIR/07-memory-health.json" || log WARN "[PASSO 7] Health check falhou"
    else
        kubectl exec -n "$NAMESPACE_MEMORY" "$ML_POD" -- curl -s http://localhost:8000/health > "$OUTPUT_DIR/07-memory-health.json" 2>/dev/null || log WARN "[PASSO 7] Health check falhou"
    fi

    # Readiness check
    log INFO "Executando readiness check..."
    if [[ -n "$ML_SVC_IP" ]]; then
        kubectl_curl "http://${ML_SVC_IP}:8000/ready" "GET" "" "" "$NAMESPACE_MEMORY" > "$OUTPUT_DIR/07-memory-ready.json" || log WARN "[PASSO 7] Readiness check falhou"
    else
        kubectl exec -n "$NAMESPACE_MEMORY" "$ML_POD" -- curl -s http://localhost:8000/ready > "$OUTPUT_DIR/07-memory-ready.json" 2>/dev/null || log WARN "[PASSO 7] Readiness check falhou"
    fi

    # Query por intent_id
    if [[ -n "$INTENT_ID" ]]; then
        log INFO "Consultando dados por Intent ID..."
        QUERY_PAYLOAD="{\"query_type\": \"INTENT\", \"entity_id\": \"$INTENT_ID\", \"use_cache\": false}"
        if [[ -n "$ML_SVC_IP" ]]; then
            kubectl_curl "http://${ML_SVC_IP}:8000/api/v1/memory/query" "POST" "$QUERY_PAYLOAD" "-H 'Content-Type: application/json'" "$NAMESPACE_MEMORY" > "$OUTPUT_DIR/07-memory-query-intent.json" || log WARN "[PASSO 7] Query por Intent ID falhou"
        else
            kubectl exec -n "$NAMESPACE_MEMORY" "$ML_POD" -- curl -s -X POST http://localhost:8000/api/v1/memory/query \
                -H "Content-Type: application/json" \
                -d "$QUERY_PAYLOAD" > "$OUTPUT_DIR/07-memory-query-intent.json" 2>/dev/null || log WARN "[PASSO 7] Query por Intent ID falhou"
        fi
    fi

    # Query por plan_id
    if [[ -n "$PLAN_ID" ]]; then
        log INFO "Consultando dados por Plan ID..."
        QUERY_PAYLOAD="{\"query_type\": \"PLAN\", \"entity_id\": \"$PLAN_ID\", \"use_cache\": false}"
        if [[ -n "$ML_SVC_IP" ]]; then
            kubectl_curl "http://${ML_SVC_IP}:8000/api/v1/memory/query" "POST" "$QUERY_PAYLOAD" "-H 'Content-Type: application/json'" "$NAMESPACE_MEMORY" > "$OUTPUT_DIR/07-memory-query-plan.json" || log WARN "[PASSO 7] Query por Plan ID falhou"
        else
            kubectl exec -n "$NAMESPACE_MEMORY" "$ML_POD" -- curl -s -X POST http://localhost:8000/api/v1/memory/query \
                -H "Content-Type: application/json" \
                -d "$QUERY_PAYLOAD" > "$OUTPUT_DIR/07-memory-query-plan.json" 2>/dev/null || log WARN "[PASSO 7] Query por Plan ID falhou"
        fi
    fi

    # Validar readiness
    READY=$(jq -r '.ready // false' "$OUTPUT_DIR/07-memory-ready.json" 2>/dev/null || echo "false")

    if [[ "$READY" != "true" ]]; then
        log ERROR "[PASSO 7] Memory Layer API: FAIL - Not ready"
        echo "[PASSO 7] Memory Layer API: FAIL - Not ready" >> "$OUTPUT_DIR/validation.log"
        FAILED_STEPS=$((FAILED_STEPS + 1))
        return 1
    fi

    # Validar dados da query de intent
    INTENT_QUERY_VALID=false
    if [[ -f "$OUTPUT_DIR/07-memory-query-intent.json" ]]; then
        INTENT_DATA_INTENT_ID=$(jq -r '.data.intent_id // empty' "$OUTPUT_DIR/07-memory-query-intent.json" 2>/dev/null || echo "")
        if [[ -n "$INTENT_DATA_INTENT_ID" ]]; then
            INTENT_QUERY_VALID=true
            log INFO "Intent query validada: intent_id=$INTENT_DATA_INTENT_ID"
        else
            log WARN "Intent query incompleta: intent_id ausente"
        fi
    fi

    # Validar dados da query de plan
    PLAN_QUERY_VALID=false
    if [[ -f "$OUTPUT_DIR/07-memory-query-plan.json" ]]; then
        PLAN_DATA_PLAN_ID=$(jq -r '.data.plan_id // empty' "$OUTPUT_DIR/07-memory-query-plan.json" 2>/dev/null || echo "")
        PLAN_DATA_OPINIONS=$(jq -r '.data.opinions // [] | length' "$OUTPUT_DIR/07-memory-query-plan.json" 2>/dev/null || echo "0")
        PLAN_DATA_DECISION=$(jq -r '.data.decision // empty' "$OUTPUT_DIR/07-memory-query-plan.json" 2>/dev/null || echo "")

        if [[ -n "$PLAN_DATA_PLAN_ID" ]] && (( PLAN_DATA_OPINIONS > 0 )); then
            PLAN_QUERY_VALID=true
            log INFO "Plan query validada: plan_id=$PLAN_DATA_PLAN_ID, opinions=$PLAN_DATA_OPINIONS"
        else
            log WARN "Plan query incompleta: plan_id=$PLAN_DATA_PLAN_ID, opinions=$PLAN_DATA_OPINIONS"
        fi
    fi

    # Salvar métricas
    cat >> "$OUTPUT_DIR/correlation-ids.txt" <<EOF

# Memory Layer Validation
INTENT_QUERY_VALID=$INTENT_QUERY_VALID
PLAN_QUERY_VALID=$PLAN_QUERY_VALID
PLAN_DATA_OPINIONS=$PLAN_DATA_OPINIONS
EOF

    # Critério de aprovação: ready + pelo menos uma query válida
    if [[ "$INTENT_QUERY_VALID" == "true" ]] || [[ "$PLAN_QUERY_VALID" == "true" ]]; then
        log SUCCESS "[PASSO 7] Memory Layer API: PASS - Ready: $READY, Intent query: $INTENT_QUERY_VALID, Plan query: $PLAN_QUERY_VALID"
        echo "[PASSO 7] Memory Layer API: PASS - Intent query: $INTENT_QUERY_VALID, Plan query: $PLAN_QUERY_VALID" >> "$OUTPUT_DIR/validation.log"
        PASSED_STEPS=$((PASSED_STEPS + 1))
        return 0
    else
        log ERROR "[PASSO 7] Memory Layer API: FAIL - Nenhuma query retornou dados válidos"
        echo "[PASSO 7] Memory Layer API: FAIL - Intent query: $INTENT_QUERY_VALID, Plan query: $PLAN_QUERY_VALID" >> "$OUTPUT_DIR/validation.log"
        FAILED_STEPS=$((FAILED_STEPS + 1))
        return 1
    fi
}

################################################################################
# Função: generate_summary
# Propósito: Gerar resumo da validação
################################################################################
generate_summary() {
    log INFO "═══════════════════════════════════════════════════════════"
    log INFO "Gerando resumo da validação..."
    log INFO "═══════════════════════════════════════════════════════════"

    SUCCESS_RATE=$(echo "scale=2; $PASSED_STEPS * 100 / $TOTAL_STEPS" | bc)

    cat > "$OUTPUT_DIR/SUMMARY.txt" <<EOF
═══════════════════════════════════════════════════════════
VALIDAÇÃO E2E - NEURAL HIVE-MIND v1.0.9
═══════════════════════════════════════════════════════════

Data: $(date)
Validation ID: $VALIDATION_ID
Correlation ID: $CORRELATION_ID

IDs de Correlação:
- Intent ID: ${INTENT_ID:-N/A}
- Plan ID: ${PLAN_ID:-N/A}
- Domain: ${DOMAIN:-N/A}

Resultados:
- Taxa de Sucesso: ${SUCCESS_RATE}% ($PASSED_STEPS/$TOTAL_STEPS passos)
- Passos PASS: $PASSED_STEPS
- Passos PARTIAL: $PARTIAL_STEPS
- Passos FAIL: $FAILED_STEPS
- Specialists Responderam: ${SPECIALISTS_RESPONDED:-0}/5
- Timeouts: ${TIMEOUTS:-0}
- TypeErrors: ${TYPEERRORS:-0}

Métricas:
- E2E Latency Total: ${E2E_LATENCY_MS:-N/A}ms
- Gateway Latency: ${PROCESSING_TIME:-N/A}ms
- Semantic Latency: ${SEMANTIC_LATENCY_MS:-N/A}ms
- Consensus Latency: ${CONSENSUS_LATENCY_MS:-N/A}ms
- Gateway Confidence: ${CONFIDENCE:-N/A}

Status por Passo:
$(grep -E "^\[PASSO" "$OUTPUT_DIR/validation.log" | tail -7)

Artefatos Gerados:
- Logs: $OUTPUT_DIR/
- Relatório: RELATORIO_VALIDACAO_E2E_POS_CORRECAO.md (gerar com generate-e2e-report-v1.0.9.sh)

Próximos Passos:
1. Gerar relatório estruturado:
   ./scripts/validation/generate-e2e-report-v1.0.9.sh $OUTPUT_DIR

2. Analisar logs detalhados:
   cat $OUTPUT_DIR/validation.log

3. Ver logs de componentes específicos:
   cat $OUTPUT_DIR/05-consensus-logs-filtered.txt
   cat $OUTPUT_DIR/06-specialists-logs-filtered.txt
EOF

    cat "$OUTPUT_DIR/SUMMARY.txt"

    log SUCCESS "Resumo gerado: $OUTPUT_DIR/SUMMARY.txt"
}

################################################################################
# MAIN
################################################################################
main() {
    echo ""
    log INFO "═══════════════════════════════════════════════════════════"
    log INFO "VALIDAÇÃO E2E - NEURAL HIVE-MIND v1.0.9"
    log INFO "═══════════════════════════════════════════════════════════"
    echo ""

    # Preparação
    check_prerequisites
    create_output_dir
    detect_pods

    echo ""
    log INFO "Iniciando validação E2E..."
    echo ""

    # Executar passos (continuar mesmo se falhar)
    step1_gateway_health || true
    step2_send_intent || true
    step3_gateway_logs || true
    step4_semantic_translation || true
    step5_consensus_engine || true
    step6_specialists || true
    step6_5_mongodb_persistence || true
    step7_memory_layer || true

    # Gerar resumo
    echo ""
    generate_summary

    # Exit code
    if (( FAILED_STEPS == 0 )); then
        log SUCCESS "Validação concluída com sucesso! ✅"
        exit 0
    else
        log WARN "Validação concluída com falhas. ⚠️"
        exit 1
    fi
}

# Executar
main "$@"
