#!/usr/bin/env bash
# Script de Build Inteligente com Self-Healing
# Implementa retry com backoff exponencial e fallback para versões anteriores
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../lib/docker.sh"

# Variáveis de configuração
SMART_BUILD_MAX_RETRIES="${SMART_BUILD_MAX_RETRIES:-3}"
SMART_BUILD_INITIAL_DELAY="${SMART_BUILD_INITIAL_DELAY:-2}"
METRICS_DIR="${METRICS_DIR:-/tmp}"

# Função principal de build inteligente
smart_build_service() {
    local service="$1"
    local version="$2"
    local no_cache="${3:-}"
    local max_retries="${SMART_BUILD_MAX_RETRIES}"

    local start_time
    start_time=$(date +%s)
    local attempt=1
    local build_success=false
    local used_fallback=false

    log_info "Smart Build iniciado para ${service}:${version}"

    # Tentar build com retry e backoff exponencial
    while [[ $attempt -le $max_retries ]]; do
        log_info "Tentativa ${attempt}/${max_retries} para ${service}"

        if build_service "$service" "$version" "$no_cache"; then
            build_success=true
            log_success "Build bem-sucedido para ${service} na tentativa ${attempt}"
            break
        fi

        log_warning "Build falhou (tentativa ${attempt}/${max_retries})"

        if [[ $attempt -lt $max_retries ]]; then
            local delay=$((SMART_BUILD_INITIAL_DELAY ** attempt))
            log_info "Aguardando ${delay}s antes da próxima tentativa..."
            sleep "$delay"
        fi

        attempt=$((attempt + 1))
    done

    # Fallback: usar versão anterior do registry
    if [[ "$build_success" == "false" ]]; then
        log_warning "Build falhou após ${max_retries} tentativas, tentando fallback..."

        if fallback_to_previous_version "$service" "$version"; then
            log_success "Fallback bem-sucedido para ${service}"
            used_fallback=true
            collect_metric "build_fallback_total" "1" "service=${service}"
        else
            log_error "Fallback também falhou para ${service}"
            collect_metric "build_failure_total" "1" "service=${service},reason=all_attempts_failed"
            return 1
        fi
    fi

    # Coletar métricas
    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))

    collect_metric "build_duration_seconds" "$duration" "service=${service},success=${build_success}"
    collect_metric "build_attempts_total" "$attempt" "service=${service}"

    if [[ "$build_success" == "true" ]]; then
        collect_metric "build_success_total" "1" "service=${service}"
    fi

    # Coletar métricas adicionais
    collect_docker_cache_metrics "$service"
    collect_image_size_metrics "$service" "$version"

    if [[ "$used_fallback" == "true" ]]; then
        log_warning "⚠️ MODO DEGRADADO: ${service} usando imagem de fallback"
    fi

    return 0
}

# Função de fallback para versão anterior
fallback_to_previous_version() {
    local service="$1"
    local version="$2"

    log_info "Tentando recuperar versão anterior de ${service}..."

    # Lista de registries para tentar (em ordem de preferência)
    local registries=(
        "${REGISTRY_PRIMARY:-registry.neural-hive.local:5000}"
        "${REGISTRY_SECONDARY:-37.60.241.150:30500}"
    )

    for registry in "${registries[@]}"; do
        local registry_image="${registry}/neural-hive-mind/${service}:latest"

        log_info "Tentando pull de ${registry_image}..."

        # Verificar se o registry está disponível
        if ! curl -sf "http://${registry}/v2/" >/dev/null 2>&1; then
            log_warning "Registry ${registry} indisponível, tentando próximo..."
            continue
        fi

        # Tentar pull da imagem
        if docker pull "$registry_image" 2>/dev/null; then
            # Re-tag como versão atual e latest
            docker tag "$registry_image" "neural-hive-mind/${service}:${version}"
            docker tag "$registry_image" "neural-hive-mind/${service}:latest"
            log_success "Imagem recuperada de ${registry}"
            return 0
        fi

        log_warning "Pull falhou de ${registry}, tentando próximo..."
    done

    # Fallback para ECR se disponível
    if [[ -n "${AWS_REGION:-}" ]]; then
        log_info "Tentando fallback para ECR..."

        local account_id
        account_id=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")

        if [[ -n "$account_id" ]]; then
            local ecr_image="${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com/neural-hive-mind/${service}:latest"

            # Login no ECR
            if aws ecr get-login-password --region "${AWS_REGION}" 2>/dev/null | \
               docker login --username AWS --password-stdin "${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com" 2>/dev/null; then

                if docker pull "$ecr_image" 2>/dev/null; then
                    docker tag "$ecr_image" "neural-hive-mind/${service}:${version}"
                    docker tag "$ecr_image" "neural-hive-mind/${service}:latest"
                    log_success "Imagem recuperada do ECR"
                    return 0
                fi
            fi
        fi
    fi

    log_error "Não foi possível recuperar versão anterior de ${service}"
    return 1
}

# Normalizar labels para formato Prometheus: key="value",key2="value2"
# Entrada: service=gateway-intencoes,success=true
# Saída: service="gateway-intencoes",success="true"
normalize_prometheus_labels() {
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

# Coletar métricas em formato JSON
collect_metric() {
    local metric_name="$1"
    local value="$2"
    local labels="$3"

    local metrics_file="${METRICS_DIR}/build-metrics-${SERVICE:-unknown}.json"
    local timestamp
    timestamp=$(date +%s)

    # Criar diretório se não existir
    mkdir -p "$(dirname "$metrics_file")"

    # Normalizar labels para formato Prometheus
    local normalized_labels
    normalized_labels=$(normalize_prometheus_labels "$labels")

    # Adicionar métrica ao arquivo JSON com labels normalizados
    printf '{"name":"%s","value":"%s","labels":"%s","timestamp":"%s"}\n' \
        "$metric_name" "$value" "$normalized_labels" "$timestamp" >> "$metrics_file"
}

# Coletar métricas de cache do Docker
collect_docker_cache_metrics() {
    local service="$1"
    local log_file="${DOCKER_BUILD_LOG_FILE:-}"

    if [[ -f "$log_file" ]]; then
        local cache_hits=0
        local total_steps=1

        cache_hits=$(grep -c "CACHED" "$log_file" 2>/dev/null || echo 0)
        total_steps=$(grep -c -E "^#[0-9]+ " "$log_file" 2>/dev/null || echo 1)

        if [[ $total_steps -gt 0 ]]; then
            local cache_ratio
            cache_ratio=$(awk "BEGIN {printf \"%.2f\", $cache_hits / $total_steps}")
            collect_metric "build_cache_hit_ratio" "$cache_ratio" "service=${service}"
        fi
    fi
}

# Coletar métricas de tamanho da imagem
collect_image_size_metrics() {
    local service="$1"
    local version="$2"

    local image="neural-hive-mind/${service}:${version}"

    if docker image inspect "$image" >/dev/null 2>&1; then
        local size
        size=$(docker image inspect "$image" --format='{{.Size}}')
        collect_metric "build_image_size_bytes" "$size" "service=${service},version=${version}"
    fi
}

# Build paralelo com smart build
build_services_parallel_smart() {
    local version="$1"
    local parallel_jobs="$2"
    shift 2

    local args=("$@")
    local last_index=$((${#args[@]}-1))
    local no_cache="${args[$last_index]}"
    unset 'args[$last_index]'
    local services=("${args[@]}")

    local semaphore_dir="/tmp/smart-build-semaphore-$$"
    mkdir -p "$semaphore_dir"

    log_info "Iniciando smart build paralelo de ${#services[@]} serviços (max ${parallel_jobs} jobs)"

    for service in "${services[@]}"; do
        # Controle de concorrência
        while [[ $(jobs -r | wc -l) -ge $parallel_jobs ]]; do
            sleep 0.5
        done

        (
            export SERVICE="$service"
            export METRICS_DIR="${METRICS_DIR}"

            if smart_build_service "$service" "$version" "$no_cache"; then
                echo "SUCCESS:${service}" > "${semaphore_dir}/${service}.status"
            else
                echo "FAILED:${service}" > "${semaphore_dir}/${service}.status"
            fi
        ) &
    done

    wait

    # Verificar resultados
    local failed=0
    local success_count=0
    local fallback_count=0

    for status_file in "${semaphore_dir}"/*.status; do
        [[ -e "$status_file" ]] || continue
        if grep -q "FAILED" "$status_file"; then
            log_error "$(cat "$status_file")"
            failed=1
        else
            log_success "$(cat "$status_file")"
            success_count=$((success_count + 1))
        fi
    done

    rm -rf "$semaphore_dir"

    log_info "Resultado: ${success_count}/${#services[@]} builds bem-sucedidos"

    return $failed
}

# Exportar funções
export -f smart_build_service fallback_to_previous_version
export -f normalize_prometheus_labels collect_metric collect_docker_cache_metrics collect_image_size_metrics
export -f build_services_parallel_smart
