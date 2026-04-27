# Análise de Arquitectura — Pipeline Cognitivo NHM

> **Task:** T3 - Analisar arquitectura, SPOFs, acoplamento e dependências
> **Data:** 2026-04-27
> **Riscos Analisados:** R-T1.1, R-T1.2, R-T1.3, R-B3.1, R-B3.2

---

## 1. Single Points of Failure (SPOFs)

### 1.1 Gateway-Intenções (Risco: ALTO)

**Componente:** `gateway-intencoes` (porta 8000)

**Problema:**
- Single entry point para todas as intenções externas
- Sem mecanismo de fallback documentado
- Falha completa = perda total de serviço

**Dependências Críticas:**
- Semantic Translation Engine (via Kafka)
- Service Registry (descoberta)

**Mitigação Recomendada:**
- Implementar múltiplas réplicas com load balancing
- Health check com failover automático
- Considerar API Gateway externo (Kong, AWS API Gateway)

---

### 1.2 Queen Agent (Risco: MÉDIO)

**Componente:** `queen-agent` (porta 8006)

**Problema:**
- Coordenação estratégica centralizada
- Leader election via Redis/ MongoDB (depende de datastore)

**Dependências Críticas:**
- MongoDB (persistência)
- Redis (leader election)

**Mitigação Recomendada:**
- Implementar leader election robusto (Raft/etcd)
- Múltiplas instâncias com standby activo

---

### 1.3 Service Registry (Risco: MÉDIO)

**Componente:** `service-registry` (porta 8007)

**Problema:**
- Descoberta de serviços centralizada
- Falha = novos serviços não conseguem registar-se

**Mitigação Recomendada:**
- Cache local de registos em cada serviço
- TTL adequado para cache

---

## 2. Acoplamento entre Serviços

### 2.1 Forte Acoplamento via Kafka

**Padrão:** Todos os serviços core dependem de Kafka

**Fluxos:**
```
gateway → nhm.intentions → STE
STE → nhm.plans → Consensus
Consensus → nhm.decisions → Orchestrator
Orchestrator → nhm.execution-tickets → Workers
```

**Problema:**
- Kafka downtime para todo o pipeline
- Ordem estrita de tópicos (INV-4)
- Falha num consumer pode bloquear downstream

**Mitigação Recomendada:**
- DLQ para todos os tópicos (CRÍTICO — R-T4.1)
- Circuit breakers entre serviços
- Idempotência em producers/consumers

---

### 2.2 Acoplamento Temporal

**Padrão:** Synchronous waiting em alguns fluxos

**Problema:**
- Timeout em specialist pode bloquear Consensus Orchestrator
- Falta de backpressure em consumers Kafka

**Mitigação Recomendada:**
- Async patterns com filas separadas
- Backpressure via credit-based flow control

---

### 2.3 gRPC Version Mismatch

**Problema Conhecido:**
- gRPC version mismatch entre serviços
- Potencial incompatibilidade de proto schemas

**Mitigação Recomendada:**
- Versionamento semântico de proto files
- Backward compatibility obrigatória
- Compatibility matrix documentada

---

## 3. Dependências Externas Críticas

### 3.1 Kafka (Risco: ALTO)

**Uso:** Message bus principal para todos os fluxos

**Impacto de Falha:**
- Perda completa de comunicação inter-serviço
- Intenções não processadas
- Decisões não distribuídas

**Configuração Actual:**
- `enable.idempotence=true`, `acks=all` (exactly-once)
- Sem DLQ documentada (RISCO CRÍTICO)

**Mitigações:**
- DLQ para todos os tópicos (PRINCIPAL)
- Cluster Kafka HA (3+ brokers)
- Monitorização de lag

---

### 3.2 MongoDB (Risco: ALTO)

**Uso:** Persistência autoritativa (INV-6)

**Impacto de Falha:**
- Perda de estado persistido
- Execution tickets (fail-closed implementado)
- Planos cognitivos não recuperáveis

**Configuração Actual:**
- Replica Set?
- Failover automático?

**Mitigações:**
- Replica Set com 3+ nós
- Backup automático diário
- Redis como cache (não autoritativo)

---

### 3.3 Redis (Risco: MÉDIO)

**Uso:** Cache, state temporal, leader election

**Impacto de Falha:**
- Cache miss (degradado, não fatal)
- Leader election pode falhar
- State temporal perdido

**Mitigações:**
- Redis Sentinel ou Redis Cluster
- TTL adequado para cached data
- Fallback para MongoDB quando crítico

---

### 3.4 Neo4j (Risco: BAIXO)

**Uso:** Knowledge graph (connections API)

**Impacto de Falha:**
- Graph queries falham
- Serviços podem funcionar sem grafos

**Mitigações:**
- Cache local de grafos frequentes
- Graceful degradation

---

### 3.5 Temporal (Risco: MÉDIO)

**Uso:** Saga orchestration no Orchestrator Dynamic

**Impacto de Falha:**
- Workflows de longa duração não executam
- Compensação Saga pode não ser triggered

**Configuração Actual:**
- Server clustering?
- Workflow timeouts configurados?

**Mitigações:**
- Temporal Cluster HA
- Timeout em todas as actividades
- Compensation actions documentadas

---

## 4. Matriz de Dependências por Serviço

| Serviço | Kafka | MongoDB | Redis | Neo4j | Temporal | Críticas |
|---------|-------|---------|-------|-------|----------|----------|
| Gateway | ✓ | ✓ | ✓ | | | Alta |
| STE | ✓ | ✓ | ✓ | | | Alta |
| Consensus | ✓ | ✓ | ✓ | | | Alta |
| Orchestrator | ✓ | ✓ | ✓ | | ✓ | Alta |
| Approval | ✓ | ✓ | | | | Média |
| Workers | ✓ | | | | | Alta |
| Queen | | ✓ | ✓ | | | Média |
| Registry | | ✓ | | | | Média |

---

## 5. Invariantes Verificados

| INV | Descrição | Status | Observação |
|-----|-----------|--------|------------|
| INV-1 | Gateway↛Workers | ✓ Respeitado | Gateway → Kafka → Workers |
| INV-3 | Specialist↛Consensus | ⚠️ Parcial | Timeout pode bloquear |
| INV-6 | MongoDB autoritativo | ✓ Respeitado | Fail-closed em tickets |
| INV-8 | Non-blocking Consensus | ⚠️ Risco | Timeout sem async fallback |

---

## 6. Priorização de Riscos

| Prioridade | Risco | Componente | Impacto | Probabilidade |
|------------|-------|------------|---------|--------------|
| 1 | Falta de DLQ | Kafka | ALTO | MÉDIA |
| 2 | Gateway SPOF | gateway-intencoes | ALTO | ALTA |
| 3 | MongoDB SPOF | MongoDB cluster | ALTO | BAIXA |
| 4 | Timeout bloqueando Consensus | Consensus Engine | MÉDIO | MÉDIA |
| 5 | Leader election single point | Queen Agent | MÉDIO | BAIXA |

---

**Analista:** Claude (Orchestrator)
**Data:** 2026-04-27
