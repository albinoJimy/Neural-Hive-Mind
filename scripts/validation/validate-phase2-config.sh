#!/bin/bash
# Script de validação de configurações da Fase 2 - Integrações Externas
# Valida configurações de LLM, ArgoCD, Flux, OPA e endpoints de serviços
#
# Uso: ./validate-phase2-config.sh [--namespace <namespace>] [--skip-opa] [--skip-argocd]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common-validation-functions.sh"

SCRIPT_NAME="validate-phase2-config"

# Valores padrão
CODE_FORGE_NAMESPACE="${CODE_FORGE_NAMESPACE:-neural-hive-execution}"
WORKER_AGENTS_NAMESPACE="${WORKER_AGENTS_NAMESPACE:-neural-hive-execution}"
OPA_NAMESPACE="${OPA_NAMESPACE:-opa-gatekeeper-system}"

# Flags de skip
SKIP_OPA=false
SKIP_ARGOCD=false
SKIP_TESTS=false

# ============================================================================
# PARSE ARGUMENTOS
# ============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace)
            CODE_FORGE_NAMESPACE="$2"
            WORKER_AGENTS_NAMESPACE="$2"
            shift 2
            ;;
        --skip-opa)
            SKIP_OPA=true
            shift
            ;;
        --skip-argocd)
            SKIP_ARGOCD=true
            shift
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        *)
            log_error "Argumento desconhecido: $1"
            exit 1
            ;;
    esac
done

# ============================================================================
# FUNÇÕES DE VALIDAÇÃO
# ============================================================================

validate_llm_config() {
    log_info "Validando configuração LLM do Code Forge..."
    local start_time=$(date +%s)

    # Verificar se deployment existe
    if ! kubectl get deployment code-forge -n "$CODE_FORGE_NAMESPACE" &>/dev/null; then
        add_test_result "llm_deployment_exists" "FAIL" "high" \
            "Deployment code-forge não encontrado em $CODE_FORGE_NAMESPACE" \
            "Verifique se o Code Forge está deployado no namespace correto"
        return
    fi

    # Extrair variáveis de ambiente do deployment
    local llm_enabled=$(kubectl get deployment code-forge -n "$CODE_FORGE_NAMESPACE" \
        -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="LLM_ENABLED")].value}' 2>/dev/null || echo "")
    local llm_provider=$(kubectl get deployment code-forge -n "$CODE_FORGE_NAMESPACE" \
        -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="LLM_PROVIDER")].value}' 2>/dev/null || echo "")

    if [[ "$llm_enabled" != "true" && "$llm_enabled" != "True" ]]; then
        add_test_result "llm_enabled" "SKIP" "medium" \
            "LLM desabilitado (LLM_ENABLED=$llm_enabled)" \
            "Configure LLM_ENABLED=true para habilitar geração de código via LLM"
        return
    fi

    # Validar provider
    if [[ -z "$llm_provider" ]]; then
        add_test_result "llm_provider" "FAIL" "high" \
            "LLM_PROVIDER não configurado quando LLM_ENABLED=true" \
            "Configure LLM_PROVIDER com 'openai', 'anthropic' ou 'local'"
        return
    fi

    case "$llm_provider" in
        openai)
            # Verificar se LLM_API_KEY está definido (via secret)
            local has_key=$(kubectl get deployment code-forge -n "$CODE_FORGE_NAMESPACE" \
                -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="LLM_API_KEY")]}' 2>/dev/null || echo "")
            if [[ -z "$has_key" ]]; then
                add_test_result "llm_openai_key" "FAIL" "high" \
                    "LLM_API_KEY não configurado para provider OpenAI" \
                    "Adicione LLM_API_KEY ao secret do Code Forge"
            else
                add_test_result "llm_openai_key" "PASS" "high" \
                    "LLM_API_KEY configurado para provider OpenAI"
            fi
            ;;
        anthropic)
            local has_key=$(kubectl get deployment code-forge -n "$CODE_FORGE_NAMESPACE" \
                -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="LLM_ANTHROPIC_API_KEY")]}' 2>/dev/null || echo "")
            if [[ -z "$has_key" ]]; then
                add_test_result "llm_anthropic_key" "FAIL" "high" \
                    "LLM_ANTHROPIC_API_KEY não configurado para provider Anthropic" \
                    "Adicione LLM_ANTHROPIC_API_KEY ao secret do Code Forge"
            else
                add_test_result "llm_anthropic_key" "PASS" "high" \
                    "LLM_ANTHROPIC_API_KEY configurado para provider Anthropic"
            fi
            ;;
        local)
            local base_url=$(kubectl get deployment code-forge -n "$CODE_FORGE_NAMESPACE" \
                -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="LLM_BASE_URL")].value}' 2>/dev/null || echo "")
            if [[ -z "$base_url" ]]; then
                add_test_result "llm_local_url" "FAIL" "high" \
                    "LLM_BASE_URL não configurado para provider local" \
                    "Configure LLM_BASE_URL com endpoint do LLM local (ex: http://ollama:11434)"
            else
                add_test_result "llm_local_url" "PASS" "high" \
                    "LLM_BASE_URL configurado: $base_url"
            fi
            ;;
        *)
            add_test_result "llm_provider_valid" "FAIL" "high" \
                "LLM_PROVIDER inválido: $llm_provider" \
                "Use 'openai', 'anthropic' ou 'local'"
            ;;
    esac

    local exec_time=$(($(date +%s) - start_time))
    log_info "Validação LLM concluída em ${exec_time}s"
}

validate_argocd_config() {
    if [[ "$SKIP_ARGOCD" == "true" ]]; then
        log_info "Pulando validação ArgoCD (--skip-argocd)"
        return
    fi

    log_info "Validando configuração ArgoCD do Worker Agents..."
    local start_time=$(date +%s)

    # Verificar se deployment existe
    if ! kubectl get deployment worker-agents -n "$WORKER_AGENTS_NAMESPACE" &>/dev/null; then
        add_test_result "argocd_deployment_exists" "FAIL" "high" \
            "Deployment worker-agents não encontrado em $WORKER_AGENTS_NAMESPACE" \
            "Verifique se Worker Agents está deployado"
        return
    fi

    # Extrair variáveis de ambiente
    local argocd_enabled=$(kubectl get deployment worker-agents -n "$WORKER_AGENTS_NAMESPACE" \
        -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="argocd_enabled")].value}' 2>/dev/null || echo "false")

    if [[ "$argocd_enabled" != "true" && "$argocd_enabled" != "True" ]]; then
        add_test_result "argocd_enabled" "SKIP" "medium" \
            "ArgoCD desabilitado (argocd_enabled=$argocd_enabled)" \
            "Configure argocd_enabled=true para usar ArgoCD para deploys"
        return
    fi

    # Validar URL
    local argocd_url=$(kubectl get deployment worker-agents -n "$WORKER_AGENTS_NAMESPACE" \
        -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="argocd_url")].value}' 2>/dev/null || echo "")

    if [[ -z "$argocd_url" ]]; then
        add_test_result "argocd_url" "FAIL" "high" \
            "argocd_url não configurado quando argocd_enabled=true" \
            "Configure argocd_url com URL do ArgoCD (ex: https://argocd.example.com)"
        return
    fi

    # Validar formato da URL
    if [[ ! "$argocd_url" =~ ^https?:// ]]; then
        add_test_result "argocd_url_format" "FAIL" "high" \
            "argocd_url não é uma URL válida: $argocd_url" \
            "URL deve começar com http:// ou https://"
        return
    fi

    # Verificar token
    local has_token=$(kubectl get deployment worker-agents -n "$WORKER_AGENTS_NAMESPACE" \
        -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="argocd_token")]}' 2>/dev/null || echo "")

    if [[ -z "$has_token" ]]; then
        add_test_result "argocd_token" "FAIL" "high" \
            "argocd_token não configurado" \
            "Adicione argocd_token ao secret do Worker Agents"
        return
    fi

    # Testar conectividade (se possível)
    log_info "Testando conectividade com ArgoCD: $argocd_url"
    local response_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
        "$argocd_url/api/version" 2>/dev/null || echo "000")

    if [[ "$response_code" == "200" || "$response_code" == "401" || "$response_code" == "403" ]]; then
        add_test_result "argocd_connectivity" "PASS" "high" \
            "ArgoCD acessível em $argocd_url (HTTP $response_code)"
    else
        add_test_result "argocd_connectivity" "WARNING" "high" \
            "ArgoCD inacessível em $argocd_url (HTTP $response_code)" \
            "Verifique conectividade de rede e firewall"
    fi

    local exec_time=$(($(date +%s) - start_time))
    log_info "Validação ArgoCD concluída em ${exec_time}s"
}

validate_flux_config() {
    log_info "Validando configuração Flux do Worker Agents..."
    local start_time=$(date +%s)

    # Verificar se deployment existe
    if ! kubectl get deployment worker-agents -n "$WORKER_AGENTS_NAMESPACE" &>/dev/null; then
        # Já reportado em validate_argocd_config
        return
    fi

    # Extrair variáveis de ambiente
    local flux_enabled=$(kubectl get deployment worker-agents -n "$WORKER_AGENTS_NAMESPACE" \
        -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="flux_enabled")].value}' 2>/dev/null || echo "false")

    if [[ "$flux_enabled" != "true" && "$flux_enabled" != "True" ]]; then
        add_test_result "flux_enabled" "SKIP" "medium" \
            "Flux desabilitado (flux_enabled=$flux_enabled)" \
            "Configure flux_enabled=true para usar Flux CD para deploys"
        return
    fi

    # Validar kubeconfig path
    local kubeconfig_path=$(kubectl get deployment worker-agents -n "$WORKER_AGENTS_NAMESPACE" \
        -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="flux_kubeconfig_path")].value}' 2>/dev/null || echo "")

    if [[ -z "$kubeconfig_path" ]]; then
        add_test_result "flux_kubeconfig" "FAIL" "high" \
            "flux_kubeconfig_path não configurado quando flux_enabled=true" \
            "Configure flux_kubeconfig_path ou monte kubeconfig como volume"
        return
    fi

    add_test_result "flux_kubeconfig" "PASS" "high" \
        "flux_kubeconfig_path configurado: $kubeconfig_path"

    # Verificar namespace Flux
    local flux_namespace=$(kubectl get deployment worker-agents -n "$WORKER_AGENTS_NAMESPACE" \
        -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="flux_namespace")].value}' 2>/dev/null || echo "flux-system")

    if kubectl get namespace "$flux_namespace" &>/dev/null; then
        add_test_result "flux_namespace" "PASS" "medium" \
            "Namespace Flux existe: $flux_namespace"
    else
        add_test_result "flux_namespace" "FAIL" "high" \
            "Namespace Flux não existe: $flux_namespace" \
            "Instale Flux CD no cluster"
    fi

    # Verificar CRDs Flux
    if kubectl get crd kustomizations.kustomize.toolkit.fluxcd.io &>/dev/null; then
        add_test_result "flux_crds" "PASS" "medium" \
            "CRDs Flux instalados"
    else
        add_test_result "flux_crds" "FAIL" "high" \
            "CRDs Flux não instalados" \
            "Execute: flux install"
    fi

    local exec_time=$(($(date +%s) - start_time))
    log_info "Validação Flux concluída em ${exec_time}s"
}

validate_code_forge_endpoint() {
    log_info "Validando endpoint do Code Forge..."
    local start_time=$(date +%s)

    # Verificar se service existe
    if ! kubectl get service code-forge -n "$CODE_FORGE_NAMESPACE" &>/dev/null; then
        add_test_result "code_forge_service" "FAIL" "medium" \
            "Service code-forge não encontrado em $CODE_FORGE_NAMESPACE" \
            "Verifique se Code Forge está deployado corretamente"
        return
    fi

    add_test_result "code_forge_service" "PASS" "medium" \
        "Service code-forge existe em $CODE_FORGE_NAMESPACE"

    # Verificar pod running
    local pod_status=$(kubectl get pods -n "$CODE_FORGE_NAMESPACE" \
        -l app.kubernetes.io/name=code-forge \
        -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "")

    if [[ "$pod_status" == "Running" ]]; then
        add_test_result "code_forge_pod" "PASS" "high" \
            "Pod code-forge está Running"
    else
        add_test_result "code_forge_pod" "FAIL" "high" \
            "Pod code-forge não está Running (status: $pod_status)" \
            "Verifique logs: kubectl logs -n $CODE_FORGE_NAMESPACE -l app.kubernetes.io/name=code-forge"
    fi

    local exec_time=$(($(date +%s) - start_time))
    log_info "Validação endpoint Code Forge concluída em ${exec_time}s"
}

validate_orchestrator_activities() {
    log_info "Validando activities do Orchestrator..."
    local start_time=$(date +%s)

    local base_path="${SCRIPT_DIR}/../../services/orchestrator-dynamic"

    # Verificar arquivos de activities
    local activities=(
        "src/activities/plan_validation.py"
        "src/activities/ticket_generation.py"
        "src/activities/result_consolidation.py"
        "src/activities/sla_monitoring.py"
    )

    local all_exist=true
    for activity in "${activities[@]}"; do
        if [[ -f "$base_path/$activity" ]]; then
            log_debug "Activity encontrada: $activity"
        else
            all_exist=false
            log_warn "Activity não encontrada: $activity"
        fi
    done

    if [[ "$all_exist" == "true" ]]; then
        add_test_result "orchestrator_activities_files" "PASS" "critical" \
            "Todos os arquivos de activities existem"
    else
        add_test_result "orchestrator_activities_files" "FAIL" "critical" \
            "Arquivos de activities faltando" \
            "Verifique services/orchestrator-dynamic/src/activities/"
        return
    fi

    # Verificar testes unitários
    local test_path="$base_path/tests/unit/activities"
    if [[ -d "$test_path" ]]; then
        local test_count=$(find "$test_path" -name "test_*.py" | wc -l)
        if [[ "$test_count" -ge 4 ]]; then
            add_test_result "orchestrator_activities_tests" "PASS" "critical" \
                "$test_count arquivos de teste encontrados em tests/unit/activities/"
        else
            add_test_result "orchestrator_activities_tests" "WARNING" "critical" \
                "Apenas $test_count arquivos de teste encontrados (esperado >= 4)" \
                "Adicione testes unitários para todas as activities"
        fi
    else
        add_test_result "orchestrator_activities_tests" "FAIL" "critical" \
            "Diretório de testes não encontrado: $test_path" \
            "Crie testes unitários em tests/unit/activities/"
        return
    fi

    # Executar testes se não pulando
    if [[ "$SKIP_TESTS" == "false" ]]; then
        log_info "Executando testes unitários das activities..."
        if cd "$base_path" && python -m pytest tests/unit/activities/ -v --tb=short 2>&1 | tee /tmp/orchestrator_tests.log; then
            add_test_result "orchestrator_activities_pytest" "PASS" "critical" \
                "Todos os testes unitários passaram"
        else
            local failed_count=$(grep -c "FAILED" /tmp/orchestrator_tests.log 2>/dev/null || echo "?")
            add_test_result "orchestrator_activities_pytest" "FAIL" "critical" \
                "$failed_count testes falharam" \
                "Verifique /tmp/orchestrator_tests.log para detalhes"
        fi
    else
        add_test_result "orchestrator_activities_pytest" "SKIP" "critical" \
            "Testes pulados (--skip-tests)"
    fi

    local exec_time=$(($(date +%s) - start_time))
    log_info "Validação activities Orchestrator concluída em ${exec_time}s"
}

validate_opa_integration() {
    if [[ "$SKIP_OPA" == "true" ]]; then
        log_info "Pulando validação OPA (--skip-opa)"
        return
    fi

    log_info "Validando integração OPA..."
    local start_time=$(date +%s)

    # Verificar deployment do Gatekeeper
    if kubectl get deployment -n "$OPA_NAMESPACE" gatekeeper-controller-manager &>/dev/null; then
        add_test_result "opa_gatekeeper_deployment" "PASS" "medium" \
            "Gatekeeper controller manager deployado"
    else
        add_test_result "opa_gatekeeper_deployment" "FAIL" "medium" \
            "Gatekeeper não encontrado em $OPA_NAMESPACE" \
            "Instale OPA Gatekeeper: kubectl apply -f https://raw.githubusercontent.com/open-policy-agent/gatekeeper/master/deploy/gatekeeper.yaml"
        return
    fi

    # Verificar constraint templates
    local template_count=$(kubectl get constrainttemplates --no-headers 2>/dev/null | wc -l || echo "0")
    if [[ "$template_count" -gt 0 ]]; then
        add_test_result "opa_constraint_templates" "PASS" "medium" \
            "$template_count constraint templates configurados"
    else
        add_test_result "opa_constraint_templates" "WARNING" "medium" \
            "Nenhum constraint template configurado" \
            "Adicione políticas OPA para validação de recursos"
    fi

    local exec_time=$(($(date +%s) - start_time))
    log_info "Validação OPA concluída em ${exec_time}s"
}

# ============================================================================
# MAIN
# ============================================================================

main() {
    init_report "Validação de Configurações Fase 2 - Integrações Externas"

    echo ""
    echo "===== Validando Configurações de Integrações Externas ====="
    echo "Code Forge Namespace: $CODE_FORGE_NAMESPACE"
    echo "Worker Agents Namespace: $WORKER_AGENTS_NAMESPACE"
    echo ""

    # Validar LLM Configuration
    validate_llm_config

    # Validar GitOps Configuration
    validate_argocd_config
    validate_flux_config

    # Validar Service Endpoints
    validate_code_forge_endpoint

    # Validar Orchestrator Activities
    validate_orchestrator_activities

    # Validar OPA Integration
    validate_opa_integration

    # Gerar relatórios
    generate_summary_report
    export_json_report
    export_html_report

    echo ""
    echo "Relatório JSON: $(export_json_report)"
    echo "Relatório HTML: $(export_html_report)"

    # Exit com código apropriado
    if [[ $FAILED_TESTS -gt 0 ]]; then
        exit 1
    fi
    exit 0
}

main "$@"
