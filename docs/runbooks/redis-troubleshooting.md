# Redis Cluster Troubleshooting Runbook

## Common Issues

### Cluster nodes not communicating
**Symptom:** `CLUSTER INFO` shows cluster_state:fail

**Diagnosis:**
```bash
kubectl exec -n redis-cluster redis-cluster-0 -- redis-cli cluster nodes
kubectl exec -n redis-cluster redis-cluster-0 -- redis-cli cluster info
```

**Solution:**
- Verificar network policies
- Verificar TLS certificates são válidos
- Recriar cluster: `kubectl exec -n redis-cluster redis-cluster-0 -- redis-cli --cluster create ...`

### TLS handshake errors
**Symptom:** Application logs show "TLS handshake failed"

**Diagnosis:**
```bash
kubectl get secrets -n redis-cluster | grep tls
kubectl describe secret redis-server-tls -n redis-cluster
```

**Solution:**
- Verificar client certificates estão montados nos pods
- Verificar CA certificate está correto
- Verificar certificate não expirou

### Keys not syncing
**Symptom:** Different key counts between old and new

**Diagnosis:**
```bash
./scripts/redis-sync-verify.sh
```

**Solution:**
- Verificar sync tool está rodando
- Forçar sync manual
- Verificar não há chaves expirando