# Spec: Redis Cluster - Migração

**ID:** FASE0-003
**Status:** Planning
**Estimativa:** 8 dias (3 cluster + 3 migração + 2 testes)

---

## 1. Objetivo

Migrar de Redis single pod para Redis Cluster com TLS, eliminando SPOF e habilitando criptografia em trânsito.

---

## 2. Contexto Atual

**Cluster:** Kubernetes v1.29.15, 5 nós

**Estado Atual:**
- ⚠️ Single pod `redis-66b84474ff-tv686` rodando há 52d
- ✅ Redis Operator instalado (`redis-operator` pod rodando)
- ❌ Sem cluster mode, sem TLS evidente
- ✅ Código Terraform robusto existe em `infrastructure/terraform/modules/redis-cluster/`

**Serviços que usam Redis:**
- gateway-intencoes (cache)
- orchestrator-dynamic (session)
- memory-layer-api (cache distribuído)
- Optimizer agents (cache ML)

---

## 3. Abordagem: Zero Downtime Migration

### 3.1 Fase 1: Preparação (1 dia)

**Tasks:**
- [ ] 1.1 Backup completo do Redis atual
- [ ] 1.2 Valida carga de dados atuais
- [ ] 1.3 Configura DNS para Redis Cluster
- [ ] 1.4 Gera certificados TLS
- [ ] 1.5 Prepara scripts de migração

**Artefatos:**
- `redis/backup/dump.rdb` - Backup dos dados
- `redis/tls/certs/` - Certificados TLS
- `scripts/redis-sync.sh` - Script de migração

### 3.2 Fase 2: Deploy Redis Cluster (3 dias)

**Tasks:**
- [ ] 2.1 Deploy Redis Cluster via Helm
- [ ] 2.2 Configurar TLS (mutual auth)
- [ ] 2.3 Configurar 6 masters (3 nós × 2 réplicas)
- [ ] 2.4 Validar cluster health (`redis-cli --cluster check`)
- [ ] 2.5 Configurar resource quotas
- [ ] 2.6 Configurar backups automáticos

**Artefatos:**
- `helm/redis-cluster/values.yaml` - Values atualizados
- `redis/redis-cluster-secret.yaml` - Secrets TLS

### 3.3 Fase 3: Migração Zero Downtime (3 dias)

**Tasks:**
- [ ] 3.1 Deploy Redis Sync Tool para replicação
- [ ] 3.2 Configurar aplicação para usar novo endpoint (feature flag)
- [ ] 3.3 Validar dados sincronizados
- [ ] 3.4 Switch DNS gradual para novo cluster
- [ ] 3.5 Valida aplicação funcionando
- [ ] 3.6 Remove pod antigo
- [ ] 3.7 Limpa configurações de migração

**Artefatos:**
- `scripts/redis-migrate.sh` - Script de migração
- `docs/runbooks/redis-migration.md` - Runbook de operação

---

## 4. Configurações Técnicas

### 4.1 Redis Cluster Values

```yaml
redis-cluster:
  enabled: true
  image:
    repository: redis
    tag: 7.2.4-alpine
  master:
    replicas: 3
    persistence:
      enabled: true
      storageClass: "longhorn"
  replication:
    replicas: 2
  tls:
    mode: mutual
    auth: true
    ca: |
      -----BEGIN CERTIFICATE-----
      ...
      -----END CERTIFICATE-----
```

### 4.2 Service Discovery

```yaml
apiVersion: v1
kind: Service
metadata:
  name: redis-cluster
spec:
  clusterIP: None  # Headless service para cluster
  ports:
  - port: 6379
    targetPort: 6379
```

### 4.3 ConfigMap Application

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: redis-config
data:
  redis_host: "redis-cluster.redis-cluster.svc.cluster.local"
  redis_port: "6379"
  redis_tls_enabled: "true"
  redis_cluster_mode: "true"
```

---

## 5. Critérios de Aceitação

### Cluster
- [ ] Redis Cluster running (6 pods across 3 nós)
- [ ] Cluster health OK (`redis-cli --cluster check`)
- [ ] TLS habilitado e validado
- [ ] Anti-affinity configurada (pods em nós diferentes)

### Migração
- [ ] Backup criado antes da migração
- [ ] Dados sincronizados sem perdas
- [ ] Aplicações conectando ao novo endpoint
- [ ] Zero downtime verificado

### Pós-Migração
- [ ] Pod antigo removido
- [ ] Configurações de migração limpas
- [ ] Backups automáticos configurados
- [ ] Documentação atualizada

### Observabilidade
- [ ] Métricas Redis exportadas
- [ ] Dashboards Grafana atualizados
- [ ] Alertas configurados

---

## 6. Testes

### Unitários
- [ ] Teste instalação Redis Cluster em cluster de teste
- [ ] Teste configuração TLS
- [ ] Teste cluster failover

### Integração
- [ ] Teste conexão aplicação → Redis Cluster
- [ ] Teste fallback para pod antigo
- [ ] Teste migração de dados

### E2E
- [ ] Teste fluxo completo com Redis Cluster
- [ ] Teste failover de nó
- [ ] Teste performance com cluster

---

## 7. Dependências

- Kubernetes v1.29+ ✓
- Redis Operator ✓
- Longhorn StorageClass ✓
- Istio Service Mesh (FASE0-001) - para mTLS

---

## 8. Riscos e Mitigações

| Risco | Mitigação |
|-------|-----------|
| Dados perdidos na migração | Backup completo antes, sync tool |
| Aplicação não compatível | Teste em staging, fallback para single |
| Performance degradation | Resource quotas, monitoring |
| Certificados TLS expiram | Cert-manager ou rotação manual |
| Cluster split-brain | Quorum configurado, monitoramento |

---

## 9. Rollback Plan

Se migração falhar:
1. Desabilitar feature flag de novo Redis
2. Switch DNS de volta para pod antigo
3. Investigar logs e corrigir problema
4. Tentar migração novamente após correção

---

**Fim da Spec**
