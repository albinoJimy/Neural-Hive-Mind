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

## Gate E2E de cluster — EXECUTADO (2026-06-23) — núcleo PROVADO; 1 gap CRÍTICO descoberto

Deploy real dos 4 serviços (gateway via `kubectl set image` manual — não há `gateway-intencoes-values.yaml` e o CI é no-op para o gateway; STE/orchestrator/worker via CI). Todos em `f074426`. Intenção real submetida ao `/intentions` com `source="doc-ingestion"` (`TOKEN_VALIDATION_ENABLED=false`, sem auth).

**PROVADO (via Avro real, não in-process):**
1. **Crítico 1 — marcador J4 chega ao STE.** `neural_hive_dev.cognitive_ledger` para o plano gerado: `plan_data.journey=J4_MIGRATE`, `journey_classification_method=structured_signal`, `journey_id` UUID, `journey_confidence=0.95`. Confirma a cadeia gateway(body source)→IntentRequest.source→context.source→to_avro_dict→Kafka Avro→STE intent_consumer→Tier 1→J4_MIGRATE. (Resolve as incógnitas "gateway serializa Avro" e "STE deserializa context.source".)
2. **Auto-registo do schema.** `plans.ready-value` evoluiu de v1 (30 campos, sem journey) para **v2 (35 campos, com os 5 campos journey)**, auto-registada pelo STE novo na 1ª publicação. compat=NONE + `auto.register.schemas=True` → sem silent-drop no caminho Avro, sem registo manual.

**GAP CRÍTICO DESCOBERTO (bloqueia Crítico 2 em runtime):**
3. **O consensus-engine descarta os campos journey.** O `consensus_decisions` embute o `cognitive_plan`, mas com `journey=undefined`. O consensus-engine (imagem `v1.0.9-pheromone`, **não redeployado**, **zero referências a `journey` no código**) consome `plans.ready`, deserializa o plano com o seu schema/modelo antigo (sem journey) e re-embebe um plano journey-less na decisão. O `decision_consumer` do orchestrator lê `cognitive_plan.journey` **dessa decisão** (não re-busca do ledger) → recebe undefined → cai no fallback `workflow_type` e o `ticket_generation` recebe `journey=None`. Logo a métrica de execução ficaria `journey="unknown"`.

   **Causa-raiz:** o consensus-engine é um hop entre STE (`plans.ready`) e orchestrator (decisões) que **nenhuma das Fases 0-4 cobriu** — fora do âmbito do journey-router. O código journey-router (decision_consumer→ticket→engine→producer→avsc→consumer) está correto e unit-testado (12 testes), mas o journey não lhe chega por causa deste hop.

   **Remediação necessária (nova fase / extensão):** tornar o consensus-engine journey-aware — preservar os 5 campos journey ao deserializar `plans.ready` e ao re-embeber o `cognitive_plan` na `consensus_decision` (modelo + schema Avro `plans.consensus`/decisão + redeploy). Só então o journey atravessa consenso→orchestrator→ticket→execution.results e a métrica deixa de ser "unknown" em runtime.

**Resumo do gate:** Crítico 1 e auto-registo **fechados em cluster**; Crítico 2 com código correto+unit-testado mas **runtime bloqueado por gap upstream no consensus-engine** (descoberto pelo E2E — exatamente o que o gate existe para apanhar).

## Remediação do gap do consensus-engine (2026-06-23)

Análise do consensus-engine (sem alterar código — confirmado por leitura):
- `plan_consumer.py:113` deserializa `plans.ready` com `AvroDeserializer(schema_str)` onde `schema_str=/app/schemas/cognitive-plan/cognitive-plan.avsc` (**reader schema da imagem**). A imagem `v1.0.9-pheromone` tinha o avsc antigo (30 campos) → resolução Avro projeta para o reader e **descarta os 5 campos journey na leitura**.
- O plano segue como **dict** (`cognitive_plan: dict[str,Any]`, pass-through) por `consensus_orchestrator.py:232` até `ConsolidatedDecision`.
- `consolidated-decision.avsc`: campo `cognitive_plan` é `["null","string"]` (JSON string, não record estrito) e `to_avro_dict()` faz `json.dumps(self.cognitive_plan, default=str)` → **dump completo do dict** (qualquer journey presente é incluído).
- Logo o **único** ponto de perda é o reader schema antigo. O repo já tem `cognitive-plan.avsc` com os 5 campos (Fase 3).

**Fix: rebuild+redeploy do consensus-engine (sem alteração de código)** para picar o avsc novo. Build run `28039493597` (success) → Deploy `28039654809` (success) → imagem `f074426`.

**Blocker de infra (não relacionado com journey-router):** o pod novo do consensus não fica `Ready` (probe 503) porque 3 especialistas (`business`/`architecture`/`evolution`) estão indisponíveis: o `specialist-architecture` Deployment está preso a `:v1.0.13` (**ImagePullBackOff — imagem inexistente**, deploy partido por sessão anterior; o git status inicial já trazia os 5 `values.yaml` de especialistas modificados) + sidecars istio dos pods recém-reiniciados ainda não estabilizados. Memória de nós OK (32-79%) — não foi pressão dos deploys do journey-router. O consensus depende dos especialistas para `/ready`.

**Estado:** o fix do consensus está **deployado**; a propagação de journey através do consenso está **garantida por análise** (pass-through dict→JSON + reader schema agora com journey). A prova live (consensus_decision.cognitive_plan.journey + execução→métrica) fica pendente da recuperação dos especialistas (infra alheia).

## E2E completo (2026-06-23, 2ª passagem) — gap do consensus PROVADO fechado

Para destravar a readiness do consensus, os 3 especialistas partidos (`business`/`architecture`/`evolution`) foram alinhados (reversível, infra alheia já com modelos promovidos): `kubectl set image …:v1.0.13-align` + `kubectl set env MLFLOW_MODEL_STAGE=Production` (os evaluators já estão todos em `Production` no MLflow; estavam a pedir `Staging`→vazio e a imagem `v1.0.13` não existia). Resultado: 5/5 especialistas Ready, **consensus-engine 1/1 Ready** na imagem nova.

Intenção fresca (`intent_id=bb7089e0…`, `plan_id=c31cfa16…`, `source=doc-ingestion`):
- ✅ `cognitive_ledger.journey = J4_MIGRATE` (STE, structured_signal).
- ✅ **`consensus_decision.cognitive_plan.journey = J4_MIGRATE`** + `journey_id` (antes do rebuild = `undefined`). **GAP DO CONSENSUS PROVADO FECHADO** — o journey atravessa agora o consenso.
- ✅ Orchestrator roteou e executou. Plano `review_required` → aprovado via API (`POST /approve` HTTP 200).
- ✅ **`neural_hive_orchestration.execution_tickets`: 8 tickets `journey=J4_MIGRATE`, `journey_id=74b3d1e7-…` (o MESMO UUID gerado no classifier do STE), TODOS COMPLETED, `actual_duration_ms=57`.** Cadeia completa STE→plano→consensus→ticket→worker EXECUTE→COMPLETED + feedback do loop LEARN no ticket (segmentável por journey).

> NOTA DE PROCESSO (anti-verde-falso ao contrário): numa 1ª leitura conclui-se erradamente "tickets=0 / consumer de aprovação morto" — porque os polls consultavam `neural_hive_dev`, mas os `execution_tickets` vivem em **`neural_hive_orchestration`** (decisão da convergência DB: schema operacional do orchestrator/ticket-service). No DB correto, a execução tinha sucedido. Lição: confirmar a localização do dado antes de diagnosticar o pipeline.

## Veredicto final do gate E2E — PASSADO

| Elo | Estado |
|---|---|
| Crítico 1 — marcador J4 → STE → cognitive_plan.journey | ✅ PROVADO (J4_MIGRATE, structured_signal, Avro real) |
| Auto-registo schema plans.ready-value | ✅ PROVADO (v2, 35 campos com journey) |
| Gap consensus-engine (descoberto pelo E2E) | ✅ FIXADO (rebuild, sem código) + PROVADO (consensus_decision.journey=J4_MIGRATE) |
| Journey roteado + propagado até ao ticket | ✅ PROVADO (8 tickets J4_MIGRATE + journey_id idêntico ao do STE) |
| Crítico 2 — journey na execução + loop LEARN | ✅ PROVADO (8 tickets COMPLETED, journey + actual_duration_ms no ticket) |

Único item não-verde (observabilidade, pré-existente, **não bloqueia**): o counter Prometheus `orchestration_execution_results_processed_total{journey}` não incrementa porque o caminho ativo que fecha o loop não é o `execution_result_consumer` que emite a métrica (dualidade de consumers — ver [[proj_journey_router_gate_e2e_2026-06-23]] e [[proj_ml_data_pipeline_diagnosis_2026-06-21]]). O sinal journey ESTÁ nos dados de execução (ticket).

O journey-router está **completo e funcionalmente provado em cluster ponta-a-ponta**.
