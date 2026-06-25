# Fase 3 — G1 → G6: geração de código real (Evidência)

> Spec: Endurecer J3/BUILD (capacidade GENERATE) — pré-condição ADR-0011
> Task 4 — G1 gera requisitos; G6 (code-forge) gera código FastAPI real
> Data: 2026-06-24 · Branch: `feat/convergencia-dbs` · Cluster: `neural-hive`

## Resumo honesto

O trabalho de CÓDIGO da Task 4 está completo e provado (wiring G6-G13, fix do tracer,
G6 fail-closed). O **gate de cluster 4.3 (produzir um `code_artifact` com código FastAPI
real) NÃO foi atingido**, bloqueado por um defeito **pré-existente** do serviço
`requirements-engineering` (G1) — fora do escopo da Task 4. Detalhe abaixo, sem verde falso.

## Task 4.0 (pré-condição) — Wiring G6-G13 portado ✅

A Fase 0 (1.4a) provou que o commit `2d945153` (wiring Fluxo G) não estava em
`feat/convergencia-dbs` (worker registava só 5 G-activities → ActivityNotRegisteredError em
G6). Cherry-pick limpo de `2d945153` (commit `20ad53c4`): regista
`generate_code`/`build_package`/`deploy_software`/`verify_deployment` + G9-G13.
**Provado em cluster:** log do worker `Fluxo G workflow … activities_count=16` (era 5).

## Task 4.1 / 4.2 — G6 real + fail-closed ✅ (código + testes)

- G6 (`code_generation_activity.py`) chama o code-forge real (`/api/v1/generate`, sem `stub://`),
  faz poll, e **persiste `code_artifact`** em `neural_hive_orchestration.code_artifacts` (best-effort).
- **Anti-verde-falso (4.1):** `_wait_for_generation` passa a **FALHAR** (RuntimeError) se a geração
  "completa" sem artefacto de código real (artifacts vazio / sem artifact_id / código vazio).
  6 testes (`test_code_generation_failclosed.py`) RED→GREEN. Status `failed`/`requires_review` → FAILED.

## Bug bloqueador real corrigido — FluxoGWorkflow tracer=None ✅ (provado em cluster)

Um **run J3 real instrumentado** revelou que o `FluxoGWorkflow` falhava em
`fluxo_g_workflow.py:110` com `'NoneType' object has no attribute 'start_as_current_span'`
(get_tracer() devolve None no sandbox Temporal) — **antes do G1**, sem gerar nada. Mesma classe
de bug já corrigida no OrchestrationWorkflow. Fix (commit `87a950f`): `nullcontext` quando tracer
é None + helper `_safe_span_event` para os 16 span events. 3 testes.

**Prova em cluster (orchestrator `87a950f`):**
- Run anterior (sem fix, imagem `42f6952`): `Failing workflow task … 'NoneType' object has no
  attribute 'start_as_current_span'  File ".../fluxo_g_workflow.py", line 110`.
- Run após fix (`f3b-…`): **0** erros `start_as_current_span`; o workflow **avança para o G1**
  (`G1: Gerando requisitos para plan_id=f3b-…`). O tracer deixou de bloquear o Fluxo G.

## Gate de cluster 4.3 — NÃO ATINGIDO (bloqueado, sem verde falso)

Sequência real do run `f3b` (orchestrator `87a950f`, code-forge `dc81f7a`):
1. `workflow_start_attempt routing_basis=journey workflow_class=FluxoGWorkflow` ✅
2. `workflow_started FluxoGWorkflow` ✅
3. `G1: Gerando requisitos` ✅ (tracer já não bloqueia)
4. `Erro ao gerar requisitos` → activity `generate_requirements` falha (attempts 1+2) →
   **`Fluxo G workflow failed: Activity task failed`** (workflow FAILED — fail-closed, **sem** verde falso).

**Causa do bloqueio (fora do escopo da Task 4):** o serviço `requirements-engineering` (que o G1
chama em `http://requirements-engineering:8010/api/v1/requirements/from-plan`) **não arranca neste
branch** — `ModuleNotFoundError: No module named 'src.clients.engineering_service_registry_client'`.
O `main.py` do req-eng importa esse módulo, mas ele **nunca foi committado no req-eng** (`git log
--all` desse caminho = vazio; existe noutros serviços). Por isso o req-eng está `replicas=0` (broken
estável). Sem G1 funcional, o J3 não chega ao G6/code-forge para produzir o `code_artifact`.

`code_artifacts` em `neural_hive_orchestration` permanece com 1 documento (igual à Fase 0) — **nenhum
artefacto novo** foi gerado por este run (honestidade: o gate não foi atingido).

## Veredicto

- 4.0 (wiring), 4.1 e 4.2: **COMPLETOS** (código + testes; wiring e tracer provados em cluster).
- 4.3 (gate cluster code_artifact real): **BLOQUEADO** por defeito pré-existente do
  `requirements-engineering` (módulo `engineering_service_registry_client` em falta), fora do
  escopo desta task. **Não marcado como concluído** — o trabalho real (code_artifact) não aconteceu.

## Investigação + correção do requirements-engineering (G1) — 2026-06-25

A pedido, investiguei e corrigi o `requirements-engineering`. Foram **4 defeitos** distintos
(o serviço estava `replicas=0` há muito, acumulando debt):
1. **Módulo + proto em falta (código, commit `dcaf53d`):** `main.py` importava
   `src.clients.engineering_service_registry_client` (nunca committado no req-eng) e `src.proto`
   (não copiado no Dockerfile). Fix: portado o cliente de `documentation-generation` (mesmo path
   `from src.proto import …`) + adicionado `COPY services/service-registry/src/proto/ ./src/proto/`
   ao Dockerfile (como docs-gen/approval-gw).
2. **Registry bloqueava o startup (código, commit `24999e5`):** `initialize()` fazia
   `await channel_ready()` **sem timeout** → se o service-registry estiver inalcançável (mTLS istio),
   o lifespan nunca chega ao `yield` e o app HTTP nunca serve (503 `connection refused`). Fix:
   `asyncio.wait_for(channel_ready(), timeout=5)` → registo best-effort; **provado: `health → 200`,
   `Application startup complete`, `Uvicorn running on :8010`**.
3. **Kafka mal configurado (config, kubectl set env):** deployment tinha `REQ_ENG_KAFKA_BOOTSTRAP_SERVERS`
   mas o settings lê `KAFKA_BOOTSTRAP_SERVERS` (validation_alias) → default `localhost:9092` → crash.
4. **MongoDB mal configurado (config, kubectl set env):** idem, `REQ_ENG_MONGODB_URL` vs `MONGODB_URL`
   → default `localhost:27017` → `/from-plan` dava erro de persistência.

**Resultado provado em cluster:** `/from-plan → 200`; um run J3 real (`f3e`) passa a **avançar
G1 → G2** (antes parava no G1). O wiring + tracer + req-eng estão funcionais.

## 4.3 — ainda NÃO atingido: blockers de AMBIENTE (não de código)

Mesmo com o req-eng corrigido, o gate 4.3 não fecha por **debt de infra do pipeline Fluxo G** no
cluster dev (cada G-step depende de um serviço que está down/degradado):
- **LLM degradado:** o req-eng responde 200 mas gera **0 requisitos** (`requirements_generated total=0`)
  — sem API key LLM válida, a geração é vazia.
- **G2 (documentation-generation, :8014) DOWN:** run `f3e` falha em `generate_documentation`
  (`Erro ao gerar documentação` → workflow FAILED, fail-closed). Provável `replicas=0` como o req-eng.
- G3 (knowledge-graph-rag), G5 (RAG) e G6 (code-forge generation) dependem igualmente de serviços/LLM.

Estes são problemas de **ambiente/infra** (serviços desligados + credenciais LLM), fora do escopo de
código da Task 4. O `code_artifacts` permanece com 1 documento — **nenhum artefacto real gerado**
(sem verde falso). As correções de config do req-eng (Kafka/Mongo) são patches imperativos
(`kubectl set env`); o ideal é corrigir os nomes das vars no helm do req-eng (usa prefixo
`REQ_ENG_` que o settings não lê).

## Próximo passo recomendado
Para fechar 4.3: (a) configurar credenciais LLM para req-eng+code-forge; (b) repor os serviços
Fluxo G em falta (documentation-generation, knowledge-graph-rag) — provavelmente o mesmo padrão de
defeitos do req-eng; (c) re-correr o gate. Alternativa pragmática: validar o G6/code_artifact de
forma isolada (injetar requisitos+docs fixos e exercitar só o G6→code-forge) se o objetivo for
provar a geração de código sem depender de todo o pipeline G1-G5.
