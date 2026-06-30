# Fase 0 — Evidência (Pré-condições: seed #3, determinismo #1 em runtime, harness E2E)

> Task 1 da spec "Migração J4 real funcional". Pipeline: dev → auditoria qualidade
> (SHIP) → auditoria completude (COMPLETO) → validação runtime em cluster → commit.
> Data: 2026-06-30. Imagem provada: `orchestrator-dynamic:f5c4da0` (HEAD inclui o
> fix #1 do commit `375129e6`).

## Resultado: FASE 0 FECHADA — #3 corrigido e provado em postgres real; #1 validado em runtime; harness reprodutível

Os três itens do DoD da Task 1 estão cumpridos e provados por evidência real (não
`success=True`): seed aplica num PostgreSQL real, `DataMigrationWorkflow` corre sem o
erro de determinismo e a composição chega à 1ª activity, harness deployável a partir
do scratchpad.

## 1. Bug #3 — seed `scripts/init-legacy-db.sql` corrigido (repo) e provado em PostgreSQL real

Correção cirúrgica (diff `+5/-4`, INSERTs/DDL/índices/`DO $$` intactos):
- Linhas 4-5: comentários estilo shell `#` → `--` (inválidos em SQL).
- Linha 8: `CREATE EXTENSION IF NOT EXISTS "pgoutput";` removido — `pgoutput` é o
  output plugin de logical decoding **embutido** no PostgreSQL, NÃO uma extensão
  instalável via `CREATE EXTENSION`; substituído por comentário explicativo.

**Prova anti-verde-falso (mutação, em postgres real):** com o seed ORIGINAL, `psql -v
ON_ERROR_STOP=1 -f` → `exit=3`, `ERROR: syntax error at or near "#"`. Com o seed
CORRIGIDO → `exit=0`, **4 tabelas** (`users/orders/products/order_items`),
contagens `users=5 orders=5 products=5 order_items=9`, **total=24**.

Teste novo: `services/orchestrator-dynamic/tests/integration/test_legacy_seed_real_postgres.py`
- `test_legacy_seed_applies_on_real_postgres` (docker-gated, skip limpo sem docker):
  arranca `postgres:17-alpine` efémero, aplica o seed com `ON_ERROR_STOP=1`, assere as
  4 tabelas + contagens == oráculo + soma 24. Lê o caminho de
  `j4_migrate_fixture.LEGACY_SEED_PATH` (reuso, sem hardcode). **PASSED** (docker
  disponível; correu de facto).
- `TestLegacySeedOracleStable` (sempre): `parse_legacy_seed_counts() ==
  EXPECTED_LEGACY_COUNTS` e soma 24. **PASSED**.

**Oráculo inalterado:** `EXPECTED_LEGACY_COUNTS = {users:5, orders:5, products:5,
order_items:9}` (soma 24); `j4_migrate_fixture.py` não foi tocado.

**Zero regressão nos testes congelados do gate:** `test_j4_migrate_fixture_harness.py`
(18) + `test_decision_consumer_journey_routing.py` (13) = **31 passed**.

## 2. Bug #1 (determinismo Temporal) — VALIDADO em runtime

- Imagem deployada antes: `bdce0f3` (anterior ao fix `375129e6`). Rebuild via
  `build-and-push-ghcr.yml` (workflow_dispatch, `services=orchestrator-dynamic`) →
  imagem `f5c4da0` (HEAD `f5c4da06`, que inclui #1). Auto-deploy do pipeline.
- Por over-commit do cluster (#4), o novo RS não agendava: requests de memória do
  orchestrator reduzidos `512Mi→256Mi` e HPA pinado (temporariamente `1/1`) para o
  rollout convergir. **Dívida a restaurar na Fase 4** (originais: HPA `min=2 max=10`,
  mem request `512Mi`). Após libertar memória, todos os pods passaram a `f5c4da0`
  (zero `bdce0f3` no task-queue → prova determinística, sem worker antigo a competir).

**Injeção J4** (plano direto, harness): `inject_j4_plan.py` produz no topic
`plans.consensus` via aiokafka (PLAINTEXT :9092) de dentro do pod. Plano
`fase0j4-1782807193` (offset 241). Logs reais (pod `f5c4da0`):

```
Plan direto do STE detectado (sem decision_id) plan_id=fase0j4-1782807193 tasks_count=1
Invocando capacidade MIGRATE  journey=J4_MIGRATE routing_basis=journey tables=[...] workflow_id=orch-fase0j4-1782807193
MigrateJourneyWorkflow iniciado  journey=J4_MIGRATE plan_id=fase0j4-1782807193
analyze_legacy_schema_started  legacy_connection_id=postgres-legacy schema=public tables=[...]
analyze_legacy_schema_completed tables_count=2
```

- **`analyze_legacy_schema_started` = a composição CHEGA À 1ª ACTIVITY do child
  `DataMigrationWorkflow`** (exatamente o que o DoD pede).
- **Zero erros de determinismo** no run inteiro: `grep -c "Cannot access
  os.environ|os.environ.get from inside|NonDeterministic"` = **0**. #1 corrigido.
- Routing por capacidade (`routing_basis=journey` → MIGRATE), não a
  `OrchestrationWorkflow` genérica.

## 3. Baseline pós-#1 (subtask 1.3) — até onde o fluxo chega antes do #2

Com #1 resolvido, a composição corre determinística por:
1. `analyze_legacy_schema` ✓ (started+completed; **ainda simulada** — torná-la
   thin-wrapper real é a Fase 2 / TR2).
2. `generate_schema_mapping` ✓ (started+completed, simulada).
3. `create_snapshot` ✗ — **falha honesta** em `src/activities/data_migration.py:380`:
   `snapshot_id = f"snap_{job_id[:8]}_..."` com `job_id=None` (`None[:8]` → erro). O
   workflow **NÃO reivindica `completed`** (anti-verde-falso confirmado).

**Observação-chave:** o fluxo **ainda não chega ao bug #2** (análise de schema do
serviço `data-migration`, `syntax error at or near "$1"` no `POST /migrations`),
porque nada cria ainda um job real no serviço — `_job_id` é `None` localmente. A
criação do job (`create_migration_job` → `POST /migrations`, onde vive o #2) é
precisamente o trabalho da **Fase 2 (TR1)**; a propagação do `job_id` real do serviço
elimina este `job_id=None` e leva o fluxo até ao #2. Ordem dos blocos confirmada:
**#1 (resolvido) → `job_id=None` em `create_snapshot` (fronteira Fase 2) → #2 (serviço,
Fase 1) → migração real (Fases 3/4)**.

## 4. Harness E2E reprodutível (DoD)

A partir do scratchpad da sessão (`.../scratchpad/`):
- `j4-fixture-dbs.yaml` — Deployments/Services `j4-postgres-legacy` (seedado) e
  `j4-postgres-modern` (vazio), `postgres:17-alpine`.
- `deploy-j4-fixtures.sh` — cria os ConfigMaps a partir de `scripts/init-{legacy,modern}-db.sql`
  do repo, aplica os manifests e verifica contagens. Idempotente.
- `inject_j4_plan.py` — produtor aiokafka do plano direto J4 (espelha
  `build_j4_migrate_plan_message`).

**Verificado em cluster:** legacy `users=5 orders=5 products=5 order_items=9` (**24**),
modern `0/0/0/0` (destino vazio). O seed corrigido aplica-se também no postgres do
cluster (prova adicional à do teste local).

## 5. Estado das subtasks

- [x] 1.1 — seed corrigido parseia num PostgreSQL real (4 tabelas, 24 linhas); oráculo inalterado.
- [x] 1.2 — `init-legacy-db.sql` corrigido; fixture recriado; rebuild+deploy orchestrator (`f5c4da0`); #1 provado em runtime.
- [x] 1.3 — baseline pós-#1 documentado (chega à 1ª activity; falha honesta em `create_snapshot` por `job_id=None`; #2 só após Fase 2).

## 6. Dívida que transita (a tratar nas fases seguintes)

- **Infra (#4):** requests do orchestrator reduzidos (`512Mi→256Mi`) e HPA pinado
  (`1/1`) para o teste — **restaurar na Fase 4** (originais HPA `2/10`, mem `512Mi`).
- **Fixtures J4** (`j4-postgres-legacy/modern` + configmaps) permanecem no cluster para
  as fases seguintes; limpar no fim da spec.
