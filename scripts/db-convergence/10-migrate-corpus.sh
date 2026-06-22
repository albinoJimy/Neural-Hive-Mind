#!/bin/bash
# 10-migrate-corpus.sh — Fase 1 da convergencia-dbs
#
# Wrapper do 10-migrate-corpus.js: migracao ADITIVA, IDEMPOTENTE e NAO-DESTRUTIVA
# do corpus de treino valido neural_hive -> neural_hive_dev (copia, nao move).
# Corre o mongosh DENTRO do pod MongoDB (kubectl exec), seguindo o padrao da
# Fase 0 (00..03). Nenhum segredo hardcoded: a password vem da env var
# MONGO_PASSWORD ou, em fallback, do secret mongodb-cluster/mongodb.
#
# GATE DE SEGURANCA: por omissao corre em DRY-RUN (zero escrita). Para escrever
# de facto e obrigatorio passar APPLY=true explicitamente:
#
#   ./10-migrate-corpus.sh            # DRY-RUN (so reporta o que faria)
#   APPLY=true ./10-migrate-corpus.sh # ESCREVE no alvo (indices + copia)
#
# Idempotencia: re-executar com APPLY=true e seguro (insere 0; a copia ja existe).
#
# Env vars:
#   MONGO_NS / MONGO_POD / MONGO_CONTAINER / MONGO_USER / MONGO_PASSWORD (como na Fase 0)
#   APPLY  (default false)            -> true escreve; qualquer outro valor = dry-run
#   SRC_DB (default neural_hive)
#   DST_DB (default neural_hive_dev)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MONGO_NS="${MONGO_NS:-mongodb-cluster}"
MONGO_CONTAINER="${MONGO_CONTAINER:-mongodb}"
MONGO_USER="${MONGO_USER:-root}"
MONGO_POD="${MONGO_POD:-}"
SRC_DB="${SRC_DB:-neural_hive}"
DST_DB="${DST_DB:-neural_hive_dev}"
# Normaliza APPLY para o booleano JS (so "true" escreve).
APPLY_RAW="${APPLY:-false}"
if [[ "${APPLY_RAW}" == "true" ]]; then APPLY_JS="true"; else APPLY_JS="false"; fi

# Sanitiza nomes de DB antes de os interpolar no --eval do mongosh (evita
# injecao de JS via env var; nomes de DB Mongo so usam estes caracteres).
for v in SRC_DB DST_DB; do
  if [[ ! "${!v}" =~ ^[A-Za-z0-9_]+$ ]]; then
    echo "[migrate] ERRO: ${v}='${!v}' invalido (esperado ^[A-Za-z0-9_]+$)." >&2
    exit 1
  fi
done

log() { echo "[migrate] $*" >&2; }

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

if [[ "${APPLY_JS}" == "true" ]]; then
  log "MODO: APPLY (vai ESCREVER em ${DST_DB})"
else
  log "MODO: DRY-RUN (zero escrita; defina APPLY=true para aplicar)"
fi
log "Pod MongoDB: ${MONGO_NS}/${MONGO_POD}; ${SRC_DB} -> ${DST_DB}"

# ---- Copiar o .js para o pod e correr ----
REMOTE_JS="/tmp/10-migrate-corpus.js"
kubectl cp "${SCRIPT_DIR}/10-migrate-corpus.js" \
  "${MONGO_NS}/${MONGO_POD}:${REMOTE_JS}" -c "${MONGO_CONTAINER}" >/dev/null

EVAL="globalThis.APPLY=${APPLY_JS}; globalThis.SRC_DB='${SRC_DB}'; globalThis.DST_DB='${DST_DB}'; load('${REMOTE_JS}');"

OUT="$(kubectl exec -n "${MONGO_NS}" "${MONGO_POD}" -c "${MONGO_CONTAINER}" -- \
  mongosh --quiet \
    --username "${MONGO_USER}" --password "${MONGO_PASSWORD}" --authenticationDatabase admin \
    --eval "${EVAL}" 2>&1)"

echo "${OUT}"

# Limpeza do ficheiro temporario no pod (best-effort).
kubectl exec -n "${MONGO_NS}" "${MONGO_POD}" -c "${MONGO_CONTAINER}" -- rm -f "${REMOTE_JS}" 2>/dev/null || true

# ---- Veredicto fail-fast ----
if echo "${OUT}" | grep -q "MIGRATION_VERDICT=OK"; then
  log "Veredicto: OK"
  exit 0
elif echo "${OUT}" | grep -q "MIGRATION_VERDICT=FAIL"; then
  log "Veredicto: FAIL (copia incompleta / erro de escrita / erro de indice)"
  exit 1
else
  log "ERRO: veredicto ausente na saida do mongosh (falha de execucao)."
  exit 2
fi
