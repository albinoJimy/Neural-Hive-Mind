#!/bin/bash
# Script para gerenciar CronJobs de retreinamento ML

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configurações
NAMESPACE=${NAMESPACE:-neural-hive-mind}
K8S_DIR="$(dirname "$0")"

echo -e "${GREEN}=== ML Retraining CronJob Manager ===${NC}"
echo "Namespace: $NAMESPACE"
echo ""

# Funções
help() {
    cat << EOF
Uso: $0 [comando] [opções]

Comandos:
    apply       Aplica os manifests CronJob ao cluster
    delete      Remove os CronJobs do cluster
    list        Lista CronJobs instalados
    status      Mostra status dos últimos jobs
    trigger     Dispara execução manual de um job
    suspend     Suspende um CronJob
    resume      Retoma um CronJob suspendido
    logs        Mostra logs do último job
    validate    Valida manifests YAML

Opções:
    -n, --namespace NAMESPACE    Namespace a usar (default: neural-hive-mind)
    -d, --daily                  Usa apenas o CronJob diário
    -w, --weekly                 Usa apenas o CronJob semanal

Exemplos:
    $0 apply -d                  # Instala apenas CronJob diário
    $0 status                    # Mostra status dos jobs
    $0 trigger ml-retraining-daily   # Execução manual
    $0 suspend ml-retraining-daily   # Suspende agendamento
    $0 logs ml-retraining-daily  # Logs do último job

EOF
}

apply() {
    echo -e "${GREEN}Aplicando manifests...${NC}"

    if [ "$DAILY" = "true" ] || [ -z "$WEEKLY" ]; then
        echo "Aplicando CronJob diário..."
        kubectl apply -f "$K8S_DIR/ml-retraining-cronjob.yaml" -n "$NAMESPACE"
    fi

    if [ "$WEEKLY" = "true" ]; then
        echo "Aplicando CronJob semanal..."
        kubectl apply -f "$K8S_DIR/ml-retraining-weekly-cronjob.yaml" -n "$NAMESPACE"
    fi

    echo -e "${GREEN}CronJobs aplicados com sucesso!${NC}"
}

delete() {
    echo -e "${YELLOW}Removendo CronJobs...${NC}"

    if [ "$DAILY" = "true" ] || [ -z "$WEEKLY" ]; then
        kubectl delete -f "$K8S_DIR/ml-retraining-cronjob.yaml" -n "$NAMESPACE" --ignore-not-found=true
    fi

    if [ "$WEEKLY" = "true" ]; then
        kubectl delete -f "$K8S_DIR/ml-retraining-weekly-cronjob.yaml" -n "$NAMESPACE" --ignore-not-found=true
    fi

    echo -e "${GREEN}CronJobs removidos!${NC}"
}

list() {
    echo -e "${GREEN}CronJobs instalados:${NC}"
    kubectl get cronjobs -n "$NAMESPACE" -l app=ml-retraining
}

status() {
    echo -e "${GREEN}Status dos últimos jobs:${NC}"
    echo ""

    for cronjob in $(kubectl get cronjobs -n "$NAMESPACE" -l app=ml-retraining -o name); do
        echo "=== $cronjob ==="
        kubectl get jobs -n "$NAMESPACE" -l app=ml-retraining --sort-by=.metadata.creationTimestamp | tail -5
        echo ""
    done
}

trigger() {
    local job_name=$1
    if [ -z "$job_name" ]; then
        echo -e "${RED}Erro: Especifique o nome do CronJob${NC}"
        echo "Uso: $0 trigger <cronjob-name>"
        exit 1
    fi

    echo -e "${GREEN}Disparando execução manual de $job_name...${NC}"
    kubectl create job --from=cronjob/$job_name manual-$(date +%s)-$job_name -n "$NAMESPACE"
    echo -e "${GREEN}Job criado! Use '$0 logs $job_name' para acompanhar${NC}"
}

suspend() {
    local job_name=$1
    if [ -z "$job_name" ]; then
        echo -e "${RED}Erro: Especifique o nome do CronJob${NC}"
        echo "Uso: $0 suspend <cronjob-name>"
        exit 1
    fi

    echo -e "${YELLOW}Suspensiondo $job_name...${NC}"
    kubectl patch cronjob $job_name -n "$NAMESPACE" -p '{"spec":{"suspend":true}}'
    echo -e "${GREEN}CronJob suspenso! Use '$0 resume $job_name' para retomar${NC}"
}

resume() {
    local job_name=$1
    if [ -z "$job_name" ]; then
        echo -e "${RED}Erro: Especifique o nome do CronJob${NC}"
        echo "Uso: $0 resume <cronjob-name>"
        exit 1
    fi

    echo -e "${GREEN}Retomando $job_name...${NC}"
    kubectl patch cronjob $job_name -n "$NAMESPACE" -p '{"spec":{"suspend":false}}'
    echo -e "${GREEN}CronJob retomado!${NC}"
}

logs() {
    local job_name=$1
    if [ -z "$job_name" ]; then
        echo -e "${RED}Erro: Especifique o nome do CronJob${NC}"
        echo "Uso: $0 logs <cronjob-name>"
        exit 1
    fi

    # Busca o último job para este cronjob
    local last_job=$(kubectl get jobs -n "$NAMESPACE" -l app=ml-retraining --sort-by=.metadata.creationTimestamp | grep "$job_name" | tail -1 | awk '{print $1}')

    if [ -z "$last_job" ]; then
        echo -e "${RED}Nenhum job encontrado para $job_name${NC}"
        exit 1
    fi

    echo -e "${GREEN}Logs do job $last_job:${NC}"
    kubectl logs -n "$NAMESPACE" job/$last_job -f
}

validate() {
    echo -e "${GREEN}Validando manifests YAML...${NC}"

    if command -v kubectl &> /dev/null; then
        if [ "$DAILY" = "true" ] || [ -z "$WEEKLY" ]; then
            echo "Validando ml-retraining-cronjob.yaml..."
            kubectl apply --dry-run=client -f "$K8S_DIR/ml-retraining-cronjob.yaml" -n "$NAMESPACE"
        fi
        if [ "$WEEKLY" = "true" ]; then
            echo "Validando ml-retraining-weekly-cronjob.yaml..."
            kubectl apply --dry-run=client -f "$K8S_DIR/ml-retraining-weekly-cronjob.yaml" -n "$NAMESPACE"
        fi
        echo -e "${GREEN}Manifests válidos!${NC}"
    else
        echo -e "${YELLOW}kubectl não encontrado. Tentando validação básica...${NC}"
        if command -v yamllint &> /dev/null; then
            yamllint "$K8S_DIR"/*.yaml
        else
            echo -e "${RED}yamllint não encontrado. Instale para validação completa.${NC}"
            exit 1
        fi
    fi
}

# Parse argumentos
COMMAND=${1:-help}
shift

while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -d|--daily)
            DAILY=true
            shift
            ;;
        -w|--weekly)
            WEEKLY=true
            shift
            ;;
        *)
            # Argumento posicional para comandos que precisam
            POSITIONAL_ARGS+=("$1")
            shift
            ;;
    esac
done

# Executa comando
case $COMMAND in
    apply) apply ;;
    delete) delete ;;
    list) list ;;
    status) status ;;
    trigger) trigger "${POSITIONAL_ARGS[0]}" ;;
    suspend) suspend "${POSITIONAL_ARGS[0]}" ;;
    resume) resume "${POSITIONAL_ARGS[0]}" ;;
    logs) logs "${POSITIONAL_ARGS[0]}" ;;
    validate) validate ;;
    *) help ;;
esac
