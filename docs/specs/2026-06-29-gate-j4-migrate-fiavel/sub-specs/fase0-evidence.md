# Fase 0 — Evidência (Diagnóstico + harness de prova reprodutível)

> Gate "J4/MIGRATE fiável" — Task 1. Esta fase **DEFINE e testa em bloco** o
> baseline, o fixture de destino e o harness de injeção. A **EXECUÇÃO real** do
> fixture (correr docker-compose / migração / cluster) é da **Fase 4** — aqui
> nada toca em Docker nem em Kafka real.

## 1. Baseline do gap (confirmado pela sonda 2026-06-29)

- **Routing vazado:** `services/orchestrator-dynamic/src/consumers/decision_consumer.py:252`
  — `if journey in ("J2_ORCHESTRATE", "J4_MIGRATE"): return OrchestrationWorkflow`.
  `J4_MIGRATE` corre a **mesma** `OrchestrationWorkflow` genérica de `J2`, que é
  agnóstica à journey e **não invoca** INGEST, GENERATE nem MIGRATE.
- **`DataMigrationWorkflow` órfão:** registado no worker
  (`src/workers/temporal_worker.py` — `workflows=[OrchestrationWorkflow,
  DataMigrationWorkflow, FluxoGWorkflow]`) mas **nenhum** `start_workflow` /
  `execute_child_workflow` o inicia em produção. Idem `CutoverWorkflow`.
- **Sonda de runtime (2026-06-29):** injetar `journey=J4_MIGRATE` faz correr a
  orquestração genérica e falhar na validação comum, **sem tocar em qualquer
  capacidade de migração**. A jornada J4 do ADR-0011 existe como *label*, não
  como fluxo executável.
- **Prova em bloco do baseline (sem cluster):** o teste
  `tests/integration/test_j4_migrate_fixture_harness.py::TestJ4BaselineRoutingGap`
  assere a **classe real**: `_select_workflow_class_by_journey("J4_MIGRATE") is
  OrchestrationWorkflow`. Reusa (não duplica) a função já testada com mocks em
  `tests/consumers/test_decision_consumer_journey_routing.py:74`.

## 2. Estado do fixture

- **Legacy (origem) — JÁ EXISTIA:** `docker-compose-fluxo-h.yml` traz
  `postgres-legacy` (postgres:17-alpine) com seed `scripts/init-legacy-db.sql`
  (4 tabelas `users/orders/products/order_items` + INSERTs de dados conhecidos).
- **Modern (destino) — ADICIONADO (o gap):** novo serviço `postgres-modern`
  (postgres:17-alpine, `DB modern_db`, `modern_user/modern_pass`, volume
  `postgres-modern-data`, healthcheck `pg_isready`, rede `fluxo-h-net`, porta host
  `5433`). Novo DDL `scripts/init-modern-db.sql` com as **4 tabelas alvo SEM
  INSERTs** (destino arranca VAZIO; a migração popula). Validação só sintáctica
  (`yaml.safe_load` OK; 0 INSERTs; 4 CREATE TABLE) — sem correr Docker.

## 3. Oráculo de contagens (validação futura — Fases 2/4)

Módulo `services/orchestrator-dynamic/tests/integration/j4_migrate_fixture.py`:

- **Constantes-oráculo** (`EXPECTED_LEGACY_COUNTS`, referência explícita a
  `scripts/init-legacy-db.sql`):

  | tabela        | linhas conhecidas |
  |---------------|-------------------|
  | `users`       | 5                 |
  | `orders`      | 5                 |
  | `products`    | 5                 |
  | `order_items` | 9                 |

- **Parser determinístico** (`parse_legacy_seed_counts`) conta os tuplos
  `(...)` de cada `INSERT ... VALUES` do seed real e **bate** com as constantes
  (anti-drift; testado por `test_parse_matches_known_constants`). Serve de oráculo
  da validação pós-migração: destino migrado deve ter `rows == N` por tabela.

## 4. Harness de injeção J4 (espelha o método do gate 3.3)

No mesmo módulo:

- **Função PURA** `build_j4_migrate_plan_message(...)` constrói a mensagem de
  **plano direto** `J4_MIGRATE` para o topic `plans.consensus`: `plan_id`,
  `journey="J4_MIGRATE"`, `context.source="doc-ingestion"`, `tasks`,
  `execution_order`, `risk_band`, `migration_config{legacy_connection_id,
  modern_connection_id, schema, tables}`. **Sem `decision_id`** → o consumer
  trata-o como `is_direct_plan` (`tasks` presente + `decision_id` ausente).
- **Round-trip provado:** `serialize_plan_message` → `_deserialize_avro_or_json`
  (o desserializador real do consumer aceita JSON puro) preserva `journey` e
  `migration_config` (`test_message_roundtrips_through_consumer_deserializer`).
- **Produção real separada e opcional:** `produce_j4_migrate_plan(...)` (Kafka)
  é uma função à parte, **não exercitada em unit** (`# pragma: no cover`), para a
  Fase 4 (produtor in-pod, Kafka interno plaintext :9092).

## 5. O que fica para a Fase 1 (e seguintes)

- **Fase 1 — des-vazar routing + des-orfanizar MIGRATE:** introduzir autoridade
  de routing por semântica da journey (espelhar `_requires_generate_capability`)
  para J4 deixar de cair na `OrchestrationWorkflow` genérica e **iniciar** o
  `DataMigrationWorkflow` com o migration spec derivado do plano. `J2` permanece
  inalterada (teste congelado verde).
- **Fase 2 — gate `/validate` fail-closed** (usando o oráculo de contagens).
- **Fase 3 — reuso condicional de `GenerateCapability`.**
- **Fase 4 — EXECUÇÃO real:** correr `docker-compose-fluxo-h.yml` (legacy+modern),
  produzir o plano via `produce_j4_migrate_plan` in-pod, e provar `rows_migrated
  == N` + `/validate` OK no cluster.

## 6. Resultado dos testes (Fase 0)

```
tests/integration/test_j4_migrate_fixture_harness.py  18 passed
tests/consumers/test_decision_consumer_journey_routing.py  13 passed (congelado, zero regressão)
```
