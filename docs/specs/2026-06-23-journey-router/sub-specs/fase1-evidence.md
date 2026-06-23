# Fase 1 — Evidência (JourneyClassifier Tier 1)

> Spec: 2026-06-23-journey-router · Task 2 · Branch `feat/convergencia-dbs`
> Pipeline: dev (agent, TDD) → auditoria qualidade + completude (agents) → remediação dirigida → commit.

## Dev (TDD)

- `services/semantic-translation-engine/src/services/journey_classifier.py`: `JourneyClassifier` Tier 1 (sinais estruturados determinísticos), espelha o `workflow_classifier`.
- `services/semantic-translation-engine/tests/unit/test_journey_classifier.py`: testes (RED→GREEN).
- **Descoberta:** `workflow_type` real é **lowercase** (`"generation"`/`"orchestration"`) — o classifier trata case-insensitive (`.lower()` sob `isinstance str`).

Precedência (Tier 1): `context.source=="doc-ingestion"`→J4 > `constraints.execution_mode=="plan_only"`→J1 > `workflow_type` generation→J3 / orchestration→J2 > sem sinal→UNKNOWN (`no_match`, anti-verde-falso). Gancho `_classify_llm` (Fase 2) levanta `NotImplementedError`, não-alcançado no Tier 1.

## Auditorias (qualidade + completude)

Código de produção sólido (confirmações positivas: sem-sinal não chama LLM; confidence dentro de [0,1]; classification_method dentro do Literal; acesso defensivo completo; precedência determinística). Achados → decisão:

| Achado | Sev | Decisão |
|---|---|---|
| TODO mal posicionado (risco na Fase 2) | ALTO | ✅ comentário clarificado (substituição inequívoca) |
| `test_tier1_does_not_invoke_llm` tautológico | BAIXO | ✅ robusto: `patch.object(_classify_llm)` + `call_count==0` nos 2 caminhos |
| teste 3 sinais simultâneos em falta | MÉDIO | ✅ +`test_all_three_signals_present_source_wins` |
| `intent_envelope=None` direto não testado | MÉDIO | ✅ +`test_intent_envelope_none_does_not_raise` |
| `workflow_type` enum (não str) não testado | BAIXO | ✅ +`test_workflow_type_as_enum_object_falls_back_unknown` |
| singleton não thread-safe | ALTO | ❌ padrão herdado do `workflow_classifier`; stateless (nota) |
| `journey_confidence_threshold` ausente em settings | BAIXO | ⚪ adiar p/ Fase 2 (getattr já faz fallback; sem efeito funcional no Tier 1) |

## Resultado

```
tests/unit/test_journey_classifier.py: 24 passed (20 + 4 da remediação)
sem regressões; black limpo; sintaxe OK
```

## Notas de prontidão

- **Fase 2 (Tier 2/LLM):** ponto de extensão definido (`_classify_llm`, assinatura final, `classification_method="llm"` já no Literal); substituir o `return self._no_match()` por `_classify_llm` com fallback. Adicionar `journey_confidence_threshold` ao `settings.py` nessa fase.
- **Fase 3:** orchestrator/cognitive_plan NÃO tocados (confirmado); propagação fica para lá.

## Gate Fase 1 — VERDE

- [x] 4 sinais Tier 1 implementados, precedência determinística
- [x] sem sinal → UNKNOWN (anti-verde-falso); LLM não invocado no Tier 1
- [x] acesso defensivo (envelope/plan None/vazios)
- [x] 24/24 testes; sem regressões
