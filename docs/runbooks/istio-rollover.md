# Istio Rollout Runbook

## Overview
Runbook para rollout de Istio sidecar injection em namespaces do Neural-Hive-Mind.

## Prerequisites
- Istio control plane instalado e healthy
- Namespace existe e tem deployments

## Rollout Steps

1. **Label namespace**
```bash
kubectl label namespace <NAMESPACE> \
  istio-injection=enabled \
  istio.io_rev=default \
  --overwrite
```

2. **Rollout deployments**
```bash
./scripts/istio-rollout.sh <NAMESPACE>
```

3. **Verify sidecars**
```bash
kubectl get pods -n <NAMESPACE> -o json | \
  jq -r '.items[] | select(.spec.containers[].name == "istio-proxy") | .metadata.name'
```

## Rollback
Se houver problemas:
```bash
kubectl label namespace <NAMESPACE> istio-injection=disabled --overwrite
kubectl rollout undo deployment/<DEPLOYMENT> -n <NAMESPACE>
```

## Troubleshooting
- Sidecar não injetado: Verificar label do namespace
- Pods CrashLoop: Verificar logs `kubectl logs <POD> -c istio-proxy`
- Comunicação falhando: Verificar mesh policy com `kubectl get meshpolicy`