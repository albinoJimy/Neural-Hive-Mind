#!/bin/bash
# Restore PostgreSQL Temporal from S3 backup

BACKUP_FILE=$1
POSTGRES_HOST="postgres-temporal-headless.temporal-postgres.svc.cluster.local"

# Download backup from S3
aws s3 cp s3://neural-hive-backups-prod/temporal/backups/${BACKUP_FILE} /tmp/

# Stop Temporal services
kubectl scale deployment temporal-frontend --replicas=0 -n temporal

# Restore database
gunzip -c /tmp/${BACKUP_FILE} | pg_restore -h $POSTGRES_HOST -U temporal -d temporal --clean --if-exists

# Restart Temporal services
kubectl scale deployment temporal-frontend --replicas=3 -n temporal

echo "Restore completed: ${BACKUP_FILE}"
