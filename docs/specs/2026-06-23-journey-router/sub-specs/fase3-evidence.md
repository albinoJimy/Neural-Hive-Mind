# Fase 3 — Evidência (propagação + roteamento por journey)

> Spec: 2026-06-23-journey-router · Task 4 · Branch `feat/convergencia-dbs`
> Pipeline: dev (agent, TDD) → auditoria qualidade + completude (agents) → remediação dirigida → commit. Gate E2E A→C6 = cluster (pendente).

## Dev (TDD) — cadeia de propagação completa

`journey`/`journey_id` flui início→fim:
1. STE `journey_classifier.classify` (async) → `JourneyDecision` (journey_id UUID).
2. `orchestrator.py` (bloco B5.5): `await classify(...)` grava 5 campos no `cognitive_plan`; falha → defaults UNKNOWN (não bloqueia).
3. `cognitive_plan.py`: 5 campos opcionais c/ default + `to_avro_dict`.
4. `decision_consumer.py`: roteia POR journey (J3→fluxo_g; J2/J4→orchestration; J1→sem execução) com **fallback** a workflow_type (planos antigos); injeta journey_id no ticket.
5. `ticket_generation.py`: journey_id no ticket. `execution_engine.py`+`kafka_result_producer.py`: journey_id no `execution.results` (6 call-sites) + `execution-result.avsc`.
6. `execution_result_consumer._emit_feedback`: já lê `journey_id` (gancho da Fundação) → ExecutionFeedback.

Testes novos: STE 11 (cognitive_plan_journey 5 + orchestrator_journey 6), orchestrator 16 (decision_consumer_journey_routing 13 + ticket_generation_journey 3), worker 4.

## Auditorias (qualidade + completude) — achado CRÍTICO bloqueante

| Achado | Sev | Decisão |
|---|---|---|
| **Drift schema Avro:** modelo+to_avro_dict têm os 5 campos journey mas o `cognitive-plan.avsc` registado NÃO → AvroSerializer descarta-os → journey nunca chega ao consumer (fallback sempre) em produção | **CRÍTICO** | ✅ adicionados os 5 campos a `schemas/cognitive-plan/cognitive-plan.avsc` **e** `helm-charts/kafka-topics/files/schemas/cognitive-plan.avsc` (opcionais c/ default; 35 campos; AVRO parse OK) |
| `decision_consumer:761` `consolidated_decision["decision_id"]` (KeyError em is_direct_plan→loop infinito) | CRÍTICO | ✅ `.get("decision_id")` |
| 7º call-site (preemption) omite journey_id | IMPORTANTE | ❌ gap pré-existente (já omite plan_id/correlation_id); nota |
| `journey_id or None` falsy | MÉDIO | ❌ correto para "" (default) |
| `original_domain` enum sem ARCHITECTURE/BEHAVIOR | MÉDIO | ⚪ pré-existente, fora de escopo |

## Resultado

```
STE: 45 passed (cognitive_plan_journey + journey_classifier)
orchestrator-dynamic: 19 (decision: 13 journey + 6 routing existente) + ticket_generation_journey
worker: 4 passed
schemas Avro: 35 campos, parse OK
sem regressões (test_decision_consumer_routing 6/6, test_execution_result_consumer_feedback intactos)
```
Nota: `test_orchestrator_journey` (STE) requer shim `neural_hive_risk_scoring` (limitação py3.10 pré-existente; dev validou 6/6 com shim) — mesmos 3 erros de import que `test_orchestrator_approval`.

## ⚠️ Dependência de deploy — Schema Registry (documentar)

Antes de o roteamento por journey funcionar no caminho **Avro** de produção:
1. **Re-registar `cognitive-plan.avsc`** (agora com 5 campos journey) no Schema Registry (Apicurio) — evolução backward-compatible (defaults).
2. **Re-registar `execution-result.avsc`** (campo journey_id, `["null","string"]` default null).
Sem isto, o producer cai no fallback JSON (que já carrega os campos) mas o caminho Avro descarta-os. (A memória regista que o Schema Registry já causou "verde falso" antes — apicurio.)

## Gate Fase 3 (código) — VERDE; E2E pendente de cluster

- [x] 5 campos no cognitive_plan (modelo + to_avro_dict + **schema Avro**)
- [x] STE grava journey (await classify); falha→UNKNOWN sem bloquear
- [x] decision_consumer roteia por journey + fallback workflow_type
- [x] cadeia journey_id plano→ticket→result→feedback (código + schema)
- [x] KeyError corrigido; sem regressões
- [ ] **Gate E2E A→C6** (cluster): `cognitive_plan.journey` preenchido + `ExecutionFeedback.journey_id` herdado (não None) — pendente de deploy + re-registo dos schemas
