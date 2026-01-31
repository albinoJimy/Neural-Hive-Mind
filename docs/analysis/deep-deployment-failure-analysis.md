# Análise Profunda: Falha no Deploy do Consensus-Engine

## 📋 Resumo Executivo

**Workflow:** Deploy After Build #21551913758  
**Status:** ❌ Falhou após 7m21s  
**Serviço:** consensus-engine  
**Namespace:** neural-hive-staging  
**Erro Principal:** `release consensus-engine failed, and has been uninstalled due to atomic being set: services "consensus-engine" not found`

---

## 🔍 Análise da Cadeia de Falha

### 1. Fluxo do Deploy

```
[Helm Install]
    ↓
[Pods Criados] ← consensus-engine-654bf5545c-* (2 replicas)
    ↓
[Startup Probe] ← /health porta 8000 ✅ PASSA
    ↓
[Readiness Probe] ← /ready porta 8000 🔴 FALHA
    ↓
[Timeout 3s] × 3 tentativas = 15s
    ↓
[Pods marcados como NOT READY (0/1)]
    ↓
[Helm aguarda com --wait --timeout 10m]
    ↓
[Timeout atingido ~7 minutos]
    ↓
[Flag --atomic ativada]
    ↓
[Rollback automático executado]
    ↓
[Service removido durante cleanup]
    ↓
[ERRO: services "consensus-engine" not found]
```

### 2. Timeline dos Eventos

| Timestamp | Evento | Status |
|-----------|--------|--------|
| 22:30:25 | Helm inicia instalação | 🟡 Iniciando |
| 22:30:25 | Pods criados (2 replicas) | 🟡 Criando |
| 22:30:25 | Startup probe iniciado | 🟡 Verificando |
| 22:30:30 | Liveness probe iniciado | 🟡 Verificando |
| 22:30:30 | Readiness probe iniciado | 🔴 Falhando |
| 22:30:30-22:37:00 | 62 falhas de readiness | 🔴 Falhando |
| 22:37:04 | Helm timeout (7m21s) | 🔴 Timeout |
| 22:37:04 | Atomic rollback executado | 🟠 Rollback |
| 22:37:04 | Service removido | 🔴 Erro |

---

## 🎯 Causa Raiz Identificada

### Problema Principal: Readiness Probe Timeout

**Configuração Atual:**
```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  periodSeconds: 5
  timeoutSeconds: 3      ← 🔴 MUITO CURTO
  failureThreshold: 3
  initialDelaySeconds: 0 ← 🔴 SEM DELAY INICIAL
```

**Problema:** O endpoint `/ready` está **demorando mais de 3 segundos** para responder, causando timeout consistente.

### Por que o /ready demora?

Baseado nos logs, o endpoint `/ready` verifica múltiplas dependências:

1. **MongoDB** ✅ (funcionando - logs mostram conexão OK)
2. **OTEL Collector** 🔴 (indisponível - timeout na conexão)
   - Endpoint: `opentelemetry-collector.observability.svc.cluster.local:4317`
   - Logs mostram: `otel_pipeline_unhealthy - OTEL Collector not reachable`
3. **Possivelmente outras dependências**:
   - Kafka (9092)
   - Redis (6379)
   - gRPC Specialists (50051)

**Cadeia de Timeout:**
```
Readiness Probe (K8s) ──► /ready (App) ──► Health Checks
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    │                           │                           │
                   MongoDB                   OTEL Collector           Outros
                   ✅ OK                     🔴 Timeout >3s            ?
                   (<100ms)                  (3-5s tentativa)
```

### Impacto do OTEL Collector

**Logs recorrentes (a cada 5-7 segundos):**
```json
{
  "timestamp": "2026-01-31T22:36:32.780023+00:00",
  "level": "DEBUG",
  "logger": "neural_hive_observability.health_checks.otel",
  "message": "OTEL collector health check error: ",
  "module": "otel",
  "function": "_check_collector_health",
  "line": 164
}

2026-01-31 22:36:32 [warning] otel_pipeline_unhealthy  
message=OTEL Collector not reachable
```

**Tempo de timeout:** A tentativa de conexão ao OTEL Collector provavelmente demora ~3-5 segundos antes de falhar, excedendo o timeout do readiness probe (3s).

---

## 📊 Análise Técnica Detalhada

### 1. Estado dos Pods

```
consensus-engine-654bf5545c-jjqgv   0/1   Running   0   9m9s   10.244.1.126
consensus-engine-654bf5545c-tzxlv   0/1   Running   0   9m9s   10.244.2.133
consensus-engine-77cf87c964-5f8gm   0/1   Running   0   3m18s  10.244.2.134
```

**Análise:**
- **Status:** Running ✅ (container iniciou)
- **Ready:** 0/1 🔴 (readiness probe falhou)
- **Restarts:** 0 ✅ (aplicação não crashou)
- **Idade:** Múltiplas revisões criadas (indica tentativas de deployment)

### 2. Network Policy

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
spec:
  egress:
  - DNS (port 53 UDP) ✅
  - Kafka:9092 (namespace: kafka) ✅
  - MongoDB:27017 (namespace: mongodb-cluster) ✅
  - Redis:6379 (namespace: redis-cluster) ✅
  - gRPC:50051 (namespace: neural-hive-specialists) ✅
  - OTEL:4317,4318 ❌ (NÃO CONFIGURADO!)
```

**Problema identificado:** A NetworkPolicy **não permite acesso ao namespace observability** onde o OTEL Collector está!

### 3. Probes Comparison

| Probe | Endpoint | Timeout | Estado | Propósito |
|-------|----------|---------|--------|-----------|
| **startupProbe** | /health | 5s | ✅ Passa | Verifica se app iniciou |
| **livenessProbe** | /health | 5s | ✅ Passa | Verifica se app está viva |
| **readinessProbe** | /ready | 3s | 🔴 Falha | Verifica se app pode receber tráfego |

**Problema:** O readiness probe tem o **menor timeout** (3s vs 5s) mas verifica **mais dependências** (incluindo OTEL).

### 4. Helm Release Status

```bash
Name: consensus-engine
Namespace: neural-hive-staging
Status: pending-upgrade  ← 🔴 Travado
Revision: 2
```

**Status `pending-upgrade`:** Indica que o Helm está aguardando o deployment completar, mas os pods nunca ficaram prontos.

### 5. Ausência de Configuração Staging

**Arquivo não encontrado:**
```
environments/staging/helm-values/consensus-engine-values.yaml ❌
```

**Impacto:** O deployment usa valores padrão do chart, que podem não ser adequados para staging.

---

## 🎨 Cenário da Falha

### Cenário 1: Timeout do Readiness Probe (Principal)

**Probabilidade:** ⭐⭐⭐⭐⭐ (99%)

**Descrição:**
1. Pod inicia e servidor HTTP fica disponível
2. Startup probe chama `/health` → retorna 200 OK rapidamente
3. Readiness probe chama `/ready` → tenta verificar OTEL Collector
4. OTEL Collector está indisponível ou inalcançável
5. Aplicação tenta conectar por 3-5 segundos
6. Timeout de 3s do readiness probe é atingido
7. Kubernetes marca pod como NOT READY
8. Após 3 falhas consecutivas (15s), pod continua NOT READY
9. Helm aguarda até 10 minutos mas pods nunca ficam ready
10. Helm falha e faz rollback (--atomic)

**Evidências:**
- Logs mostram warning `otel_pipeline_unhealthy` recorrente
- Eventos Kubernetes: `Readiness probe failed: context deadline exceeded`
- NetworkPolicy não inclui regra para namespace observability

### Cenário 2: Bloqueio de Rede (Secundário)

**Probabilidade:** ⭐⭐⭐ (30%)

**Descrição:**
- NetworkPolicy pode estar bloqueando comunicação interna
- Embora as regras de egress pareçam corretas, pode haver problemas de DNS ou resolução de serviço

**Evidências:**
- NetworkPolicy permite acesso a múltiplos serviços externos
- Mas não permite acesso ao observability namespace

---

## 🔧 Soluções Propostas

### Solução 1: Corrigir NetworkPolicy (Prioridade: 🔴 ALTA)

**Adicionar regra de egress para OTEL Collector:**

```yaml
# helm-charts/consensus-engine/templates/networkpolicy.yaml
spec:
  egress:
    # ... regras existentes ...
    - ports:
      - port: 4317
        protocol: TCP
      - port: 4318
        protocol: TCP
      to:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: observability
```

### Solução 2: Aumentar Timeout do Readiness Probe (Prioridade: 🔴 ALTA)

**Modificar values.yaml:**
```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  periodSeconds: 10       # Aumentar de 5 para 10
  timeoutSeconds: 10      # Aumentar de 3 para 10
  failureThreshold: 5     # Aumentar de 3 para 5
  initialDelaySeconds: 5  # Adicionar delay inicial
```

### Solução 3: Criar Configuração Staging (Prioridade: 🟡 MÉDIA)

**Criar arquivo:** `environments/staging/helm-values/consensus-engine-values.yaml`

```yaml
# Configurações específicas para staging
replicaCount: 2

readinessProbe:
  timeoutSeconds: 10
  periodSeconds: 10
  failureThreshold: 5
  initialDelaySeconds: 5

# Desabilitar OTEL em staging se não estiver disponível
observability:
  enabled: false  # Ou configurar endpoint alternativo
```

### Solução 4: Modificar Código da Aplicação (Prioridade: 🟢 BAIXA)

**Tornar OTEL opcional para readiness:**
```python
# health.py - pseudocódigo
async def readiness_check():
    checks = [
        check_mongodb(),      # Obrigatório
        check_kafka(),        # Obrigatório
        check_redis(),        # Obrigatório
    ]
    
    # OTEL é opcional - não bloqueia readiness
    try:
        await asyncio.wait_for(check_otel(), timeout=2.0)
    except TimeoutError:
        logger.warning("OTEL indisponível, continuando...")
    
    return all(checks)
```

### Solução 5: Remover Flag --atomic Temporariamente (Workaround)

**No workflow:**
```yaml
# .github/workflows/deploy-after-build.yml
# Comentar ou remover:
# "--atomic"
# "--cleanup-on-fail"
```

⚠️ **Risco:** Deployment pode ficar em estado inconsistente se falhar

---

## 📋 Plano de Ação

### Fase 1: Hotfix Imediato (5 minutos)

1. **Escalar timeout do readiness probe via kubectl:**
```bash
kubectl patch deployment consensus-engine -n neural-hive-staging -p '{"spec":{"template":{"spec":{"containers":[{"name":"consensus-engine","readinessProbe":{"timeoutSeconds":10,"periodSeconds":10}}]}}}}'
```

2. **Verificar se pods ficam ready:**
```bash
kubectl get pods -n neural-hive-staging -w
```

### Fase 2: Correção Definitiva (30 minutos)

1. **Atualizar NetworkPolicy no Helm chart**
2. **Atualizar valores padrão do readiness probe**
3. **Criar staging values file**
4. **Commit e push das alterações**

### Fase 3: Verificação (10 minutos)

1. **Re-executar workflow de deploy**
2. **Monitorar rollout:**
```bash
kubectl rollout status deployment/consensus-engine -n neural-hive-staging
```
3. **Verificar pods:**
```bash
kubectl get pods -n neural-hive-staging
```

---

## 📊 Métricas de Impacto

| Métrica | Valor | Impacto |
|---------|-------|---------|
| **Tentativas de deploy** | 7 em 60 minutos | 🔴 Alto |
| **Tempo médio de falha** | ~7 minutos | 🔴 Alto |
| **Pods criados** | 14+ | 🟡 Médio |
| **Service indisponível** | 100% | 🔴 Crítico |
| **Rollback automático** | 100% | 🟡 Médio |

---

## 🔍 Comandos para Investigação

```bash
# Verificar logs em tempo real
kubectl logs -n neural-hive-staging -l app.kubernetes.io/name=consensus-engine -f

# Testar endpoint /ready manualmente
kubectl exec -n neural-hive-staging consensus-engine-654bf5545c-jjqgv -- curl -v http://localhost:8000/ready

# Verificar se OTEL está acessível
kubectl exec -n neural-hive-staging consensus-engine-654bf5545c-jjqgv -- nc -zv opentelemetry-collector.observability.svc.cluster.local 4317

# Verificar eventos do deployment
kubectl get events -n neural-hive-staging --field-selector involvedObject.name=consensus-engine --sort-by='.lastTimestamp'

# Descrever deployment
kubectl describe deployment -n neural-hive-staging consensus-engine

# Verificar status do rollout
kubectl rollout status deployment/consensus-engine -n neural-hive-staging

# Histórico de revisões do helm
helm history consensus-engine -n neural-hive-staging
```

---

## 📝 Conclusão

A falha do deployment é causada por uma **combinação de fatores**:

1. **Causa Primária:** Readiness probe timeout (3s) é insuficiente para verificação do OTEL Collector
2. **Causa Secundária:** NetworkPolicy não permite acesso ao namespace observability
3. **Causa Terciária:** Ausência de configuração específica para staging

**Impacto:** O deploy falha consistentemente devido ao timeout do readiness probe, causando rollback automático pelo Helm (--atomic).

**Recomendação Imediata:** Aplicar hotfix aumentando o timeout do readiness probe para 10s via kubectl patch, depois implementar correções permanentes no Helm chart.

**Arquivos a serem modificados:**
1. `helm-charts/consensus-engine/templates/networkpolicy.yaml`
2. `helm-charts/consensus-engine/values.yaml`
3. `environments/staging/helm-values/consensus-engine-values.yaml` (criar)

---

## 📚 Referências

- [Kubernetes Probes Documentation](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Helm Atomic Flag](https://helm.sh/docs/helm/helm_upgrade/#options)
- [NetworkPolicy API](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/)
