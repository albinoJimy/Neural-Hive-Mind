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

- [ ] 2. `execution_result_consumer` como adapter fino + DI do sink
  - **DoR:** Fase 0 fechada (sink testado).
  - **DoD:** o consumer traduz `ExecutionResult` → `ExecutionFeedback` e delega ao sink (sem lógica de Mongo no consumer); persistência desacoplada do signal (falha não bloqueia o workflow); E2E A→C6 fecha 8/8 tickets COMPLETED e os tickets ficam com `actual_duration_ms>0` e `completed_at` em millis.
  - **Evidência:** `sub-specs/fase1-evidence.md` (plano de teste + contagem por DB + prova de que o signal continua a fechar).
  - [ ] 2.1 Escrever teste do adapter (`_emit_feedback` mapeia `metadata.simulated`→`simulated`, `actual_duration_ms`, `capability="EXECUTE"`; `journey_id` opcional)
  - [ ] 2.2 Adicionar `feedback_sink` ao construtor do `ExecutionResultConsumer`; implementar `_emit_feedback()`; chamar após `_send_workflow_signal`, antes do `commit`
  - [ ] 2.3 Injetar `FeedbackSink(app_state.mongodb_client)` no `main.py` (DI já disponível em `main.py:498,544`)
  - [ ] 2.4 Gate E2E A→C6: 8/8 COMPLETED + `db.execution_tickets` do novo plano com `actual_duration_ms>0` e `completed_at` epoch millis; provar que persist falha (Mongo down simulado) NÃO impede o signal

### Fase 2 — Leitor LEARN (alinhar o consumidor de dados)

- [ ] 3. Corrigir contrato de tipo e exclusão de verde-falso no `duration_predictor`
  - **DoR:** Fase 1 verde (duração a chegar ao corpus).
  - **DoD:** filtro temporal em epoch millis (2 sítios: `check_training_data_availability` ~203 e `train`/`find` ~571); query exclui `result_simulated`; `check_training_data_availability()` deixa de registar `insufficient_training_data` quando há execuções reais na janela.
  - **Evidência:** `sub-specs/fase2-evidence.md` (count antes/depois; ticket simulado presente na coleção mas ausente do treino).
  - [ ] 3.1 Substituir `cutoff_date` (datetime) por `cutoff_ms` (epoch millis) nos filtros `completed_at: {"$gte": ...}`
  - [ ] 3.2 Adicionar `result_simulated: {"$ne": True}` às queries de contagem e de treino
  - [ ] 3.3 Provar: `countDocuments({actual_duration_ms:{$gt:0}, result_simulated:{$ne:true}})` sobe vs baseline; ticket `simulated=true` excluído do conjunto de treino

### Fase 3 — Anti-regressão e prova de transversalidade

- [ ] 4. Guardas anti-regressão no E2E/CI + asserção arquitetural
  - **DoR:** Fases 1–2 verdes.
  - **DoD:** asserção E2E "contagem de duração real sobe vs baseline" ativa; guarda que falha se o filtro do predictor voltar a usar `datetime`; teste de transversalidade do sink no CI (prova de que GENERATE/MIGRATE encaixam sem reabrir a Fundação).
  - **Evidência:** `sub-specs/fase3-evidence.md`.
  - [ ] 4.1 Adicionar assert estruturado ao `scripts/test-e2e-pipeline-completo.sh`: nº de tickets com `actual_duration_ms>0` do run > 0 (loop fechado)
  - [ ] 4.2 Guarda no CI: teste que falha se `duration_predictor` filtrar `completed_at` com `datetime` (regressão do contrato de tipo)
  - [ ] 4.3 Promover o teste de transversalidade (`record(capability="GENERATE")`) a gate de CI — âncora do princípio Fundação → Roteamento → Capacidades
  - [ ] 4.4 Documentar estado final + ganchos prontos (`capability`/`journey_id`) e o caminho de evolução (Roteamento passo 2, Capacidades passo 3) em `fase3-evidence.md`
