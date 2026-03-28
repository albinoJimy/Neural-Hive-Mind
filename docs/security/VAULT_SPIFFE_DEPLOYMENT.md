# Vault/SPIFFE Deployment Guide

## Overview

This guide explains how to activate Vault and SPIFFE (via SPIRE) for Neural Hive-Mind services.

## Prerequisites

- Kubernetes cluster (v1.25+)
- Helm 3.x
- kubectl configured
- jq installed

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Neural Hive-Mind Cluster                     │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Vault (vault namespace)                  │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │ │
│  │  │ KV Secrets   │  │ PKI (CA/Certs)│  │ Database Creds │      │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘      │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              ▲                                    │
│                              │ Kubernetes Auth                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    SPIRE (spire namespace)                 │ │
│  │  ┌──────────────┐              ┌──────────────┐              │ │
│  │  │ SPIRE Server  │◄─────────────┤ SPIRE Agent  │              │ │
│  │  │              │  Workload API │              │              │ │
│  │  └──────────────┘              └──────────────┘              │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              ▲                                    │
│                              │ Unix Socket                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              Neural Hive Services                          │ │
│  │  ┌───────────┐ ┌──────────┐ ┌───────────┐ ┌────────────┐   │ │
│  │  │ Gateway   │ │   STE    │ │ Consensus │ │ Orchestrator│  │ │
│  │  │           │ │          │ │           │ │             │  │ │
│  │  │ Vault     │ │ SPIFFE   │ │ Vault     │ │ SPIFFE      │  │ │
│  │  │ Client    │ │ Manager  │ │ Client    │ │ Manager     │  │ │
│  │  └───────────┘ └──────────┘ └───────────┘ └────────────┘   │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

## Step 1: Deploy Vault

```bash
# Deploy Vault with HA and Raft storage
helm install vault helm-charts/vault \
  --namespace vault \
  --create-namespace \
  --set server.replicas=3 \
  --set server.ha.enabled=true \
  --set server.ha.raft.enabled=true

# Wait for Vault pods to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=vault -n vault --timeout=300s
```

## Step 2: Initialize Vault

```bash
# Run initialization script
./scripts/security/vault-init.sh vault

# This will:
# - Initialize Vault (first time only)
# - Unseal Vault
# - Enable Kubernetes authentication
# - Enable secrets engines (KV, PKI, Database)
# - Create policies for services
# - Save unseal key and root token to project root
```

## Step 3: Deploy SPIRE

```bash
# Deploy SPIRE server and agent daemonset
helm install spire helm-charts/spire \
  --namespace spire \
  --create-namespace

# Wait for SPIRE server to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=spire-server -n spire --timeout=300s
```

## Step 4: Initialize SPIRE

```bash
# Run SPIRE initialization script
./scripts/security/spire-init.sh spire

# This will:
# - Create registration entries for all services
# - Generate trust bundle
# - Verify SPIRE agent connectivity
```

## Step 5: Activate Vault/SPIFFE in Services

### For Gateway (example)

```bash
# Enable Vault and SPIFFE
helm upgrade gateway-intencoes helm-charts/gateway-intencoes \
  --namespace neural-hive-system \
  --set config.security.vault.enabled=true \
  --set config.security.spiffe.enabled=true \
  --set config.security.vault.address="https://vault.vault.svc.cluster.local:8200" \
  --set config.security.vault.tlsVerify=true
```

### Environment Variables

When enabled, the following environment variables are set automatically:

**Vault:**
```bash
SECURITY_ENABLE_VAULT=true
VAULT_ADDRESS=https://vault.vault.svc.cluster.local:8200
VAULT_AUTH_METHOD=kubernetes
VAULT_KUBERNETES_ROLE=gateway-intencoes
VAULT_MOUNT_PATH_KV=secret
VAULT_MOUNT_PATH_PKI=pki
VAULT_TLS_VERIFY=true
```

**SPIFFE:**
```bash
SECURITY_ENABLE_SPIFFE=true
SPIFFE_TRUST_DOMAIN=neural-hive.local
SPIFFE_WORKLOAD_API_SOCKET=unix:///run/spire/sockets/agent.sock
SPIFFE_JWT_AUDIENCE=vault.neural-hive.local
SPIFFE_JWT_TTL_SECONDS=3600
```

## Step 6: Verify Integration

### Check Vault Status

```bash
# Port-forward to Vault
kubectl port-forward -n vault vault-0 8200:8200

# Login with root token
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=$(cat .vault-root-token)

# Check status
vault status
vault auth list
vault secrets list

# Test KV access
vault kv get secret/gateway-intencoes/config
```

### Check SPIRE Entries

```bash
# List all registered entries
kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server entry show

# Check specific service
kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server entry get \
  -spiffeID spiffe://neural-hive.local/neural-hive-system/gateway-intencoes
```

### Verify SVID in Pod

```bash
# Check if SPIRE socket is mounted
kubectl exec -n neural-hive-system deployment/gateway-intencoes -- ls -la /run/spire/sockets/

# Test workload API (if SPIFFE is enabled)
kubectl exec -n neural-hive-system deployment/gateway-intencoes -- \
  curl -s --unix-socket /run/spire/sockets/agent.sock \
  http://SPIRE_PrivateGroupID/bundle/x509
```

## Rollback Plan

If issues occur, disable Vault/SPIFFE:

```bash
# Disable in service
helm upgrade gateway-intencoes helm-charts/gateway-intencoes \
  --namespace neural-hive-system \
  --set config.security.vault.enabled=false \
  --set config.security.spiffe.enabled=false

# Or use fail-open mode (fallback to env vars)
helm upgrade gateway-intencoes helm-charts/gateway-intencoes \
  --namespace neural-hive-system \
  --set config.security.vault.enabled=true \
  --set config.security.vault.failOpen=true
```

## Monitoring

### Vault Metrics

Vault exposes Prometheus metrics on port 9090:

```bash
# Port-forward
kubectl port-forward -n vault vault-0 9090:9090

# Access metrics
curl http://localhost:9090/metrics
```

Key metrics:
- `vault_request_count` - Total requests
- `vault_token_count` - Active tokens
- `vault_lease_count` - Active leases

### SPIRE Metrics

SPIRE exposes Prometheus metrics on port 9091:

```bash
# Port-forward
kubectl port-forward -n spire spire-server-0 9091:9091

# Access metrics
curl http://localhost:9091/metrics
```

## Troubleshooting

### Vault Issues

**Problem:** Vault won't unseal
```bash
# Unseal manually
kubectl exec -n vault vault-0 -- vault operator unseal $(cat .vault-unseal-key)
```

**Problem:** Services can't authenticate
```bash
# Check Kubernetes auth config
kubectl exec -n vault vault-0 -- vault read auth/kubernetes/config

# Verify role exists
kubectl exec -n vault vault-0 -- vault read auth/kubernetes/role/gateway-intencoes
```

### SPIRE Issues

**Problem:** Socket not found in pod
```bash
# Verify SPIRE agent daemonset is running
kubectl get pods -n spire -l app.kubernetes.io/name=spire-agent

# Check agent logs
kubectl logs -n spire -l app.kubernetes.io/name=spire-agent --tail=50
```

**Problem:** No SVIDs issued
```bash
# Check registration entries
kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server entry show

# Verify pod selector matches
kubectl get pods -n neural-hive-system -L app.kubernetes.io/name
```

## Security Considerations

1. **Root Token:** Never commit `.vault-root-token` or `.vault-unseal-key`
2. **RBAC:** Use principle of least privilege for service roles
3. **Audit:** Enable Vault audit logging in production
4. **TLS:** Always use TLS in production (set `VAULT_TLS_VERIFY=true`)
5. **Token TTL:** Rotate Vault tokens regularly (default: 24h)

## References

- [Vault Kubernetes Integration](https://developer.hashicorp.com/vault/tutorials/kubernetes/kubernetes-minikube)
- [SPIRE Kubernetes Tutorial](https://spiffe.io/docs/latest/spire/installing/spire-kubernetes/)
- [neural_hive_security library](../libraries/security/neural_hive_security/)

## Next Steps

1. Test with one service first (e.g., gateway-intencoes)
2. Monitor logs for authentication errors
3. Gradually roll out to other services
4. Set up automated token rotation
5. Configure Vault audit logging
