# Checklist de Validação: Migração etcd→Redis

**Ticket:** OPS-003
**Versão:** v1.3.0
**Fase:** Fase 1 - Backward Compatibility

## Checklist Pré-Deploy

### 1. Preparação de Ambiente

- [ ] Backup do ConfigMap atual
  ```bash
  kubectl get configmap service-registry-config -o yaml > backup-configmap-$(date +%Y%m%d).yaml
  ```

- [ ] Backup do Secret atual (se aplicável)
  ```bash
  kubectl get secret service-registry-secret -o yaml > backup-secret-$(date +%Y%m%d).yaml
  ```

- [ ] Documentar valores atuais de `ETCD_*`
  ```bash
  kubectl get configmap service-registry-config -o jsonpath='{.data.ETCD_ENDPOINTS}'
  kubectl get configmap service-registry-config -o jsonpath='{.data.ETCD_PREFIX}'
  kubectl get configmap service-registry-config -o jsonpath='{.data.ETCD_TIMEOUT_SECONDS}'
  ```

### 2. Validação de Código

- [ ] Código compilado sem erros
  ```bash
  cd services/service-registry
  python -m py_compile src/config/settings.py
  python -m py_compile src/main.py
  ```

- [ ] Testes unitários passando
  ```bash
  pytest tests/unit/test_config_validation.py -v
  ```

- [ ] Linting sem erros
  ```bash
  ruff check src/
  ```

### 3. Validação de Config

- [ ] Novas configs definidas (ou legados funcionando)
  ```bash
  # Verificar se REGISTRY_REDIS_* existe OU ETCD_* ainda funciona
  kubectl get configmap service-registry-config -o jsonpath='{.data}'
  ```

- [ ] Senha Redis configurada (produção)
  ```bash
  kubectl get secret service-registry-secret -o jsonpath='{.data.REDIS_PASSWORD}' | base64 -d
  ```

## Checklist Pós-Deploy

### 1. Verificação de Pods

- [ ] Pods iniciaram com sucesso
  ```bash
  kubectl get pods -l app=service-registry
  # Esperado: STATUS=Running, READY=1/1
  ```

- [ ] Nenhum crash loop
  ```bash
  kubectl get pods -l app=service-registry | grep -v CrashLoopBackOff
  ```

- [ ] Pods prontos (READY)
  ```bash
  kubectl get pods -l app=service-registry | awk '{print $2}' | grep -c '1/1'
  # Deve igualar número de pods
  ```

### 2. Verificação de Logs

- [ ] Sem erros de startup
  ```bash
  kubectl logs --tail=100 deployment/service-registry | grep -i "error"
  # Esperado: sem output
  ```

- [ ] Sem warnings críticos
  ```bash
  kubectl logs --tail=100 deployment/service-registry | grep -i "warning" | grep -v "deprecated"
  # Deprecated warnings são OK na Fase 1
  ```

- [ ] Warnings de deprecation esperados (se usando `ETCD_*`)
  ```bash
  kubectl logs deployment/service-registry | grep -i "deprecated"
  # Esperado: "ETCD_ENDPOINTS is deprecated" se usando configs antigas
  ```

- [ ] Cliente Redis inicializado
  ```bash
  kubectl logs deployment/service-registry | grep "redis_registry_client_initialized"
  # Esperado: timestamp e endpoints
  ```

### 3. Verificação de Saúde

- [ ] gRPC health check passando
  ```bash
  kubectl exec -it deployment/service-registry -- \
    grpcurl -plaintext localhost:8000 grpc.health.v1.Health/Check
  # Esperado: status: SERVING
  ```

- [ ] HTTP metrics endpoint respondendo
  ```bash
  kubectl exec -it deployment/service-registry -- \
    curl -s http://localhost:9090/metrics
  # Esperado: métricas Prometheus
  ```

- [ ] Kubernetes health check passando
  ```bash
  kubectl get endpoints service-registry
  # Esperado: endpoints listados (não 0)
  ```

### 4. Verificação Funcional

- [ ] Registry service respondendo
  ```bash
  kubectl exec -it deployment/service-registry -- \
    grpcurl -plaintext localhost:8000 list
  # Esperado: neural_hive.service_registry.v1.ServiceRegistry
  ```

- [ ] ListAgents funcionando
  ```bash
  kubectl exec -it deployment/service-registry -- \
    grpcurl -plaintext localhost:8000 \
    neural_hive.service_registry.v1.ServiceRegistry/ListAgents
  # Esperado: lista de agentes (pode estar vazia)
  ```

- [ ] DiscoverAgents funcionando
  ```bash
  kubectl exec -it deployment/service-registry -- \
    grpcurl -plaintext -d '{"agent_type": "WORKER"}' localhost:8000 \
    neural_hive.service_registry.v1.ServiceRegistry/DiscoverAgents
  # Esperado: resposta com agents (vazia ou preenchida)
  ```

### 5. Verificação de Conectividade

- [ ] Conexão Redis estabelecida
  ```bash
  kubectl logs deployment/service-registry | grep "redis_registry_client_initialized"
  # Esperado: log com host e port
  ```

- [ ] Redis health check passando
  ```bash
  kubectl exec -it deployment/service-registry -- \
    python -c "
import asyncio
from src.clients.redis_registry_client import RedisRegistryClient

async def test():
    client = RedisRegistryClient(['redis:6379'], 'test', '', 5)
    await client.initialize()
    result = await client.health_check()
    print(f'Health: {result}')
    await client.close()

asyncio.run(test())
"
  # Esperado: Health: True
  ```

### 6. Verificação de Integração

- [ ] Agentes Worker conseguem registrar
  ```bash
  kubectl logs -f deployment/worker-agents | grep "registered"
  # Esperado: logs de registro bem-sucedido
  ```

- [ ] Queen Agent consegue descobrir workers
  ```bash
  kubectl logs -f deployment/queen-agent | grep "discovered"
  # Esperado: logs de descoberta de workers
  ```

- [ ] Orchestrator consegue listar agentes
  ```bash
  kubectl logs -f deployment/orchestrator-dynamic | grep "agents"
  # Esperado: logs de listagem de agentes
  ```

## Checklist de Regressão

### 1. Comparação Antes/Depois

- [ ] Número de agentes similar
  ```bash
  # Antes (anotar)
  kubectl exec -it deployment/service-registry -- \
    grpcurl -plaintext localhost:8000 \
    neural_hive.service_registry.v1.ServiceRegistry/ListAgents | jq '.agents | length'

  # Depois (comparar)
  # Deve ser similar (pode variar com heartbeat)
  ```

- [ ] Latência de resposta similar
  ```bash
  kubectl exec -it deployment/service-registry -- \
    grpcurl -plaintext localhost:8000 \
    neural_hive.service_registry.v1.ServiceRegistry/ListAgents
  # Tempo de resposta deve ser < 100ms
  ```

### 2. Monitoramento

- [ ] Métricas de erro sem aumento
  ```bash
  kubectl exec -it deployment/service-registry -- \
    curl -s http://localhost:9090/metrics | grep "error"
  # Esperado: sem aumento significativo
  ```

- [ ] Redis connections estáveis
  ```bash
  kubectl exec -it redis-0 -- redis-cli INFO clients | grep connected_clients
  # Esperado: número estável de conexões
  ```

## Checklist Final

### 1. Documentação

- [ ] Migração documentada no ticket OPS-003
- [ ] Mudanças registradas no changelog
- [ ] Equipe notificada sobre mudança de config

### 2. Handoff

- [ ] Runbooks atualizados
- [ ] Oncall documentado sobre mudança
- [ ] Monitores configurados para detectar issues

### 3. Sinais

- [ ] Sem erros críticos por 30min
- [ ] Todos os testes funcionais passando
- [ ] Métricas dentro de baseline

## Script de Validação Automatizada

```bash
#!/bin/bash
# validate_migration.sh - Valida migração etcd→Redis

set -e

echo "=== Validando migração Service Registry ==="

# 1. Pods
echo "1. Verificando pods..."
POD_COUNT=$(kubectl get pods -l app=service-registry --no-headers | wc -l)
READY_COUNT=$(kubectl get pods -l app=service-registry --no-headers | grep -c Running || true)
if [ "$POD_COUNT" -eq "$READY_COUNT" ]; then
  echo "   ✅ Todos os pods running"
else
  echo "   ❌ Pods não ready: $READY_COUNT/$POD_COUNT"
  exit 1
fi

# 2. Logs
echo "2. Verificando logs..."
ERRORS=$(kubectl logs --tail=50 deployment/service-registry | grep -i "error" || true)
if [ -z "$ERRORS" ]; then
  echo "   ✅ Sem erros nos logs"
else
  echo "   ❌ Erros encontrados:"
  echo "$ERRORS"
  exit 1
fi

# 3. Health
echo "3. Verificando health..."
HEALTH=$(kubectl exec -it deployment/service-registry -- \
  grpcurl -plaintext localhost:8000 grpc.health.v1.Health/Check 2>/dev/null | grep -c "SERVING" || true)
if [ "$HEALTH" -eq "1" ]; then
  echo "   ✅ Health check passando"
else
  echo "   ❌ Health check falhando"
  exit 1
fi

# 4. Redis
echo "4. Verificando Redis..."
REDIS_LOG=$(kubectl logs deployment/service-registry | grep "redis_registry_client_initialized" || true)
if [ -n "$REDIS_LOG" ]; then
  echo "   ✅ Redis client inicializado"
else
  echo "   ❌ Redis client não inicializado"
  exit 1
fi

# 5. API
echo "5. Verificando API..."
API_TEST=$(kubectl exec -it deployment/service-registry -- \
  grpcurl -plaintext localhost:8000 \
  neural_hive.service_registry.v1.ServiceRegistry/ListAgents 2>/dev/null | grep -c "agents" || true)
if [ "$API_TEST" -eq "1" ]; then
  echo "   ✅ API respondendo"
else
  echo "   ❌ API não respondendo"
  exit 1
fi

echo ""
echo "=== ✅ Validação completa ==="
echo "Migração validada com sucesso."
```

## Criterários de Sucesso

| Critério | Esperado | Observado | Passou? |
|----------|----------|-----------|---------|
| Pods running | 100% | ___ | [ ] |
| Logs sem erros | 0 errors | ___ | [ ] |
| Health check | SERVING | ___ | [ ] |
| Redis conectado | Sim | ___ | [ ] |
| API respondendo | <100ms | ___ | [ ] |
| Agentes registrando | Sim | ___ | [ ] |

## Referências

- [Migration Guide](./MIGRATION_ETCD_TO_REDIS.md)
- [Rollback Plan](./ROLLBACK_ETCD_TO_REDIS.md)
- Ticket OPS-003: Documentar migração etcd→Redis
