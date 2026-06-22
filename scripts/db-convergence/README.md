# scripts/db-convergence — Fase 0 (convergencia-dbs)

Deliverables da **Fase 0** da spec `docs/specs/2026-06-21-convergencia-dbs/`:
preparacao risco-zero (backup verificavel + inventario + identificacao de
registos degenerados). **Nao reaponta servicos. Nao apaga dados.** Todas as
operacoes Mongo/PostgreSQL correm via `kubectl exec` dentro dos pods (a maquina
local so tem `kubectl` e `jq`).

## Ordem de execucao

| # | Script | O que faz | Toca runtime? |
|---|--------|-----------|---------------|
| 1 | `00-inventory.sh` | Lista colecoes + contagens (Mongo) e tabelas + `COUNT(*)` exato (PostgreSQL: TODAS as DBs nao-sistema) + alvo de migracao por colecao. Gera `../../docs/specs/2026-06-21-convergencia-dbs/sub-specs/inventory.md`. | Nao (read-only) |
| 2 | `01-backup.sh` | `mongodump` das 4 DBs Mongo + `pg_dump` de TODAS as DBs PostgreSQL nao-sistema (cobre `sla_management`, onde residem os tickets reais) para `./.db-backups/<UTC-timestamp>/`. Idempotente (timestamp por execucao). | Nao (read-only sobre as DBs) |
| 3 | `02-restore-test.sh [backup-dir]` | Prova que o backup e restauravel (gate Fase 0): namespace efemero + Mongo minimo (`mongorestore` de `neural_hive_dev`) **e** PostgreSQL minimo (`pg_restore` de `sla_management`, 935 tickets reais); compara contagens com a origem read-only em ambos; veredicto combinado exige Mongo **e** PG verdes; limpa o namespace. Falha honesta se um pod nao agendar. | Apenas namespace efemero isolado |
| 4 | `03-identify-degenerate.js` | mongosh read-only que **identifica** (nao apaga) registos degenerados em `cognitive_ledger@neural_hive`. | Nao (read-only) |

Sequencia tipica: `00` → `01` → `02` → `03`.

### Correr o identificador de degenerados (passo 4)

```bash
POD=$(kubectl get pod -n mongodb-cluster -l app=mongodb -o jsonpath='{.items[0].metadata.name}')
kubectl cp scripts/db-convergence/03-identify-degenerate.js \
  mongodb-cluster/$POD:/tmp/03-identify-degenerate.js -c mongodb
kubectl exec -n mongodb-cluster $POD -c mongodb -- mongosh --quiet \
  -u root -p "$MONGO_PASSWORD" --authenticationDatabase admin \
  neural_hive --file /tmp/03-identify-degenerate.js
```

## Variaveis de ambiente

Nenhum segredo de produção e hardcoded. A password do Mongo e lida da env var
`MONGO_PASSWORD` ou, em fallback, do secret `mongodb-cluster/mongodb`
(chave `mongodb-root-password`). A password do PostgreSQL de **origem** e lida de
dentro do pod (`$POSTGRES_PASSWORD`), nunca passada pela linha de comando.

Excecao consciente: o restore-test (`02`) cria um PostgreSQL **efemero,
isolado e descartavel** num namespace proprio, cuja password (`restoretest`) e
um valor throwaway local a esse pod — nao e um segredo de producao e o pod e
apagado pelo trap de cleanup ao fim de minutos.

| Var | Default | Usada por |
|-----|---------|-----------|
| `MONGO_NS` | `mongodb-cluster` | todos |
| `MONGO_POD` | auto (`-l app=mongodb`) | todos |
| `MONGO_CONTAINER` | `mongodb` | todos |
| `MONGO_USER` | `root` | todos |
| `MONGO_PASSWORD` | secret `mongodb-cluster/mongodb` | todos |
| `PG_NS` | `neural-hive-data` | `00`, `01` |
| `PG_POD` | auto (`app=postgres-sla`) | `00`, `01` |
| `PG_USER` | `sla_user` | `00`, `01` |
| `PG_DBS` | auto (todas as DBs nao-sistema) | `00`, `01` |
| `BACKUP_ROOT` | `<repo>/.db-backups` | `01`, `02` |
| `RESTORE_DB` | `neural_hive_dev` | `02` (DB Mongo a testar) |
| `PG_RESTORE_DB` | `sla_management` | `02` (DB PG a testar) |
| `PG_VERIFY_TABLE` | `execution_tickets` | `02` (tabela-chave comparada) |
| `PG_IMAGE` | `postgres:15-alpine` | `02` |
| `SCHED_TIMEOUT` | `120` (s) | `02` |
| `MONGO_IMAGE` | `mongo:7.0` | `02` |

## Notas

- Os dumps de `.db-backups/` sao binarios grandes e estao no `.gitignore` — **nao** sao commitados.
- O contexto kubectl esperado e `neural-hive-prod`.
- Nenhuma DB PostgreSQL converge para Mongo: todas entram so no backup. Os tickets reais residem em `sla_management.execution_tickets`; `neural_hive_tickets` esta vazia.
