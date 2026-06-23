# Technical Specification

This is the technical specification para a spec detalhada em @docs/specs/2026-06-23-journey-router/spec.md

## Contexto e estado atual (medido no código)

- **Bifurcação existente:** `services/semantic-translation-engine/src/services/workflow_classifier.py` — `classify(intent_envelope, intermediate_repr) → (WorkflowType, metadata)`, por keywords (GENERATION/ORCHESTRATION), com `metadata{confidence, reason}`.
- **Roteamento difuso:** `services/orchestrator-dynamic/src/consumers/decision_consumer.py` re-deriva `workflow_type` para escolher `fluxo_g_workflow` vs `orchestration_workflow`.
- **Gancho pronto (Fundação):** `ExecutionFeedback.journey_id` (`services/orchestrator-dynamic/src/models/execution_feedback.py`) e o adapter (`execution_result_consumer._emit_feedback`) já leem `result_data.get("journey_id")` — hoje sempre `None`.
- **Libs partilhadas:** `libraries/python/neural_hive_domain/` (domain.py — padrão `UnifiedDomain.UNKNOWN` a espelhar) e `libraries/python/neural_hive_llm/` (LLM client com circuit breaker/resiliência) para o Tier 2.

## Princípio de desenho

1. **Decidir cedo, propagar** — a Journey é decidida no STE (junto com o workflow_type) e gravada no `cognitive_plan`; nada a jusante re-deriva.
2. **Híbrido tiered** — sinais estruturados determinísticos primeiro (rápido, barato, fiável); LLM só nos casos ambíguos (minimiza latência/custo/dependência).
3. **Anti-verde-falso** — `confidence` + `reasoning` + `classification_method`; baixa confiança → `UNKNOWN` (espelha `UnifiedDomain.UNKNOWN`), nunca força jornada.
4. **Lógica única partilhada** — enum e contrato de decisão em `neural_hive_domain`; sem duplicar critérios entre serviços.
5. **Sinais, não keywords, para os ganchos** — J4 por marcador `source` de ingestão (não por palavras como "migração").

## Modelo `Journey` (neural_hive_domain)

`libraries/python/neural_hive_domain/journey.py`:
- `class Journey(StrEnum)`: `J1_PLAN_ONLY`, `J2_ORCHESTRATE`, `J3_BUILD`, `J4_MIGRATE`, `UNKNOWN`.
- `class JourneyDecision(BaseModel)`: `journey: Journey`, `journey_id: str`, `confidence: float`, `reasoning: str`, `classification_method: str` (`structured_signal`|`llm`|`no_match`).
- Exportado em `__init__.py`.

## `JourneyClassifier` (STE)

`services/semantic-translation-engine/src/services/journey_classifier.py`:

```
classify(intent_envelope, cognitive_plan) -> JourneyDecision
  # Tier 1 — sinais estruturados (determinístico)
  if intent_envelope.context.source == "doc-ingestion":      -> J4_MIGRATE  (conf alta)
  if intent_envelope.constraints.execution_mode == "plan_only": -> J1_PLAN_ONLY
  if cognitive_plan.workflow_type == GENERATION:             -> J3_BUILD
  if cognitive_plan.workflow_type == ORCHESTRATION:          -> J2_ORCHESTRATE
  # Tier 2 — LLM (só se Tier 1 não deu sinal forte / confiança baixa)
  decision = llm_classify(contexto completo: texto, entities, metadata, plano)
  # Anti-verde-falso
  if decision.confidence < settings.journey_confidence_threshold: -> UNKNOWN + requires_manual_validation
```

- **Tier 1** lê sinais já presentes; não chama LLM nos casos claros (a maioria).
- **Tier 2** usa `neural_hive_llm` (com circuit breaker); prompt estruturado pede `{journey, confidence, reasoning}`. Se o LLM falhar/timeout → degrada para o melhor sinal Tier 1 ou `UNKNOWN` (nunca bloqueia o pipeline).
- `journey_id` = UUID gerado na decisão (estável por plano).
- Threshold configurável: `JOURNEY_CONFIDENCE_THRESHOLD` (default ~0.6, alinhado com o NLU).

## Propagação

- **STE orchestrator** (`orchestrator.py`): após `workflow_classifier` + DAG, chama `JourneyClassifier.classify(...)` e grava no `cognitive_plan`: `journey`, `journey_id`, `journey_confidence`, `journey_reasoning`, `journey_classification_method`. (`models/cognitive_plan.py` ganha os campos.)
- **decision_consumer** (orchestrator): lê `cognitive_plan.journey` e roteia (J3→fluxo_g; J2/J4→orchestration/cutover; J1→sem execução/plan-only); injeta `journey_id` nos tickets/`execution.tickets`.
- **ExecutionFeedback**: o adapter já lê `journey_id` do evento — passa a vir preenchido. Sem alteração no sink (gancho pronto).

## Marcador de ingestão (J4)

`services/doc-ingestion/src/services/gateway_client.py`: ao construir a intenção, definir `context.source = "doc-ingestion"` (e opcional `context.metadata.journey_hint = "MIGRATE"`). Sinal estruturado fiável para o Tier 1.

## Métricas por jornada

`neural_hive_observability`: adicionar label `journey` às métricas-chave do pipeline (duração de orquestração, tickets, resultados). Permite segmentar o loop LEARN e dashboards por jornada.

## Anti-verde-falso (padrão do projeto)

Espelha o `UnifiedDomain.UNKNOWN` do NLU: `classification_method` distingue `structured_signal`/`llm`/`no_match`; baixa confiança → `UNKNOWN` + `requires_manual_validation`; `reasoning` sempre presente para explicabilidade.

## Validação por fase (gates)

- **Gate Fase 0 (modelo):** enum `Journey` + `JourneyDecision` em `neural_hive_domain`; testes unitários.
- **Gate Fase 1 (classifier Tier 1):** sinais estruturados → jornada correta sem LLM; anti-verde-falso (UNKNOWN) testado.
- **Gate Fase 2 (classifier Tier 2):** LLM mockado → Journey+confidence+reasoning; fallback em falha do LLM.
- **Gate Fase 3 (propagação + roteamento):** STE grava journey no plano; decision_consumer roteia por journey; journey_id propaga até ao ExecutionFeedback (E2E).
- **Gate Fase 4 (ingestão + métricas):** marcador source no doc-ingestion → J4; label journey nas métricas.

## Mapa de risco

| Risco | Mitigação |
|---|---|
| LLM latência/indisponível (Tier 2) | Tier 1 cobre a maioria; LLM só ambíguos; circuit breaker; fallback UNKNOWN |
| J4/Fluxo H sem E2E real | roteamento J4 funcional; validação E2E completa fica dependente do Fluxo H |
| Classificação errada de jornada | confidence+reasoning+UNKNOWN; manual validation; explicável |
| Campos novos no cognitive_plan (compat Avro) | adicionar como opcionais com default; consumidores antigos ignoram |
