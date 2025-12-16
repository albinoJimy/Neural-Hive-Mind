#!/bin/bash
#===============================================================================
# Script: setup-registry-mirror.sh
# Description: Configures containerd on worker nodes to use local registry
# Usage: ./setup-registry-mirror.sh [REGISTRY_IP] [REGISTRY_PORT]
#===============================================================================

set -euo pipefail

# Configuration
REGISTRY_IP="${1:-37.60.241.150}"
REGISTRY_PORT="${2:-30500}"
REGISTRY_URL="${REGISTRY_IP}:${REGISTRY_PORT}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Worker nodes
WORKERS=(
    "root@158.220.101.216"  # vmi2911680
    "root@84.247.138.35"    # vmi2911681
)

# Containerd config for registry mirror
generate_containerd_config() {
    cat <<EOF
# Registry mirror configuration for Neural-Hive-Mind
# Added by setup-registry-mirror.sh

[plugins."io.containerd.grpc.v1.cri".registry]
  [plugins."io.containerd.grpc.v1.cri".registry.mirrors]
    [plugins."io.containerd.grpc.v1.cri".registry.mirrors."${REGISTRY_URL}"]
      endpoint = ["http://${REGISTRY_URL}"]
    [plugins."io.containerd.grpc.v1.cri".registry.mirrors."docker.io"]
      endpoint = ["http://${REGISTRY_URL}", "https://registry-1.docker.io"]
  [plugins."io.containerd.grpc.v1.cri".registry.configs]
    [plugins."io.containerd.grpc.v1.cri".registry.configs."${REGISTRY_URL}".tls]
      insecure_skip_verify = true
EOF
}

# Containerd hosts.toml for containerd 2.x (workers use 2.1.5)
generate_hosts_toml() {
    cat <<EOF
server = "http://${REGISTRY_URL}"

[host."http://${REGISTRY_URL}"]
  capabilities = ["pull", "resolve", "push"]
  skip_verify = true
EOF
}

configure_worker() {
    local worker=$1
    log_info "Configuring worker: $worker"

    # Check containerd version
    local version=$(ssh -o StrictHostKeyChecking=no "$worker" "containerd --version 2>/dev/null | grep -oP '\d+\.\d+' | head -1" || echo "1.7")
    log_info "Containerd version on $worker: $version"

    # For containerd 2.x, use hosts.toml approach
    if [[ "$version" == "2."* ]]; then
        log_info "Using containerd 2.x configuration (hosts.toml)"

        # Create hosts directory
        ssh -o StrictHostKeyChecking=no "$worker" "mkdir -p /etc/containerd/certs.d/${REGISTRY_URL}"

        # Write hosts.toml
        generate_hosts_toml | ssh -o StrictHostKeyChecking=no "$worker" "cat > /etc/containerd/certs.d/${REGISTRY_URL}/hosts.toml"

        # Also add for localhost reference
        ssh -o StrictHostKeyChecking=no "$worker" "mkdir -p /etc/containerd/certs.d/localhost:${REGISTRY_PORT}"
        generate_hosts_toml | ssh -o StrictHostKeyChecking=no "$worker" "cat > /etc/containerd/certs.d/localhost:${REGISTRY_PORT}/hosts.toml"

        # Ensure config.toml has config_path set
        ssh -o StrictHostKeyChecking=no "$worker" "grep -q 'config_path' /etc/containerd/config.toml || sed -i '/\[plugins\.\"io\.containerd\.grpc\.v1\.cri\"\.registry\]/a\      config_path = \"/etc/containerd/certs.d\"' /etc/containerd/config.toml 2>/dev/null || true"

    else
        log_info "Using containerd 1.x configuration (config.toml)"

        # Backup existing config
        ssh -o StrictHostKeyChecking=no "$worker" "cp /etc/containerd/config.toml /etc/containerd/config.toml.backup.$(date +%Y%m%d%H%M%S) 2>/dev/null || true"

        # Check if registry section exists
        if ssh -o StrictHostKeyChecking=no "$worker" "grep -q 'registry.mirrors' /etc/containerd/config.toml 2>/dev/null"; then
            log_warn "Registry mirrors already configured, skipping..."
        else
            # Append registry config
            generate_containerd_config | ssh -o StrictHostKeyChecking=no "$worker" "cat >> /etc/containerd/config.toml"
        fi
    fi

    # Restart containerd
    log_info "Restarting containerd on $worker..."
    ssh -o StrictHostKeyChecking=no "$worker" "systemctl restart containerd"

    # Verify containerd is running
    if ssh -o StrictHostKeyChecking=no "$worker" "systemctl is-active --quiet containerd"; then
        log_info "Containerd restarted successfully on $worker"
    else
        log_error "Failed to restart containerd on $worker"
        return 1
    fi
}

verify_registry_access() {
    local worker=$1
    log_info "Verifying registry access from $worker..."

    if ssh -o StrictHostKeyChecking=no "$worker" "curl -s -o /dev/null -w '%{http_code}' http://${REGISTRY_URL}/v2/" | grep -q "200"; then
        log_info "Registry is accessible from $worker"
        return 0
    else
        log_warn "Registry not accessible from $worker (may not be deployed yet)"
        return 1
    fi
}

main() {
    log_info "=============================================="
    log_info "Configuring containerd registry mirror"
    log_info "Registry URL: http://${REGISTRY_URL}"
    log_info "=============================================="

    for worker in "${WORKERS[@]}"; do
        echo ""
        configure_worker "$worker"
        verify_registry_access "$worker" || true
    done

    echo ""
    log_info "=============================================="
    log_info "Configuration complete!"
    log_info "=============================================="
    log_info ""
    log_info "Next steps:"
    log_info "1. Deploy the registry: helm install registry helm-charts/docker-registry -n registry --create-namespace"
    log_info "2. Tag and push images: docker tag myimage ${REGISTRY_URL}/myimage && docker push ${REGISTRY_URL}/myimage"
    log_info "3. Use in k8s: image: ${REGISTRY_URL}/myimage:tag"
}

main "$@"
