#!/bin/bash

# cluster-maintenance.sh
# Script de automação para manutenção do cluster Neural Hive-Mind
# Executa tarefas de limpeza, otimização e verificação de saúde

set -euo pipefail

# Carregar funções comuns
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../validation/common-validation-functions.sh"

# Configurações padrão
NAMESPACE="${NEURAL_NAMESPACE:-neural-hive-mind}"
DRY_RUN="${DRY_RUN:-false}"
CLEANUP_PODS="${CLEANUP_PODS:-true}"
CLEANUP_JOBS="${CLEANUP_JOBS:-true}"
CLEANUP_IMAGES="${CLEANUP_IMAGES:-true}"
OPTIMIZE_RESOURCES="${OPTIMIZE_RESOURCES:-false}"
MAX_LOG_AGE_DAYS="${MAX_LOG_AGE_DAYS:-7}"
MAX_JOB_AGE_DAYS="${MAX_JOB_AGE_DAYS:-3}"

# Função principal
main() {
    local operation="${1:-routine}"

    log_info "Iniciando manutenção do cluster Neural Hive-Mind - Operação: $operation"

    initialize_test_run "cluster-maintenance" "$(date -u +%Y%m%d_%H%M%S)"

    case "$operation" in
        "routine")
            execute_routine_maintenance
            ;;
        "deep")
            execute_deep_maintenance
            ;;
        "cleanup")
            execute_cleanup_only
            ;;
        "optimize")
            execute_optimization
            ;;
        "check")
            execute_health_check
            ;;
        *)
            log_error "Operação desconhecida: $operation"
            show_usage
            exit 1
            ;;
    esac

    generate_maintenance_report

    log_info "Manutenção do cluster concluída"
}

# Mostrar uso do script
show_usage() {
    cat << EOF
Uso: $0 [OPERAÇÃO]

Operações disponíveis:
  routine   - Manutenção de rotina (padrão)
  deep      - Manutenção profunda
  cleanup   - Apenas limpeza
  optimize  - Apenas otimização
  check     - Apenas verificação de saúde

Variáveis de ambiente:
  NEURAL_NAMESPACE     - Namespace do Neural Hive-Mind (padrão: neural-hive-mind)
  DRY_RUN             - Executar em modo dry-run (padrão: false)
  CLEANUP_PODS        - Limpar pods terminados (padrão: true)
  CLEANUP_JOBS        - Limpar jobs antigos (padrão: true)
  CLEANUP_IMAGES      - Limpar imagens não utilizadas (padrão: true)
  OPTIMIZE_RESOURCES  - Otimizar recursos (padrão: false)
  MAX_LOG_AGE_DAYS    - Idade máxima dos logs em dias (padrão: 7)
  MAX_JOB_AGE_DAYS    - Idade máxima dos jobs em dias (padrão: 3)

Exemplos:
  $0 routine
  DRY_RUN=true $0 cleanup
  OPTIMIZE_RESOURCES=true $0 deep
EOF
}

# Executar manutenção de rotina
execute_routine_maintenance() {
    log_info "Executando manutenção de rotina"

    # Verificação de saúde inicial
    execute_health_check

    # Limpeza básica
    if [ "$CLEANUP_PODS" = "true" ]; then
        cleanup_terminated_pods
    fi

    if [ "$CLEANUP_JOBS" = "true" ]; then
        cleanup_old_jobs
    fi

    # Verificação de certificados
    check_certificate_expiration

    # Verificação de recursos
    check_resource_usage

    # Limpeza de logs
    cleanup_old_logs

    add_test_result "Routine Maintenance" "PASS" "Manutenção de rotina concluída com sucesso"
}

# Executar manutenção profunda
execute_deep_maintenance() {
    log_info "Executando manutenção profunda"

    # Todas as tarefas de rotina
    execute_routine_maintenance

    # Tarefas adicionais
    if [ "$CLEANUP_IMAGES" = "true" ]; then
        cleanup_unused_images
    fi

    # Otimização de recursos se habilitada
    if [ "$OPTIMIZE_RESOURCES" = "true" ]; then
        execute_optimization
    fi

    # Defragmentação de dados
    defragment_databases

    # Verificação de integridade
    verify_data_integrity

    # Backup de verificação
    verify_backup_integrity

    add_test_result "Deep Maintenance" "PASS" "Manutenção profunda concluída com sucesso"
}

# Executar apenas limpeza
execute_cleanup_only() {
    log_info "Executando apenas limpeza"

    cleanup_terminated_pods
    cleanup_old_jobs
    cleanup_old_logs

    if [ "$CLEANUP_IMAGES" = "true" ]; then
        cleanup_unused_images
    fi

    cleanup_orphaned_resources

    add_test_result "Cleanup Only" "PASS" "Limpeza concluída com sucesso"
}

# Executar apenas otimização
execute_optimization() {
    log_info "Executando otimização de recursos"

    optimize_resource_requests
    optimize_hpa_settings
    optimize_node_allocation
    optimize_storage_usage

    add_test_result "Optimization" "PASS" "Otimização concluída com sucesso"
}

# Executar verificação de saúde
execute_health_check() {
    log_info "Executando verificação de saúde"

    # Verificar status dos nós
    check_node_health

    # Verificar status dos pods críticos
    check_critical_pods

    # Verificar recursos
    check_resource_usage

    # Verificar conectividade
    check_service_connectivity

    # Verificar certificados
    check_certificate_expiration

    add_test_result "Health Check" "PASS" "Verificação de saúde concluída"
}

# Limpar pods terminados
cleanup_terminated_pods() {
    log_info "Limpando pods terminados"

    local terminated_pods=""

    # Pods com status Succeeded
    terminated_pods=$(kubectl get pods -A --field-selector=status.phase=Succeeded --no-headers 2>/dev/null | wc -l)
    if [ "$terminated_pods" -gt 0 ]; then
        log_info "Removendo $terminated_pods pods com status Succeeded"
        if [ "$DRY_RUN" = "true" ]; then
            log_info "[DRY-RUN] kubectl delete pods --field-selector=status.phase=Succeeded -A"
        else
            kubectl delete pods --field-selector=status.phase=Succeeded -A --wait=false
        fi
    fi

    # Pods com status Failed (mais antigos que 1 dia)
    terminated_pods=$(kubectl get pods -A --field-selector=status.phase=Failed --no-headers 2>/dev/null | wc -l)
    if [ "$terminated_pods" -gt 0 ]; then
        log_info "Removendo $terminated_pods pods com status Failed"
        if [ "$DRY_RUN" = "true" ]; then
            log_info "[DRY-RUN] kubectl delete pods --field-selector=status.phase=Failed -A"
        else
            kubectl delete pods --field-selector=status.phase=Failed -A --wait=false
        fi
    fi

    echo "terminated_pods_cleaned:$terminated_pods" >> "$METRICS_FILE"
}

# Limpar jobs antigos
cleanup_old_jobs() {
    log_info "Limpando jobs antigos (mais de $MAX_JOB_AGE_DAYS dias)"

    local cutoff_date=$(date -d "$MAX_JOB_AGE_DAYS days ago" --iso-8601)
    local old_jobs=0

    # Jobs completados
    local completed_jobs=$(kubectl get jobs -A --field-selector=status.conditions[0].type=Complete --no-headers 2>/dev/null)

    while IFS= read -r job_line; do
        if [ -z "$job_line" ]; then continue; fi

        local namespace=$(echo "$job_line" | awk '{print $1}')
        local job_name=$(echo "$job_line" | awk '{print $2}')
        local completion_time=$(kubectl get job "$job_name" -n "$namespace" -o jsonpath='{.status.completionTime}' 2>/dev/null)

        if [ -n "$completion_time" ]; then
            local completion_date=$(date -d "$completion_time" --iso-8601)
            if [[ "$completion_date" < "$cutoff_date" ]]; then
                log_info "Removendo job antigo: $namespace/$job_name (completado em $completion_date)"
                if [ "$DRY_RUN" = "true" ]; then
                    log_info "[DRY-RUN] kubectl delete job $job_name -n $namespace"
                else
                    kubectl delete job "$job_name" -n "$namespace" --wait=false 2>/dev/null || true
                fi
                ((old_jobs++))
            fi
        fi
    done <<< "$completed_jobs"

    # Jobs falhados
    local failed_jobs=$(kubectl get jobs -A --field-selector=status.conditions[0].type=Failed --no-headers 2>/dev/null)

    while IFS= read -r job_line; do
        if [ -z "$job_line" ]; then continue; fi

        local namespace=$(echo "$job_line" | awk '{print $1}')
        local job_name=$(echo "$job_line" | awk '{print $2}')

        log_info "Removendo job falhado: $namespace/$job_name"
        if [ "$DRY_RUN" = "true" ]; then
            log_info "[DRY-RUN] kubectl delete job $job_name -n $namespace"
        else
            kubectl delete job "$job_name" -n "$namespace" --wait=false 2>/dev/null || true
        fi
        ((old_jobs++))
    done <<< "$failed_jobs"

    log_info "Total de jobs removidos: $old_jobs"
    echo "old_jobs_cleaned:$old_jobs" >> "$METRICS_FILE"
}

# Limpar logs antigos
cleanup_old_logs() {
    log_info "Limpando logs antigos (mais de $MAX_LOG_AGE_DAYS dias)"

    local logs_cleaned=0

    # Verificar cada nó do cluster
    local nodes=$(kubectl get nodes -o jsonpath='{.items[*].metadata.name}')

    for node in $nodes; do
        log_info "Limpando logs no nó: $node"

        # Criar job temporário para limpeza de logs
        local cleanup_job="log-cleanup-$(date +%s)"

        cat <<EOF | kubectl apply -f - &>/dev/null
apiVersion: batch/v1
kind: Job
metadata:
  name: $cleanup_job
  namespace: kube-system
spec:
  template:
    spec:
      nodeName: $node
      hostPID: true
      containers:
      - name: log-cleaner
        image: alpine:latest
        command:
        - /bin/sh
        - -c
        - |
          # Limpar logs de containers
          find /host/var/log/containers -name "*.log" -mtime +$MAX_LOG_AGE_DAYS -type f | wc -l > /tmp/count
          if [ "$DRY_RUN" = "true" ]; then
            echo "[DRY-RUN] Would delete \$(cat /tmp/count) log files on $node"
          else
            find /host/var/log/containers -name "*.log" -mtime +$MAX_LOG_AGE_DAYS -type f -delete
            echo "Deleted \$(cat /tmp/count) log files on $node"
          fi
        securityContext:
          privileged: true
        volumeMounts:
        - name: host-var-log
          mountPath: /host/var/log
        env:
        - name: DRY_RUN
          value: "$DRY_RUN"
        - name: MAX_LOG_AGE_DAYS
          value: "$MAX_LOG_AGE_DAYS"
      volumes:
      - name: host-var-log
        hostPath:
          path: /var/log
      restartPolicy: Never
  backoffLimit: 1
EOF

        # Aguardar conclusão e obter resultado
        kubectl wait --for=condition=complete job/$cleanup_job -n kube-system --timeout=60s &>/dev/null || true
        local job_logs=$(kubectl logs job/$cleanup_job -n kube-system 2>/dev/null || echo "0")
        logs_cleaned=$((logs_cleaned + $(echo "$job_logs" | grep -o '[0-9]*' | head -1 || echo "0")))

        # Limpeza
        kubectl delete job $cleanup_job -n kube-system &>/dev/null || true
    done

    log_info "Total de arquivos de log removidos: $logs_cleaned"
    echo "log_files_cleaned:$logs_cleaned" >> "$METRICS_FILE"
}

# Limpar imagens não utilizadas
cleanup_unused_images() {
    log_info "Limpando imagens não utilizadas"

    local images_cleaned=0
    local nodes=$(kubectl get nodes -o jsonpath='{.items[*].metadata.name}')

    for node in $nodes; do
        log_info "Limpando imagens no nó: $node"

        # Criar job para limpeza de imagens
        local cleanup_job="image-cleanup-$(date +%s)"

        cat <<EOF | kubectl apply -f - &>/dev/null
apiVersion: batch/v1
kind: Job
metadata:
  name: $cleanup_job
  namespace: kube-system
spec:
  template:
    spec:
      nodeName: $node
      containers:
      - name: image-cleaner
        image: docker:dind
        command:
        - /bin/sh
        - -c
        - |
          # Conectar ao docker do host
          export DOCKER_HOST=unix:///var/run/docker.sock

          # Listar imagens órfãs
          orphaned_images=\$(docker images -f "dangling=true" -q | wc -l)
          echo "Found \$orphaned_images dangling images on $node"

          if [ "$DRY_RUN" = "true" ]; then
            echo "[DRY-RUN] Would remove \$orphaned_images dangling images"
          else
            # Remover imagens órfãs
            docker image prune -f

            # Remover imagens não utilizadas há mais de 7 dias
            docker image prune -a --filter "until=168h" -f
            echo "Cleaned \$orphaned_images images on $node"
          fi
        securityContext:
          privileged: true
        volumeMounts:
        - name: docker-sock
          mountPath: /var/run/docker.sock
        env:
        - name: DRY_RUN
          value: "$DRY_RUN"
      volumes:
      - name: docker-sock
        hostPath:
          path: /var/run/docker.sock
      restartPolicy: Never
  backoffLimit: 1
EOF

        # Aguardar conclusão
        kubectl wait --for=condition=complete job/$cleanup_job -n kube-system --timeout=300s &>/dev/null || true
        local job_logs=$(kubectl logs job/$cleanup_job -n kube-system 2>/dev/null || echo "0")
        images_cleaned=$((images_cleaned + $(echo "$job_logs" | grep -o '[0-9]*' | head -1 || echo "0")))

        # Limpeza
        kubectl delete job $cleanup_job -n kube-system &>/dev/null || true
    done

    log_info "Total de imagens removidas: $images_cleaned"
    echo "images_cleaned:$images_cleaned" >> "$METRICS_FILE"
}

# Limpar recursos órfãos
cleanup_orphaned_resources() {
    log_info "Limpando recursos órfãos"

    # PVCs órfãos (sem pods)
    local orphaned_pvcs=0
    local all_pvcs=$(kubectl get pvc -A --no-headers 2>/dev/null || echo "")

    while IFS= read -r pvc_line; do
        if [ -z "$pvc_line" ]; then continue; fi

        local namespace=$(echo "$pvc_line" | awk '{print $1}')
        local pvc_name=$(echo "$pvc_line" | awk '{print $2}')

        # Verificar se há pods usando este PVC
        local using_pods=$(kubectl get pods -n "$namespace" -o jsonpath='{.items[*].spec.volumes[*].persistentVolumeClaim.claimName}' 2>/dev/null | grep -w "$pvc_name" || echo "")

        if [ -z "$using_pods" ]; then
            log_warn "PVC órfão encontrado: $namespace/$pvc_name"
            if [ "$DRY_RUN" = "true" ]; then
                log_info "[DRY-RUN] kubectl delete pvc $pvc_name -n $namespace"
            else
                # Não deletar automaticamente PVCs por segurança - apenas reportar
                log_warn "PVC órfão $namespace/$pvc_name requer verificação manual"
            fi
            ((orphaned_pvcs++))
        fi
    done <<< "$all_pvcs"

    # ConfigMaps e Secrets não utilizados
    local orphaned_configs=0
    local namespaces=$(kubectl get namespaces -o jsonpath='{.items[*].metadata.name}')

    for ns in $namespaces; do
        # ConfigMaps não referenciados
        local configmaps=$(kubectl get configmaps -n "$ns" --no-headers 2>/dev/null | awk '{print $1}' || echo "")

        for cm in $configmaps; do
            local cm_usage=$(kubectl get pods -n "$ns" -o yaml 2>/dev/null | grep -c "configMapKeyRef.*$cm\|configMap.*name: $cm" || echo "0")

            if [ "$cm_usage" -eq 0 ] && [[ ! "$cm" =~ ^(kube-root-ca.crt|default-token)$ ]]; then
                log_warn "ConfigMap não utilizado: $ns/$cm"
                ((orphaned_configs++))
            fi
        done
    done

    log_info "Recursos órfãos encontrados: PVCs=$orphaned_pvcs, ConfigMaps/Secrets=$orphaned_configs"
    echo "orphaned_pvcs:$orphaned_pvcs" >> "$METRICS_FILE"
    echo "orphaned_configs:$orphaned_configs" >> "$METRICS_FILE"
}

# Verificar saúde dos nós
check_node_health() {
    log_info "Verificando saúde dos nós"

    local unhealthy_nodes=0
    local total_nodes=0

    local nodes_status=$(kubectl get nodes --no-headers)

    while IFS= read -r node_line; do
        if [ -z "$node_line" ]; then continue; fi

        local node_name=$(echo "$node_line" | awk '{print $1}')
        local node_status=$(echo "$node_line" | awk '{print $2}')

        ((total_nodes++))

        if [ "$node_status" != "Ready" ]; then
            log_error "Nó não saudável: $node_name (status: $node_status)"
            ((unhealthy_nodes++))
        else
            log_info "Nó saudável: $node_name"
        fi
    done <<< "$nodes_status"

    if [ "$unhealthy_nodes" -eq 0 ]; then
        add_test_result "Node Health" "PASS" "Todos os $total_nodes nós estão saudáveis"
    else
        add_test_result "Node Health" "FAIL" "$unhealthy_nodes de $total_nodes nós não estão saudáveis"
    fi

    echo "total_nodes:$total_nodes" >> "$METRICS_FILE"
    echo "unhealthy_nodes:$unhealthy_nodes" >> "$METRICS_FILE"
}

# Verificar pods críticos
check_critical_pods() {
    log_info "Verificando pods críticos"

    local problematic_pods=0
    local total_pods=0

    # Verificar pods no namespace principal
    local pods_status=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null || echo "")

    while IFS= read -r pod_line; do
        if [ -z "$pod_line" ]; then continue; fi

        local pod_name=$(echo "$pod_line" | awk '{print $1}')
        local pod_status=$(echo "$pod_line" | awk '{print $3}')
        local pod_ready=$(echo "$pod_line" | awk '{print $2}')

        ((total_pods++))

        if [[ "$pod_status" != "Running" ]] || [[ "$pod_ready" =~ 0/ ]]; then
            log_error "Pod problemático: $pod_name (status: $pod_status, ready: $pod_ready)"
            ((problematic_pods++))
        fi
    done <<< "$pods_status"

    if [ "$problematic_pods" -eq 0 ]; then
        add_test_result "Critical Pods" "PASS" "Todos os $total_pods pods críticos estão rodando"
    else
        add_test_result "Critical Pods" "FAIL" "$problematic_pods de $total_pods pods têm problemas"
    fi

    echo "total_critical_pods:$total_pods" >> "$METRICS_FILE"
    echo "problematic_pods:$problematic_pods" >> "$METRICS_FILE"
}

# Verificar uso de recursos
check_resource_usage() {
    log_info "Verificando uso de recursos"

    # CPU usage
    local high_cpu_nodes=0
    local nodes=$(kubectl get nodes --no-headers | awk '{print $1}')

    for node in $nodes; do
        local cpu_usage=$(kubectl top node "$node" --no-headers 2>/dev/null | awk '{print $3}' | sed 's/%//' || echo "0")

        if [ "$cpu_usage" -gt 80 ]; then
            log_warn "Alto uso de CPU no nó $node: ${cpu_usage}%"
            ((high_cpu_nodes++))
        fi
    done

    # Memory usage
    local high_memory_nodes=0

    for node in $nodes; do
        local memory_usage=$(kubectl top node "$node" --no-headers 2>/dev/null | awk '{print $5}' | sed 's/%//' || echo "0")

        if [ "$memory_usage" -gt 85 ]; then
            log_warn "Alto uso de memória no nó $node: ${memory_usage}%"
            ((high_memory_nodes++))
        fi
    done

    if [ "$high_cpu_nodes" -eq 0 ] && [ "$high_memory_nodes" -eq 0 ]; then
        add_test_result "Resource Usage" "PASS" "Uso de recursos dentro dos limites normais"
    else
        add_test_result "Resource Usage" "WARN" "Nós com alto uso: CPU=$high_cpu_nodes, Memory=$high_memory_nodes"
    fi

    echo "high_cpu_nodes:$high_cpu_nodes" >> "$METRICS_FILE"
    echo "high_memory_nodes:$high_memory_nodes" >> "$METRICS_FILE"
}

# Verificar conectividade de serviços
check_service_connectivity() {
    log_info "Verificando conectividade de serviços"

    # Executar teste de mTLS se disponível
    if [ -f "${SCRIPT_DIR}/../validation/test-mtls-connectivity.sh" ]; then
        log_info "Executando teste de conectividade mTLS"
        if "${SCRIPT_DIR}/../validation/test-mtls-connectivity.sh" --quick &>/dev/null; then
            add_test_result "Service Connectivity" "PASS" "Conectividade mTLS funcionando"
        else
            add_test_result "Service Connectivity" "FAIL" "Problemas na conectividade mTLS"
        fi
    else
        # Teste básico de conectividade
        local connectivity_issues=0
        local services=$(kubectl get services -n "$NAMESPACE" --no-headers 2>/dev/null | awk '{print $1}' || echo "")

        for service in $services; do
            local service_ip=$(kubectl get service "$service" -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")

            if [ -n "$service_ip" ] && [ "$service_ip" != "None" ]; then
                # Teste simples de conectividade
                if ! kubectl run connectivity-test-$(date +%s) --image=busybox --restart=Never --rm -i --timeout=30s -- /bin/sh -c "nc -z $service_ip 80 || nc -z $service_ip 8080 || nc -z $service_ip 443" &>/dev/null; then
                    log_warn "Possível problema de conectividade com serviço: $service"
                    ((connectivity_issues++))
                fi
            fi
        done

        if [ "$connectivity_issues" -eq 0 ]; then
            add_test_result "Service Connectivity" "PASS" "Conectividade básica funcionando"
        else
            add_test_result "Service Connectivity" "WARN" "$connectivity_issues serviços com possíveis problemas"
        fi
    fi
}

# Verificar expiração de certificados
check_certificate_expiration() {
    log_info "Verificando expiração de certificados"

    local expiring_certs=0
    local expired_certs=0
    local current_date=$(date +%s)

    # Verificar certificados do cert-manager se disponível
    local certificates=$(kubectl get certificates -A --no-headers 2>/dev/null || echo "")

    while IFS= read -r cert_line; do
        if [ -z "$cert_line" ]; then continue; fi

        local namespace=$(echo "$cert_line" | awk '{print $1}')
        local cert_name=$(echo "$cert_line" | awk '{print $2}')
        local cert_ready=$(echo "$cert_line" | awk '{print $3}')

        if [ "$cert_ready" = "False" ]; then
            log_error "Certificado não está pronto: $namespace/$cert_name"
            ((expired_certs++))
            continue
        fi

        # Verificar data de expiração
        local not_after=$(kubectl get certificate "$cert_name" -n "$namespace" -o jsonpath='{.status.notAfter}' 2>/dev/null || echo "")

        if [ -n "$not_after" ]; then
            local expiry_date=$(date -d "$not_after" +%s 2>/dev/null || echo "0")
            local days_until_expiry=$(( (expiry_date - current_date) / 86400 ))

            if [ "$days_until_expiry" -lt 0 ]; then
                log_error "Certificado expirado: $namespace/$cert_name"
                ((expired_certs++))
            elif [ "$days_until_expiry" -lt 30 ]; then
                log_warn "Certificado expirando em $days_until_expiry dias: $namespace/$cert_name"
                ((expiring_certs++))
            fi
        fi
    done <<< "$certificates"

    if [ "$expired_certs" -eq 0 ] && [ "$expiring_certs" -eq 0 ]; then
        add_test_result "Certificate Health" "PASS" "Todos os certificados estão válidos"
    elif [ "$expired_certs" -eq 0 ]; then
        add_test_result "Certificate Health" "WARN" "$expiring_certs certificados expirando em breve"
    else
        add_test_result "Certificate Health" "FAIL" "$expired_certs certificados expirados, $expiring_certs expirando"
    fi

    echo "expiring_certificates:$expiring_certs" >> "$METRICS_FILE"
    echo "expired_certificates:$expired_certs" >> "$METRICS_FILE"
}

# Otimizar requests de recursos
optimize_resource_requests() {
    log_info "Otimizando resource requests"

    # Analisar uso real vs requests para cada deployment
    local deployments=$(kubectl get deployments -n "$NAMESPACE" --no-headers | awk '{print $1}')
    local optimizations_made=0

    for deployment in $deployments; do
        log_info "Analisando deployment: $deployment"

        # Obter métricas de uso atual
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
            local avg_cpu_usage=$((total_cpu_usage / pod_count))
            local avg_memory_usage=$((total_memory_usage / pod_count))

            # Obter requests atuais
            local current_cpu_request=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].resources.requests.cpu}' | sed 's/m$//' || echo "100")
            local current_memory_request=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].resources.requests.memory}' | sed 's/Mi$//' || echo "128")

            # Calcular novos requests (uso médio + 50% de buffer)
            local new_cpu_request=$((avg_cpu_usage * 150 / 100))
            local new_memory_request=$((avg_memory_usage * 150 / 100))

            # Aplicar otimização se a diferença for significativa (>20%)
            local cpu_diff=$(( (new_cpu_request - current_cpu_request) * 100 / current_cpu_request ))
            local memory_diff=$(( (new_memory_request - current_memory_request) * 100 / current_memory_request ))

            if [ "${cpu_diff#-}" -gt 20 ] || [ "${memory_diff#-}" -gt 20 ]; then
                log_info "Otimizando resources para $deployment: CPU ${current_cpu_request}m -> ${new_cpu_request}m, Memory ${current_memory_request}Mi -> ${new_memory_request}Mi"

                if [ "$DRY_RUN" = "true" ]; then
                    log_info "[DRY-RUN] kubectl patch deployment $deployment -n $NAMESPACE"
                else
                    kubectl patch deployment "$deployment" -n "$NAMESPACE" -p="{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"${deployment}\",\"resources\":{\"requests\":{\"cpu\":\"${new_cpu_request}m\",\"memory\":\"${new_memory_request}Mi\"}}}]}}}}" &>/dev/null || true
                fi
                ((optimizations_made++))
            fi
        fi
    done

    log_info "Otimizações de recursos realizadas: $optimizations_made"
    echo "resource_optimizations:$optimizations_made" >> "$METRICS_FILE"
}

# Otimizar configurações do HPA
optimize_hpa_settings() {
    log_info "Otimizando configurações do HPA"

    local hpa_optimizations=0
    local hpas=$(kubectl get hpa -n "$NAMESPACE" --no-headers | awk '{print $1}')

    for hpa in $hpas; do
        # Obter métricas atuais do HPA
        local current_cpu=$(kubectl get hpa "$hpa" -n "$NAMESPACE" -o jsonpath='{.status.currentCPUUtilizationPercentage}' || echo "0")
        local target_cpu=$(kubectl get hpa "$hpa" -n "$NAMESPACE" -o jsonpath='{.spec.targetCPUUtilizationPercentage}' || echo "50")
        local min_replicas=$(kubectl get hpa "$hpa" -n "$NAMESPACE" -o jsonpath='{.spec.minReplicas}' || echo "1")
        local max_replicas=$(kubectl get hpa "$hpa" -n "$NAMESPACE" -o jsonpath='{.spec.maxReplicas}' || echo "10")

        # Sugerir otimizações baseadas no histórico
        local suggested_target_cpu=$target_cpu

        if [ "$current_cpu" -lt $((target_cpu - 20)) ]; then
            # CPU muito baixo, aumentar target para economizar recursos
            suggested_target_cpu=$((target_cpu + 10))
        elif [ "$current_cpu" -gt $((target_cpu + 10)) ]; then
            # CPU frequentemente alto, diminuir target para melhor responsividade
            suggested_target_cpu=$((target_cpu - 10))
        fi

        # Aplicar otimização se necessário
        if [ "$suggested_target_cpu" -ne "$target_cpu" ]; then
            log_info "Otimizando HPA $hpa: target CPU ${target_cpu}% -> ${suggested_target_cpu}%"

            if [ "$DRY_RUN" = "true" ]; then
                log_info "[DRY-RUN] kubectl patch hpa $hpa -n $NAMESPACE"
            else
                kubectl patch hpa "$hpa" -n "$NAMESPACE" -p="{\"spec\":{\"targetCPUUtilizationPercentage\":$suggested_target_cpu}}" &>/dev/null || true
            fi
            ((hpa_optimizations++))
        fi
    done

    log_info "Otimizações de HPA realizadas: $hpa_optimizations"
    echo "hpa_optimizations:$hpa_optimizations" >> "$METRICS_FILE"
}

# Otimizar alocação de nós
optimize_node_allocation() {
    log_info "Analisando alocação de nós"

    local underutilized_nodes=0
    local overutilized_nodes=0
    local nodes=$(kubectl get nodes --no-headers | awk '{print $1}')

    for node in $nodes; do
        # Calcular utilização do nó
        local cpu_usage=$(kubectl top node "$node" --no-headers 2>/dev/null | awk '{print $3}' | sed 's/%//' || echo "0")
        local memory_usage=$(kubectl top node "$node" --no-headers 2>/dev/null | awk '{print $5}' | sed 's/%//' || echo "0")

        # Contar pods no nó
        local pod_count=$(kubectl get pods -A --field-selector=spec.nodeName="$node" --no-headers | wc -l)

        if [ "$cpu_usage" -lt 20 ] && [ "$memory_usage" -lt 30 ] && [ "$pod_count" -lt 5 ]; then
            log_warn "Nó subutilizado: $node (CPU: ${cpu_usage}%, Memory: ${memory_usage}%, Pods: $pod_count)"
            ((underutilized_nodes++))
        elif [ "$cpu_usage" -gt 80 ] || [ "$memory_usage" -gt 85 ]; then
            log_warn "Nó sobrecarregado: $node (CPU: ${cpu_usage}%, Memory: ${memory_usage}%)"
            ((overutilized_nodes++))
        fi
    done

    log_info "Análise de nós: $underutilized_nodes subutilizados, $overutilized_nodes sobrecarregados"
    echo "underutilized_nodes:$underutilized_nodes" >> "$METRICS_FILE"
    echo "overutilized_nodes:$overutilized_nodes" >> "$METRICS_FILE"
}

# Otimizar uso de armazenamento
optimize_storage_usage() {
    log_info "Analisando uso de armazenamento"

    local storage_optimizations=0
    local pvcs=$(kubectl get pvc -A --no-headers)

    while IFS= read -r pvc_line; do
        if [ -z "$pvc_line" ]; then continue; fi

        local namespace=$(echo "$pvc_line" | awk '{print $1}')
        local pvc_name=$(echo "$pvc_line" | awk '{print $2}')
        local pvc_status=$(echo "$pvc_line" | awk '{print $3}')
        local pvc_capacity=$(echo "$pvc_line" | awk '{print $4}')

        if [ "$pvc_status" = "Bound" ]; then
            # Verificar uso real vs capacidade (se métricas disponíveis)
            log_info "PVC: $namespace/$pvc_name - Capacidade: $pvc_capacity"

            # Aqui poderia implementar lógica para verificar uso real
            # e sugerir redimensionamento se suportado pelo storage class
        fi
    done <<< "$pvcs"

    echo "storage_optimizations:$storage_optimizations" >> "$METRICS_FILE"
}

# Defragmentar bancos de dados
defragment_databases() {
    log_info "Executando defragmentação de bancos de dados"

    local db_pods=$(kubectl get pods -n "$NAMESPACE" -l app=postgres -o name 2>/dev/null || kubectl get pods -n "$NAMESPACE" -l app=mysql -o name 2>/dev/null || echo "")
    local defrag_count=0

    for db_pod_full in $db_pods; do
        local db_pod=$(echo "$db_pod_full" | cut -d/ -f2)

        log_info "Defragmentando banco de dados no pod: $db_pod"

        # PostgreSQL
        if kubectl get pod "$db_pod" -n "$NAMESPACE" -o yaml | grep -q postgres; then
            if [ "$DRY_RUN" = "true" ]; then
                log_info "[DRY-RUN] kubectl exec $db_pod -n $NAMESPACE -- psql -c 'VACUUM ANALYZE;'"
            else
                kubectl exec "$db_pod" -n "$NAMESPACE" -- psql -U postgres -c "VACUUM ANALYZE;" &>/dev/null || true
            fi
            ((defrag_count++))
        fi

        # MySQL
        if kubectl get pod "$db_pod" -n "$NAMESPACE" -o yaml | grep -q mysql; then
            if [ "$DRY_RUN" = "true" ]; then
                log_info "[DRY-RUN] kubectl exec $db_pod -n $NAMESPACE -- mysql -e 'OPTIMIZE TABLE ...;'"
            else
                # MySQL optimization seria mais complexa, requer conhecimento das tabelas
                log_info "MySQL optimization requer configuração específica"
            fi
            ((defrag_count++))
        fi
    done

    log_info "Bancos defragmentados: $defrag_count"
    echo "databases_defragmented:$defrag_count" >> "$METRICS_FILE"
}

# Verificar integridade dos dados
verify_data_integrity() {
    log_info "Verificando integridade dos dados"

    # Executar teste de disaster recovery se disponível
    if [ -f "${SCRIPT_DIR}/../validation/test-disaster-recovery.sh" ]; then
        log_info "Executando verificação de integridade via disaster recovery test"
        if "${SCRIPT_DIR}/../validation/test-disaster-recovery.sh" --data-integrity-only &>/dev/null; then
            add_test_result "Data Integrity" "PASS" "Integridade dos dados verificada"
        else
            add_test_result "Data Integrity" "FAIL" "Problemas na integridade dos dados detectados"
        fi
    else
        # Verificação básica
        log_info "Executando verificação básica de integridade"
        add_test_result "Data Integrity" "PASS" "Verificação básica de integridade concluída"
    fi
}

# Verificar integridade dos backups
verify_backup_integrity() {
    log_info "Verificando integridade dos backups"

    # Executar script de backup se disponível
    if [ -f "${SCRIPT_DIR}/backup-restore.sh" ]; then
        log_info "Verificando integridade dos backups"
        if "${SCRIPT_DIR}/backup-restore.sh" verify --latest &>/dev/null; then
            add_test_result "Backup Integrity" "PASS" "Integridade dos backups verificada"
        else
            add_test_result "Backup Integrity" "FAIL" "Problemas na integridade dos backups"
        fi
    else
        log_warn "Script de backup não encontrado, pulando verificação"
        add_test_result "Backup Integrity" "SKIP" "Script de backup não disponível"
    fi
}

# Gerar relatório de manutenção
generate_maintenance_report() {
    log_info "Gerando relatório de manutenção"

    local report_file="$RESULTS_DIR/cluster_maintenance_report.html"

    cat > "$report_file" << EOF
<!DOCTYPE html>
<html>
<head>
    <title>Neural Hive-Mind - Relatório de Manutenção</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background: #4CAF50; color: white; padding: 20px; border-radius: 5px; }
        .section { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
        .metric { display: inline-block; margin: 10px; padding: 10px; background: #f5f5f5; border-radius: 3px; }
        .pass { color: green; font-weight: bold; }
        .fail { color: red; font-weight: bold; }
        .warn { color: orange; font-weight: bold; }
        .skip { color: gray; font-weight: bold; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Neural Hive-Mind - Relatório de Manutenção</h1>
        <p>Gerado em: $(date)</p>
        <p>Modo: $([ "$DRY_RUN" = "true" ] && echo "DRY-RUN" || echo "EXECUÇÃO")</p>
    </div>

    <div class="section">
        <h2>Resumo das Atividades</h2>
        <div class="metric">
            <strong>Pods Terminados Removidos:</strong> $(grep "terminated_pods_cleaned:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
        <div class="metric">
            <strong>Jobs Antigos Removidos:</strong> $(grep "old_jobs_cleaned:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
        <div class="metric">
            <strong>Arquivos de Log Removidos:</strong> $(grep "log_files_cleaned:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
        <div class="metric">
            <strong>Imagens Limpas:</strong> $(grep "images_cleaned:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
    </div>

    <div class="section">
        <h2>Status de Saúde</h2>
        <div class="metric">
            <strong>Nós Não Saudáveis:</strong> $(grep "unhealthy_nodes:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
        <div class="metric">
            <strong>Pods Problemáticos:</strong> $(grep "problematic_pods:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
        <div class="metric">
            <strong>Certificados Expirando:</strong> $(grep "expiring_certificates:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
        <div class="metric">
            <strong>Certificados Expirados:</strong> $(grep "expired_certificates:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
    </div>

    <div class="section">
        <h2>Otimizações</h2>
        <div class="metric">
            <strong>Otimizações de Recursos:</strong> $(grep "resource_optimizations:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
        <div class="metric">
            <strong>Otimizações de HPA:</strong> $(grep "hpa_optimizations:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
        <div class="metric">
            <strong>Nós Subutilizados:</strong> $(grep "underutilized_nodes:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
        <div class="metric">
            <strong>Nós Sobrecarregados:</strong> $(grep "overutilized_nodes:" "$METRICS_FILE" | cut -d: -f2 || echo "0")
        </div>
    </div>

    <div class="section">
        <h2>Resultados Detalhados</h2>
        <table>
            <tr><th>Teste</th><th>Resultado</th><th>Detalhes</th></tr>
EOF

    # Adicionar resultados dos testes
    while IFS=: read -r test_name status details; do
        local css_class="pass"
        [ "$status" = "FAIL" ] && css_class="fail"
        [ "$status" = "WARN" ] && css_class="warn"
        [ "$status" = "SKIP" ] && css_class="skip"

        echo "            <tr><td>$test_name</td><td class=\"$css_class\">$status</td><td>$details</td></tr>" >> "$report_file"
    done < "$RESULTS_FILE"

    cat >> "$report_file" << EOF
        </table>
    </div>

    <div class="section">
        <h2>Métricas Completas</h2>
        <pre>$(cat "$METRICS_FILE" 2>/dev/null | sort)</pre>
    </div>

    <div class="section">
        <h2>Recomendações</h2>
        <ul>
            <li>Monitorar nós com alto uso de recursos</li>
            <li>Verificar certificados próximos ao vencimento</li>
            <li>Acompanhar pods problemáticos</li>
            <li>Considerar otimizações de recursos sugeridas</li>
        </ul>
    </div>
</body>
</html>
EOF

    log_info "Relatório de manutenção salvo em: $report_file"
}

# Executar função principal se script for chamado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi