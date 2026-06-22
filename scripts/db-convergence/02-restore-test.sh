#!/bin/bash
# 02-restore-test.sh — Fase 0 da convergencia-dbs
#
# PROVA que o backup (Mongo + PostgreSQL) e restauravel (gate da Fase 0):
#   1. Cria um namespace efemero isolado.
#   2. Sobe um MongoDB minimo (requests baixos; labels Gatekeeper
#      app.kubernetes.io/name; sem auth, isolado e descartavel).
#   3. mongorestore de UMA DB (neural_hive_dev, a mais pequena) a partir
#      do dump produzido por 01-backup.sh.
#   4. Compara as contagens por colecao do alvo restaurado com a ORIGEM
#      (pod Mongo de producao, read-only).
#   5. Sobe um PostgreSQL minimo, pg_restore de UMA DB com dados reais
#      (sla_management, 935 tickets) e compara a contagem de uma tabela-chave
#      com a ORIGEM (read-only). A DoD da Fase 0 exige provar Mongo *e* PG.
#   6. LIMPA sempre o namespace efemero (trap/cleanup).
#
# O veredicto final exige AMBAS as provas (Mongo + PostgreSQL) verdes. O ramo
# PostgreSQL e ignorado apenas se o backup nao contiver o dump PG correspondente
# (e nesse caso o facto e registado explicitamente, nao silenciado).
#
# Falha HONESTA: timeout apertado no agendamento; se o pod nao agendar por
# falta de recursos (cluster sob pressao de memoria), regista o motivo e
# falha explicitamente. NUNCA fica pendurado nem reporta falso sucesso.
#
# ACOPLAMENTO TEMPORAL (importante): a comparacao e feita contra a ORIGEM VIVA
# no momento do teste, nao contra um snapshot congelado. Se a DB de origem
# receber escritas entre o 01-backup.sh e este teste (ex.: um E2E a correr),
# o restaurado (estado do dump) divergira da origem (estado atual) e o teste
# falhara — correctamente, mas por drift temporal, nao por backup corrupto.
# Regra pratica: correr o 02 LOGO APOS o 01, sem pipeline a escrever entremeio.
#
# Uso:
#   ./02-restore-test.sh <backup-dir>        # diretorio gerado por 01-backup.sh
#   (se omitido, usa o backup mais recente em ./.db-backups/)
#
# Env vars:
#   MONGO_NS / MONGO_POD / MONGO_CONTAINER / MONGO_USER / MONGO_PASSWORD  (origem)
#   RESTORE_DB        (default: neural_hive_dev — a DB Mongo a restaurar/testar)
#   EPHEMERAL_NS      (default: dbconv-restoretest-<ts>)
#   MONGO_IMAGE       (default: mongo:7.0)
#   SCHED_TIMEOUT     (default: 120  — segundos para o pod ficar Ready)
#   PG_NS / PG_POD / PG_USER              (origem PostgreSQL, para comparacao)
#   PG_RESTORE_DB     (default: sla_management — a DB PG com dados reais a testar)
#   PG_VERIFY_TABLE   (default: execution_tickets — tabela-chave para comparar)
#   PG_IMAGE          (default: postgres:15-alpine — alinhado com a origem 15.x)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

MONGO_NS="${MONGO_NS:-mongodb-cluster}"
MONGO_CONTAINER="${MONGO_CONTAINER:-mongodb}"
MONGO_USER="${MONGO_USER:-root}"
MONGO_POD="${MONGO_POD:-}"
RESTORE_DB="${RESTORE_DB:-neural_hive_dev}"
MONGO_IMAGE="${MONGO_IMAGE:-mongo:7.0}"
SCHED_TIMEOUT="${SCHED_TIMEOUT:-120}"

# ---- Configuracao PostgreSQL (origem + restore-test) ----
PG_NS="${PG_NS:-neural-hive-data}"
PG_POD="${PG_POD:-}"
PG_USER="${PG_USER:-sla_user}"
PG_RESTORE_DB="${PG_RESTORE_DB:-sla_management}"
PG_VERIFY_TABLE="${PG_VERIFY_TABLE:-execution_tickets}"
PG_IMAGE="${PG_IMAGE:-postgres:15-alpine}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
# Nome de namespace tem de ser um RFC 1123 label (so minusculas/digitos/'-').
# O timestamp UTC tem 'T'/'Z' maiusculos => normalizar para minusculas.
NS_TS="$(printf '%s' "${TS}" | tr '[:upper:]' '[:lower:]')"
EPHEMERAL_NS="${EPHEMERAL_NS:-dbconv-restoretest-${NS_TS}}"

log()  { echo "[restore-test] $*" >&2; }
fail() { echo "[restore-test] FALHA: $*" >&2; exit 1; }

# ---- Resolver backup-dir ----
BACKUP_DIR="${1:-}"
if [[ -z "${BACKUP_DIR}" ]]; then
  BACKUP_DIR="$(ls -1dt "${REPO_ROOT}/.db-backups"/*/ 2>/dev/null | head -1 || true)"
  BACKUP_DIR="${BACKUP_DIR%/}"
fi
[[ -n "${BACKUP_DIR}" && -d "${BACKUP_DIR}" ]] || fail "diretorio de backup invalido: '${BACKUP_DIR}' (passe-o como argumento ou corra 01-backup.sh primeiro)."
DUMP_FILE="${BACKUP_DIR}/mongo-${RESTORE_DB}.archive.gz"
[[ -f "${DUMP_FILE}" ]] || fail "dump da DB ${RESTORE_DB} nao encontrado em ${DUMP_FILE}."
log "Backup: ${BACKUP_DIR}"
log "Dump a testar: ${DUMP_FILE}"

# ---- Resolver origem para comparacao ----
if [[ -z "${MONGO_POD}" ]]; then
  MONGO_POD="$(kubectl get pod -n "${MONGO_NS}" -l app=mongodb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
fi
[[ -n "${MONGO_POD}" ]] || fail "pod MongoDB de origem nao encontrado em ${MONGO_NS}."
if [[ -z "${MONGO_PASSWORD:-}" ]]; then
  MONGO_PASSWORD="$(kubectl get secret -n "${MONGO_NS}" mongodb -o jsonpath='{.data.mongodb-root-password}' 2>/dev/null | base64 -d || true)"
fi
[[ -n "${MONGO_PASSWORD:-}" ]] || fail "MONGO_PASSWORD vazio (origem)."

# ---- Cleanup garantido (trap) ----
CLEANED=0
cleanup() {
  [[ "${CLEANED}" -eq 1 ]] && return
  CLEANED=1
  log "Cleanup: a apagar namespace efemero ${EPHEMERAL_NS}..."
  kubectl delete namespace "${EPHEMERAL_NS}" --wait=false --ignore-not-found >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

# ---- 1. Namespace efemero ----
log "A criar namespace efemero ${EPHEMERAL_NS}..."
kubectl create namespace "${EPHEMERAL_NS}" >/dev/null 2>&1 || fail "nao foi possivel criar o namespace ${EPHEMERAL_NS}."

# ---- 2. Mongo minimo (labels Gatekeeper, requests baixos, sem PVC) ----
RT_POD="restore-test-mongo"
log "A subir MongoDB efemero (${MONGO_IMAGE}, requests baixos)..."
cat <<YAML | kubectl apply -f - >/dev/null 2>&1 || fail "kubectl apply do pod efemero falhou (provavel rejeicao de admission)."
apiVersion: v1
kind: Pod
metadata:
  name: ${RT_POD}
  namespace: ${EPHEMERAL_NS}
  labels:
    app: ${RT_POD}
    app.kubernetes.io/name: ${RT_POD}
    app.kubernetes.io/component: db-convergence-restore-test
spec:
  restartPolicy: Never
  terminationGracePeriodSeconds: 5
  containers:
    - name: mongodb
      image: ${MONGO_IMAGE}
      args: ["--bind_ip_all", "--wiredTigerCacheSizeGB", "0.25"]
      ports:
        - containerPort: 27017
      resources:
        requests:
          cpu: "50m"
          memory: "256Mi"
        limits:
          cpu: "500m"
          memory: "512Mi"
YAML

# ---- 3. Esperar Ready com timeout APERTADO; falha honesta se nao agendar ----
log "A aguardar pod Ready (timeout ${SCHED_TIMEOUT}s)..."
if ! kubectl wait --for=condition=ready pod/"${RT_POD}" -n "${EPHEMERAL_NS}" --timeout="${SCHED_TIMEOUT}s" >/dev/null 2>&1; then
  PHASE="$(kubectl get pod "${RT_POD}" -n "${EPHEMERAL_NS}" -o jsonpath='{.status.phase}' 2>/dev/null || echo '?')"
  REASON="$(kubectl get events -n "${EPHEMERAL_NS}" --field-selector involvedObject.name="${RT_POD}" -o jsonpath='{range .items[*]}{.reason}: {.message}{"\n"}{end}' 2>/dev/null | tail -5)"
  log "Pod nao ficou Ready. Phase=${PHASE}. Eventos recentes:"
  echo "${REASON}" >&2
  fail "MongoDB efemero nao agendou/arrancou em ${SCHED_TIMEOUT}s (cluster sob pressao de recursos?). NAO ha falso sucesso."
fi
log "Pod Ready."

# ---- 4. Restore de UMA DB no pod efemero ----
log "A copiar dump para o pod efemero..."
gunzip -c "${DUMP_FILE}" > "/tmp/rt-${RESTORE_DB}.archive" 2>/dev/null || fail "nao foi possivel descomprimir ${DUMP_FILE} localmente."
kubectl cp "/tmp/rt-${RESTORE_DB}.archive" "${EPHEMERAL_NS}/${RT_POD}:/tmp/restore.archive" >/dev/null 2>&1 || fail "kubectl cp do dump falhou."
rm -f "/tmp/rt-${RESTORE_DB}.archive"

log "mongorestore no pod efemero (DB ${RESTORE_DB})..."
# Pod sem auth: restore direto. Restaura para o mesmo nome de DB.
kubectl exec -n "${EPHEMERAL_NS}" "${RT_POD}" -- \
  mongorestore --archive=/tmp/restore.archive --nsInclude="${RESTORE_DB}.*" >/dev/null 2>&1 \
  || fail "mongorestore falhou no pod efemero."

# ---- 5. Comparar contagens: origem (read-only) vs restaurado ----
# IMPORTANTE: o mongorestore pode NAO recriar coleccoes vazias (count==0). Se
# comparassemos o conjunto exato de nomes de coleccoes, uma coleccao a 0 na
# origem (ex.: neural_hive_dev.plan_approvals, specialist_feedback) que nao e
# recriada no restauro produziria um FALSO NEGATIVO. Por isso filtramos para
# apenas coleccoes com count>0 dos DOIS lados antes de comparar. Coleccoes
# vazias sao irrelevantes para a prova de "backup restauravel".
count_js='const out=[]; db.getCollectionNames().sort().forEach(function(c){ const n=db.getCollection(c).countDocuments({}); if(n>0){ out.push(c+"="+n); } }); print(out.join(","));'

log "A contar colecoes NAO-VAZIAS na ORIGEM (${MONGO_NS}/${MONGO_POD}, read-only)..."
SRC="$(kubectl exec -n "${MONGO_NS}" "${MONGO_POD}" -c "${MONGO_CONTAINER}" -- \
  mongosh --quiet --username "${MONGO_USER}" --password "${MONGO_PASSWORD}" --authenticationDatabase admin \
  "${RESTORE_DB}" --eval "${count_js}" 2>/dev/null || true)"

log "A contar colecoes NAO-VAZIAS no RESTAURADO (pod efemero)..."
DST="$(kubectl exec -n "${EPHEMERAL_NS}" "${RT_POD}" -- \
  mongosh --quiet "${RESTORE_DB}" --eval "${count_js}" 2>/dev/null || true)"

log "Origem    (count>0): ${SRC}"
log "Restaurado (count>0): ${DST}"

if [[ -z "${SRC}" && -z "${DST}" ]]; then
  fail "ambas as contagens (count>0) vazias — restore Mongo nao verificavel (DB de origem sem dados?)."
fi

if [[ "${SRC}" == "${DST}" ]]; then
  log "SUCESSO (Mongo): contagens das coleccoes NAO-VAZIAS IDENTICAS entre origem e restauro."
  log "(Coleccoes vazias sao ignoradas: o mongorestore pode nao as recriar.)"
else
  log "Divergencia Mongo entre origem e restauro (apenas coleccoes nao-vazias):"
  log "  origem     = ${SRC}"
  log "  restaurado = ${DST}"
  fail "contagens de coleccoes nao-vazias divergem — backup Mongo NAO considerado restauravel de forma verificada."
fi

# =====================================================================
# FASE PostgreSQL — pg_restore de uma DB com dados reais (sla_management)
# =====================================================================
# A DoD da Fase 0 exige provar Mongo *e* PostgreSQL. Restauramos a DB com
# dados reais (sla_management.execution_tickets ~935), nao a vazia
# neural_hive_tickets (provaria pouco). Veredicto combinado no fim.
PG_DUMP_FILE="${BACKUP_DIR}/pg-${PG_RESTORE_DB}.dump"
if [[ ! -f "${PG_DUMP_FILE}" ]]; then
  fail "dump PostgreSQL ${PG_RESTORE_DB} nao encontrado em ${PG_DUMP_FILE} — backup incompleto, DoD da Fase 0 (Mongo+PG) nao satisfeita."
fi
log "Dump PostgreSQL a testar: ${PG_DUMP_FILE}"

# ---- Resolver pod PostgreSQL de origem (para a contagem de comparacao) ----
if [[ -z "${PG_POD}" ]]; then
  PG_POD="$(kubectl get pod -n "${PG_NS}" -o jsonpath='{.items[?(@.metadata.labels.app=="postgres-sla")].metadata.name}' 2>/dev/null || true)"
  if [[ -z "${PG_POD}" ]]; then
    PG_POD="$(kubectl get pod -n "${PG_NS}" -o name 2>/dev/null | grep -i postgres | head -1 | sed 's#pod/##' || true)"
  fi
fi
[[ -n "${PG_POD}" ]] || fail "pod PostgreSQL de origem nao encontrado em ${PG_NS} (necessario para comparar contagens)."

# ---- Subir PostgreSQL efemero (mesmo namespace isolado, descartavel) ----
RT_PG_POD="restore-test-postgres"
RT_PG_PASS="restoretest"
log "A subir PostgreSQL efemero (${PG_IMAGE})..."
cat <<YAML | kubectl apply -f - >/dev/null 2>&1 || fail "kubectl apply do pod PostgreSQL efemero falhou (provavel rejeicao de admission)."
apiVersion: v1
kind: Pod
metadata:
  name: ${RT_PG_POD}
  namespace: ${EPHEMERAL_NS}
  labels:
    app: ${RT_PG_POD}
    app.kubernetes.io/name: ${RT_PG_POD}
    app.kubernetes.io/component: db-convergence-restore-test
spec:
  restartPolicy: Never
  terminationGracePeriodSeconds: 5
  containers:
    - name: postgres
      image: ${PG_IMAGE}
      env:
        - name: POSTGRES_PASSWORD
          value: ${RT_PG_PASS}
        - name: PGDATA
          value: /tmp/pgdata
      ports:
        - containerPort: 5432
      resources:
        requests:
          cpu: "50m"
          memory: "128Mi"
        limits:
          cpu: "500m"
          memory: "512Mi"
YAML

log "A aguardar PostgreSQL efemero Ready (timeout ${SCHED_TIMEOUT}s)..."
if ! kubectl wait --for=condition=ready pod/"${RT_PG_POD}" -n "${EPHEMERAL_NS}" --timeout="${SCHED_TIMEOUT}s" >/dev/null 2>&1; then
  PHASE="$(kubectl get pod "${RT_PG_POD}" -n "${EPHEMERAL_NS}" -o jsonpath='{.status.phase}' 2>/dev/null || echo '?')"
  REASON="$(kubectl get events -n "${EPHEMERAL_NS}" --field-selector involvedObject.name="${RT_PG_POD}" -o jsonpath='{range .items[*]}{.reason}: {.message}{"\n"}{end}' 2>/dev/null | tail -5)"
  log "Pod PostgreSQL nao ficou Ready. Phase=${PHASE}. Eventos recentes:"
  echo "${REASON}" >&2
  fail "PostgreSQL efemero nao agendou/arrancou em ${SCHED_TIMEOUT}s. NAO ha falso sucesso."
fi
# Esperar o socket aceitar ligacoes (Ready != aceitar queries imediatamente).
kubectl exec -n "${EPHEMERAL_NS}" "${RT_PG_POD}" -- \
  bash -lc 'for i in $(seq 1 30); do pg_isready -U postgres -h localhost >/dev/null 2>&1 && exit 0; sleep 1; done; exit 1' \
  >/dev/null 2>&1 || fail "PostgreSQL efemero nao aceitou ligacoes a tempo."
log "PostgreSQL efemero Ready."

log "A copiar dump PostgreSQL para o pod efemero..."
kubectl cp "${PG_DUMP_FILE}" "${EPHEMERAL_NS}/${RT_PG_POD}:/tmp/pg-restore.dump" >/dev/null 2>&1 || fail "kubectl cp do dump PostgreSQL falhou."

log "createdb + pg_restore no pod efemero (DB ${PG_RESTORE_DB})..."
kubectl exec -n "${EPHEMERAL_NS}" "${RT_PG_POD}" -- \
  bash -lc 'PGPASSWORD='"${RT_PG_PASS}"' createdb -U postgres '"${PG_RESTORE_DB}"' 2>/dev/null || true' >/dev/null 2>&1 || true
# pg_restore pode emitir warnings de roles/ownership inexistentes (--no-owner
# mitiga); o que valida o restauro e a contagem de linhas comparada abaixo.
kubectl exec -n "${EPHEMERAL_NS}" "${RT_PG_POD}" -- \
  bash -lc 'PGPASSWORD='"${RT_PG_PASS}"' pg_restore --no-owner --no-acl -U postgres -d '"${PG_RESTORE_DB}"' /tmp/pg-restore.dump' >/dev/null 2>&1 || true

log "A contar ${PG_VERIFY_TABLE} na ORIGEM (${PG_NS}/${PG_POD}, read-only)..."
PG_SRC="$(kubectl exec -n "${PG_NS}" "${PG_POD}" -- \
  bash -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U '"${PG_USER}"' -d '"${PG_RESTORE_DB}"' -tA -c "SELECT count(*) FROM '"${PG_VERIFY_TABLE}"';"' 2>/dev/null | tr -dc '0-9' || true)"

log "A contar ${PG_VERIFY_TABLE} no RESTAURADO (pod efemero)..."
PG_DST="$(kubectl exec -n "${EPHEMERAL_NS}" "${RT_PG_POD}" -- \
  bash -lc 'PGPASSWORD='"${RT_PG_PASS}"' psql -U postgres -d '"${PG_RESTORE_DB}"' -tA -c "SELECT count(*) FROM '"${PG_VERIFY_TABLE}"';"' 2>/dev/null | tr -dc '0-9' || true)"

log "Origem PostgreSQL    (${PG_RESTORE_DB}.${PG_VERIFY_TABLE}): ${PG_SRC:-<vazio>}"
log "Restaurado PostgreSQL (${PG_RESTORE_DB}.${PG_VERIFY_TABLE}): ${PG_DST:-<vazio>}"

if [[ -z "${PG_SRC}" || ! "${PG_SRC}" =~ ^[0-9]+$ ]]; then
  fail "contagem de origem PostgreSQL invalida ('${PG_SRC}') — comparacao nao verificavel."
fi
# Guarda simetrica: PG_DST tambem tem de ser numerico. Sem isto, um pg_restore
# falhado (tabela inexistente => contagem vazia) com PG_SRC valido cairia no
# ramo 'else' como divergencia generica; validar explicitamente da uma mensagem
# honesta de "restauro nao produziu a tabela" e fecha qualquer falso-verde.
if [[ -z "${PG_DST}" || ! "${PG_DST}" =~ ^[0-9]+$ ]]; then
  fail "contagem do restaurado PostgreSQL invalida ('${PG_DST}') — pg_restore pode ter falhado ou a tabela ${PG_VERIFY_TABLE} nao existir no restauro."
fi
if [[ "${PG_SRC}" == "${PG_DST}" ]]; then
  log "SUCESSO (PostgreSQL): contagem de ${PG_VERIFY_TABLE} IDENTICA entre origem e restauro (${PG_SRC})."
else
  fail "contagem PostgreSQL diverge (origem=${PG_SRC} restaurado=${PG_DST:-<vazio>}) — backup PG NAO restauravel de forma verificada."
fi

# =====================================================================
# Veredicto combinado (Mongo + PostgreSQL)
# =====================================================================
log "RESTORE-TEST GLOBAL: Mongo (${RESTORE_DB}) OK + PostgreSQL (${PG_RESTORE_DB}) OK."
echo "RESTORE-TEST: OK (mongo:${RESTORE_DB}, pg:${PG_RESTORE_DB})"
