# Technical Specification

This is the technical specification for the spec detailed in @docs/specs/2026-06-29-gate-j4-migrate-fiavel/spec.md

## Estado actual (âncoras de código)

- **Atribuição da journey:** `services/semantic-translation-engine/src/services/journey_classifier.py:154`
  — sinal estruturado `context.source == "doc-ingestion"` → `J4_MIGRATE` (confiança 0.95). Funciona; a
  journey é gravada no Cognitive Plan e propagada.
- **Roteamento actual (o gap):** `services/orchestrator-dynamic/src/consumers/decision_consumer.py:252`
  — `if journey in ("J2_ORCHESTRATE", "J4_MIGRATE"): return OrchestrationWorkflow`. J4 corre a
  orquestração genérica de J2.
- **`OrchestrationWorkflow` é agnóstica:** `src/workflows/orchestration_workflow.py` não lê `journey`
  nem invoca migração/geração/ingestão.
- **Capacidade MIGRATE (órfã):** `src/workflows/data_migration_workflow.py` (`DataMigrationWorkflow`,
  8 fases: analyze→snapshot→batch→CDC→validate→cleanup) e `src/workflows/cutover_workflow.py`
  (`CutoverWorkflow`) estão **registados** em `src/workers/temporal_worker.py:493`
  (`workflows=[OrchestrationWorkflow, DataMigrationWorkflow, FluxoGWorkflow]`) mas **nenhum
  `start_workflow`/`execute_child_workflow` os inicia** em produção. Activities em
  `src/activities/data_migration.py` (9 activities) e `src/activities/cutover.py`.
- **Capacidade GENERATE (reusável):** `src/capabilities/generate/` — `GenerateCapability.start(
  GenerateRequest) → GenerateHandle`, contrato fail-closed, registry de stacks. Provada E2E pelo
  consumer (gate 3.3).
- **Serviços de capacidade (produção):** `doc-ingestion:8018` (upload/parse/entities) e
  `data-migration:8019` (`POST /api/v1/migrations`, `/start`, `/validate`, `/approve`, `/rollback`,
  `GET /{job_id}` com progress/rows_migrated). Ambos com Helm chart v1.0.0 e `docker-compose-fluxo-h.yml`.

## Technical Requirements

### TR1 — Fluxo composto da jornada J4 (não a OrchestrationWorkflow genérica)
- Introduzir um caminho de execução de jornada para J4 que encadeia, com durabilidade Temporal,
  `INGEST → PLAN(já feito a montante) → GENERATE → EXECUTE(deploy) → MIGRATE → VALIDATE`.
- Opções de desenho (a decidir na Fase 1, preferir a de menor diff): (a) um `MigrateJourneyWorkflow`
  novo (análogo ao `FluxoGWorkflow`), ou (b) reuso do `FluxoGWorkflow` para a porção GENERATE+EXECUTE
  seguido do `DataMigrationWorkflow` como child workflow. O routing por journey decide o caminho —
  **não** se reusa a `OrchestrationWorkflow` de J2 para J4.
- A decisão "J4 requer fluxo de migração" deriva da **semântica da journey** (`_journey_requires_*`),
  espelhando o padrão `_requires_generate_capability` (autoridade única partilhada consumer↔resume).

### TR2 — Des-orfanizar MIGRATE
- A jornada inicia o `DataMigrationWorkflow` (child workflow ou start dedicado), passando o
  `migration spec` derivado do plano: `legacy_db_url`, `modern_db_url`, lista de tabelas.
- Recolher o resultado (`rows_migrated`, `status`, `current_phase`) para o gate de validação.
- Preservar a saga/rollback existente (`/rollback`, `execute_rollback`) em caso de falha.

### TR3 — Reuso de GENERATE (condicional)
- A fase GENERATE invoca `GenerateCapability.start(GenerateRequest(...))` com o `target` derivado do
  plano (stack do serviço moderno). O deploy do serviço gerado precede a migração de dados.
- GENERATE é **condicional**: planos de migração que não exijam código novo saltam a fase (a journey
  marca-o). A composição não reimplementa G1–G8.

### TR4 — Gate de validação anti-verde-falso (FAIL-CLOSED)
- Após MIGRATE, chamar `POST /api/v1/migrations/{job_id}/validate` (data-migration:8019) e exigir
  resultado positivo explícito (contagem de linhas origem == destino + checks de integridade).
- Fail-closed: validação reprovada, divergência de contagem, ou `/validate` indisponível/erro →
  resultado da jornada `FAILED` com `failure_reason`. Sem fallback que assuma sucesso.
- Espelhar a doutrina do gate J3 (`map_result` exige `verified is True`) e de `caminho-real-first-class`.

### TR5 — Harness de prova E2E (fixture reprodutível)
- DB **legacy** PostgreSQL de fixture com dados conhecidos (N linhas em ≥1 tabela) e DB **moderno**
  vazio, em namespace de teste (efémero, TTL/ResourceQuota — reusar o padrão de deploy do gate J3).
- A prova: intenção J4 → migração executada → `rows_migrated == N` e `/validate` OK → serviço moderno
  gerado a correr (`/health` 200, se GENERATE aplicável).
- Método de injeção idêntico ao gate 3.3 (plan direto/decisão no topic `plans.consensus`, produtor
  dentro do pod; Kafka interno plaintext).

### TR6 — Zero regressão e disciplina
- `J2_ORCHESTRATE` permanece a usar `OrchestrationWorkflow` inalterada; teste congelado de routing J2
  mantém-se verde.
- TDD estrito; diffs mínimos compat **py3.10**; cada fase é um gate (só avança com testes verdes).
- Anti-verde-falso provado por mutação (desligar o gate `/validate` ou o fail-closed derruba ≥1 teste).

## Integration Points (reuso, sem novos serviços)

- `data-migration:8019` — `POST /migrations`, `/migrations/{id}/start`, `/migrations/{id}/validate`,
  `/migrations/{id}` (status), `/migrations/{id}/rollback`.
- `doc-ingestion:8018` — entrada INGEST (mínimo necessário para alimentar o plano de teste).
- `src/capabilities/generate/` — `GenerateCapability` (reuso).
- Temporal worker `orchestration-tasks` — `DataMigrationWorkflow` já registado.

## External Dependencies (Conditional)

Nenhuma dependência nova. A spec compõe serviços, workflows e capacidades **já existentes** no
repositório; o trabalho é de wiring/fronteira e prova E2E, não de novas bibliotecas.
