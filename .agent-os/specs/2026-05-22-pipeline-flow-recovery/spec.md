# Spec Requirements Document

> Spec: Recuperação dos Fluxos Cognitivos (Pipeline Flow Recovery)
> Created: 2026-05-22
> Status: Planning
> Priority: P1 — Pipeline parcialmente inactivo

---

## Overview

Repor a totalidade do cognitive pipeline NHM (Gateway → STE → Specialists → Consensus → Orchestrator → Workers) que actualmente funciona apenas até à fase de consenso. Quatro defeitos pré-existentes, descobertos durante validação E2E em 2026-05-22, degradam ou inativam fluxos críticos:

1. **Queen Agent — Redis cliente em modo standalone** acede a Redis Cluster (6 nós) usando `Redis(host=node[0])` em vez de `RedisCluster(startup_nodes=...)`, causando `CLUSTERDOWN Hash slot not served` em todas as operações cujo hash slot caia fora do nó conectado. Impacto downstream: consensus-engine recebe `DEADLINE_EXCEEDED` ao consultar queen status → 3+ planos em lag no tópico `plans.ready`.

2. **Worker fleet a 0 réplicas** — `worker-agents`, `analyst-agents`, `guard-agents`, `optimizer-agents`, `scout-agents`, `self-healing-engine` estão `0/0` desired há ≥103 dias. HPAs em `<unknown>` (sem pods, sem métricas). Pipeline downstream do Orchestrator (Flow D) **não pode executar tickets**. Tópico `execution.tickets` vazio.

3. **Orchestrator-dynamic duplicado em 2 namespaces** — `neural-hive/orchestrator-dynamic` (2/2 OK) e `orchestrator-dynamic/orchestrator-dynamic` (2/3, com 110+ restarts por pod). Ambos partilham consumer group `orchestrator-dynamic` no Kafka → consumo competitivo de partições, risco de split-brain de workflows Temporal.

4. **Approval-service Istio sidecar em readiness flapping** — 66 restarts em 28h num pod, sidecar `istio-proxy` perde readiness probe via 15020 a cada ~3–10 minutos com `context deadline exceeded`. Aplicação está saudável (200 OK directo) mas readiness do pod oscila → endpoint slice instável → tráfego não-determinístico.

**Problema cumulativo:** dos 7 fluxos do pipeline, **3 estão funcionais (A, C, E)**, **2 degradados (B, F)** e **2 inativos (D, G-aux)**. O sistema ingere intents mas não os executa.

---

## User Stories

### US-001: SRE recupera capacidade de execução
Como **SRE responsável pelo cluster NHM**, quero que o pipeline aceite uma intenção end-to-end e produza output executado pelos workers, para validar que o sistema cumpre o seu propósito core.

**Workflow esperado:**
1. Cliente envia intent ao Gateway (`POST /api/v1/intent`).
2. STE consome de `intentions.*` → produz plano em `plans.ready`.
3. Consensus consome → consulta Queen e 5 Specialists (sem erros Redis) → publica em `plans.consensus`.
4. Orchestrator consome → cria workflow Temporal → emite ticket em `execution.tickets`.
5. **Worker-agent consome o ticket** → executa → publica resultado em `execution.results`.
6. SRE observa todas as etapas em logs estruturados sem erros gRPC/Redis/Kafka.

### US-002: Operador elimina duplicação de namespaces
Como **operador NHM**, quero um único deployment canónico de `orchestrator-dynamic`, para que o consumer group consuma deterministicamente e os workflows Temporal não dupliquem.

**Workflow esperado:**
1. Operador escolhe o namespace canónico (`neural-hive` por convenção do produto).
2. Operador escala o duplicado a 0 réplicas (não elimina deployment de imediato — rollback safety).
3. Operador valida 0 reset offsets, 0 workflow duplications durante 24h.
4. Operador elimina o deployment legacy e respectivos HPAs/PDBs/Services.

### US-003: Dev confirma estabilidade Istio sidecar
Como **developer do approval-service**, quero que o pod fique READY consistentemente, para que o autoscaler não interprete falsos negativos e o tráfego não saltite entre réplicas.

**Workflow esperado:**
1. Pod tem readiness probe estável durante 1h consecutiva (sem container restarts).
2. Logs do sidecar mostram XDS reconnects máximo 1× por hora (não a cada 3–10 min).
3. Métricas Istio mostram `pilot_proxy_convergence_time` < 5s.

---

## Spec Scope

1. **Migrar Queen-Agent Redis client para cluster-mode** — substituir `redis.asyncio.Redis` por `redis.asyncio.cluster.RedisCluster` em `services/queen-agent/src/clients/redis_client.py` e popular ENV vars no deployment.
2. **Reactivar worker fleet** — escalar 6 deployments de 0 → valor de produção (mínimo do HPA). Validar consumo dos tópicos relevantes.
3. **Consolidar namespace orchestrator-dynamic** — escalar a 0 o namespace legacy `orchestrator-dynamic`, confirmar zero impacto durante 24h, depois eliminar manifest legacy.
4. **Estabilizar Istio sidecar do approval-service** — investigar deadline timeout do app health probe (8080), ajustar `terminationDrainDuration`/probe timeouts ou aumentar `connectionPool.tcp.maxConnections`.

## Out of Scope

- Não vamos resolver os 14 testes de `tests/test_contract_grpc_extended.py` (protobuf MergeFrom mismatch) — domínio separado.
- Não vamos resolver o `python-grpc-base` Dockerfile hierarchy drift (Validar Base Images CI) — ticket próprio.
- Não vamos eliminar a duplicação `nlu/pii/gateway/approval` (5 outros serviços com mesmo padrão) — exige decisão maior de namespace strategy.
- Não vamos atacar os 14 testes de signature drift em `tests/unit/libraries/test_real_module_coverage.py` — já corrigidos no PR #100.
- Não vamos remover o `tests/test_storage_client.py UTC import` — proibido por `CLAUDE.md` (regra: tests intocáveis).

## Expected Deliverable

1. **Fluxo D ativo (Workers consomem tickets)** — `kafka-consumer-groups --describe --group worker-agents` mostra `LAG=0` em `execution.tickets` após injectar 5 intents de teste.
2. **Queen-agent zero erros Redis durante 1h** — `kubectl logs deploy/queen-agent | grep CLUSTERDOWN` retorna 0 entradas em 60 minutos consecutivos.
3. **Consensus lag plans.ready estável em 0** — após Queen recuperar, plans em backlog drenam e fica em 0.
4. **Orchestrator-dynamic única réplica activa** — `kubectl get deploy -A | grep orchestrator-dynamic` mostra apenas a entrada em `neural-hive/`.
5. **Approval-service 0 restarts em 1h** — `kubectl get pod` mostra `RESTARTS=0` para os 2 pods durante uma janela de 60min.
