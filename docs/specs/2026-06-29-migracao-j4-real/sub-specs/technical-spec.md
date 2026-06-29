# Technical Specification

This is the technical specification for the spec detailed in @docs/specs/2026-06-29-migracao-j4-real/spec.md

## Estado actual (âncoras de código + evidência da Fase 4)

Ver `docs/specs/2026-06-29-gate-j4-migrate-fiavel/sub-specs/fase4-evidence.md` para a prova de runtime e
os 4 bugs. Resumo:

- **Composição PROVADA em runtime**: `decision_consumer` → `MigrateJourneyWorkflow` →
  child `DataMigrationWorkflow` (`{wid}-migrate`). Não é preciso re-arquitetar a jornada.
- **Bug #1 (determinismo) CORRIGIDO** (commit `375129e6`): activities movidas para
  `imports_passed_through` no topo de `src/workflows/data_migration_workflow.py`. **Falta validar runtime.**
- **Activities simuladas** em `services/orchestrator-dynamic/src/activities/data_migration.py`:
  `analyze_legacy_schema` (`# Simular análise`), `run_batch_migration` (`rows_migrated = total_rows
  # Simular 100%`). Só `validate_data` é real (thin-wrapper httpx → `/validate`, Fase 2 do gate).
- **Serviço `data-migration:8019`** (fonte de verdade, já deployado): `batch_migrator.py`
  (`run_batch_migration`, `_migrate_table`), `data_validator.py` (`validate_row_counts` com
  `SELECT COUNT(*)`), endpoints `POST /api/v1/migrations` (`MigrationCreateRequest`:
  `legacy_db_url`, `modern_db_url`, `tables`, `batch_size`, `auto_approve`),
  `/migrations/{job_id}/start|validate|rollback`, `GET /migrations/{job_id}`.
- **Bug #2**: `POST /api/v1/migrations` falha com `syntax error at or near "$1"` na análise de schema
  (`services/data-migration/src/services/schema_mapper.py` ou introspeção via asyncpg — query com `$1`
  num contexto que o não aceita; possível uso de placeholder para identificador/DDL).
- **Bug #3**: `scripts/init-legacy-db.sql` começa com comentários `#` (inválidos em SQL) +
  `CREATE EXTENSION "pgoutput"` (não instalável).
- **Padrão thin-wrapper a replicar**: `validate_data` + `set_data_migration_dependencies(http_client,
  base_url)` (data_migration.py) — fail-closed em todos os ramos de erro.

## Technical Requirements

### TR1 — Activity de criação de job (resolve a desconexão job_id)
- Nova activity (ou início de `analyze`) `create_migration_job(migration_config) -> job_id`: chama
  `POST /api/v1/migrations` com `legacy_db_url`/`modern_db_url`/`tables`/`auto_approve=true`; devolve o
  `job_id` REAL do serviço. Fail-closed (erro/timeout/não-2xx → FAILED).
- O `DataMigrationWorkflow` passa a usar ESTE `job_id` (substitui o `self._job_id` gerado localmente) em
  todas as fases seguintes.

### TR2 — `analyze`/`batch` thin-wrappers reais
- `analyze_legacy_schema` → opcional (o serviço já analisa no `POST /migrations`); se mantida, lê o
  estado via `GET /migrations/{job_id}`. Remover a simulação.
- `run_batch_migration` → `POST /migrations/{job_id}/start` (aciona o `batch_migrator` real do serviço);
  fazer poll de `GET /migrations/{job_id}` até `rows_migrated`/fase terminal. **Remover** o
  `rows_migrated = total_rows # Simular 100%`. Fail-closed.
- `validate_data` → já real (Fase 2 do gate); confirmar que opera sobre o `job_id` do serviço.

### TR3 — Contrato do plano J4: db_urls
- O `migration_config` passa a carregar `legacy_db_url`/`modern_db_url` (ou um resolvedor
  `connection_id → db_url`). Atualizar `_extract_migration_config` (decision_consumer) e o harness
  `build_j4_migrate_plan_message` (Fase 0 do gate) em conformidade. Manter o fail-closed
  (`InvalidMigrationConfigError` se faltarem).

### TR4 — Corrigir o serviço `data-migration` (bug #2)
- Diagnosticar e corrigir a `syntax error at or near "$1"` na análise/mapeamento de schema (provável
  parametrização inválida de identificador/DDL via asyncpg — usar interpolação validada de identificador
  como em `data_validator.validate_sql_identifier`, não placeholder `$1`). TDD no serviço.
- Corrigir quaisquer outros bugs expostos pelo primeiro fluxo real (start/batch/poll).

### TR5 — Corrigir o seed (#3) e validar #1 (runtime)
- `scripts/init-legacy-db.sql`: `#`→`--`; remover/ajustar `CREATE EXTENSION "pgoutput"`. Atualizar o
  oráculo de contagens da Fase 0 do gate se necessário (mantém 24 linhas).
- Validar em runtime (rebuild+deploy do orchestrator) que o `DataMigrationWorkflow` corre sem o erro de
  determinismo (#1 corrigido).

### TR6 — Gates E2E (negativo + positivo) e anti-verde-falso
- **Negativo**: forçar destino vazio/divergência → `/validate` real reporta `overall_passed=False` →
  `DataMigrationWorkflow` faz rollback → `FAILED`. Observar em cluster.
- **Positivo**: migração íntegra → `rows_migrated == N` (=24) + `/validate` OK → `completed`.
- Anti-verde-falso por mutação onde aplicável; sem ramos que assumam sucesso.

### TR7 — Disciplina
- TDD; testes de bloco com httpx mockado para as activities (como a Fase 2); diffs mínimos compat
  **py3.10**; zero regressão nos testes congelados do gate (journey/generate/migrate routing,
  migrate_journey). Reduzir requests do orchestrator só para o teste; restaurar depois.

## Integration Points (reuso)

- `data-migration:8019` — `POST /migrations`, `/migrations/{id}/start|validate|rollback`,
  `GET /migrations/{id}`.
- `src/activities/data_migration.py` — `set_data_migration_dependencies` (httpx injetado, já existe).
- `src/workflows/{data_migration_workflow,migrate_journey_workflow}.py` — composição já provada.
- DBs fixture: manifests em `scratchpad/j4-fixture-dbs.yaml` (legacy seedado + modern vazio).

## External Dependencies (Conditional)

Nenhuma nova. Compõe e corrige serviços/workflows existentes.
