# Fase 1 — Evidência (des-vazar routing J4 + des-orfanizar DataMigrationWorkflow)

> Task 2 do gate "J4/MIGRATE fiável". Pipeline dev(TDD) → auditoria(qualidade SHIP + completude SHIP)
> → remediação. Commit: ver histórico (`feat(j4-migrate): Fase 1 ...`).

## O que foi feito

Espelhou-se **exatamente o padrão GENERATE** em `services/orchestrator-dynamic/src/consumers/decision_consumer.py`:

- `_journey_requires_migration(journey)` → True só para `J4_MIGRATE` (semântica pura, análogo a
  `_journey_requires_generation`).
- `_requires_migration(journey, workflow_type)` → autoridade única (análogo a
  `_requires_generate_capability`); guard plan-only (J1 nunca executa). Sem fallback por
  `workflow_type` (não existe "migration" legado por workflow_type).
- `_extract_migration_config(plan)` + `InvalidMigrationConfigError` → **fail-closed**: exige
  `legacy_connection_id` (str não-vazia) e `tables` (lista com ≥1 entrada não-vazia); `schema` default
  "public"; `modern_connection_id` opcional. Sem defaults silenciosos. Reusa o formato do harness da
  Fase 0 (`build_j4_migrate_plan_message`).
- **Bloco de routing** inserido APÓS o bloco GENERATE e ANTES do bloco genérico de orquestração: para
  J4 com `migration_config`, constrói o input dedicado do workflow
  (`{migration_config, job_id: None, initial_phase: "pending"}`) e faz
  `await self.temporal_client.start_workflow(DataMigrationWorkflow.run, ...)` — **des-orfanizando** o
  `DataMigrationWorkflow` (antes registado no worker mas sem chamador). `routing_basis="journey"`,
  `capability="MIGRATE"`. commit + return.
- **NÃO se tocou** `_select_workflow_class_by_journey` (J4→OrchestrationWorkflow fica dead-code,
  exatamente como J3→FluxoGWorkflow após a extração de GENERATE) → o teste congelado
  `tests/consumers/test_decision_consumer_journey_routing.py:74` mantém-se verde.

## Anti-verde-falso (provado por mutação)

- `migration_config` **presente mas inválido** (`legacy_connection_id` vazio ou `tables` vazias) →
  `InvalidMigrationConfigError` → o handler faz commit+return e **NÃO cai na OrchestrationWorkflow
  genérica** (uma tentativa REAL de migração malformada nunca "passa" via orquestração). Mutação
  confirmada pela auditoria: remover qualquer `raise` em `_extract_migration_config`, ou o try/except,
  derruba ≥1 teste (`test_empty_tables_raises`, `test_missing_legacy_connection_id_raises`,
  `test_j4_migrate_invalid_config_does_not_start_migration`).

## Nuance de desenho (decisão consciente + risco conhecido)

A condição de interceção é `_requires_migration(...) and "migration_config" in cognitive_plan_json`.
Isto distingue dois casos de J4:

| Caso | Comportamento | Razão |
|---|---|---|
| J4 **com** `migration_config` válido | → `DataMigrationWorkflow` (capacidade MIGRATE) | caminho real |
| J4 com `migration_config` **presente mas inválido** | → `FAILED` (commit+return, sem orquestração) | anti-verde-falso |
| J4 **sem** a chave `migration_config` | → compat (OrchestrationWorkflow genérica) | preserva o teste `test_j4_migrate_uses_orchestration_workflow` (escrito na Fase 2 do GENERATE), regra 7 |

**Risco conhecido (a reavaliar em fase futura):** um plano J4 que *deveria* migrar mas perdeu o
`migration_config` por bug upstream (STE) cai silenciosamente no compat e falha de forma confusa
(validação genérica `risk_score`), em vez de um erro explícito "J4 requer migration_config". Aceitável
agora porque (a) o harness/STE real sempre inclui `migration_config`, e (b) preserva o contrato de teste
existente. Quando o **resume** for wired e a composição completa estabilizada, o caso "J4 sem
`migration_config`" deve passar a erro explícito (e o teste legado revisitado).

## Resume pós-aprovação — diferido (honestidade)

Ao contrário de GENERATE (que partilha a autoridade entre o consumer e o resume HTTP de `main.py`), o
**resume NÃO foi wired para MIGRATE** nesta fase. O docstring de `_requires_migration` foi corrigido
(remediação Q1) para **não afirmar** paridade inexistente com o resume. Um plano J4 aprovado via resume
→ MIGRATE é escopo de fase posterior (a Fase 1 cobre o ramo do consumer Kafka, análogo à Fase 2 do
GENERATE).

## Testes

- **71 verdes** no comando obrigatório: `test_decision_consumer_migrate_routing.py` (19 novos) +
  `test_decision_consumer_journey_routing.py` (13, congelado verde) + `test_decision_consumer_generate_routing.py`
  (18) + `test_decision_consumer_plan_only_guard.py` (3) + `test_j4_migrate_fixture_harness.py` (18).
- **Zero regressão GENERATE** (gate 3.3): suíte `tests/unit/capabilities/` + `test_workflow_start_generate_capability.py`
  = 48 verdes.
- Cobertura: semântica/autoridade/extractor; J4+config → `DataMigrationWorkflow.run` com o config certo
  (não-tautológico); J2 → OrchestrationWorkflow; J3 → GenerateCapability; sem-journey → fallback;
  consistência harness↔consumer.

## Honestidade de escopo

A Fase 1 prova o **routing/wiring em bloco** (mock do `temporal_client`). A execução real do
`DataMigrationWorkflow` em cluster (migração de dados, `rows_migrated == N`, `/validate`) é a **Fase 4**.
