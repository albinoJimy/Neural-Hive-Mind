#!/bin/bash
set -euo pipefail

# Script para extrair métricas de performance do Prometheus
# Extrai P95 de latência e throughput de componentes chave
#
# Uso:
#   ./extract-performance-metrics.sh [OUTPUT_DIR] [PROMETHEUS_URL] [TIME_RANGE]
#
# Exemplo:
#   ./extract-performance-metrics.sh tests/results http://localhost:9090 5m

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${1:-${SCRIPT_DIR}/../tests/results}"
PROMETHEUS_URL="${2:-http://localhost:9090}"
TIME_RANGE="${3:-5m}"

# Criar diretório de saída se não existir
mkdir -p "$OUTPUT_DIR"

# Arquivo de saída
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_FILE="${OUTPUT_DIR}/performance-metrics-${TIMESTAMP}.txt"

echo "Extraindo métricas de performance do Prometheus..."
echo "Prometheus URL: $PROMETHEUS_URL"
echo "Output: $OUTPUT_FILE"
echo ""

# Função para verificar conectividade com Prometheus
check_prometheus() {
    if ! curl -s "${PROMETHEUS_URL}/api/v1/query?query=up" &>/dev/null; then
        echo "ERRO: Não foi possível conectar ao Prometheus em ${PROMETHEUS_URL}"
        echo "Verifique se o Prometheus está rodando e acessível"
        return 1
    fi
    return 0
}

# Função para consultar Prometheus
query_prometheus() {
    local query=$1
    local label=$2

    local response=$(curl -s "${PROMETHEUS_URL}/api/v1/query?query=${query}" 2>/dev/null)
    local status=$(echo "$response" | jq -r '.status' 2>/dev/null)

    if [ "$status" != "success" ]; then
        echo "${label}: N/A (query falhou)"
        return 1
    fi

    local result=$(echo "$response" | jq -r '.data.result[0].value[1]' 2>/dev/null)

    if [ -z "$result" ] || [ "$result" == "null" ]; then
        echo "${label}: N/A (métrica não encontrada)"
        return 1
    fi

    echo "${label}: ${result}"
    return 0
}

# Função para consultar métrica com histogram
query_histogram_p95() {
    local metric_base=$1
    local label=$2

    # Calcular P95 usando histogram_quantile
    local query="histogram_quantile(0.95, rate(${metric_base}_bucket[${TIME_RANGE}]))"
    local encoded_query=$(echo -n "$query" | jq -sRr @uri)
    local response=$(curl -s "${PROMETHEUS_URL}/api/v1/query?query=${encoded_query}" 2>/dev/null)
    local status=$(echo "$response" | jq -r '.status' 2>/dev/null)

    if [ "$status" != "success" ]; then
        echo "${label}: N/A (query falhou)"
        return 1
    fi

    local result=$(echo "$response" | jq -r '.data.result[0].value[1]' 2>/dev/null)

    if [ -z "$result" ] || [ "$result" == "null" ]; then
        echo "${label}: N/A (métrica não encontrada - pode não ter dados no intervalo ${TIME_RANGE})"
        return 1
    fi

    # Converter para milissegundos se for latência em segundos
    result=$(echo "$result * 1000" | bc 2>/dev/null || echo "$result")
    echo "${label}: ${result}ms"
    return 0
}

# Verificar conectividade com Prometheus
if ! check_prometheus; then
    echo "AVISO: Prometheus não está acessível. Gerando relatório com dados vazios."
    echo ""
fi

# Início do relatório
{
    echo "=========================================="
    echo "Neural Hive-Mind - Performance Metrics"
    echo "=========================================="
    echo ""
    echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    echo "Prometheus: $PROMETHEUS_URL"
    echo "Time Range: $TIME_RANGE"
    echo ""

    echo "=========================================="
    echo "Latências P95 (últimos 5 minutos)"
    echo "=========================================="
    echo ""

    # Latência de geração de planos
    query_histogram_p95 "neural_hive_plan_generation_duration_seconds" "Plan Generation (Intent → Plan)"

    # Latência de avaliação dos specialists
    query_histogram_p95 "neural_hive_specialist_evaluation_duration_seconds" "Specialist Evaluation"

    # Latência de consenso
    query_histogram_p95 "neural_hive_consensus_duration_seconds" "Consensus Decision"

    # Latência de escrita no ledger
    query_histogram_p95 "neural_hive_ledger_write_duration_seconds" "Ledger Write"

    echo ""
    echo "=========================================="
    echo "Throughput (intervalo: ${TIME_RANGE})"
    echo "=========================================="
    echo ""

    # Taxa de geração de planos
    local plans_query="rate(neural_hive_plans_generated_total[${TIME_RANGE}])*60"
    local plans_response=$(curl -s "${PROMETHEUS_URL}/api/v1/query?query=$(echo -n "$plans_query" | jq -sRr @uri)" 2>/dev/null)
    local plans_rate=$(echo "$plans_response" | jq -r '.data.result[0].value[1]' 2>/dev/null || echo "N/A")
    if [ "$plans_rate" == "null" ] || [ -z "$plans_rate" ]; then
        echo "Plans Generated: N/A (métrica não encontrada)"
    else
        echo "Plans Generated: ${plans_rate} plans/min"
    fi

    # Taxa de avaliações de specialists
    local evals_query="rate(neural_hive_specialist_evaluations_total[${TIME_RANGE}])*60"
    local evals_response=$(curl -s "${PROMETHEUS_URL}/api/v1/query?query=$(echo -n "$evals_query" | jq -sRr @uri)" 2>/dev/null)
    local evals_rate=$(echo "$evals_response" | jq -r '.data.result[0].value[1]' 2>/dev/null || echo "N/A")
    if [ "$evals_rate" == "null" ] || [ -z "$evals_rate" ]; then
        echo "Specialist Evaluations: N/A (métrica não encontrada)"
    else
        echo "Specialist Evaluations: ${evals_rate} evaluations/min"
    fi

    # Taxa de decisões de consenso
    local decisions_query="rate(neural_hive_consensus_decisions_total[${TIME_RANGE}])*60"
    local decisions_response=$(curl -s "${PROMETHEUS_URL}/api/v1/query?query=$(echo -n "$decisions_query" | jq -sRr @uri)" 2>/dev/null)
    local decisions_rate=$(echo "$decisions_response" | jq -r '.data.result[0].value[1]' 2>/dev/null || echo "N/A")
    if [ "$decisions_rate" == "null" ] || [ -z "$decisions_rate" ]; then
        echo "Consensus Decisions: N/A (métrica não encontrada)"
    else
        echo "Consensus Decisions: ${decisions_rate} decisions/min"
    fi

    echo ""
    echo "=========================================="
    echo "Taxas de Sucesso (intervalo: ${TIME_RANGE})"
    echo "=========================================="
    echo ""

    # Taxa de sucesso de geração de planos
    local plan_success_query="rate(neural_hive_plans_generated_total{status=\"success\"}[${TIME_RANGE}])/rate(neural_hive_plans_generated_total[${TIME_RANGE}])*100"
    local plan_success_response=$(curl -s "${PROMETHEUS_URL}/api/v1/query?query=$(echo -n "$plan_success_query" | jq -sRr @uri)" 2>/dev/null)
    local plan_success=$(echo "$plan_success_response" | jq -r '.data.result[0].value[1]' 2>/dev/null || echo "N/A")
    if [ "$plan_success" == "null" ] || [ -z "$plan_success" ]; then
        echo "Plan Generation Success Rate: N/A (métrica não encontrada)"
    else
        echo "Plan Generation Success Rate: ${plan_success}%"
    fi

    # Taxa de sucesso de consenso
    local consensus_success_query="rate(neural_hive_consensus_decisions_total{status=\"success\"}[${TIME_RANGE}])/rate(neural_hive_consensus_decisions_total[${TIME_RANGE}])*100"
    local consensus_success_response=$(curl -s "${PROMETHEUS_URL}/api/v1/query?query=$(echo -n "$consensus_success_query" | jq -sRr @uri)" 2>/dev/null)
    local consensus_success=$(echo "$consensus_success_response" | jq -r '.data.result[0].value[1]' 2>/dev/null || echo "N/A")
    if [ "$consensus_success" == "null" ] || [ -z "$consensus_success" ]; then
        echo "Consensus Success Rate: N/A (métrica não encontrada)"
    else
        echo "Consensus Success Rate: ${consensus_success}%"
    fi

    # Disponibilidade dos specialists
    local specialist_up_query='avg(up{job=~"specialist-.*"})*100'
    local specialist_up_response=$(curl -s "${PROMETHEUS_URL}/api/v1/query?query=$(echo -n "$specialist_up_query" | jq -sRr @uri)" 2>/dev/null)
    local specialist_up=$(echo "$specialist_up_response" | jq -r '.data.result[0].value[1]' 2>/dev/null || echo "N/A")
    if [ "$specialist_up" == "null" ] || [ -z "$specialist_up" ]; then
        echo "Specialist Availability: N/A (métrica não encontrada)"
    else
        echo "Specialist Availability: ${specialist_up}%"
    fi

    echo ""
    echo "=========================================="
    echo "Métricas de Recursos"
    echo "=========================================="
    echo ""

    # CPU usage médio dos specialists
    local specialist_cpu_query="avg(rate(container_cpu_usage_seconds_total{namespace=~\"specialist-.*\"}[${TIME_RANGE}]))*100"
    local specialist_cpu_response=$(curl -s "${PROMETHEUS_URL}/api/v1/query?query=$(echo -n "$specialist_cpu_query" | jq -sRr @uri)" 2>/dev/null)
    local specialist_cpu=$(echo "$specialist_cpu_response" | jq -r '.data.result[0].value[1]' 2>/dev/null || echo "N/A")
    if [ "$specialist_cpu" == "null" ] || [ -z "$specialist_cpu" ]; then
        echo "Avg Specialist CPU Usage: N/A (métrica não encontrada)"
    else
        echo "Avg Specialist CPU Usage: ${specialist_cpu}%"
    fi

    # Memória média dos specialists
    local specialist_mem_query='avg(container_memory_working_set_bytes{namespace=~"specialist-.*"})/1024/1024'
    local specialist_mem_response=$(curl -s "${PROMETHEUS_URL}/api/v1/query?query=$(echo -n "$specialist_mem_query" | jq -sRr @uri)" 2>/dev/null)
    local specialist_mem=$(echo "$specialist_mem_response" | jq -r '.data.result[0].value[1]' 2>/dev/null || echo "N/A")
    if [ "$specialist_mem" == "null" ] || [ -z "$specialist_mem" ]; then
        echo "Avg Specialist Memory Usage: N/A (métrica não encontrada)"
    else
        echo "Avg Specialist Memory Usage: ${specialist_mem}MB"
    fi

    echo ""
    echo "=========================================="
    echo "Benchmarks de Referência"
    echo "=========================================="
    echo ""
    echo "Latências esperadas (P95):"
    echo "  - Intent → Plan: < 500ms"
    echo "  - Specialist Evaluation: < 200ms"
    echo "  - Consensus Decision: < 300ms"
    echo "  - Ledger Write: < 100ms"
    echo "  - End-to-End: < 2s"
    echo ""
    echo "Throughput esperado:"
    echo "  - Plans Generated: 10-50 plans/min"
    echo "  - Specialist Evaluations: 50-250 evaluations/min"
    echo "  - Consensus Decisions: 10-50 decisions/min"
    echo ""
    echo "Taxas de sucesso esperadas:"
    echo "  - Plan Generation: > 99%"
    echo "  - Specialist Availability: > 99.9%"
    echo "  - Consensus Success: > 95%"
    echo ""

} > "$OUTPUT_FILE"

# Exibir conteúdo
cat "$OUTPUT_FILE"

echo ""
echo "Relatório salvo em: $OUTPUT_FILE"
