# Runbook — Orchestrator Dynamic Namespace Consolidation (TR-3)

> Spec: `.agent-os/specs/2026-05-22-pipeline-flow-recovery/` (TR-3)
> Depende de: TR-1 + TR-2 estáveis (queen-agent saudável + workers
> consumindo tickets) por pelo menos 24 h consecutivas

## Contexto

Existem **dois deployments** `orchestrator-dynamic` no cluster:

| Namespace | Origem | Estado |
|---|---|---|
| `neural-hive` (ou `neural-hive-{dev,staging,prod}`) | Flux-managed (`infrastructure/fluxcd/clusters/*/services/orchestrator-dynamic.yaml`) | **Canónico** — 2/2 OK, 0 restarts (85d) |
| `orchestrator-dynamic` | Deploy manual (`kubectl apply` / `helm install` legacy, **não em git**) | 2/3 com ~110 restarts em 24d |

Ambos partilham **5 consumer groups Kafka** distintos. Cada um expõe
uma via de split-brain durante a transição:

| Consumer group | Tópico consumido | Consumer |
|---|---|---|
| `orchestrator-dynamic` | `plans.consensus` | `decision_consumer` |
| `orchestrator-dynamic-flow-c` | (multi-topic Flow C) | `FlowCConsumer` |
| `orchestrator-dynamic-approval-responses` | `cognitive-plans-approval-responses` | `ApprovalResponsesConsumer` |
| `orchestrator-execution-results` | `execution.results` | `execution_result_consumer` |
| `orchestrator-sla-alerts` | `sla.events` | `sla_alert_consumer` |

Resultado actual: rebalances entre 4 consumers (2 ns × 2 réplicas) em
**todos** os 5 grupos, processamento não-determinístico, risco de
split-brain de workflows Temporal.

**Decisão arquitetural:** o namespace `neural-hive*` é canónico (managed
por Flux, sob controlo de versão). O namespace `orchestrator-dynamic`
deve ser eliminado.

---

## Pré-requisitos

1. **TR-1 estável há ≥24h:**
   ```bash
   kubectl logs -n neural-hive deploy/queen-agent --since=24h \
     | grep CLUSTERDOWN | wc -l
   # Esperado: 0
   ```

2. **TR-2 estável há ≥24h:**
   ```bash
   kubectl get pods -n neural-hive -l 'app in (worker-agents,analyst-agents,guard-agents,optimizer-agents,scout-agents,self-healing-engine)' \
     -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.containerStatuses[0].restartCount}{"\n"}{end}'
   # Cada pod deve ter RESTARTS=0 ou número estável (sem incrementos no último 1h)
   ```

3. **Pre-flight passa sem blockers:**
   ```bash
   python3 scripts/tr3_preflight_check.py
   echo "Exit code: $?"   # 0 = OK proceder
   ```

   Atenção especial a:
   - PVCs no ns legacy (blocker — confirmar que state é descartável)
   - Imagens divergentes entre legacy e canónico (warning)
   - Secrets custom (Vault tokens, API keys específicas)

4. **Backup do estado Temporal:** os workflows Temporal são
   persistidos no servidor Temporal (não nos pods do orchestrator), pelo
   que a eliminação dos pods do orchestrator NÃO perde workflows.
   Confirmar:
   ```bash
   kubectl exec -n temporal sts/temporal -- \
     tctl --ns default workflow list -p 1 | head -20
   ```
   Se houver workflows `Running`, anotar IDs; vão continuar a processar
   no orchestrator do ns canónico após Fase 1.

---

## Fase 1 — Scale-down reversível (24 h observação)

### Step 1.1: Listar deployments no ns legacy

```bash
kubectl get deploy,svc,cm,secret,hpa,pdb,pvc -n orchestrator-dynamic
# Anotar todos os recursos. Vão ser eliminados na Fase 2.
```

### Step 1.2a: Scale = 0 do deployment principal

```bash
kubectl scale -n orchestrator-dynamic deploy/orchestrator-dynamic --replicas=0
# Verificar resultado:
kubectl get deploy orchestrator-dynamic -n orchestrator-dynamic \
  -o jsonpath='{.spec.replicas}'   # Deve devolver 0
```

### Step 1.2b: Scale = 0 do temporal-worker (explícito)

A spec lista o `orchestrator-dynamic-temporal-worker` como segundo
deployment a parar. Tratar separado para verificação clara:

```bash
if kubectl get deploy orchestrator-dynamic-temporal-worker -n orchestrator-dynamic >/dev/null 2>&1; then
  kubectl scale -n orchestrator-dynamic \
    deploy/orchestrator-dynamic-temporal-worker --replicas=0
  kubectl get deploy orchestrator-dynamic-temporal-worker -n orchestrator-dynamic \
    -o jsonpath='{.spec.replicas}'   # Deve devolver 0
else
  echo "INFO: temporal-worker não existe nesta instalação — skip."
fi
```

### Step 1.2c: Aguardar expiração session_timeout

```bash
# aiokafka usa session_timeout_ms=30000 (ver flow_c_consumer.py:253).
# Kafka só remove members após este timeout + rebalance.
echo "Aguardando 60s para session_timeout expirar..."
sleep 60
```

### Step 1.3: Confirmar TODOS os 5 consumer groups consolidados

Snapshot dos IPs esperados (apenas pods do ns canónico):

```bash
EXPECTED_IPS=$(kubectl get pods -n neural-hive -l app=orchestrator-dynamic \
  -o jsonpath='{range .items[*]}{.status.podIP}{"\n"}{end}' | sort -u)
echo "Pods canónicos: $EXPECTED_IPS"
```

Verificar cada um dos 5 grupos:

```bash
for GROUP in orchestrator-dynamic orchestrator-dynamic-flow-c \
             orchestrator-dynamic-approval-responses \
             orchestrator-execution-results \
             orchestrator-sla-alerts; do
  echo "=== $GROUP ==="
  kubectl exec -n kafka neural-hive-kafka-0 -- \
    kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
    --group "$GROUP" --describe 2>/dev/null \
    | awk 'NR>1 && $8 != "" && $8 != "HOST" {print $8}' \
    | sort -u
  # Critério de aceitação: TODOS os HOSTs devem estar em $EXPECTED_IPS.
done
```

**Critério automatizável:** o pre-flight check (`scripts/tr3_preflight_check.py`)
fornece a contagem distinta de CONSUMER-IDs por grupo. Se exceder 2 em
qualquer grupo, há split residual.

### Step 1.4: Observação 24 h

Métricas a observar (Grafana / Prometheus):

| Métrica | Threshold | Acção se falhar |
|---|---|---|
| `kafka_consumergroup_lag{group="orchestrator-dynamic"}` | < 100 sustained | Investigar; possível rollback Fase 1 |
| Temporal `temporal_workflow_completed_total` taxa | ≥ baseline pré-Fase 1 | Idem |
| `kube_pod_container_status_restarts_total{namespace="neural-hive",pod=~"orchestrator-dynamic.*"}` | == 0 (24 h) | Investigar pods canónicos |
| Logs `kubectl logs deploy/orchestrator-dynamic -n neural-hive` | sem `DEADLINE_EXCEEDED`, `RACE`, `DUPLICATE_WORKFLOW` | Rollback |

### Step 1.5: Rollback Fase 1 (reversível instantaneamente)

Se qualquer critério falhar:

```bash
kubectl scale -n orchestrator-dynamic deploy/orchestrator-dynamic --replicas=2
# Restaurar réplicas anteriores. Verificar consumer group volta ao split.
```

Após rollback, abrir ticket de investigação. **Não prosseguir para
Fase 2** enquanto a causa não for entendida.

---

## Fase 2 — Eliminação (irreversível)

Executar **apenas após 24 h de Fase 1 sem regressão**.

### Step 2.1: Confirmação final

```bash
python3 scripts/tr3_preflight_check.py --json | jq '.blockers, .warnings'
# Re-correr 24h depois para garantir que o estado não mudou.
```

### Step 2.2: Identificar tipo de instalação

```bash
helm list -n orchestrator-dynamic
```

Se houver releases Helm → usar `helm uninstall`. Se não → `kubectl delete`
manifest a manifest.

### Step 2.3: Eliminar recursos

**Variante A — Helm-managed:**
```bash
helm uninstall orchestrator-dynamic -n orchestrator-dynamic
```

**Variante B — Manifest manual:**

*Step 2.3.B.1 — Eliminar workloads e services* (reversível com
re-deploy via Flux ou re-aplicar manifest legacy se backup existir):
```bash
for kind in hpa pdb deploy statefulset daemonset job cronjob; do
  kubectl delete $kind --all -n orchestrator-dynamic --wait=true
done
kubectl delete svc --all -n orchestrator-dynamic
kubectl delete cm,secret -n orchestrator-dynamic --all
```

*Step 2.3.B.2 — Cross-check secrets antes de prosseguir:*
```bash
# Para cada secret custom reportado pelo pre-flight em `secrets_legacy`,
# confirmar que existe um par no ns canónico antes de descartar:
for SECRET in $(python3 scripts/tr3_preflight_check.py --json \
                | jq -r '.info.secrets_legacy[]?.name // empty'); do
  kubectl get secret "$SECRET" -n neural-hive >/dev/null 2>&1 \
    && echo "OK: $SECRET existe em neural-hive" \
    || echo "ATENÇÃO: $SECRET NÃO existe em neural-hive — não descartar!"
done
```

*Step 2.3.B.3 — Eliminar PVCs (IRREVERSÍVEL — confirmação interactiva):*
```bash
# CRITICAL: este passo destrói state local. O pre-flight bloqueia se
# detectar PVCs sem confirmação humana de descartabilidade. Aqui
# adicionar gate explícito:
PVC_LIST=$(kubectl get pvc -n orchestrator-dynamic -o name)
if [ -n "$PVC_LIST" ]; then
  echo "PVCs a eliminar:"
  echo "$PVC_LIST"
  read -p "Confirmar que estes PVCs são descartáveis [yes/no]? " confirm
  if [ "$confirm" = "yes" ]; then
    kubectl delete pvc --all -n orchestrator-dynamic
  else
    echo "ABORT: re-executar o runbook após confirmar destino dos PVCs."
    exit 1
  fi
fi
# Aguardar release dos PVs:
sleep 30
kubectl get pv | grep orchestrator-dynamic || echo "OK: PVs libertos"
```

### Step 2.4: Eliminar namespace

```bash
kubectl delete namespace orchestrator-dynamic
# Se ficar em Terminating > 60s, investigar finalizers:
kubectl get namespace orchestrator-dynamic -o json \
  | jq '.spec.finalizers, .status'
```

Se hang em `Terminating`, ver guia:
[Kubernetes — Stuck Namespace Termination](https://kubernetes.io/docs/tasks/administer-cluster/namespaces/#deleting-a-namespace)

### Step 2.5: Verificação pós-delete

```bash
# 1. Namespace removido
kubectl get ns orchestrator-dynamic 2>&1 | grep -q NotFound && echo "OK: ns removido"

# 2. PVCs em qualquer ns referenciando orchestrator-dynamic — devem ser 0
kubectl get pvc -A | grep orchestrator-dynamic && echo "REMAINING PVCs" \
  || echo "OK: sem PVCs órfãos"

# 3. PVs libertos
kubectl get pv | grep orchestrator-dynamic && echo "REMAINING PV" \
  || echo "OK: PVs limpos"

# 4. Expected Deliverable #4 da spec: apenas o deploy do ns canónico
kubectl get deploy -A | grep orchestrator-dynamic
# Esperado: linhas apenas em ns `neural-hive*`, NÃO `orchestrator-dynamic`.

# 5. Consumer groups continuam a funcionar com 1 set de consumers
for GROUP in orchestrator-dynamic orchestrator-dynamic-flow-c \
             orchestrator-dynamic-approval-responses \
             orchestrator-execution-results \
             orchestrator-sla-alerts; do
  echo "=== $GROUP ==="
  kubectl exec -n kafka neural-hive-kafka-0 -- \
    kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
    --group "$GROUP" --describe 2>/dev/null
done

# 6. Workflows Temporal sem duplicação — tentar CLI moderna `temporal`,
# fallback para `tctl` (legado).
TEMPORAL_POD=$(kubectl get pods -n temporal -l app=temporal -o name | head -1)
if kubectl exec -n temporal "$TEMPORAL_POD" -- which temporal >/dev/null 2>&1; then
  kubectl exec -n temporal "$TEMPORAL_POD" -- \
    temporal workflow list --namespace default --limit 10
elif kubectl exec -n temporal "$TEMPORAL_POD" -- which tctl >/dev/null 2>&1; then
  kubectl exec -n temporal "$TEMPORAL_POD" -- \
    tctl --ns default workflow list -p 1 | head -10
else
  echo "AVISO: nem temporal nem tctl disponíveis no pod $TEMPORAL_POD."
fi
```

---

## Critérios de aceitação (spec)

- [ ] **Fase 1:** após scale-down, todas as partições dos 5 tópicos de
      orchestrator consumidas apenas por `neural-hive/orchestrator-dynamic`
- [ ] **Fase 1:** Temporal `workflow list` durante 24 h não mostra
      workflows duplicados
- [ ] **Fase 2:** `kubectl get deploy -A | grep orchestrator-dynamic`
      mostra apenas a entrada em `neural-hive*/`
- [ ] **Fase 2:** namespace `orchestrator-dynamic` removido sem afectar
      fluxos
- [ ] PVCs e finalizers limpos

---

## Riscos conhecidos

1. **State em PVC não-replicado:** se o ns legacy tiver PVCs com state
   crítico (cache local de workflows, audit logs), `kubectl delete pvc`
   perde dados. Pre-flight reporta PVCs como **BLOCKER** — não avançar
   sem confirmação humana.

2. **Secrets divergentes:** Vault tokens, API keys ou TLS certs no ns
   legacy podem não existir no ns canónico. Cross-check com `kubectl
   get secret -n neural-hive` antes da Fase 2.

3. **Consumer group offset reset:** ao eliminar o membro legacy do grupo,
   o Kafka faz rebalance e atribui as partições ao membro canónico. Há
   uma janela de 30-60s sem consumo durante o rebalance. Aceitável.

4. **Workflows Temporal em flight:** se um workflow estava a ser
   processado pelo pod legacy no momento do scale-down, o Temporal
   re-atribui-o ao pod canónico no próximo poll. **Não há perda** —
   mas a re-atribuição depende do `schedule_to_start_timeout` do task
   queue (não configurado explicitamente neste serviço → default
   ilimitado do Temporal). Em prática, o re-poll do worker canónico
   acontece a cada poll cycle. Tempo de retomada varia com a carga;
   monitorar `temporal_workflow_completed_total` no Grafana durante a
   Fase 1 para detectar workflows estagnados.

5. **Imagens divergentes (legacy vs canónico):** pre-flight reporta como
   warning. Se o legacy tinha um build especial (hotfix manual, branch
   privado), a consolidação fá-lo desaparecer. Documentar
   explicitamente antes de proceder.

6. **Outros consumers no ns legacy:** se houver workloads que NÃO sejam
   `orchestrator-dynamic` no ns (ex.: jobs ad-hoc, debug pods), a
   eliminação do namespace mata-os também. Pre-flight lista todos os
   workloads detectados.

7. **Hooks Helm pre-delete:** se o chart legacy era Helm-managed com
   `pre-delete` hooks, `helm uninstall` corre-os primeiro. Confirmar com
   `helm get hooks orchestrator-dynamic -n orchestrator-dynamic` antes.

---

## Referências

- Spec: `.agent-os/specs/2026-05-22-pipeline-flow-recovery/spec.md`
- Technical spec: `.agent-os/specs/2026-05-22-pipeline-flow-recovery/sub-specs/technical-spec.md`
- Pre-flight script: `scripts/tr3_preflight_check.py`
- Flux HelmRelease canónico: `infrastructure/fluxcd/clusters/{dev,staging,prod}/services/orchestrator-dynamic.yaml`
- PR TR-1 (dependência): #102
- PR TR-2 (dependência): #103
- PR TR-4: #101
