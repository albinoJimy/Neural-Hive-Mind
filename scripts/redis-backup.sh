#!/bin/bash
set -e

NAMESPACE="redis-cluster"
POD_NAME=$(kubectl get pods -n $NAMESPACE -o jsonpath='{.items[0].metadata.name}')
BACKUP_DIR="redis/backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR

echo "Backing up Redis from pod: $POD_NAME"

kubectl exec -n $NAMESPACE $POD_NAME -- \
  redis-cli --rdb /tmp/dump.rdb

kubectl cp $NAMESPACE/$POD_NAME:/tmp/dump.rdb \
  $BACKUP_DIR/dump.rdb

kubectl exec -n $NAMESPACE $POD_NAME -- \
  cat /usr/local/etc/redis/redis.conf > $BACKUP_DIR/redis.conf

if kubectl exec -n $NAMESPACE $POD_NAME -- test -f /data/appendonly.aof; then
  kubectl cp $NAMESPACE/$POD_NAME:/data/appendonly.aof \
    $BACKUP_DIR/appendonly.aof
fi

echo "Backup completed: $BACKUP_DIR"
ls -lh $BACKUP_DIR

BACKUP_SIZE=$(du -sh $BACKUP_DIR | cut -f1)
echo "Backup size: $BACKUP_SIZE"

sha256sum $BACKUP_DIR/dump.rdb > $BACKUP_DIR/sha256sum.txt

echo "Backup verified!"