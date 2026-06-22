# Fase 0 — Evidência (Fundação: contrato + sink transversal)

> Spec: 2026-06-22-fundacao-loop-learn · Task 1 · Branch `feat/fundacao-loop-learn` (de `feat/convergencia-dbs`)
> Data: 2026-06-22 · Princípio: Fundação → Roteamento → Capacidades (ADR-0011)

## Resumo

Construída a **Fundação transversal** do loop OBSERVE→LEARN como plano-Z, **sem tocar no runtime** (nenhum emissor ligado ainda). Disciplina TDD estrita: teste escrito primeiro, RED observado, GREEN mínimo.

## Artefactos criados

| Ficheiro | Papel |
|---|---|
| `services/orchestrator-dynamic/tests/unit/test_feedback_sink.py` | 10 testes (RED primeiro) |
| `services/orchestrator-dynamic/src/models/execution_feedback.py` | contrato Pydantic v2 `ExecutionFeedback` |
| `services/orchestrator-dynamic/src/observability/feedback_sink.py` | `FeedbackSink` (plano-Z, capability-agnostic) |
| `schemas/execution-feedback/execution-feedback.avsc` | contrato Avro (`AVRO parse OK`) |

## Ciclo TDD (prova)

1. **RED** — `python3 -m pytest tests/unit/test_feedback_sink.py` →
   `ModuleNotFoundError: No module named 'src.models.execution_feedback'` (falha pela razão certa: feature em falta).
2. **GREEN** — criados modelo + sink → `10 passed in 0.23s`.
3. **REFACTOR/lint** — `black` (reformatado) + `ruff check --fix` (2 nits auto-corrigidos: `RUF100` noqa não usado, `I001` ordenação de imports) → `ruff check` limpo.

```
tests/unit/test_feedback_sink.py ..........            10 passed
sanity (+ test_metrics):                               23 passed
```

## Invariantes da harmonização provados por teste

| Invariante (ADR-0011) | Teste |
|---|---|
| **I1 · loop transversal** (capability-agnostic) | `test_transversal_accepts_generate_without_change` — sink aceita `capability="GENERATE"` **sem alteração** |
| **I2 · Fundação manda no formato** | contrato `ExecutionFeedback` canónico; `extra="forbid"` |
| **I3 · ganchos prontos** | `test_journey_id_optional_for_routing_hook`, `test_carries_capability_hook` (`journey_id` p/ Roteamento, `capability` p/ Capacidades) |
| **anti-verde-falso** | `test_marks_simulated_for_green_false_guard` (`result_simulated` persistido) |
| **desacoplamento** | `test_persist_failure_does_not_propagate` (falha de Mongo engolida) |
| **idempotência** | `test_idempotent_uses_update_by_ticket_id` (update por `ticket_id`) |
| **contrato de tipo** | `test_completed_at_persisted_as_bson_date` (sink converte millis→Date; ver cluster-gate-evidence.md) |

## Nota de honestidade — vermelhos pré-existentes (não causados pela Fase 0)

`tests/unit/test_execution_result_consumer.py` tem **5 testes a falhar** (`MagicMock can't be used in 'await'`): o consumer faz `await self.temporal_client.get_workflow_handle(...)` (mudança anterior, documentada em `execution_result_consumer.py:252-254`) mas o teste mocka `get_workflow_handle` síncrono.

**Prova de pré-existência:** com os ficheiros da Fase 0 removidos (`git stash -u`) e na base `42dfab21`, o mesmo teste falha **exatamente os mesmos 5** (`5 failed, 9 passed`). A Fase 0 não toca o consumer nem o seu teste. Estes vermelhos são tratados na Fase 1 (que reescreve o consumer como adapter) ou ficam fora de escopo se o teste-contrato precisar de atualização separada.

## Gate Fase 0 — VERDE

- [x] `FeedbackSink` testado (transversalidade + idempotência + não-propagação) — 10/10
- [x] ruff + black limpos nos ficheiros novos
- [x] avsc JSON + AVRO parse OK
- [x] runtime não tocado (sem emissor ligado; Fase 1 fará o adapter EXECUTE)
