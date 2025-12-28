#!/usr/bin/env bash
# Biblioteca de Métricas para Observabilidade de Builds
# Coleta e envia métricas para Prometheus Pushgateway
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# Configuração
PROMETHEUS_PUSHGATEWAY_URL="${PROMETHEUS_PUSHGATEWAY_URL:-http://prometheus-pushgateway.observability.svc.cluster.local:9091}"
METRICS_JOB_NAME="${METRICS_JOB_NAME:-neural_hive_builds}"
METRICS_INSTANCE="${METRICS_INSTANCE:-${HOSTNAME:-ci}}"

# Normalizar labels para formato Prometheus: key="value",key2="value2"
# Entrada: service=gateway-intencoes,success=true
# Saída: service="gateway-intencoes",success="true"
normalize_labels_for_prometheus() {
    local raw_labels="$1"
    local normalized=""

    # Dividir por vírgula e processar cada par key=value
    IFS=',' read -ra label_pairs <<< "$raw_labels"
    for pair in "${label_pairs[@]}"; do
        [[ -z "$pair" ]] && continue

        # Separar key e value
        local key="${pair%%=*}"
        local value="${pair#*=}"

        # Escapar caracteres especiais no value (backslash, newline, aspas)
        value="${value//\\/\\\\}"
        value="${value//$'\n'/\\n}"
        value="${value//\"/\\\"}"

        # Adicionar ao resultado com aspas em volta do valor
        if [[ -n "$normalized" ]]; then
            normalized="${normalized},${key}=\"${value}\""
        else
            normalized="${key}=\"${value}\""
        fi
    done

    echo "$normalized"
}

# Agregar e enviar métricas para Prometheus Pushgateway
push_build_metrics() {
    local metrics_dir="${1:-/tmp}"
    local aggregated_metrics="/tmp/aggregated-build-metrics-$$.prom"

    log_info "Agregando métricas de build de ${metrics_dir}..."

    # Limpar arquivo anterior
    > "$aggregated_metrics"

    # Verificar se há arquivos de métricas
    local metrics_files=("$metrics_dir"/build-metrics-*.json)
    if [[ ! -e "${metrics_files[0]}" ]]; then
        log_warning "Nenhum arquivo de métricas encontrado em ${metrics_dir}"
        return 0
    fi

    # Converter métricas JSON para formato Prometheus
    for metrics_file in "$metrics_dir"/build-metrics-*.json; do
        [[ -f "$metrics_file" ]] || continue

        log_debug "Processando ${metrics_file}..."

        while IFS= read -r line; do
            [[ -z "$line" ]] && continue

            local name value labels timestamp
            name=$(echo "$line" | jq -r '.name // empty' 2>/dev/null)
            value=$(echo "$line" | jq -r '.value // empty' 2>/dev/null)
            labels=$(echo "$line" | jq -r '.labels // empty' 2>/dev/null)
            timestamp=$(echo "$line" | jq -r '.timestamp // empty' 2>/dev/null)

            [[ -z "$name" || -z "$value" ]] && continue

            # Validar e normalizar labels para formato Prometheus
            # Labels já devem vir no formato key="value",key2="value2"
            # Se não, aplicar normalização de segurança
            if [[ -n "$labels" ]]; then
                local normalized_labels="$labels"
                # Verificar se labels já estão no formato correto (contém aspas)
                if [[ ! "$labels" =~ \" ]]; then
                    # Labels não têm aspas, precisam ser normalizadas
                    normalized_labels=$(normalize_labels_for_prometheus "$labels")
                fi
                echo "${name}{${normalized_labels}} ${value}" >> "$aggregated_metrics"
            else
                echo "${name} ${value}" >> "$aggregated_metrics"
            fi
        done < "$metrics_file"
    done

    # Verificar se há métricas para enviar
    if [[ ! -s "$aggregated_metrics" ]]; then
        log_warning "Nenhuma métrica para enviar"
        rm -f "$aggregated_metrics"
        return 0
    fi

    local metrics_count
    metrics_count=$(wc -l < "$aggregated_metrics")
    log_info "Total de métricas agregadas: ${metrics_count}"

    # Tentar enviar para Pushgateway
    if push_to_pushgateway "$aggregated_metrics"; then
        log_success "Métricas enviadas para Prometheus Pushgateway"
        cleanup_metrics_files "$metrics_dir"
    else
        log_warning "Falha ao enviar métricas para Pushgateway"
        # Manter arquivos para retry posterior
    fi

    rm -f "$aggregated_metrics"
}

# Enviar métricas para Pushgateway
push_to_pushgateway() {
    local metrics_file="$1"
    local pushgateway_url="${PROMETHEUS_PUSHGATEWAY_URL}/metrics/job/${METRICS_JOB_NAME}/instance/${METRICS_INSTANCE}"

    log_info "Enviando métricas para ${pushgateway_url}..."

    # Verificar conectividade
    if ! curl -sf "${PROMETHEUS_PUSHGATEWAY_URL}/-/healthy" >/dev/null 2>&1; then
        log_warning "Pushgateway não está acessível em ${PROMETHEUS_PUSHGATEWAY_URL}"
        return 1
    fi

    # Enviar métricas
    if curl -sf --data-binary @"$metrics_file" "$pushgateway_url"; then
        return 0
    else
        log_error "Falha ao enviar métricas via curl"
        return 1
    fi
}

# Limpar arquivos de métricas após envio bem-sucedido
cleanup_metrics_files() {
    local metrics_dir="$1"

    log_debug "Limpando arquivos de métricas em ${metrics_dir}..."
    rm -f "$metrics_dir"/build-metrics-*.json
}

# Criar métricas de resumo do build
create_build_summary_metrics() {
    local metrics_dir="${1:-/tmp}"
    local total_builds=0
    local successful_builds=0
    local failed_builds=0
    local total_duration=0
    local fallback_count=0

    for metrics_file in "$metrics_dir"/build-metrics-*.json; do
        [[ -f "$metrics_file" ]] || continue

        while IFS= read -r line; do
            [[ -z "$line" ]] && continue

            local name value
            name=$(echo "$line" | jq -r '.name // empty' 2>/dev/null)
            value=$(echo "$line" | jq -r '.value // empty' 2>/dev/null)

            case "$name" in
                build_success_total)
                    successful_builds=$((successful_builds + value))
                    total_builds=$((total_builds + 1))
                    ;;
                build_failure_total)
                    failed_builds=$((failed_builds + value))
                    total_builds=$((total_builds + 1))
                    ;;
                build_duration_seconds)
                    total_duration=$((total_duration + value))
                    ;;
                build_fallback_total)
                    fallback_count=$((fallback_count + value))
                    ;;
            esac
        done < "$metrics_file"
    done

    # Criar arquivo de resumo
    local summary_file="${metrics_dir}/build-summary.json"
    cat > "$summary_file" << EOF
{
    "total_builds": ${total_builds},
    "successful_builds": ${successful_builds},
    "failed_builds": ${failed_builds},
    "total_duration_seconds": ${total_duration},
    "fallback_count": ${fallback_count},
    "success_rate": $(awk "BEGIN {if($total_builds>0) printf \"%.2f\", $successful_builds/$total_builds; else print 0}"),
    "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF

    log_info "Resumo de build criado em ${summary_file}"
    cat "$summary_file"
}

# Função para registrar início de build (para métricas de histograma)
start_build_timer() {
    local service="$1"
    local timer_file="/tmp/build-timer-${service}.txt"
    date +%s > "$timer_file"
}

# Função para registrar fim de build
stop_build_timer() {
    local service="$1"
    local success="$2"
    local timer_file="/tmp/build-timer-${service}.txt"

    if [[ -f "$timer_file" ]]; then
        local start_time
        start_time=$(cat "$timer_file")
        local end_time
        end_time=$(date +%s)
        local duration=$((end_time - start_time))

        # Exportar para coleta posterior
        echo "$duration" > "/tmp/build-duration-${service}.txt"
        rm -f "$timer_file"
    fi
}

# Exportar funções
export -f normalize_labels_for_prometheus
export -f push_build_metrics push_to_pushgateway cleanup_metrics_files
export -f create_build_summary_metrics
export -f start_build_timer stop_build_timer
