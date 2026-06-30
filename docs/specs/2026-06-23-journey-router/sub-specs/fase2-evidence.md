# Fase 2 — Evidência (JourneyClassifier Tier 2 — LLM)

> Spec: 2026-06-23-journey-router · Task 3 · Branch `feat/convergencia-dbs`
> Pipeline: dev (agent, TDD) → auditoria qualidade + completude (agents) → remediação dirigida (agent) → commit.

## Dev (TDD)

Tier 2 do `JourneyClassifier`: quando o Tier 1 não dá sinal e há `llm_client`, delega a decisão ao LLM (`neural_hive_llm.LLMClient.generate` → `.text`; circuit breaker embutido na lib). DI do `llm_client` (testável). Parsing defensivo, anti-verde-falso (UNKNOWN/no_match em falha/baixa confiança). `journey_confidence_threshold` adicionado ao `settings.py`. 34 testes (24 Tier 1 + 10 Tier 2), LLM sempre mockado.

## Auditorias (qualidade + completude) — achado CRÍTICO

| Achado | Sev | Decisão |
|---|---|---|
| `_run_async` (sync-over-async): `classify()` síncrono chamava LLM async via asyncio.run/ThreadPoolExecutor — bloquearia uma thread do event loop (orchestrator STE é `async def process_intent`) | **CRÍTICO** | ✅ `classify()`/`_classify_llm()` tornados **async**; `_run_async` + `import asyncio` eliminados |
| `_extract_json` regex greedy `\{.*\}` → JSON malformado com texto à volta | ALTO | ✅ lazy `\{.*?\}` + teste prefácio/sufixo |
| `test_classify_llm_hook_not_implemented` obsoleto/enganador | ALTO | ✅ removido; substituído por teste do comportamento real (sem client → no_match) |
| prompt injection latente (entities/metadata sem limite) | MÉDIO | ✅ `_truncate_field` (500 chars) + nota; mitigação temperature=0+threshold |
| cenários sem teste (resposta vazia, confidence bool/fora-range, reasoning ausente) | BAIXO | ✅ +testes |
| docstrings desatualizadas (Tier 1/sem LLM) | COSM | ✅ atualizadas |

## Remediação (agent) — verificada pelo orquestrador

- `classify()` async (linha ~125), `_classify_llm()` async (~235); `_run_async`/`asyncio` removidos (confirmado por grep).
- regex lazy (linha ~423, `re.DOTALL`).
- 40 testes (34 baseline + 6 novos; 1 obsoleto substituído).

```
tests/unit/test_journey_classifier.py: 40 passed
neural_hive_domain/tests/test_journey.py: 17 passed (sem regressão)
sintaxe OK · sem UTC · black limpo
```

## Prontidão Fase 3

`classify()` é agora **async** — o orchestrator async do STE fará `await journey_classifier.classify(intent_envelope, cognitive_plan)` e gravará a `JourneyDecision` (journey, journey_id, confidence, reasoning, classification_method) no `cognitive_plan`. `journey_confidence_threshold` já no settings. Wiring (orchestrator/cognitive_plan/decision_consumer) NÃO tocado — é a Fase 3.

## Gate Fase 2 — VERDE

- [x] Tier 2 LLM (neural_hive_llm) nos casos ambíguos; classification_method="llm"
- [x] fallback resiliente (timeout/circuit/malformado/baixa confiança → UNKNOWN)
- [x] **classify() async** (correção crítica sync-over-async)
- [x] threshold em settings, usado no Tier 2
- [x] 40/40 testes; Tier 1 preservado; sem regressões
