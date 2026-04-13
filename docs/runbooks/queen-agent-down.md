# Runbook: Queen Agent Down

**Alerta:** `QueenAgentDown`
**Severidade:** Critical
**Caminho:** `coordination -> leadership`

---

## Descrição

O Queen Agent está inativo ou não responde há mais de 3 minutos. O Queen Agent é responsável pela coordenação estratégica e liderança do sistema Neural Hive Mind.

## Impacto

- **Alto:** Sistema sem coordenação central
- Workers podem ficar orfãos ou sem direção
- Novas tarefas não serão distribuídas
- Decisões estratégicas não serão tomadas

## Primeiras Ações (5 minutos)

### 1. Verificar Status do Pod

```bash
# Ver pods do Queen Agent
kubectl get pods -n neural-hive -l app=queen-agent

# Ver status detalhado
kubectl describe pod -n neural-hive <pod-name>
```

### 2. Verificar Logs Recentes

```bash
# Logs do container principal
kubectl logs -n neural-hive <pod-name> --tail=100

# Logs anteriores se o pod reiniciou
kubectl logs -n neural-hive <pod-name> --previous --tail=100
```

### 3. Verificar Métricas

```bash
# Port-forward para Prometheus
kubectl port-forward -n observability svc/neural-hive-prometheus-kub-prometheus 9090:9090

# Query: up{job="queen-agent"}
# Query: rate(queen_agent_requests_total[5m])
```

## Diagnóstico

### Causa Comum 1: Pod CrashLoopBackOff

**Sintomas:** Pod reiniciando continuamente

**Diagnóstico:**
```bash
kubectl get pods -n neural-hive -l app=queen-agent
kubectl describe pod -n neural-hive <pod-name> | grep -A 10 Events:
```

**Resolução:**
1. Verificar logs para identificar o erro
2. Corrigir a causa raiz (config, dependência, recurso)
3. Se for erro transitório, considerar livenessProbe ajustado

### Causa Comum 2: Resource Limits

**Sintomas:** Pod OOMKilled ou throttling de CPU

**Diagnóstico:**
```bash
kubectl top pod -n neural-hive <pod-name>
kubectl describe pod -n neural-hive <pod-name> | grep -A 5 Limits
```

**Resolução:**
1. Aumentar limits de CPU/Memory no deployment
2. Verificar se há memory leak
3. Configurar HPA se necessário

### Causa Comum 3: Dependências Indisponíveis

**Sintomas:** Erros de conexão no startup

**Diagnóstico:**
```bash
# Verificar dependências
kubectl get pods -n neural-hive -l app=mongodb
kubectl get pods -n neural-hive -l app=redis
kubectl get pods -n neural-hive -l app=kafka
```

**Resolução:**
1. Restaurar dependências primeiro
2. Reiniciar Queen Agent após dependências OK

### Causa Comum 4: Problema de Liderança

**Sintomas:** Pod rodando mas sem liderar

**Diagnóstico:**
```bash
# Verificar estado de liderança
kubectl logs -n neural-hive <pod-name> | grep -i "leader\|election"

# Query: queen_agent_is_leader
```

**Resolução:**
1. Verificar se há outro pod líder (HA)
2. Forçar re-eleição se necessário
3. Verificar configuration lock em MongoDB/Redis

## Ações de Recuperação

### Recuperação 1: Restart do Pod

```bash
# Delete pod para forçar restart
kubectl delete pod -n neural-hive <pod-name>

# Aguardar novo pod
kubectl wait --for=condition=Ready pod -n neural-hive -l app=queen-agent --timeout=120s
```

### Recuperação 2: Rollback do Deployment

```bash
# Ver histórico de revisões
kubectl rollout history deployment/queen-agent -n neural-hive

# Rollback para versão anterior
kubectl rollout undo deployment/queen-agent -n neural-hive

# Verificar status
kubectl rollout status deployment/queen-agent -n neural-hive
```

### Recuperação 3: Scale Up (se HA)

```bash
# Garantir réplicas mínimas
kubectl scale deployment/queen-agent -n neural-hive --replicas=2

# Verificar eleição de líder
kubectl logs -n neural-hive -l app=queen-agent | grep -i "elected"
```

### Recuperação 4: Debug Interativo

```bash
# Criar pod de debug
kubectl run debug-queen -n neural-hive --rm -i --tty --image=nicolaka/netshoot -- bash

# Testar conectividade
nc -zv queen-agent.neural-hive.svc.cluster.local 8006
```

## Verificação Pós-Recovery

```bash
# 1. Verificar pod healthy
kubectl get pods -n neural-hive -l app=queen-agent

# 2. Verificar liderança estabelecida
kubectl logs -n neural-hive -l app=queen-agent --tail=20 | grep -i "leader"

# 3. Verificar workers conectados
kubectl logs -n neural-hive -l app=queen-agent | grep "workers connected"

# 4. Verificar métricas no Prometheus
# Query: up{job="queen-agent"} == 1
# Query: queen_agent_active_workers > 0
# Query: queen_agent_is_leader == 1
```

## Escalation

| Tempo | Ação |
|-------|------|
| 5 min | Primeiro respondente investiga |
| 15 min | Escalar para time de plataforma se não resolvido |
| 30 min | Escalar para arquitecto se crítico |
| 1 hora | Considerar incidente maior |

## Prevenção

### Melhorias de Configuração

1. **Pod Disruption Budget**
   ```yaml
   apiVersion: policy/v1
   kind: PodDisruptionBudget
   metadata:
     name: queen-agent-pdb
   spec:
     minAvailable: 1
     selector:
       matchLabels:
         app: queen-agent
   ```

2. **HorizontalPodAutoscaler**
   ```yaml
   apiVersion: autoscaling/v2
   kind: HorizontalPodAutoscaler
   metadata:
     name: queen-agent-hpa
   spec:
     scaleTargetRef:
       apiVersion: apps/v1
       kind: Deployment
       name: queen-agent
     minReplicas: 2
     maxReplicas: 5
     metrics:
     - type: Resource
       resource:
         name: cpu
         target:
           type: Utilization
           averageUtilization: 70
   ```

3. **Resources Adequados**
   ```yaml
   resources:
     requests:
       cpu: 500m
       memory: 512Mi
     limits:
       cpu: 1000m
       memory: 1Gi
   ```

## Referências

- **Dashboard:** [Queen Agent Dashboard](http://grafana.observability.svc.cluster.local:3000/d/queen-agent-dashboard)
- **Documentação:** `docs/services/queen-agent.md`
- **Responsável:** Platform Team

---

**Última atualização:** 2026-04-13
**Versão:** 1.0
