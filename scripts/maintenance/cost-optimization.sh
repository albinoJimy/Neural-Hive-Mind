#!/bin/bash

# cost-optimization.sh
# Script de otimização de custos para o Neural Hive-Mind
# Analisa uso de recursos e implementa otimizações para reduzir custos

set -euo pipefail

# Carregar funções comuns
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../validation/common-validation-functions.sh"

# Configurações padrão
NAMESPACE="${NEURAL_NAMESPACE:-neural-hive-mind}"
DRY_RUN="${DRY_RUN:-true}"
SAVINGS_THRESHOLD="${SAVINGS_THRESHOLD:-10}"  # % mínimo de economia para implementar
CPU_EFFICIENCY_TARGET="${CPU_EFFICIENCY_TARGET:-70}"  # % de utilização ideal
MEMORY_EFFICIENCY_TARGET="${MEMORY_EFFICIENCY_TARGET:-75}"
STORAGE_UTILIZATION_TARGET="${STORAGE_UTILIZATION_TARGET:-80}"

# Função principal
main() {
    local operation="${1:-analyze}"

    log_info "Iniciando otimização de custos do Neural Hive-Mind - Operação: $operation"

    initialize_test_run "cost-optimization" "$(date -u +%Y%m%d_%H%M%S)"

    case "$operation" in
        "analyze")
            analyze_cost_optimization
            ;;
        "recommend")
            generate_recommendations
            ;;
        "optimize")
            implement_optimizations
            ;;
        "report")
            generate_cost_report
            ;;
        *)
            log_error "Operação desconhecida: $operation"
            show_usage
            exit 1
            ;;
    esac

    generate_summary_report

    log_info "Otimização de custos concluída"
}

# Mostrar uso do script
show_usage() {
    cat << EOF
Uso: $0 [OPERAÇÃO]

Operações disponíveis:
  analyze    - Analisar oportunidades de otimização (padrão)
  recommend  - Gerar recomendações detalhadas
  optimize   - Implementar otimizações automaticamente
  report     - Gerar relatório de custos

Variáveis de ambiente:
  NEURAL_NAMESPACE            - Namespace do Neural Hive-Mind (padrão: neural-hive-mind)
  DRY_RUN                    - Executar em modo dry-run (padrão: true)
  SAVINGS_THRESHOLD          - % mínimo de economia para implementar (padrão: 10)
  CPU_EFFICIENCY_TARGET      - % de utilização ideal de CPU (padrão: 70)
  MEMORY_EFFICIENCY_TARGET   - % de utilização ideal de memória (padrão: 75)
  STORAGE_UTILIZATION_TARGET - % de utilização ideal de storage (padrão: 80)

Exemplos:
  $0 analyze
  DRY_RUN=false $0 optimize
  SAVINGS_THRESHOLD=5 $0 recommend
EOF
}

# Analisar oportunidades de otimização
analyze_cost_optimization() {
    log_info "Analisando oportunidades de otimização de custos"

    analyze_compute_costs
    analyze_storage_costs
    analyze_network_costs
    analyze_idle_resources
    analyze_scaling_efficiency

    add_test_result "Cost Analysis" "PASS" "Análise de custos concluída"
}

# Analisar custos de computação
analyze_compute_costs() {
    log_info "Analisando custos de computação"

    local total_savings_cpu=0
    local total_savings_memory=0
    local deployments=$(kubectl get deployments -n "$NAMESPACE" --no-headers | awk '{print $1}')

    for deployment in $deployments; do
        log_info "Analisando deployment: $deployment"

        # Obter replicas e métricas
        local replicas=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}')
        local pods=$(kubectl get pods -n "$NAMESPACE" -l app="$deployment" --no-headers | awk '{print $1}')

        if [ -z "$pods" ]; then
            continue
        fi

        # Calcular uso médio de recursos
        local total_cpu_usage=0
        local total_memory_usage=0
        local pod_count=0
        local total_cpu_request=0
        local total_memory_request=0

        for pod in $pods; do
            # Uso atual
            local cpu_usage=$(kubectl top pod "$pod" -n "$NAMESPACE" --no-headers 2>/dev/null | awk '{print $2}' | sed 's/m$//' || echo "0")
            local memory_usage=$(kubectl top pod "$pod" -n "$NAMESPACE" --no-headers 2>/dev/null | awk '{print $3}' | sed 's/Mi$//' || echo "0")

            # Requests configurados
            local cpu_request=$(kubectl get pod "$pod" -n "$NAMESPACE" -o jsonpath='{.spec.containers[0].resources.requests.cpu}' | sed 's/m$//' || echo "100")
            local memory_request=$(kubectl get pod "$pod" -n "$NAMESPACE" -o jsonpath='{.spec.containers[0].resources.requests.memory}' | sed 's/Mi$//' || echo "128")

            total_cpu_usage=$((total_cpu_usage + cpu_usage))
            total_memory_usage=$((total_memory_usage + memory_usage))
            total_cpu_request=$((total_cpu_request + cpu_request))
            total_memory_request=$((total_memory_request + memory_request))
            ((pod_count++))
        done

        if [ "$pod_count" -gt 0 ]; then
            # Calcular eficiência atual
            local cpu_efficiency=$((total_cpu_usage * 100 / total_cpu_request))
            local memory_efficiency=$((total_memory_usage * 100 / total_memory_request))

            log_info "Deployment $deployment - CPU: ${cpu_efficiency}%, Memory: ${memory_efficiency}%"

            # Calcular potencial de economia
            if [ "$cpu_efficiency" -lt "$CPU_EFFICIENCY_TARGET" ]; then
                local optimal_cpu=$((total_cpu_usage * 100 / CPU_EFFICIENCY_TARGET))
                local cpu_savings=$((total_cpu_request - optimal_cpu))
                total_savings_cpu=$((total_savings_cpu + cpu_savings))

                log_info "Potencial economia CPU em $deployment: ${cpu_savings}m (${total_cpu_request}m -> ${optimal_cpu}m)"
            fi

            if [ "$memory_efficiency" -lt "$MEMORY_EFFICIENCY_TARGET" ]; then
                local optimal_memory=$((total_memory_usage * 100 / MEMORY_EFFICIENCY_TARGET))
                local memory_savings=$((total_memory_request - optimal_memory))
                total_savings_memory=$((total_savings_memory + memory_savings))

                log_info "Potencial economia Memory em $deployment: ${memory_savings}Mi (${total_memory_request}Mi -> ${optimal_memory}Mi)"
            fi

            # Salvar métricas
            echo "deployment_${deployment}_cpu_efficiency:$cpu_efficiency" >> "$METRICS_FILE"
            echo "deployment_${deployment}_memory_efficiency:$memory_efficiency" >> "$METRICS_FILE"
        fi
    done

    log_info "Potencial de economia total - CPU: ${total_savings_cpu}m, Memory: ${total_savings_memory}Mi"
    echo "total_cpu_savings_potential:$total_savings_cpu" >> "$METRICS_FILE"
    echo "total_memory_savings_potential:$total_savings_memory" >> "$METRICS_FILE"
}

# Analisar custos de armazenamento
analyze_storage_costs() {
    log_info "Analisando custos de armazenamento"

    local total_storage_waste=0
    local pvcs=$(kubectl get pvc -A --no-headers)

    while IFS= read -r pvc_line; do
        if [ -z "$pvc_line" ]; then continue; fi

        local namespace=$(echo "$pvc_line" | awk '{print $1}')
        local pvc_name=$(echo "$pvc_line" | awk '{print $2}')
        local pvc_capacity=$(echo "$pvc_line" | awk '{print $4}' | sed 's/Gi$//')

        # Verificar se há métricas de uso disponíveis
        local pod_using_pvc=$(kubectl get pods -n "$namespace" -o yaml 2>/dev/null | grep -B5 -A5 "claimName: $pvc_name" | grep "name:" | awk '{print $2}' | head -1 || echo "")

        if [ -n "$pod_using_pvc" ]; then
            # Estimar uso (simplificado - em produção usaria métricas mais precisas)
            log_info "PVC $namespace/$pvc_name: ${pvc_capacity}Gi (pod: $pod_using_pvc)"

            # Verificar se PVC está sendo subutilizado (necessitaria métricas específicas)
            # Por enquanto, apenas reportar tamanhos grandes
            if [ "$pvc_capacity" -gt 50 ]; then
                log_warn "PVC grande detectado: $namespace/$pvc_name (${pvc_capacity}Gi)"
                echo "large_pvc_${namespace}_${pvc_name}:$pvc_capacity" >> "$METRICS_FILE"
            fi
        fi
    done <<< "$pvcs"

    # Verificar volumes órfãos
    local orphaned_pvs=$(kubectl get pv --no-headers | grep Available | wc -l)
    if [ "$orphaned_pvs" -gt 0 ]; then
        log_warn "$orphaned_pvs volumes órfãos encontrados"
        echo "orphaned_persistent_volumes:$orphaned_pvs" >> "$METRICS_FILE"
    fi

    echo "storage_waste_analysis:completed" >> "$METRICS_FILE"
}

# Analisar custos de rede
analyze_network_costs() {
    log_info "Analisando custos de rede"

    # Verificar LoadBalancers externos (custos adicionais)
    local external_lbs=$(kubectl get services -A --field-selector=spec.type=LoadBalancer --no-headers | wc -l)
    log_info "LoadBalancers externos: $external_lbs"

    # Verificar uso de Ingress vs LoadBalancer
    local ingresses=$(kubectl get ingress -A --no-headers | wc -l)
    log_info "Ingresses configurados: $ingresses"

    if [ "$external_lbs" -gt "$ingresses" ]; then
        local potential_savings=$((external_lbs - ingresses))
        log_warn "Potencial economia: $potential_savings LoadBalancers poderiam ser substituídos por Ingress"
        echo "loadbalancer_optimization_potential:$potential_savings" >> "$METRICS_FILE"
    fi

    # Verificar cross-AZ traffic
    analyze_cross_az_traffic

    echo "external_loadbalancers:$external_lbs" >> "$METRICS_FILE"
    echo "ingress_controllers:$ingresses" >> "$METRICS_FILE"
}

# Analisar tráfego cross-AZ
analyze_cross_az_traffic() {
    log_info "Analisando tráfego cross-AZ"

    # Verificar distribuição de pods por AZ
    local nodes_by_az=$(kubectl get nodes -o custom-columns=NAME:.metadata.name,AZ:.metadata.labels.'topology\.kubernetes\.io/zone' --no-headers)
    local az_count=$(echo "$nodes_by_az" | awk '{print $2}' | sort | uniq | wc -l)

    log_info "Cluster distribuído em $az_count zonas de disponibilidade"

    if [ "$az_count" -gt 1 ]; then
        # Verificar se há anti-affinity configurado adequadamente
        local deployments_with_antiaffinity=0
        local total_deployments=0

        local deployments=$(kubectl get deployments -n "$NAMESPACE" --no-headers | awk '{print $1}')
        for deployment in $deployments; do
            ((total_deployments++))
            local has_antiaffinity=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o yaml | grep -c "podAntiAffinity" || echo "0")
            if [ "$has_antiaffinity" -gt 0 ]; then
                ((deployments_with_antiaffinity++))
            fi
        done

        local antiaffinity_percentage=$((deployments_with_antiaffinity * 100 / total_deployments))
        log_info "Deployments com anti-affinity: ${antiaffinity_percentage}% (${deployments_with_antiaffinity}/${total_deployments})"

        echo "availability_zones:$az_count" >> "$METRICS_FILE"
        echo "antiaffinity_coverage_percent:$antiaffinity_percentage" >> "$METRICS_FILE"
    fi
}

# Analisar recursos ociosos
analyze_idle_resources() {
    log_info "Analisando recursos ociosos"

    local idle_nodes=0
    local idle_pods=0

    # Verificar nós com baixa utilização
    local nodes=$(kubectl get nodes --no-headers | awk '{print $1}')
    for node in $nodes; do
        local cpu_usage=$(kubectl top node "$node" --no-headers 2>/dev/null | awk '{print $3}' | sed 's/%//' || echo "0")
        local memory_usage=$(kubectl top node "$node" --no-headers 2>/dev/null | awk '{print $5}' | sed 's/%//' || echo "0")
        local pod_count=$(kubectl get pods -A --field-selector=spec.nodeName="$node" --no-headers | wc -l)

        # Considerar nó ocioso se uso < 20% CPU e < 30% memory e < 5 pods
        if [ "$cpu_usage" -lt 20 ] && [ "$memory_usage" -lt 30 ] && [ "$pod_count" -lt 5 ]; then
            log_warn "Nó potencialmente ocioso: $node (CPU: ${cpu_usage}%, Memory: ${memory_usage}%, Pods: $pod_count)"
            ((idle_nodes++))
        fi
    done

    # Verificar pods com baixo uso
    local pods=$(kubectl get pods -n "$NAMESPACE" --no-headers | awk '{print $1}')
    for pod in $pods; do
        local cpu_usage=$(kubectl top pod "$pod" -n "$NAMESPACE" --no-headers 2>/dev/null | awk '{print $2}' | sed 's/m$//' || echo "0")
        local memory_usage=$(kubectl top pod "$pod" -n "$NAMESPACE" --no-headers 2>/dev/null | awk '{print $3}' | sed 's/Mi$//' || echo "0")

        # Considerar pod ocioso se uso muito baixo
        if [ "$cpu_usage" -lt 10 ] && [ "$memory_usage" -lt 50 ]; then
            ((idle_pods++))
        fi
    done

    log_info "Recursos ociosos identificados - Nós: $idle_nodes, Pods: $idle_pods"
    echo "idle_nodes:$idle_nodes" >> "$METRICS_FILE"
    echo "idle_pods:$idle_pods" >> "$METRICS_FILE"
}

# Analisar eficiência de scaling
analyze_scaling_efficiency() {
    log_info "Analisando eficiência de scaling"

    local over_provisioned_hpas=0
    local under_provisioned_hpas=0
    local hpas=$(kubectl get hpa -n "$NAMESPACE" --no-headers | awk '{print $1}')

    for hpa in $hpas; do
        local current_replicas=$(kubectl get hpa "$hpa" -n "$NAMESPACE" -o jsonpath='{.status.currentReplicas}' || echo "1")
        local desired_replicas=$(kubectl get hpa "$hpa" -n "$NAMESPACE" -o jsonpath='{.status.desiredReplicas}' || echo "1")
        local min_replicas=$(kubectl get hpa "$hpa" -n "$NAMESPACE" -o jsonpath='{.spec.minReplicas}' || echo "1")
        local max_replicas=$(kubectl get hpa "$hpa" -n "$NAMESPACE" -o jsonpath='{.spec.maxReplicas}' || echo "10")
        local target_cpu=$(kubectl get hpa "$hpa" -n "$NAMESPACE" -o jsonpath='{.spec.targetCPUUtilizationPercentage}' || echo "50")
        local current_cpu=$(kubectl get hpa "$hpa" -n "$NAMESPACE" -o jsonpath='{.status.currentCPUUtilizationPercentage}' || echo "0")

        log_info "HPA $hpa: ${current_replicas}/${max_replicas} replicas, CPU: ${current_cpu}%/${target_cpu}%"

        # Verificar se min_replicas está muito alto
        if [ "$current_replicas" -eq "$min_replicas" ] && [ "$current_cpu" -lt $((target_cpu / 2)) ]; then
            log_warn "HPA $hpa pode estar over-provisionado (min_replicas muito alto)"
            ((over_provisioned_hpas++))
        fi

        # Verificar se max_replicas está limitando
        if [ "$current_replicas" -eq "$max_replicas" ] && [ "$current_cpu" -gt $((target_cpu + 20)) ]; then
            log_warn "HPA $hpa pode estar under-provisionado (max_replicas muito baixo)"
            ((under_provisioned_hpas++))
        fi

        echo "hpa_${hpa}_efficiency:$((100 - (current_cpu - target_cpu) * (current_cpu - target_cpu) / target_cpu))" >> "$METRICS_FILE"
    done

    log_info "HPAs com problemas - Over-provisionados: $over_provisioned_hpas, Under-provisionados: $under_provisioned_hpas"
    echo "over_provisioned_hpas:$over_provisioned_hpas" >> "$METRICS_FILE"
    echo "under_provisioned_hpas:$under_provisioned_hpas" >> "$METRICS_FILE"
}

# Gerar recomendações
generate_recommendations() {
    log_info "Gerando recomendações de otimização"

    # Primeiro executar análise se não foi feita
    analyze_cost_optimization

    local recommendations_file="$RESULTS_DIR/cost_optimization_recommendations.md"

    cat > "$recommendations_file" << EOF
# Recomendações de Otimização de Custos - Neural Hive-Mind

## Resumo Executivo

Análise realizada em: $(date)
Namespace analisado: $NAMESPACE

## Recomendações por Categoria

### 1. Otimização de Computação

EOF

    # Recomendações de CPU
    local cpu_savings=$(grep "total_cpu_savings_potential:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
    if [ "$cpu_savings" -gt 100 ]; then
        cat >> "$recommendations_file" << EOF
#### CPU
- **Economia potencial**: ${cpu_savings}m CPU
- **Ação recomendada**: Reduzir resource requests de deployments subutilizados
- **Prioridade**: Alta
- **Economia estimada**: 15-25% dos custos de computação

EOF
    fi

    # Recomendações de Memória
    local memory_savings=$(grep "total_memory_savings_potential:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
    if [ "$memory_savings" -gt 500 ]; then
        cat >> "$recommendations_file" << EOF
#### Memória
- **Economia potencial**: ${memory_savings}Mi RAM
- **Ação recomendada**: Ajustar memory requests baseado no uso real
- **Prioridade**: Alta
- **Economia estimada**: 10-20% dos custos de computação

EOF
    fi

    # Recomendações de Nós Ociosos
    local idle_nodes=$(grep "idle_nodes:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
    if [ "$idle_nodes" -gt 0 ]; then
        cat >> "$recommendations_file" << EOF
#### Nós Ociosos
- **Nós subutilizados**: $idle_nodes
- **Ação recomendada**: Consolidar workloads ou remover nós
- **Prioridade**: Média
- **Economia estimada**: 30-50% por nó removido

EOF
    fi

    # Recomendações de Storage
    local orphaned_pvs=$(grep "orphaned_persistent_volumes:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
    if [ "$orphaned_pvs" -gt 0 ]; then
        cat >> "$recommendations_file" << EOF
### 2. Otimização de Armazenamento

#### Volumes Órfãos
- **Volumes não utilizados**: $orphaned_pvs
- **Ação recomendada**: Remover persistent volumes órfãos
- **Prioridade**: Baixa
- **Economia estimada**: \$5-20 por volume/mês

EOF
    fi

    # Recomendações de Rede
    local lb_optimization=$(grep "loadbalancer_optimization_potential:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
    if [ "$lb_optimization" -gt 0 ]; then
        cat >> "$recommendations_file" << EOF
### 3. Otimização de Rede

#### LoadBalancers
- **LoadBalancers que podem ser otimizados**: $lb_optimization
- **Ação recomendada**: Substituir por Ingress Controller
- **Prioridade**: Média
- **Economia estimada**: \$15-25 por LoadBalancer/mês

EOF
    fi

    # Recomendações de HPA
    local over_hpas=$(grep "over_provisioned_hpas:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
    if [ "$over_hpas" -gt 0 ]; then
        cat >> "$recommendations_file" << EOF
### 4. Otimização de Auto-Scaling

#### HPA Over-provisionado
- **HPAs com min_replicas alto**: $over_hpas
- **Ação recomendada**: Reduzir min_replicas
- **Prioridade**: Média
- **Economia estimada**: 10-30% por deployment

EOF
    fi

    cat >> "$recommendations_file" << EOF

## Plano de Implementação

### Fase 1 - Implementação Imediata (0-1 semana)
1. Remover volumes órfãos
2. Ajustar resource requests de deployments críticos
3. Otimizar configurações de HPA

### Fase 2 - Implementação Gradual (1-4 semanas)
1. Consolidar workloads em nós subutilizados
2. Substituir LoadBalancers por Ingress
3. Implementar políticas de resource quotas

### Fase 3 - Monitoramento e Ajuste (Contínuo)
1. Monitorar impacto das otimizações
2. Ajustar configurações baseado em métricas
3. Implementar alertas para desperdício de recursos

## Comandos de Implementação

Para implementar as otimizações automaticamente:
\`\`\`bash
# Modo dry-run primeiro
DRY_RUN=true $0 optimize

# Implementação real
DRY_RUN=false $0 optimize
\`\`\`

## Métricas de Acompanhamento

EOF

    # Adicionar métricas atuais
    echo "### Métricas Atuais" >> "$recommendations_file"
    echo '```' >> "$recommendations_file"
    cat "$METRICS_FILE" | sort >> "$recommendations_file"
    echo '```' >> "$recommendations_file"

    log_info "Recomendações salvas em: $recommendations_file"
    add_test_result "Recommendations" "PASS" "Recomendações geradas com sucesso"
}

# Implementar otimizações
implement_optimizations() {
    log_info "Implementando otimizações de custo"

    # Primeiro gerar recomendações
    generate_recommendations

    optimize_resource_requests
    optimize_hpa_configurations
    cleanup_orphaned_resources
    optimize_node_utilization

    add_test_result "Implementation" "PASS" "Otimizações implementadas"
}

# Otimizar resource requests
optimize_resource_requests() {
    log_info "Otimizando resource requests"

    local optimizations_applied=0
    local deployments=$(kubectl get deployments -n "$NAMESPACE" --no-headers | awk '{print $1}')

    for deployment in $deployments; do
        # Calcular uso médio dos últimos dados
        local pods=$(kubectl get pods -n "$NAMESPACE" -l app="$deployment" --no-headers | awk '{print $1}')
        local total_cpu_usage=0
        local total_memory_usage=0
        local pod_count=0

        for pod in $pods; do
            local cpu_usage=$(kubectl top pod "$pod" -n "$NAMESPACE" --no-headers 2>/dev/null | awk '{print $2}' | sed 's/m$//' || echo "0")
            local memory_usage=$(kubectl top pod "$pod" -n "$NAMESPACE" --no-headers 2>/dev/null | awk '{print $3}' | sed 's/Mi$//' || echo "0")

            total_cpu_usage=$((total_cpu_usage + cpu_usage))
            total_memory_usage=$((total_memory_usage + memory_usage))
            ((pod_count++))
        done

        if [ "$pod_count" -gt 0 ]; then
            # Calcular novos requests (uso médio + buffer de 30%)
            local avg_cpu_usage=$((total_cpu_usage / pod_count))
            local avg_memory_usage=$((total_memory_usage / pod_count))
            local new_cpu_request=$((avg_cpu_usage * 130 / 100))
            local new_memory_request=$((avg_memory_usage * 130 / 100))

            # Obter requests atuais
            local current_cpu_request=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].resources.requests.cpu}' | sed 's/m$//' || echo "100")
            local current_memory_request=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].resources.requests.memory}' | sed 's/Mi$//' || echo "128")

            # Calcular economia percentual
            local cpu_savings_percent=$(((current_cpu_request - new_cpu_request) * 100 / current_cpu_request))
            local memory_savings_percent=$(((current_memory_request - new_memory_request) * 100 / current_memory_request))

            # Aplicar otimização se economia for significativa
            if [ "$cpu_savings_percent" -gt "$SAVINGS_THRESHOLD" ] || [ "$memory_savings_percent" -gt "$SAVINGS_THRESHOLD" ]; then
                log_info "Otimizando $deployment: CPU ${current_cpu_request}m -> ${new_cpu_request}m, Memory ${current_memory_request}Mi -> ${new_memory_request}Mi"

                if [ "$DRY_RUN" = "true" ]; then
                    log_info "[DRY-RUN] kubectl patch deployment $deployment -n $NAMESPACE"
                else
                    kubectl patch deployment "$deployment" -n "$NAMESPACE" -p="{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"${deployment}\",\"resources\":{\"requests\":{\"cpu\":\"${new_cpu_request}m\",\"memory\":\"${new_memory_request}Mi\"}}}]}}}}" &>/dev/null || true
                fi
                ((optimizations_applied++))
            fi
        fi
    done

    log_info "Otimizações de resource requests aplicadas: $optimizations_applied"
    echo "resource_request_optimizations:$optimizations_applied" >> "$METRICS_FILE"
}

# Otimizar configurações do HPA
optimize_hpa_configurations() {
    log_info "Otimizando configurações do HPA"

    local hpa_optimizations=0
    local hpas=$(kubectl get hpa -n "$NAMESPACE" --no-headers | awk '{print $1}')

    for hpa in $hpas; do
        local current_min=$(kubectl get hpa "$hpa" -n "$NAMESPACE" -o jsonpath='{.spec.minReplicas}' || echo "1")
        local current_max=$(kubectl get hpa "$hpa" -n "$NAMESPACE" -o jsonpath='{.spec.maxReplicas}' || echo "10")
        local current_target=$(kubectl get hpa "$hpa" -n "$NAMESPACE" -o jsonpath='{.spec.targetCPUUtilizationPercentage}' || echo "50")
        local current_replicas=$(kubectl get hpa "$hpa" -n "$NAMESPACE" -o jsonpath='{.status.currentReplicas}' || echo "1")
        local current_cpu=$(kubectl get hpa "$hpa" -n "$NAMESPACE" -o jsonpath='{.status.currentCPUUtilizationPercentage}' || echo "0")

        local new_min=$current_min
        local new_target=$current_target

        # Otimizar min_replicas se está sempre baixo
        if [ "$current_replicas" -eq "$current_min" ] && [ "$current_cpu" -lt $((current_target / 2)) ]; then
            new_min=$((current_min > 1 ? current_min - 1 : 1))
        fi

        # Otimizar target se está sempre muito baixo
        if [ "$current_cpu" -lt $((current_target - 20)) ]; then
            new_target=$((current_target + 10))
        fi

        # Aplicar otimizações se há mudanças
        if [ "$new_min" -ne "$current_min" ] || [ "$new_target" -ne "$current_target" ]; then
            log_info "Otimizando HPA $hpa: min $current_min -> $new_min, target $current_target% -> $new_target%"

            if [ "$DRY_RUN" = "true" ]; then
                log_info "[DRY-RUN] kubectl patch hpa $hpa -n $NAMESPACE"
            else
                kubectl patch hpa "$hpa" -n "$NAMESPACE" -p="{\"spec\":{\"minReplicas\":$new_min,\"targetCPUUtilizationPercentage\":$new_target}}" &>/dev/null || true
            fi
            ((hpa_optimizations++))
        fi
    done

    log_info "Otimizações de HPA aplicadas: $hpa_optimizations"
    echo "hpa_configuration_optimizations:$hpa_optimizations" >> "$METRICS_FILE"
}

# Limpar recursos órfãos
cleanup_orphaned_resources() {
    log_info "Limpando recursos órfãos para economia de custos"

    local resources_cleaned=0

    # Remover PVs órfãos (Available)
    local orphaned_pvs=$(kubectl get pv --no-headers | grep Available | awk '{print $1}')
    for pv in $orphaned_pvs; do
        log_warn "Removendo PV órfão: $pv"
        if [ "$DRY_RUN" = "true" ]; then
            log_info "[DRY-RUN] kubectl delete pv $pv"
        else
            kubectl delete pv "$pv" --wait=false &>/dev/null || true
        fi
        ((resources_cleaned++))
    done

    # Remover LoadBalancers desnecessários (se houver Ingress alternativo)
    local external_lbs=$(kubectl get services -A --field-selector=spec.type=LoadBalancer --no-headers)
    local ingress_count=$(kubectl get ingress -A --no-headers | wc -l)

    if [ "$ingress_count" -gt 0 ]; then
        while IFS= read -r lb_line; do
            if [ -z "$lb_line" ]; then continue; fi

            local namespace=$(echo "$lb_line" | awk '{print $1}')
            local service_name=$(echo "$lb_line" | awk '{print $2}')

            # Verificar se há ingress correspondente
            local has_ingress=$(kubectl get ingress -n "$namespace" -o yaml 2>/dev/null | grep -c "serviceName: $service_name\|service.*name: $service_name" || echo "0")

            if [ "$has_ingress" -gt 0 ]; then
                log_warn "LoadBalancer $namespace/$service_name tem Ingress alternativo disponível"
                # Não deletar automaticamente por segurança - apenas reportar
                echo "redundant_loadbalancer_${namespace}_${service_name}:1" >> "$METRICS_FILE"
            fi
        done <<< "$external_lbs"
    fi

    log_info "Recursos órfãos removidos: $resources_cleaned"
    echo "orphaned_resources_cleaned:$resources_cleaned" >> "$METRICS_FILE"
}

# Otimizar utilização de nós
optimize_node_utilization() {
    log_info "Otimizando utilização de nós"

    # Verificar nós subutilizados e sugerir consolidação
    local consolidation_opportunities=0
    local nodes=$(kubectl get nodes --no-headers | awk '{print $1}')

    for node in $nodes; do
        local cpu_usage=$(kubectl top node "$node" --no-headers 2>/dev/null | awk '{print $3}' | sed 's/%//' || echo "0")
        local memory_usage=$(kubectl top node "$node" --no-headers 2>/dev/null | awk '{print $5}' | sed 's/%//' || echo "0")
        local pod_count=$(kubectl get pods -A --field-selector=spec.nodeName="$node" --no-headers | wc -l)

        if [ "$cpu_usage" -lt 20 ] && [ "$memory_usage" -lt 30 ] && [ "$pod_count" -lt 5 ]; then
            log_warn "Nó $node está subutilizado (CPU: ${cpu_usage}%, Memory: ${memory_usage}%, Pods: $pod_count)"

            # Sugerir migração de pods (não implementar automaticamente)
            log_info "Considere drenar nó $node para consolidação"
            ((consolidation_opportunities++))
        fi
    done

    # Verificar se cluster autoscaler está configurado adequadamente
    local ca_pods=$(kubectl get pods -n kube-system -l app=cluster-autoscaler --no-headers | wc -l)
    if [ "$ca_pods" -eq 0 ]; then
        log_warn "Cluster Autoscaler não encontrado - considere configurar para otimização automática"
    fi

    log_info "Oportunidades de consolidação identificadas: $consolidation_opportunities"
    echo "node_consolidation_opportunities:$consolidation_opportunities" >> "$METRICS_FILE"
}

# Gerar relatório de custos
generate_cost_report() {
    log_info "Gerando relatório de custos"

    # Executar análise completa
    analyze_cost_optimization

    local report_file="$RESULTS_DIR/cost_optimization_report.html"

    cat > "$report_file" << EOF
<!DOCTYPE html>
<html>
<head>
    <title>Neural Hive-Mind - Relatório de Otimização de Custos</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background: #FF9800; color: white; padding: 20px; border-radius: 5px; }
        .section { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
        .metric { display: inline-block; margin: 10px; padding: 15px; background: #f5f5f5; border-radius: 5px; text-align: center; min-width: 120px; }
        .savings { background: #4CAF50; color: white; }
        .warning { background: #FF5722; color: white; }
        .opportunity { background: #2196F3; color: white; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .chart { width: 100%; height: 200px; background: #f9f9f9; display: flex; align-items: center; justify-content: center; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Neural Hive-Mind - Otimização de Custos</h1>
        <p>Gerado em: $(date)</p>
        <p>Namespace: $NAMESPACE</p>
    </div>

    <div class="section">
        <h2>Resumo de Economia Potencial</h2>
        <div class="metric savings">
            <strong>CPU</strong><br>
            $(grep "total_cpu_savings_potential:" "$METRICS_FILE" | cut -d: -f2 || echo "0")m
        </div>
        <div class="metric savings">
            <strong>Memória</strong><br>
            $(grep "total_memory_savings_potential:" "$METRICS_FILE" | cut -d: -f2 || echo "0")Mi
        </div>
        <div class="metric warning">
            <strong>Nós Ociosos</strong><br>
            $(grep "idle_nodes:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
        <div class="metric opportunity">
            <strong>LoadBalancers Otimizáveis</strong><br>
            $(grep "loadbalancer_optimization_potential:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
    </div>

    <div class="section">
        <h2>Análise por Deployment</h2>
        <table>
            <tr>
                <th>Deployment</th>
                <th>Eficiência CPU</th>
                <th>Eficiência Memória</th>
                <th>Recomendação</th>
            </tr>
EOF

    # Adicionar dados dos deployments
    local deployments=$(kubectl get deployments -n "$NAMESPACE" --no-headers | awk '{print $1}')
    for deployment in $deployments; do
        local cpu_eff=$(grep "deployment_${deployment}_cpu_efficiency:" "$METRICS_FILE" | cut -d: -f2 || echo "N/A")
        local mem_eff=$(grep "deployment_${deployment}_memory_efficiency:" "$METRICS_FILE" | cut -d: -f2 || echo "N/A")
        local recommendation="OK"

        if [ "$cpu_eff" != "N/A" ] && [ "$cpu_eff" -lt 50 ]; then
            recommendation="Reduzir CPU requests"
        elif [ "$mem_eff" != "N/A" ] && [ "$mem_eff" -lt 50 ]; then
            recommendation="Reduzir Memory requests"
        fi

        echo "            <tr><td>$deployment</td><td>${cpu_eff}%</td><td>${mem_eff}%</td><td>$recommendation</td></tr>" >> "$report_file"
    done

    cat >> "$report_file" << EOF
        </table>
    </div>

    <div class="section">
        <h2>Recursos e Desperdícios</h2>
        <div class="metric warning">
            <strong>PVs Órfãos</strong><br>
            $(grep "orphaned_persistent_volumes:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
        <div class="metric warning">
            <strong>HPAs Over-provisionados</strong><br>
            $(grep "over_provisioned_hpas:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
        <div class="metric opportunity">
            <strong>Oportunidades Consolidação</strong><br>
            $(grep "node_consolidation_opportunities:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
    </div>

    <div class="section">
        <h2>Próximos Passos</h2>
        <ol>
            <li>Revisar recomendações de otimização geradas</li>
            <li>Implementar otimizações de baixo risco primeiro</li>
            <li>Monitorar impacto das mudanças</li>
            <li>Configurar alertas para prevenir desperdícios futuros</li>
        </ol>
    </div>

    <div class="section">
        <h2>Métricas Detalhadas</h2>
        <pre>$(cat "$METRICS_FILE" | sort)</pre>
    </div>
</body>
</html>
EOF

    log_info "Relatório de custos salvo em: $report_file"
    add_test_result "Cost Report" "PASS" "Relatório de custos gerado com sucesso"
}

# Executar função principal se script for chamado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi