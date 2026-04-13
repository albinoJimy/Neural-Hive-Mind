# Runbook: Consensus Engine No Quorum

**Alerta:** `ConsensusEngineNoQuorum`
**Severidade:** Critical
**Camada:** cognitive

---

## Descrição

O Consensus Engine não tem quórum mínimo de especialistas (menos de 3 ativos). Isso significa que decisões cognitivas não podem ser tomadas de forma confiável.

## Impacto

- **Crítico:** Sistema não pode tomar decisões cognitivas
- Planos não serão aprovados ou rejeitados
- Consenso entre especialistas não é possível
- Gateway de intenções pode acumular backlog

## Primeiras Ações (5 minutos)

### 1. Verificar Especialistas Ativos

```bash
# Ver pods de especialistas
kubectl get pods -n neural-hive -l layer=cognitive

# Ver contagem de especialistas ativos
kubectl get pods -n neural-hive -l specialist=true
```

### 2. Verificar Métricas de Quórum

```bash
# Port-forward para Prometheus
kubectl port-forward -n observability svc/neural-hive-prometheus-kub-prometheus 9090:9090

# Query: consensus_quorum_size
# Query: consensus_active_specialists
# Query: up{job=~".*specialist.*"}
```

### 3. Identificar Especialistas Down

```bash
# Ver status de cada especialista
for specialist in business technical architecture behavior evolution; do
  echo "=== $specialist ==="
  kubectl get pods -n neural-hive -l specialist=$specialist
done
```

## Diagnóstico

### Causa Comum 1: Especialistas em CrashLoopBackOff

**Diagnóstico:**
```bash
kubectl get pods -n neural-hive -l layer=cognitive
kubectl describe pod -n neural-hive <pod-name> | grep -A 10 Events:
```

**Resolução:**
1. Verificar logs de cada especialista com problema
2. Corrigir causa raiz individualmente
3. Priorizar especialistas críticos (business, technical)

### Causa Comum 2: Network Policies Bloqueando

**Diagnóstico:**
```bash
# Verificar NetworkPolicies
kubectl get networkpolicies -n neural-hive

# Testar conectividade
kubectl run test-net -n neural-hive --rm -i --image=nicolaka/netshoot -- \
  curl -v http://consensus-engine.neural-hive.svc.cluster.local:8002/health
```

**Resolução:**
1. Revisar NetworkPolicies para permitir comunicação
2. Adicionar regras para comunicação entre especialistas e consensus-engine

### Causa Comum 3: Resource Starvation

**Diagnóstico:**
```bash
kubectl top pods -n neural-hive -l layer=cognitive
kubectl describe nodes | grep -A 5 "Resource.*Pressure"
```

**Resolução:**
1. Aumentar recursos dos pods de especialistas
2. Escalar cluster se necessário
3. Configurar requests/limits adequados

### Causa Comum 4: Configuração Incorreta

**Diagnóstico:**
```bash
# Verificar ConfigMaps e Secrets
kubectl get configmap -n neural-hive | grep specialist
kubectl get secret -n neural-hive | specialist

# Verificar configuração de quórum
kubectl get configmap consensus-engine-config -n neural-hive -o yaml
```

**Resolução:**
1. Corrigir configuração de quórum mínimo
2. Garantir que todos os especialistas estão registados
3. Reiniciar consensus-engine após correção

## Ações de Recuperação

### Recuperação 1: Restart Especialistas Problemáticos

```bash
# Restart especialistas não healthy
kubectl delete pod -n neural-hive <pod-name>

# Aguardar recuperação
kubectl wait --for=condition=Ready pod -n neural-hive -l specialist=<type> --timeout=120s
```

### Recuperação 2: Forçar Registo de Especialistas

```bash
# Restart consensus-engine para forçar re-descoberta
kubectl rollout restart deployment/consensus-engine -n neural-hive

# Verificar logs para ver especialistas descobertos
kubectl logs -n neural-hive -l app=consensus-engine -f | grep "specialist.*registered"
```

### Recuperação 3: Reduzir Quórum Temporariamente

⚠️ **Apenas emergência - reduz segurança do consenso**

```bash
# Editar ConfigMap
kubectl edit configmap consensus-engine-config -n neural-hive

# Alterar min_quorum de 3 para 2 (temporário)
# min_quorum: "2"

# Restart consensus-engine
kubectl rollout restart deployment/consensus-engine -n neural-hive
```

### Recuperação 4: Escalar Especialistas

```bash
# Aumentar replicas de especialistas críticos
kubectl scale deployment/business-specialist -n neural-hive --replicas=2
kubectl scale deployment/technical-specialist -n neural-hive --replicas=2
```

## Verificação Pós-Recovery

```bash
# 1. Verificar quórum restaurado
kubectl logs -n neural-hive -l app=consensus-engine --tail=20 | grep "quorum"

# 2. Verificar todos os especialistas registados
kubectl logs -n neural-hive -l app=consensus-engine | grep "specialist.*registered"

# 3. Verificar métricas
# Query: consensus_quorum_size >= 3
# Query: rate(consensus_decisions_total[5m]) > 0

# 4. Testar decisão
curl -X POST http://consensus-engine.neural-hive.svc.cluster.local:8002/health
```

## Dashboard e Métricas

### Consultas Prometheus Úteis

```
# Quórum atual
consensus_quorum_size

# Especialistas ativos
count(up{job=~".*specialist.*"} == 1)

# Taxa de decisões
rate(consensus_decisions_total[5m])

# Taxa de falhas
rate(consensus_decisions_failed_total[5m]) / rate(consensus_decisions_total[5m])
```

## Escalation

| Tempo | Ação |
|-------|------|
| Imediato | Verificar especialistas críticos (business, technical) |
| 5 min | Restart especialistas não healthy |
| 15 min | Escalar para time de plataforma |
| 30 min | Considerar reduzir quórum temporariamente |

## Prevenção

### PodDisruptionBudget para Especialistas

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: specialists-pdb
spec:
  minAvailable: 3
  selector:
    matchLabels:
      layer: cognitive
```

### Alertas Adicionais

```yaml
- alert: ConsensusEngineSpecialistDown
  expr: up{job=~".*specialist.*"} == 0
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "Especialista {{ $labels.job }} está down"
```

## Referências

- **Dashboard:** [Consensus Dashboard](http://grafana.observability.svc.cluster.local:3000/d/consensus-governance)
- **Documentação:** `docs/services/consensus-engine.md`
- **Arquitetura:** `docs/architecture/consensus-system.md`

---

**Última atualização:** 2026-04-13
**Versão:** 1.0
