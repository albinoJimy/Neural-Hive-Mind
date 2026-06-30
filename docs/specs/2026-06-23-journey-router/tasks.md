# Spec Tasks

> Passo 2 do ADR-0011 (Roteamento). Ordenação: Fase 0 (modelo partilhado) → Fase 1 (classifier Tier 1) → Fase 2 (classifier Tier 2/LLM) → Fase 3 (propagação + roteamento) → Fase 4 (ingestão + métricas). Cada fase é um gate: só avança com testes verdes + evidência.
>
> **Princípio:** decidir cedo (STE), propagar; sinais estruturados primeiro, LLM só nos ambíguos; anti-verde-falso (confidence/reasoning/UNKNOWN). TDD obrigatório. Detalhe em `sub-specs/technical-spec.md`.

## Tasks

### Fase 0 — Modelo `Journey` partilhado (neural_hive_domain)

- [x] 1. Enum `Journey` + `JourneyDecision` (pipeline: dev→auditorias→remediação)
  - **DoR:** ADR-0011 como referência; acesso a `libraries/python/neural_hive_domain/`.
  - **DoD:** enum (J1-J4 + UNKNOWN) + `JourneyDecision` criados e exportados; testes unitários verdes.
  - **Evidência:** `sub-specs/fase0-evidence.md` (17 testes; auditorias qualidade+completude → remediação: confidence [0,1], classification_method Literal, use_enum_values).
  - [x] 1.1 `tests/test_journey.py` (17 testes: enum, UNKNOWN, serialização, validação + negativos confidence/classification_method)
  - [x] 1.2 `journey.py` — `Journey(str, Enum)` (compat py3.10, espelha UnifiedDomain) + `JourneyDecision` (Field ge/le, Literal, use_enum_values)
  - [x] 1.3 Exportado em `__init__.py`; 17/17 + 148 suite verdes, sem regressões

### Fase 1 — `JourneyClassifier` Tier 1 (sinais estruturados, sem LLM)

- [x] 2. Classificação determinística por sinais + anti-verde-falso (pipeline: dev→auditorias→remediação)
  - **DoR:** Fase 0 fechada.
  - **DoD:** `JourneyClassifier.classify(intent_envelope, cognitive_plan)` resolve J1-J4 por sinais (source→J4, execution_mode→J1, workflow_type→J2/J3) sem LLM; sinal ausente → UNKNOWN; gancho Tier 2 não-ativo. Testes verdes.
  - **Evidência:** `sub-specs/fase1-evidence.md` (24 testes; auditorias → remediação: +4 testes de precedência/defensivo/enum + guarda real anti-LLM; descoberta workflow_type lowercase).
  - [x] 2.1 `tests/unit/test_journey_classifier.py` (24 testes: cada sinal, precedência total, defensivo, UNKNOWN, anti-LLM via mock)
  - [x] 2.2 `journey_classifier.py` — Tier 1 (precedência source>execution_mode>workflow_type, case-insensitive) + `journey_id` UUID + threshold via getattr
  - [x] 2.3 24/24 verdes; Tier 1 não chama o LLM (provado por mock call_count==0)

### Fase 2 — `JourneyClassifier` Tier 2 (LLM semântico)

- [x] 3. Classificação por LLM nos casos ambíguos + fallback (pipeline: dev→auditorias→remediação)
  - **DoR:** Fase 1 fechada; `neural_hive_llm` disponível.
  - **DoD:** quando Tier 1 não dá sinal forte, invoca `neural_hive_llm` (prompt estruturado → journey+confidence+reasoning); falha/timeout → UNKNOWN; baixa confiança → UNKNOWN. Testes (LLM mockado) verdes.
  - **Evidência:** `sub-specs/fase2-evidence.md` (40 testes; auditoria apanhou CRÍTICO sync-over-async → classify() tornado async; +regex lazy, +truncagem prompt, +testes).
  - [x] 3.1 Testes Tier 2 (LLM mockado: Journey+confidence+reasoning method="llm"; falha→fallback; confidence<threshold→UNKNOWN; malformado/vazio/bool/reasoning-ausente; prefácio-sufixo)
  - [x] 3.2 `neural_hive_llm` (LLMClient.generate, circuit breaker embutido) via DI; prompt estruturado (truncado, temp=0); parsing defensivo (_extract_json lazy)
  - [x] 3.3 40/40 verdes; **classify() async** (correção crítica); threshold no settings; Tier 1 preservado; sem regressões

### Fase 3 — Propagação no plano + roteamento por jornada

- [x] 4. STE grava journey; decision_consumer roteia por journey; journey_id flui (gate E2E PASSADO em cluster)
  - **DoR:** Fase 2 fechada.
  - **DoD:** `cognitive_plan` ganha os 5 campos journey; STE chama o classifier e grava; `decision_consumer` roteia por `journey` (não re-deriva); `journey_id` propaga até ao `ExecutionFeedback`. E2E A→C6 verde com journey_id preenchido.
  - **Evidência:** `sub-specs/fase3-evidence.md` (pipeline; auditoria apanhou CRÍTICO: drift schema Avro cognitive-plan → 5 campos adicionados aos 2 .avsc; +KeyError fix; ~68 testes journey verdes).
  - [x] 4.1 Testes por serviço (STE 11, orchestrator 16, worker 4; routing journey + fallback + propagação)
  - [x] 4.2 5 campos journey no `cognitive_plan.py` (opcionais, default) + `to_avro_dict` + **schemas Avro (2 .avsc)** + gravação no `orchestrator.py` (await classify, falha→UNKNOWN)
  - [x] 4.3 `decision_consumer` roteia por `journey` (J3→fluxo_g; J2/J4→orchestration; J1→plan-only) + fallback workflow_type; journey_id no ticket→result→feedback (6 call-sites + avsc)
  - [x] 4.4 Gate E2E A→C6 **PASSADO**: `cognitive_plan.journey` preenchido + `journey_id` herdado até aos `execution_tickets` em `neural_hive_orchestration` (8 tickets J4_MIGRATE COMPLETED, journey_id idêntico ao gerado no STE). Schema `plans.ready-value` auto-registado v2 (compat NONE)

### Fase 4 — Marcador de ingestão (J4) + métricas por jornada

- [x] 5. Sinal de ingestão para J4 + observabilidade por jornada (gate E2E PASSADO em cluster)
  - **DoR:** Fase 3 fechada.
  - **DoD:** `doc-ingestion` marca `context.source="doc-ingestion"` → J4_MIGRATE pelo Tier 1; métricas-chave ganham label `journey`; loop LEARN segmentável por jornada.
  - **Evidência:** `sub-specs/fase4-evidence.md` (pipeline; auditorias apanharam 2 CRÍTICOS: marcador J4 descartado gateway→STE + enum journey nunca chega ao execution.results → label sempre "unknown"; ambos remediados; 12 testes journey/source verdes).
  - [x] 5.1 `doc-ingestion` marca `context.source="doc-ingestion"` **e** marcador corrigido para atravessar gateway→STE (`IntentRequest.source` + `Context.source` + `to_avro_dict` + intent-envelope.avsc); teste de integração real (2)
  - [x] 5.2 Label `journey` nas métricas; enum `journey` propagado plano→ticket→result→consumer (execution-result.avsc + 10 testes) — métrica deixa de ser estruturalmente "unknown"; métricas órfãs do lib documentadas
  - [x] 5.3 Gate E2E **PASSADO em cluster**: intenção doc-ingestion real → `cognitive_ledger.journey==J4_MIGRATE` (structured_signal) + `consensus_decision.cognitive_plan.journey==J4_MIGRATE` (gap do consensus fechado por rebuild) + 8 `execution_tickets` (neural_hive_orchestration) `journey=J4_MIGRATE`+`journey_id` idêntico ao STE, todos COMPLETED + actual_duration. Counter Prometheus `{journey}` não incrementa (dualidade de consumers pré-existente, não bloqueia)
