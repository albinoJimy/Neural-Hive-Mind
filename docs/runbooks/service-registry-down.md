# Runbook: Service Registry Down

**Alerta:** `ServiceRegistryDown`
**Severidade:** Critical
**Camada:** coordination

---

## Descrição

O Service Registry está inativo ou não responde. Este serviço é crítico para a descoberta e registro de todos os microserviços do Neural Hive Mind.

## Impacto

- **Crítico:** Serviços não podem se descobrir mutuamente
- Novos serviços não conseguem registrar-se
- Balanceamento de carga pode falhar
- Service Mesh pode ter comportamento indefinido

## Primeiras Ações (5 minutos)

### 1. Verificar Status do Pod

```bash
# Ver pods do Service Registry
kubectl get pods -n neural-hive -l app=service-registry

# Ver status detalhado
kubectl describe pod -n neural-hive <pod-name>
```

### 2. Verificar Conectividade

```bash
# Criar pod de teste
kubectl run test-registry -n neural-hive --rm -i --image=nicolaka/netshoot -- \
  curl -v http://service-registry.neural-hive.svc.cluster.local:8007/health
```

### 3. Verificar Dependências

```bash
# Service Registry depende de MongoDB
kubectl get pods -n neural-hive -l app=mongodb

# Verificar conectividade com MongoDB
kubectl logs -n neural-hive <pod-name> | grep -i "mongo\|connection"
```

## Diagnóstico

### Causa Comum 1: MongoDB Indisponível

**Sintomas:** Erros de conexão com MongoDB nos logs

**Diagnóstico:**
```bash
# Verificar MongoDB
kubectl get pods -n neural-hive -l app=mongodb

# Verificar logs do MongoDB
kubectl logs -n neural-hive -l app=mongodb --tail=50

# Testar conexão
kubectl exec -n neural-hive <pod-name> -- nc -zv mongodb.neural-hive.svc.cluster.local 27017
```

**Resolução:**
1. Restaurar MongoDB primeiro
2. Reiniciar Service Registry após MongoDB OK
3. Verificar replica set status

### Causa Comum 2: Pod OOMKilled

**Sintomas:** Pod sendo reiniciado com OOMKilled

**Diagnóstico:**
```bash
kubectl describe pod -n neural-hive <pod-name> | grep -i "oom\|memory"

kubectl top pod -n neural-hive <pod-name>
```

**Resolução:**
1. Aumentar memory limit no deployment
2. Verificar memory leak
3. Configurar HPA se necessário

### Causa Comum 3: Porta em Uso

**Sintomas:** Erro "bind: address already in use"

**Diagnóstico:**
```bash
# Verificar portas em uso no nó
kubectl exec -n neural-hive <pod-name> -- netstat -tulpn | grep 8007
```

**Resolução:**
1. Verificar se há outro pod usando a porta
2. Usar `kubectl delete pod` para forçar recreação
3. Verificar se `terminationGracePeriodSeconds` está adequado

### Causa Comum 4: Startup Probe Falhando

**Sintomas:** Pod reiniciando mas sem logs de erro

**Diagnóstico:**
```bash
kubectl describe pod -n neural-hive <pod-name> | grep -A 10 Liveness
kubectl describe pod -n neural-hive <pod-name> | grep -A 10 Readiness
```

**Resolução:**
1. Ajustar `initialDelaySeconds` das probes
2. Aumentar `timeoutSeconds`
3. Verificar se há inicialização lenta

## Ações de Recuperação

### Recuperação 1: Restart do Pod

```bash
# Delete pod para forçar restart
kubectl delete pod -n neural-hive <pod-name>

# Aguardar novo pod
kubectl wait --for=condition=Ready pod -n neural-hive -l app=service-registry --timeout=120s
```

### Recuperação 2: Rollback do Deployment

```bash
# Ver histórico
kubectl rollout history deployment/service-registry -n neural-hive

# Rollback
kubectl rollout undo deployment/service-registry -n neural-hive

# Verificar status
kubectl rollout status deployment/service-registry -n neural-hive
```

### Recuperação 3: Scale Up (HA)

```bash
# Se tiver múltiplas réplicas, escalar
kubectl scale deployment/service-registry -n neural-hive --replicas=2

# Verificar qual é líder
kubectl logs -n neural-hive -l app=service-registry | grep -i "leader\|primary"
```

### Recuperação 4: Limpar Estado Persistente

⚠️ **Perda de dados - usar apenas como último recurso**

```bash
# Identificar PVC
kubectl get pvc -n neural-hive | grep service-registry

# Opção 1: Criar novo PVC (estado limpo)
kubectl patch pvc <pvc-name> -n neural-hive -p '{"metadata":{"finalizers":null}}'
kubectl delete pvc <pvc-name> -n neural-hive

# Opção 2: Limpar dados existentes (exec no pod)
kubectl exec -n neural-hive <pod-name> -- rm -rf /data/registry.db
```

## Verificação Pós-Recovery

```bash
# 1. Health check
curl http://service-registry.neural-hive.svc.cluster.local:8007/health

# 2. Verificar serviços registados
curl http://service-registry.neural-hive.svc.cluster.local:8007/services | jq .

# 3. Verificar métricas
# Query: up{job="service-registry"} == 1
# Query: service_registry_count > 0
# Query: rate(service_registry_operations_total[5m]) > 0

# 4. Verificar logs sem erros
kubectl logs -n neural-hive -l app=service-registry --tail=50 | grep -i "error\|fail"
```

## Operações de Serviço

### Listar Serviços Registados

```bash
# Via API
curl http://service-registry.neural-hive.svc.cluster.local:8007/services | jq '.'

# Via kubectl (se usar CRDs)
kubectl get services.registry -n neural-hive
```

### Remover Serviço Órfão

```bash
# Via API
curl -X DELETE http://service-registry.neural-hive.svc.cluster.local:8007/services/<service-id>

# Via kubectl
kubectl delete service.registry <service-name> -n neural-hive
```

### Forçar Re-registro de Serviço

```bash
# Restart do serviço que precisa registrar-se
kubectl rollout restart deployment/<service-name> -n neural-hive

# Verificar logs do service-registry
kubectl logs -n neural-hive -l app=service-registry -f | grep "<service-name>"
```

## Dashboard e Métricas

### Consultas Prometheus

```
# Status do registry
up{job="service-registry"}

# Serviços registados
service_registry_count

# Operações por segundo
rate(service_registry_operations_total[5m])

# Latência P95
histogram_quantile(0.95, rate(service_registry_lookup_duration_seconds_bucket[5m]))

# Erros por segundo
rate(service_registry_errors_total[5m])
```

## Escalation

| Tempo | Ação |
|-------|------|
| Imediato | Verificar status do pod |
| 5 min | Tentar restart se necessário |
| 15 min | Escalar para time de plataforma |
| 30 min | Considerar incidente maior |

## Prevenção

### Alta Disponibilidade

```yaml
# deployment.yaml
spec:
  replicas: 2  # Mínimo para HA
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
```

### PodDisruptionBudget

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-registry-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: service-registry
```

### Recursos Adequados

```yaml
resources:
  requests:
    cpu: 200m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi
```

## Referências

- **Dashboard:** [Service Registry Dashboard](http://grafana.observability.svc.cluster.local:3000/d/service-registry-dashboard)
- **Documentação:** `docs/services/service-registry.md`
- **API:** `http://service-registry.neural-hive.svc.cluster.local:8007/docs`

---

**Última atualização:** 2026-04-13
**Versão:** 1.0
