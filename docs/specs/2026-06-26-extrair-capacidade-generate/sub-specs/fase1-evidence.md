# Fase 1 — GenerateCapability (Evidência)

> Spec: Extrair GENERATE como capacidade autónoma (multi-linguagem-ready)
> Task 2 — Adaptador fino capacidade → FluxoGWorkflow (`start` durável + `map_result` puro)
> Data: 2026-06-26 · Branch: `feat/convergencia-dbs` · Serviço: `orchestrator-dynamic`

## Estado: COMPLETA — fronteira da capacidade GENERATE, 38 testes verdes

Pipeline: dev (TDD) → auditoria qualidade → auditoria completude → remediação dirigida.
Task aditiva e isolada: **não** toca `decision_consumer.py` (Task 3) nem `fluxo_g_workflow.py`.
Evidência unit-level (sem gate de cluster — paridade E2E é a Fase 4).

## Entregáveis

- `src/capabilities/generate/capability.py` — `GenerateHandle` (workflow_id, journey) e
  `GenerateCapability`:
  - `async start(GenerateRequest) -> GenerateHandle`: resolve a estratégia (fail-closed: stack
    desconhecida → `UnsupportedStackError` **sem iniciar** o workflow), enriquece `parameters` com a
    estratégia e **inicia** o `FluxoGWorkflow` via `temporal_client.start_workflow(FluxoGWorkflow.run,
    input_data, id=f"{prefix}{plan_id}", task_queue=...)`. **Start durável** — sem await do resultado.
  - `@staticmethod map_result(workflow_output, journey) -> GenerateResult`: função pura fail-closed.
- `src/capabilities/generate/__init__.py` — re-exporta `GenerateCapability`/`GenerateHandle`.
- `tests/unit/capabilities/test_generate_capability.py` — 13 testes (cliente Temporal mockado).

## Anti-verde-falso (núcleo) — provado por teste

- `map_result`: `status != "completed"` → failed; sem `code_generation.artifact_id` → failed;
  `deployment.status != "deployed"` → failed; **`deployment.verified != True` → failed**
  (endurecido na remediação: rollout pronto mas healthcheck não confirmado NÃO é sucesso — a
  capacidade é mais estrita que o FluxoGWorkflow, que é leniente).
- `start`: estratégia resolvida **antes** de iniciar → stack desconhecida nunca inicia workflow
  (`start_workflow.assert_not_called()`).

## Fidelidade ao caminho legado (remediação das auditorias)

- **ALTO (gate verified):** `map_result` passou a exigir `deployment.verified is True` para
  `completed` (GEN-US4 healthcheck-200; Scope 5 "qualquer G-step falhado → failed"). + 2 testes.
- **MÉDIO (multi-linguagem):** `start` propaga a estratégia **completa**
  (`template_ref`/`builder`/`health_path`/`container_port`) para `parameters`, não só
  `language`/`framework` — registar uma stack nova passa a governar o que é construído/deployado. + teste.
- **MÉDIO (datetime):** `start` normaliza datetimes (`json.dumps(default=...)`) tal como o
  `decision_consumer` faz antes do `start_workflow` (planos do STE contêm datetime). + teste.
- Não-mutação do `request.cognitive_plan` (cópia, não referência) — provado por teste.

## DoD confirmado

- Start durável **sem await bloqueante** do resultado; **não reimplementa G1–G8** (delega no
  `FluxoGWorkflow.run`).
- `decision_consumer.py` e `fluxo_g_workflow.py` **intactos** (git status) — des-vazar a fronteira
  é a Task 3.
- Fidelidade de assinatura/shape ao real: `start_workflow(workflow, arg, *, id, task_queue)` e
  `input_data={consolidated_decision, cognitive_plan, is_direct_plan}` confirmados.

## Verificação
- `python3 -m pytest tests/unit/capabilities/ -q` → **38 passed** (13 capability + 16 contrato + 9 stacks; Task 1 sem regressão).
- `black -l 100 --check` limpo · `ruff check --select F,E9` sem erros · mypy `capability.py` sem erros.
