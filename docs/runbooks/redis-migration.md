# Redis Migration Runbook

## Overview
Runbook para migração zero-downtime de Redis single pod para Redis Cluster.

## Prerequisites
- Backup completo do Redis atual
- Certificados TLS gerados
- Novo Redis Cluster instalado e healthy

## Migration Steps

1. **Backup**
```bash
./scripts/redis-backup.sh
./scripts/redis-verify-backup.sh
```

2. **Deploy New Cluster**
```bash
./scripts/redis-cluster-install.sh dev
```

3. **Sync Data**
```bash
./scripts/redis-sync-setup.sh
# Wait for sync...
./scripts/redis-sync-verify.sh
```

4. **Migrate Applications**
```bash
./scripts/redis-migrate-apps.sh neural-hive
./scripts/redis-migrate-apps.sh approval
```

5. **Switch DNS**
```bash
./scripts/redis-switch-dns.sh
```

6. **Cleanup**
```bash
./scripts/redis-cleanup.sh 7
```

## Verification

Testar após migração:
```bash
kubectl exec -n neural-hive <POD> -- redis-cli -h redis-cluster -p 6379 PING
kubectl exec -n neural-hive <POD> -- redis-cli -h redis-cluster -p 6379 SET test-key "test-value"
kubectl exec -n neural-hive <POD> -- redis-cli -h redis-cluster -p 6379 GET test-key
```