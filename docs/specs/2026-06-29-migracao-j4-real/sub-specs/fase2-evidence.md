# Fase 2 — Evidência (activities thin-wrappers; job_id real; db_urls no contrato)

> Task 3 da spec "Migração J4 real funcional". Pipeline: dev → auditoria qualidade
> (SHIP) → auditoria completude (COMPLETO) → remediação dirigida → commit. Data:
> 2026-06-30. DoR ("Fase 1 fechada") satisfeita. Gate da fase = **bloco verde + zero
> regressão** (o E2E em cluster é Fases 3/4).

## Resultado: FASE 2 FECHADA — activities reais sobre o serviço, job_id real propagado, db_urls no contrato; 20+95 testes verdes

## 1. Activities thin-wrappers reais (sem simulação)

`services/orchestrator-dynamic/src/activities/data_migration.py`:
- **NOVA `create_migration_job(migration_config) -> {success, job_id}`** — `POST
  /api/v1/migrations` (`MigrationCreateRequest`: legacy_db_url/modern_db_url/tables/
  batch_size/auto_approve=True) → devolve o **job_id REAL do serviço**. Fail-closed
  (espelha `validate_data`): sem `_http_client`, db_urls em falta/vazias, non-2xx,
  erro/timeout, JSON inválido, 2xx sem job_id → `success=False`. **É aqui o ponto de
  fail-closed das db_urls.**
- **`run_batch_migration` real** — `POST /migrations/{job_id}/start` + **poll** de
  `GET /migrations/{job_id}` até estado terminal (`completed`/`cdc_running`/`validating`
  → ok; `failed`/`rolled_back` → `success=False`), com contagens **reais** do serviço.
  **Removido `rows_migrated = total_rows # Simular 100%`.** `asyncio.sleep` no poll vive
  na ACTIVITY (determinismo Temporal preservado). Esgotar a janela de poll → fail-closed.
- **`analyze_legacy_schema` thin-wrapper de leitura** — `GET /migrations/{job_id}`;
  constrói `schema_analysis` mínima (tables do config + `total_rows` REAL do serviço),
  SHAPE preservada para `generate_schema_mapping`. Sem colunas hardcoded, sem `# Simular`.
- `validate_data` — inalterada (já real na Fase 2 do gate); opera sobre o mesmo job_id.

## 2. Propagação do job_id real

`src/workflows/data_migration_workflow.py`:
- No início de `run()`: se `self._job_id` for None → `execute_activity(create_migration_job,
  [config_data])`; `not success` → `_build_error_result`; senão `self._job_id =
  result["job_id"]`. `create_migration_job` importada em `imports_passed_through`.
- Todas as fases (analyze/mapping/snapshot/batch/cdc/validate/rollback) operam sobre
  `self._job_id` — o **uuid local desapareceu do caminho**. `create_migration_job`
  registada no worker (`src/workers/temporal_worker.py`) → sem `ActivityNotRegistered`.

## 3. db_urls no contrato (aditivo — constrangimento dos testes congelados)

- `src/consumers/decision_consumer.py` `_extract_migration_config`: carrega
  `legacy_db_url`/`modern_db_url` se presentes (ausente → `None`), **sem levantar erro**.
  **Decisão de desenho:** o fail-closed das db_urls NÃO foi colocado aqui (como a letra
  de TR3 sugeria via `InvalidMigrationConfigError`) porque o teste congelado
  `test_decision_consumer_migrate_routing.py::test_valid_migration_config` aceita um
  config só com `legacy_connection_id`+`tables` e exige SUCESSO. O fail-closed vive em
  `create_migration_job` (o ponto que realmente precisa das db_urls). Zero regressão.
- `tests/integration/j4_migrate_fixture.py` `build_j4_migrate_plan_message`: ganha
  kwargs `legacy_db_url`/`modern_db_url` com defaults (DNS dos fixtures); incluídas no
  `migration_config`. Os 18 testes congelados do harness (asserem campos específicos,
  não igualdade exata nem ausência de db_urls) continuam verdes.

## 4. Endpoints reais usados

`POST /api/v1/migrations`, `POST /api/v1/migrations/{id}/start`,
`GET /api/v1/migrations/{id}`, `POST /api/v1/migrations/{id}/validate`. Estados terminais
batem com o enum `MigrationStatus` do serviço.

## 5. Testes (subtasks 3.1 + 3.3)

`tests/activities/test_data_migration_thin_wrappers.py` (novo, httpx mockado, 20 testes):
- `create_migration_job` (7): 201→job_id; sem client; legacy/modern db_url em
  falta/vazia; non-2xx; erro de rede; 2xx sem job_id.
- `run_batch_migration` (7): start+poll running→completed com contagens reais; terminal
  `failed`→success=False; sem client; start non-2xx (sem poll); erro de poll;
  **JSON inválido no poll → fail-closed** (remediação); **timeout do poll → fail-closed**
  (remediação, `_BATCH_POLL_MAX_ATTEMPTS` monkeypatch=3, esgota exatamente 3 GETs).
- `analyze_legacy_schema` (4): GET→SHAPE+total_rows real; sem client; non-2xx;
  **JSON inválido → fail-closed** (remediação).
- `_extract_migration_config` (2): db_urls presentes carregadas; ausentes→None sem raise.

**Gate 3.3 (bloco verde + zero regressão nos congelados):**
```
tests/activities/test_data_migration_thin_wrappers.py        20 passed (17 + 3 remediação)
congelados (journey/generate/migrate routing + harness 18 + migrate_journey
  + validate_data)                                            95 passed
```
ruff/black -l 100 limpos. py3.10. Testes existentes NÃO modificados (só o helper
`j4_migrate_fixture.py` e ADIÇÃO do teste novo).

## 6. Dívidas que transitam para Fase 3/4 (anti-verde-falso a vigiar)

- **`execute_rollback` ainda simulado** — crítico para o **gate negativo da Fase 3**
  (rollback observável). A resolver na Fase 3.
- **`start_cdc`/`create_snapshot`/`cleanup_snapshot` simulados** — `start_cdc` simulado
  pode dar verde-falso no caminho positivo da Fase 4; avaliar.
- **`analyze` devolve `columns: []`** — confirmar no E2E (Fase 4) que o `batch_migrator`
  do serviço não depende de mapping enriquecido de colunas.
- **`batch_migrator` do serviço usa métodos inexistentes** (`insert_batch`/`insert_many`/
  `execute` no `PostgreSQLClient`) → bloqueia a escrita real (Fase 1 já sinalizou).
- **MongoDB wiring durável** do data-migration (Fase 1: patch de env em runtime).
- **Infra orchestrator (#4):** requests/HPA da Fase 0 — restaurar na Fase 4.
