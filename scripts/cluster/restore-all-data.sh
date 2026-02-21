#!/bin/bash
# Script de restore completo de dados essenciais do Neural Hive-Mind
# Uso: ./restore-all-data.sh <backup-dir>

set -e

BACKUP_DIR="${1}"
if [[ -z "${BACKUP_DIR}" || ! -d "${BACKUP_DIR}" ]]; then
  echo "ERRO: Diretório de backup inválido: ${BACKUP_DIR}"
  echo "Uso: ./restore-all-data.sh <backup-dir>"
  exit 1
fi

echo "=== Restore Neural Hive-Mind ==="
echo "Diretório de backup: ${BACKUP_DIR}"

# Aguardar bancos estarem prontos
echo "Aguardando bancos de dados ficarem prontos..."
kubectl wait --for=condition=ready pod -l app=mongodb -n mongodb-cluster --timeout=300s 2>/dev/null || true
kubectl wait --for=condition=ready pod -l app=neo4j -n neo4j-cluster --timeout=300s 2>/dev/null || true
kubectl wait --for=condition=ready pod -l app=clickhouse -n clickhouse-cluster --timeout=300s 2>/dev/null || true
kubectl wait --for=condition=ready pod -l statefulset.kubernetes.io/pod-name=mongodb-0 -n mongodb-cluster --timeout=300s 2>/dev/null || true

# Restore MongoDB
echo "[1/4] Restore MongoDB..."
if [[ -f "${BACKUP_DIR}/mongodb-neural-hive.archive.gz" ]]; then
  MONGO_PASSWORD=$(kubectl get secret -n mongodb-cluster neural-hive-mongodb-auth -o jsonpath='{.data.password}' | base64 -d)
  kubectl cp "${BACKUP_DIR}/mongodb-neural-hive.archive.gz" \
    mongodb-cluster/mongodb-0:/tmp/neural_hive_backup.archive.gz
  kubectl exec -n mongodb-cluster statefulset/mongodb -- \
    mongorestore --uri="mongodb://root:${MONGO_PASSWORD}@localhost:27017/?authSource=admin" \
    --archive=/tmp/neural_hive_backup.archive.gz --gzip --drop
  echo "MongoDB neural_hive restore concluído."
else
  echo "AVISO: Backup MongoDB neural_hive não encontrado."
fi

if [[ -f "${BACKUP_DIR}/mongodb-ml.archive.gz" ]]; then
  kubectl cp "${BACKUP_DIR}/mongodb-ml.archive.gz" \
    mongodb-cluster/mongodb-0:/tmp/ml_metadata_backup.archive.gz
  kubectl exec -n mongodb-cluster statefulset/mongodb -- \
    mongorestore --uri="mongodb://root:${MONGO_PASSWORD}@localhost:27017/?authSource=admin" \
    --archive=/tmp/ml_metadata_backup.archive.gz --gzip --drop
  echo "MongoDB ml_metadata restore concluído."
else
  echo "AVISO: Backup MongoDB ml_metadata não encontrado."
fi

# Restore PostgreSQL (MLflow e Temporal)
echo "[2/4] Restore PostgreSQL..."
if [[ -f "${BACKUP_DIR}/postgresql-mlflow.sql.gz" ]]; then
  gunzip < "${BACKUP_DIR}/postgresql-mlflow.sql.gz" | \
    kubectl exec -i -n mlflow deployment/mlflow-postgresql -- \
    psql -U mlflow mlflow
  echo "MLflow restore concluído."
else
  echo "AVISO: Backup MLflow não encontrado."
fi

if [[ -f "${BACKUP_DIR}/postgresql-temporal.sql.gz" ]]; then
  gunzip < "${BACKUP_DIR}/postgresql-temporal.sql.gz" | \
    kubectl exec -i -n temporal deployment/temporal-postgresql -- \
    psql -U temporal temporal
  echo "Temporal restore concluído."
else
  echo "AVISO: Backup Temporal não encontrado."
fi

# Restore Neo4j
echo "[3/4] Restore Neo4j..."
if [[ -f "${BACKUP_DIR}/neo4j.dump" ]]; then
  kubectl cp "${BACKUP_DIR}/neo4j.dump" neo4j-cluster/neo4j-0:/tmp/neo4j.dump
  kubectl exec -n neo4j-cluster statefulset/neo4j -- \
    neo4j-admin database load neo4j --from-path=/tmp --overwrite-destination=true
  echo "Neo4j restore concluído."
else
  echo "AVISO: Backup Neo4j não encontrado."
fi

# Restore ClickHouse
echo "[4/4] Restore ClickHouse..."
if [[ -d "${BACKUP_DIR}/clickhouse/backups" ]]; then
  for backup in "${BACKUP_DIR}"/clickhouse/backups/*.zip; do
    if [[ -f "${backup}" ]]; then
      backup_name=$(basename "${backup}")
      CLICKHOUSE_POD=$(kubectl get pod -n clickhouse-cluster -l app=clickhouse -o jsonpath='{.items[0].metadata.name}')
      kubectl cp "${backup}" clickhouse-cluster/${CLICKHOUSE_POD}:/var/lib/clickhouse/backups/
      kubectl exec -n clickhouse-cluster deployment/clickhouse -- \
        clickhouse-client --query="RESTORE DATABASE neural_hive FROM Disk('backups', '${backup_name}')"
      echo "ClickHouse restore ${backup_name} concluído."
    fi
  done
else
  echo "AVISO: Backups ClickHouse não encontrados."
fi

echo ""
echo "=== Restore Completo ==="
echo "Verificar estado dos bancos:"
echo "  MongoDB: kubectl get pods -n mongodb-cluster"
echo "  PostgreSQL: kubectl get pods -n mlflow -n temporal"
echo "  Neo4j: kubectl get pods -n neo4j-cluster"
echo "  ClickHouse: kubectl get pods -n clickhouse-cluster"
