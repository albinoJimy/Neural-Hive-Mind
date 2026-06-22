# Spec Tasks

> Ordenação alinhada ao princípio do ADR-0011: **Fundação → Roteamento → Capacidades. Nunca o inverso.**
> Fase 0 (Fundação: contrato + sink) → Fase 1 (Adapter EXECUTE) → Fase 2 (Leitor LEARN) → Fase 3 (Anti-regressão + prova de transversalidade). Cada fase é um gate: só avança com testes verdes + evidência registada.
>
> **Regra de ouro:** construir a Fundação transversal primeiro; ligar EXECUTE como adapter depois; nunca deixar uma capacidade ditar o formato da Fundação. Detalhe em `sub-specs/technical-spec.md`.
>
> **Alvo:** coleção `execution_tickets` em `neural_hive_dev` (reutilizada; sem store novo nesta spec).

## Tasks

### Fase 0 — Fundação transversal (contrato + sink; não toca runtime)

- [x] 1. Contrato `ExecutionFeedback` + `FeedbackSink` (plano-Z, capability-agnostic)
  - **DoR:** ADR-0011 aceite como referência; acesso ao modelo `ExecutionTicket` e ao `mongodb_client` do orchestrator.
  - **DoD:** schema Avro + modelo Pydantic criados; `FeedbackSink.record()` idempotente; testes unitários verdes incluindo transversalidade (`capability="GENERATE"` sem alterar o sink) e idempotência (2ª chamada não duplica).
  - **Evidência:** `sub-specs/fase0-evidence.md` (TDD RED→GREEN; 10/10 testes verdes; ruff+black limpos; avsc AVRO-parse OK; falhas de `test_execution_result_consumer` provadas PRÉ-EXISTENTES via stash da base).
  - [x] 1.1 Escrever testes do `FeedbackSink` (`tests/unit/test_feedback_sink.py`, 10 testes: persistência por `ticket_id`; idempotência; `capability="GENERATE"` sem alteração; `ticket_id` ausente não toca Mongo; falha de Mongo não propaga; `completed_at` int millis; `simulated` marcado)
  - [x] 1.2 `schemas/execution-feedback/execution-feedback.avsc` (contrato canónico; `capability`, `journey_id`, `actual_duration_ms`, `simulated`, timestamps `long` epoch millis; AVRO-parse OK)
  - [x] 1.3 Modelo Pydantic `ExecutionFeedback` (`src/models/execution_feedback.py`; Pydantic v2 `ConfigDict(extra="forbid")`; `simulated`/`journey_id` defaults; ganchos `capability`+`journey_id`)
  - [x] 1.4 `src/observability/feedback_sink.py` (`update_one` por `ticket_id`, `$set` idempotente, marca `result_simulated`, `try/except` que não propaga, `COLLECTION="execution_tickets"` evoluível)
  - [x] 1.5 Testes da Fase 0 verdes (10/10 sink; sanity 23/23 com `test_metrics`; sem regressão causada — vermelhos do consumer são pré-Fase-0)

### Fase 1 — Adapter EXECUTE (ligar o emissor à Fundação)

- [~] 2. `execution_result_consumer` como adapter fino + DI do sink (código completo; gate E2E real pendente de cluster)
  - **DoR:** Fase 0 fechada (sink testado).
  - **DoD:** o consumer traduz `ExecutionResult` → `ExecutionFeedback` e delega ao sink (sem lógica de Mongo no consumer); persistência desacoplada do signal (falha não bloqueia o workflow); E2E A→C6 fecha 8/8 tickets COMPLETED e os tickets ficam com `actual_duration_ms>0` e `completed_at` em millis.
  - **Evidência:** `sub-specs/fase1-evidence.md` (6 testes de adapter verdes; desacoplamento provado por `test_feedback_failure_does_not_block_signal_or_commit`; gate E2E A→C6 marcado como pendente de execução no cluster).
  - [x] 2.1 Teste do adapter (`tests/unit/test_execution_result_consumer_feedback.py`, 6 testes: `capability="EXECUTE"`, `simulated`←`metadata.simulated`, `completed_at` fallback millis, no-sink noop, integração `_process_result` emite+signala, falha não bloqueia signal/commit)
  - [x] 2.2 `feedback_sink` no construtor do `ExecutionResultConsumer` (kwarg opcional, não quebra assinatura); `_emit_feedback()` adapter defensivo (try/except, sem Mongo); chamada após `_send_workflow_signal`, antes do `commit`
  - [x] 2.3 DI: `FeedbackSink(app_state.mongodb_client, metrics=...)` injetado no `main.py` (guarda `if FeedbackSink and app_state.mongodb_client`)
  - [~] 2.4 Gate E2E A→C6 **PENDENTE de cluster** (script E2E não corre via harness — exit 144, ver MEMORY). Desacoplamento (persist falha → signal+commit continuam) PROVADO por teste de integração. A correr no cluster: 8/8 COMPLETED + `actual_duration_ms>0` + `completed_at` epoch millis

### Fase 2 — Leitor LEARN (alinhar o consumidor de dados)

- [~] 3. Corrigir contrato de tipo e exclusão de verde-falso no `duration_predictor` (código+contrato verdes; prova com dados reais pendente de cluster)
  - **DoR:** Fase 1 verde (duração a chegar ao corpus).
  - **DoD:** filtro temporal em epoch millis (2 sítios: `_check_training_data_availability` e `train_model`/`find`); query exclui `result_simulated`; `_check_training_data_availability()` deixa de registar `insufficient_training_data` quando há execuções reais na janela.
  - **Evidência:** `sub-specs/fase2-evidence.md` (2 testes de contrato verdes; diff mínimo 20/5; 6 falhas de `test_ml_prediction_integration` provadas PRÉ-EXISTENTES).
  - [x] 3.1 `cutoff_date` (datetime) → `cutoff_ms` (epoch millis) nos 2 filtros `completed_at: {"$gte": ...}` (`_check_training_data_availability` + `train_model`)
  - [x] 3.2 `result_simulated: {"$ne": True}` adicionado às queries de contagem e de treino
  - [~] 3.3 Contrato provado por teste unit (`test_duration_predictor_feedback_query.py`: `$gte` é int + `result_simulated` excluído). Prova com **dados reais** (`countDocuments` sobe vs baseline; `insufficient_training_data` desaparece) **PENDENTE de cluster** (agrupada com gate E2E da Fase 1)

### Fase 3 — Anti-regressão e prova de transversalidade

- [x] 4. Guardas anti-regressão no CI + asserção arquitetural (gate E2E de cluster documentado)
  - **DoR:** Fases 1–2 verdes.
  - **DoD:** guarda que falha se o filtro do predictor voltar a usar `datetime`; teste de transversalidade do sink no CI; guarda de contrato cruzado sink↔predictor; assert E2E de loop-fechado documentado para o cluster.
  - **Evidência:** `sub-specs/fase3-evidence.md` (guarda de contrato cruzado PROVADA a detetar regressão por renomeação; 21/21 testes do loop verdes; ruff limpo).
  - [~] 4.1 Assert E2E "tickets com `actual_duration_ms>0` > 0" — o script `test-e2e-pipeline-completo.sh` é **git-ignored** (não versionável); snippet de validação `mongosh` documentado em `fase3-evidence.md` para correr no cluster
  - [x] 4.2 Guarda de tipo no CI: `test_duration_predictor_feedback_query.py` + `test_loop_learn_contract_guard.py::test_predictor_time_filter_is_epoch_millis_not_datetime` (falham se voltar a `datetime`)
  - [x] 4.3 Transversalidade no CI: `test_feedback_sink.py::test_transversal_accepts_generate_without_change` (gate corre em `tests/unit/`) — âncora do princípio
  - [x] 4.4 **NOVO** guarda de contrato cruzado `test_loop_learn_contract_guard.py` (sink↔predictor; provada a detetar renomeação); estado final + ganchos `capability`/`journey_id` documentados em `fase3-evidence.md`
