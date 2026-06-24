# Fase 2 — Contrato ExecutionTicket canónico (Evidência)

> Spec: Endurecer J3/BUILD (capacidade GENERATE) — pré-condição ADR-0011
> Task 3 — Unificar o contrato de ticket entre produtor, worker e code-forge
> Data: 2026-06-24 · Branch: `feat/convergencia-dbs` · Cluster: `neural-hive`

## Resumo

A Fase 0 (1.3) provou em cluster que o code-forge rejeitava (Pydantic enum estrito)
tickets legados com `task_type` minúsculo (ex.: 'transform') ou `priority` inteiro
(ex.: 5), enviando-os para DLQ (`message_deserialization_error`). A Fase 2 unifica o
contrato **canónico** (`task_type` MAIÚSCULAS, `priority` enum string) e torna os
consumidores **tolerantes** ao legado, com o produtor a emitir o canónico.

## Contrato canónico + correção (Subtask 3.2)

- **Contrato:** `task_type ∈ {BUILD,DEPLOY,TEST,VALIDATE,EXECUTE,COMPENSATE,QUERY,TRANSFORM}`
  (MAIÚSCULAS); `priority ∈ {LOW,NORMAL,HIGH,CRITICAL}` (enum string).
- **code-forge** (`services/code-forge/src/models/execution_ticket.py`): `model_validator(mode="before")`
  `_normalize_legacy_contract` — `task_type.upper()` + `priority` int 1-10 → enum string
  (1-2 LOW, 3-5 NORMAL, 6-8 HIGH, 9-10 CRITICAL; clamp fora do intervalo); cópia rasa (não muta o
  dict do chamador); valores desconhecidos continuam a falhar (anti-verde-falso).
- **worker-agents** (`services/worker-agents/src/models/execution_ticket.py`): mesmo validador +
  `TRANSFORM` adicionado ao enum (estava em falta) + `use_enum_values=True` (paridade de representação
  interna com o code-forge — "o mesmo modelo").
- **produtor** (`services/orchestrator-dynamic/src/activities/ticket_generation.py`): emite canónico —
  `task_type=str(...).upper()` e `priority=normalize_priority(...).value`.

## Testes (Subtask 3.1) — TDD

34 testes novos (RED→GREEN), sem modificar testes existentes:
- code-forge `tests/unit/test_execution_ticket_tolerance.py` (18): canónico ok; task_type minúsculo →
  MAIÚSCULAS; priority int 1-10 → enum (todos os limites); priority string minúscula; caso misto
  (transform+5); task_type/priority desconhecidos rejeitados.
- worker `tests/test_execution_ticket_tolerance.py` (10): TRANSFORM no enum; minúsculo normalizado;
  int normalizado; misto; desconhecido rejeitado.
- produtor `tests/unit/activities/test_ticket_generation_canonical.py` (6): emissão MAIÚSCULAS +
  priority int→enum string + caso misto.

Regressão verde (code-forge 18, worker 10+36 parallel_executor, orchestrator canónico+journey).
`black -l 100` limpo; `ruff` sem erros novos (import first-party reordenado com fix targeted I001).
Falhas pré-existentes confirmadas por stash (TestAllocateResources scheduler/OPA; parallel_executor
timeout) — não são regressão.

## Pré-condição de deploy resolvida (drift de deps — Fase 0/1.4b)

O build limpo do code-forge **não arrancava** (CrashLoopBackOff), revelando a rot de deps que a
Fase 0 (1.4b) tinha previsto: `GitPython`, `kubernetes` e `asyncpg` eram importados mas **não
declarados** em `requirements.txt` (existiam só por drift na imagem antiga). Declarados
explicitamente (versões alinhadas com produção: GitPython 3.1.43, kubernetes 28.1.0, asyncpg 0.29.0).
Só após isto o code-forge arranca limpo (Ready 1/1, 0 restarts). Antecipa parte da Fase 4.

## Gate de cluster (Subtask 3.3) — EVIDÊNCIA REAL

Deploy: `ghcr.io/albinojimy/neural-hive-mind/code-forge:dc81f7a` via `workflow_dispatch` +
`kubectl set image`. Pod `Running 2/2`, 0 restarts.

Publicados no tópico `execution.tickets` dois tickets **legados** (o caso exato do DLQ da Fase 0):
`task_type='build'`/`priority=5` e `task_type='transform'`/`priority=5`.

| Ticket de teste | Resultado no code-forge |
|---|---|
| `f2gate-build-*` (build/5) | **`build_ticket_received`** — desserializado + normalizado (BUILD/NORMAL), aceite |
| `f2gate-transform-*` (transform/5) | desserializado OK + filtrado (não-BUILD); **sem** `message_deserialization_error`, **não** foi para DLQ |

Verificações: `message_sent_to_dlq` para `f2gate-*` = **0**; os meus tickets legados deixaram de ser
rejeitados (antes da Fase 2 iriam para DLQ, como provado na Fase 0).

**Nuance honesta:** persistem 2 `message_deserialization_error` no stream, mas para
`task_type='CREATE'` (offset 763, mesma mensagem retried) — um tipo **não-canónico** (fora dos 8 do
contrato). É corretamente rejeitado (anti-verde-falso: normaliza-se, não se inventa). 'CREATE' é uma
anomalia de dados legada (Fase 0 viu 1 ticket `create` no Mongo), **fora do escopo** do contrato
canónico desta spec.

## Veredicto

DoD da Task 3 satisfeita: contrato canónico definido; produtor emite canónico (code-proven, 6
testes); worker e code-forge validam o mesmo modelo tolerante; legado (minúsculas/int) dos 8 tipos
canónicos é normalizado e aceite (provado em cluster). Gate de cluster (3.3) **PASSADO** para o
contrato canónico.

## Notas / limites
- Deploy do gate é imperativo (`kubectl set image dc81f7a`). O produtor canónico (commit d8811d50)
  está code-proven mas o orchestrator deployado é ainda `ee14f1a` (Fase 1) — o stream legado continua
  até redeploy do orchestrator; o code-forge tolerante torna o sistema resiliente entretanto.
- `task_type='CREATE'` (não-canónico) fica para tratamento de dados/decomposição fora desta spec.
