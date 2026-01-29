#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
set -euo pipefail

#==============================================================================
# Script Orquestrador Mestre - Validação Completa de Especialistas
#
# Executa todos os scripts de validação em sequência:
# 1. Validação de modelos ML (validate_models_loaded.sh)
# 2. Validação de saúde dos especialistas (validate-specialist-health.sh)
# 3. Teste de inferência de modelos (test-specialist-inference.py)
# 4. Teste E2E do Consensus Engine (test-consensus-engine-e2e.py)
# 5. Validação de métricas Prometheus (validate-prometheus-metrics.sh)
#
# Gera relatório HTML unificado com resultados de todas as validações.
#
# Uso:
#   ./validate-all-specialists.sh
#   ./validate-all-specialists.sh --quick              # Skip testes de inferência e E2E
#   ./validate-all-specialists.sh --specialist technical  # Valida apenas um especialista
#   ./validate-all-specialists.sh --output-dir ./reports  # Diretório customizado para relatórios
#   ./validate-all-specialists.sh --ci-mode            # Output JSON para CI/CD
#==============================================================================

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configurações padrão
NAMESPACE="${NAMESPACE:-semantic-translation}"
OUTPUT_DIR="${OUTPUT_DIR:-./validation-reports}"
QUICK_MODE=false
CI_MODE=false
SPECIALIST=""

# Timestamps
START_TIME=$(date +%s)
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Contadores globais
TOTAL_PHASES=6
COMPLETED_PHASES=0
FAILED_PHASES=0

# Parse argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)
            QUICK_MODE=true
            shift
            ;;
        --specialist)
            SPECIALIST="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --ci-mode)
            CI_MODE=true
            shift
            ;;
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        *)
            echo "Argumento desconhecido: $1"
            exit 1
            ;;
    esac
done

# Criar diretório de saída
mkdir -p "$OUTPUT_DIR"

# Log file
LOG_FILE="$OUTPUT_DIR/validation-run-$TIMESTAMP.log"

# Função de log
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

log "================================================================================"
log "🚀 Neural Hive - Validação Completa de Especialistas"
log "================================================================================"
log ""
log "Configuração:"
log "  Namespace: $NAMESPACE"
log "  Quick Mode: $QUICK_MODE"
log "  CI Mode: $CI_MODE"
log "  Output Dir: $OUTPUT_DIR"
log "  Specialist Filter: ${SPECIALIST:-todos}"
log "  Timestamp: $TIMESTAMP"
log ""

#==============================================================================
# Fase 1: Pré-requisitos
#==============================================================================
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "🔍 Fase 1/6: Verificando pré-requisitos"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Verificar kubectl
if ! command -v kubectl &> /dev/null; then
    log "${RED}❌ kubectl não encontrado${NC}"
    exit 1
fi

# Verificar acesso ao cluster
if ! kubectl cluster-info &> /dev/null; then
    log "${RED}❌ Não foi possível conectar ao cluster Kubernetes${NC}"
    exit 1
fi

# Verificar namespace
if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
    log "${RED}❌ Namespace $NAMESPACE não existe${NC}"
    exit 1
fi

# Verificar ferramentas necessárias
REQUIRED_TOOLS=("curl" "jq" "python3")
for tool in "${REQUIRED_TOOLS[@]}"; do
    if ! command -v "$tool" &> /dev/null; then
        log "${RED}❌ Ferramenta necessária não encontrada: $tool${NC}"
        exit 1
    fi
done

log "${GREEN}✅ Pré-requisitos OK${NC}"
log ""

#==============================================================================
# Fase 2: Validação de Modelos ML
#==============================================================================
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "🤖 Fase 2/6: Validando modelos ML (MLflow)"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

MODELS_SCRIPT="../../ml_pipelines/training/validate_models_loaded.sh"
if [[ -f "$MODELS_SCRIPT" ]]; then
    if NAMESPACE="$NAMESPACE" bash "$MODELS_SCRIPT" >> "$LOG_FILE" 2>&1; then
        log "${GREEN}✅ Modelos ML validados com sucesso${NC}"
        COMPLETED_PHASES=$((COMPLETED_PHASES + 1))
    else
        log "${RED}❌ Falha na validação de modelos ML${NC}"
        FAILED_PHASES=$((FAILED_PHASES + 1))
    fi
else
    log "${YELLOW}⚠️  Script de validação de modelos não encontrado: $MODELS_SCRIPT${NC}"
    FAILED_PHASES=$((FAILED_PHASES + 1))
fi
log ""

#==============================================================================
# Fase 3: Validação de Saúde dos Especialistas
#==============================================================================
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "🏥 Fase 3/6: Validando saúde dos especialistas (pods, containers, endpoints)"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

HEALTH_SCRIPT="./validate-specialist-health.sh"
if [[ -f "$HEALTH_SCRIPT" ]]; then
    HEALTH_CMD="bash $HEALTH_SCRIPT --namespace $NAMESPACE"
    if [[ -n "$SPECIALIST" ]]; then
        HEALTH_CMD="$HEALTH_CMD --specialist $SPECIALIST"
    fi

    if $HEALTH_CMD >> "$LOG_FILE" 2>&1; then
        log "${GREEN}✅ Saúde dos especialistas validada${NC}"
        COMPLETED_PHASES=$((COMPLETED_PHASES + 1))
    else
        log "${RED}❌ Falha na validação de saúde${NC}"
        FAILED_PHASES=$((FAILED_PHASES + 1))
    fi
else
    log "${YELLOW}⚠️  Script de validação de saúde não encontrado${NC}"
    FAILED_PHASES=$((FAILED_PHASES + 1))
fi
log ""

#==============================================================================
# Fase 4: Teste de Inferência (skip se --quick)
#==============================================================================
if [[ "$QUICK_MODE" == false ]]; then
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "🧠 Fase 4/6: Testando inferência de modelos via gRPC"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    INFERENCE_SCRIPT="./test-specialist-inference.py"
    if [[ -f "$INFERENCE_SCRIPT" ]]; then
        INFERENCE_OUTPUT="$OUTPUT_DIR/inference-test-$TIMESTAMP.json"
        INFERENCE_CMD="python3 $INFERENCE_SCRIPT --namespace $NAMESPACE --output-json $INFERENCE_OUTPUT"

        if [[ -n "$SPECIALIST" ]]; then
            INFERENCE_CMD="$INFERENCE_CMD --specialist $SPECIALIST"
        fi

        if $INFERENCE_CMD >> "$LOG_FILE" 2>&1; then
            log "${GREEN}✅ Testes de inferência completados${NC}"
            COMPLETED_PHASES=$((COMPLETED_PHASES + 1))
        else
            log "${RED}❌ Falha nos testes de inferência${NC}"
            FAILED_PHASES=$((FAILED_PHASES + 1))
        fi
    else
        log "${YELLOW}⚠️  Script de teste de inferência não encontrado${NC}"
        FAILED_PHASES=$((FAILED_PHASES + 1))
    fi
else
    log "⏩ Fase 4/6: Teste de inferência PULADO (--quick mode)"
    TOTAL_PHASES=$((TOTAL_PHASES - 1))
fi
log ""

#==============================================================================
# Fase 5: Teste E2E do Consensus Engine (skip se --quick)
#==============================================================================
if [[ "$QUICK_MODE" == false ]]; then
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "🔄 Fase 5/6: Testando Consensus Engine E2E (Kafka → MongoDB/Redis)"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    CONSENSUS_E2E_SCRIPT="./test-consensus-engine-e2e.py"
    if [[ -f "$CONSENSUS_E2E_SCRIPT" ]]; then
        CONSENSUS_E2E_OUTPUT="$OUTPUT_DIR/consensus-e2e-test-$TIMESTAMP.json"
        CONSENSUS_E2E_CMD="python3 $CONSENSUS_E2E_SCRIPT --namespace $NAMESPACE --output-json $CONSENSUS_E2E_OUTPUT"

        if $CONSENSUS_E2E_CMD >> "$LOG_FILE" 2>&1; then
            log "${GREEN}✅ Teste E2E do Consensus Engine completado${NC}"
            COMPLETED_PHASES=$((COMPLETED_PHASES + 1))
        else
            log "${RED}❌ Falha no teste E2E do Consensus Engine${NC}"
            FAILED_PHASES=$((FAILED_PHASES + 1))
        fi
    else
        log "${YELLOW}⚠️  Script de teste E2E do Consensus Engine não encontrado: $CONSENSUS_E2E_SCRIPT${NC}"
        FAILED_PHASES=$((FAILED_PHASES + 1))
    fi
else
    log "⏩ Fase 5/6: Teste E2E do Consensus Engine PULADO (--quick mode)"
    TOTAL_PHASES=$((TOTAL_PHASES - 1))
fi
log ""

#==============================================================================
# Fase 6: Validação de Métricas Prometheus
#==============================================================================
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "📊 Fase 6/6: Validando métricas Prometheus/Grafana"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

METRICS_SCRIPT="./validate-prometheus-metrics.sh"
if [[ -f "$METRICS_SCRIPT" ]]; then
    if bash "$METRICS_SCRIPT" --namespace "$NAMESPACE" >> "$LOG_FILE" 2>&1; then
        log "${GREEN}✅ Métricas Prometheus validadas${NC}"
        COMPLETED_PHASES=$((COMPLETED_PHASES + 1))
    else
        log "${RED}❌ Falha na validação de métricas${NC}"
        FAILED_PHASES=$((FAILED_PHASES + 1))
    fi
else
    log "${YELLOW}⚠️  Script de validação de métricas não encontrado${NC}"
    FAILED_PHASES=$((FAILED_PHASES + 1))
fi
log ""

#==============================================================================
# Relatório Final
#==============================================================================
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

log "================================================================================"
log "📊 RELATÓRIO FINAL - Validação de Especialistas"
log "================================================================================"
log ""
log "Fases executadas: $TOTAL_PHASES"
log -e "${GREEN}✅ Completadas: $COMPLETED_PHASES${NC}"
log -e "${RED}❌ Falhadas: $FAILED_PHASES${NC}"
log ""
log "Duração total: ${DURATION}s"
log "Log completo: $LOG_FILE"
log ""

# Calcular taxa de sucesso
SUCCESS_RATE=0
if [[ $TOTAL_PHASES -gt 0 ]]; then
    SUCCESS_RATE=$((COMPLETED_PHASES * 100 / TOTAL_PHASES))
fi

log "Taxa de sucesso: ${SUCCESS_RATE}%"

if [[ $SUCCESS_RATE -ge 80 ]]; then
    log -e "${GREEN}🎉 VALIDAÇÃO APROVADA${NC}"
    EXIT_CODE=0
elif [[ $SUCCESS_RATE -ge 50 ]]; then
    log -e "${YELLOW}⚠️  VALIDAÇÃO COM AVISOS (modo degradado)${NC}"
    EXIT_CODE=2
else
    log -e "${RED}❌ VALIDAÇÃO REPROVADA${NC}"
    EXIT_CODE=1
fi

log "================================================================================"

# CI Mode: gerar JSON
if [[ "$CI_MODE" == true ]]; then
    CI_REPORT="$OUTPUT_DIR/ci-report-$TIMESTAMP.json"
    cat > "$CI_REPORT" <<EOF
{
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "namespace": "$NAMESPACE",
  "total_phases": $TOTAL_PHASES,
  "completed_phases": $COMPLETED_PHASES,
  "failed_phases": $FAILED_PHASES,
  "success_rate": $SUCCESS_RATE,
  "duration_seconds": $DURATION,
  "exit_code": $EXIT_CODE,
  "log_file": "$LOG_FILE"
}
EOF
    log "📄 Relatório CI gerado: $CI_REPORT"
fi

exit $EXIT_CODE
