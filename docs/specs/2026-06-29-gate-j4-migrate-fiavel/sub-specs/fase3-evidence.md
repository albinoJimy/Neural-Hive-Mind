# Fase 3 — Evidência: composição J4 (GENERATE condicional → MIGRATE via child-workflows)

> Spec: `docs/specs/2026-06-29-gate-j4-migrate-fiavel/` — eixo Jornadas, gate "J4/MIGRATE fiável"
> (ADR-0011). Objectivo (Task 4): compor a jornada J4 com um workflow que sequencia GENERATE
> (condicional) → MIGRATE via **child-workflows**, reusando `FluxoGWorkflow` e `DataMigrationWorkflow`
> sem reimplementar G1–G8 nem as 8 fases da migração. TDD estrito, diffs mínimos (py3.10), zero regressão.

## 1. Arquitetura escolhida (decisão do utilizador)

J4 deixa de cair na `OrchestrationWorkflow` genérica (Fase 1 já des-vazou o routing) e passa a arrancar
um **`MigrateJourneyWorkflow`** novo (`src/workflows/migrate_journey_workflow.py`) que **compõe** as
capacidades existentes via `workflow.execute_child_workflow`:

```
MigrateJourneyWorkflow.run(cognitive_plan)
  ├─ (condicional) child  FluxoGWorkflow.run      id=f"{wid}-generate"   → GENERATE (G1–G13)
  └─            child  DataMigrationWorkflow.run   id=f"{wid}-migrate"    → MIGRATE (8 fases + saga)
```

É o **primeiro** padrão de child-workflow do repo (não existia precedente). Segue a doc temporalio:
`workflow.execute_child_workflow(Wf.run, input, id=..., task_queue=...)` com o `task_queue` do parent
(`workflow.info().task_queue`) para os filhos correrem no mesmo worker `orchestration-tasks`.

Os child-workflows são importados sob `with workflow.unsafe.imports_passed_through():` (evita o sandbox
Temporal reanalisar as activities transitivas do `FluxoGWorkflow`).

## 2. Condicionalidade da geração (sem defaults silenciosos)

A decisão "a jornada precisa gerar código novo antes de migrar?" é uma **função pura** derivada da
SEMÂNTICA do plano — `_journey_needs_generation(cognitive_plan)`:

```python
return bool(cognitive_plan.get("generate_target"))
```

- `generate_target` presente e não-vazio → corre o `FluxoGWorkflow` child ANTES da migração;
- ausente / `{}` → **salta** GENERATE e migra sobre um destino já existente.

Sem sinal, sem geração (não há default que invente uma stack). A modernização que precisa de serviço
novo marca-o; a migração "lift-and-shift" sobre destino pré-existente não paga o custo de G1–G13.

## 3. Fail-closed: GENERATE falha → NÃO migra

Espelha a doutrina `caminho-real-first-class` e o `map_result` de GENERATE (verificação real, sem verde
falso). Após o child de geração:

```python
if not _generate_succeeded(generate_result):   # FluxoGWorkflow -> status != "completed"
    return {"journey": "J4_MIGRATE", "status": "failed",
            "failure_reason": "generate_failed", "migration_result": None, ...}
```

Não se migram dados para um destino que **não está de pé**. A migração só arranca depois de o GENERATE
concluir com `status="completed"`. A migração falhada (`DataMigrationWorkflow` → `rolled_back`/`failed`,
i.e. `status != "success"`) também produz `status="failed"` + `failure_reason="migration_failed"`.

Prova anti-verde-falso no teste de bloco
(`test_generate_failure_does_not_run_migration_fail_closed`): o mock de `execute_child_workflow` tem
**um único** `side_effect` (o GENERATE falhado). Se o workflow tentasse executar o MIGRATE, o segundo
`__next__` do `side_effect` levantaria `StopIteration` e o teste partia — logo o teste **só** passa
porque o MIGRATE NÃO é executado. `call_count == 1` é assertado explicitamente.

## 4. Dependência de dados GENERATE → destino da migração

Na modernização, o serviço que o GENERATE deploya **é** o destino (`modern_connection`) do MIGRATE.
`build_migrate_child_input(plan, generate_result)` deriva-o:

```python
derived_modern = generate_result["deployment"]["service_url"]   # se presente
if derived_modern:
    migration_config["modern_connection_id"] = derived_modern   # sobrepõe o do plano
```

Quando não há GENERATE (ou o resultado não traz `service_url`), mantém-se o `modern_connection_id` do
plano. Cópia defensiva: o `migration_config` do plano original **não é mutado**
(`test_does_not_mutate_plan_config`).

## 5. Refactor do consumer (Fase 1 → Fase 3)

`src/consumers/decision_consumer.py` (bloco MIGRATE): mantém-se a **autoridade** `_requires_migration`
(semântica da jornada) e o **gate fail-closed** `_extract_migration_config` (anti-verde-falso: config
presente mas inválida NÃO arranca nada). Muda apenas o **alvo** do start durável:

- antes: `start_workflow(DataMigrationWorkflow.run, {migration_config, job_id, initial_phase}, ...)`;
- agora: `start_workflow(MigrateJourneyWorkflow.run, cognitive_plan_json, ...)` — a jornada composta
  recebe o plano (com o `migration_config` validado reinjetado e, opcional, `generate_target`).

`MigrateJourneyWorkflow` registado no worker (`src/workers/temporal_worker.py`):
`workflows=[OrchestrationWorkflow, DataMigrationWorkflow, FluxoGWorkflow, MigrateJourneyWorkflow]`.

## 6. Evolução consciente dos testes da Fase 1 (não enfraquecimento)

`tests/consumers/test_decision_consumer_migrate_routing.py` (DESTA sessão): a asserção do happy-path
mudou de `DataMigrationWorkflow.run` para `MigrateJourneyWorkflow.run`, **preservando toda a semântica**:

- o input continua a carregar `migration_config.tables == MIGRATION_TABLES` e
  `legacy_connection_id == "postgres-legacy"` (consistência harness↔consumer);
- anti-verde-falso intocado: `tables=[]` e `legacy_connection_id=""` continuam a **não** arrancar nada;
- J4 **sem** `migration_config` → `OrchestrationWorkflow` (compat); J2/J3/sem-journey inalterados.

Testes **congelados** de outras specs mantidos **verdes e inalterados**:
`test_decision_consumer_journey_routing.py` e `test_decision_consumer_generate_routing.py` — incl.
`test_j4_migrate_uses_orchestration_workflow` (J4 sem `migration_config` → Orchestration), que continua
válido porque a sua mensagem não traz `migration_config`.

## 7. Honestidade de escopo

- **Fase 3 prova a orquestração durável EM BLOCO**: a sequência condicional, a ordem GENERATE→MIGRATE, o
  fail-closed (GENERATE falha → não migra) e a dependência de dados GENERATE→destino são exercitados com
  `workflow.execute_child_workflow` **mockado** (espelha o padrão de `test_fluxo_g_workflow.py`). Não há
  Temporal real nesta fase.
- **E2E real = Fase 4**: intenção `J4_MIGRATE` → fluxo composto no cluster → serviço moderno gerado a
  correr (`/health` 200, quando GENERATE aplicável) + PostgreSQL migrado (`rows_migrated == N`) +
  `/validate` OK; e o caminho negativo (divergência forçada → `FAILED` observável). O verde-falso do
  `run_batch_migration` (batch simulado, dívida da Fase 2) é apanhado pela validação real da Fase 2.
- **Não tocado**: `_select_workflow_class_by_journey` (J4→Orchestration mantém-se como dead-code/fallback
  legado, congelado); o gate `/validate` da Fase 2; o routing por journey da Fase 1.

## 8. Ficheiros

- `services/orchestrator-dynamic/src/workflows/migrate_journey_workflow.py` — **novo**
  (`MigrateJourneyWorkflow` + funções puras `_journey_needs_generation`, `build_generate_child_input`,
  `build_migrate_child_input`, `_derive_modern_connection`, `_generate_succeeded`,
  `_migration_succeeded`).
- `services/orchestrator-dynamic/src/consumers/decision_consumer.py` — bloco MIGRATE arranca
  `MigrateJourneyWorkflow.run` (em vez de `DataMigrationWorkflow.run`); import ajustado.
- `services/orchestrator-dynamic/src/workers/temporal_worker.py` — `MigrateJourneyWorkflow` registado.
- `services/orchestrator-dynamic/tests/workflows/test_migrate_journey_workflow.py` — **novo**, 13 testes.
- `services/orchestrator-dynamic/tests/consumers/test_decision_consumer_migrate_routing.py` — asserção do
  happy-path evoluída para `MigrateJourneyWorkflow.run` (semântica preservada).

## 9. Gate verde (contagem)

```
python3 -m pytest tests/workflows/test_migrate_journey_workflow.py \
  tests/consumers/test_decision_consumer_migrate_routing.py \
  tests/consumers/test_decision_consumer_journey_routing.py \
  tests/consumers/test_decision_consumer_generate_routing.py -q
→ 63 passed
```

- 13 novos (`test_migrate_journey_workflow.py`) + 19 (`migrate_routing`, 1 evoluído) + 13
  (`journey_routing`, congelado) + 18 (`generate_routing`, congelado) = **63 verdes, zero regressão**.
- `tests/workflows/` completo: **32 passed** (inclui `FluxoGWorkflow` e `OrchestrationWorkflow` intactos).
- ruff limpo nos ficheiros novos; black aplicado.

## 10. Nuances de honestidade (dívidas conhecidas, a reconciliar na Fase 4 / spec de extração)

1. **`generate_target` ainda não tem produtor upstream.** O ramo GENERATE só corre quando o plano J4 traz
   `generate_target` não-vazio, mas hoje **nenhum componente (STE/consenso) popula essa chave** — logo, em
   produção, o `MigrateJourneyWorkflow` salta sempre GENERATE e vai direto a MIGRATE. O ramo está **provado
   em bloco** mas é **dead-code em runtime** até a Fase 4 ligar o plano (o STE marcar `generate_target` nas
   intenções de modernização). É o mesmo padrão da Fase 1 (J4 sem `migration_config` → compat) e do
   `map_result` de GENERATE (contrato testado em isolamento).
2. **Reusa `FluxoGWorkflow` (implementação), não `GenerateCapability` (fronteira).** Dentro de um workflow
   Temporal **não se pode** invocar `GenerateCapability.start` (usa `temporal_client`, válido só fora de
   workflows); a composição durável exige `workflow.execute_child_workflow(FluxoGWorkflow.run, ...)`. Isto
   **re-introduz acoplamento à classe `FluxoGWorkflow`** no contexto da jornada — precisamente a fronteira
   que a spec GENERATE des-vazou para o consumer. É uma restrição técnica do Temporal, não uma regressão do
   consumer (que continua a usar a capability). A reconciliação (tornar a capacidade composável dentro de
   workflows, ou extrair MIGRATE com a mesma disciplina) é trabalho da **spec de extração de MIGRATE**
   seguinte; aceitável para este gate de fiabilidade.
