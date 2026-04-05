# Plano de Rollback: Migração etcd→Redis

**Ticket:** OPS-003
**Versão:** v1.3.0
**Severidade:** Média (serviço continua funcional durante rollback)

## Visão Geral

Este documento descreve como reverter a migração de configurações `ETCD_*` → `REGISTRY_REDIS_*` se problemas forem detectados em produção.

## Quando Fazer Rollback

### Sinais de Problema

1. **Service Registry não inicia**
   ```bash
   kubectl logs -f deployment/service-registry | grep -i "error"
   ```

2. **Agentes não conseguem registrar**
   ```bash
   # Verificar erros de conexão
   kubectl logs -f deployment/worker-agents | grep -i "registry"
   ```

3. **Health checks falhando**
   ```bash
   kubectl get endpoints service-registry
   ```

4. **Warnings de config inválida**
   ```bash
   kubectl logs deployment/service-registry | grep -i "validation"
   ```

## Procedimento de Rollback

### Passo 1: Avaliar Impacto

```bash
# Verificar pods não saudáveis
kubectl get pods -l app=service-registry

# Verificar logs recentes
kubectl logs --tail=100 -f deployment/service-registry

# Verificar métricas de erro
kubectl top pods -l app=service-registry
```

### Passo 2: Backup Config Atual

```bash
# Salvar ConfigMap atual
kubectl get configmap service-registry-config -o yaml > /tmp/service-registry-config-backup.yaml

# Salvar secrets se aplicável
kubectl get secret service-registry-secret -o yaml > /tmp/service-registry-secret-backup.yaml
```

### Passo 3: Reverter ConfigMap

```bash
# Opção A: Reverter para ConfigMap anterior (se disponível)
kubectl rollout history deployment/service-registry
kubectl rollout undo deployment/service-registry

# Opção B: Criar ConfigMap com nomes antigos
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: service-registry-config
  namespace: neural-hive
data:
  # Configs legadas (funcionam com v1.3.0)
  ETCD_ENDPOINTS: |
    ["redis:6379"]
  ETCD_PREFIX: "neural-hive:agents"
  ETCD_TIMEOUT_SECONDS: "5"

  # Outras configs (mantidas)
  ENVIRONMENT: "production"
  LOG_LEVEL: "INFO"
EOF
```

### Passo 4: Forçar Restart dos Pods

```bash
# Restart deployment para aplicar configs antigas
kubectl rollout restart deployment/service-registry

# Aguardar rollout
kubectl rollout status deployment/service-registry --timeout=5m
```

### Passo 5: Verificar Recuperação

```bash
# Verificar pods running
kubectl get pods -l app=service-registry

# Verificar logs
kubectl logs -f deployment/service-registry --tail=50

# Testar gRPC health
kubectl exec -it deployment/service-registry -- \
  grpcurl -plaintext localhost:8000 grpc.health.v1.Health/Check

# Listar agentes (deve retornar lista)
grpcurl -plaintext \
  service-registry:8000 \
  neural_hive.service_registry.v1.ServiceRegistry/ListAgents
```

## Rollback por Ambiente

### Kubernetes (Produção)

```bash
# 1. Identificar revisão anterior funcional
kubectl rollout history deployment/service-registry

# 2. Rollback para revisão N
kubectl rollout undo deployment/service-registry --to-revision=<N>

# 3. Monitorar
kubectl rollout status deployment/service-registry
```

### Docker Compose (Desenvolvimento)

```bash
# 1. Reverter .env
cat > .env <<EOF
ETCD_ENDPOINTS=["localhost:6379"]
ETCD_PREFIX=neural-hive:agents
ETCD_TIMEOUT_SECONDS=5
EOF

# 2. Restart containers
docker-compose down && docker-compose up -d

# 3. Verificar logs
docker-compose logs -f service-registry
```

### Helm Charts

```bash
# 1. Listar releases
helm list -n neural-hive

# 2. Reverter para versão anterior
helm rollback service-registry <PREVIOUS_REVISION> -n neural-hive

# 3. Verificar status
helm status service-registry -n neural-hive
```

## Validação Pós-Rollback

### Checklist de Verificação

- [ ] Pods do Service Registry estão `Running`
- [ ] Nenhum erro nos logs (grep: `error|ERROR|failed`)
- [ ] Health check gRPC retorna `SERVING`
- [ ] Agentes conseguem registrar (ver logs de workers)
- [ ] Endpoint `/list_agents` retorna agentes
- [ ] Métricas Prometheus funcionando

### Teste Completo

```bash
#!/bin/bash
set -e

echo "=== Validando Rollback ==="

# 1. Check pods
echo "1. Verificando pods..."
kubectl get pods -l app=service-registry

# 2. Check logs
echo "2. Verificando logs (últimos 20)..."
kubectl logs --tail=20 deployment/service-registry

# 3. Check health
echo "3. Verificando health..."
kubectl exec -it deployment/service-registry -- \
  grpcurl -plaintext localhost:8000 grpc.health.v1.Health/Check

# 4. List agents
echo "4. Listando agentes..."
kubectl exec -it deployment/service-registry -- \
  grpcurl -plaintext localhost:8000 \
  neural_hive.service_registry.v1.ServiceRegistry/ListAgents

echo "=== Rollback validado ==="
```

## Situações Especiais

### Dados Corrompidos no Redis

Se os dados estiverem corrompidos (não relacionado a configs):

```bash
# 1. Conectar ao Redis
kubectl exec -it -n neural-hive redis-0 -- redis-cli

# 2. Backup das chaves (se possível)
KEYS neural-hive:agents:* | xargs redis-cli DUMP > /tmp/redis-backup.txt

# 3. Limpar chaves do registry (cuidado!)
# FLUSHDB  # ⚠️ Limpa TODO o banco

# 4. Deixar agentes registrarem novamente
```

### Conflito de Versão (Pydantic)

Se erro de validação do Pydantic:

```bash
# 1. Verificar versão instalada
kubectl exec -it deployment/service-registry -- \
  python -c "import pydantic; print(pydantic.__version__)"

# 2. Se necessário, fazer downgrade da imagem
kubectl set image deployment/service-registry \
  service-registry=neural-hive/service-registry:v1.2.0
```

## Comunicação

### Se Rollback em Produção

1. **Notificar time:**
   ```bash
   # Slack/Teams
   @channel 🔴 Rollback de Service Registry iniciado devido a [motivo].
   ETA: 5 minutos para recuperação.
   ```

2. **Atualizar ticket:**
   - OPS-003: Adicionar comentário com motivo e logs

3. **Post-mortem:**
   - Documentar causa raiz
   - Propor fix para v1.3.1

## Prevenção

### Antes de Próxima Migração

1. **Testar em staging primeiro:**
   ```bash
   # Deploy em staging com novas configs
   helm upgrade service-registry ./charts/service-registry \
     -n staging -f values-staging.yaml \
     --set registryRedis.endpoints=["redis:6379"]
   ```

2. **Smoke test:**
   ```bash
   # Verificar startups
   kubectl logs -f deployment/service-registry -n staging

   # Testar registro
   python scripts/test_register_agent.py --env=staging
   ```

3. **Canary deploy (se disponível):**
   ```bash
   # 10% do tráfego
   kubectl patch deployment service-registry \
     -p '{"spec":{"strategy":{"rollingUpdate":{"maxSurge":"10%"}}}}'
   ```

## Referências

- [Migration Guide](./MIGRATION_ETCD_TO_REDIS.md) - Como migrar
- [Validation Checklist](./VALIDATION_CHECKLIST.md) - Como validar
- Ticket OPS-003: Documentar migração etcd→Redis
