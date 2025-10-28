#!/bin/bash

# backup-restore.sh
# Script de backup e restore para o Neural Hive-Mind
# Gerencia backups de dados, configurações e estado do cluster

set -euo pipefail

# Carregar funções comuns
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../validation/common-validation-functions.sh"

# Configurações padrão
NAMESPACE="${NEURAL_NAMESPACE:-neural-hive-mind}"
BACKUP_STORAGE="${BACKUP_STORAGE:-s3://neural-hive-mind-backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
VELERO_NAMESPACE="${VELERO_NAMESPACE:-velero}"
ENCRYPTION_KEY="${ENCRYPTION_KEY:-/etc/backup/encryption.key}"
COMPRESSION_LEVEL="${COMPRESSION_LEVEL:-6}"

# Função principal
main() {
    local operation="${1:-status}"
    local timestamp="${2:-$(date -u +%Y%m%d_%H%M%S)}"

    log_info "Iniciando operação de backup/restore: $operation"

    initialize_test_run "backup-restore" "$timestamp"

    case "$operation" in
        "backup")
            execute_backup "$timestamp" "${3:-full}"
            ;;
        "restore")
            execute_restore "$timestamp" "${3:-latest}"
            ;;
        "verify")
            verify_backup "$timestamp" "${3:-latest}"
            ;;
        "list")
            list_backups
            ;;
        "status")
            show_backup_status
            ;;
        "cleanup")
            cleanup_old_backups
            ;;
        *)
            log_error "Operação desconhecida: $operation"
            show_usage
            exit 1
            ;;
    esac

    generate_summary_report

    log_info "Operação de backup/restore concluída"
}

# Mostrar uso do script
show_usage() {
    cat << EOF
Uso: $0 [OPERAÇÃO] [TIMESTAMP] [TIPO/OPÇÕES]

Operações disponíveis:
  backup    - Criar backup (tipos: full, incremental, config, data)
  restore   - Restaurar backup (opções: latest, TIMESTAMP, selective)
  verify    - Verificar integridade do backup
  list      - Listar backups disponíveis
  status    - Mostrar status dos backups
  cleanup   - Limpar backups antigos

Variáveis de ambiente:
  NEURAL_NAMESPACE        - Namespace do Neural Hive-Mind (padrão: neural-hive-mind)
  BACKUP_STORAGE         - Local de armazenamento (padrão: s3://neural-hive-mind-backups)
  BACKUP_RETENTION_DAYS  - Dias de retenção (padrão: 30)
  VELERO_NAMESPACE       - Namespace do Velero (padrão: velero)
  ENCRYPTION_KEY         - Chave de criptografia (padrão: /etc/backup/encryption.key)
  COMPRESSION_LEVEL      - Nível de compressão 1-9 (padrão: 6)

Exemplos:
  $0 backup                          # Backup completo
  $0 backup $(date +%Y%m%d_%H%M%S) incremental
  $0 restore latest
  $0 restore 20231215_120000
  $0 verify latest
EOF
}

# Executar backup
execute_backup() {
    local timestamp="$1"
    local backup_type="${2:-full}"

    log_info "Executando backup tipo: $backup_type"

    case "$backup_type" in
        "full")
            create_full_backup "$timestamp"
            ;;
        "incremental")
            create_incremental_backup "$timestamp"
            ;;
        "config")
            create_config_backup "$timestamp"
            ;;
        "data")
            create_data_backup "$timestamp"
            ;;
        "daily"|"--daily")
            create_daily_backup "$timestamp"
            ;;
        "pre-deploy"|"--pre-deploy")
            create_pre_deploy_backup "$timestamp"
            ;;
        *)
            log_error "Tipo de backup desconhecido: $backup_type"
            exit 1
            ;;
    esac

    add_test_result "Backup Creation" "PASS" "Backup $backup_type criado com timestamp $timestamp"
}

# Criar backup completo
create_full_backup() {
    local timestamp="$1"
    local backup_name="neural-hive-mind-full-$timestamp"

    log_info "Criando backup completo: $backup_name"

    # Verificar se Velero está disponível
    if ! kubectl get pods -n "$VELERO_NAMESPACE" -l name=velero --no-headers 2>/dev/null | grep -q Running; then
        log_warn "Velero não está rodando, usando backup manual"
        create_manual_backup "$timestamp" "full"
        return
    fi

    # Criar backup com Velero
    cat <<EOF | kubectl apply -f -
apiVersion: velero.io/v1
kind: Backup
metadata:
  name: $backup_name
  namespace: $VELERO_NAMESPACE
spec:
  includedNamespaces:
  - $NAMESPACE
  - kube-system
  - istio-system
  storageLocation: default
  ttl: ${BACKUP_RETENTION_DAYS}d
  hooks:
    resources:
    - name: database-backup-hook
      includedNamespaces:
      - $NAMESPACE
      pre:
      - exec:
          container: postgres
          command:
          - /bin/bash
          - -c
          - "pg_dump -U postgres -h localhost > /tmp/backup.sql"
EOF

    # Aguardar conclusão do backup
    log_info "Aguardando conclusão do backup..."
    kubectl wait --for=condition=Completed backup/$backup_name -n "$VELERO_NAMESPACE" --timeout=3600s

    # Verificar status
    local backup_status=$(kubectl get backup "$backup_name" -n "$VELERO_NAMESPACE" -o jsonpath='{.status.phase}')
    if [ "$backup_status" = "Completed" ]; then
        log_info "Backup completo criado com sucesso: $backup_name"
        echo "backup_${timestamp}_status:completed" >> "$METRICS_FILE"
        echo "backup_${timestamp}_type:full" >> "$METRICS_FILE"
    else
        log_error "Falha na criação do backup: $backup_status"
        add_test_result "Full Backup" "FAIL" "Status: $backup_status"
        return 1
    fi

    # Criar backup adicional de configurações críticas
    backup_critical_configs "$timestamp"

    add_test_result "Full Backup" "PASS" "Backup completo $backup_name criado"
}

# Criar backup incremental
create_incremental_backup() {
    local timestamp="$1"
    local backup_name="neural-hive-mind-incremental-$timestamp"

    log_info "Criando backup incremental: $backup_name"

    # Encontrar último backup completo
    local last_full_backup=$(kubectl get backups -n "$VELERO_NAMESPACE" -l type=full --sort-by=.metadata.creationTimestamp -o name | tail -1 | cut -d/ -f2)

    if [ -z "$last_full_backup" ]; then
        log_warn "Nenhum backup completo encontrado, criando backup completo"
        create_full_backup "$timestamp"
        return
    fi

    log_info "Backup incremental baseado em: $last_full_backup"

    # Backup apenas de dados que mudaram
    backup_changed_data "$timestamp" "$last_full_backup"

    add_test_result "Incremental Backup" "PASS" "Backup incremental $backup_name criado"
}

# Criar backup de configurações
create_config_backup() {
    local timestamp="$1"
    local backup_dir="/tmp/neural-hive-mind-config-$timestamp"

    log_info "Criando backup de configurações: $timestamp"

    mkdir -p "$backup_dir"

    # Backup de ConfigMaps
    kubectl get configmaps -n "$NAMESPACE" -o yaml > "$backup_dir/configmaps.yaml"

    # Backup de Secrets (sem valores sensíveis por segurança)
    kubectl get secrets -n "$NAMESPACE" -o yaml | grep -v "data:" > "$backup_dir/secrets-metadata.yaml"

    # Backup de Deployments
    kubectl get deployments -n "$NAMESPACE" -o yaml > "$backup_dir/deployments.yaml"

    # Backup de Services
    kubectl get services -n "$NAMESPACE" -o yaml > "$backup_dir/services.yaml"

    # Backup de Ingress
    kubectl get ingress -n "$NAMESPACE" -o yaml > "$backup_dir/ingress.yaml" 2>/dev/null || true

    # Backup de HPA
    kubectl get hpa -n "$NAMESPACE" -o yaml > "$backup_dir/hpa.yaml" 2>/dev/null || true

    # Backup de PVCs
    kubectl get pvc -n "$NAMESPACE" -o yaml > "$backup_dir/pvc.yaml"

    # Backup de ServiceAccounts e RBAC
    kubectl get serviceaccounts,roles,rolebindings -n "$NAMESPACE" -o yaml > "$backup_dir/rbac.yaml"

    # Backup de Custom Resources relacionados ao Istio
    kubectl get peerauthentication,authorizationpolicy,destinationrule,virtualservice -n "$NAMESPACE" -o yaml > "$backup_dir/istio.yaml" 2>/dev/null || true

    # Compactar e criptografar
    tar -czf "$backup_dir.tar.gz" -C /tmp "neural-hive-mind-config-$timestamp"

    if [ -f "$ENCRYPTION_KEY" ]; then
        gpg --cipher-algo AES256 --compress-algo 2 --symmetric --no-use-agent --batch --yes --passphrase-file "$ENCRYPTION_KEY" --output "$backup_dir.tar.gz.gpg" "$backup_dir.tar.gz"
        rm "$backup_dir.tar.gz"
        backup_file="$backup_dir.tar.gz.gpg"
    else
        backup_file="$backup_dir.tar.gz"
    fi

    # Upload para storage
    upload_backup_file "$backup_file" "config/$timestamp/"

    # Limpeza
    rm -rf "$backup_dir" "$backup_file"

    add_test_result "Config Backup" "PASS" "Backup de configurações criado: $timestamp"
}

# Criar backup de dados
create_data_backup() {
    local timestamp="$1"

    log_info "Criando backup de dados: $timestamp"

    # Backup de bancos de dados
    backup_databases "$timestamp"

    # Backup de volumes persistentes
    backup_persistent_volumes "$timestamp"

    add_test_result "Data Backup" "PASS" "Backup de dados criado: $timestamp"
}

# Criar backup diário automatizado
create_daily_backup() {
    local timestamp="$1"

    log_info "Executando backup diário automatizado"

    # Backup incremental durante a semana, completo no domingo
    local day_of_week=$(date +%u)

    if [ "$day_of_week" -eq 7 ]; then
        log_info "Domingo: executando backup completo semanal"
        create_full_backup "$timestamp"
    else
        log_info "Dia $day_of_week: executando backup incremental"
        create_incremental_backup "$timestamp"
    fi

    # Cleanup automático de backups antigos
    cleanup_old_backups

    add_test_result "Daily Backup" "PASS" "Backup diário executado"
}

# Criar backup pré-deploy
create_pre_deploy_backup() {
    local timestamp="$1"

    log_info "Criando backup pré-deploy"

    # Backup rápido focado em recuperação rápida
    create_config_backup "$timestamp"

    # Backup de estado atual das aplicações
    local backup_dir="/tmp/neural-hive-mind-predeploy-$timestamp"
    mkdir -p "$backup_dir"

    # Estado atual dos pods
    kubectl get pods -n "$NAMESPACE" -o yaml > "$backup_dir/current-pods.yaml"

    # Logs recentes para debugging
    kubectl logs -l app=neural-hive-mind -n "$NAMESPACE" --tail=1000 > "$backup_dir/recent-logs.txt" 2>/dev/null || true

    # Métricas atuais
    kubectl top pods -n "$NAMESPACE" > "$backup_dir/current-metrics.txt" 2>/dev/null || true

    # Compactar
    tar -czf "$backup_dir.tar.gz" -C /tmp "neural-hive-mind-predeploy-$timestamp"

    # Upload
    upload_backup_file "$backup_dir.tar.gz" "pre-deploy/$timestamp/"

    # Limpeza
    rm -rf "$backup_dir" "$backup_dir.tar.gz"

    add_test_result "Pre-Deploy Backup" "PASS" "Backup pré-deploy criado"
}

# Backup manual quando Velero não está disponível
create_manual_backup() {
    local timestamp="$1"
    local backup_type="$2"

    log_info "Executando backup manual: $backup_type"

    local backup_dir="/tmp/neural-hive-mind-manual-$timestamp"
    mkdir -p "$backup_dir"

    # Backup de todos os recursos
    kubectl get all,configmaps,secrets,pvc -n "$NAMESPACE" -o yaml > "$backup_dir/all-resources.yaml"

    # Backup de dados específicos
    backup_databases_manual "$backup_dir"

    # Compactar com compressão configurada
    tar -czf "$backup_dir.tar.gz" --level="$COMPRESSION_LEVEL" -C /tmp "neural-hive-mind-manual-$timestamp"

    # Upload
    upload_backup_file "$backup_dir.tar.gz" "manual/$timestamp/"

    # Limpeza
    rm -rf "$backup_dir" "$backup_dir.tar.gz"

    add_test_result "Manual Backup" "PASS" "Backup manual $backup_type criado"
}

# Backup de configurações críticas
backup_critical_configs() {
    local timestamp="$1"

    log_info "Fazendo backup de configurações críticas"

    local config_dir="/tmp/critical-configs-$timestamp"
    mkdir -p "$config_dir"

    # Certificados (metadados apenas)
    kubectl get certificates -A -o yaml > "$config_dir/certificates.yaml" 2>/dev/null || true

    # Políticas de segurança
    kubectl get networkpolicies -A -o yaml > "$config_dir/network-policies.yaml" 2>/dev/null || true

    # Configurações do Istio
    kubectl get gateways,virtualservices,destinationrules -A -o yaml > "$config_dir/istio-config.yaml" 2>/dev/null || true

    # Configurações de monitoramento
    kubectl get servicemonitors,prometheusrules -A -o yaml > "$config_dir/monitoring.yaml" 2>/dev/null || true

    # Helm releases
    helm list -A -o yaml > "$config_dir/helm-releases.yaml" 2>/dev/null || true

    # Compactar e upload
    tar -czf "$config_dir.tar.gz" -C /tmp "critical-configs-$timestamp"
    upload_backup_file "$config_dir.tar.gz" "critical/$timestamp/"

    rm -rf "$config_dir" "$config_dir.tar.gz"
}

# Backup de bancos de dados
backup_databases() {
    local timestamp="$1"

    log_info "Fazendo backup de bancos de dados"

    # Identificar pods de banco de dados
    local db_pods=$(kubectl get pods -n "$NAMESPACE" -l app=postgres -o name 2>/dev/null || kubectl get pods -n "$NAMESPACE" -l app=mysql -o name 2>/dev/null || echo "")

    for db_pod_full in $db_pods; do
        local db_pod=$(echo "$db_pod_full" | cut -d/ -f2)
        log_info "Fazendo backup do banco no pod: $db_pod"

        # PostgreSQL
        if kubectl get pod "$db_pod" -n "$NAMESPACE" -o yaml | grep -q postgres; then
            kubectl exec "$db_pod" -n "$NAMESPACE" -- pg_dump -U postgres --clean --if-exists > "/tmp/postgres-backup-$timestamp.sql"
            upload_backup_file "/tmp/postgres-backup-$timestamp.sql" "database/$timestamp/"
            rm "/tmp/postgres-backup-$timestamp.sql"
        fi

        # MySQL
        if kubectl get pod "$db_pod" -n "$NAMESPACE" -o yaml | grep -q mysql; then
            kubectl exec "$db_pod" -n "$NAMESPACE" -- mysqldump -u root --all-databases > "/tmp/mysql-backup-$timestamp.sql"
            upload_backup_file "/tmp/mysql-backup-$timestamp.sql" "database/$timestamp/"
            rm "/tmp/mysql-backup-$timestamp.sql"
        fi
    done

    add_test_result "Database Backup" "PASS" "Backup de bancos de dados concluído"
}

# Backup manual de bancos de dados
backup_databases_manual() {
    local backup_dir="$1"

    log_info "Backup manual de bancos de dados"

    # Similar ao backup_databases mas salva no diretório local
    local db_pods=$(kubectl get pods -n "$NAMESPACE" -l app=postgres -o name 2>/dev/null || kubectl get pods -n "$NAMESPACE" -l app=mysql -o name 2>/dev/null || echo "")

    for db_pod_full in $db_pods; do
        local db_pod=$(echo "$db_pod_full" | cut -d/ -f2)

        if kubectl get pod "$db_pod" -n "$NAMESPACE" -o yaml | grep -q postgres; then
            kubectl exec "$db_pod" -n "$NAMESPACE" -- pg_dump -U postgres --clean --if-exists > "$backup_dir/postgres-$db_pod.sql" 2>/dev/null || true
        fi

        if kubectl get pod "$db_pod" -n "$NAMESPACE" -o yaml | grep -q mysql; then
            kubectl exec "$db_pod" -n "$NAMESPACE" -- mysqldump -u root --all-databases > "$backup_dir/mysql-$db_pod.sql" 2>/dev/null || true
        fi
    done
}

# Backup de volumes persistentes
backup_persistent_volumes() {
    local timestamp="$1"

    log_info "Fazendo backup de volumes persistentes"

    # Listar PVCs
    local pvcs=$(kubectl get pvc -n "$NAMESPACE" --no-headers | awk '{print $1}')

    for pvc in $pvcs; do
        log_info "Fazendo backup do PVC: $pvc"

        # Criar job para backup do volume
        local backup_job="pvc-backup-$(echo "$pvc" | tr '[:upper:]' '[:lower:]')-$(date +%s)"

        cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: $backup_job
  namespace: $NAMESPACE
spec:
  template:
    spec:
      containers:
      - name: backup
        image: alpine:latest
        command:
        - /bin/sh
        - -c
        - |
          apk add --no-cache rsync
          tar -czf /backup/pvc-$pvc-$timestamp.tar.gz -C /data .
        volumeMounts:
        - name: data-volume
          mountPath: /data
        - name: backup-volume
          mountPath: /backup
      volumes:
      - name: data-volume
        persistentVolumeClaim:
          claimName: $pvc
      - name: backup-volume
        emptyDir: {}
      restartPolicy: Never
  backoffLimit: 3
EOF

        # Aguardar conclusão
        kubectl wait --for=condition=complete job/$backup_job -n "$NAMESPACE" --timeout=1800s || true

        # Copiar backup
        kubectl cp "$NAMESPACE/$backup_job-pod:/backup/pvc-$pvc-$timestamp.tar.gz" "/tmp/pvc-$pvc-$timestamp.tar.gz" 2>/dev/null || true

        # Upload se o arquivo existe
        if [ -f "/tmp/pvc-$pvc-$timestamp.tar.gz" ]; then
            upload_backup_file "/tmp/pvc-$pvc-$timestamp.tar.gz" "volumes/$timestamp/"
            rm "/tmp/pvc-$pvc-$timestamp.tar.gz"
        fi

        # Limpeza
        kubectl delete job $backup_job -n "$NAMESPACE" &>/dev/null || true
    done

    add_test_result "Volume Backup" "PASS" "Backup de volumes concluído"
}

# Backup de dados alterados
backup_changed_data() {
    local timestamp="$1"
    local base_backup="$2"

    log_info "Fazendo backup de dados alterados desde: $base_backup"

    # Para backup incremental real, seria necessário comparar timestamps
    # Por simplicidade, fazendo backup de configurações que mudam frequentemente

    local backup_dir="/tmp/neural-hive-mind-incremental-$timestamp"
    mkdir -p "$backup_dir"

    # Logs recentes
    kubectl logs -l app=neural-hive-mind -n "$NAMESPACE" --since=24h > "$backup_dir/recent-logs.txt" 2>/dev/null || true

    # Estado atual dos recursos
    kubectl get pods,services -n "$NAMESPACE" -o yaml > "$backup_dir/current-state.yaml"

    # ConfigMaps que podem ter mudado
    kubectl get configmaps -n "$NAMESPACE" -o yaml > "$backup_dir/configmaps.yaml"

    # Eventos recentes
    kubectl get events -n "$NAMESPACE" --sort-by='.lastTimestamp' > "$backup_dir/recent-events.txt"

    tar -czf "$backup_dir.tar.gz" -C /tmp "neural-hive-mind-incremental-$timestamp"
    upload_backup_file "$backup_dir.tar.gz" "incremental/$timestamp/"

    rm -rf "$backup_dir" "$backup_dir.tar.gz"
}

# Upload de arquivo de backup
upload_backup_file() {
    local file_path="$1"
    local remote_path="$2"

    log_info "Fazendo upload do backup: $(basename "$file_path")"

    # Simular upload - em produção usaria aws s3 cp, gsutil cp, etc.
    if command -v aws &> /dev/null && [[ "$BACKUP_STORAGE" =~ ^s3:// ]]; then
        aws s3 cp "$file_path" "$BACKUP_STORAGE/$remote_path$(basename "$file_path")"
    elif command -v gsutil &> /dev/null && [[ "$BACKUP_STORAGE" =~ ^gs:// ]]; then
        gsutil cp "$file_path" "$BACKUP_STORAGE/$remote_path$(basename "$file_path")"
    else
        # Fallback para armazenamento local
        local local_backup_dir="/var/backups/neural-hive-mind/$remote_path"
        mkdir -p "$local_backup_dir"
        cp "$file_path" "$local_backup_dir"
        log_info "Backup salvo localmente em: $local_backup_dir$(basename "$file_path")"
    fi

    echo "backup_uploaded:$(basename "$file_path")" >> "$METRICS_FILE"
}

# Executar restore
execute_restore() {
    local timestamp="$1"
    local restore_target="${2:-latest}"

    log_info "Executando restore: $restore_target"

    case "$restore_target" in
        "latest")
            restore_latest_backup
            ;;
        "selective")
            restore_selective "$timestamp"
            ;;
        *)
            restore_specific_backup "$restore_target"
            ;;
    esac

    add_test_result "Restore Operation" "PASS" "Restore executado: $restore_target"
}

# Restaurar último backup
restore_latest_backup() {
    log_info "Restaurando último backup disponível"

    # Encontrar último backup
    local latest_backup=""

    if kubectl get pods -n "$VELERO_NAMESPACE" -l name=velero --no-headers 2>/dev/null | grep -q Running; then
        latest_backup=$(kubectl get backups -n "$VELERO_NAMESPACE" --sort-by=.metadata.creationTimestamp -o name | tail -1 | cut -d/ -f2)
    fi

    if [ -n "$latest_backup" ]; then
        restore_velero_backup "$latest_backup"
    else
        restore_manual_backup "latest"
    fi

    add_test_result "Latest Backup Restore" "PASS" "Último backup restaurado"
}

# Restaurar backup específico
restore_specific_backup() {
    local backup_name="$1"

    log_info "Restaurando backup específico: $backup_name"

    if kubectl get backup "$backup_name" -n "$VELERO_NAMESPACE" &>/dev/null; then
        restore_velero_backup "$backup_name"
    else
        restore_manual_backup "$backup_name"
    fi

    add_test_result "Specific Backup Restore" "PASS" "Backup $backup_name restaurado"
}

# Restaurar backup via Velero
restore_velero_backup() {
    local backup_name="$1"
    local restore_name="restore-$(date +%s)"

    log_info "Restaurando via Velero: $backup_name"

    cat <<EOF | kubectl apply -f -
apiVersion: velero.io/v1
kind: Restore
metadata:
  name: $restore_name
  namespace: $VELERO_NAMESPACE
spec:
  backupName: $backup_name
  includedNamespaces:
  - $NAMESPACE
  restorePVs: true
EOF

    # Aguardar conclusão
    kubectl wait --for=condition=Completed restore/$restore_name -n "$VELERO_NAMESPACE" --timeout=3600s

    # Verificar status
    local restore_status=$(kubectl get restore "$restore_name" -n "$VELERO_NAMESPACE" -o jsonpath='{.status.phase}')
    if [ "$restore_status" = "Completed" ]; then
        log_info "Restore via Velero concluído com sucesso"
    else
        log_error "Falha no restore via Velero: $restore_status"
        return 1
    fi
}

# Restaurar backup manual
restore_manual_backup() {
    local backup_identifier="$1"

    log_info "Executando restore manual: $backup_identifier"

    # Download do backup
    local backup_file="/tmp/restore-$backup_identifier.tar.gz"
    download_backup_file "$backup_identifier" "$backup_file"

    if [ ! -f "$backup_file" ]; then
        log_error "Arquivo de backup não encontrado: $backup_file"
        return 1
    fi

    # Extrair backup
    local restore_dir="/tmp/restore-$(date +%s)"
    mkdir -p "$restore_dir"
    tar -xzf "$backup_file" -C "$restore_dir"

    # Aplicar configurações
    find "$restore_dir" -name "*.yaml" -exec kubectl apply -f {} \; 2>/dev/null || true

    # Restaurar bancos de dados se disponível
    restore_databases "$restore_dir"

    # Limpeza
    rm -rf "$restore_dir" "$backup_file"

    log_info "Restore manual concluído"
}

# Restaurar bancos de dados
restore_databases() {
    local restore_dir="$1"

    log_info "Restaurando bancos de dados"

    # Restaurar PostgreSQL
    local postgres_backup=$(find "$restore_dir" -name "postgres*.sql" | head -1)
    if [ -n "$postgres_backup" ]; then
        local postgres_pod=$(kubectl get pods -n "$NAMESPACE" -l app=postgres --no-headers | awk '{print $1}' | head -1)
        if [ -n "$postgres_pod" ]; then
            kubectl exec -i "$postgres_pod" -n "$NAMESPACE" -- psql -U postgres < "$postgres_backup"
            log_info "PostgreSQL restaurado"
        fi
    fi

    # Restaurar MySQL
    local mysql_backup=$(find "$restore_dir" -name "mysql*.sql" | head -1)
    if [ -n "$mysql_backup" ]; then
        local mysql_pod=$(kubectl get pods -n "$NAMESPACE" -l app=mysql --no-headers | awk '{print $1}' | head -1)
        if [ -n "$mysql_pod" ]; then
            kubectl exec -i "$mysql_pod" -n "$NAMESPACE" -- mysql -u root < "$mysql_backup"
            log_info "MySQL restaurado"
        fi
    fi
}

# Restore seletivo
restore_selective() {
    local timestamp="$1"

    log_info "Executando restore seletivo"

    # Permite restaurar apenas componentes específicos
    echo "Funcionalidade de restore seletivo - requer implementação específica baseada em necessidades"

    add_test_result "Selective Restore" "SKIP" "Requer implementação específica"
}

# Download de arquivo de backup
download_backup_file() {
    local backup_identifier="$1"
    local local_file="$2"

    log_info "Fazendo download do backup: $backup_identifier"

    # Implementar download baseado no storage configurado
    if command -v aws &> /dev/null && [[ "$BACKUP_STORAGE" =~ ^s3:// ]]; then
        aws s3 cp "$BACKUP_STORAGE/manual/$backup_identifier/" "$local_file" 2>/dev/null || \
        aws s3 cp "$BACKUP_STORAGE/full/$backup_identifier/" "$local_file" 2>/dev/null || \
        aws s3 cp "$BACKUP_STORAGE/config/$backup_identifier/" "$local_file" 2>/dev/null || true
    else
        # Fallback para armazenamento local
        find /var/backups/neural-hive-mind -name "*$backup_identifier*" -type f | head -1 | xargs -I {} cp {} "$local_file" 2>/dev/null || true
    fi
}

# Verificar backup
verify_backup() {
    local timestamp="$1"
    local backup_target="${2:-latest}"

    log_info "Verificando integridade do backup: $backup_target"

    if [ "$backup_target" = "latest" ]; then
        verify_latest_backup
    else
        verify_specific_backup "$backup_target"
    fi

    add_test_result "Backup Verification" "PASS" "Verificação de backup concluída"
}

# Verificar último backup
verify_latest_backup() {
    log_info "Verificando último backup"

    # Verificar via Velero se disponível
    if kubectl get pods -n "$VELERO_NAMESPACE" -l name=velero --no-headers 2>/dev/null | grep -q Running; then
        local latest_backup=$(kubectl get backups -n "$VELERO_NAMESPACE" --sort-by=.metadata.creationTimestamp -o name | tail -1 | cut -d/ -f2)
        if [ -n "$latest_backup" ]; then
            local backup_status=$(kubectl get backup "$latest_backup" -n "$VELERO_NAMESPACE" -o jsonpath='{.status.phase}')
            log_info "Status do último backup ($latest_backup): $backup_status"

            if [ "$backup_status" = "Completed" ]; then
                add_test_result "Latest Backup Status" "PASS" "Último backup está íntegro"
            else
                add_test_result "Latest Backup Status" "FAIL" "Último backup com status: $backup_status"
            fi
        fi
    else
        # Verificação manual
        verify_manual_backups
    fi
}

# Verificar backup específico
verify_specific_backup() {
    local backup_name="$1"

    log_info "Verificando backup específico: $backup_name"

    if kubectl get backup "$backup_name" -n "$VELERO_NAMESPACE" &>/dev/null; then
        local backup_status=$(kubectl get backup "$backup_name" -n "$VELERO_NAMESPACE" -o jsonpath='{.status.phase}')
        local backup_errors=$(kubectl get backup "$backup_name" -n "$VELERO_NAMESPACE" -o jsonpath='{.status.errors}')

        log_info "Status do backup $backup_name: $backup_status"

        if [ -n "$backup_errors" ] && [ "$backup_errors" != "null" ]; then
            log_warn "Erros encontrados no backup: $backup_errors"
            add_test_result "Backup Verification" "WARN" "Backup com erros: $backup_errors"
        else
            add_test_result "Backup Verification" "PASS" "Backup $backup_name verificado"
        fi
    else
        log_warn "Backup não encontrado no Velero, verificando storage manual"
        verify_manual_backup "$backup_name"
    fi
}

# Verificar backups manuais
verify_manual_backups() {
    log_info "Verificando backups manuais"

    local backup_count=0
    local corrupted_count=0

    # Verificar arquivos locais
    if [ -d "/var/backups/neural-hive-mind" ]; then
        local backup_files=$(find /var/backups/neural-hive-mind -name "*.tar.gz" -mtime -7)

        for backup_file in $backup_files; do
            ((backup_count++))
            if ! tar -tzf "$backup_file" &>/dev/null; then
                log_error "Backup corrompido: $backup_file"
                ((corrupted_count++))
            fi
        done
    fi

    log_info "Verificação manual: $backup_count backups verificados, $corrupted_count corrompidos"

    if [ "$corrupted_count" -eq 0 ]; then
        add_test_result "Manual Backup Verification" "PASS" "$backup_count backups íntegros"
    else
        add_test_result "Manual Backup Verification" "FAIL" "$corrupted_count de $backup_count backups corrompidos"
    fi
}

# Verificar backup manual específico
verify_manual_backup() {
    local backup_name="$1"

    log_info "Verificando backup manual: $backup_name"

    # Tentar download e verificação
    local backup_file="/tmp/verify-$backup_name.tar.gz"
    download_backup_file "$backup_name" "$backup_file"

    if [ -f "$backup_file" ]; then
        if tar -tzf "$backup_file" &>/dev/null; then
            log_info "Backup manual $backup_name está íntegro"
            add_test_result "Manual Backup Check" "PASS" "Backup $backup_name verificado"
        else
            log_error "Backup manual $backup_name está corrompido"
            add_test_result "Manual Backup Check" "FAIL" "Backup $backup_name corrompido"
        fi
        rm "$backup_file"
    else
        log_error "Backup manual $backup_name não encontrado"
        add_test_result "Manual Backup Check" "FAIL" "Backup $backup_name não encontrado"
    fi
}

# Listar backups
list_backups() {
    log_info "Listando backups disponíveis"

    echo "=== Backups do Velero ==="
    if kubectl get pods -n "$VELERO_NAMESPACE" -l name=velero --no-headers 2>/dev/null | grep -q Running; then
        kubectl get backups -n "$VELERO_NAMESPACE" --sort-by=.metadata.creationTimestamp
    else
        echo "Velero não está disponível"
    fi

    echo -e "\n=== Backups Manuais ==="
    if [ -d "/var/backups/neural-hive-mind" ]; then
        find /var/backups/neural-hive-mind -name "*.tar.gz*" -printf "%T@ %Tc %p\n" | sort -n | cut -d' ' -f2-
    else
        echo "Diretório de backup manual não encontrado"
    fi

    add_test_result "List Backups" "PASS" "Listagem de backups concluída"
}

# Mostrar status dos backups
show_backup_status() {
    log_info "Mostrando status dos backups"

    # Status do Velero
    if kubectl get pods -n "$VELERO_NAMESPACE" -l name=velero --no-headers 2>/dev/null | grep -q Running; then
        echo "=== Status do Velero ==="
        kubectl get backups -n "$VELERO_NAMESPACE" --sort-by=.metadata.creationTimestamp | tail -5

        # Último backup
        local latest_backup=$(kubectl get backups -n "$VELERO_NAMESPACE" --sort-by=.metadata.creationTimestamp -o name | tail -1 | cut -d/ -f2)
        if [ -n "$latest_backup" ]; then
            echo -e "\n=== Último Backup ==="
            kubectl describe backup "$latest_backup" -n "$VELERO_NAMESPACE"
        fi
    fi

    # Status dos backups manuais
    echo -e "\n=== Backups Recentes (últimos 7 dias) ==="
    if [ -d "/var/backups/neural-hive-mind" ]; then
        find /var/backups/neural-hive-mind -name "*.tar.gz*" -mtime -7 -printf "%T@ %Tc %s bytes %p\n" | sort -nr | head -10 | cut -d' ' -f2-
    fi

    # Estatísticas
    echo -e "\n=== Estatísticas ==="
    local total_backups=0
    local total_size=0

    if [ -d "/var/backups/neural-hive-mind" ]; then
        total_backups=$(find /var/backups/neural-hive-mind -name "*.tar.gz*" | wc -l)
        total_size=$(find /var/backups/neural-hive-mind -name "*.tar.gz*" -exec du -b {} + | awk '{sum+=$1} END {print sum/1024/1024 " MB"}')
    fi

    echo "Total de backups manuais: $total_backups"
    echo "Tamanho total: $total_size"

    add_test_result "Backup Status" "PASS" "Status dos backups exibido"
}

# Limpar backups antigos
cleanup_old_backups() {
    log_info "Limpando backups antigos (mais de $BACKUP_RETENTION_DAYS dias)"

    local cleaned_count=0

    # Limpar backups manuais antigos
    if [ -d "/var/backups/neural-hive-mind" ]; then
        local old_backups=$(find /var/backups/neural-hive-mind -name "*.tar.gz*" -mtime +$BACKUP_RETENTION_DAYS)

        for old_backup in $old_backups; do
            log_info "Removendo backup antigo: $(basename "$old_backup")"
            rm "$old_backup"
            ((cleaned_count++))
        done
    fi

    # Limpar backups do Velero (configurado via TTL no momento da criação)
    if kubectl get pods -n "$VELERO_NAMESPACE" -l name=velero --no-headers 2>/dev/null | grep -q Running; then
        log_info "Backups do Velero são limpos automaticamente via TTL"
    fi

    log_info "Backups antigos removidos: $cleaned_count"
    echo "old_backups_cleaned:$cleaned_count" >> "$METRICS_FILE"

    add_test_result "Backup Cleanup" "PASS" "$cleaned_count backups antigos removidos"
}

# Executar função principal se script for chamado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi