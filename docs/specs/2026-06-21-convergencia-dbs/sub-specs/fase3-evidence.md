# Evidência de execução — Fase 3 (Tasks 5+6: restantes escritores)

> Spec: convergencia-dbs — Fase 3. Contexto kubectl: `neural-hive-prod`.

## Task 5 — gateway-intencoes + worker-agents → `neural_hive_dev`

### DoD — checklist com evidência

| Item | Estado | Evidência |
|---|---|---|
| dev-values em falta criados (5.1) | ✅ | `worker-agents-values.yaml` criado; gateway **não precisa** (ver achado) |
| Deploy + gate E2E por serviço (5.2) | ✅ | worker repontado + E2E A→C6 verde (plano fresco `cde2180d`) |
| Coleções dos serviços no alvo | ✅ | plan_approval do plano novo em `neural_hive_dev` (0 em `neural_hive`); worker executa contra a DB canónica |

### Achado: gateway-intencoes NÃO persiste em MongoDB

A premissa da spec ("gateway herda o default `neural_hive`") **é inexata para o
gateway**. Verificado:
- `services/gateway-intencoes/src/config/settings.py` **não tem nenhum campo Mongo**.
- Zero uso de Mongo/motor/cliente em `services/gateway-intencoes/src` (só Kafka/Redis/gRPC).
- Env vivo do pod: sem `MONGODB_DATABASE` (apenas `ENVIRONMENT`, Redis).

Logo o gateway **não tem coleções a convergir** e **não precisa de repoint nem de
dev-values** — criar um seria cargo-cult. Documentado honestamente em vez de
fabricar um artefacto inerte.

### worker-agents — repoint efetivo

O `worker-agents` usa `mongodb_database` (settings.py:411, default código
`neural_hive_workers`; chart `neural_hive`) APENAS para:
- o DLQ (`execution_tickets_dlq`, `mongodb_client.py:46-47`) — vazio;
- o **fallback** de QUERY/TRANSFORM quando a task não traz o parâmetro `database`
  (`query_executor.py:206`, `transform_executor.py:520`). As tasks reais trazem
  `database` (definido pela orquestração).

Repoint: criado `environments/dev/helm-values/worker-agents-values.yaml`
(`env.MONGODB_DATABASE: neural_hive_dev`) + aplicado em runtime por
`kubectl set env deployment/worker-agents -n neural-hive MONGODB_DATABASE=neural_hive_dev`
(instância dev patcheada via `kubectl set image`; persistente e reversível).

### Gate E2E (plano fresco `cde2180d`, medido no cluster)

Intent ao gateway (`intent_id=dbcfdb02-...`, domínio TECHNICAL) →
`plan_id=cde2180d-6371-4cbd-bd85-26eea0851fb9`.

| Passo | Resultado |
|---|---|
| Rollout worker-agents | 2 pods novos (`884d84569`) Running 2/2; `MONGODB_DATABASE=neural_hive_dev` confirmado |
| Consenso + aprovação pendente | `consensus_decisions`=1, `plan_approvals`=1 em `neural_hive_dev` |
| `GET /api/v1/approvals/{plan_id}` | HTTP 200 (0 404) |
| `POST /approve` | HTTP 200 |
| Tickets executados pelo worker | 4 task_ids únicos, **todos COMPLETED** |
| Localização do plan_approval | `neural_hive_dev`=1, `neural_hive`=0 |

O worker executou os tickets normalmente com a DB canónica — o repoint **não o
partiu**. (Mesmo padrão de tickets duplicados — 4 task_ids ×2, 4 PENDING presos —
da issue conhecida do orchestrator, independente do repoint do worker.)

### Rollback

`kubectl set env deployment/worker-agents -n neural-hive MONGODB_DATABASE-` (remover;
volta ao default código `neural_hive_workers`) + reverter o dev-values. `neural_hive`
e `neural_hive_workers` intactas.

---

## Task 6 — avaliar `neural_hive_orchestration` e tratar `neural_hive_workers`

### DoD — checklist com evidência

| Item | Estado | Evidência |
|---|---|---|
| Mapear leitores/escritores de `neural_hive_orchestration` (6.1) | ✅ | mapa abaixo (orchestrator-dynamic + execution-ticket-service) |
| Decisão documentada: migrar vs manter (6.2) | ✅ | **MANTER** como schema lógico intencional (decisão + rationale abaixo) |
| Tratar `execution_tickets_dlq` (6.3) | ✅ | vazio + worker repontado (Task 5) → arquivar em Fase 5 (decisão abaixo) |

### 6.1 — Mapa de leitores/escritores de `neural_hive_orchestration`

| Serviço | Como resolve a DB | Uso |
|---|---|---|
| `orchestrator-dynamic` | `settings.py:137` default `neural_hive_orchestration` + env explícito | escreve `execution_tickets`, `workflow_results`, `authorization_audit`, `validation_audit`, `code_artifacts` |
| `execution-ticket-service` | `settings.py:37` default `neural_hive_orchestration` + `.env.example` | camada de orquestração (tickets canónicos reais em PostgreSQL `sla_management`) |

Estado vivo (2026-06-22, a crescer a cada run): `execution_tickets`=1295,
`authorization_audit`=3905, `validation_audit`=248, `workflow_results`=67,
`code_artifacts`=1. **Nenhum serviço da camada cognitiva** lê/escreve aqui. (O
`train_predictive_models.py:54` lê `self.mongo_client.neural_hive` — DB ERRADA, 0
tickets — é o bug pré-existente das Tasks 9/12, não esta DB.)

### 6.2 — DECISÃO: manter `neural_hive_orchestration` como schema lógico intencional

**Não migrar.** Mantém-se como a DB operacional da camada de orquestração, distinta
da DB canónica do corpus cognitivo (`neural_hive_dev`). Rationale baseado em evidência:

1. **Fronteira arquitetural deliberada, não drift silencioso:** é usada por DOIS
   serviços (orchestrator-dynamic + execution-ticket-service) com `MONGODB_DATABASE`
   explícito — ao contrário do approval-service (que caía no default por omissão).
2. **É estado OPERACIONAL, não corpus de treino:** execution_tickets (cópia de
   trabalho), workflow_results, audits. O objetivo da spec — reunificar o **sinal de
   treino** (opinions/feedback/approvals) — já foi cumprido nas Fases 1–2. Este estado
   não pertence a esse corpus.
3. **Risco vs benefício:** migrar estado operacional vivo e de alto volume (1295
   tickets, 3905 audits, a crescer por run) arrisca partir o orchestrator/ticket-service
   a meio de execuções, sem benefício para o sinal de treino.
4. **Tickets canónicos são PostgreSQL:** os tickets reais vivem em
   `sla_management.execution_tickets`; a cópia Mongo aqui é o working-set da orquestração.
   A consolidação de fonte-única de tickets está explicitamente diferida (technical-spec).

Esta decisão alinha com o âmbito da spec, que listou orchestration como "avaliar:
migrar ou manter schema lógico documentado". A convergência converge o **corpus
cognitivo**; a camada de orquestração permanece um schema lógico próprio, documentado.

### 6.3 — DECISÃO: `neural_hive_workers` → arquivar em Fase 5

`execution_tickets_dlq`=0 (vazio). Após a Task 5, o worker-agents escreve o DLQ em
`neural_hive_dev` (`MONGODB_DATABASE=neural_hive_dev`), pelo que `neural_hive_workers`
**deixou de ser escrita**. Nada a migrar (vazio). Decisão: **arquivar/descartar em
Fase 5**, após uma janela a confirmar 0 escritas, alinhado com o princípio "arquivar,
não apagar". Não é apagada agora (prematuro antes da janela de observação).

### Resultado da Fase 3

A convergência do **corpus cognitivo** está completa: STE/consensus/specialists
(pré-existente) + approval-service (Fase 2) escrevem em `neural_hive_dev`; gateway não
usa Mongo; worker-agents repontado. A **camada de orquestração** (`neural_hive_orchestration`)
mantém-se como schema lógico intencional documentado. `neural_hive_workers` fica para
arquivo na Fase 5.
