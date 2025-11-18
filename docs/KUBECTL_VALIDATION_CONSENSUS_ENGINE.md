# Kubectl Validation Commands - Consensus Engine

**Validações manuais pós-deploy** usando kubectl:

## 1. Verificar Status do Pod

```bash
kubectl get pods -n consensus-engine
kubectl describe pod -n consensus-engine -l app.kubernetes.io/name=consensus-engine
```

**Esperado**: Pod `Running 1/1 Ready`, 0 Restarts, Age > 2min

**Se CrashLoopBackOff**:
- Verificar eventos: `kubectl get events -n consensus-engine --sort-by='.lastTimestamp' | tail -20`
- Verificar logs: `kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine --previous` (logs do crash anterior)
- Verificar ConfigMap: `kubectl get configmap -n consensus-engine consensus-engine-config -o yaml | grep -E 'KAFKA|MONGODB|REDIS'`

## 2. Verificar Logs de Inicialização

```bash
kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine --tail=100 -f
```

**Buscar por**:
- ✅ "Iniciando Consensus Engine" (linha 43 de `main.py`)
- ✅ "MongoDB client inicializado" (linha 50)
- ✅ "Redis client inicializado" (linha 63)
- ✅ "Specialists gRPC client inicializado" (linha 68)
- ✅ "Plan consumer inicializado" (linha 82)
- ✅ "Decision producer inicializado" (linha 87)
- ✅ "Consensus Engine iniciado com sucesso" (linha 99)
- ❌ Erros de conexão, ValueError, TypeError, KeyError

## 3. Testar Health Endpoint

```bash
kubectl port-forward -n consensus-engine svc/consensus-engine 8000:8000 &
PF_PID=$!
curl http://localhost:8000/health
# Esperado: {"status":"healthy","service":"consensus-engine"}
kill $PF_PID
```

## 4. Testar Readiness Endpoint

```bash
kubectl port-forward -n consensus-engine svc/consensus-engine 8000:8000 &
PF_PID=$!
curl http://localhost:8000/ready | jq .
# Esperado: {"ready":true,"checks":{"mongodb":true,"specialists":true,"redis":true}}
kill $PF_PID
```

**Se /ready retorna false**:
- Identificar qual check falhou no JSON response
- MongoDB false: Verificar conectividade `kubectl run mongo-test --image=busybox --rm -it --restart=Never -n consensus-engine -- nc -zv mongodb.mongodb-cluster.svc.cluster.local 27017`
- Redis false: Similar para porta 6379
- Specialists false: Verificar logs para identificar qual specialist não responde

## 5. Verificar Conectividade gRPC com Specialists

```bash
POD_NAME=$(kubectl get pods -n consensus-engine -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[0].metadata.name}')

for specialist in business technical behavior evolution architecture; do
  echo "Testing specialist-${specialist}..."
  kubectl exec -n consensus-engine $POD_NAME -- nc -zv specialist-${specialist}.specialist-${specialist}.svc.cluster.local 50051 2>&1 | grep -q succeeded && echo "✓ ${specialist}" || echo "✗ ${specialist}"
done
```

**Esperado**: Todos os 5 specialists retornam "✓"

## 6. Verificar Service e Endpoints

```bash
kubectl get svc -n consensus-engine
kubectl get endpoints -n consensus-engine consensus-engine
```

**Esperado**: Service com ClusterIP, Endpoint com IP do pod (formato `10.x.x.x:8000`)

## 7. Verificar ConfigMap e Secret

```bash
kubectl get configmap -n consensus-engine consensus-engine-config -o yaml | head -30
kubectl get secret -n consensus-engine consensus-engine-secrets -o yaml
```

**Validar**:
- ConfigMap tem todas as variáveis esperadas (KAFKA_BOOTSTRAP_SERVERS, MONGODB_URI, REDIS_CLUSTER_NODES, etc.)
- Secret existe (mesmo que vazio para dev local)

## 8. Verificar Métricas Prometheus

```bash
kubectl port-forward -n consensus-engine svc/consensus-engine 8080:8080 &
PF_PID=$!
curl http://localhost:8080/metrics | grep neural_hive
kill $PF_PID
```

**Esperado**: Métricas como `consensus_decisions_total`, `bayesian_aggregation_duration_seconds`, `voting_ensemble_duration_seconds`

## 9. Verificar Namespace Labels

```bash
kubectl get namespace consensus-engine -o jsonpath='{.metadata.labels}' | jq .
```

**Esperado**: `{"neural-hive.io/component":"consensus-engine","neural-hive.io/layer":"cognitiva"}`
