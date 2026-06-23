# Technical Specification

This is the technical specification for the spec detailed in @docs/specs/2026-06-23-j3-build-generate/spec.md

## Fluxo-alvo

```
Intenção de geração
  → STE (workflow_type=generation, journey=J3_BUILD)
  → Consensus (propaga journey — já provado)
  → decision_consumer: J3_BUILD → FluxoGWorkflow  [direto E resume pós-aprovação]
  → FluxoGWorkflow:
        G1 generate_requirements (intent+plan → requisitos/user-stories)
        G6 generate_code (code-forge → código FastAPI real)
        G7 build (Kaniko → imagem GHCR + digest)
        G8 deploy (namespace efémero TTL → Deployment ready 1/1 → healthcheck 200)
  → code_artifact persistido (neural_hive_orchestration.code_artifacts) + ExecutionFeedback(journey=J3_BUILD)
```

## Requisitos Técnicos

### Roteamento (Scope 1)
- `services/orchestrator-dynamic/src/consumers/decision_consumer.py`: `_select_workflow_class_by_journey` já mapeia `J3_BUILD → FluxoGWorkflow`. Garantir que o **caminho de resume pós-aprovação** (flow_c após receber a approval response) também seleciona o workflow por journey, em vez de cair em `OrchestrationWorkflow` genérico.
- A Fase 0 deve confirmar o ponto exato onde, para planos `review_required`, o journey deixa de governar a escolha de workflow.
- Compatibilidade: planos sem journey / UNKNOWN mantêm o fallback por `workflow_type`.

### Contrato `ExecutionTicket` (Scope 2)
- Definir contrato **canónico** único: `task_type` enum maiúsculas {BUILD,DEPLOY,TEST,VALIDATE,EXECUTE,COMPENSATE,QUERY,TRANSFORM}; `priority` enum string {LOW,NORMAL,HIGH,CRITICAL}.
- Produtor (STE/orchestrator `ticket_generation`) emite o canónico.
- Consumidores `worker-agents` (`kafka_ticket_consumer`) e `code-forge` validam contra o **mesmo** modelo.
- **Desserializador tolerante**: normaliza legado (`task_type` minúsculas, `priority` int) → canónico, sem rejeitar (evita partir tickets em voo). Erros atuais observados: `task_type='transform'` (esperava 'TRANSFORM'), `priority=5` (esperava enum string).

### Pipeline G real e fail-closed (Scope 3)
- `fluxo_g_workflow.py` + activities `generate_requirements` (G1), `generate_code` (G6), build (G7), deploy (G8).
- Cada etapa **fail-closed**: código vazio/stub, build falhado, imagem não-puxável, Deployment não-ready, healthcheck != 200 → marca **FAILED** com razão; nunca COMPLETED simulado (eliminar qualquer ramo de simulação para J3).
- G6: code-forge gera código real (sem `stub://`); produz `code_artifact` persistido.
- G7: build real via Kaniko → imagem GHCR; validar com `skopeo inspect` (digest puxável).
- G8: deploy via `kubernetes_asyncio` (imperativo) em namespace efémero com TTL+ResourceQuota; healthcheck HTTP 200.

### Stack canónica (Scope 4)
- Template de geração: microserviço Python **FastAPI** REST com endpoint `/health` (200) — alvo de geração, build e deploy.

## Diagnóstico (Fase 0) — pontos a confirmar
1. Para o plano J3 review_required, o resume pós-aprovação inicia `FluxoGWorkflow` ou `OrchestrationWorkflow`? (Logs orchestrator + Temporal.)
2. As tarefas genéricas query/transform do STE são executadas mesmo em J3 (parasitas) ou ignoradas quando FluxoG corre?
3. Onde o code-forge consome tickets (tópico/grupo) e qual o caminho do erro de desserialização (G7 build-ticket vs consumer geral).
4. Estado real das deps do code-forge (GitPython, kubernetes) e dos 2 bugs críticos pré-existentes (ver `proj_code_forge_build_real_2026-06-20`, `proj_fluxo_g_wiring_2026-06-20`).

## Dependências e mecânica (da memória, confirmar na Fase 0)
- Build: Kaniko + GHCR (`proj_code_forge_build_real_2026-06-20`).
- Deploy: RBAC `ClusterRole` worker + namespace efémero TTL+ResourceQuota (`proj_deploy_imperative_2026-06-21`).
- Activities G6-G13 registadas no Temporal worker (`proj_fluxo_g_wiring_2026-06-20`).
- DB: `execution_tickets`/`code_artifacts` em **`neural_hive_orchestration`** (não `neural_hive_dev`).
- Deploy de serviços: `helm upgrade -f environments/dev/helm-values/<svc>-values.yaml` (orchestrator/STE/worker/code-forge têm values); gateway por `kubectl set image`.

## Restrições de implementação
- TDD estrito (RED→GREEN). Nunca modificar `tests/` existentes (regra 7).
- `ruff --fix` (UP017/UTC) e `black` quebram em py3.10 — diffs mínimos/aditivos; reverter reformatação alheia.
- Schemas Avro: campos novos opcionais com default (retrocompat); re-registo no Apicurio quando aplicável (compat=NONE no dev).
- Gate E2E por fase com evidência em `sub-specs/faseN-evidence.md`.
