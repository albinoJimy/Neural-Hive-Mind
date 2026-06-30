# Fase 0 — Diagnóstico instrumentado (Evidência)

> Spec: Endurecer J3/BUILD (capacidade GENERATE) — pré-condição ADR-0011
> Task 1 — Fixar os break-points reais de J3_BUILD num run de cluster
> Data: 2026-06-24 · Branch: `feat/convergencia-dbs` · Cluster: `neural-hive` (K8s 1.29.15)

## DoR (Definition of Ready)

- **journey-router fechado:** ✓ gate E2E PASSADO 2026-06-23 (commit `6768d914`, ver `proj_journey_router_gate_e2e_2026-06-23`).
- **cluster acessível:** ✓ pods relevantes `Running 2/2`: `orchestrator-dynamic` (×3), `code-forge`, `worker-agents` (×2), `consensus-engine`, `gateway-intencoes`.

## Método

Diagnóstico estático (leitura de código, `file:line`) + dinâmico (logs de cluster, MongoDB `neural_hive_orchestration` via `kubectl exec`, `pip`/`env` nos pods). Cada afirmação é classificada **CÓDIGO** (`file:line` no branch atual) ou **CLUSTER** (comando + saída real). O que não foi possível provar está marcado **não provado**.

---

## 1.1 Routing J3 (direto vs pós-aprovação)

### CÓDIGO
- **Caminho DIRETO (plano sem aprovação) — CORRETO.** `services/orchestrator-dynamic/src/consumers/decision_consumer.py:814` extrai `journey`; `:832` `_select_workflow_class_by_journey(journey)` → `J3_BUILD → FluxoGWorkflow` (def em `:223-241`); `:853-858` arranca `workflow_class.run`. Fallback por `workflow_type` preservado para journey ausente/UNKNOWN (`:834-837`).
- **Caminho PÓS-APROVAÇÃO — QUEBRADO (break-point central).** O resume não honra a journey:
  1. `services/orchestrator-dynamic/src/integration/flow_c_consumer.py:785` → `self.orchestrator.resume_flow_c_after_approval(approval_response)`. O parse (`:751-773`) extrai `cognitive_plan` mas **nunca lê `journey`**.
  2. `libraries/neural_hive_integration/.../orchestration/flow_c_orchestrator.py` `resume_flow_c_after_approval` (~`:1769-1966`) constrói `consolidated_decision` e chama `execute_flow_c` (~`:1965`) — **`journey` não é referida em lado nenhum** deste caminho.
  3. `libraries/neural_hive_integration/.../clients/orchestrator_client.py:68-114` `start_workflow()` faz `POST /api/v1/workflows/start` **sem `journey`**.
  4. **BREAK-POINT:** `services/orchestrator-dynamic/src/main.py:3378` — o endpoint `/api/v1/workflows/start` hardcodeia `OrchestrationWorkflow.run`, ignorando a journey. (verificado diretamente)

### CLUSTER
- `flow_c_executions` (coleção de tracking do resume) = **0** documentos (`neural_hive_orchestration`).
- Não foi possível capturar o log `Iniciando workflow … workflow_class=` do run do gate J3 (2026-06-23 ~16-18h): pods do `orchestrator-dynamic` têm 21h, logs anteriores rotados. → **não provado por log direto**, mas a cadeia de código é conclusiva e corroborada por 1.2/1.3 (geração de tickets genéricos = OrchestrationWorkflow, não FluxoG).

### VEREDICTO
O routing por journey **só existe no caminho direto**. Para planos `review_required` (que é o caso normal de J3), o resume pós-aprovação cai **sempre** em `OrchestrationWorkflow` por causa do hardcode em `main.py:3378`. **Fase 1** tem de propagar `journey` pela cadeia resume e selecionar o workflow por journey (mover a decisão para `resume_flow_c_after_approval`/`execute_flow_c`, ou propagar `journey` por `OrchestratorClient.start_workflow` → endpoint e aplicar `_select_workflow_class_by_journey` em `main.py:3377`).

---

## 1.2 STE: tarefas genéricas parasitas em J3?

### CÓDIGO
- STE **não tem template de geração**: `services/semantic-translation-engine/src/services/decomposition_templates.py` cobre VIABILITY/MIGRATION/FEATURE/INFRA/GENERIC — sem GENERATION. Intenções de geração caem no genérico → tasks `query/transform/validate` (`services/semantic-translation-engine/src/services/dag_generator.py`).
- `services/orchestrator-dynamic/src/workflows/fluxo_g_workflow.py` **não itera `cognitive_plan.tasks`** — executa G1-G13 hardcoded (`:123-431`). Logo, quando o FluxoG corre, as tasks genéricas do STE são **ignoradas**.

### CLUSTER
- `execution_tickets` dominado por tasks genéricas (ver 1.3): `query`, `transform`, `validate` — **nenhum `BUILD`/`DEPLOY`**.
- `code_artifacts` = **1** documento → a geração nunca produziu artefactos de código reais.

### VEREDICTO
As tasks genéricas **só são "parasitas" no estado atual quebrado**: como o FluxoG não arranca (1.1), corre a `OrchestrationWorkflow`, que **gera e publica** os tickets `query/transform/validate` — que depois inundam o DLQ do code-forge (1.3). **Não bloqueia J3 estruturalmente:** assim que a Fase 1 fizer o FluxoG arrancar, essas tasks são ignoradas. **Confirma o Out-of-Scope:** refactor da decomposição do STE fica fora desta spec.

---

## 1.3 Contrato code-forge: tópico/grupo + caminho do erro de desserialização

### CÓDIGO / CLUSTER (config)
- **Tópico partilhado** `execution.tickets`; grupos distintos. Cluster (`env` do pod code-forge): `KAFKA_TICKETS_TOPIC=execution.tickets`, `KAFKA_CONSUMER_GROUP_ID=code-forge`. Worker usa grupo `worker-agents`.

### Comparação de contrato (`task_type` / `priority`)

| Campo | Produtor (orchestrator `ticket_generation`) | worker-agents | code-forge |
|---|---|---|---|
| `task_type` | emite **ambos os casos** (legado minúsculas + canónico maiúsculas) — `services/orchestrator-dynamic/src/models/execution_ticket.py` tem enum maiúsculas **e** valores legados `query/transform/validate` | StrEnum maiúsculas + **normaliza** `.upper()` no consumer (`kafka_ticket_consumer.py:166-179`), mas **falta `TRANSFORM`** no enum (`src/models/execution_ticket.py`) e **não trata `priority` int** | Enum estrito maiúsculas (`src/models/execution_ticket.py:8-18`); **sem normalização** |
| `priority` | `normalize_priority()` mapeia int→enum no produtor, mas tickets legados em voo têm `priority=5` (int) | enum string | enum string estrito |

- **BREAK-POINT code-forge:** `services/code-forge/src/clients/kafka_ticket_consumer.py:73` `ExecutionTicket(**data)` (Pydantic v2). Enums estritos → `ValidationError` para `task_type` minúsculo ou `priority` int → capturado em `:91-97` (`message_deserialization_error`) → enviado para DLQ.

### CLUSTER (prova de erro real)
Dezenas de erros reais (2026-06-23, offsets 879-908), p.ex.:
```
message_deserialization_error  offset=879
  2 validation errors for ExecutionTicket
  task_type: Input should be 'BUILD'|...|'TRANSFORM' [input_value='transform']
  priority:  Input should be 'LOW'|'NORMAL'|'HIGH'|'CRITICAL' [input_value=5, input_type=int]
→ message_sent_to_dlq  offset=879
```
Distribuição completa em `execution_tickets` (**1352 docs**, soma confere) prova os **dois casos a coexistir**: `query` 394 / `QUERY` 154 · `validate` 185 / `VALIDATE` 133 · `transform` 181 / `TRANSFORM` 48 · `EXECUTE` 256 · `create` 1. Zero `BUILD`/`DEPLOY`.

### VEREDICTO
Confirma o defeito da spec. **Fase 2** precisa de: (a) desserializador **tolerante** no code-forge (`task_type.upper()` + `normalize_priority` int→enum) antes de `ExecutionTicket(**data)`; (b) adicionar `TRANSFORM` ao enum do worker e tratar `priority` int no worker; (c) produtor a emitir **só** canónico. Nota: a hipótese "produtor nunca emite minúsculas" é **falsa** — o cluster prova minúsculas+int em voo.

---

## 1.4 Deps code-forge + bugs críticos pré-existentes + activities G6-G13

### Activities G6-G13 — **CRÍTICO (não registadas neste branch)**
- `services/orchestrator-dynamic/src/workflows/fluxo_g_workflow.py:20-27` importa e chama `generate_code` (`:249-250`), `build_package` (`:276-277`), `deploy_software` (`:313-314`), `verify_deployment` (`:324-325`) e mais (G9-G13, `:346-417`).
- **MAS** `services/orchestrator-dynamic/src/workers/temporal_worker.py:465-497` regista apenas **5** Fluxo G activities (G1-G5): `generate_requirements, generate_documentation, update_knowledge_graph, request_approval, query_knowledge_graph`. `generate_code/build_package/deploy_software/verify_deployment` **não são importadas nem registadas**.
- **CLUSTER confirma:** log `Fluxo G workflow e atividades registradas no Worker activities_count=5 workflow=FluxoGWorkflow`.
- **Causa-raiz:** o commit `2d945153` ("wiring do Fluxo G — registar G6-G13 + persistir code_artifact_id (CR Task 5)") **NÃO é ancestral de HEAD** em `feat/convergencia-dbs` (`git merge-base --is-ancestor 2d945153 HEAD` → falso). O wiring existe noutro branch e **não foi mergeado** aqui.
- **Implicação:** um run J3 real que chegue a G6 falha com `ActivityNotRegisteredError`. As Fases 3/4/5 **dependem** de re-fazer/portar este wiring primeiro.

### Deps GitPython / kubernetes
| Dep | Declarada (requirements/pyproject) | Instalada no pod | Importa OK |
|---|---|---|---|
| GitPython | **não** (grep vazio em `services/code-forge/requirements*.txt`/`pyproject.toml`) | `git 3.1.43` | ✓ |
| kubernetes | **não** | `kubernetes 28.1.0` | ✓ |

→ **Drift código↔imagem:** funcionam no pod atual mas não estão declaradas; um rebuild limpo pode partir. Corrigir na Fase 4 (declarar deps).

### Bugs pré-existentes
- **Bug #1 (elif "Failed" duplicado): PRESENTE.** `services/code-forge/src/services/container_builder.py:1117` **e** `:1126` — dois `elif phase == "Failed":`. Corrigir na Fase 4 (build).
- **Bug #2 (`await` em falta): aparentemente corrigido** (reportado pelo agente de investigação; confirmar pontualmente na Fase 4).
- **Bug colateral `_http_client=None`: mitigado neste branch** — CLUSTER: log `HTTP client injetado para Fluxo G activities` no arranque do worker.

### code-forge pod
- CLUSTER: `code-forge-6f4f47987b-5wkx4` `Running 2/2`, ~3d, **0 restarts**. A descrição antiga "0/0 161d" **já não se aplica** (pod vivo e saudável).

---

## Mapa de break-points (resumo) e reordenação das fases

| # | Break-point | `file:line` | Prova cluster |
|---|---|---|---|
| 1.1 | Resume pós-aprovação hardcodeia `OrchestrationWorkflow` | `services/orchestrator-dynamic/src/main.py:3378` | `flow_c_executions=0`; tickets genéricos (indireto) |
| 1.2 | STE sem template de geração → tasks genéricas (ignoradas pelo FluxoG) | `decomposition_templates.py` / `fluxo_g_workflow.py:123-431` | `code_artifacts=1`; sem `BUILD`/`DEPLOY` |
| 1.3 | code-forge rejeita ticket (enum estrito) | `services/code-forge/src/clients/kafka_ticket_consumer.py:73` + `models/execution_ticket.py:8-18` | `message_deserialization_error` ×N + DLQ; casos mistos em `execution_tickets` |
| 1.4a | G6-G13 não registadas no worker (commit `2d945153` ausente do branch) | `services/orchestrator-dynamic/src/workers/temporal_worker.py:465-497` | `activities_count=5` |
| 1.4b | Deps GitPython/kubernetes não declaradas | `services/code-forge/requirements*.txt` (ausentes) | pod tem git 3.1.43 / k8s 28.1.0 |
| 1.4c | Bug `elif "Failed"` duplicado | `services/code-forge/src/services/container_builder.py:1117,1126` | — |

### Reordenação/redução das fases seguintes (DoD da Task 1)
- **Fase 1 (routing):** alvo confirmado = `main.py:3377-3382` + propagação de `journey` por toda a cadeia resume (`flow_c_consumer` → `flow_c_orchestrator.resume_flow_c_after_approval` → `OrchestratorClient.start_workflow` → endpoint). **Inalterada em escopo.**
- **Fase 2 (contrato):** alvo confirmado e cluster-provado. Acrescentar ao escopo: **`TRANSFORM` em falta no enum do worker** e tratamento de `priority` int no worker (além do desserializador tolerante do code-forge). **Ligeiramente expandida.**
- **NOVA pré-condição da Fase 3:** **portar o wiring G6-G13** (equivalente ao commit `2d945153`) para este branch — registar `generate_code/build_package/deploy_software/verify_deployment/...` em `temporal_worker.py` e confirmar `activities_count` ≥ 13. **Sem isto, Fases 3/4/5 não correm.** Recomenda-se tratá-lo como Task 4.0 (primeiro subtask da Fase 3).
- **Fase 4 (build):** acrescentar correção do **bug #1 (`elif "Failed"` duplicado)** e **declarar deps GitPython/kubernetes**. **Ligeiramente expandida.**
- **STE/decomposição:** mantém-se **Out-of-Scope** (não bloqueia J3 uma vez corrigido o routing).

### Honestidade / limites
- Não foi possível capturar o log de routing do run do gate (logs rotados) nem provar via Temporal qual workflow arrancou nesse run específico → **não provado por log direto**, mas conclusivo por código + evidência indireta (tickets genéricos + `code_artifacts=1`).
- Bug #2 (`await`) e o estado fino do `_http_client` reportados por agente de investigação; reconfirmar na Fase 4.
