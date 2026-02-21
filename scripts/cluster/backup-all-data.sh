#!/bin/bash
# Script de backup completo de dados essenciais do Neural Hive-Mind
# Uso: ./backup-all-data.sh [ambiente]

set -e

ENV="${1:-local}"
BACKUP_DIR="backup/cluster-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "${BACKUP_DIR}"/{secrets,configmaps,clickhouse}

echo "=== Backup Neural Hive-Mind - ${ENV} ==="
echo "Diretório de backup: ${BACKUP_DIR}"

# 1.1 Inventário do Ambiente
echo "[1/7] Criando inventário do ambiente..."
kubectl get all --all-namespaces -o yaml > "${BACKUP_DIR}/cluster-inventory.yaml"
kubectl get pvc --all-namespaces -o yaml > "${BACKUP_DIR}/pvcs-inventory.yaml"
kubectl get secrets --all-namespaces -o yaml > "${BACKUP_DIR}/secrets-inventory.yaml"
kubectl get configmaps --all-namespaces -o yaml > "${BACKUP_DIR}/configmaps-inventory.yaml"
helm list --all-namespaces -o yaml > "${BACKUP_DIR}/helm-releases.yaml"
echo "Inventário criado."

# 1.2 Backup MongoDB
echo "[2/7] Backup MongoDB..."
if kubectl get statefulset -n mongodb-cluster mongodb &>/dev/null; then
  MONGO_PASSWORD=$(kubectl get secret -n mongodb-cluster neural-hive-mongodb-auth -o jsonpath='{.data.password}' | base64 -d)
  kubectl exec -n mongodb-cluster statefulset/mongodb -- \
    mongodump --uri="mongodb://root:${MONGO_PASSWORD}@localhost:27017/neural_hive?authSource=admin" \
    --archive=/tmp/neural_hive_backup.archive --gzip
  kubectl cp mongodb-cluster/mongodb-0:/tmp/neural_hive_backup.archive \
    "${BACKUP_DIR}/mongodb-neural-hive.archive.gz"
  kubectl exec -n mongodb-cluster statefulset/mongodb -- \
    mongodump --uri="mongodb://root:${MONGO_PASSWORD}@localhost:27017/ml_metadata?authSource=admin" \
    --archive=/tmp/ml_metadata_backup.archive --gzip
  kubectl cp mongodb-cluster/mongodb-0:/tmp/ml_metadata_backup.archive \
    "${BACKUP_DIR}/mongodb-ml.archive.gz"
  echo "MongoDB backup concluído."
else
  echo "AVISO: MongoDB não encontrado, pulando backup."
fi

# 1.3 Backup PostgreSQL (MLflow e Temporal)
echo "[3/7] Backup PostgreSQL..."
if kubectl get deployment -n mlflow mlflow-postgresql &>/dev/null; then
  kubectl exec -n mlflow deployment/mlflow-postgresql -- \
    pg_dump -U mlflow mlflow | gzip > "${BACKUP_DIR}/postgresql-mlflow.sql.gz"
  echo "MLflow backup concluído."
else
  echo "AVISO: MLflow PostgreSQL não encontrado, pulando."
fi

if kubectl get deployment -n temporal deployment/temporal-postgresql &>/dev/null; then
  kubectl exec -n temporal deployment/temporal-postgresql -- \
    pg_dump -U temporal temporal | gzip > "${BACKUP_DIR}/postgresql-temporal.sql.gz"
  echo "Temporal backup concluído."
else
  echo "AVISO: Temporal PostgreSQL não encontrado, pulando."
fi

# 1.4 Backup Neo4j
echo "[4/7] Backup Neo4j..."
if kubectl get statefulset -n neo4j-cluster neo4j &>/dev/null; then
  kubectl exec -n neo4j-cluster statefulset/neo4j -- \
    neo4j-admin database dump neo4j --to-path=/tmp/neo4j-backup
  kubectl cp neo4j-cluster/neo4j-0:/tmp/neo4j-backup/neo4j.dump \
    "${BACKUP_DIR}/neo4j.dump"
  echo "Neo4j backup concluído."
else
  echo "AVISO: Neo4j não encontrado, pulando backup."
fi

# 1.5 Backup ClickHouse
echo "[5/7] Backup ClickHouse..."
if kubectl get deployment -n clickhouse-cluster clickhouse &>/dev/null; then
  TIMESTAMP=$(date +%Y%m%d-%H%M%S)
  kubectl exec -n clickhouse-cluster deployment/clickhouse -- \
    clickhouse-client --query="BACKUP DATABASE neural_hive TO Disk('backups', 'neural_hive_${TIMESTAMP}.zip')"
  CLICKHOUSE_POD=$(kubectl get pod -n clickhouse-cluster -l app=clickhouse -o jsonpath='{.items[0].metadata.name}')
  kubectl cp clickhouse-cluster/${CLICKHOUSE_POD}:/var/lib/clickhouse/backups/ "${BACKUP_DIR}/clickhouse/"
  echo "ClickHouse backup concluído."
else
  echo "AVISO: ClickHouse não encontrado, pulando backup."
fi

# 1.6 Backup Secrets e ConfigMaps críticos
echo "[6/7] Backup de secrets e configmaps críticos..."
mkdir -p "${BACKUP_DIR}/secrets" "${BACKUP_DIR}/configmaps"
for ns in mongodb-cluster neo4j-cluster vault; do
  if kubectl get namespace "${ns}" &>/dev/null; then
    kubectl get secrets -n "${ns}" -o yaml > "${BACKUP_DIR}/secrets/${ns}.yaml"
    kubectl get configmaps -n "${ns}" -o yaml > "${BACKUP_DIR}/configmaps/${ns}.yaml"
  fi
done
echo "Secrets e configmaps backup concluído."

# 1.7 Documentar configurações
echo "[7/7] Documentando configurações customizadas..."
cp helm-values-eks.yaml "${BACKUP_DIR}/" 2>/dev/null || true
cp helm-values-eks-complete.yaml "${BACKUP_DIR}/" 2>/dev/null || true
env | grep -E "(AWS|MONGO|NEO4J|CLICKHOUSE|KAFKA)" > "${BACKUP_DIR}/environment-vars.txt" 2>/dev/null || true
echo "Configurações documentadas."

echo ""
echo "=== Backup Completo ==="
echo "Localização: ${BACKUP_DIR}"
echo "Tamanho: $(du -sh ${BACKUP_DIR} | cut -f1)"
