# Fase 4 — Evidência (marcador de ingestão J4 + métricas por jornada)

> Spec: 2026-06-23-journey-router · Task 5 · Branch `feat/convergencia-dbs`
> Pipeline: dev (agent, TDD) → auditoria qualidade + completude (agents) → remediação dirigida (agent) → commit. Gate E2E = cluster (pendente).

## Dev (TDD) — 1ª iteração

- `doc-ingestion/src/services/gateway_client.py`: `_build_intent_request` passa `context.source="doc-ingestion"` (+`metadata.journey_hint="MIGRATE"`).
- Label `journey` adicionado às métricas-chave (`neural_hive_observability/metrics.py` + `orchestrator-dynamic/src/observability/metrics.py`); `execution_result_consumer` emite `record_execution_result_processed(status, journey)`.

## Auditorias (qualidade + completude) — 2 achados CRÍTICOS convergentes

Ambas as auditorias provaram que a 1ª iteração estava **verde nos testes unitários mas partida ponta-a-ponta**: os *consumidores* do sinal foram adicionados, mas os *produtores/elos* estavam quebrados.

| Achado | Sev | Decisão |
|---|---|---|
| **Marcador J4 nunca chega ao STE.** `IntentRequest` (gateway) não tem campo `source` (extra ignorado pelo Pydantic); o gateway constrói `IntentEnvelope.context` a partir do `user_context` (headers/JWT), não do corpo; e — elo mais subtil — `IntentEnvelope.to_avro_dict()` (o que vai para o Kafka) **não emitia** `context.source`. Logo o `journey_classifier` Tier 1 (`context.get("source")`) nunca via "doc-ingestion" → J4 nunca disparava por este caminho. Testes do `gateway_client` passavam por testarem output descartado. | **CRÍTICO** | ✅ Corrigido (ver abaixo). |
| **Label `journey` sempre "unknown".** `execution.results` carregava só `journey_id` (UUID), nunca o enum `journey`; `execution_result_consumer` lia `result_data.get("journey")` → sempre None → label sempre "unknown". Segmentação do loop LEARN por jornada (objetivo do Scope) não alcançada. | **CRÍTICO** | ✅ Corrigido (ver abaixo). |
| Métricas journey em `neural_hive_observability` (`observe_orquestracao_duration`, `increment_plans`, `observe_plan_execution`) sem chamadores de produção (os 2 callers do STE usam a classe homónima `NeuralHiveMetrics` do próprio STE, sem `journey`). | ALTO | ⚪ Não ligar a callers fabricados (inventaria dados — viola "marcar+medir+falhar"); não reverter o label (testes-contrato do lib `tests/test_metrics.py` já o fixam, regra 7). Ficam como API órfã/forward-looking documentada. Métrica com caminho de dados real = a do orchestrator. |

## Remediação dirigida — verificada pelo orquestrador

### Crítico 1 — `source` flui gateway → STE
1. `gateway-intencoes/src/models/intent_envelope.py:146` — `Context.source: str | None = None`.
2. `…/intent_envelope.py:375` — `IntentRequest.source: str | None = None`.
3. `…/src/main.py:862-870` — `envelope_context = dict(user_context)`; se `request.source` vier no corpo, `envelope_context["source"] = request.source` (**precedência** sobre user_context); `:884` passa `context=envelope_context`.
4. `…/intent_envelope.py:281-283` — `to_avro_dict()` passa a emitir `"source": self.context.source` (elo load-bearing).
5. `schemas/intent-envelope/intent-envelope.avsc` — campo `source` (`["null","string"]`, default null → retrocompat) no record `Context`.

Daí, STE `journey_classifier.py` (`context.get("source")`) resolve **J4_MIGRATE**.

### Crítico 2 — enum `journey` flui até `execution.results` (mesmo padrão do `journey_id` da Fase 3)
1. `orchestrator-dynamic/src/activities/ticket_generation.py` — `journey = plan_data.get("journey") or cognitive_plan.get("journey")`; `"journey": journey` no ticket.
2. `worker-agents/src/engine/execution_engine.py` (`_result_correlation_kwargs`) — propaga `journey` (só se truthy); alimenta as 11 chamadas `publish_result` via `**kwargs` (path de preempção fica de fora, igual ao journey_id).
3. `worker-agents/src/clients/kafka_result_producer.py` — novo param `journey` → `"journey"` no payload.
4. `schemas/execution-result/execution-result.avsc` — campo `journey` (`["null","string"]`, default null → retrocompat).
5. `execution_result_consumer.py` — `record_execution_result_processed(status, journey=result_data.get("journey"))` passa a receber valor real (fallback "unknown" mantido).

## Resultado (RED→GREEN)

```
gateway source propagation (integração real, TestClient): 2 passed
worker journey enum (engine + producer):                  6 passed
orchestrator journey enum (ticket + consumer):            4 passed
schemas Avro (intent-envelope +source, execution-result +journey): parse OK
sem regressões (worker journey_id Fase 3 16/16; falhas pré-existentes confirmadas por stash)
```
black limpo nos 5 ficheiros de produção; sem `ruff --fix` (UP017/UTC quebra py3.10); diffs mínimos/aditivos.

## Gate Fase 4 (código) — VERDE; E2E pendente de cluster

- [x] `doc-ingestion` marca `context.source="doc-ingestion"` **e** o marcador atravessa gateway→STE (corrigido o descarte)
- [x] Tier 1 resolve J4_MIGRATE a partir de `context.source`
- [x] enum `journey` propaga plano→ticket→result→consumer; métrica deixa de ser estruturalmente "unknown"
- [x] decisão documentada sobre métricas órfãs do lib observability
- [ ] **Gate E2E** (cluster): intenção doc-ingestion real → `cognitive_plan.journey == J4_MIGRATE` + métrica `record_execution_result_processed` com `journey != "unknown"` no Prometheus — pendente de deploy (gateway+STE+orchestrator+worker) + **re-registo dos schemas** (intent-envelope, cognitive-plan, execution-result) no Schema Registry/Apicurio (evolução backward-compatible por defaults)

## Honestidade — o que só o E2E de cluster confirma
1. Schema Registry aceita a evolução BACKWARD dos `.avsc` (defaults null/"" devem ser compatíveis; subject pode estar pinado).
2. Gateway em produção serializa via Avro (não JSON) e o STE deserializa `context.source` do binário.
3. Um plano doc-ingestion real percorre `/intentions`→STE→J4_MIGRATE e a métrica aparece no Prometheus com `journey="J4_MIGRATE"` (não só `unknown`).

O teste de integração do gateway é in-process (TestClient), não atravessa Kafka real.
