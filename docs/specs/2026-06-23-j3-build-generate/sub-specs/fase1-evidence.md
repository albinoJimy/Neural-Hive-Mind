# Fase 1 — Roteamento J3 → FluxoGWorkflow fiável (Evidência)

> Spec: Endurecer J3/BUILD (capacidade GENERATE) — pré-condição ADR-0011
> Task 2 — Garantir que J3_BUILD inicia o FluxoGWorkflow (direto e pós-aprovação)
> Data: 2026-06-24 · Branch: `feat/convergencia-dbs` · Cluster: `neural-hive`

## Resumo

O break-point fixado na Fase 0 (`main.py:3378`, endpoint `/api/v1/workflows/start` — resume
pós-aprovação chamado pelo `FlowCOrchestrator`) hardcodeava `OrchestrationWorkflow.run`. Foi
corrigido para selecionar o workflow **por journey**, espelhando o caminho direto
(`decision_consumer`), preservando o fallback por `workflow_type` para planos sem journey.

## Correção (Scope 1 / Subtask 2.2)

- `services/orchestrator-dynamic/src/main.py` (endpoint `start_workflow`): extrai `journey` do
  `cognitive_plan` e seleciona via `_select_workflow_class_by_journey` (reutiliza
  `decision_consumer`). Contrato:
  - `J3_BUILD` → `FluxoGWorkflow`
  - `J2_ORCHESTRATE` / `J4_MIGRATE` → `OrchestrationWorkflow`
  - `J1_PLAN_ONLY` → **sem execução** (não inicia workflow; anti-verde-falso)
  - sem journey / `UNKNOWN` → fallback por `workflow_type` (retrocompat)
- Removido o import órfão `OrchestrationWorkflow` (passou a ser resolvido por classe selecionada).
- **Porquê elimina tickets parasitas:** os tickets são gerados **pelo workflow** (a activity
  `generate_execution_tickets` da `OrchestrationWorkflow`), não diretamente pelo `flow_c`. Como o
  `FluxoGWorkflow` não itera `cognitive_plan.tasks` (G1-G13 próprios), arrancar FluxoG para J3
  remove a origem dos tickets `query/transform/validate` parasitas.

## Testes (Subtask 2.1) — TDD

Ficheiro novo `services/orchestrator-dynamic/tests/unit/test_workflow_start_journey_routing.py`
(8 testes; não modifica testes existentes):
- `J3_BUILD` → FluxoGWorkflow (+ variante minúscula `j3_build`)
- `J2_ORCHESTRATE` / `J4_MIGRATE` → OrchestrationWorkflow
- `J1_PLAN_ONLY` → não inicia workflow, `status != "started"`
- sem journey → fallback OrchestrationWorkflow · `UNKNOWN` explícita → fallback · `workflow_type=generation` → FluxoG

RED→GREEN provado: com o código antigo 4 testes falhavam (J3, J3 minúscula, J1, generation-fallback);
após a correção **8/8 verdes**, regressão `test_workflow_start_endpoint.py` + routing do consumer
**52/52 verdes**. `black -l 100` limpo; `ruff` sem erros novos (I001 reduziu 4→1 ao remover o import órfão).

## Gate de cluster (Subtask 2.3) — EVIDÊNCIA REAL

Deploy: imagem `ghcr.io/albinojimy/neural-hive-mind/orchestrator-dynamic:ee14f1a` (commit `ee14f1a7`),
publicada via `workflow_dispatch` (build de PR não publica por política de segurança) e aplicada com
`kubectl set image` + `rollout restart`. Pods `ee14f1a` `Running 2/2`.

Chamada real ao endpoint deployado (de dentro do pod, como faz o `OrchestratorClient`):

| Plano | Resposta HTTP | Log do orchestrator | Temporal |
|---|---|---|---|
| `journey=J3_BUILD` | `200 {"status":"started"}` | `workflow_start_attempt … routing_basis=journey workflow_class=FluxoGWorkflow` + `workflow_started … workflow_class=FluxoGWorkflow` | **`workflow_type = FluxoGWorkflow`** (status RUNNING) |
| `journey=J1_PLAN_ONLY` | `200 {"status":"skipped_plan_only"}` | `workflow_start_skipped_plan_only journey=J1_PLAN_ONLY` | nenhum workflow iniciado |

Logs (excerto real, plano `f1gate-j3-1782317769`):
```
workflow_start_attempt   journey=J3_BUILD routing_basis=journey workflow_class=FluxoGWorkflow workflow_id=orch-flow-c-f1gate-j3-1782317769
workflow_started         workflow_class=FluxoGWorkflow workflow_id=orch-flow-c-f1gate-j3-1782317769
workflow_start_skipped_plan_only  journey=J1_PLAN_ONLY plan_id=f1gate-j1-1782317769
```
Prova Temporal (describe direto): `TEMPORAL workflow_type = FluxoGWorkflow | status = RUNNING`.

**Zero tickets parasitas:** `neural_hive_orchestration.execution_tickets` para `plan_id=f1gate-j3-…`
→ `count = 0` (FluxoG não gera tickets `query/transform/validate`).

Cleanup: o workflow de teste foi terminado (falharia em G6 — as activities G6-G13 não estão
registadas neste branch, achado da Fase 0; é a pré-condição da Fase 3, **não** afeta a prova de routing).

## Veredicto

DoD da Task 2 satisfeita e provada em cluster: plano J3_BUILD (caminho de resume pós-aprovação)
**inicia FluxoGWorkflow** (não OrchestrationWorkflow), **sem tickets parasitas**, com fallback por
`workflow_type` preservado. Gate de cluster (2.3) **PASSADO**.

## Notas / limites
- Deploy do gate é imperativo (`kubectl set image`); o `helm upgrade` legítimo deve seguir-se ao
  merge (values têm tag `latest`). O código já está committado/pushed (`ee14f1a7`).
- Validou-se o endpoint de resume diretamente (caminho do defeito). O E2E completo
  (gateway→STE→consensus→aprovação→resume) fica coberto pelo gate E2E da Fase 5.
