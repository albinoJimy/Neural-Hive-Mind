# Spec Tasks

> Passo 2 do ADR-0011 (Roteamento). Ordenação: Fase 0 (modelo partilhado) → Fase 1 (classifier Tier 1) → Fase 2 (classifier Tier 2/LLM) → Fase 3 (propagação + roteamento) → Fase 4 (ingestão + métricas). Cada fase é um gate: só avança com testes verdes + evidência.
>
> **Princípio:** decidir cedo (STE), propagar; sinais estruturados primeiro, LLM só nos ambíguos; anti-verde-falso (confidence/reasoning/UNKNOWN). TDD obrigatório. Detalhe em `sub-specs/technical-spec.md`.

## Tasks

### Fase 0 — Modelo `Journey` partilhado (neural_hive_domain)

- [ ] 1. Enum `Journey` + `JourneyDecision`
  - **DoR:** ADR-0011 como referência; acesso a `libraries/python/neural_hive_domain/`.
  - **DoD:** enum (J1-J4 + UNKNOWN) + `JourneyDecision` criados e exportados; testes unitários verdes.
  - **Evidência:** `sub-specs/fase0-evidence.md`.
  - [ ] 1.1 Escrever testes do modelo (`tests/test_journey.py`: valores do enum, defaults, UNKNOWN, `classification_method`)
  - [ ] 1.2 `libraries/python/neural_hive_domain/journey.py` (`Journey` StrEnum + `JourneyDecision` Pydantic)
  - [ ] 1.3 Exportar em `__init__.py`; verificar testes verdes

### Fase 1 — `JourneyClassifier` Tier 1 (sinais estruturados, sem LLM)

- [ ] 2. Classificação determinística por sinais + anti-verde-falso
  - **DoR:** Fase 0 fechada.
  - **DoD:** `JourneyClassifier.classify(intent_envelope, cognitive_plan)` resolve J1-J4 por sinais (source→J4, execution_mode→J1, workflow_type→J2/J3) sem LLM; sinal ausente/ambíguo → marca para Tier 2; baixa confiança → UNKNOWN. Testes verdes.
  - **Evidência:** `sub-specs/fase1-evidence.md`.
  - [ ] 2.1 Escrever testes Tier 1 (cada sinal → jornada; `classification_method="structured_signal"`; sem invocar LLM; UNKNOWN em sinal ausente quando LLM desabilitado)
  - [ ] 2.2 `services/semantic-translation-engine/src/services/journey_classifier.py` — Tier 1 + `journey_id` (UUID) + threshold configurável
  - [ ] 2.3 Verificar testes verdes; Tier 1 não chama o LLM

### Fase 2 — `JourneyClassifier` Tier 2 (LLM semântico)

- [ ] 3. Classificação por LLM nos casos ambíguos + fallback
  - **DoR:** Fase 1 fechada; `neural_hive_llm` disponível.
  - **DoD:** quando Tier 1 não dá sinal forte, invoca `neural_hive_llm` (prompt estruturado → journey+confidence+reasoning); falha/timeout do LLM → degrada para melhor sinal Tier 1 ou UNKNOWN; baixa confiança → UNKNOWN. Testes (LLM mockado) verdes.
  - **Evidência:** `sub-specs/fase2-evidence.md`.
  - [ ] 3.1 Escrever testes Tier 2 (LLM mockado → Journey+confidence+reasoning, `classification_method="llm"`; LLM falha → fallback; confidence<threshold → UNKNOWN)
  - [ ] 3.2 Integrar `neural_hive_llm` (circuit breaker) no classifier; prompt estruturado; parsing defensivo da resposta
  - [ ] 3.3 Verificar testes verdes

### Fase 3 — Propagação no plano + roteamento por jornada

- [ ] 4. STE grava journey; decision_consumer roteia por journey; journey_id flui
  - **DoR:** Fase 2 fechada.
  - **DoD:** `cognitive_plan` ganha `journey`/`journey_id`/`journey_confidence`/`journey_reasoning`/`journey_classification_method`; STE chama o classifier e grava; `decision_consumer` roteia por `journey` (não re-deriva); `journey_id` propaga até ao `ExecutionFeedback`. E2E A→C6 verde com journey_id preenchido.
  - **Evidência:** `sub-specs/fase3-evidence.md`.
  - [ ] 4.1 Escrever testes (cognitive_plan com campos journey; STE invoca classifier e grava; decision_consumer roteia J3→fluxo_g / J2/J4→orchestration-cutover / J1→plan-only)
  - [ ] 4.2 Adicionar campos journey ao `models/cognitive_plan.py` (opcionais, default — compat Avro) + gravação no `orchestrator.py`
  - [ ] 4.3 `decision_consumer` roteia por `journey`; injeta `journey_id` nos tickets/`execution.tickets`
  - [ ] 4.4 Gate E2E A→C6: `cognitive_plan.journey` preenchido e `ExecutionFeedback.journey_id` herdado (não None) em `neural_hive_orchestration`

### Fase 4 — Marcador de ingestão (J4) + métricas por jornada

- [ ] 5. Sinal de ingestão para J4 + observabilidade por jornada
  - **DoR:** Fase 3 fechada.
  - **DoD:** `doc-ingestion` marca `context.source="doc-ingestion"` → J4_MIGRATE pelo Tier 1; métricas-chave ganham label `journey`; loop LEARN segmentável por jornada.
  - **Evidência:** `sub-specs/fase4-evidence.md`.
  - [ ] 5.1 `doc-ingestion/src/services/gateway_client.py`: definir `context.source="doc-ingestion"` na intenção; teste de que uma intenção de ingestão → J4_MIGRATE
  - [ ] 5.2 Adicionar label `journey` às métricas-chave em `neural_hive_observability` (+ pontos de emissão no orchestrator)
  - [ ] 5.3 Verificar: intenção doc-ingestion → J4; métricas com label journey (E2E/coleção)
