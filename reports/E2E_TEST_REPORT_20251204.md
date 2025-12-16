# Relatório de Teste E2E Manual - Neural Hive-Mind

**Data:** 2025-12-04 21:01 UTC
**Executor:** Claude Code (automated test)
**Ambiente:** Kubernetes cluster (3 nodes)

---

## Resumo Executivo

| Fluxo | Status | Observações |
|-------|--------|-------------|
| **Fluxo A** | ✅ SUCESSO | Gateway → Kafka funcionando |
| **Fluxo B** | ⚠️ PARCIAL | STE OK, Consensus Engine com bug de serialização |
| **Fluxo C** | ❌ BLOQUEADO | Depende de correção no Fluxo B |

---

## 1. FLUXO A: Gateway → Kafka

### 1.1 Health Check do Gateway

```json
{
  "status": "healthy",
  "timestamp": "2025-12-04T21:01:02.972479",
  "version": "1.0.0",
  "service_name": "gateway-intencoes",
  "components": {
    "redis": {"status": "healthy"},
    "asr_pipeline": {"status": "healthy"},
    "nlu_pipeline": {"status": "healthy"},
    "kafka_producer": {"status": "healthy"},
    "oauth2_validator": {"status": "healthy"}
  }
}
```

**Status:** ✅ SUCESSO

### 1.2 Envio de Intenção

**Input:**
```json
{
  "text": "Analisar viabilidade técnica de implementar autenticação biométrica no aplicativo móvel",
  "language": "pt-BR",
  "correlation_id": "test-e2e-manual-1764882128"
}
```

**Output:**
```json
{
  "intent_id": "417cdd3b-dc0b-4fd8-a872-182536478104",
  "correlation_id": "test-e2e-manual-1764882128",
  "status": "processed",
  "confidence": 0.95,
  "confidence_status": "high",
  "domain": "security",
  "classification": "authentication",
  "processing_time_ms": 1993.14
}
```

**Status:** ✅ SUCESSO

### 1.3 Logs do Gateway

```
[KAFKA-DEBUG] _process_text_intention_with_context INICIADO - intent_id=417cdd3b-dc0b-4fd8-a872-182536478104
[KAFKA-DEBUG] Enviando para Kafka - HIGH confidence: 0.95
[KAFKA-DEBUG] Enviado com sucesso - HIGH
```

**Status:** ✅ SUCESSO - Mensagem publicada no Kafka

---

## 2. FLUXO B: Semantic Translation Engine → Specialists

### 2.1 Semantic Translation Engine (STE)

**Logs relevantes:**
```
2025-12-04 21:02:14 - Intent parsed e enriquecido com contexto historico
                      intent_id=417cdd3b-dc0b-4fd8-a872-182536478104
                      num_similar_intents=0
                      objectives=['query']

2025-12-04 21:02:15 - B3: Gerando DAG de tarefas
2025-12-04 21:02:15 - B4: Avaliando risco
2025-12-04 21:02:15 - B5: Versionando plano

2025-12-04 21:02:15 - Plano registrado no ledger
                      plan_id=edf96263-1f27-4534-b9db-4234c44fa0a2

2025-12-04 21:02:16 - Plan publicado
                      topic=plans.ready
                      risk_band=low
                      size_bytes=761
```

**Dados capturados:**
- `plan_id`: `edf96263-1f27-4534-b9db-4234c44fa0a2`
- `risk_band`: `low`
- `risk_score`: `0.30`

**Status:** ✅ SUCESSO

### 2.2 Consensus Engine - Invocação de Specialists

**Erro identificado:**
```
2025-12-04 21:02:19 - ERRO: Falha ao obter parecer de especialista
                      error='RetryError[...raised TypeError]'
                      specialist_type=business/technical/behavior/evolution/architecture

2025-12-04 21:02:19 - Erro processando mensagem:
                      "Pareceres insuficientes: 0/5"
```

**Status:** ❌ FALHA - Bug de serialização gRPC

### 2.3 Análise da Causa Raiz

O Consensus Engine recebe o plano do Kafka, mas ao serializar para gRPC, o campo `cognitive_plan` enviado aos specialists não inclui `version` dentro do JSON.

**Evidência nos logs do Specialist:**
```
PlanVersionIncompatibleError: Versão do plano None não é suportada.
Versões suportadas: ['1.0.0'].
```

#### Teste Manual de Specialist (sucesso)

Ao enviar um payload COMPLETO diretamente via gRPC:
```
SUCCESS!
Opinion ID: 66b202c0-f12e-4074-b5a7-42a22cf7fc5b
confidence_score=0.6613
recommendation=approve
processing_time_ms=35005
```

**Status:** ✅ Specialist funciona quando recebe payload correto

---

## 3. PERSISTÊNCIA

### 3.1 MongoDB - Cognitive Ledger

**Contagem de documentos:**
- cognitive_ledger: 2 (plano + intent)
- specialist_opinions: 1 (business - teste manual)
- consensus_decisions: 0 (não geradas - fluxo bloqueado)

### 3.2 MongoDB - Opinião do Specialist

```javascript
{
  opinion_id: "66b202c0-f12e-4074-b5a7-42a22cf7fc5b",
  plan_id: "edf96263-1f27-4534-b9db-4234c44fa0a2",
  specialist_type: "business",
  opinion: {
    confidence_score: 0.6613,
    risk_score: 0.1960,
    recommendation: "approve",
    reasoning_factors: [
      { factor_name: "workflow_efficiency", weight: 0.4, score: 0.88 },
      { factor_name: "kpi_alignment", weight: 0.3, score: 0.6 },
      { factor_name: "cost_effectiveness", weight: 0.3, score: 0.9999 }
    ]
  },
  processing_time_ms: 35005
}
```

### 3.3 Redis - Cache

- `nlu:cache:fac21d28e41b13c5208dfbb26940db81`
- **Feromônios:** Nenhum (gerados apenas após consenso)

---

## 4. ANÁLISE APROFUNDADA DOS ISSUES

### ISSUE #1 - CRÍTICO: Serialização do cognitive_plan no Consensus Engine

**Componente:** `services/consensus-engine/src/clients/specialists_grpc_client.py`

**Evidências da Investigação:**

1. **Mensagem no Kafka (Avro) está CORRETA:**
   ```
   Offset: 2 (topic: plans.ready)
   version: '1.0.0'
   original_domain: 'SECURITY'
   original_priority: 'normal'
   ```

2. **Deserialização Avro funciona:**
   - O Consensus Engine deserializa corretamente a mensagem Avro
   - Todos os 23 campos estão presentes após deserialização

3. **Serialização JSON para gRPC funciona:**
   - O cliente gRPC serializa corretamente para JSON com `version: '1.0.0'`
   - Teste de serialização manual confirma sucesso

4. **PORÉM, o Specialist recebe `version: None`:**
   ```
   2025-12-04 21:08:07 [error] Versão do plano incompatível
   plan_version=None
   supported_versions=['1.0.0']
   ```

**Causa Raiz Provável:**
O erro ocorre em algum ponto entre a serialização no Consensus Engine e a deserialização no Specialist. Possíveis causas:
- Race condition na invocação paralela
- Problema no retry do tenacity que perde o contexto
- Estrutura do `cognitive_plan` sendo modificada antes da serialização

**Localização do Código:**
- [services/consensus-engine/src/clients/specialists_grpc_client.py:89-92](services/consensus-engine/src/clients/specialists_grpc_client.py#L89-L92)
- [libraries/python/neural_hive_specialists/base_specialist.py:1213-1250](libraries/python/neural_hive_specialists/base_specialist.py#L1213-L1250)

**Fix Proposto:**
Adicionar logging detalhado antes da serialização JSON para capturar o estado exato do `cognitive_plan`:
```python
# Em specialists_grpc_client.py, antes da linha 89
logger.debug(
    "Serializando cognitive_plan para gRPC",
    plan_id=cognitive_plan.get('plan_id'),
    has_version='version' in cognitive_plan,
    version_value=cognitive_plan.get('version')
)
```

---

### ISSUE #2 - ALTO: Incompatibilidade de Versão do scikit-learn

**Componente:** `services/specialist-*/` (todos os specialists)

**Erro Capturado:**
```
2025-12-04 21:23:33 [error] Model inference failed
error="'DecisionTreeClassifier' object has no attribute 'monotonic_cst'"
plan_id=edf96263-1f27-4534-b9db-4234c44fa0a2
```

**Análise:**
1. O modelo ML foi treinado com scikit-learn >= 1.4 que tem o atributo `monotonic_cst`
2. O ambiente de produção tem uma versão anterior do scikit-learn
3. O specialist usa fallback para heurísticas quando o modelo falha
4. Heurísticas levam 35 segundos (15.5s só para explainability)

**Impacto:**
- Latência de 35 segundos por specialist (vs ~500ms esperado com modelo)
- Timeout no Consensus Engine (configurado para 15s por specialist)
- Fallback para heurísticas reduz qualidade das decisões

**Localização do Código:**
- [libraries/python/neural_hive_specialists/mlflow_client.py](libraries/python/neural_hive_specialists/mlflow_client.py)

**Fix Proposto:**
1. Atualizar scikit-learn nos specialists: `scikit-learn>=1.4.0`
2. Ou retreinar modelos com versão compatível
3. Aumentar timeout do gRPC temporariamente

---

### ISSUE #3 - BAIXO: Neo4j sem dados históricos

**Componente:** `services/semantic-translation-engine/`

**Log:**
```
2025-12-04 21:02:14 [warning] Nenhum similar intent encontrado no Neo4j
sugestao='Verifique se Neo4j possui dados historicos (execute seed_neo4j_intents.py)'
```

**Impacto:**
- Sem enriquecimento de contexto histórico
- `num_similar_intents: 0` para todas as intenções
- Planos gerados sem referência a padrões anteriores

**Fix Proposto:**
```bash
python scripts/seed_neo4j_intents.py
```

---

## 5. RECOMENDAÇÕES PRIORIZADAS

### Prioridade CRÍTICA (Bloqueia E2E)
1. Investigar e corrigir perda do campo `version` no fluxo Consensus → Specialist
2. Atualizar scikit-learn ou retreinar modelos para compatibilidade

### Prioridade ALTA (Performance)
3. Aumentar timeout gRPC de 15s para 60s temporariamente
4. Otimizar geração de explainability (15.5s atual)

### Prioridade MÉDIA (Qualidade)
5. Popular Neo4j com dados históricos
6. Habilitar Opinion Cache no Redis

### Prioridade BAIXA (Observability)
7. Configurar ServiceMonitors para coleta de métricas específicas
8. Adicionar tracing distribuído para rastrear latência

---

## 6. CHECKLIST DE VALIDAÇÃO

### Fluxo A (Gateway → Kafka)
- [x] Gateway respondendo health check
- [x] Intenção aceita e processada
- [x] Logs confirmam publicação no Kafka
- [x] Cache no Redis

### Fluxo B (STE → Specialists → Plano)
- [x] Semantic Translation processou e gerou plan
- [x] Plano persistido no MongoDB
- [ ] Consensus Engine orquestrou specialists (FALHOU)
- [x] Specialist responde via gRPC (teste manual)

### Fluxo C (Consensus → Orchestrator → Tickets)
- [ ] Consensus Engine agregou opiniões (BLOQUEADO)
- [ ] Decisão persistida no MongoDB (BLOQUEADO)
- [ ] Feromônios publicados no Redis (BLOQUEADO)
- [ ] Orchestrator gerou execution tickets (BLOQUEADO)

---

## Anexos

### IDs para Rastreamento

| Campo | Valor |
|-------|-------|
| intent_id | `417cdd3b-dc0b-4fd8-a872-182536478104` |
| correlation_id | `test-e2e-manual-1764882128` |
| plan_id | `edf96263-1f27-4534-b9db-4234c44fa0a2` |
| opinion_id (business) | `66b202c0-f12e-4074-b5a7-42a22cf7fc5b` |

---

*Relatório gerado automaticamente por Claude Code - 2025-12-04*
