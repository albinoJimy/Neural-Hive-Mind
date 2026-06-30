#!/bin/bash
# 01-backup.sh — Fase 0 da convergencia-dbs
#
# Cria um snapshot verificavel ANTES de qualquer escrita:
#   - mongodump das 4 DBs Mongo neural* (gzip, --archive)
#   - pg_dump de TODAS as DBs PostgreSQL nao-sistema da instancia de dados
#     (custom format, comprimido). Cobre os tickets canonicos reais, que
#     residem em sla_management.execution_tickets (a DB neural_hive_tickets
#     esta GENUINAMENTE vazia: execution_tickets=0, confirmado por COUNT(*)
#     direto). Iterar todas as DBs garante cobertura total ("backup
#     verificavel") sem depender de uma premissa de fonte-de-verdade errada.
# Tudo via 'kubectl exec' dentro dos pods (que tem as ferramentas),
# seguindo o padrao de scripts/cluster/backup-all-data.sh.
#
# Idempotente: cada execucao cria um diretorio timestampado proprio em
# ./.db-backups/<UTC-timestamp>/ (nunca sobrescreve um backup anterior).
# Os dumps sao binarios grandes e NAO sao commitados (.db-backups/ no .gitignore).
#
# Env vars (sem segredos hardcoded):
#   MONGO_NS / MONGO_POD / MONGO_CONTAINER / MONGO_USER / MONGO_PASSWORD
#   PG_NS / PG_POD / PG_USER
#   PG_DBS (default: vazio => descobre todas as DBs nao-sistema da instancia;
#           se definido, lista de DBs separada por espacos a fazer dump)
#   BACKUP_ROOT (default: <repo>/.db-backups)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

MONGO_NS="${MONGO_NS:-mongodb-cluster}"
MONGO_CONTAINER="${MONGO_CONTAINER:-mongodb}"
MONGO_USER="${MONGO_USER:-root}"
MONGO_POD="${MONGO_POD:-}"
MONGO_DBS=(neural_hive neural_hive_dev neural_hive_orchestration neural_hive_workers)

PG_NS="${PG_NS:-neural-hive-data}"
PG_POD="${PG_POD:-}"
PG_USER="${PG_USER:-sla_user}"
# PG_DBS vazio => descoberta automatica de todas as DBs nao-sistema.
PG_DBS="${PG_DBS:-}"

BACKUP_ROOT="${BACKUP_ROOT:-${REPO_ROOT}/.db-backups}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${BACKUP_ROOT}/${TS}"

log() { echo "[backup] $*" >&2; }

# ---- Resolver pod Mongo ----
if [[ -z "${MONGO_POD}" ]]; then
  MONGO_POD="$(kubectl get pod -n "${MONGO_NS}" -l app=mongodb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
fi
[[ -n "${MONGO_POD}" ]] || { log "ERRO: pod MongoDB nao encontrado em ${MONGO_NS} (defina MONGO_POD)."; exit 1; }

# ---- Resolver password Mongo (env > secret) ----
if [[ -z "${MONGO_PASSWORD:-}" ]]; then
  MONGO_PASSWORD="$(kubectl get secret -n "${MONGO_NS}" mongodb -o jsonpath='{.data.mongodb-root-password}' 2>/dev/null | base64 -d || true)"
fi
[[ -n "${MONGO_PASSWORD:-}" ]] || { log "ERRO: MONGO_PASSWORD vazio (env var ou secret mongodb-cluster/mongodb)."; exit 1; }

# ---- Resolver pod PostgreSQL ----
if [[ -z "${PG_POD}" ]]; then
  PG_POD="$(kubectl get pod -n "${PG_NS}" -o jsonpath='{.items[?(@.metadata.labels.app=="postgres-sla")].metadata.name}' 2>/dev/null || true)"
  if [[ -z "${PG_POD}" ]]; then
    PG_POD="$(kubectl get pod -n "${PG_NS}" -o name 2>/dev/null | grep -i postgres | head -1 | sed 's#pod/##' || true)"
  fi
fi

mkdir -p "${BACKUP_DIR}"
log "Diretorio de backup: ${BACKUP_DIR}"
log "Pod MongoDB: ${MONGO_NS}/${MONGO_POD}"

MANIFEST="${BACKUP_DIR}/MANIFEST.txt"
{
  echo "Backup convergencia-dbs Fase 0"
  echo "timestamp_utc=${TS}"
  echo "kube_context=$(kubectl config current-context 2>/dev/null || echo desconhecido)"
  echo "mongo=${MONGO_NS}/${MONGO_POD}"
  echo "pg=${PG_NS}/${PG_POD:-<nao-encontrado>}"
} > "${MANIFEST}"

# ---- mongodump por DB ----
for db in "${MONGO_DBS[@]}"; do
  log "mongodump ${db}..."
  REMOTE="/tmp/dbconv_${db}_${TS}.archive.gz"
  LOCAL="${BACKUP_DIR}/mongo-${db}.archive.gz"
  if kubectl exec -n "${MONGO_NS}" "${MONGO_POD}" -c "${MONGO_CONTAINER}" -- \
      mongodump \
        --uri="mongodb://${MONGO_USER}:${MONGO_PASSWORD}@localhost:27017/${db}?authSource=admin" \
        --archive="${REMOTE}" --gzip 2>/dev/null; then
    kubectl cp "${MONGO_NS}/${MONGO_POD}:${REMOTE}" "${LOCAL}" -c "${MONGO_CONTAINER}" >/dev/null 2>&1 || \
      kubectl cp "${MONGO_NS}/${MONGO_POD}:${REMOTE}" "${LOCAL}" >/dev/null 2>&1
    kubectl exec -n "${MONGO_NS}" "${MONGO_POD}" -c "${MONGO_CONTAINER}" -- rm -f "${REMOTE}" 2>/dev/null || true
    SZ="$(du -h "${LOCAL}" 2>/dev/null | cut -f1)"
    log "  -> ${LOCAL} (${SZ})"
    echo "mongo:${db}=mongo-${db}.archive.gz (${SZ})" >> "${MANIFEST}"
  else
    log "  AVISO: mongodump de ${db} falhou (DB inexistente ou inacessivel)."
    echo "mongo:${db}=FALHOU" >> "${MANIFEST}"
  fi
done

# ---- pg_dump de TODAS as DBs PostgreSQL nao-sistema ----
# Os tickets canonicos REAIS vivem em sla_management.execution_tickets;
# neural_hive_tickets esta vazia. Iterar todas as DBs (descoberta automatica)
# garante que o backup captura sla_management, code_forge e neural_hive_tickets
# sem depender de uma premissa de "fonte-de-verdade" errada.
if [[ -n "${PG_POD}" ]]; then
  # Descoberta das DBs nao-sistema (se PG_DBS nao foi imposto via env).
  if [[ -z "${PG_DBS}" ]]; then
    PG_DBS="$(kubectl exec -n "${PG_NS}" "${PG_POD}" -- \
      bash -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U '"${PG_USER}"' -d postgres -tA -c "SELECT datname FROM pg_database WHERE datistemplate=false AND datname NOT IN ('"'"'postgres'"'"') ORDER BY datname;"' 2>/dev/null | tr -d '\r' || true)"
  fi
  if [[ -z "${PG_DBS//[[:space:]]/}" ]]; then
    log "  AVISO: nao foi possivel descobrir DBs PostgreSQL; nenhum pg_dump efetuado."
    echo "pg=SEM_DBS" >> "${MANIFEST}"
  else
    for pgdb in ${PG_DBS}; do
      log "pg_dump ${pgdb}..."
      LOCAL="${BACKUP_DIR}/pg-${pgdb}.dump"
      # Formato custom (-Fc) compactado, restauravel com pg_restore.
      if kubectl exec -n "${PG_NS}" "${PG_POD}" -- \
          bash -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U '"${PG_USER}"' -d '"${pgdb}"' -Fc' > "${LOCAL}" 2>/dev/null; then
        SZ="$(du -h "${LOCAL}" 2>/dev/null | cut -f1)"
        log "  -> ${LOCAL} (${SZ})"
        echo "pg:${pgdb}=pg-${pgdb}.dump (${SZ})" >> "${MANIFEST}"
      else
        log "  AVISO: pg_dump de ${pgdb} falhou."
        rm -f "${LOCAL}"
        echo "pg:${pgdb}=FALHOU" >> "${MANIFEST}"
      fi
    done
  fi
else
  log "AVISO: pod PostgreSQL nao encontrado; pg_dump ignorado."
  echo "pg=SEM_POD" >> "${MANIFEST}"
fi

log "Backup concluido. Manifesto: ${MANIFEST}"
echo "${BACKUP_DIR}"
