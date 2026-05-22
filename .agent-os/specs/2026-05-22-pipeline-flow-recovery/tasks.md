# Spec Tasks

> Spec: Recuperação dos Fluxos Cognitivos
> Ordem: TR-4 → TR-1 → TR-2 → TR-3 (segurança crescente)

---

## Tasks

- [ ] **1. TR-4: Estabilizar Istio sidecar approval-service** (P2, esforço S)
  - [ ] 1.1 Escrever teste de integração: pod approval-service deve manter `RESTARTS=0` por 30min em smoke run com 100 req/s
  - [ ] 1.2 Adicionar annotations Istio (`proxy.istio.io/config`, `holdApplicationUntilProxyStarts`) ao deployment
  - [ ] 1.3 Aumentar `readinessProbe.timeoutSeconds: 1→10`, `periodSeconds: 10→30`, `failureThreshold: 3→5`
  - [ ] 1.4 Rollout deployment, observar 1h
  - [ ] 1.5 Confirmar `RESTARTS=0` por 60min e XDS reconnect ≤1/h

- [ ] **2. TR-1: Migrar Queen-Agent para Redis Cluster client** (P1, esforço M)
  - [ ] 2.1 Escrever testes unitários para `RedisClient` simulando hash slot redirects (`MOVED`, `ASK`)
  - [ ] 2.2 Substituir `redis.asyncio.Redis` por `redis.asyncio.cluster.RedisCluster` em `redis_client.py`
  - [ ] 2.3 Verificar todas as 8+ chamadas internas (`get`, `set`, `delete`, `expire`, `hset`, `hget`) compatíveis com cluster client
  - [ ] 2.4 Adicionar env vars (`REDIS_CLUSTER_NODES`, `REDIS_SSL_ENABLED`, `REDIS_PASSWORD` cluster ref) ao deployment
  - [ ] 2.5 Build + push imagem queen-agent
  - [ ] 2.6 Rollout queen-agent (3 réplicas)
  - [ ] 2.7 Validar `CLUSTERDOWN` count = 0 em 60min
  - [ ] 2.8 Validar `plans.ready` lag drena para 0
  - [ ] 2.9 Validar consensus-engine deixa de emitir `grpc_get_system_status_failed`

- [ ] **3. TR-2: Reactivar worker fleet** (P1, esforço M, depende de #2)
  - [ ] 3.1 Auditoria pré-flight: verificar imagens GHCR existem, secrets/configmaps presentes, Gatekeeper labels conformes
  - [ ] 3.2 Escalar `optimizer-agents` para 1 réplica, smoke test 30min
  - [ ] 3.3 Escalar `scout-agents` para 2 réplicas, smoke test 30min
  - [ ] 3.4 Escalar `analyst-agents` para 2 réplicas, smoke test 30min
  - [ ] 3.5 Escalar `guard-agents` para 2 réplicas, smoke test 30min
  - [ ] 3.6 Escalar `worker-agents` para 2 réplicas, smoke test 30min
  - [ ] 3.7 Escalar `self-healing-engine` para 2 réplicas, smoke test 30min
  - [ ] 3.8 E2E: injectar 5 test intents via Gateway, validar `execution.results` recebe 5 messages

- [ ] **4. TR-3: Consolidar orchestrator-dynamic** (P2, esforço L, depende de #2 e #3 estáveis)
  - [ ] 4.1 Fase 1 — scale-down: `kubectl scale -n orchestrator-dynamic deploy/orchestrator-dynamic --replicas=0`
  - [ ] 4.2 Monitor 24h: Temporal workflow duplicates, Kafka consumer rebalances, alertas
  - [ ] 4.3 Confirmar `neural-hive/orchestrator-dynamic` único consumidor das 5 topics
  - [ ] 4.4 Fase 2 — remoção: `helm uninstall` ou `kubectl delete` recursos em `orchestrator-dynamic`
  - [ ] 4.5 Eliminar namespace vazio
  - [ ] 4.6 Confirmar PVCs + finalizers limpos

- [ ] **5. Validação E2E final** (gate de aceitação)
  - [ ] 5.1 5/7 fluxos funcionais (A, B, C, D, E) — Flow F automático com #3 done, Flow G dashboard verificado
  - [ ] 5.2 `kubectl logs --since=1h | grep -iE "CLUSTERDOWN|DEADLINE_EXCEEDED|CrashLoop"` = 0 entries
  - [ ] 5.3 `kubectl get pods -A | awk '$4!~/Running|Completed/'` = vazio
  - [ ] 5.4 Documentar runbook em `docs/runbooks/pipeline-recovery.md`
  - [ ] 5.5 Memória de sessão: actualizar `MEMORY.md` com data 2026-05-22 e link para esta spec

---

## Critérios de aceitação por task

| Task | Verificação automática |
|---|---|
| 1 | `pytest tests/integration/test_approval_stability.py -v` PASS |
| 2.1 | `pytest tests/unit/test_redis_cluster_client.py -v` PASS |
| 2.6+ | `kubectl logs deploy/queen-agent --since=1h \| grep CLUSTERDOWN \| wc -l` = 0 |
| 3.x | `kubectl get hpa -n neural-hive` mostra `TARGETS` numérico (não `<unknown>`) |
| 3.8 | Test E2E `tests/e2e/test_intent_to_execution_flow.py::test_full_pipeline` PASS |
| 4.3 | `kafka-consumer-groups --describe --group orchestrator-dynamic` mostra apenas IPs do ns `neural-hive` |
| 5.x | Dashboard FluxoG (`fluxo-g-dashboard:8001`) verde em todos os fluxos |

---

## Riscos consolidados

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Worker imagens antigas (100+ dias) com regressões | Média | Alto | Escalonamento incremental, smoke test 30min entre |
| Queen Redis migration introduz incompatibilidade API | Baixa | Médio | Testes unitários cobrindo todos os métodos do client |
| Orchestrator ns legacy tem state crítico | Baixa | Alto | Fase 1 reversível (scale=0); fase 2 só após 24h sem regressão |
| Istio sidecar tweaks afetam outros serviços | Baixa | Baixo | Mudanças apenas em annotations do approval-service |

---

## Métricas de sucesso

- **Throughput pipeline:** ≥10 intents/min processadas E2E em smoke test
- **Lag médio Kafka (todos os tópicos):** ≤5
- **Pods unhealthy:** 0
- **Erros Redis em 1h:** 0
- **Container restarts em 1h:** 0 em todos os pods do pipeline
- **Duplicação consumer groups:** 0
