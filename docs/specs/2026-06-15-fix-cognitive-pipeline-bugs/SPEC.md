# Spec: FIX-CP-001 — Correção de Bugs do Cognitive Pipeline (Consensus)

**Epic:** Estabilização do Cognitive Pipeline (Fluxo A→C6)
**Data:** 2026-06-15
**Prioridade:** P1 (Crítico — bloqueia decisões de consenso com qualidade)
**Branch:** fix/e2e-cognitive-pipeline-bugs
**Estimativa:** 1-2 dias

---

## 1. Objetivo

Corrigir três bugs de código identificados por análise de causa-raiz durante a validação E2E do pipeline cognitivo, que degradam a qualidade das decisões de consenso e bloqueiam o processamento fiável de planos:

1. Especialistas a operar sempre em fallback heurístico (modelos ML nunca carregam).
2. Consumer Kafka do `consensus-engine` que fica preso (idle-com-lag) em loop de backoff.
3. Falha de comparação de datetimes no fallback MongoDB das feromonas.

---

## 2. Status Atual

**Validado a funcionar:** Fluxo A→C6 end-to-end (Gateway→STE→Consensus→Approval→Orchestrator→Workers), provado com o plano `20249596` (aprovação HTTP 200, workers QUERY/VALIDATE/TRANSFORM COMPLETED).

**Já corrigido em runtime (fora desta spec):** `otel_pipeline` (health check), `KAFKA_BOOTSTRAP_SERVERS` em 2 ConfigMaps.

**Bloqueios remanescentes (esta spec):** os 3 bugs abaixo, que fazem o consenso decidir sempre `review_required` por degradação e travam o consumer sob falha de dependências.

---

## 3. Problemas e Correções

### 3.1 BUG-1 — Especialistas em modo degradado (MLflow model name mismatch)

**Causa-raiz:** os serviços procuram `models:/<tipo>-evaluator/Production` (`services/specialist-*/src/config.py:21`), mas os scripts de treino registam os modelos com nomes PascalCase (`ml_pipelines/training/train_technical_specialist.py:170` → `"TechnicalSpecialistModel"`). O URI não existe → `base_specialist.py:543` devolve `None` → fallback semântico (`base_specialist.py:1557-1586`, confidence×0.8≈0.096, `model_source=semantic_pipeline`). `consensus-engine/src/services/compliance_fallback.py:62-66` marca 5/5 degraded → decisão sempre `review_required`. (`business` funciona: registado como `business-evaluator`.)

**Correção:** alinhar os nomes de registo com o que os serviços esperam (`*-evaluator`) em `ml_pipelines/training/train_all_specialist_models.py` (linhas 31,37,43,49,55) e nos `train_{tipo}_specialist.py` (default `--model-name`). Re-registo/re-treino dos modelos (operacional). Sem alteração no código dos serviços.

### 3.2 BUG-2 — Consumer do consensus preso em loop de backoff (idle-com-lag)

**Causa-raiz:** `services/consensus-engine/src/consumers/plan_consumer.py` — quando um plano falha e entra em backoff, `_process_message_with_retry` lança `Exception("Backoff em andamento")` (~L880); o loop principal (~L225-286) **não** a classifica como sistémica (`_is_systemic_error` ~L326-370), por isso **não dorme, não faz commit e não solta a mensagem** → re-`poll` do mesmo offset em tight-loop; o offset nunca avança. Estado de backoff em dict local perde-se em rebalance do HPA.

**Correção:** tratar a condição de backoff explicitamente no loop — aplicar `asyncio.sleep` pelo tempo de backoff restante (com cap) e `continue` sem incrementar erros consecutivos; idealmente pausar a partição (`consumer.pause`) durante o backoff. Reduzir risco de rebalance: HPA do consensus a 1 réplica enquanto `plans.ready` tiver 1 partição (ou aumentar partições).

### 3.3 BUG-3 — Falha de datetime no fallback MongoDB das feromonas

**Causa-raiz (2 sub-bugs, acionados sob Redis CLUSTERDOWN):**
- (A) `services/consensus-engine/src/clients/mongodb_client.py:35` cria `AsyncIOMotorClient` sem `tz_aware=True` → Motor devolve datetimes *naive* → `naive < aware` em `fallback_storage.py:441` (e 416, 568).
- (B) `services/consensus-engine/src/clients/pheromone_client.py:291` usa `model_dump(mode="json")` → grava `expires_at` como **string ISO** → `str < datetime` em `pheromone_client.py:372`.

**Correção:** (A) adicionar `tz_aware=True` ao construtor do Motor. (B) usar `model_dump(mode="python")` ao gravar o sinal, mantendo `datetime` nativo (BSON Date). Garantir normalização tz-aware na leitura.

---

## 4. Out of Scope (infra/ops — tratar separadamente)

- Redis Cluster `CLUSTERDOWN` (slots não servidos; usa TLS).
- Tópicos Kafka duplicados (`plans.ready`/`plans-ready`) e partição única do `plans.ready`.
- Helm release `gateway-intencoes` preso em `pending-upgrade`.
- Node `vmi3075398` sem rede ao GHCR; over-commit de memória.

---

## 5. Tarefas (TDD)

- [x] 1. **BUG-3 (datetime)** — fix mais barato e isolado
  - [x] 1.1 Teste unitário: normalização tz (`test_pheromone_fallback_datetime.py`, 8 testes)
  - [x] 1.2 `mongodb_client.py`: `tz_aware=True`
  - [x] 1.3 `pheromone_client.py`: `model_dump(mode="python")` + helper `_to_aware_datetime` na leitura
  - [x] 1.4 Testes passam
- [x] 2. **BUG-2 (consumer backoff)**
  - [x] 2.1 Teste unitário: `_extract_backoff_seconds` (`test_plan_consumer_backoff.py`, 5 testes)
  - [x] 2.2 `plan_consumer.py`: dormir o backoff na rama de erro de negócio (quebra tight-loop)
  - [x] 2.3 Testes passam
- [x] 3. **BUG-1 (MLflow names)**
  - [x] 3.1 Corrigidos nomes em `train_all_specialist_models.py` (+ passa `--model-name`) e defaults dos `train_{tipo}_specialist.py`
  - [ ] 3.2 (Operacional — pendente) re-registar/re-treinar os modelos `*-evaluator/Production` no MLflow
  - [ ] 3.3 (Operacional — pendente) validar em runtime: `model_source=ml_model` nos logs do consensus
- [x] 4. Lint (black ok; ruff só avisos estilísticos pré-existentes) + testes afetados verdes (44 + 13 novos)

---

## 6. Critérios de Aceitação

1. `consensus-engine` lê sinais de feromona do fallback MongoDB sem `TypeError` (BUG-3).
2. Consumer do consensus não fica preso com lag residual sob falha de um plano; offset avança (BUG-2).
3. Especialistas reportam `model_source=ml_model` e o consenso deixa de ser forçado a `review_required` por degradação (BUG-1).
4. Testes unitários novos verdes; sem regressões na suíte do `consensus-engine`.
