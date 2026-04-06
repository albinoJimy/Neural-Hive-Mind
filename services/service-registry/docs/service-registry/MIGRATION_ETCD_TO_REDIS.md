# Guia de Migração: etcd → Redis

**Ticket:** OPS-003
**Status:** Em Progresso (Fase 1)
**Versão Alvo:** v1.3.0

## Resumo

O Service Registry foi migrado de etcd para Redis como backend de armazenamento. Este documento guia operadores através da migração das configurações.

## Contexto

### Problema Original
- `etcd_client.py` usava biblioteca `etcd3` incompatível com protobuf >= 4.0
- Solução inicial foi criar `RedisRegistryClient` com alias `EtcdClient`
- Isso criou confusão operacional: configs com nomes `ETCD_*` mas usando Redis

### Solução
- Renomear configs `ETCD_*` para `REGISTRY_REDIS_*`
- Remover alias `EtcdClient` (usar `RedisRegistryClient` diretamente)
- Manter backward compatibility durante transição

## Estratégia de 3 Fases

### Fase 1: Backward Compatibility (v1.3.0) ✅
**Objetivo:** Suportar ambos os nomes de config

**Implementado:**
- Novas configs `REGISTRY_REDIS_*` adicionadas ao `settings.py`
- Configs `ETCD_*` marcadas como `deprecated` (removem em v1.6.0)
- `model_validator` mescla configs: `REGISTRY_REDIS_*` tem prioridade
- Propriedades `registry_redis_*` para acesso transparente
- `main.py` usa `RedisRegistryClient` diretamente

**Comportamento:**
```python
# Se ambos definidos, REGISTRY_REDIS_* ganha
REGISTRY_REDIS_ENDPOINTS=["redis:6379"]  # ✅ usado
ETCD_ENDPOINTS=["etcd:2379"]  # ⚠️ ignorado, warning emitido

# Se apenas ETCD_* definido (legado)
ETCD_ENDPOINTS=["redis:6379"]  # ✅ usado, warning de deprecation
```

### Fase 2: Migration (v1.4.0) ⏳
**Objetivo:** Atualizar Helm charts e documentação

**Tarefas:**
- [ ] Atualizar `helm/service-registry/values.yaml` com `REGISTRY_REDIS_*`
- [ ] Atualizar dokumentação de deploy
- [ ] Comunicar mudança para operadores
- [ ] Atualizar scripts de CI/CD

### Fase 3: Cleanup (v1.6.0) 🔜
**Objetivo:** Remover código deprecated

**Tarefas:**
- [ ] Remover campos `ETCD_*` do `settings.py`
- [ ] Remover `model_validator` de migração
- [ ] Remover propriedades de compatibilidade
- [ ] Manter apenas `REGISTRY_REDIS_*`

## Variáveis de Ambiente

### Novos Nomes (Padrão)

| Variável | Tipo | Default | Descrição |
|----------|------|---------|-----------|
| `REGISTRY_REDIS_ENDPOINTS` | list | `["redis:6379"]` | Endpoints Redis (host:port) |
| `REGISTRY_REDIS_PREFIX` | string | `"neural-hive:agents"` | Prefixo das chaves Redis |
| `REGISTRY_REDIS_TIMEOUT_SECONDS` | int | `5` | Timeout operações (s) |

### Nomes Legados (Deprecated)

| Variável Antiga | Nova Variável | Status |
|-----------------|---------------|--------|
| `ETCD_ENDPOINTS` | `REGISTRY_REDIS_ENDPOINTS` | ⚠️ Removido em v1.6.0 |
| `ETCD_PREFIX` | `REGISTRY_REDIS_PREFIX` | ⚠️ Removido em v1.6.0 |
| `ETCD_TIMEOUT_SECONDS` | `REGISTRY_REDIS_TIMEOUT_SECONDS` | ⚠️ Removido em v1.6.0 |

## Guia de Migração por Ambiente

### Desenvolvimento Local

**Antes (`.env`):**
```bash
ETCD_ENDPOINTS=["localhost:6379"]
ETCD_PREFIX=neural-hive:agents
ETCD_TIMEOUT_SECONDS=5
```

**Depois (`.env`):**
```bash
# Novos nomes
REGISTRY_REDIS_ENDPOINTS=["localhost:6379"]
REGISTRY_REDIS_PREFIX=neural-hive:agents
REGISTRY_REDIS_TIMEOUT_SECONDS=5

# OU (mantém compatibilidade temporária)
ETCD_ENDPOINTS=["localhost:6379"]  # ⚠️ deprecated
```

### Kubernetes / Helm

**Antes (`values.yaml`):**
```yaml
serviceRegistry:
  etcd:
    endpoints:
      - "redis:6379"
    prefix: "neural-hive:agents"
    timeoutSeconds: 5
```

**Depois (`values.yaml`):**
```yaml
serviceRegistry:
  registryRedis:
    endpoints:
      - "redis:6379"
    prefix: "neural-hive:agents"
    timeoutSeconds: 5
```

**ConfigMap resultante:**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: service-registry-config
data:
  REGISTRY_REDIS_ENDPOINTS: |
    ["redis:6379"]
  REGISTRY_REDIS_PREFIX: "neural-hive:agents"
  REGISTRY_REDIS_TIMEOUT_SECONDS: "5"
```

### Docker Compose

**Antes:**
```yaml
environment:
  - ETCD_ENDPOINTS=["redis:6379"]
  - ETCD_PREFIX=neural-hive:agents
```

**Depois:**
```yaml
environment:
  - REGISTRY_REDIS_ENDPOINTS=["redis:6379"]
  - REGISTRY_REDIS_PREFIX=neural-hive:agents
```

## Validação

### 1. Verificar Warnings de Deprecation

```bash
# Se usando ETCD_*, ver warnings no startup
kubectl logs -f deployment/service-registry | grep -i "deprecated"

# Output esperado (se usando configs antigas):
# DeprecationWarning: ETCD_ENDPOINTS is deprecated and will be removed in v1.6.0.
# Use REGISTRY_REDIS_ENDPOINTS instead.
```

### 2. Verificar Conexão Redis

```bash
# Test health endpoint
kubectl exec -it deployment/service-registry -- \
  python -c "
import asyncio
from src.clients.redis_registry_client import RedisRegistryClient

async def test():
    client = RedisRegistryClient(['redis:6379'], 'test', '', 5)
    await client.initialize()
    healthy = await client.health_check()
    print(f'Redis healthy: {healthy}')
    await client.close()

asyncio.run(test())
"
```

### 3. Verificar Registro de Agentes

```bash
# Listar agentes registrados
grpcurl -plaintext \
  service-registry:8000 \
  neural_hive.service_registry.v1.ServiceRegistry/ListAgents
```

## Rollback

Se problemas ocorrerem após migração de configs:

1. **Reverter configs para nomes antigos:**
   ```bash
   # Reverter ConfigMap
   kubectl create configmap service-registry-config \
     --from-literal=ETCD_ENDPOINTS='["redis:6379"]' \
     --from-literal=ETCD_PREFIX='neural-hive:agents' \
     --dry-run=client -o yaml | kubectl apply -f -

   # Restart pods
   kubectl rollout restart deployment/service-registry
   ```

2. **Verificar logs:**
   ```bash
   kubectl logs -f deployment/service-registry
   ```

Ver `ROLLBACK_ETCD_TO_REDIS.md` para detalhes completos.

## Timeline

| Data | Versão | Fase | Status |
|------|--------|------|--------|
| 2025-04-05 | v1.3.0 | Fase 1: Backward compatibility | ✅ Completo |
| TBD | v1.4.0 | Fase 2: Migration de configs | ⏳ Pending |
| TBD | v1.6.0 | Fase 3: Cleanup de código deprecated | 🔜 Pending |

## Perguntas Frequentes

**Q: Posso usar `ETCD_*` e `REGISTRY_REDIS_*` junto?**
A: Sim, mas `REGISTRY_REDIS_*` tem prioridade. `ETCD_*` será ignorado com warning.

**Q: Preciso migrar meus dados?**
A: Não. Apenas nomes de configuração mudaram. Os dados já estavam em Redis.

**Q: O que acontece com o arquivo `etcd_client.py`?**
A: Foi movido para `.deprecated/etcd_client.py.deprecated` como referência histórica.

**Q: Como sei se minha config está usando Redis?**
A: Verifique se `ETCD_ENDPOINTS` aponta para `redis:6379` (não `etcd:2379`).

## Referências

- Ticket OPS-003: Documentar migração etcd→Redis
- `src/config/settings.py`: Configurações com validação de migração
- `src/clients/redis_registry_client.py`: Cliente Redis atual
- `src/clients/__init__.py`: Exporta `RedisRegistryClient`
- `.deprecated/etcd_client.py.deprecated`: Código legado para referência
