#!/bin/bash
#
# Create Phase 2 Secrets for Neural Hive Mind
#
# This script generates all Kubernetes secrets required for the 13 Phase 2 services,
# organized by namespace. Supports multiple modes for different deployment strategies.
#
# Modes:
#   static           - Generate Kubernetes Secrets with placeholder values (dev/staging)
#   vault-agent      - Generate Secrets with Vault Agent Injector annotations (production)
#   external-secrets - Generate ExternalSecret CRs for External Secrets Operator (GitOps)
#
# Usage:
#   ./scripts/create-phase2-secrets.sh --mode static --environment dev
#   ./scripts/create-phase2-secrets.sh --mode vault-agent --environment production
#   ./scripts/create-phase2-secrets.sh --mode external-secrets --environment production
#
# Arguments:
#   --mode        : static | vault-agent | external-secrets (default: static)
#   --environment : dev | staging | production (default: dev)
#   --registry    : Docker registry URL (default: localhost:30500)
#   --dry-run     : Generate YAML files without applying (default: false)
#   --output-dir  : Directory for generated YAML files (default: /tmp/phase2-secrets)
#

set -euo pipefail

# Default values
MODE="static"
ENVIRONMENT="dev"
REGISTRY="localhost:30500"
DRY_RUN="false"
OUTPUT_DIR="/tmp/phase2-secrets"
APPLY_SECRETS="true"

# =============================================================================
# CENTRALIZED SERVICE DEFINITIONS
# =============================================================================
# This is the single source of truth for all Phase 2 services and their secrets.
# Format: "namespace|secret-name|key1,key2,key3|vault-path"
#
# To add a new service:
#   1. Add entry to PHASE2_SERVICES array below
#   2. Run: ./scripts/create-phase2-secrets.sh
#   3. Add corresponding entry to validate-phase2-secrets.sh (or regenerate)
# =============================================================================

declare -a PHASE2_SERVICES=(
    # neural-hive-orchestration
    "neural-hive-orchestration|orchestrator-dynamic-secrets|POSTGRES_USER,POSTGRES_PASSWORD,MONGODB_URI,REDIS_PASSWORD,KAFKA_SASL_USERNAME,KAFKA_SASL_PASSWORD|secret/orchestrator-dynamic"
    "neural-hive-orchestration|execution-ticket-service-secrets|POSTGRES_PASSWORD,MONGODB_URI,JWT_SECRET_KEY|secret/execution-ticket-service"

    # neural-hive-queen
    "neural-hive-queen|queen-agent-secrets|MONGODB_URI,REDIS_CLUSTER_NODES,REDIS_PASSWORD,NEO4J_URI,NEO4J_USER,NEO4J_PASSWORD|secret/queen-agent"

    # neural-hive-execution
    "neural-hive-execution|worker-agents-secrets|KAFKA_SASL_USERNAME,KAFKA_SASL_PASSWORD,ARGOCD_TOKEN,JENKINS_TOKEN,SONARQUBE_TOKEN,SNYK_TOKEN|secret/worker-agents"
    "neural-hive-execution|code-forge-secrets|POSTGRES_USER,POSTGRES_PASSWORD,MONGODB_URI,REDIS_PASSWORD,KAFKA_SASL_USERNAME,KAFKA_SASL_PASSWORD,GIT_USERNAME,GIT_TOKEN,OPENAI_API_KEY,ANTHROPIC_API_KEY|secret/code-forge"

    # neural-hive-registry
    "neural-hive-registry|service-registry-secrets|REDIS_PASSWORD,ETCD_USERNAME,ETCD_PASSWORD|secret/service-registry"

    # neural-hive-estrategica
    "neural-hive-estrategica|scout-agents-secrets|KAFKA_SASL_USERNAME,KAFKA_SASL_PASSWORD,REDIS_PASSWORD|secret/scout-agents"
    "neural-hive-estrategica|analyst-agents-secrets|MONGODB_URI,REDIS_PASSWORD,NEO4J_PASSWORD,CLICKHOUSE_PASSWORD,ELASTICSEARCH_PASSWORD|secret/analyst-agents"
    "neural-hive-estrategica|optimizer-agents-secrets|MONGODB_URI,REDIS_PASSWORD,MLFLOW_TRACKING_TOKEN|secret/optimizer-agents"

    # neural-hive-resilience
    "neural-hive-resilience|guard-agents-secrets|MONGODB_PASSWORD,REDIS_PASSWORD,KAFKA_SASL_USERNAME,KAFKA_SASL_PASSWORD|secret/guard-agents"
    "neural-hive-resilience|self-healing-engine-secrets|MONGODB_PASSWORD,REDIS_PASSWORD,KAFKA_SASL_PASSWORD,PAGERDUTY_API_KEY,SLACK_WEBHOOK_URL|secret/self-healing-engine"

    # neural-hive-monitoring
    "neural-hive-monitoring|sla-management-system-secrets|POSTGRES_USER,POSTGRES_PASSWORD,REDIS_PASSWORD,PROMETHEUS_BEARER_TOKEN|secret/sla-management-system"

    # neural-hive-mcp
    "neural-hive-mcp|mcp-tool-catalog-secrets|MONGODB_URI,REDIS_PASSWORD,KAFKA_SASL_USERNAME,KAFKA_SASL_PASSWORD,GITHUB_TOKEN,GITLAB_TOKEN|secret/mcp-tool-catalog"
)

# =============================================================================
# END SERVICE DEFINITIONS
# =============================================================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --mode)
                MODE="$2"
                shift 2
                ;;
            --environment)
                ENVIRONMENT="$2"
                shift 2
                ;;
            --registry)
                REGISTRY="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN="true"
                APPLY_SECRETS="false"
                shift
                ;;
            --output-dir)
                OUTPUT_DIR="$2"
                shift 2
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

show_help() {
    cat << EOF
Neural Hive Mind - Phase 2 Secrets Generator

Usage: $0 [OPTIONS]

Options:
    --mode          Mode for secret generation (default: static):
                      static           - Kubernetes Secrets with generated placeholder values
                      vault-agent      - Secrets with Vault Agent Injector annotations
                      external-secrets - ExternalSecret CRs for External Secrets Operator
    --environment   Target environment: dev | staging | production (default: dev)
    --registry      Docker registry URL (default: localhost:30500)
    --dry-run       Generate YAML files without applying to cluster
    --output-dir    Directory for generated YAML files (default: /tmp/phase2-secrets)
    --help, -h      Show this help message

Modes explained:
    static:
      Generates standard Kubernetes Secrets with randomly generated placeholder values.
      Best for: development, staging, CI/CD testing.

    vault-agent:
      Generates Secrets with vault.hashicorp.com/* annotations for Vault Agent Injector.
      Requires: Vault Agent Injector installed in cluster.
      Best for: production with sidecar injection.

    external-secrets:
      Generates ExternalSecret custom resources that sync from Vault to K8s Secrets.
      Requires: External Secrets Operator + ClusterSecretStore configured.
      Best for: GitOps workflows (ArgoCD, Flux).

Examples:
    # Create static secrets for development
    $0 --mode static --environment dev

    # Generate secrets for production with Vault Agent Injector
    $0 --mode vault-agent --environment production

    # Generate ExternalSecrets for GitOps deployment
    $0 --mode external-secrets --environment production --dry-run --output-dir ./gitops/secrets

    # Dry run - generate files without applying
    $0 --mode static --environment staging --dry-run --output-dir ./secrets

EOF
}

# Generate random password
generate_password() {
    local length=${1:-32}
    openssl rand -hex "$length" | head -c "$length"
}

# Validate mode argument
validate_mode() {
    case "$MODE" in
        static|vault-agent|external-secrets)
            return 0
            ;;
        vault)
            # Backward compatibility: map 'vault' to 'vault-agent'
            log_warn "Mode 'vault' is deprecated. Use 'vault-agent' or 'external-secrets' instead."
            MODE="vault-agent"
            return 0
            ;;
        *)
            log_error "Invalid mode: $MODE"
            log_error "Valid modes: static, vault-agent, external-secrets"
            exit 1
            ;;
    esac
}

# Generate a placeholder value based on environment
generate_value() {
    local key=$1
    local service=$2

    if [[ "$MODE" == "static" ]]; then
        case $key in
            *PASSWORD*)
                echo "changeme-$(generate_password 16)"
                ;;
            *URI*)
                if [[ "$key" == *MONGODB* ]]; then
                    echo "mongodb://admin:changeme-$(generate_password 16)@mongodb-headless.neural-hive-infrastructure:27017/?replicaSet=rs0"
                elif [[ "$key" == *NEO4J* ]]; then
                    echo "bolt://neo4j-headless.neural-hive-infrastructure:7687"
                else
                    echo "placeholder-uri-$(generate_password 8)"
                fi
                ;;
            *TOKEN*)
                echo "token-$(generate_password 32)"
                ;;
            *SECRET*)
                echo "secret-$(generate_password 32)"
                ;;
            *USER*)
                echo "${service}-user"
                ;;
            *NODES*)
                echo "redis-cluster-0.redis-cluster-headless.neural-hive-infrastructure:6379,redis-cluster-1.redis-cluster-headless.neural-hive-infrastructure:6379,redis-cluster-2.redis-cluster-headless.neural-hive-infrastructure:6379"
                ;;
            *)
                echo "placeholder-$(generate_password 8)"
                ;;
        esac
    else
        # For vault-agent mode, return placeholder that will be replaced by Vault injection
        echo "vault-injected-placeholder"
    fi
}

# Validate namespace exists (warns if missing, does not auto-create)
# Rationale: Namespaces should be created via k8s/bootstrap/namespaces-phase2.yaml
# to ensure proper ResourceQuotas, LimitRanges, and NetworkPolicies are applied.
ensure_namespace() {
    local namespace=$1

    if ! kubectl get namespace "$namespace" &>/dev/null; then
        log_warn "Namespace '$namespace' does not exist!"
        log_warn "Please create namespaces first using: kubectl apply -f k8s/bootstrap/namespaces-phase2.yaml"
        log_warn "Skipping secrets for namespace: $namespace"
        return 1
    fi
    return 0
}

# Create a Kubernetes secret (for static and vault-agent modes)
create_secret() {
    local namespace=$1
    local secret_name=$2
    shift 2
    local keys=("$@")

    # Skip if external-secrets mode (only ExternalSecret CRs are generated)
    if [[ "$MODE" == "external-secrets" ]]; then
        log_info "Skipping Secret creation for $secret_name (external-secrets mode)"
        return 0
    fi

    log_info "Creating secret: $secret_name in namespace: $namespace"

    # Validate namespace exists (only when applying to cluster)
    if [[ "$APPLY_SECRETS" == "true" ]]; then
        if ! ensure_namespace "$namespace"; then
            return 1
        fi
    fi

    # Build the secret YAML
    local yaml_file="${OUTPUT_DIR}/${namespace}/${secret_name}.yaml"
    mkdir -p "$(dirname "$yaml_file")"

    # Extract service name from secret name
    local service_name="${secret_name%-secrets}"

    if [[ "$MODE" == "vault-agent" ]]; then
        # Vault Agent mode - create secret with annotations for Vault Agent Injector
        cat > "$yaml_file" << EOF
apiVersion: v1
kind: Secret
metadata:
  name: ${secret_name}
  namespace: ${namespace}
  labels:
    app.kubernetes.io/name: ${service_name}
    app.kubernetes.io/component: secrets
    neuralhive/phase: phase2
    neuralhive/environment: ${ENVIRONMENT}
  annotations:
    vault.hashicorp.com/agent-inject: "true"
    vault.hashicorp.com/role: "${service_name}"
    vault.hashicorp.com/agent-inject-status: "update"
EOF
        # Add Vault injection annotations for each key
        for key in "${keys[@]}"; do
            local vault_path="secret/data/${service_name}/${key,,}"
            cat >> "$yaml_file" << EOF
    vault.hashicorp.com/agent-inject-secret-${key,,}: "${vault_path}"
    vault.hashicorp.com/agent-inject-template-${key,,}: |
      {{- with secret "${vault_path}" -}}
      {{ .Data.data.value }}
      {{- end -}}
EOF
        done

        echo "type: Opaque" >> "$yaml_file"
        echo "stringData:" >> "$yaml_file"

        for key in "${keys[@]}"; do
            echo "  ${key}: \"vault-injected-placeholder\"" >> "$yaml_file"
        done
    else
        # Static mode - create secret with generated values
        cat > "$yaml_file" << EOF
apiVersion: v1
kind: Secret
metadata:
  name: ${secret_name}
  namespace: ${namespace}
  labels:
    app.kubernetes.io/name: ${service_name}
    app.kubernetes.io/component: secrets
    neuralhive/phase: phase2
    neuralhive/environment: ${ENVIRONMENT}
type: Opaque
stringData:
EOF
        for key in "${keys[@]}"; do
            local value
            value=$(generate_value "$key" "$service_name")
            echo "  ${key}: \"${value}\"" >> "$yaml_file"
        done
    fi

    # Apply the secret if not dry-run
    if [[ "$APPLY_SECRETS" == "true" ]]; then
        kubectl apply -f "$yaml_file"
        log_success "Created secret: $secret_name"
    else
        log_info "Generated: $yaml_file"
    fi
}

# Create External Secret (for External Secrets Operator mode only)
create_external_secret() {
    local namespace=$1
    local secret_name=$2
    local vault_path=$3
    shift 3
    local keys=("$@")

    # Only create ExternalSecret in external-secrets mode
    if [[ "$MODE" != "external-secrets" ]]; then
        return 0
    fi

    log_info "Creating ExternalSecret: $secret_name in namespace: $namespace"

    # Validate namespace exists (only when applying to cluster)
    if [[ "$APPLY_SECRETS" == "true" ]]; then
        if ! ensure_namespace "$namespace"; then
            return 1
        fi
    fi

    local service_name="${secret_name%-secrets}"
    local yaml_file="${OUTPUT_DIR}/${namespace}/${secret_name}-externalsecret.yaml"
    mkdir -p "$(dirname "$yaml_file")"

    cat > "$yaml_file" << EOF
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: ${secret_name}
  namespace: ${namespace}
  labels:
    app.kubernetes.io/name: ${service_name}
    app.kubernetes.io/component: external-secrets
    neuralhive/phase: phase2
    neuralhive/environment: ${ENVIRONMENT}
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: ${secret_name}
    creationPolicy: Owner
    template:
      type: Opaque
      metadata:
        labels:
          app.kubernetes.io/name: ${service_name}
          neuralhive/phase: phase2
  data:
EOF

    for key in "${keys[@]}"; do
        cat >> "$yaml_file" << EOF
  - secretKey: ${key}
    remoteRef:
      key: ${vault_path}
      property: ${key,,}
EOF
    done

    if [[ "$APPLY_SECRETS" == "true" ]]; then
        kubectl apply -f "$yaml_file" || log_warn "External Secrets Operator may not be installed"
        log_success "Created ExternalSecret: $secret_name"
    else
        log_info "Generated: $yaml_file"
    fi
}

# =============================================================================
# SECRET DEFINITIONS BY NAMESPACE
# =============================================================================

create_orchestration_secrets() {
    log_info "Creating secrets for namespace: neural-hive-orchestration"

    # orchestrator-dynamic-secrets
    create_secret "neural-hive-orchestration" "orchestrator-dynamic-secrets" \
        "POSTGRES_USER" \
        "POSTGRES_PASSWORD" \
        "MONGODB_URI" \
        "REDIS_PASSWORD" \
        "KAFKA_SASL_USERNAME" \
        "KAFKA_SASL_PASSWORD"

    create_external_secret "neural-hive-orchestration" "orchestrator-dynamic-secrets" \
        "secret/orchestrator-dynamic" \
        "POSTGRES_USER" "POSTGRES_PASSWORD" "MONGODB_URI" "REDIS_PASSWORD" "KAFKA_SASL_USERNAME" "KAFKA_SASL_PASSWORD"

    # execution-ticket-service-secrets
    create_secret "neural-hive-orchestration" "execution-ticket-service-secrets" \
        "POSTGRES_PASSWORD" \
        "MONGODB_URI" \
        "JWT_SECRET_KEY"

    create_external_secret "neural-hive-orchestration" "execution-ticket-service-secrets" \
        "secret/execution-ticket-service" \
        "POSTGRES_PASSWORD" "MONGODB_URI" "JWT_SECRET_KEY"
}

create_queen_secrets() {
    log_info "Creating secrets for namespace: neural-hive-queen"

    # queen-agent-secrets
    create_secret "neural-hive-queen" "queen-agent-secrets" \
        "MONGODB_URI" \
        "REDIS_CLUSTER_NODES" \
        "REDIS_PASSWORD" \
        "NEO4J_URI" \
        "NEO4J_USER" \
        "NEO4J_PASSWORD"

    create_external_secret "neural-hive-queen" "queen-agent-secrets" \
        "secret/queen-agent" \
        "MONGODB_URI" "REDIS_CLUSTER_NODES" "REDIS_PASSWORD" "NEO4J_URI" "NEO4J_USER" "NEO4J_PASSWORD"
}

create_execution_secrets() {
    log_info "Creating secrets for namespace: neural-hive-execution"

    # worker-agents-secrets
    create_secret "neural-hive-execution" "worker-agents-secrets" \
        "KAFKA_SASL_USERNAME" \
        "KAFKA_SASL_PASSWORD" \
        "ARGOCD_TOKEN" \
        "JENKINS_TOKEN" \
        "SONARQUBE_TOKEN" \
        "SNYK_TOKEN"

    create_external_secret "neural-hive-execution" "worker-agents-secrets" \
        "secret/worker-agents" \
        "KAFKA_SASL_USERNAME" "KAFKA_SASL_PASSWORD" "ARGOCD_TOKEN" "JENKINS_TOKEN" "SONARQUBE_TOKEN" "SNYK_TOKEN"

    # code-forge-secrets
    create_secret "neural-hive-execution" "code-forge-secrets" \
        "POSTGRES_USER" \
        "POSTGRES_PASSWORD" \
        "MONGODB_URI" \
        "REDIS_PASSWORD" \
        "KAFKA_SASL_USERNAME" \
        "KAFKA_SASL_PASSWORD" \
        "GIT_USERNAME" \
        "GIT_TOKEN" \
        "OPENAI_API_KEY" \
        "ANTHROPIC_API_KEY"

    create_external_secret "neural-hive-execution" "code-forge-secrets" \
        "secret/code-forge" \
        "POSTGRES_USER" "POSTGRES_PASSWORD" "MONGODB_URI" "REDIS_PASSWORD" "KAFKA_SASL_USERNAME" "KAFKA_SASL_PASSWORD" "GIT_USERNAME" "GIT_TOKEN" "OPENAI_API_KEY" "ANTHROPIC_API_KEY"
}

create_registry_secrets() {
    log_info "Creating secrets for namespace: neural-hive-registry"

    # service-registry-secrets
    create_secret "neural-hive-registry" "service-registry-secrets" \
        "REDIS_PASSWORD" \
        "ETCD_USERNAME" \
        "ETCD_PASSWORD"

    create_external_secret "neural-hive-registry" "service-registry-secrets" \
        "secret/service-registry" \
        "REDIS_PASSWORD" "ETCD_USERNAME" "ETCD_PASSWORD"
}

create_estrategica_secrets() {
    log_info "Creating secrets for namespace: neural-hive-estrategica"

    # scout-agents-secrets
    create_secret "neural-hive-estrategica" "scout-agents-secrets" \
        "KAFKA_SASL_USERNAME" \
        "KAFKA_SASL_PASSWORD" \
        "REDIS_PASSWORD"

    create_external_secret "neural-hive-estrategica" "scout-agents-secrets" \
        "secret/scout-agents" \
        "KAFKA_SASL_USERNAME" "KAFKA_SASL_PASSWORD" "REDIS_PASSWORD"

    # analyst-agents-secrets
    create_secret "neural-hive-estrategica" "analyst-agents-secrets" \
        "MONGODB_URI" \
        "REDIS_PASSWORD" \
        "NEO4J_PASSWORD" \
        "CLICKHOUSE_PASSWORD" \
        "ELASTICSEARCH_PASSWORD"

    create_external_secret "neural-hive-estrategica" "analyst-agents-secrets" \
        "secret/analyst-agents" \
        "MONGODB_URI" "REDIS_PASSWORD" "NEO4J_PASSWORD" "CLICKHOUSE_PASSWORD" "ELASTICSEARCH_PASSWORD"

    # optimizer-agents-secrets
    create_secret "neural-hive-estrategica" "optimizer-agents-secrets" \
        "MONGODB_URI" \
        "REDIS_PASSWORD" \
        "MLFLOW_TRACKING_TOKEN"

    create_external_secret "neural-hive-estrategica" "optimizer-agents-secrets" \
        "secret/optimizer-agents" \
        "MONGODB_URI" "REDIS_PASSWORD" "MLFLOW_TRACKING_TOKEN"
}

create_resilience_secrets() {
    log_info "Creating secrets for namespace: neural-hive-resilience"

    # guard-agents-secrets
    create_secret "neural-hive-resilience" "guard-agents-secrets" \
        "MONGODB_PASSWORD" \
        "REDIS_PASSWORD" \
        "KAFKA_SASL_USERNAME" \
        "KAFKA_SASL_PASSWORD"

    create_external_secret "neural-hive-resilience" "guard-agents-secrets" \
        "secret/guard-agents" \
        "MONGODB_PASSWORD" "REDIS_PASSWORD" "KAFKA_SASL_USERNAME" "KAFKA_SASL_PASSWORD"

    # self-healing-engine-secrets
    create_secret "neural-hive-resilience" "self-healing-engine-secrets" \
        "MONGODB_PASSWORD" \
        "REDIS_PASSWORD" \
        "KAFKA_SASL_PASSWORD" \
        "PAGERDUTY_API_KEY" \
        "SLACK_WEBHOOK_URL"

    create_external_secret "neural-hive-resilience" "self-healing-engine-secrets" \
        "secret/self-healing-engine" \
        "MONGODB_PASSWORD" "REDIS_PASSWORD" "KAFKA_SASL_PASSWORD" "PAGERDUTY_API_KEY" "SLACK_WEBHOOK_URL"
}

create_monitoring_secrets() {
    log_info "Creating secrets for namespace: neural-hive-monitoring"

    # sla-management-system-secrets
    create_secret "neural-hive-monitoring" "sla-management-system-secrets" \
        "POSTGRES_USER" \
        "POSTGRES_PASSWORD" \
        "REDIS_PASSWORD" \
        "PROMETHEUS_BEARER_TOKEN"

    create_external_secret "neural-hive-monitoring" "sla-management-system-secrets" \
        "secret/sla-management-system" \
        "POSTGRES_USER" "POSTGRES_PASSWORD" "REDIS_PASSWORD" "PROMETHEUS_BEARER_TOKEN"
}

create_mcp_secrets() {
    log_info "Creating secrets for namespace: neural-hive-mcp"

    # mcp-tool-catalog-secrets
    create_secret "neural-hive-mcp" "mcp-tool-catalog-secrets" \
        "MONGODB_URI" \
        "REDIS_PASSWORD" \
        "KAFKA_SASL_USERNAME" \
        "KAFKA_SASL_PASSWORD" \
        "GITHUB_TOKEN" \
        "GITLAB_TOKEN"

    create_external_secret "neural-hive-mcp" "mcp-tool-catalog-secrets" \
        "secret/mcp-tool-catalog" \
        "MONGODB_URI" "REDIS_PASSWORD" "KAFKA_SASL_USERNAME" "KAFKA_SASL_PASSWORD" "GITHUB_TOKEN" "GITLAB_TOKEN"
}

# =============================================================================
# CENTRALIZED PROCESSING (alternative approach using PHASE2_SERVICES array)
# =============================================================================

# Process all services from the centralized PHASE2_SERVICES array
# This function can be used instead of the individual create_*_secrets functions
process_all_services() {
    local current_namespace=""
    local total_secrets=0
    local successful_secrets=0

    for service_def in "${PHASE2_SERVICES[@]}"; do
        # Parse the service definition: namespace|secret-name|keys|vault-path
        IFS='|' read -r namespace secret_name keys_str vault_path <<< "$service_def"

        # Log namespace change
        if [[ "$namespace" != "$current_namespace" ]]; then
            current_namespace="$namespace"
            log_info "Processing namespace: $namespace"
        fi

        # Convert comma-separated keys to array
        IFS=',' read -ra keys <<< "$keys_str"

        ((total_secrets++))

        # Create the secret (function already handles mode selection)
        if create_secret "$namespace" "$secret_name" "${keys[@]}"; then
            ((successful_secrets++))
        fi

        # Create external secret (function already handles mode selection)
        create_external_secret "$namespace" "$secret_name" "$vault_path" "${keys[@]}"
    done

    log_info "Processed $successful_secrets/$total_secrets secrets successfully"
}

# Print summary from centralized array
print_services_summary() {
    local -A namespace_secrets
    local total=0

    for service_def in "${PHASE2_SERVICES[@]}"; do
        IFS='|' read -r namespace secret_name _ _ <<< "$service_def"
        if [[ -z "${namespace_secrets[$namespace]:-}" ]]; then
            namespace_secrets[$namespace]="$secret_name"
        else
            namespace_secrets[$namespace]="${namespace_secrets[$namespace]}, $secret_name"
        fi
        ((total++))
    done

    echo ""
    log_info "Summary of secrets created:"
    for ns in "${!namespace_secrets[@]}"; do
        echo "  - $ns: ${namespace_secrets[$ns]}"
    done
    echo ""
    log_info "Total: $total secrets across ${#namespace_secrets[@]} namespaces"
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    parse_args "$@"
    validate_mode

    log_info "=============================================="
    log_info "Neural Hive Mind - Phase 2 Secrets Generator"
    log_info "=============================================="
    log_info "Mode: $MODE"
    log_info "Environment: $ENVIRONMENT"
    log_info "Registry: $REGISTRY"
    log_info "Dry Run: $DRY_RUN"
    log_info "Output Directory: $OUTPUT_DIR"
    log_info "=============================================="

    # Mode-specific info
    case "$MODE" in
        static)
            log_info "Generating Kubernetes Secrets with placeholder values"
            ;;
        vault-agent)
            log_info "Generating Secrets with Vault Agent Injector annotations"
            ;;
        external-secrets)
            log_info "Generating ExternalSecret CRs for External Secrets Operator"
            ;;
    esac
    echo ""

    # Create output directory
    mkdir -p "$OUTPUT_DIR"

    # Check kubectl connectivity (unless dry-run)
    if [[ "$APPLY_SECRETS" == "true" ]]; then
        if ! kubectl cluster-info &>/dev/null; then
            log_error "Cannot connect to Kubernetes cluster. Please check your kubeconfig."
            exit 1
        fi
        log_success "Connected to Kubernetes cluster"
    fi

    # Create secrets using centralized service definitions
    # Uses PHASE2_SERVICES array as single source of truth
    process_all_services

    log_info "=============================================="
    log_success "Phase 2 secrets generation completed!"
    log_info "=============================================="

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "Generated YAML files are in: $OUTPUT_DIR"
        log_info "To apply them manually, run:"
        log_info "  kubectl apply -f $OUTPUT_DIR/<namespace>/"
    fi

    # Print summary from centralized definitions
    print_services_summary

    # Validation reminder
    echo ""
    log_info "Next steps:"
    echo "  1. Run validation: ./scripts/validate-phase2-secrets.sh"
    echo "  2. Deploy services: helm upgrade --install <service> helm-charts/<service>/"
    echo "  3. Verify pods: kubectl get pods -n <namespace>"
}

main "$@"
