# Runbook: Low Model Uptime

## Sintomas
- Alerta: `LowModelUptime` ou `CriticalModelUptime` disparado
- Model uptime < 99.5%
- Falhas frequentes de health checks

## Diagnóstico

### 1. Verificar Logs do Specialist
```bash
kubectl logs -n neural-hive-mind -l app=specialist-technical --tail=200 | grep -i "error\|fail"
```

### 2. Verificar Health Checks
```bash
# Testar health check manualmente
curl http://specialist-technical.neural-hive-mind.svc.cluster.local:8080/health
```

### 3. Verificar Recursos do Pod
```bash
kubectl top pod -n neural-hive-mind -l app=specialist-technical
```

### 4. Verificar Falhas de Inferência
```bash
# Consultar opiniões com erro
mongo neural_hive --eval '
db.specialist_opinions.count({
  evaluated_at: {$gte: new Date(Date.now() - 24*60*60*1000)},
  inference_error: {$exists: true}
})
'
```

## Resolução

### Opção 1: Reiniciar Pod
Se problema é temporário:

```bash
kubectl rollout restart deployment/specialist-technical -n neural-hive-mind
```

### Opção 2: Escalar Recursos
Se pod está com OOM ou CPU throttling:

```yaml
# Aumentar recursos em deployment
resources:
  requests:
    cpu: "1000m"
    memory: "2Gi"
  limits:
    cpu: "2000m"
    memory: "4Gi"
```

### Opção 3: Rollback de Modelo
Se problema começou após deploy de novo modelo:

```bash
python ml_pipelines/deployment/rollback_model.py \
  --model-name technical_specialist \
  --reason "low_uptime"
```

### Opção 4: Verificar Dependências
Se problema é de conectividade:

```bash
# Verificar MongoDB
kubectl exec -it specialist-technical-xxx -n neural-hive-mind -- \
  nc -zv mongodb.neural-hive-mind.svc.cluster.local 27017

# Verificar Redis
kubectl exec -it specialist-technical-xxx -n neural-hive-mind -- \
  nc -zv redis.neural-hive-mind.svc.cluster.local 6379
```

## Prevenção
- Configurar resource requests/limits adequados
- Implementar circuit breakers para dependências
- Monitorar latency de inferência
- Configurar auto-scaling baseado em CPU/memória
