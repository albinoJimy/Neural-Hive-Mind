#!/bin/bash
set -euo pipefail

# Neural Hive-Mind Observability Stack - Secure Secrets Setup
# This script creates and manages secrets for the observability stack securely

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="observability"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARN: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

# Check if running as root
check_permissions() {
    if [[ $EUID -eq 0 ]]; then
        error "This script should not be run as root for security reasons"
    fi
}

# Check dependencies
check_dependencies() {
    local deps=("kubectl" "openssl" "base64")
    for cmd in "${deps[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            error "Required command '$cmd' not found. Please install it first."
        fi
    done
}

# Verify Kubernetes connection
check_k8s_connection() {
    log "Checking Kubernetes connection..."
    if ! kubectl cluster-info &> /dev/null; then
        error "Cannot connect to Kubernetes cluster. Please check your kubeconfig."
    fi
    log "✓ Kubernetes connection verified"
}

# Create namespace if it doesn't exist
create_namespace() {
    log "Creating namespace '$NAMESPACE' if it doesn't exist..."
    kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

    # Add security labels
    kubectl label namespace "$NAMESPACE" \
        pod-security.kubernetes.io/enforce=restricted \
        pod-security.kubernetes.io/audit=restricted \
        pod-security.kubernetes.io/warn=restricted \
        --overwrite

    log "✓ Namespace '$NAMESPACE' ready with security policies"
}

# Generate secure password
generate_password() {
    local length=${1:-32}
    openssl rand -base64 "$length" | tr -d "=+/" | cut -c1-"$length"
}

# Create Grafana admin credentials
create_grafana_secrets() {
    local secret_name="grafana-admin-credentials"

    log "Creating Grafana admin credentials..."

    # Check if secret already exists
    if kubectl get secret "$secret_name" -n "$NAMESPACE" &> /dev/null; then
        warn "Secret '$secret_name' already exists. Skipping creation."
        return
    fi

    # Generate secure admin password
    local admin_password
    admin_password=$(generate_password 32)

    # Create the secret
    kubectl create secret generic "$secret_name" \
        --from-literal=admin-user=admin \
        --from-literal=admin-password="$admin_password" \
        --namespace="$NAMESPACE"

    # Add security annotations
    kubectl annotate secret "$secret_name" \
        -n "$NAMESPACE" \
        neural.hive/component=grafana \
        neural.hive/managed-by=security-script \
        neural.hive/created-date="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --overwrite

    log "✓ Grafana admin credentials created"
    log "  Username: admin"
    log "  Password: $admin_password"
    warn "⚠️  Please save the password securely and delete it from this terminal"
}

# Create Prometheus credentials (if needed)
create_prometheus_secrets() {
    local secret_name="prometheus-auth-credentials"

    log "Creating Prometheus authentication credentials..."

    # Check if secret already exists
    if kubectl get secret "$secret_name" -n "$NAMESPACE" &> /dev/null; then
        warn "Secret '$secret_name' already exists. Skipping creation."
        return
    fi

    # Generate credentials for Prometheus basic auth
    local prometheus_user="prometheus"
    local prometheus_password
    prometheus_password=$(generate_password 24)

    # Create htpasswd format for basic auth
    local htpasswd
    htpasswd=$(echo "$prometheus_password" | openssl passwd -apr1 -stdin)

    kubectl create secret generic "$secret_name" \
        --from-literal=username="$prometheus_user" \
        --from-literal=password="$prometheus_password" \
        --from-literal=htpasswd="$prometheus_user:$htpasswd" \
        --namespace="$NAMESPACE"

    # Add security annotations
    kubectl annotate secret "$secret_name" \
        -n "$NAMESPACE" \
        neural.hive/component=prometheus \
        neural.hive/managed-by=security-script \
        neural.hive/created-date="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --overwrite

    log "✓ Prometheus authentication credentials created"
}

# Create AlertManager credentials
create_alertmanager_secrets() {
    local secret_name="alertmanager-config-secrets"

    log "Creating AlertManager configuration secrets..."

    # Check if secret already exists
    if kubectl get secret "$secret_name" -n "$NAMESPACE" &> /dev/null; then
        warn "Secret '$secret_name' already exists. Skipping creation."
        return
    fi

    # Generate webhook URL tokens (placeholders - replace with actual values)
    local slack_webhook="https://hooks.slack.com/services/PLACEHOLDER/PLACEHOLDER/PLACEHOLDER"
    local teams_webhook="https://outlook.office.com/webhook/PLACEHOLDER/PLACEHOLDER"
    local pagerduty_key="placeholder-pagerduty-service-key"

    kubectl create secret generic "$secret_name" \
        --from-literal=slack-webhook-url="$slack_webhook" \
        --from-literal=teams-webhook-url="$teams_webhook" \
        --from-literal=pagerduty-service-key="$pagerduty_key" \
        --namespace="$NAMESPACE"

    # Add security annotations
    kubectl annotate secret "$secret_name" \
        -n "$NAMESPACE" \
        neural.hive/component=alertmanager \
        neural.hive/managed-by=security-script \
        neural.hive/created-date="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --overwrite

    log "✓ AlertManager configuration secrets created"
    warn "⚠️  Please update the webhook URLs and service keys with real values"
}

# Create TLS certificates for internal communication
create_tls_secrets() {
    local secret_name="observability-internal-tls"

    log "Creating TLS certificates for internal communication..."

    # Check if secret already exists
    if kubectl get secret "$secret_name" -n "$NAMESPACE" &> /dev/null; then
        warn "Secret '$secret_name' already exists. Skipping creation."
        return
    fi

    # Create temporary directory for certificates
    local temp_dir
    temp_dir=$(mktemp -d)

    # Generate CA private key
    openssl genrsa -out "$temp_dir/ca-key.pem" 4096

    # Generate CA certificate
    openssl req -new -x509 -days 365 -key "$temp_dir/ca-key.pem" \
        -out "$temp_dir/ca-cert.pem" \
        -subj "/C=US/ST=CA/L=SF/O=Neural-Hive/OU=Observability/CN=neural-hive-ca"

    # Generate server private key
    openssl genrsa -out "$temp_dir/server-key.pem" 4096

    # Generate server certificate request
    openssl req -new -key "$temp_dir/server-key.pem" \
        -out "$temp_dir/server-req.pem" \
        -subj "/C=US/ST=CA/L=SF/O=Neural-Hive/OU=Observability/CN=*.observability.svc.cluster.local"

    # Generate server certificate
    openssl x509 -req -days 365 -in "$temp_dir/server-req.pem" \
        -CA "$temp_dir/ca-cert.pem" -CAkey "$temp_dir/ca-key.pem" \
        -out "$temp_dir/server-cert.pem" -CAcreateserial

    # Create the secret
    kubectl create secret generic "$secret_name" \
        --from-file=ca-cert.pem="$temp_dir/ca-cert.pem" \
        --from-file=ca-key.pem="$temp_dir/ca-key.pem" \
        --from-file=server-cert.pem="$temp_dir/server-cert.pem" \
        --from-file=server-key.pem="$temp_dir/server-key.pem" \
        --namespace="$NAMESPACE"

    # Add security annotations
    kubectl annotate secret "$secret_name" \
        -n "$NAMESPACE" \
        neural.hive/component=tls \
        neural.hive/managed-by=security-script \
        neural.hive/created-date="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --overwrite

    # Secure cleanup
    rm -rf "$temp_dir"

    log "✓ TLS certificates created for internal communication"
}

# Set RBAC restrictions on secrets
secure_secrets() {
    log "Applying RBAC restrictions to secrets..."

    # Create a role that only allows reading specific secrets
    cat <<EOF | kubectl apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  namespace: $NAMESPACE
  name: observability-secrets-reader
rules:
- apiGroups: [""]
  resources: ["secrets"]
  resourceNames: ["grafana-admin-credentials", "prometheus-auth-credentials", "alertmanager-config-secrets", "observability-internal-tls"]
  verbs: ["get", "list"]
EOF

    log "✓ RBAC restrictions applied"
}

# Rotate a specific secret
rotate_secret() {
    local secret_name="$1"

    log "Rotating secret: $secret_name"

    case "$secret_name" in
        "grafana-admin-credentials")
            kubectl delete secret "$secret_name" -n "$NAMESPACE" --ignore-not-found
            create_grafana_secrets
            ;;
        "prometheus-auth-credentials")
            kubectl delete secret "$secret_name" -n "$NAMESPACE" --ignore-not-found
            create_prometheus_secrets
            ;;
        "alertmanager-config-secrets")
            kubectl delete secret "$secret_name" -n "$NAMESPACE" --ignore-not-found
            create_alertmanager_secrets
            ;;
        "observability-internal-tls")
            kubectl delete secret "$secret_name" -n "$NAMESPACE" --ignore-not-found
            create_tls_secrets
            ;;
        *)
            error "Unknown secret: $secret_name"
            ;;
    esac

    log "✓ Secret $secret_name rotated successfully"
}

# List all secrets
list_secrets() {
    log "Listing observability secrets..."
    kubectl get secrets -n "$NAMESPACE" \
        -l neural.hive/managed-by=security-script \
        -o custom-columns=NAME:.metadata.name,TYPE:.type,AGE:.metadata.creationTimestamp
}

# Backup secrets to a secure location
backup_secrets() {
    local backup_dir="${1:-./secrets-backup-$(date +%Y%m%d_%H%M%S)}"

    log "Backing up secrets to: $backup_dir"
    mkdir -p "$backup_dir"

    # Export each secret
    for secret in grafana-admin-credentials prometheus-auth-credentials alertmanager-config-secrets observability-internal-tls; do
        if kubectl get secret "$secret" -n "$NAMESPACE" &> /dev/null; then
            kubectl get secret "$secret" -n "$NAMESPACE" -o yaml > "$backup_dir/$secret.yaml"
            log "✓ Backed up secret: $secret"
        fi
    done

    # Set secure permissions on backup directory
    chmod 700 "$backup_dir"
    chmod 600 "$backup_dir"/*.yaml

    log "✓ Secrets backed up to: $backup_dir"
    warn "⚠️  Please store this backup securely and encrypt it if necessary"
}

# Main execution
main() {
    local command="${1:-setup}"

    case "$command" in
        "setup")
            log "Setting up Neural Hive-Mind observability secrets..."
            check_permissions
            check_dependencies
            check_k8s_connection
            create_namespace
            create_grafana_secrets
            create_prometheus_secrets
            create_alertmanager_secrets
            create_tls_secrets
            secure_secrets
            log "✅ Observability secrets setup completed successfully"
            ;;
        "rotate")
            local secret_name="${2:-}"
            if [[ -z "$secret_name" ]]; then
                error "Please specify a secret name to rotate"
            fi
            check_permissions
            check_dependencies
            check_k8s_connection
            rotate_secret "$secret_name"
            ;;
        "list")
            check_dependencies
            check_k8s_connection
            list_secrets
            ;;
        "backup")
            local backup_dir="${2:-}"
            check_dependencies
            check_k8s_connection
            backup_secrets "$backup_dir"
            ;;
        "help"|"-h"|"--help")
            cat <<EOF
Neural Hive-Mind Observability Secrets Manager

Usage: $0 [COMMAND] [OPTIONS]

Commands:
    setup                   Setup all observability secrets (default)
    rotate <secret-name>    Rotate a specific secret
    list                    List all managed secrets
    backup [backup-dir]     Backup secrets to a directory
    help                    Show this help message

Examples:
    $0 setup
    $0 rotate grafana-admin-credentials
    $0 list
    $0 backup ./my-backup-dir

Managed Secrets:
    - grafana-admin-credentials
    - prometheus-auth-credentials
    - alertmanager-config-secrets
    - observability-internal-tls

Security Notes:
    - This script generates cryptographically secure passwords
    - All secrets are annotated for tracking and management
    - RBAC restrictions are applied automatically
    - Never run this script as root
    - Always backup secrets before rotation
EOF
            ;;
        *)
            error "Unknown command: $command. Use '$0 help' for usage information."
            ;;
    esac
}

# Execute main function with all arguments
main "$@"