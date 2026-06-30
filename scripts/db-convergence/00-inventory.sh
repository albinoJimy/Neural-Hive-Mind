#!/bin/bash
# 00-inventory.sh — Fase 0 da convergencia-dbs (READ-ONLY)
#
# Levanta o inventario de fonte-de-verdade por colecao:
#   - Para cada DB Mongo neural* (neural_hive, neural_hive_dev,
#     neural_hive_orchestration, neural_hive_workers) lista colecoes
#     e contagem de documentos, via 'kubectl exec' no pod MongoDB.
#   - Conta a DB PostgreSQL neural_hive_tickets (tabelas + linhas),
#     via 'kubectl exec' no pod postgres-sla.
#
# Gera/atualiza docs/specs/2026-06-21-convergencia-dbs/sub-specs/inventory.md.
#
# NAO escreve nada nas DBs. NAO reaponta servicos. NAO apaga dados.
#
# Env vars (todas com default seguro; sem segredos hardcoded):
#   MONGO_NS         (default: mongodb-cluster)
#   MONGO_POD        (default: deteta via label app=mongodb)
#   MONGO_CONTAINER  (default: mongodb)
#   MONGO_USER       (default: root)
#   MONGO_PASSWORD   (default: lido do secret mongodb-cluster/mongodb)
#   PG_NS            (default: neural-hive-data)
#   PG_POD           (default: deteta via label)
#   PG_USER          (default: sla_user)
#   PG_DBS           (default: vazio => descobre todas as DBs nao-sistema)
set -euo pipefail

# ---- Localizar raiz do repo (para o caminho do inventory.md) ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
INVENTORY_MD="${REPO_ROOT}/docs/specs/2026-06-21-convergencia-dbs/sub-specs/inventory.md"

# ---- Configuracao Mongo ----
MONGO_NS="${MONGO_NS:-mongodb-cluster}"
MONGO_CONTAINER="${MONGO_CONTAINER:-mongodb}"
MONGO_USER="${MONGO_USER:-root}"
MONGO_POD="${MONGO_POD:-}"
MONGO_DBS=(neural_hive neural_hive_dev neural_hive_orchestration neural_hive_workers)

# ---- Configuracao PostgreSQL ----
PG_NS="${PG_NS:-neural-hive-data}"
PG_POD="${PG_POD:-}"
PG_USER="${PG_USER:-sla_user}"
# PG_DBS vazio => descoberta automatica de todas as DBs nao-sistema.
PG_DBS="${PG_DBS:-}"

log() { echo "[inventory] $*" >&2; }

# ---- Resolver pod Mongo ----
if [[ -z "${MONGO_POD}" ]]; then
  MONGO_POD="$(kubectl get pod -n "${MONGO_NS}" -l app=mongodb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
fi
if [[ -z "${MONGO_POD}" ]]; then
  log "ERRO: nao foi possivel determinar o pod MongoDB em ${MONGO_NS} (defina MONGO_POD)."
  exit 1
fi
log "Pod MongoDB: ${MONGO_NS}/${MONGO_POD} (container ${MONGO_CONTAINER})"

# ---- Resolver password Mongo (env > secret) ----
if [[ -z "${MONGO_PASSWORD:-}" ]]; then
  MONGO_PASSWORD="$(kubectl get secret -n "${MONGO_NS}" mongodb -o jsonpath='{.data.mongodb-root-password}' 2>/dev/null | base64 -d || true)"
fi
if [[ -z "${MONGO_PASSWORD:-}" ]]; then
  log "ERRO: MONGO_PASSWORD vazio (defina a env var ou garanta acesso ao secret mongodb-cluster/mongodb)."
  exit 1
fi

# ---- Resolver pod PostgreSQL ----
if [[ -z "${PG_POD}" ]]; then
  PG_POD="$(kubectl get pod -n "${PG_NS}" -o jsonpath='{.items[?(@.metadata.labels.app=="postgres-sla")].metadata.name}' 2>/dev/null || true)"
  if [[ -z "${PG_POD}" ]]; then
    PG_POD="$(kubectl get pod -n "${PG_NS}" -o name 2>/dev/null | grep -i postgres | head -1 | sed 's#pod/##' || true)"
  fi
fi
if [[ -z "${PG_POD}" ]]; then
  log "AVISO: pod PostgreSQL nao encontrado em ${PG_NS}; contagens PostgreSQL serao marcadas N/D."
fi

# ---- Helper: corre mongosh com um pipeline JS read-only e devolve JSON ----
mongo_eval() {
  local db="$1" js="$2"
  kubectl exec -n "${MONGO_NS}" "${MONGO_POD}" -c "${MONGO_CONTAINER}" -- \
    mongosh --quiet \
      --username "${MONGO_USER}" --password "${MONGO_PASSWORD}" --authenticationDatabase admin \
      "${db}" --eval "${js}" 2>/dev/null
}

# Acumuladores
TMP_ROWS="$(mktemp)"
trap 'rm -f "${TMP_ROWS}"' EXIT
declare -A DB_TOTALS

# ---- Mapa de migracao coleccao -> alvo (decisao de desenho, nao medicao) ----
# Alinhado com a tabela "Alvo e mapa de migracao de coleccoes" do
# technical-spec.md (linhas 43-52). Estatico porque o alvo e desenho, nao
# uma contagem. Coleccoes nao mapeadas ficam "(avaliar)".
migration_target() {
  case "$1" in
    cognitive_ledger)       echo "manter dev; nao migrar legado degenerado" ;;
    specialist_opinions)    echo "copiar legado valido -> dev (de-dup plan_id+specialist_type+created_at)" ;;
    specialist_feedback)    echo "copiar -> dev" ;;
    plan_approvals)         echo "copiar -> dev + recriar TTL GDPR (m002)" ;;
    plan_features)          echo "copiar -> dev" ;;
    explainability_ledger)  echo "copiar -> dev" ;;
    consensus_decisions)    echo "manter dev" ;;
    execution_tickets_dlq)  echo "vazio -> descartavel" ;;
    execution_tickets)      echo "orchestration: avaliar (tickets-Mongo != tickets-PG)" ;;
    *)                      echo "(avaliar)" ;;
  esac
}

GENERATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

log "A inventariar DBs Mongo..."
for db in "${MONGO_DBS[@]}"; do
  log "  -> ${db}"
  # Para cada colecao devolve "nome\tcount" (estimativa exata via countDocuments)
  JS='const out=[]; db.getCollectionNames().sort().forEach(function(c){ try { out.push(c + "\t" + db.getCollection(c).countDocuments({})); } catch(e) { out.push(c + "\tERR"); } }); print(out.join("\n"));'
  RESULT="$(mongo_eval "${db}" "${JS}" || true)"
  total=0
  if [[ -z "${RESULT}" ]]; then
    # DB sem colecoes ou inacessivel
    printf '%s\t%s\t%s\n' "${db}" "(sem colecoes / inacessivel)" "0" >> "${TMP_ROWS}"
  else
    while IFS=$'\t' read -r coll cnt; do
      [[ -z "${coll}" ]] && continue
      printf '%s\t%s\t%s\n' "${db}" "${coll}" "${cnt}" >> "${TMP_ROWS}"
      if [[ "${cnt}" =~ ^[0-9]+$ ]]; then total=$((total + cnt)); fi
    done <<< "${RESULT}"
  fi
  DB_TOTALS["${db}"]="${total}"
done

# ---- PostgreSQL: TODAS as DBs nao-sistema, com COUNT(*) EXATO ----
# n_live_tup e estimativa do planner (pode ser stale se autoanalyze nao correu);
# por isso contamos com COUNT(*) exato por tabela. Iterar todas as DBs evita
# confirmar um falso "canonico em PG": neural_hive_tickets esta vazia, os
# tickets reais residem em sla_management.execution_tickets.
PG_ROWS=""
PG_TOTAL="N/D"
if [[ -n "${PG_POD}" ]]; then
  # Descobrir DBs nao-sistema (se PG_DBS nao foi imposto via env).
  if [[ -z "${PG_DBS}" ]]; then
    PG_DBS="$(kubectl exec -n "${PG_NS}" "${PG_POD}" -- \
      bash -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U '"${PG_USER}"' -d postgres -tA -c "SELECT datname FROM pg_database WHERE datistemplate=false AND datname NOT IN ('"'"'postgres'"'"') ORDER BY datname;"' 2>/dev/null | tr -d '\r' || true)"
  fi
  pg_total=0
  pg_has=0
  for pgdb in ${PG_DBS}; do
    log "A inventariar PostgreSQL ${pgdb} (COUNT exato)..."
    # Para cada tabela, gera dinamicamente um COUNT(*) exato.
    PG_SQL="SELECT 'SELECT '''||relname||''' AS t, count(*) AS n FROM '||quote_ident(relname) FROM pg_stat_user_tables ORDER BY relname;"
    COUNT_QUERIES="$(kubectl exec -n "${PG_NS}" "${PG_POD}" -- \
      bash -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U '"${PG_USER}"' -d '"${pgdb}"' -tA -c "'"${PG_SQL}"'"' 2>/dev/null | tr -d '\r' || true)"
    while IFS= read -r q; do
      [[ -z "${q}" ]] && continue
      ROW="$(kubectl exec -n "${PG_NS}" "${PG_POD}" -- \
        bash -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U '"${PG_USER}"' -d '"${pgdb}"' -tA -F$'"'"'\t'"'"' -c "'"${q};"'"' 2>/dev/null | tr -d '\r' || true)"
      tbl="$(printf '%s' "${ROW}" | cut -f1)"
      rows="$(printf '%s' "${ROW}" | cut -f2)"
      [[ -z "${tbl}" ]] && continue
      pg_has=1
      PG_ROWS+="| \`${pgdb}\` | \`${tbl}\` | ${rows} |"$'\n'
      if [[ "${rows}" =~ ^[0-9]+$ ]]; then pg_total=$((pg_total + rows)); fi
    done <<< "${COUNT_QUERIES}"
  done
  if [[ "${pg_has}" -eq 1 ]]; then PG_TOTAL="${pg_total}"; fi
fi

# ---- Gerar inventory.md ----
log "A escrever ${INVENTORY_MD}"
mkdir -p "$(dirname "${INVENTORY_MD}")"

{
  echo "# Inventário de fonte-de-verdade por coleção (Fase 0)"
  echo
  echo "> Spec: convergencia-dbs — Fase 0 (preparação risco-zero)"
  echo "> Gerado por: \`scripts/db-convergence/00-inventory.sh\` (read-only)"
  echo "> Data do levantamento (UTC): ${GENERATED_AT}"
  echo "> Contexto kubectl: $(kubectl config current-context 2>/dev/null || echo desconhecido)"
  echo
  echo "Levantamento read-only das DBs MongoDB \`neural*\` e de TODAS as DBs"
  echo "PostgreSQL não-sistema da instância de dados. Contagens via"
  echo "\`countDocuments\` (Mongo) e \`COUNT(*)\` exato (PostgreSQL — não"
  echo "\`n_live_tup\`, que é estimativa do planner e pode estar stale)."
  echo
  echo "## MongoDB — coleção → DB → contagem → alvo de migração"
  echo
  echo "Coluna **Alvo** = decisão de desenho (mapa de migração do"
  echo "\`technical-spec.md\`), não uma medição. DB-alvo dev: \`neural_hive_dev\`."
  echo
  echo "| DB | Coleção | Documentos | Alvo de migração |"
  echo "|---|---|---|---|"
  while IFS=$'\t' read -r db coll cnt; do
    echo "| \`${db}\` | \`${coll}\` | ${cnt} | $(migration_target "${coll}") |"
  done < "${TMP_ROWS}"
  echo
  echo "### Totais por DB Mongo"
  echo
  echo "| DB | Total de documentos |"
  echo "|---|---|"
  for db in "${MONGO_DBS[@]}"; do
    echo "| \`${db}\` | ${DB_TOTALS[${db}]:-0} |"
  done
  echo
  echo "## PostgreSQL — todas as DBs não-sistema (só backup, não convergem para Mongo)"
  echo
  if [[ -n "${PG_ROWS}" ]]; then
    echo "| DB | Tabela | Linhas (COUNT exato) |"
    echo "|---|---|---|"
    printf '%s' "${PG_ROWS}"
    echo
    echo "Total de linhas: ${PG_TOTAL}"
  else
    echo "PostgreSQL não inventariado (pod não encontrado ou inacessível). Total: ${PG_TOTAL}"
  fi
  echo
  echo "## Notas"
  echo
  echo "- Este artefacto é regenerado idempotentemente por \`00-inventory.sh\`; cada execução substitui o conteúdo com o estado atual."
  echo "- **Fonte-de-verdade dos tickets em PostgreSQL:** \`sla_management.execution_tickets\` (dados reais). A DB \`neural_hive_tickets.execution_tickets\` está **genuinamente vazia (0)** — confirmado por \`COUNT(*)\` exato, não estimativa stale. O \`execution-ticket-service\` aponta para \`POSTGRES_DATABASE=sla_management\`."
  echo "- **Discrepância a resolver (Fases 3/6):** tickets-PG (\`sla_management.execution_tickets\`) vs tickets-Mongo (\`neural_hive_orchestration.execution_tickets\`) são conjuntos distintos. O mapeamento de fonte-de-verdade única de tickets fica para as fases de consolidação; o backup da Fase 0 captura **ambos** os lados (todas as DBs PG + todas as DBs Mongo)."
  echo "- Nenhuma DB PostgreSQL converge para Mongo nesta spec — entram apenas no backup (ver \`01-backup.sh\`)."
  echo "- Registos degenerados de \`cognitive_ledger\` em \`neural_hive\` são identificados (sem apagar) por \`03-identify-degenerate.js\`."
} > "${INVENTORY_MD}"

log "Inventário concluído."
echo "${INVENTORY_MD}"
