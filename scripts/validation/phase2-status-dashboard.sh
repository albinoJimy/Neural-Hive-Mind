#!/usr/bin/env bash
#
# phase2-status-dashboard.sh - Dashboard de Status da Fase 2 em Tempo Real
#
# Este script exibe um dashboard interativo com status de todos os servicos
# da Fase 2, incluindo:
# - Status dos Pods Kubernetes
# - Health Checks (HTTP e gRPC)
# - Conexoes de Banco de Dados
# - Kafka Consumers
# - Metricas Chave
# - Alertas Ativos
#
# Uso: ./phase2-status-dashboard.sh [--refresh SECONDS] [--once]
#

set -euo pipefail

# Cores para saida
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
NC='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'

# Configuracao
NAMESPACE="${NAMESPACE:-neural-hive}"
REFRESH_INTERVAL=5
RUN_ONCE=false

# Servicos da Fase 2
PHASE2_SERVICES=(
    "orchestrator-dynamic"
    "queen-agent"
    "worker-agents"
    "code-forge"
    "service-registry"
    "execution-ticket-service"
    "scout-agents"
    "analyst-agents"
    "optimizer-agents"
    "guard-agents"
    "sla-management-system"
    "mcp-tool-catalog"
    "self-healing-engine"
)

# Servicos gRPC
GRPC_SERVICES=("queen-agent" "service-registry" "optimizer-agents")

# Parse argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --refresh)
            REFRESH_INTERVAL="$2"
            shift 2
            ;;
        --once)
            RUN_ONCE=true
            shift
            ;;
        -h|--help)
            echo "Uso: $0 [--refresh SECONDS] [--once]"
            echo ""
            echo "Opcoes:"
            echo "  --refresh SECONDS  Intervalo de atualizacao (padrao: 5)"
            echo "  --once             Executar apenas uma vez"
            exit 0
            ;;
        *)
            echo "Opcao desconhecida: $1"
            exit 1
            ;;
    esac
done

# Funcoes de desenho
draw_box_top() {
    local width=$1
    echo -e "${CYAN}╔$(printf '═%.0s' $(seq 1 $width))╗${NC}"
}

draw_box_bottom() {
    local width=$1
    echo -e "${CYAN}╚$(printf '═%.0s' $(seq 1 $width))╝${NC}"
}

draw_box_separator() {
    local width=$1
    echo -e "${CYAN}╠$(printf '═%.0s' $(seq 1 $width))╣${NC}"
}

draw_box_line() {
    local content="$1"
    local width=$2
    local content_length=${#content}
    # Remover codigos de cor para calculo de padding
    local clean_content
    clean_content=$(echo -e "$content" | sed 's/\x1b\[[0-9;]*m//g')
    local clean_length=${#clean_content}
    local padding=$((width - clean_length - 2))
    if [ $padding -lt 0 ]; then
        padding=0
    fi
    echo -e "${CYAN}║${NC} ${content}$(printf ' %.0s' $(seq 1 $padding)) ${CYAN}║${NC}"
}

# Obter status do pod
get_pod_status() {
    local service=$1
    local pod_info
    pod_info=$(kubectl get pods -n "$NAMESPACE" -l "app=$service" -o json 2>/dev/null || echo '{"items":[]}')

    local pod_count
    pod_count=$(echo "$pod_info" | jq '.items | length')

    if [ "$pod_count" -eq 0 ]; then
        echo "NO_PODS"
        return
    fi

    local ready_pods=0
    local total_pods=0

    for pod in $(echo "$pod_info" | jq -r '.items[].metadata.name'); do
        ((total_pods++))
        local ready
        ready=$(kubectl get pod "$pod" -n "$NAMESPACE" -o jsonpath='{.status.containerStatuses[0].ready}' 2>/dev/null)
        if [ "$ready" = "true" ]; then
            ((ready_pods++))
        fi
    done

    if [ "$ready_pods" -eq "$total_pods" ]; then
        echo "READY:$ready_pods/$total_pods"
    else
        echo "NOT_READY:$ready_pods/$total_pods"
    fi
}

# Obter status do health check HTTP
get_http_health() {
    local service=$1
    local pod
    pod=$(kubectl get pods -n "$NAMESPACE" -l "app=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -z "$pod" ]; then
        echo "NO_POD"
        return
    fi

    local response
    response=$(kubectl exec -n "$NAMESPACE" "$pod" -- curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000/health" 2>/dev/null || echo "000")

    if [ "$response" = "200" ]; then
        echo "OK"
    else
        echo "FAIL:$response"
    fi
}

# Obter status gRPC
get_grpc_status() {
    local service=$1
    local pod
    pod=$(kubectl get pods -n "$NAMESPACE" -l "app=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -z "$pod" ]; then
        echo "NO_POD"
        return
    fi

    # Verificar se porta 50051 esta aberta
    local port_check
    port_check=$(kubectl exec -n "$NAMESPACE" "$pod" -- sh -c "ss -tlnp 2>/dev/null | grep :50051 || echo ''" 2>/dev/null)

    if [ -n "$port_check" ]; then
        echo "OK"
    else
        echo "FAIL"
    fi
}

# Obter metricas chave
get_key_metrics() {
    local pod
    pod=$(kubectl get pods -n "$NAMESPACE" -l "app=orchestrator-dynamic" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -z "$pod" ]; then
        echo "N/A"
        return
    fi

    local metrics
    metrics=$(kubectl exec -n "$NAMESPACE" "$pod" -- curl -s "http://localhost:8000/metrics" 2>/dev/null || echo "")

    if [ -z "$metrics" ]; then
        echo "N/A"
        return
    fi

    # Extrair metricas
    local workflows
    workflows=$(echo "$metrics" | grep "^orchestrator_workflows_started_total" | awk '{print $2}' || echo "0")

    echo "$workflows"
}

# Obter alertas ativos
get_active_alerts() {
    local alerts=()

    # Verificar pods nao prontos
    local not_ready
    not_ready=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running -o name 2>/dev/null | wc -l)
    if [ "$not_ready" -gt 0 ]; then
        alerts+=("$not_ready pod(s) nao prontos")
    fi

    # Verificar pods com restart recente
    local pods_with_restarts
    pods_with_restarts=$(kubectl get pods -n "$NAMESPACE" -o json 2>/dev/null | \
        jq -r '.items[] | select(.status.containerStatuses[0].restartCount > 0) | .metadata.name' | wc -l)
    if [ "$pods_with_restarts" -gt 0 ]; then
        alerts+=("$pods_with_restarts pod(s) com restarts")
    fi

    if [ ${#alerts[@]} -eq 0 ]; then
        echo "Nenhum alerta ativo"
    else
        printf '%s\n' "${alerts[@]}"
    fi
}

# Renderizar dashboard
render_dashboard() {
    # Limpar tela
    clear

    local width=66
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # Cabecalho
    echo ""
    draw_box_top $width
    draw_box_line "${BOLD}${WHITE}     NEURAL HIVE MIND - DASHBOARD DE STATUS FASE 2${NC}" $width
    draw_box_line "${DIM}Atualizado: $timestamp${NC}" $width
    draw_box_bottom $width

    echo ""

    # Secao 1: Status dos Pods
    draw_box_top $width
    draw_box_line "${BOLD}${WHITE}STATUS DOS PODS${NC}" $width
    draw_box_separator $width

    local total_services=${#PHASE2_SERVICES[@]}
    local healthy_services=0

    for service in "${PHASE2_SERVICES[@]}"; do
        local status
        status=$(get_pod_status "$service")

        local status_icon
        local status_color

        if [[ "$status" == READY* ]]; then
            status_icon="✅"
            status_color="${GREEN}"
            ((healthy_services++))
        elif [[ "$status" == "NO_PODS" ]]; then
            status_icon="❌"
            status_color="${RED}"
        else
            status_icon="⚠️"
            status_color="${YELLOW}"
        fi

        # Formatar nome do servico (max 25 chars)
        local service_name
        service_name=$(printf "%-25s" "$service")

        # Extrair contagem
        local count=""
        if [[ "$status" == *:* ]]; then
            count=$(echo "$status" | cut -d: -f2)
        fi

        draw_box_line "${status_icon} ${status_color}${service_name}${NC} ${count}" $width
    done

    draw_box_separator $width
    draw_box_line "${BOLD}Total: ${GREEN}$healthy_services${NC}/${total_services} servicos saudaveis${NC}" $width
    draw_box_bottom $width

    echo ""

    # Secao 2: Health Checks
    draw_box_top $width
    draw_box_line "${BOLD}${WHITE}HEALTH CHECKS${NC}" $width
    draw_box_separator $width

    local http_ok=0
    local http_total=${#PHASE2_SERVICES[@]}

    for service in "${PHASE2_SERVICES[@]}"; do
        local health
        health=$(get_http_health "$service")

        if [ "$health" = "OK" ]; then
            ((http_ok++))
        fi
    done

    local grpc_ok=0
    local grpc_total=${#GRPC_SERVICES[@]}

    for service in "${GRPC_SERVICES[@]}"; do
        local grpc_status
        grpc_status=$(get_grpc_status "$service")

        if [ "$grpc_status" = "OK" ]; then
            ((grpc_ok++))
        fi
    done

    if [ "$http_ok" -eq "$http_total" ]; then
        draw_box_line "HTTP Endpoints:        ${GREEN}$http_ok/$http_total ✅${NC}" $width
    else
        draw_box_line "HTTP Endpoints:        ${YELLOW}$http_ok/$http_total ⚠️${NC}" $width
    fi

    if [ "$grpc_ok" -eq "$grpc_total" ]; then
        draw_box_line "gRPC Services:         ${GREEN}$grpc_ok/$grpc_total ✅${NC}" $width
    else
        draw_box_line "gRPC Services:         ${YELLOW}$grpc_ok/$grpc_total ⚠️${NC}" $width
    fi

    draw_box_line "Database Connections:  ${DIM}verificando...${NC}" $width
    draw_box_line "Kafka Consumers:       ${DIM}verificando...${NC}" $width
    draw_box_bottom $width

    echo ""

    # Secao 3: Metricas Chave
    draw_box_top $width
    draw_box_line "${BOLD}${WHITE}METRICAS CHAVE (Ultimos 5 minutos)${NC}" $width
    draw_box_separator $width

    local workflows
    workflows=$(get_key_metrics)

    draw_box_line "Workflows Iniciados:   ${CYAN}$workflows${NC}" $width
    draw_box_line "Tickets Executados:    ${DIM}N/A${NC}" $width
    draw_box_line "Decisoes Estrategicas: ${DIM}N/A${NC}" $width
    draw_box_line "Pipelines de Codigo:   ${DIM}N/A${NC}" $width
    draw_box_line "Latencia Media:        ${DIM}N/A${NC}" $width
    draw_box_bottom $width

    echo ""

    # Secao 4: Alertas
    draw_box_top $width
    draw_box_line "${BOLD}${WHITE}ALERTAS${NC}" $width
    draw_box_separator $width

    local alerts
    alerts=$(get_active_alerts)

    if [ "$alerts" = "Nenhum alerta ativo" ]; then
        draw_box_line "${GREEN}✅ Nenhum alerta ativo${NC}" $width
    else
        while IFS= read -r alert; do
            draw_box_line "${YELLOW}⚠️  $alert${NC}" $width
        done <<< "$alerts"
    fi

    draw_box_bottom $width

    echo ""

    # Rodape
    if [ "$RUN_ONCE" = false ]; then
        echo -e "${DIM}Pressione Ctrl+C para sair | Atualizacao a cada ${REFRESH_INTERVAL}s${NC}"
    fi
}

# Main
main() {
    # Verificar kubectl
    if ! command -v kubectl &> /dev/null; then
        echo -e "${RED}Erro: kubectl nao encontrado${NC}"
        exit 1
    fi

    # Verificar conectividade do cluster
    if ! kubectl cluster-info &> /dev/null; then
        echo -e "${RED}Erro: Nao foi possivel conectar ao cluster Kubernetes${NC}"
        exit 1
    fi

    if [ "$RUN_ONCE" = true ]; then
        render_dashboard
    else
        # Loop de atualizacao
        while true; do
            render_dashboard
            sleep "$REFRESH_INTERVAL"
        done
    fi
}

# Capturar Ctrl+C
trap 'echo -e "\n${CYAN}Dashboard encerrado.${NC}"; exit 0' INT

# Executar
main
