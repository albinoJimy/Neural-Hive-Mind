#!/bin/bash
# Testa execução manual dos CronJobs de ML Retraining
# Uso: ./scripts/test-cronjob-manual.sh [trigger|retraining|all]

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuração
TRIGGER_NAMESPACE="neural-hive-mind"
RETRAINING_NAMESPACE="mlflow"
TARGET_JOB=""

# Parse argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        trigger|retraining|all)
            TARGET_JOB=$1
            shift
            ;;
        -h|--help)
            echo "Uso: $0 [trigger|retraining|all]"
            echo ""
            echo "Opções:"
            echo "  trigger     - Testa apenas retraining-trigger-checker"
            echo "  retraining  - Testa apenas specialist-models-retraining"
            echo "  all         - Testa ambos (padrão)"
            exit 0
            ;;
        *)
            echo "Argumento inválido: $1"
            echo "Use --help para ver opções"
            exit 1
            ;;
    esac
done

# Default: testar todos
if [ -z "$TARGET_JOB" ]; then
    TARGET_JOB="all"
fi

# Função para criar job manual a partir de CronJob
create_manual_job() {
    local cronjob_name=$1
    local namespace=$2
    local job_name="${cronjob_name}-manual-$(date +%s)"

    echo -e "${YELLOW}Criando job manual: $job_name${NC}" >&2

    kubectl create job "$job_name" \
        --from=cronjob/"$cronjob_name" \
        -n "$namespace" \
        -o name 2>&1 >&2

    echo "$job_name"
}

# Função para monitorar job
monitor_job() {
    local job_name=$1
    local namespace=$2
    local timeout=600  # 10 minutos
    local elapsed=0

    echo -e "${YELLOW}Monitorando job: $job_name${NC}"
    echo ""

    while [ $elapsed -lt $timeout ]; do
        # Obter status do job
        status=$(kubectl get job "$job_name" -n "$namespace" -o jsonpath='{.status.conditions[0].type}' 2>/dev/null || echo "")

        if [ "$status" = "Complete" ]; then
            echo -e "${GREEN}✓ Job completado com sucesso${NC}"
            return 0
        elif [ "$status" = "Failed" ]; then
            echo -e "${RED}✗ Job falhou${NC}"
            return 1
        fi

        # Mostrar progresso
        echo -n "."
        sleep 5
        elapsed=$((elapsed + 5))
    done

    echo -e "${RED}✗ Timeout após ${timeout}s${NC}"
    return 1
}

# Função para mostrar logs
show_logs() {
    local job_name=$1
    local namespace=$2

    echo ""
    echo "=========================================="
    echo "Logs do Job: $job_name"
    echo "=========================================="

    # Obter pod do job
    pod_name=$(kubectl get pods -n "$namespace" \
        --selector=job-name="$job_name" \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -z "$pod_name" ]; then
        echo -e "${RED}✗ Pod não encontrado${NC}"
        return 1
    fi

    # Mostrar logs
    kubectl logs -n "$namespace" "$pod_name" --tail=50

    echo ""
    echo "=========================================="
}

# Função para limpar job
cleanup_job() {
    local job_name=$1
    local namespace=$2

    echo -e "${YELLOW}Limpando job: $job_name${NC}"
    kubectl delete job "$job_name" -n "$namespace" --ignore-not-found=true
}

# Função para testar retraining trigger
test_retraining_trigger() {
    echo ""
    echo "=========================================="
    echo "Testando Retraining Trigger Checker"
    echo "=========================================="

    # Verificar se CronJob existe
    if ! kubectl get cronjob retraining-trigger-checker -n "$TRIGGER_NAMESPACE" &>/dev/null; then
        echo -e "${RED}✗ CronJob retraining-trigger-checker não encontrado${NC}"
        return 1
    fi

    # Criar job manual
    job_name=$(create_manual_job "retraining-trigger-checker" "$TRIGGER_NAMESPACE")

    # Monitorar execução
    if monitor_job "$job_name" "$TRIGGER_NAMESPACE"; then
        show_logs "$job_name" "$TRIGGER_NAMESPACE"
        cleanup_job "$job_name" "$TRIGGER_NAMESPACE"
        return 0
    else
        show_logs "$job_name" "$TRIGGER_NAMESPACE"
        cleanup_job "$job_name" "$TRIGGER_NAMESPACE"
        return 1
    fi
}

# Função para testar specialist retraining
test_specialist_retraining() {
    echo ""
    echo "=========================================="
    echo "Testando Specialist Models Retraining"
    echo "=========================================="

    # Verificar se CronJob existe
    if ! kubectl get cronjob specialist-models-retraining -n "$RETRAINING_NAMESPACE" &>/dev/null; then
        echo -e "${RED}✗ CronJob specialist-models-retraining não encontrado${NC}"
        return 1
    fi

    # Verificar se PVC existe
    if ! kubectl get pvc ml-training-data-pvc -n "$RETRAINING_NAMESPACE" &>/dev/null; then
        echo -e "${YELLOW}⚠ PVC ml-training-data-pvc não encontrado - job pode falhar${NC}"
    fi

    # Criar job manual
    job_name=$(create_manual_job "specialist-models-retraining" "$RETRAINING_NAMESPACE")

    # Monitorar execução (timeout maior: 20 min)
    echo -e "${YELLOW}Monitorando job: $job_name (timeout: 20 min)${NC}"
    echo ""

    timeout=1200
    elapsed=0

    while [ $elapsed -lt $timeout ]; do
        status=$(kubectl get job "$job_name" -n "$RETRAINING_NAMESPACE" -o jsonpath='{.status.conditions[0].type}' 2>/dev/null || echo "")

        if [ "$status" = "Complete" ]; then
            echo -e "${GREEN}✓ Job completado com sucesso${NC}"
            show_logs "$job_name" "$RETRAINING_NAMESPACE"
            cleanup_job "$job_name" "$RETRAINING_NAMESPACE"
            return 0
        elif [ "$status" = "Failed" ]; then
            echo -e "${RED}✗ Job falhou${NC}"
            show_logs "$job_name" "$RETRAINING_NAMESPACE"
            cleanup_job "$job_name" "$RETRAINING_NAMESPACE"
            return 1
        fi

        echo -n "."
        sleep 10
        elapsed=$((elapsed + 10))
    done

    echo -e "${RED}✗ Timeout após ${timeout}s${NC}"
    show_logs "$job_name" "$RETRAINING_NAMESPACE"
    cleanup_job "$job_name" "$RETRAINING_NAMESPACE"
    return 1
}

# Função para verificar pré-requisitos
check_prerequisites() {
    echo "=========================================="
    echo "Verificando Pré-requisitos"
    echo "=========================================="

    # Verificar kubectl
    if ! command -v kubectl &>/dev/null; then
        echo -e "${RED}✗ kubectl não encontrado${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ kubectl instalado${NC}"

    # Verificar acesso ao cluster
    if ! kubectl cluster-info &>/dev/null; then
        echo -e "${RED}✗ Sem acesso ao cluster Kubernetes${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Acesso ao cluster OK${NC}"

    # Verificar namespaces
    if ! kubectl get namespace "$TRIGGER_NAMESPACE" &>/dev/null; then
        echo -e "${RED}✗ Namespace $TRIGGER_NAMESPACE não encontrado${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Namespace $TRIGGER_NAMESPACE existe${NC}"

    if ! kubectl get namespace "$RETRAINING_NAMESPACE" &>/dev/null; then
        echo -e "${RED}✗ Namespace $RETRAINING_NAMESPACE não encontrado${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Namespace $RETRAINING_NAMESPACE existe${NC}"

    # Verificar secrets
    if ! kubectl get secret mongodb-secret -n "$TRIGGER_NAMESPACE" &>/dev/null; then
        echo -e "${YELLOW}⚠ Secret mongodb-secret não encontrado em $TRIGGER_NAMESPACE${NC}"
    else
        echo -e "${GREEN}✓ Secret mongodb-secret existe${NC}"
    fi

    if ! kubectl get secret mongodb-secret -n "$RETRAINING_NAMESPACE" &>/dev/null; then
        echo -e "${YELLOW}⚠ Secret mongodb-secret não encontrado em $RETRAINING_NAMESPACE${NC}"
    else
        echo -e "${GREEN}✓ Secret mongodb-secret existe${NC}"
    fi

    echo ""
}

# Main
echo "=========================================="
echo "ML Retraining CronJobs - Teste Manual"
echo "=========================================="
echo "Target: $TARGET_JOB"
echo ""

# Verificar pré-requisitos
check_prerequisites

# Executar testes
success=true

if [ "$TARGET_JOB" = "trigger" ] || [ "$TARGET_JOB" = "all" ]; then
    if ! test_retraining_trigger; then
        success=false
    fi
fi

if [ "$TARGET_JOB" = "retraining" ] || [ "$TARGET_JOB" = "all" ]; then
    if ! test_specialist_retraining; then
        success=false
    fi
fi

# Resumo final
echo ""
echo "=========================================="
if [ "$success" = true ]; then
    echo -e "${GREEN}✓ Todos os testes passaram${NC}"
    exit 0
else
    echo -e "${RED}✗ Alguns testes falharam${NC}"
    exit 1
fi
