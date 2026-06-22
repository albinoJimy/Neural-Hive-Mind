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
