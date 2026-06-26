# Technical Specification

This is the technical specification for the spec detailed in @docs/specs/2026-06-26-extrair-capacidade-generate/spec.md

## Estado atual (ponto de partida)

- `decision_consumer.py`: `_select_workflow_class_by_journey(journey)` mapeia `J3_BUILD →
  FluxoGWorkflow` e o handler inicia-o directamente (`temporal_client.start_workflow(workflow_class.run, input_data, …)`, ~linha 853). A fronteira está **vazada**: o routing conhece a classe do workflow.
- `fluxo_g_workflow.py`: `FluxoGWorkflow.run(input_data: dict)` orquestra G1–G8 e devolve um dict
  com `code_generation{artifact_id, language, framework, lines_of_code}`, `build{pipeline_id,
  image_tag, quality_score, test_pass_rate}`, `deployment{deployment_id, service_url, status,
  verified}`, `journey`, etc. (linhas ~500-536). O resultado **já carrega language/framework**.
- Activities G6/G7 chamam o code-forge; G8 chama o deploy-service. A stack (language/framework)
  já atravessa o payload — falta torná-la um eixo de seleção explícito e a fronteira da capacidade.

## Arquitetura-alvo

```
decision_consumer (routing por journey)
  → GenerateCapability.invoke(GenerateRequest)         [fronteira: não conhece FluxoGWorkflow]
        → StackRegistry.resolve(language, framework)   [estratégia: template + builder + health]
        → inicia FluxoGWorkflow (Temporal) com input enriquecido pela estratégia
        → mapeia resultado G1–G8 → GenerateResult (fail-closed)
  → GenerateResult { status, code_artifact_id, container_image_ref, deployment{…}, journey }
```

## Requisitos Técnicos

### Contrato (Scope 1) — `src/capabilities/generate/contract.py`
- `GenerateTarget`: `{ language: str, framework: str, options: dict = {} }` — **stack-neutro**
  (sem enum fechado a fastapi).
- `GenerateRequest`: `{ plan_id: str, journey: str, cognitive_plan: dict, target: GenerateTarget }`.
- `GenerateResult`: `{ status: Literal["completed","failed"], code_artifact_id: str | None,
  container_image_ref: str | None, deployment: { namespace, service_url, health } | None,
  journey: str, failure_reason: str | None }`.
- **Fail-closed**: qualquer G-step falhado / stack não suportada → `status="failed"` + `failure_reason`;
  nunca `completed` simulado. Modelos Pydantic, sem lógica de negócio.

### GenerateCapability (Scope 2) — `src/capabilities/generate/capability.py`
> **Mecânica async (importante):** o `decision_consumer` hoje **inicia** o `FluxoGWorkflow` e faz
> commit — **não bloqueia** à espera do resultado (Temporal corre o workflow de forma durável; o
> resultado é processado via signals/ExecutionResultConsumer). A capacidade respeita isto: a
> invocação é um **start durável**, e o **mapeamento de resultado é uma função pura** aplicada ao
> output do workflow quando este conclui. Não se introduz um await bloqueante no consumer (evita
> regressão).

- `async def start(request: GenerateRequest) -> GenerateHandle`: resolve a estratégia via
  `StackRegistry`, constrói o `input_data` do `FluxoGWorkflow` (a partir do `cognitive_plan` +
  parâmetros da estratégia: template/builder/health-path), e **inicia** o `FluxoGWorkflow` via o
  cliente Temporal injetado (mantém task_queue, id por plano, durabilidade/retry/saga). Devolve um
  `GenerateHandle { workflow_id, journey }`. Stack desconhecida → erro traduzido em FAILED (não
  inicia workflow).
- `map_result(workflow_output: dict) -> GenerateResult`: função **pura** que traduz
  `code_generation/build/deployment/journey` do output do `FluxoGWorkflow` para `GenerateResult`;
  workflow falhado / output incompleto → `failed` com razão. É o alvo do teste de contrato em bloco.
- A capacidade **não** reimplementa G1–G8; é um adaptador fino (start) + tradução de contrato
  (map_result). O `GenerateResult` é o contrato lógico in/out; a sua materialização segue a cadência
  durável do Temporal.

### Des-vazar o routing (Scope 3) — `decision_consumer.py`
- Substituir o uso directo de `FluxoGWorkflow`/`_select_workflow_class_by_journey` (para jornadas de
  geração) por uma decisão "esta jornada requer GENERATE → invocar `GenerateCapability`".
- Preservar: J1_PLAN_ONLY (não executa), J2/J4 → OrchestrationWorkflow, fallback por `workflow_type`
  quando journey ausente/UNKNOWN. A escolha "requer geração" deriva da jornada (J3_BUILD hoje), não
  de conhecer a classe do workflow.
- O resume pós-aprovação (Fase 1 da spec j3-build) tem de continuar a honrar a capacidade.

### Registry de stacks (Scope 4) — `src/capabilities/generate/stacks.py`
- `StackRegistry` keyed por `(language, framework)` → `GenerationStrategy` com:
  `template_ref`, `builder` (passa ao code-forge), `health_path`, `container_port`.
- Registar **FastAPI** (`("python","fastapi")`) com os valores hoje provados (porta 8080,
  `/health`, template TEMPLATE). É a **única** estratégia registada.
- `resolve(language, framework)`: desconhecida → levanta erro de stack (a capacidade traduz para
  `GenerateResult.failed`, **sem fallback silencioso** para FastAPI).
- Registo **extensível**: adicionar uma stack = registar uma entrada; o ponto de extensão é
  documentado no módulo. Não há código específico de FastAPI fora da entrada registada e do template.

### Gates de equivalência (Scope 5)
- **Bloco**: testar `GenerateCapability.start` com o cliente Temporal mockado (inicia com o input
  certo; stack desconhecida → FAILED sem iniciar) e `map_result` como função pura (output de
  sucesso → `completed` com code_artifact_id/container_image_ref/deployment; output falhado/
  incompleto → `failed`); estratégia "fake" registada em teste é selecionada sem tocar no contrato
  (prova de extensibilidade).
- **Routing**: testar que o `decision_consumer` invoca a capacidade para J3_BUILD e preserva os
  outros caminhos (J1 não executa; J2/J4 → Orchestration; fallback por workflow_type).
- **Jornada (cluster)**: intenção J3 real → Deployment ready 1/1 + `/health` 200 via a capacidade;
  `code_artifact` journey=J3_BUILD. Paridade com o caminho FluxoG anterior.

## Restrições de implementação
- TDD estrito (RED→GREEN). Nunca modificar `tests/` existentes (regra 7) — adicionar ficheiros novos.
- `ruff --fix` (UP017/UTC) e `black` quebram em py3.10 — diffs mínimos/aditivos.
- Compatibilidade: nenhuma mudança de runtime para J2/J4; o `input_data` do `FluxoGWorkflow`
  mantém-se retrocompatível (a estratégia só acrescenta campos com default).
- A capacidade vive no orchestrator (não é serviço novo); a fronteira é interna mas explícita e
  testável — o que habilita, sem reescrever, um futuro grau de extração (serviço dedicado).
- Anti-verde-falso: stack desconhecida e qualquer G-step falhado → FAILED com razão.
