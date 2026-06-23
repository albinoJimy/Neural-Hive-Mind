# Fase 0 — Evidência (modelo Journey partilhado)

> Spec: 2026-06-23-journey-router · Task 1 · Branch `feat/convergencia-dbs`
> Pipeline: dev (agent) → auditoria qualidade (agent) → auditoria completude (agent) → remediação dirigida → commit.

## Dev (TDD)

- `libraries/python/neural_hive_domain/journey.py`: `Journey(str, Enum)` (J1-J4 + UNKNOWN; `str+Enum` por compat py3.10, espelha `UnifiedDomain`) + `JourneyDecision` (Pydantic v2).
- `libraries/python/neural_hive_domain/tests/test_journey.py`: testes (RED→GREEN observado).
- `__init__.py`: exporta `Journey`, `JourneyDecision`.

## Auditorias (qualidade + completude, em paralelo)

Achados convergentes e respetiva decisão:

| Achado | Sev | Decisão |
|---|---|---|
| `confidence` sem constraint [0,1] | ALTO | ✅ `Field(ge=0.0, le=1.0)` + teste negativo |
| `classification_method` str livre | ALTO | ✅ `Literal["structured_signal","llm","no_match"]` + teste negativo |
| `model_dump` frágil (enum vs str) | MÉDIO | ✅ `ConfigDict(use_enum_values=True)` — serialização string consistente p/ Kafka/Avro/Mongo |
| `journey_id` UUID estrito | ALTO | ❌ rejeitado — todo o sistema usa `str` ids (plan_id/ticket_id/feedback_id); consistência |
| `UnifiedDomain.UNKNOWN` ausente vs MEMORY | MÉDIO | ⚪ fora de escopo (código alheio; nota para verificação separada) |
| defaults p/ Fase 3 (cognitive_plan) | MÉDIO | ⚪ trabalho da Fase 3 (campos do plano opcionais c/ default por compat Avro) |

## Remediação dirigida (aplicada)

`journey.py`: `Field(ge,le)` em `confidence`, `Literal` em `classification_method`, `use_enum_values=True`, import `Field`/`Literal`/`ConfigDict`. `test_journey.py`: +`test_confidence_out_of_range_raises`, +`test_invalid_classification_method_raises`.

## Resultado

```
tests/test_journey.py: 17 passed  (15 + 2 negativos da remediação)
suite neural_hive_domain: 148 passed (sem regressões)
black: limpo · sintaxe OK
```

## Gate Fase 0 — VERDE

- [x] `Journey` enum (5 variantes, UNKNOWN anti-verde-falso) + `JourneyDecision` validado
- [x] exportado em `neural_hive_domain`
- [x] contrato fechado (Literal) + confidence [0,1] + serialização string
- [x] 17/17 testes; 148 suite verdes; sem regressões
