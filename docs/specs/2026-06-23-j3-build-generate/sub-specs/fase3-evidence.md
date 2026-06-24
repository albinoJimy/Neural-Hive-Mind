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

## Próximo passo recomendado
Restaurar o `requirements-engineering` (criar/portar `engineering_service_registry_client` para
`services/requirements-engineering/src/clients/`, ou corrigir o import em `main.py`), repor
`replicas≥1`, e re-correr o gate 4.3. Só então a Fase 3 fecha e a Fase 4 (build) pode arrancar.
