# Runbook — Worker Fleet Reactivation (TR-2)

> Spec: `.agent-os/specs/2026-05-22-pipeline-flow-recovery/` (TR-2)
> Depende de: TR-1 (Queen Redis cluster) estável em produção

## Contexto

Os 6 deployments da worker fleet (`worker-agents`, `analyst-agents`,
`guard-agents`, `optimizer-agents`, `scout-agents`,
`self-healing-engine`) estão em `0/0` desired há ≥132 dias. Pipeline
downstream do Orchestrator (Flow D) não pode executar tickets.

**Causa raiz identificada:** os pod templates não declaravam as labels
exigidas pelo Gatekeeper constraint `neural-hive-pod-labels` (`app`,
`component`, `version`). Cada `kubectl scale --replicas=N` falhava
silenciosamente no admission webhook → deploy ficava em `0/N`.

Este PR/branch corrigiu os charts. O runbook abaixo guia a reactivação
incremental.

---

## Pré-requisitos

1. **TR-1 merged e queen-agent estável em runtime:**
   ```bash
   kubectl logs -n neural-hive deploy/queen-agent --since=10m | grep CLUSTERDOWN | wc -l
   # Deve devolver 0.
   ```

2. **Pre-flight check passa:**
   ```bash
   python3 scripts/tr2_preflight_check.py
   echo "Exit code: $?"   # Esperado: 0
   ```

3. **Imagens GHCR existem** (rápido, sem cluster):
   ```bash
   for chart in worker-agents analyst-agents guard-agents \
                optimizer-agents scout-agents self-healing-engine; do
     img=$(yq '.image.repository + ":" + .image.tag' helm-charts/$chart/values.yaml)
     echo "Verificando $img..."
     docker manifest inspect "$img" >/dev/null 2>&1 && echo "  OK" || echo "  MISSING"
   done
   ```

4. **ConfigMaps + Secrets já existem** no ns `neural-hive` (criados em
   deploys anteriores; Flux mantém-nos):
   ```bash
   kubectl -n neural-hive get cm,secret | grep -E "worker-agents|analyst-agents|guard-agents|optimizer-agents|scout-agents|self-healing-engine"
   ```

5. **Capacidade do cluster:** os 6 deployments somam um pico de ~30 pods
   (HPA max). Validar headroom de CPU/memória:
   ```bash
   kubectl top nodes
   kubectl describe nodes | grep -A5 "Allocated resources"
   ```

---

## Sequência de execução

### Justificativa da ordem

A ordem é deliberada: `optimizer → scout → analyst → guard → worker →
self-healing-engine`. Razões:

- **`optimizer-agents` primeiro:** menor blast-radius, 1 réplica
  apenas. Validar conectividade Kafka/Redis sem comprometer outros
  workers.
- **`self-healing-engine` por último:** componente de auto-remediação
  dos restantes workers. Se entrar primeiro com política agressiva,
  pode reiniciar pods que estão intencionalmente a 0/N ou interferir
  com o scale-up incremental. Durante as janelas de smoke 30 min dos
  primeiros 5 workers, **o operador é a única salvaguarda** —
  monitorar manualmente os critérios de continuação.

Ordem do scale-up (do menor risco para o maior, com smoke 30min entre
cada — spec TR-2 subtasks 3.2–3.7):

| # | Deployment | Réplicas alvo | Smoke duration |
|---|---|---|---|
| 1 | `optimizer-agents` | 1 | 30 min |
| 2 | `scout-agents` | 2 | 30 min |
| 3 | `analyst-agents` | 2 | 30 min |
| 4 | `guard-agents` | 2 | 30 min |
| 5 | `worker-agents` | 2 | 30 min |
| 6 | `self-healing-engine` | 2 | 30 min |

### Para CADA deployment

**1. Scale-up:**
```bash
kubectl scale -n neural-hive deploy/<DEPLOYMENT> --replicas=<N>
```

**2. Aguardar pods Ready:**
```bash
kubectl -n neural-hive rollout status deploy/<DEPLOYMENT> --timeout=5m
```

**3. Validar Kafka registration nos logs:**
```bash
kubectl -n neural-hive logs deploy/<DEPLOYMENT> --since=2m \
  | grep -iE "kafka.*connected|consumer.*group|service-registry.*registered"
# Esperado: pelo menos uma entrada de cada padrão.
```

**4. Smoke test 30 min — janela de observação:**
```bash
# Em loop, a cada 5 min:
kubectl -n neural-hive get pod -l app=<DEPLOYMENT> -o wide
kubectl -n neural-hive top pod -l app=<DEPLOYMENT>
kubectl -n neural-hive logs deploy/<DEPLOYMENT> --since=5m \
  | grep -iE "error|exception|circuit.*open" | head
```

**5. Critérios de continuação:** se durante 30 min consecutivos:
   - `RESTARTS = 0` em todos os pods
   - Zero `error|exception` críticos nos logs
   - Memória < 80% do limit
   - CPU < 80% do limit

   → avançar para o próximo deployment.

**6. Rollback trigger:** se qualquer critério acima falhar:
```bash
kubectl scale -n neural-hive deploy/<DEPLOYMENT> --replicas=0
# Investigar logs e métricas; voltar a este runbook apenas após
# entender a causa raiz.
```

---

## Validação E2E final (subtask 3.8)

Após os 6 deployments scaled e estáveis 30min cada:

**1. Injectar 5 test intents via Gateway:**
```bash
for i in $(seq 1 5); do
  curl -X POST https://gateway.neural-hive.local/api/v1/intent \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"Test intent $i — E2E smoke\", \"priority\": \"low\"}"
done
```

**2. Validar `execution.tickets` recebe ≥5 messages:**
```bash
# Consumer group ID vem do ConfigMap (configurável via
# helm-charts/worker-agents/values.yaml::config.kafka.consumerGroup).
GROUP=$(kubectl -n neural-hive get cm worker-agents-config \
  -o jsonpath='{.data.KAFKA_CONSUMER_GROUP}')
kubectl -n kafka exec -it neural-hive-kafka-0 -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group "${GROUP:-worker-agents}" --describe
# Coluna LOG-END-OFFSET deve ter incrementado em pelo menos 5.
```

**3. Validar `execution.results` recebe ≥5 messages:**
```bash
kubectl -n kafka exec -it neural-hive-kafka-0 -- \
  kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic execution.results --from-beginning --max-messages 5 --timeout-ms 60000
```

**4. HPA targets numéricos (não `<unknown>`):**
```bash
kubectl -n neural-hive get hpa
# Coluna TARGETS deve ter percentagens ou valores absolutos, não `<unknown>`.
```

---

## Métricas-chave

| Métrica | Threshold | Onde |
|---|---|---|
| `kube_pod_container_status_restarts_total{namespace="neural-hive",pod=~"<deployment>.*"}` | == 0 (1h) | Grafana |
| `kafka_consumergroup_lag{group="worker-agents",topic="execution.tickets"}` | < 10 sustained | Grafana |
| `container_memory_working_set_bytes / container_spec_memory_limit_bytes` | < 0.8 | Grafana |
| `rate(container_cpu_usage_seconds_total[5m]) / container_spec_cpu_quota` | < 0.8 | Grafana |

---

## Riscos conhecidos

1. **Imagens antigas (≥100 dias):** se houve mudanças incompatíveis no
   resto do stack durante este período (proto schemas, Kafka topics
   renomeados, env vars), pods podem entrar em CrashLoopBackOff.
   Mitigação: escalonamento incremental + smoke 30min antes do próximo.

2. **CPU saturation Contabo:** o cluster está em nós shared-vCPU.
   30 pods novos × ~200m CPU request = 6 vCPU adicionais. Validar
   `kubectl top nodes` antes de cada step.

3. **Kafka consumer-group rebalances:** scale-up de N consumers no
   mesmo grupo dispara N rebalances. Pode haver janela de 30-60s sem
   consumo enquanto rebalance corre.

4. **Gatekeeper drift:** se a constraint
   `neural-hive-pod-labels` for actualizada (adicionar labels), este
   fix de TR-2 ficará incompleto. Re-correr o pre-flight check.

5. **PDB `minAvailable: 1` em workloads a 0/N (`worker-agents`,
   `guard-agents`, `scout-agents`, `self-healing-engine`):** com 0
   réplicas, o constraint `minAvailable: 1` é estruturalmente
   impossível. A eviction API (`kubectl drain`, cluster autoscaler,
   Flux reconcile) recusa evictions de pods nos nós onde estes
   workloads pretendem estar — bloqueia node-drains até o workload
   ter ≥1 pod Running. **Não agendar manutenção de nós durante a
   execução de TR-2.** `kubectl rollout status` não detecta isto;
   só sinais externos (drain stuck, alertas Flux) o revelam.

6. **Outros charts em `neural-hive` ainda não-compliant com
   `neural-hive-pod-labels`:** este PR só corrigiu os 6 worker charts.
   `approval-service`, `consensus-engine` e restantes ainda usam só
   `app.kubernetes.io/*` (sem labels bare `app`/`component`/`version`).
   **Não disparar re-deploys destes serviços durante TR-2** — o
   Gatekeeper rejeitaria a criação dos pods (constraint default action
   é `deny`). Ticket separado para alinhar todos os charts.

7. **`schemaRegistryUrl: ""` no `worker-agents`
   (JSON fallback):** o values.yaml tem um TODO "Desabilitado para
   forçar fallback JSON (mensagens antigas em JSON)". Se a pipeline
   upstream (STE, orchestrator) entretanto migrou para Avro nos
   tópicos `execution.tickets` ou `execution.results`, o `worker-agents`
   vai crash-loop em deserialização. **Antes do step 5 (scale
   worker-agents), validar o formato actual das mensagens:**
   ```bash
   kubectl -n kafka exec -it neural-hive-kafka-0 -- \
     kafka-console-consumer.sh --bootstrap-server localhost:9092 \
     --topic execution.tickets --max-messages 1 --timeout-ms 10000 \
     --from-beginning | head -c 100
   ```
   Se a saída começar por `{` (JSON) → OK. Se começar por bytes
   binários (Avro magic byte `0x00`) → **ABORT scale-up** e abrir
   ticket para migrar `worker-agents` para Avro consumer.

---

## Critérios de aceitação TR-2 (spec)

- [ ] `kubectl get hpa -n neural-hive` mostra TARGETS numérico (não
      `<unknown>`) para os 6 HPAs.
- [ ] `kafka-consumer-groups --describe --group worker-agents` mostra
      LAG = 0 em `execution.tickets` após injectar 5 test intents.
- [ ] `kubectl logs deploy/<each-worker> --since=1h | grep -iE
      "CrashLoop|OOMKill"` retorna 0 entradas.
- [ ] `execution.results` recebe ≥5 messages após injecção.

---

## Referências

- Spec: `.agent-os/specs/2026-05-22-pipeline-flow-recovery/spec.md`
- Technical spec: `.agent-os/specs/2026-05-22-pipeline-flow-recovery/sub-specs/technical-spec.md`
- Pre-flight script: `scripts/tr2_preflight_check.py`
- Constraints Gatekeeper: `gatekeeper/constraints/neural-hive-constraints.yaml`
- PR TR-1 (dependência): #102
- PR TR-4 (independente): #101
