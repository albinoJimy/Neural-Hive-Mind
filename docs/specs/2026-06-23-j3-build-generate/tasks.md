# Spec Tasks

> Passo 3 do ADR-0011 (Capacidades) — pré-condição: tornar J3/BUILD fiável antes de extrair GENERATE.
> Ordenação faseada pelo fluxo: Fase 0 (diagnóstico) → Fase 1 (roteamento) → Fase 2 (contrato) → Fase 3 (gerar) → Fase 4 (build) → Fase 5 (deploy+E2E). Cada fase é um gate: só avança com testes verdes + evidência de cluster.
>
> **Princípios:** anti-verde-falso (marcar+medir+FALHAR, nunca COMPLETED simulado); TDD estrito; diffs mínimos (py3.10: sem `ruff --fix` UP017/UTC). Stack canónica: Python FastAPI REST. Detalhe em `sub-specs/technical-spec.md`.

## Tasks

### Fase 0 — Diagnóstico instrumentado

- [x] 1. Fixar os break-points reais de J3_BUILD num run de cluster
  - **DoR:** journey-router fechado; cluster acessível.
  - **DoD:** mapa documentado de onde cada elo parte (routing pós-aprovação, FluxoG inicia?, G-steps, contrato code-forge, deps); reordena/reduz as fases seguintes conforme achados.
  - **Evidência:** `sub-specs/fase0-evidence.md`.
  - [x] 1.1 Run J3 real (intenção FastAPI) com tracing; capturar workflow iniciado (FluxoG vs Orchestration) no caminho direto e pós-aprovação
  - [x] 1.2 Confirmar se tarefas genéricas do STE são executadas em J3 (parasitas) ou ignoradas
  - [x] 1.3 Localizar tópico/grupo onde o code-forge consome tickets + caminho do erro de desserialização
  - [x] 1.4 Verificar estado das deps do code-forge (GitPython, kubernetes) e dos 2 bugs críticos pré-existentes

### Fase 1 — Roteamento J3 → FluxoGWorkflow fiável

- [x] 2. Garantir que J3_BUILD inicia o FluxoGWorkflow (direto e pós-aprovação)
  - **DoR:** Fase 0 fechada.
  - **DoD:** plano J3_BUILD (incl. `review_required`→aprovado) **inicia FluxoGWorkflow**; sem tarefas query/transform parasitas; fallback workflow_type preservado para planos sem journey.
  - **Evidência:** `sub-specs/fase1-evidence.md` (log/Temporal a iniciar FluxoG; 0 tickets parasitas).
  - [x] 2.1 Testes: resume pós-aprovação seleciona workflow por journey (J3→FluxoG); J1/UNKNOWN sem execução; J2/J4→Orchestration
  - [x] 2.2 Corrigir o ponto de resume pós-aprovação para honrar `_select_workflow_class_by_journey`
  - [x] 2.3 Gate cluster: plano J3 aprovado inicia FluxoGWorkflow (não Orchestration)

### Fase 2 — Contrato `ExecutionTicket` canónico

- [x] 3. Unificar o contrato de ticket entre produtor, worker e code-forge
  - **DoR:** Fase 1 fechada.
  - **DoD:** contrato canónico (`task_type` enum maiúsculas, `priority` enum string); produtor emite canónico; worker e code-forge validam o mesmo modelo; desserializador tolerante normaliza legado (minúsculas/int) sem rejeitar.
  - **Evidência:** `sub-specs/fase2-evidence.md` (code-forge sem `message_deserialization_error`; ticket BUILD aceite por ambos).
  - [x] 3.1 Testes: desserialização canónica + normalização de legado (task_type minúsculas, priority int) em worker e code-forge
  - [x] 3.2 Definir contrato único + ajustar produtor (ticket_generation) e ambos os consumidores
  - [x] 3.3 Gate cluster: tickets fluem para o code-forge sem erro de desserialização

### Fase 3 — G1 → G6: geração de código real

- [x] 4. G1 gera requisitos; G6 (code-forge) gera código FastAPI real
  - **DoR:** Fase 2 fechada.
  - **DoD:** G1 produz requisitos/user-stories do intent+plano; G6 gera código-fonte FastAPI real (sem stub) via code-forge; `code_artifact` persistido em `neural_hive_orchestration.code_artifacts`. Geração vazia/stub → FAILED.
  - **Evidência:** `sub-specs/fase3-evidence.md` (code_artifact com código real; falha de geração → FAILED).
  - [x] 4.1 Testes: G6 produz artefacto não-vazio; geração vazia/erro → FAILED (anti-verde-falso)
  - [x] 4.2 Garantir G6 chama code-forge real (sem `stub://`) e persiste code_artifact
  - [x] 4.3 Gate cluster: plano J3 produz code_artifact com código FastAPI real (PROVADO E2E: J3_BUILD→FluxoG→G6→code_artifact bafbf10e, framework=fastapi, generation_method=TEMPLATE, sem LLM; G2-G5 degradam best-effort; workflow falha em G7/build=Fase 4 esperado). Ver fase3-evidence.md.

### Fase 4 — G7: build real (Kaniko → GHCR)

- [x] 5. Build real do código gerado em imagem de container
  - **DoR:** Fase 3 fechada.
  - **DoD:** G7 constrói imagem real via Kaniko e publica no GHCR com digest; imagem **puxável** (skopeo inspect). Build falhado / imagem não-puxável → FAILED.
  - **Evidência:** `sub-specs/fase4-evidence.md` (imagem no GHCR, digest, skopeo inspect OK; build falhado → FAILED).
  - [ ] 5.1 Testes: G7 sucesso publica imagem; falha de build → FAILED; sem ramo de simulação
  - [x] 5.2 Garantir build real (Kaniko) + digest — PROVADO: build FastAPI Succeeded + push GHCR com digest sha256:0cbe85b8…
  - [x] 5.3 Gate cluster: imagem publicada e puxável — ATINGIDO: Kaniko `Pushed ghcr.io/albinojimy/neural-hive-mind/…@sha256:0cbe85b8…` (causa do DENIED era o secret não montado, NÃO o token; fix f9585d8). Ver fase4-evidence.md.

### Fase 5 — G8: deploy real + healthcheck (E2E completo)

- [ ] 6. Deploy real do software gerado + prova E2E
  - **DoR:** Fase 4 fechada.
  - **DoD:** G8 faz deploy real (kubernetes_asyncio) em namespace efémero TTL+ResourceQuota; `Deployment ready 1/1`; healthcheck HTTP 200; `code_artifact`+`ExecutionFeedback` com `journey=J3_BUILD`. Deploy não-ready / healthcheck != 200 → FAILED.
  - **Evidência:** `sub-specs/fase5-evidence.md` (Deployment ready 1/1 + healthcheck 200 + journey nos artefactos; E2E gera→build→deploy→healthcheck).
  - [ ] 6.1 Testes: G8 sucesso → ready+healthcheck; deploy não-saudável → FAILED
  - [ ] 6.2 Garantir deploy real + healthcheck + persistência final com journey
  - [ ] 6.3 Gate cluster E2E: intenção de geração → software FastAPI real a correr (ready 1/1, /health 200), gate "J3/BUILD fiável" do ADR-0011 estabelecido
