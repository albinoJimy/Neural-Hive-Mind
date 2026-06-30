# Fase 2 — Des-vazar a fronteira no routing (Evidência)

> Spec: Extrair GENERATE como capacidade autónoma (multi-linguagem-ready)
> Task 3 — `decision_consumer` invoca a capacidade em vez de conhecer FluxoGWorkflow
> Data: 2026-06-26 · Branch: `feat/convergencia-dbs` · Serviço: `orchestrator-dynamic`

## Estado: COMPLETA (código + contrato) — 18 testes novos verdes, zero regressão

Pipeline: dev (TDD) → auditoria qualidade (SHIP) → auditoria completude (COMPLETO) →
remediação dirigida (DRY da autoridade de routing) → commit. Evidência unit/contrato-level.
**Gate de cluster 3.3 (plano J3 aprovado processado via capacidade) DIFERIDO** — exige
deploy + cluster (API de control-plane instável hoje); a paridade E2E real é a Fase 4 (Task 5).

## Entregáveis (diff cirúrgico, aditivo)

- `src/capabilities/generate/capability.py` — `start(request, workflow_id=None)`: parâmetro
  `workflow_id` opcional (retrocompatível) para o resume preservar o id `flow-c-{correlation_id}`;
  na ausência mantém o id por plano `{prefix}{plan_id}` (caminho legado).
- `src/consumers/decision_consumer.py`:
  - Helpers module-level: `_journey_requires_generation(journey)` (autoridade primária — deriva da
    SEMÂNTICA da jornada, J3_BUILD), `_requires_generate_capability(journey, workflow_type)`
    (autoridade ÚNICA partilhada com o resume: jornada OU fallback `workflow_type=generation`),
    `_extract_generate_target(plan)` (stack-alvo; default provado python/fastapi quando o plano não
    a fixa — registry continua fail-closed para stacks EXPLÍCITAS não suportadas).
  - `__init__`: constrói `self.generate_capability = GenerateCapability(temporal_client=<injetado>,
    task_queue, workflow_id_prefix)` — mesmos prefix/queue do legado → workflow_id idêntico.
  - `_process_message`: para `requires_generation`, invoca `self.generate_capability.start(...)` e
    NÃO inicia `FluxoGWorkflow` diretamente; `UnsupportedStackError` → commit + return (erro
    permanente, anti-verde-falso). Bloco de orquestração J2/J4 INTACTO.
- `src/main.py` (endpoint resume `POST /api/v1/workflows/start`): mesmo predicado
  `_requires_generate_capability`; invoca `GenerateCapability(temporal_client=app_state.temporal_client,
  ...)` preservando o `workflow_id`; `UnsupportedStackError` → HTTP 422.

## Fronteira não-vazada (Scope 3) — provado

- A decisão "requer geração" deriva da jornada (`_journey_requires_generation`), **não** de conhecer
  a classe do workflow (technical-spec Scope 3). O handler do consumer e o resume delegam na
  capacidade; o arranque do `FluxoGWorkflow` vive dentro da capacidade.
- Equivalência ao caminho legado (auditoria qualidade SHIP):
  - `FluxoGWorkflow.run` só lê `cognitive_plan`/`original_intent`/`skip_approvals` — `consolidated_decision`/
    `is_direct_plan` (que a capacidade fixa) são ignorados → comportamento idêntico.
  - `start_workflow(FluxoGWorkflow.run, input_data, id=..., task_queue=...)` chamado via o cliente
    injetado (consumer e resume) → o teste EXISTENTE `test_workflow_start_journey_routing.py`
    (asserts `args[0]==FluxoGWorkflow.run`) **continua verde**: garantia de **não-regressão de
    routing**. **Precisão (CR-002, ver fase4-evidence):** este teste prova apenas que `FluxoGWorkflow.run`
    é passado ao `start_workflow` para J3 — passaria na mesma num revert que arrancasse o FluxoG
    *directamente*, sem a capacidade; NÃO é prova de que a fronteira da capacidade foi exercida. A
    prova da fronteira é `test_workflow_start_generate_capability.py` (id `flow-c-{correlation_id}`,
    só gerado via capacidade) + o log de cluster `routing_basis=capability_generate`.
  - workflow_id idêntico: consumer `{prefix}{plan_id}`; resume `{prefix}flow-c-{corr}` (preservado
    via `workflow_id=` explícito).

## Anti-verde-falso

- Stack EXPLÍCITA não suportada (ex: rust/actix) → `UnsupportedStackError` → consumer commita sem
  arrancar nada; resume devolve HTTP 422. Sem fallback silencioso para FastAPI. Provado por teste.
- O default python/fastapi do `_extract_generate_target` aplica-se só quando o plano NÃO fixa stack
  (preserva o comportamento atual; o registry é a barreira fail-closed para stacks explícitas).

## Remediação dirigida (auditoria qualidade)

- **CR-001 (warning, DRY):** extraída a autoridade única `_requires_generate_capability(journey,
  workflow_type)`, usada pelo consumer e pelo resume — eliminada a duplicação do predicado inline
  (impedindo divergência futura entre os dois caminhos). +4 testes diretos.
- **CR-002 (warning, dead-code futuro):** documentado em `_select_workflow_class_by_journey` que NÃO
  é a autoridade de routing de geração; ao adicionar uma jornada de geração, atualizar
  `_journey_requires_generation`. (A linha J3_BUILD→FluxoGWorkflow mantém-se: há teste congelado que
  a afirma — regra 7.)
- CR-004 (info, capability por-pedido no resume) aceite como não-bloqueante (registry stateless/barato).

## Testes (TDD) — novos

- `tests/consumers/test_decision_consumer_generate_routing.py` — 16 testes: helpers
  (`_journey_requires_generation`, `_requires_generate_capability`, `_extract_generate_target`) +
  handler `_process_message` (J3_BUILD→capability 1×, sem `start_workflow`; J2/J4→OrchestrationWorkflow;
  J1→nada; sem-journey+generation→capability; sem-journey→Orchestration; `UnsupportedStackError`→commit+return).
- `tests/unit/test_workflow_start_generate_capability.py` — 2 testes: resume J3_BUILD → 200 via
  capacidade (`FluxoGWorkflow.run` pelo cliente injetado, id sufixo `flow-c-corr-1`, não default por
  plan_id); stack explícita não suportada → 422.

## Verificação (independente)

- `pytest tests/consumers tests/unit/capabilities tests/unit/test_workflow_start_journey_routing.py
  tests/unit/test_workflow_start_generate_capability.py -q` → **83 passed**.
- Regressão (suíte unit+consumers): baseline limpo **96 failed / 761 passed** → com a mudança
  **96 failed / 779 passed** (+18 = testes novos; **failed idêntico → zero regressão**). Os 96
  failed/4 errors são pré-existentes (ML scheduling, alert_manager, timedelta) sem relação.
- `black -l 100` aplicado · ruff: só avisos pré-existentes do ficheiro (B904/TRY200 em todos os
  `raise HTTPException` de `main.py`); o único `raise` novo (422) usa `from e`.

## Pendente (gate de cluster — Task 3.3)

- Deploy do orchestrator e validação no cluster de que um plano J3 aprovado é processado via a
  capacidade (logs `Invocando capacidade GENERATE` / Temporal `FluxoGWorkflow` coerentes). Diferido
  por instabilidade do control-plane; a prova E2E "software a correr" é a Fase 4 (Task 5).
