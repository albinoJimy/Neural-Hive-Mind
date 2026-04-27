# Análise de Infraestrutura Kubernetes — Neural Hive Mind

> **Sub-requirements:** R-T6.1, R-T6.2, R-T6.3, R-B3.1, R-B3.2
> **Foco:** SPOFs, zone distribution, PDBs, HPA

---

## 1. Single Points of Failure no Cluster

### 1.1 Queen Agent SPOF

**Componente:** `queen-agent` (porta 8006)

**Problema:**
- Apenas 2 réplicas configuradas no HPA
- `minAvailable: 1` no PodDisruptionBudget
- Leader election via Redis (depende de datastore)

**Impacto:**
- Se uma réplica falhar durante rolling update, sistema fica com única instância
- Redis SPOF afeta leader election

**Mitigação Recomendada:**
1. Aumentar réplicas para 3+
2. Implementar leader election robusto (Raft/etcd)
3. Configurar `minAvailable: 2` no PDB

### 1.2 Service Registry SPOF

**Componente:** `service-registry` (porta 8007)

**Problema:**
- Descoberta de serviços centralizada
- Falha = novos serviços não conseguem registar-se
- Sem cache local nos clientes

**Mitigação Recomendada:**
- Cache local de registros em cada serviço (TTL 30s)
- Múltiplas réplicas com readiness probe

### 1.3 Gateway-Intenções SPOF

**Componente:** `gateway-intencoes` (porta 8000)

**Problema:**
- Single entry point para todas as intenções externas
- HPA configurado (2-10 replicas) mas sem zone distribution

**Mitigação Recomendada:**
- Implementar multi-region deployment
- Load balancer com health checks

---

## 2. Zone Distribution

### 2.1 Estado Atual

**Cluster:** Single-zone deployment identificado

**Problema:**
- Todos os pods em mesma zona
- Falha de zona = downtime total

**Serviços críticos sem zone distribution:**
- gateway-intencoes
- consensus-engine
- orchestrator-dynamic
- queen-agent

**Mitigação Recomendada:**
1. Configurar pod anti-affinity rules
2. Spreading across 3+ zones
3. Testar zone failure simulation

---

## 3. PodDisruptionBudgets

### 3.1 PDBs Configurados

| Serviço | minAvailable | maxUnavailable | Status |
|---------|--------------|-----------------|--------|
| gateway-intencoes | 1 | N/A | ⚠️ Baixo |
| consensus-engine | 1 | N/A | ⚠️ Baixo |
| orchestrator-dynamic | 1 | N/A | ⚠️ Baixo |
| worker-agents | 1 | N/A | ⚠️ Baixo |
| queen-agent | 1 | N/A | ⚠️ BAIXO |

**Problema:**
- `minAvailable: 1` permite redução a 1 pod durante updates
- Nenhum serviço tem `maxUnavailable` configurado
- Rolling updates podem degradar capacidade significativamente

**Mitigação Recomendada:**
- Configurar `minAvailable: 2` para serviços críticos
- Usar `maxUnavailable: 25%` para serviços com 3+ réplicas

---

## 4. HorizontalPodAutoscaler

### 4.1 HPA Configuração

| Serviço | Min Replicas | Max Replicas | Target CPU | Target Memory | Status |
|---------|--------------|--------------|------------|---------------|--------|
| gateway-intencoes | 2 | 10 | 70% | N/A | ✅ |
| consensus-engine | 2 | 10 | 70% | N/A | ✅ |
| orchestrator-dynamic | 2 | 10 | 70% | N/A | ✅ |
| worker-agents | 2 | 10 | 70% | N/A | ✅ |
| queen-agent | 2 | 8 | 70% | N/A | ⚠️ Max baixo |

**Gaps Identificados:**

1. **HPA baseado apenas em CPU**
   - Sem custom metrics (queue depth, request latency)
   - Não reage a load spikes adequadamente

2. **Replicas mínimas podem ser insuficientes**
   - Min 2 pode ser pouco para carga inicial
   - Cold start problema identificado

3. **Upscaling stabilization window**
   - Não configurado explicitamente
   - Pode causar flapping

---

## 5. Resource Limits

### 5.1 CPU/Memory Configuration

| Serviço | CPU Request | CPU Limit | Memory Request | Memory Limit | Ratio Req/Lim |
|---------|-------------|-----------|----------------|--------------|---------------|
| gateway-intencoes | 100m | 500m | 256Mi | 512Mi | 5x |
| consensus-engine | 100m | 500m | 256Mi | 512Mi | 5x |
| orchestrator-dynamic | 100m | 500m | 256Mi | 512Mi | 5x |
| worker-agents | 100m | 500m | 256Mi | 512Mi | 5x |

**Problemas:**

1. **CPU limit muito baixo (500m)**
   - Pod causar throttling sob carga moderada
   - NLP/ML processing pode consumir mais

2. **Memory limit inadequada (512Mi)**
   - Intents complexas podem consumir mais
   - ML inference pode requerer mais memória

**Mitigação Recomendada:**
- Gateway: CPU 1000m, Memory 1Gi
- STE: CPU 500m, Memory 1Gi
- Workers: CPU 500m, Memory 1Gi

---

## 6. Health Checks

### 6.1 Liveness/Readiness Probes

**Status:** NÃO CONFIGURADOS em Helm charts

**Problema:**
- 0 de 8 serviços verificados têm liveness/readiness probes configurados
- Kubernetes não consegue detectar pods mortos
- Traffic pode ser roteado para pods não prontos

**Mitigação Recomendada:**

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /ready
    port: http
  initialDelaySeconds: 10
  periodSeconds: 5
```

---

## 7. Matriz de Risco

| # | Risco | Prob. | Imp. | Risco | Esforço | Prioridade |
|---|-------|-------|------|-------|---------|------------|
| 1 | Queen Agent SPOF | MÉDIA | ALTO | 6 | Médio (3-5 dias) | **P1** |
| 2 | Sem zone distribution | BAIXA | ALTO | 4 | Alto (7-10 dias) | P2 |
| 3 | PDBs minAvailable=1 | ALTA | MÉDIO | 6 | Baixo (1-2 dias) | **P1** |
| 4 | Health checks não configurados | ALTA | MÉDIO | 6 | Baixo (2 dias) | **P1** |
| 5 | Resource limits inadequados | MÉDIA | ALTO | 6 | Baixo (1 dia) | **P1** |
| 6 | HPA apenas CPU | MÉDIA | MÉDIO | 4 | Médio (3-4 dias) | P2 |

---

## 8. Recomendações de Mitigação

### 8.1 Prioridade ALTA

1. **Configurar health checks**
   - Adicionar liveness/readiness probes
   - Esforço: 2 dias

2. **Ajustar PDBs**
   - Configurar minAvailable: 2 para serviços críticos
   - Esforço: 1-2 dias

3. **Aumentar resource limits**
   - CPU 1000m, Memory 1Gi para serviços intensivos
   - Esforço: 1 dia

### 8.2 Prioridade MÉDIA

4. **Implementar zone distribution**
   - Pod anti-affinity rules
   - Multi-zone deployment
   - Esforço: 7-10 dias

5. **HPA com custom metrics**
   - Queue depth, request latency
   - Esforço: 3-4 dias

### 8.3 Prioridade BAIXA

6. **Eliminar Queen Agent SPOF**
   - Leader election robusto
   - Esforço: 3-5 dias

---

## Status dos Invariantes

| INV | Descrição | Status |
|-----|-----------|--------|
| INV-3 | Isolamento de failures | ⚠️ Parcial |
| INV-8 | Non-blocking Consensus | ⚠️ Risco |
| INV-9 | Exclusividade Queen Agent | ⚠️ SPOF potencial |
