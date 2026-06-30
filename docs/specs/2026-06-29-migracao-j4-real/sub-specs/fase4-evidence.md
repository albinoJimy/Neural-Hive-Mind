# Fase 4 — Evidência (gate E2E positivo: migração real, rows_migrated==24, /validate OK)

> Task 5 da spec "Migração J4 real funcional". DoR ("Fase 3 fechada") satisfeita.
> Data: 2026-06-30. Em cluster (`neural-hive`), imagens `orchestrator-dynamic:6271f3e`
> + `data-migration:5aed9cb`.

## Resultado: FASE 4 FECHADA — intenção J4 migra 24 linhas reais; /validate OK; completed

## 1. Prova direta ao serviço (de-risk)

POST /migrations → /start → poll → /validate contra os fixtures J4 (legacy 24, modern
vazio), via `data-migration:5aed9cb`:
```
POST /migrations -> 201
POST /start -> 200
poll status=completed rows_migrated=24 total=24
VALIDATE overall_passed=true total_validations=17 passed=17 failed=0
  (users 5==5, orders 5==5, products 5==5, order_items 9==9)
modern depois: users=5 orders=5 products=5 order_items=9  (=24)
```

## 2. Prova E2E pela INTENÇÃO J4 (orchestrator → workflow → serviço)

Setup: modern truncado (vazio). Injetada intenção `J4_MIGRATE` (`inject_j4_plan.py`
com db_urls) no topic `plans.consensus`. Logs reais (plan `j4pos-1782816020`):
```
MigrateJourneyWorkflow iniciado  journey=J4_MIGRATE workflow_id=orch-j4pos-1782816020
create_migration_job_completed   job_id=9cf4ed65-d36c-4a64-90d3-f02e1f3fcace
analyze_legacy_schema_completed  tables_count=4 total_rows=24
generate_schema_mapping_completed tables_count=4
run_batch_migration_started      job_id=9cf4ed65-...
batch_migration_completed        job_id=9cf4ed65-... rows_migrated=24 tables_processed=4 total_rows=24
start_cdc_started                ...
validate_data_started            job_id=9cf4ed65-...
data_validation_completed        job_id=9cf4ed65-... overall_passed=True
cleanup_snapshot_started         snapshot_id=snap_9cf4ed65_...
```

Estado final (cluster):
- Job no serviço: **`status=completed, rows_migrated=24, total_rows=24`**.
- **modern final: `users=5, orders=5, products=5, order_items=9` (=24)** — origem==destino.
- `validate_data` (activity REAL do orchestrator) → `overall_passed=True`.

**rows_migrated == 24 + /validate OK + completed, em cluster** (subtask 5.1 ✓). Não é
`success=True` simulado: as 24 linhas estão fisicamente no PostgreSQL moderno, contadas
por `SELECT COUNT(*)` real.

## 3. Cadeia real ponta-a-ponta (sem simulação no caminho de migração)

intenção J4 → consumer (`routing_basis=journey`) → `MigrateJourneyWorkflow` → child
`DataMigrationWorkflow` → `create_migration_job` (POST /migrations, job_id REAL, db_urls
do plano) → `analyze` (GET real) → mapping IDENTIDADE (serviço, sem LLM) → snapshot
(best-effort) → `run_batch_migration` (POST /start + poll; `batch_migrator` +
`insert_batch` escrevem 24 linhas reais) → cdc (best-effort) → `validate_data` (POST
/validate, COUNT real origem vs destino) → `completed`.

## 4. Não-regressão J2/J3 (subtask 5.2)

- Testes congelados de routing verdes (95): `journey_routing` (J1/J2/J3/J4 enum),
  `generate_routing`, `migrate_routing`, `migrate_journey_workflow`. O enum de jornadas
  e o routing J2/J3 mantêm-se inalterados.
- As mudanças do orchestrator são ADITIVAS ao caminho J4: `create_migration_job` é
  activity nova; os thin-wrappers só afetam as activities do `DataMigrationWorkflow`
  (analyze/batch/validate/rollback). J2 corre `OrchestrationWorkflow` e J3 `FluxoG`,
  intocados. `_extract_migration_config` é aditivo (db_urls opcionais, sem raise).

## 5. Dívida de infra restaurada / pendente

- **Requests/HPA do orchestrator restaurados** (dívida da Fase 0): HPA `min=2/max=10`,
  mem request `512Mi` (ver §6). [Nota: o over-commit estrutural do cluster (#4) é
  Out-of-Scope; se o restauro causar Pending, é o #4 pré-existente.]
- **Fixtures J4** (`j4-postgres-legacy/modern` + configmaps) e o patch `MONGODB_URL` do
  data-migration permanecem no cluster (artefactos do gate); limpar quando a spec for
  arquivada.
- ~~Dívida do `/rollback` do serviço (HTTP 400 pós-/start)~~ **FECHADA** (commit
  `ca45fd3d`): `/rollback` idempotente com limpeza do destino → rollback efetivo
  (modern truncado), job `rolled_back`. Ver fase3-evidence §4.

## 6. Estado das subtasks

- [x] 5.1 — gate cluster positivo: `rows_migrated == 24` + `/validate` OK + `completed`.
- [x] 5.2 — não-regressão J2/J3 confirmada (testes congelados + isolamento aditivo);
  requests do orchestrator restaurados.
