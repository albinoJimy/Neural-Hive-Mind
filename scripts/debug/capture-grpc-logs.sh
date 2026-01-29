#!/bin/bash

################################################################################
# Script: capture-grpc-logs.sh
# Descrição: Automatiza a captura de logs gRPC com filtros específicos para
#            análise do TypeError relacionado ao campo evaluated_at
# Versão: 1.0.0
# Data: 2025-11-09
################################################################################

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configurações padrão
NAMESPACE_SPECIALISTS="${NAMESPACE_SPECIALISTS:-neural-hive}"
NAMESPACE_CONSENSUS="${NAMESPACE_CONSENSUS:-neural-hive}"
DURATION="${DURATION:-300}" # 5 minutos padrão
PLAN_ID="${PLAN_ID:-}" # Opcional
LOG_DIR_BASE="/jimy/Neural-Hive-Mind/logs"
SESSION_ID="debug-session-$(date +%Y%m%d-%H%M%S)"
LOG_DIR="$LOG_DIR_BASE/$SESSION_ID"

# Array de specialists
SPECIALISTS=("business" "technical" "behavior" "evolution" "architecture")

# PIDs dos processos de captura
declare -a CAPTURE_PIDS=()

# Funções auxiliares
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

log_alert() {
    echo -e "${MAGENTA}[ALERT]${NC} $1"
}

print_separator() {
    echo "================================================================================"
}

print_banner() {
    print_separator
    echo -e "${CYAN}"
    echo "   ____                   _____  ____   ____   ____   _                       "
    echo "  / ___| _ __  ___  __  |  ___||  _ \ / ___| |  _ \ / \                      "
    echo " | |  _ | '__|/ _ \| | || |_   | |_) | |     | |_) / _ \                     "
    echo " | |_| || |  | (_) | |_|| |_|  |  __/| |___  |  __/ ___ \                    "
    echo "  \____||_|   \___/ \__,_|_|    |_|    \____| |_| /_/   \_\                  "
    echo "                                                                              "
    echo "                  Log Capture Tool for TypeError Analysis                    "
    echo -e "${NC}"
    print_separator
}

setup_log_directory() {
    log_info "Criando diretório de logs: $LOG_DIR"

    mkdir -p "$LOG_DIR"

    if [ ! -d "$LOG_DIR" ]; then
        log_error "Falha ao criar diretório de logs: $LOG_DIR"
        exit 1
    fi

    log_success "Diretório de logs criado: $LOG_DIR"
}

create_session_readme() {
    local readme_file="$LOG_DIR/README.md"

    log_info "Criando arquivo README da sessão..."

    cat > "$readme_file" <<EOF
# Sessão de Captura de Logs gRPC - TypeError Analysis

**Session ID**: $SESSION_ID
**Data/Hora Início**: $(date '+%Y-%m-%d %H:%M:%S')
**Duração Configurada**: ${DURATION}s ($(($DURATION / 60)) minutos)
**Namespace Specialists**: $NAMESPACE_SPECIALISTS
**Namespace Consensus**: $NAMESPACE_CONSENSUS
$([ -n "$PLAN_ID" ] && echo "**Plan ID Filtrado**: $PLAN_ID")

---

## Arquivos de Log Capturados

| Componente | Arquivo | Padrões Filtrados |
|------------|---------|-------------------|
| consensus-engine | consensus-engine-<pod-name>-debug.log (um arquivo por pod) + consensus-engine-combined-debug.log (todos os pods) | EvaluatePlan, TypeError, evaluated_at, gRPC channel, Invocando especialistas |
| specialist-business | specialist-business-<pod-name>-debug.log (por pod) + specialist-business-combined-debug.log | EvaluatePlan, evaluated_at, processing_time_ms, Received EvaluatePlan, completed successfully |
| specialist-technical | specialist-technical-<pod-name>-debug.log (por pod) + specialist-technical-combined-debug.log | EvaluatePlan, evaluated_at, processing_time_ms, Received EvaluatePlan, completed successfully |
| specialist-behavior | specialist-behavior-<pod-name>-debug.log (por pod) + specialist-behavior-combined-debug.log | EvaluatePlan, evaluated_at, processing_time_ms, Received EvaluatePlan, completed successfully |
| specialist-evolution | specialist-evolution-<pod-name>-debug.log (por pod) + specialist-evolution-combined-debug.log | EvaluatePlan, evaluated_at, processing_time_ms, Received EvaluatePlan, completed successfully |
| specialist-architecture | specialist-architecture-<pod-name>-debug.log (por pod) + specialist-architecture-combined-debug.log | EvaluatePlan, evaluated_at, processing_time_ms, Received EvaluatePlan, completed successfully |

**Nota**: Arquivos `-combined-debug.log` agregam logs de todos os pods do respectivo componente em tempo real.

---

## Comandos kubectl Utilizados

### Consensus Engine
\`\`\`bash
# Captura de cada pod individualmente
for pod in \$(kubectl get pods -n $NAMESPACE_CONSENSUS -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[*].metadata.name}'); do
  kubectl logs -f \$pod -n $NAMESPACE_CONSENSUS --tail=100 | \\
    grep -E 'EvaluatePlan|TypeError|evaluated_at|gRPC channel|Invocando especialistas'
done
\`\`\`

### Specialists
\`\`\`bash
for specialist in business technical behavior evolution architecture; do
  kubectl logs -f deployment/specialist-\$specialist -n $NAMESPACE_SPECIALISTS --tail=100 | \\
    grep -E 'EvaluatePlan|evaluated_at|processing_time_ms|Received EvaluatePlan|completed successfully'
done
\`\`\`

---

## Status da Captura

- **Status**: Em andamento
- **Início**: $(date '+%Y-%m-%d %H:%M:%S')
- **Término Previsto**: $(date -d "+${DURATION} seconds" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -v +${DURATION}S '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "N/A")

---

## Próximos Passos

1. Aguardar término da captura (${DURATION}s)
2. Analisar logs capturados neste diretório
3. Preencher análise em \`ANALISE_DEBUG_GRPC_TYPEERROR.md\`
4. Correlacionar logs por plan_id/trace_id
5. Identificar causa raiz do TypeError

---

## Observações

- Todos os pods devem estar com LOG_LEVEL=DEBUG
- Filtros regex aplicados para reduzir ruído
- Logs capturados em tempo real via \`kubectl logs -f\`
- Sessão pode ser interrompida com Ctrl+C (será tratado gracefully)

EOF

    log_success "README da sessão criado: $readme_file"
}

check_pod_exists() {
    local namespace=$1
    local deployment=$2

    if ! kubectl get deployment "$deployment" -n "$namespace" &> /dev/null; then
        log_warning "Deployment $deployment não encontrado no namespace $namespace"
        return 1
    fi

    # Try primary label selector first
    local pod_count=$(kubectl get pods -n "$namespace" -l app.kubernetes.io/name="$deployment" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)

    # Fallback to alternative label selector if no pods found
    if [ "$pod_count" -eq 0 ]; then
        pod_count=$(kubectl get pods -n "$namespace" -l app="$deployment" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
    fi

    if [ "$pod_count" -eq 0 ]; then
        log_warning "Nenhum pod running encontrado para deployment $deployment"
        return 1
    fi

    return 0
}

capture_consensus_logs() {
    local filter_pattern="${CONSENSUS_FILTER:-EvaluatePlan|TypeError|evaluated_at|gRPC channel|Invocando especialistas}"

    log_info "Iniciando captura de logs do consensus-engine..."

    if ! check_pod_exists "$NAMESPACE_CONSENSUS" "consensus-engine"; then
        log_error "Não foi possível iniciar captura para consensus-engine"
        return 1
    fi

    # Adicionar plan_id ao filtro se fornecido
    if [ -n "$PLAN_ID" ]; then
        filter_pattern="$filter_pattern|$PLAN_ID"
    fi

    # Obter lista de pods do consensus-engine
    local pods=($(kubectl get pods -n "$NAMESPACE_CONSENSUS" -l app.kubernetes.io/name=consensus-engine --field-selector=status.phase=Running -o jsonpath='{.items[*].metadata.name}' 2>/dev/null))

    # Fallback to alternative label if no pods found
    if [ ${#pods[@]} -eq 0 ]; then
        log_warning "Nenhum pod encontrado com label app.kubernetes.io/name=consensus-engine, tentando app=consensus-engine..."
        pods=($(kubectl get pods -n "$NAMESPACE_CONSENSUS" -l app=consensus-engine --field-selector=status.phase=Running -o jsonpath='{.items[*].metadata.name}' 2>/dev/null))
    fi

    if [ ${#pods[@]} -eq 0 ]; then
        log_error "Nenhum pod running encontrado para consensus-engine"
        return 1
    fi

    log_info "Encontrados ${#pods[@]} pod(s) do consensus-engine: ${pods[*]}"

    # Create combined log file for consensus-engine
    local combined_log="$LOG_DIR/consensus-engine-combined-debug.log"
    touch "$combined_log"

    # Capturar logs de cada pod
    for pod in "${pods[@]}"; do
        local log_file="$LOG_DIR/consensus-engine-${pod}-debug.log"

        # Captura em background com tee para arquivo individual, arquivo combinado e stdout
        (
            kubectl logs -f "$pod" -n "$NAMESPACE_CONSENSUS" --tail=100 2>&1 | \
            grep --line-buffered -E "$filter_pattern" | \
            tee -a "$log_file" | \
            tee -a "$combined_log" | \
            while IFS= read -r line; do
                # Detectar erros críticos e emitir alerta visual
                if echo "$line" | grep -qi "TypeError"; then
                    echo -e "${RED}[CONSENSUS-ENGINE:${pod}]${NC} ${MAGENTA}[TypeError DETECTED]${NC} $line"
                elif echo "$line" | grep -qi "error"; then
                    echo -e "${RED}[CONSENSUS-ENGINE:${pod}]${NC} ${YELLOW}[ERROR]${NC} $line"
                else
                    echo -e "${CYAN}[CONSENSUS-ENGINE:${pod}]${NC} $line"
                fi
            done
        ) &

        CAPTURE_PIDS+=($!)
        log_success "Captura do consensus-engine pod $pod iniciada (PID: ${CAPTURE_PIDS[-1]})"
    done

    log_info "Arquivo combinado sendo continuamente populado: $combined_log"
}

capture_specialist_logs() {
    local specialist_type=$1
    local filter_pattern="${SPECIALIST_FILTER:-EvaluatePlan|evaluated_at|processing_time_ms|Received EvaluatePlan|completed successfully}"

    log_info "Iniciando captura de logs do specialist-${specialist_type}..."

    if ! check_pod_exists "$NAMESPACE_SPECIALISTS" "specialist-${specialist_type}"; then
        log_error "Não foi possível iniciar captura para specialist-${specialist_type}"
        return 1
    fi

    # Adicionar plan_id ao filtro se fornecido
    if [ -n "$PLAN_ID" ]; then
        filter_pattern="$filter_pattern|$PLAN_ID"
    fi

    # Get list of running pods for this specialist (similar to consensus-engine)
    local pods=($(kubectl get pods -n "$NAMESPACE_SPECIALISTS" -l app.kubernetes.io/name=specialist-${specialist_type} --field-selector=status.phase=Running -o jsonpath='{.items[*].metadata.name}' 2>/dev/null))

    # Fallback to alternative label if no pods found
    if [ ${#pods[@]} -eq 0 ]; then
        log_warning "Nenhum pod encontrado com label app.kubernetes.io/name=specialist-${specialist_type}, tentando app=specialist-${specialist_type}..."
        pods=($(kubectl get pods -n "$NAMESPACE_SPECIALISTS" -l app=specialist-${specialist_type} --field-selector=status.phase=Running -o jsonpath='{.items[*].metadata.name}' 2>/dev/null))
    fi

    if [ ${#pods[@]} -eq 0 ]; then
        log_error "Nenhum pod running encontrado para specialist-${specialist_type}"
        return 1
    fi

    log_info "Encontrados ${#pods[@]} pod(s) do specialist-${specialist_type}: ${pods[*]}"

    # Create combined log file
    local combined_log="$LOG_DIR/specialist-${specialist_type}-combined-debug.log"
    touch "$combined_log"

    # Capture logs from each pod individually
    for pod in "${pods[@]}"; do
        local log_file="$LOG_DIR/specialist-${specialist_type}-${pod}-debug.log"

        # Captura em background com tee para arquivo individual, arquivo combinado e stdout
        (
            kubectl logs -f "$pod" -n "$NAMESPACE_SPECIALISTS" --tail=100 2>&1 | \
            grep --line-buffered -E "$filter_pattern" | \
            tee -a "$log_file" | \
            tee -a "$combined_log" | \
            while IFS= read -r line; do
                # Detectar erros e adicionar coloração
                if echo "$line" | grep -qi "error"; then
                    echo -e "${GREEN}[SPECIALIST-${specialist_type^^}:${pod}]${NC} ${YELLOW}[ERROR]${NC} $line"
                elif echo "$line" | grep -qi "completed successfully"; then
                    echo -e "${GREEN}[SPECIALIST-${specialist_type^^}:${pod}]${NC} ${GREEN}[SUCCESS]${NC} $line"
                else
                    echo -e "${GREEN}[SPECIALIST-${specialist_type^^}:${pod}]${NC} $line"
                fi
            done
        ) &

        CAPTURE_PIDS+=($!)
        log_success "Captura do specialist-${specialist_type} pod $pod iniciada (PID: ${CAPTURE_PIDS[-1]})"
    done

    log_info "Arquivo combinado sendo continuamente populado: $combined_log"
}

start_all_captures() {
    log_info "Iniciando captura de logs de todos os componentes..."
    print_separator

    # Capturar consensus-engine
    capture_consensus_logs
    sleep 1

    # Capturar specialists
    for specialist in "${SPECIALISTS[@]}"; do
        capture_specialist_logs "$specialist"
        sleep 1
    done

    print_separator
    log_success "Todas as capturas iniciadas! PIDs: ${CAPTURE_PIDS[*]}"
    log_info "Logs sendo salvos em: $LOG_DIR"
    log_info "Captura rodará por ${DURATION}s ($(($DURATION / 60)) minutos)"
    print_separator
}

monitor_captures() {
    local elapsed=0
    local check_interval=15 # Verificar a cada 15 segundos

    log_info "Monitorando capturas... (Ctrl+C para parar antes do tempo)"

    while [ $elapsed -lt $DURATION ]; do
        sleep $check_interval
        elapsed=$((elapsed + check_interval))

        # Verificar se processos ainda estão rodando
        local running_count=0
        for pid in "${CAPTURE_PIDS[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                ((running_count++))
            fi
        done

        local progress=$((elapsed * 100 / DURATION))
        log_info "Progresso: ${progress}% (${elapsed}s / ${DURATION}s) - Processos ativos: $running_count/${#CAPTURE_PIDS[@]}"

        # Se todos os processos morreram, encerrar
        if [ $running_count -eq 0 ]; then
            log_warning "Todos os processos de captura foram encerrados inesperadamente"
            break
        fi
    done

    log_success "Tempo de captura completo!"
}

stop_all_captures() {
    log_info "Encerrando processos de captura..."

    for pid in "${CAPTURE_PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            log_info "Encerrando processo PID: $pid"
            kill -TERM "$pid" 2>/dev/null || true
        fi
    done

    # Aguardar um pouco para processos encerrarem gracefully
    sleep 2

    # Force kill se necessário
    for pid in "${CAPTURE_PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            log_warning "Force killing processo PID: $pid"
            kill -9 "$pid" 2>/dev/null || true
        fi
    done

    log_success "Todos os processos de captura foram encerrados"
}

generate_summary() {
    log_info "Gerando resumo da captura..."
    print_separator

    echo ""
    echo -e "${CYAN}RESUMO DA SESSÃO DE CAPTURA${NC}"
    print_separator

    echo ""
    echo "Session ID: $SESSION_ID"
    echo "Diretório: $LOG_DIR"
    echo "Duração: ${DURATION}s ($(($DURATION / 60)) minutos)"
    echo ""

    echo "Arquivos de log capturados:"
    echo ""

    local total_lines=0
    for log_file in "$LOG_DIR"/*.log; do
        if [ -f "$log_file" ]; then
            local filename=$(basename "$log_file")
            local line_count=$(wc -l < "$log_file" 2>/dev/null || echo 0)
            local file_size=$(du -h "$log_file" | cut -f1)
            total_lines=$((total_lines + line_count))

            printf "  %-40s %10s linhas    %8s\n" "$filename" "$line_count" "$file_size"

            # Detectar erros no arquivo
            local error_count=$(grep -ci "error\|typeerror" "$log_file" 2>/dev/null || echo 0)
            if [ "$error_count" -gt 0 ]; then
                echo -e "    ${RED}→ $error_count erros detectados!${NC}"
            fi
        fi
    done

    echo ""
    print_separator
    echo "Total de linhas capturadas: $total_lines"
    print_separator
    echo ""
}

suggest_next_steps() {
    print_separator
    echo -e "${CYAN}PRÓXIMOS PASSOS${NC}"
    print_separator

    echo ""
    echo "1. Analisar logs capturados:"
    echo "   cd $LOG_DIR"
    echo "   ls -lh"
    echo ""
    echo "2. Procurar por TypeErrors:"
    echo "   grep -i \"typeerror\" $LOG_DIR/*.log"
    echo ""
    echo "3. Procurar por evaluated_at:"
    echo "   grep -i \"evaluated_at\" $LOG_DIR/*.log"
    echo ""
    echo "4. Correlacionar por plan_id (exemplo):"
    echo "   grep \"<plan_id>\" $LOG_DIR/*.log"
    echo ""
    echo "5. Preencher análise em:"
    echo "   vim /jimy/Neural-Hive-Mind/ANALISE_DEBUG_GRPC_TYPEERROR.md"
    echo ""
    echo "6. Copiar logs relevantes para o arquivo de análise"
    echo ""

    print_separator
}

cleanup() {
    log_info "Executando limpeza..."
    stop_all_captures
    generate_summary
    suggest_next_steps
}

trap_handler() {
    echo ""
    log_warning "Captura interrompida pelo usuário (Ctrl+C)"
    cleanup
    exit 130
}

show_usage() {
    cat <<EOF
Uso: $0 [OPÇÕES]

Script para captura automatizada de logs gRPC para análise de TypeError.

OPÇÕES:
    -d, --duration SECONDS          Duração da captura em segundos (padrão: 300)
    -p, --plan-id ID                Filtrar logs por plan_id específico
    -n, --namespace-specialists NS  Namespace dos specialists (padrão: neural-hive)
    -c, --namespace-consensus NS    Namespace do consensus-engine (padrão: neural-hive)
    --consensus-filter PATTERN      Padrão regex customizado para filtrar logs do consensus-engine
                                    (padrão: "EvaluatePlan|TypeError|evaluated_at|gRPC channel|Invocando especialistas")
    --specialist-filter PATTERN     Padrão regex customizado para filtrar logs dos specialists
                                    (padrão: "EvaluatePlan|evaluated_at|processing_time_ms|Received EvaluatePlan|completed successfully")
    -h, --help                      Mostrar esta mensagem de ajuda

EXEMPLOS:
    # Captura padrão de 5 minutos
    $0

    # Captura de 10 minutos
    $0 --duration 600

    # Captura filtrando por plan_id específico
    $0 --plan-id "plan-12345-abcde"

    # Captura com namespace customizado
    $0 --namespace-specialists my-namespace

    # Captura com filtro customizado para consensus
    $0 --consensus-filter "TypeError|GRPC|error"

    # Captura com múltiplas opções
    $0 --duration 600 --plan-id "plan-abc" --consensus-filter "TypeError|evaluated_at"

VARIÁVEIS DE AMBIENTE:
    CONSENSUS_FILTER      Padrão de filtro para logs do consensus-engine
    SPECIALIST_FILTER     Padrão de filtro para logs dos specialists
    NAMESPACE_SPECIALISTS Namespace dos specialists
    NAMESPACE_CONSENSUS   Namespace do consensus-engine
    DURATION              Duração da captura em segundos

EOF
}

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -d|--duration)
                DURATION="$2"
                shift 2
                ;;
            -p|--plan-id)
                PLAN_ID="$2"
                shift 2
                ;;
            -n|--namespace-specialists)
                NAMESPACE_SPECIALISTS="$2"
                shift 2
                ;;
            -c|--namespace-consensus)
                NAMESPACE_CONSENSUS="$2"
                shift 2
                ;;
            --consensus-filter)
                CONSENSUS_FILTER="$2"
                shift 2
                ;;
            --specialist-filter)
                SPECIALIST_FILTER="$2"
                shift 2
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
}

main() {
    # Parse argumentos
    parse_arguments "$@"

    # Banner
    print_banner

    # Setup trap para Ctrl+C
    trap trap_handler SIGINT SIGTERM

    # Setup diretório de logs
    setup_log_directory

    # Criar README da sessão
    create_session_readme

    # Iniciar capturas
    start_all_captures

    # Monitorar capturas
    monitor_captures

    # Cleanup e resumo
    cleanup

    log_success "Captura de logs concluída com sucesso!"
    exit 0
}

# Executar main
main "$@"
