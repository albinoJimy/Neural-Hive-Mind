# Technical Specification

This is the technical specification for the spec detailed in @.agent-os/specs/2026-05-22-pipeline-flow-recovery/spec.md

---

## TR-1 — Queen Agent: Migrar Redis client para cluster-mode

### Evidência de raiz
- Pod log:
  ```
  CLUSTERDOWN Hash slot not served
  event=acquire_leadership_failed logger=src.services.leader_election
  event=context_get_failed key=telemetry:snapshot:latest
  ```
- Código actual em `services/queen-agent/src/clients/redis_client.py:23-30`:
  ```python
  nodes = self.settings.REDIS_CLUSTER_NODES.split(",")
  self.client = Redis(                       # ← standalone client
      host=nodes[0].split(":")[0],           # ← só primeiro nó!
      port=int(nodes[0].split(":")[1]),
      password=self.settings.REDIS_PASSWORD,
      ssl=self.settings.REDIS_SSL_ENABLED,
      decode_responses=True,
  )
  ```
- Cluster Redis confirmado saudável (16384 slots, 6 nodes, `cluster_state:ok`).
- Slots distribuídos por 3 master nodes (10.244.2.73, 10.244.3.214, 10.244.2.243). Operação contra slot fora do nó-alvo dispara erro `CLUSTERDOWN`.

### Mudanças de código
**Ficheiro:** `services/queen-agent/src/clients/redis_client.py`

```python
from redis.asyncio.cluster import RedisCluster, ClusterNode
# ...

async def initialize(self) -> None:
    try:
        nodes = [
            ClusterNode(
                host=h.split(":")[0],
                port=int(h.split(":")[1]) if ":" in h else 6379,
            )
            for h in self.settings.REDIS_CLUSTER_NODES.split(",")
        ]
        self.client = RedisCluster(
            startup_nodes=nodes,
            password=self.settings.REDIS_PASSWORD or None,
            ssl=self.settings.REDIS_SSL_ENABLED,
            decode_responses=True,
            require_full_coverage=False,
            reinitialize_steps=5,
        )
        await self.client.ping()
        logger.info("redis_cluster_initialized", node_count=len(nodes))
    except Exception as e:
        logger.exception("redis_cluster_initialization_failed", error=str(e))
        raise
```

### Mudanças de deployment
**Ficheiro:** `services/queen-agent/k8s/deployment.yaml` (ou Helm `values.yaml`)

Adicionar 3 env vars:
```yaml
- name: REDIS_CLUSTER_NODES
  value: "neural-hive-cache.redis-cluster.svc.cluster.local:6379"
- name: REDIS_SSL_ENABLED
  value: "false"          # cluster Redis interno sem TLS
- name: REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: redis-secret
      key: password
```

### Validação
1. `kubectl exec queen-agent-pod -- python -c "from src.clients.redis_client import RedisClient; ..."` → `redis_cluster_initialized`.
2. `kubectl logs deploy/queen-agent | grep CLUSTERDOWN | wc -l` → `0` durante 60 minutos.
3. Consensus engine deixa de emitir `grpc_get_system_status_failed`.

### Risco
- **Médio**. Mudança requer rolling restart de queen-agent (3 réplicas). Se a nova lógica de cluster falhar, leader election fica indisponível mas pipeline continua (queen-agent já é tolerante a falhas).

---

## TR-2 — Worker fleet reactivation

### Evidência
```
neural-hive/worker-agents:         0/0   (revision 101, image abaa59f)
neural-hive/analyst-agents:        0/0   132d sem replicas
neural-hive/guard-agents:          0/0   132d
neural-hive/optimizer-agents:      0/0   132d
neural-hive/scout-agents:          0/0   132d
neural-hive/self-healing-engine:   0/0   132d
```
- HPA min=2 max=10 mas réplicas = 0 → indica `kubectl scale deploy worker-agents --replicas=0` aplicado manualmente, ou Gatekeeper a rejeitar criação.
- Imagem actual `worker-agents:abaa59f` é a mesma do specialist-business (commit recente), provavelmente válida.

### Pré-requisitos
1. Verificar que Gatekeeper não está a bloquear (audit 46 violações `must-have-app-label-all` no cluster).
2. Validar que imagens existem no GHCR (`ghcr.io/albinojimy/neural-hive-mind/{worker-agents,analyst-agents,...}:abaa59f`).
3. Validar configmaps/secrets referenciados estão presentes.

### Mudanças
**Por deployment**, escalar para `replicas: <min HPA>`:
```bash
kubectl scale deploy -n neural-hive worker-agents --replicas=2
kubectl scale deploy -n neural-hive analyst-agents --replicas=2
kubectl scale deploy -n neural-hive guard-agents --replicas=2
kubectl scale deploy -n neural-hive optimizer-agents --replicas=1
kubectl scale deploy -n neural-hive scout-agents --replicas=2
kubectl scale deploy -n neural-hive self-healing-engine --replicas=2
```

### Validação
1. Cada deployment chega a `AVAILABLE = desired`.
2. Logs mostram conexão Kafka + service-registry registration.
3. Após injectar 5 intents de teste:
   - `execution.tickets` recebe ≥5 messages
   - `kafka-consumer-groups --group worker-agents --describe` mostra LAG = 0
   - `execution.results` recebe ≥5 messages

### Risco
- **Médio-Alto**. Reactivar 6 deployments com imagens antigas pode reintroduzir comportamentos não testados há 100+ dias. Mitigação: ativar 1 deployment de cada vez, validar 30min antes do próximo.

---

## TR-3 — Consolidação namespace `orchestrator-dynamic`

### Evidência
```
neural-hive/orchestrator-dynamic            2/2  85d   0 restarts (estável)
orchestrator-dynamic/orchestrator-dynamic   2/3  24d   110+ restarts/pod
```
- Ambos consomem do **mesmo consumer group** Kafka `orchestrator-dynamic` em `plans.consensus`, `cognitive-plans-approval-responses`, `execution.results`.
- Kafka rebalancing redistribui partições entre 4 consumers (2 ns × 2 replicas) → processamento não-determinístico.
- Os pods em `orchestrator-dynamic/` têm 110+ restarts em 24d ≈ 4–5 restarts/dia → recurring crash loop não diagnosticado.

### Mudanças
**Fase 1 (mitigação imediata, reversível):**
```bash
kubectl scale deploy -n orchestrator-dynamic orchestrator-dynamic --replicas=0
kubectl scale deploy -n orchestrator-dynamic orchestrator-dynamic-temporal-worker --replicas=0
```

**Fase 2 (após 24h sem regressão):**
```bash
helm uninstall orchestrator-dynamic -n orchestrator-dynamic   # se for Helm-managed
# OU
kubectl delete deploy,svc,sa,configmap,secret,hpa,pdb -n orchestrator-dynamic -l app.kubernetes.io/name=orchestrator-dynamic
kubectl delete namespace orchestrator-dynamic
```

### Validação
1. **Fase 1:** após scale-down, todas as partições dos 5 tópicos de orchestrator são consumidas só por `neural-hive/orchestrator-dynamic` (2 consumers).
2. Temporal: `temporal workflow list` durante 24h não mostra workflows duplicados.
3. **Fase 2:** namespace removido sem afectar fluxos.

### Risco
- **Médio**. Risco de perder estado do ns legacy. Mitigação: confirmar com `kubectl get all -n orchestrator-dynamic` que não há PVCs nem state externo antes de eliminar.

---

## TR-4 — Approval-service Istio sidecar stability

### Evidência
- `approval-service-5b48bc7b56-pdhck`: **66 restarts em 28h** (cada ~25 min).
- Sidecar `istio-proxy` log:
  ```
  Request to probe app failed: Get "http://10.244.6.57:8080/health": context deadline exceeded
  ```
- A aplicação responde 200 OK directamente. Problema é o **sidecar a proxiar /health** entre kubelet (15020) e app (8080) com timeout.
- Sidecar tem limites generosos: CPU=2, Memory=1Gi.
- Pod no nó `vmi3313361` (substituto, vCPU partilhado Contabo) — possível CPU throttling.

### Hipóteses de causa
1. **H1 — App CPU throttling sob carga Istio mTLS** → sidecar TLS handshake + app sync work conflict por vCPU.
2. **H2 — Probe timeout demasiado curto** (default 1s) para o caminho kubelet → sidecar → app via 127.0.0.6:80.
3. **H3 — XDS reconnect cycle a cada ~30min** força redescoberta de endpoints durante a qual probes falham.

### Mudanças propostas
**Ficheiro:** `services/approval-service/k8s/deployment.yaml`

```yaml
spec:
  template:
    metadata:
      annotations:
        # Aumentar timeout do probe rewrite do sidecar
        proxy.istio.io/config: |
          terminationDrainDuration: 30s
          holdApplicationUntilProxyStarts: true
          proxyMetadata:
            ISTIO_META_INTERCEPTION_MODE: REDIRECT
    spec:
      containers:
        - name: approval-service
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 30        # ← era 10s, dar mais espaço
            timeoutSeconds: 10       # ← era 1s, dar mais espaço
            failureThreshold: 5      # ← era 3
```

**Adicionalmente**, considerar `sidecar.istio.io/proxyCPU: 500m` request (não usar `limits` excessivos para evitar throttling).

### Validação
1. Pod estável durante 1h: `RESTARTS=0` na coluna do `kubectl get pod`.
2. Sidecar log mostra XDS reconnect máximo 1×/hora.
3. `pilot_proxy_convergence_time_p99` < 5s.

### Risco
- **Baixo**. Mudanças apenas em probe timing — só relaxa tolerância. Reversível instantaneamente.

---

## Dependências externas

| Dependência | Versão | Justificação |
|---|---|---|
| `redis>=5.0` (Python) | já presente | API `redis.asyncio.cluster.RedisCluster` |

Nenhuma nova lib externa requerida.

---

## Ordem de execução recomendada

1. **TR-4** primeiro (baixo risco, estabiliza approval-service).
2. **TR-1** depois (corrige Queen Redis, desbloqueia Flow B).
3. **TR-2** após TR-1 confirmado (workers escalam contra cluster Redis funcional).
4. **TR-3** por último (consolidação ns, irreversible parcialmente).
