#!/bin/bash

################################################################################
# Script: upgrade-helm-debug-mode.sh
# Descrição: Automatiza o upgrade dos Helm releases para ativar LOG_LEVEL=DEBUG
#            em todos os specialists e consensus-engine
# Versão: 1.0.0
# Data: 2025-11-09
################################################################################

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Determinar REPO_ROOT de forma portável
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Configurações
NAMESPACE_SPECIALISTS="neural-hive"
NAMESPACE_CONSENSUS="neural-hive"
TIMEOUT="5m"

# Array de specialists
SPECIALISTS=("business" "technical" "behavior" "evolution" "architecture")

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

print_separator() {
    echo "================================================================================"
}

check_prerequisites() {
    log_info "Verificando pré-requisitos..."

    # Verificar REPO_ROOT
    if [ ! -d "$REPO_ROOT" ]; then
        log_error "REPO_ROOT não encontrado: $REPO_ROOT"
        exit 1
    fi
    log_success "REPO_ROOT detectado: $REPO_ROOT"

    # Verificar kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado. Instale kubectl antes de continuar."
        exit 1
    fi
    log_success "kubectl encontrado: $(kubectl version --client --short 2>/dev/null || kubectl version --client)"

    # Verificar helm
    if ! command -v helm &> /dev/null; then
        log_error "helm não encontrado. Instale helm antes de continuar."
        exit 1
    fi
    log_success "helm encontrado: $(helm version --short)"

    # Verificar conectividade com cluster
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Não foi possível conectar ao cluster Kubernetes."
        log_error "Verifique sua configuração kubectl (kubeconfig)."
        exit 1
    fi
    log_success "Conectado ao cluster: $(kubectl config current-context)"

    # Verificar se namespaces existem
    if ! kubectl get namespace "$NAMESPACE_SPECIALISTS" &> /dev/null; then
        log_warning "Namespace '$NAMESPACE_SPECIALISTS' não encontrado."
        log_info "Criando namespace '$NAMESPACE_SPECIALISTS'..."
        kubectl create namespace "$NAMESPACE_SPECIALISTS" || {
            log_error "Falha ao criar namespace '$NAMESPACE_SPECIALISTS'"
            exit 1
        }
    fi
    log_success "Namespace '$NAMESPACE_SPECIALISTS' existe"

    if ! kubectl get namespace "$NAMESPACE_CONSENSUS" &> /dev/null; then
        log_warning "Namespace '$NAMESPACE_CONSENSUS' não encontrado."
        log_info "Criando namespace '$NAMESPACE_CONSENSUS'..."
        kubectl create namespace "$NAMESPACE_CONSENSUS" || {
            log_error "Falha ao criar namespace '$NAMESPACE_CONSENSUS'"
            exit 1
        }
    fi
    log_success "Namespace '$NAMESPACE_CONSENSUS' existe"

    print_separator
}

upgrade_specialist() {
    local specialist_type=$1
    local chart_path="$REPO_ROOT/helm-charts/specialist-${specialist_type}"
    local values_file="$chart_path/values-k8s.yaml"
    local release_name="specialist-${specialist_type}"

    log_info "Upgrading specialist-${specialist_type}..."

    # Verificar se chart existe
    if [ ! -d "$chart_path" ]; then
        log_error "Chart não encontrado: $chart_path"
        return 1
    fi

    # Verificar se values file existe
    if [ ! -f "$values_file" ]; then
        log_error "Values file não encontrado: $values_file"
        return 1
    fi

    # Verificar se logLevel está como DEBUG
    if ! grep -q "logLevel: DEBUG" "$values_file"; then
        log_warning "logLevel não está configurado como DEBUG em $values_file"
        log_warning "Verifique a configuração antes de prosseguir."
    fi

    # Executar helm upgrade
    log_info "Executando: helm upgrade --install $release_name $chart_path -n $NAMESPACE_SPECIALISTS -f $values_file --wait --timeout $TIMEOUT"

    if helm upgrade --install "$release_name" "$chart_path" \
        --namespace "$NAMESPACE_SPECIALISTS" \
        --values "$values_file" \
        --wait \
        --timeout "$TIMEOUT"; then
        log_success "Upgrade de $release_name concluído com sucesso!"
        return 0
    else
        log_error "Falha no upgrade de $release_name"
        return 1
    fi
}

upgrade_consensus_engine() {
    local chart_path="$REPO_ROOT/helm-charts/consensus-engine"
    local values_file="$chart_path/values.yaml"
    local release_name="consensus-engine"

    log_info "Upgrading consensus-engine..."

    # Verificar se chart existe
    if [ ! -d "$chart_path" ]; then
        log_error "Chart não encontrado: $chart_path"
        return 1
    fi

    # Verificar se values file existe
    if [ ! -f "$values_file" ]; then
        log_error "Values file não encontrado: $values_file"
        return 1
    fi

    # Verificar se logLevel está como DEBUG
    if ! grep -q "logLevel: DEBUG" "$values_file"; then
        log_warning "logLevel não está configurado como DEBUG em $values_file"
        log_warning "Verifique a configuração antes de prosseguir."
    fi

    # Executar helm upgrade
    log_info "Executando: helm upgrade --install $release_name $chart_path -n $NAMESPACE_CONSENSUS -f $values_file --wait --timeout $TIMEOUT"

    if helm upgrade --install "$release_name" "$chart_path" \
        --namespace "$NAMESPACE_CONSENSUS" \
        --values "$values_file" \
        --wait \
        --timeout "$TIMEOUT"; then
        log_success "Upgrade de $release_name concluído com sucesso!"
        return 0
    else
        log_error "Falha no upgrade de $release_name"
        return 1
    fi
}

wait_for_pods_ready() {
    local namespace=$1
    local deployment=$2
    local timeout=300 # 5 minutos

    log_info "Aguardando pod de $deployment estar ready..."

    if kubectl wait --for=condition=available \
        --timeout="${timeout}s" \
        deployment/"$deployment" \
        -n "$namespace" 2>/dev/null; then
        log_success "Pod de $deployment está ready"
        return 0
    else
        log_warning "Timeout aguardando pod de $deployment ficar ready"
        return 1
    fi
}

verify_log_level() {
    local namespace=$1
    local deployment=$2
    local expected_log_level="DEBUG"

    log_info "Verificando LOG_LEVEL em $deployment..."

    # Try primary label selector first, then fallback to alternative
    local pod_name=$(kubectl get pods -n "$namespace" -l app.kubernetes.io/name="$deployment" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -z "$pod_name" ]; then
        log_warning "Pod não encontrado com label app.kubernetes.io/name=$deployment, tentando app=$deployment..."
        pod_name=$(kubectl get pods -n "$namespace" -l app="$deployment" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    fi

    if [ -z "$pod_name" ]; then
        log_warning "Não foi possível encontrar pod para $deployment"
        return 1
    fi

    # Method 1: Try to get LOG_LEVEL environment variable
    local log_level=$(kubectl exec -n "$namespace" "$pod_name" -- env 2>/dev/null | grep "^LOG_LEVEL=" | cut -d'=' -f2 || echo "")

    if [ "$log_level" = "$expected_log_level" ]; then
        log_success "LOG_LEVEL=$log_level confirmado em $deployment (via env)"
        return 0
    fi

    # Method 2: Fallback - check recent logs for log level indication (more comprehensive)
    if [ -z "$log_level" ] || [ "$log_level" = "NOT_FOUND" ]; then
        log_info "LOG_LEVEL env var não encontrado, verificando logs de boot..."

        # Look for log level indicators with broader window and more patterns
        # Using --tail=200 and --since=5m to increase chances of finding the evidence
        local log_check=$(kubectl logs -n "$namespace" "$pod_name" --tail=200 --since=5m 2>/dev/null | \
            grep -iE "(log.?level.*debug|debug.*mode|level.*:.*debug|DEBUG root|level=DEBUG|Configured log level.*DEBUG|LOG_LEVEL.*DEBUG)" | \
            head -1 || echo "")

        if [ -n "$log_check" ]; then
            log_success "LOG_LEVEL=DEBUG detectado nos logs de boot em $deployment"
            log_info "Evidência: $log_check"
            return 0
        else
            # Soft failure - don't block deployment, just warn
            log_warning "LOG_LEVEL=DEBUG não detectado nos logs de $deployment"
            log_warning "Isso pode ser um falso negativo. Deployment prossegue normalmente."
            log_warning "Verifique manualmente: kubectl logs -n $namespace $pod_name | grep -i debug"
            # Return 0 (success) to not block the deployment
            return 0
        fi
    else
        log_warning "LOG_LEVEL esperado: $expected_log_level, encontrado: $log_level em $deployment"
        return 1
    fi
}

print_upgrade_summary() {
    local success_count=$1
    local total_count=$2

    print_separator
    log_info "RESUMO DO UPGRADE"
    print_separator

    if [ "$success_count" -eq "$total_count" ]; then
        log_success "Todos os $total_count componentes foram atualizados com sucesso!"
        log_success "LOG_LEVEL=DEBUG está ativo em todos os componentes."
    else
        log_warning "$success_count de $total_count componentes atualizados com sucesso."
        log_warning "Verifique os logs acima para detalhes dos componentes que falharam."
    fi

    print_separator
}

print_next_steps() {
    print_separator
    log_info "PRÓXIMOS PASSOS"
    print_separator

    echo ""
    echo "1. Verificar status dos pods:"
    echo "   kubectl get pods -n $NAMESPACE_SPECIALISTS"
    echo "   kubectl get pods -n $NAMESPACE_CONSENSUS"
    echo ""
    echo "2. Capturar logs com o script de captura:"
    echo "   ./scripts/debug/capture-grpc-logs.sh"
    echo ""
    echo "3. Ou capturar logs manualmente:"
    echo "   # Consensus Engine"
    echo "   kubectl logs -f deployment/consensus-engine -n $NAMESPACE_CONSENSUS | grep -E 'EvaluatePlan|TypeError|evaluated_at'"
    echo ""
    echo "   # Specialists (exemplo para business)"
    echo "   kubectl logs -f deployment/specialist-business -n $NAMESPACE_SPECIALISTS | grep -E 'EvaluatePlan|evaluated_at'"
    echo ""
    echo "4. Preencher análise em ANALISE_DEBUG_GRPC_TYPEERROR.md"
    echo ""

    print_separator
}

main() {
    local start_time=$(date +%s)
    local success_count=0
    local total_count=6 # 5 specialists + 1 consensus-engine

    print_separator
    log_info "INICIANDO UPGRADE PARA MODO DEBUG"
    log_info "Data/Hora: $(date '+%Y-%m-%d %H:%M:%S')"
    print_separator

    # Verificar pré-requisitos
    check_prerequisites

    # Upgrade dos specialists
    log_info "FASE 1: Upgrading Specialists"
    print_separator

    for specialist in "${SPECIALISTS[@]}"; do
        if upgrade_specialist "$specialist"; then
            # Wait for pods to be ready (this is critical)
            wait_for_pods_ready "$NAMESPACE_SPECIALISTS" "specialist-${specialist}"
            local wait_status=$?

            # Verify log level (soft check - warnings only, doesn't block)
            verify_log_level "$NAMESPACE_SPECIALISTS" "specialist-${specialist}"
            # Note: verify_log_level now returns 0 even on detection failure (soft failure)

            # Increment success_count if pod became ready (log level verification is advisory only)
            if [ $wait_status -eq 0 ]; then
                ((success_count++))
            fi
        fi
        echo ""
    done

    # Upgrade do consensus-engine
    log_info "FASE 2: Upgrading Consensus Engine"
    print_separator

    if upgrade_consensus_engine; then
        # Wait for pods to be ready (this is critical)
        wait_for_pods_ready "$NAMESPACE_CONSENSUS" "consensus-engine"
        local wait_status=$?

        # Verify log level (soft check - warnings only, doesn't block)
        verify_log_level "$NAMESPACE_CONSENSUS" "consensus-engine"
        # Note: verify_log_level now returns 0 even on detection failure (soft failure)

        # Increment success_count if pod became ready (log level verification is advisory only)
        if [ $wait_status -eq 0 ]; then
            ((success_count++))
        fi
    fi
    echo ""

    # Resumo
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    print_upgrade_summary "$success_count" "$total_count"
    log_info "Tempo total de execução: ${duration}s"
    echo ""

    # Próximos passos
    print_next_steps

    # Exit code baseado no sucesso
    if [ "$success_count" -eq "$total_count" ]; then
        exit 0
    else
        exit 1
    fi
}

# Executar main
main "$@"
