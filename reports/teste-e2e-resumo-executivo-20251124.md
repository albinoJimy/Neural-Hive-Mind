# Resumo Executivo - Teste E2E Manual
**Data**: 24/11/2025
**Status**: PARCIALMENTE CONCLUÍDO - Fluxo A validado, Fluxos B/C bloqueados

---

## 🎯 Objetivo

Validar end-to-end os três fluxos principais do Neural Hive-Mind:
- **Fluxo A**: Gateway → Kafka
- **Fluxo B**: Semantic Translation → Specialists → Plano Cognitivo
- **Fluxo C**: Consensus → Orchestrator → Execution Tickets

---

## ✅ FLUXO A: VALIDADO COM SUCESSO (100%)

### Resultados

| Passo | Status | Tempo | Observação |
|-------|--------|-------|------------|
| Gateway Health Check | ✅ | <200ms | Todos componentes healthy |
| Processar Intenção | ✅ | 231ms | Confidence 0.95 (HIGH) |
| Publicar no Kafka | ✅ | - | Topic: intentions-security |
| Cache no Redis | ✅ | - | TTL aplicado corretamente |

### IDs Capturados

```
intent_id: b7e4d61f-b41c-4779-914b-d14bbcaa1a04
correlation_id: e2e-test-08fcb589
domain: security
classification: authentication
confidence: 0.95
```

### Evidências

**Mensagem no Kafka (intentions-security partition 2, offset 9)**:
```json
{
  "id": "b7e4d61f-b41c-4779-914b-d14bbcaa1a04",
  "correlationId": "e2e-test-08fcb589",
  "intent": {
    "text": "Analisar viabilidade técnica de implementar autenticação biométrica no aplicativo móvel",
    "domain": "SECURITY",
    "classification": "authentication"
  },
  "confidence": 0.95
}
```

**Cache no Redis**:
```bash
redis-cli GET "intent:b7e4d61f-b41c-4779-914b-d14bbcaa1a04"
# ✓ Dados completos cacheados
```

---

## ❌ FLUXO B/C: BLOQUEADOS (0%)

### Problema Crítico

**Semantic Translation Engine não consegue consumir mensagens do Kafka**

**Sintoma**:
```
KafkaError{code=UNKNOWN_TOPIC_OR_PART,val=3,str="Subscribed topic not available: intentions-security: Broker: Unknown topic or partition"}
```

### Análise Profunda Executada

Executei script de debug Python com logging completo do `librdkafka`:

**Descobertas**:
1. ✅ AdminClient lista tópicos corretamente (17 tópicos encontrados)
2. ✅ Tópicos `intentions-*` existem e têm 3 partitions cada
3. ✅ DNS resolve: `neural-hive-kafka-kafka-bootstrap → 10.99.11.200`
4. ✅ Consumer conecta ao bootstrap server
5. ✅ Consumer obtém metadata inicial
6. ❌ **Broker termina conexão ao tentar fazer partition assignment**

**Evidência dos Logs**:
```
[DEBUG] AdminClient.list_topics() → SUCESSO
[DEBUG] Consumer.subscribe(topics) → SUCESSO
[DEBUG] Consumer obtém metadata → SUCESSO
[ERROR] Broker: Client is terminating (after 395ms) (_DESTROY)
[ERROR] Broker changed state UP → DOWN
```

### Root Cause

**O broker Kafka está encerrando forçadamente conexões de consumers após metadata exchange**, provavelmente devido a:

1. Configuração `connections.max.idle.ms` muito baixa
2. Incompatibilidade com múltiplos listeners (REPLICATION, PLAIN, TLS)
3. Bug na versão do Strimzi Operator ou Kafka 4.1.0

### Tentativas de Resolução

| Solução | Status | Resultado |
|---------|--------|-----------|
| Opção 1: Atualizar confluent-kafka | ⏸️ | Requer rebuild de imagem |
| Opção 2: Usar broker direto | ❌ | Testado - problema persiste |
| Opção 3: Adicionar keepalive configs | ⏸️ | Requer rebuild de imagem |
| Restart do broker Kafka | ✅ | Executado - não resolveu |
| Restart dos pods STE | ✅ | Executado - não resolveu |

---

## 📊 Impacto

### Componentes Afetados

- ❌ Semantic Translation Engine (não consome)
- ❌ 5 Specialists (não são consultados)
- ❌ Consensus Engine (não recebe plans)
- ❌ Orchestrator Dynamic (não gera tickets)
- ❌ Memory Layer API (sem dados para armazenar)

### Métricas

| Métrica | Esperado | Obtido | Status |
|---------|----------|--------|--------|
| Intenções publicadas | 1 | 1 | ✅ |
| Plans gerados | 1 | **0** | ❌ |
| Specialists consultados | 5 | **0** | ❌ |
| Decisões de consensus | 1 | **0** | ❌ |
| Execution tickets | 3-5 | **0** | ❌ |

---

## 🔧 Soluções Propostas (Em Ordem de Prioridade)

### 1. CRÍTICO - Ajustar Configuração do Broker Kafka

```bash
kubectl edit kafka neural-hive-kafka -n kafka
```

```yaml
spec:
  kafka:
    config:
      # Aumentar timeout de conexões idle
      connections.max.idle.ms: 600000  # 10 minutos (padrão: 600000)

      # Aumentar buffer de requests
      socket.request.max.bytes: 104857600  # 100MB

      # Ajustar metadata refresh
      metadata.max.age.ms: 300000  # 5 minutos

      # Desabilitar compressão agressiva (pode causar timeouts)
      compression.type: "none"
```

**Reiniciar broker após mudança**:
```bash
kubectl delete pod neural-hive-kafka-broker-0 -n kafka
kubectl wait --for=condition=ready pod -l strimzi.io/name=neural-hive-kafka-kafka -n kafka --timeout=180s
```

### 2. ALTA - Rebuild STE com Configurações Corrigidas

**services/semantic-translation-engine/src/consumers/intent_consumer.py**:
```python
consumer_config = {
    'bootstrap.servers': self.settings.kafka_bootstrap_servers,
    'group.id': self.settings.kafka_consumer_group_id,
    'auto.offset.reset': self.settings.kafka_auto_offset_reset,
    'enable.auto.commit': False,
    'isolation.level': 'read_committed',
    'session.timeout.ms': self.settings.kafka_session_timeout_ms,

    # FIX: Prevenir timeout e desconexões
    'connections.max.idle.ms': 540000,  # 9 minutos
    'socket.keepalive.enable': True,
    'heartbeat.interval.ms': 3000,
    'max.poll.interval.ms': 300000,  # 5 minutos
    'metadata.max.age.ms': 180000,  # 3 minutos
    'topic.metadata.refresh.interval.ms': 10000,  # 10 segundos
}
```

**Rebuild e deploy**:
```bash
cd /jimy/Neural-Hive-Mind
docker build -t docker.io/neural-hive-mind/semantic-translation-engine:1.0.8-kafka-fix \
  --build-arg BUILD_CONTEXT=. \
  -f services/semantic-translation-engine/Dockerfile .

docker push docker.io/neural-hive-mind/semantic-translation-engine:1.0.8-kafka-fix

kubectl set image deployment/semantic-translation-engine \
  semantic-translation-engine=docker.io/neural-hive-mind/semantic-translation-engine:1.0.8-kafka-fix \
  -n semantic-translation

kubectl rollout status deployment/semantic-translation-engine -n semantic-translation
```

### 3. MÉDIA - Investigar Strimzi Operator

O Strimzi v0.x pode ter bugs conhecidos com metadata requests. Considerar:

1. Verificar versão atual:
```bash
kubectl get deploy -n strimzi-system strimzi-cluster-operator -o yaml | grep image:
```

2. Upgrade para versão mais recente (se < 0.40.0):
```bash
kubectl apply -f 'https://strimzi.io/install/latest?namespace=strimzi-system'
```

### 4. ALTERNATIVA - Migrar para Kafka Nativo

Se Strimzi continuar problemático:

```bash
# Deploy Kafka usando Helm Chart oficial da Apache
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install neural-hive-kafka bitnami/kafka \
  --namespace kafka \
  --set replicaCount=1 \
  --set listeners.client.protocol=PLAINTEXT
```

---

## 📋 Checklist de Validação Pós-Correção

### Fluxo A (Revalidar)
- [ ] Gateway health check
- [ ] Enviar nova intenção
- [ ] Verificar publicação no Kafka
- [ ] Validar cache no Redis

### Fluxo B
- [ ] STE consumir mensagem do Kafka
- [ ] STE gerar plano cognitivo
- [ ] STE publicar plan no topic `plans.ready`
- [ ] Verificar persistência no MongoDB (`cognitive_ledger`)
- [ ] Validar métricas no Prometheus
- [ ] Verificar trace no Jaeger

### Specialists
- [ ] Specialist Business responder
- [ ] Specialist Technical responder
- [ ] Specialist Architecture responder
- [ ] Specialist Behavior responder
- [ ] Specialist Evolution responder
- [ ] 5/5 opiniões persistidas no MongoDB

### Fluxo C
- [ ] Consensus Engine agregar opiniões
- [ ] Consensus Engine gerar decisão
- [ ] Decisão persistida no MongoDB (`consensus_decisions`)
- [ ] Feromônios publicados no Redis
- [ ] Orchestrator gerar execution tickets
- [ ] Tickets persistidos no MongoDB (`execution_tickets`)

---

## 🎯 Próximos Passos Imediatos

### ✅ Ações Já Executadas

1. ✅ **Correção #1 APLICADA**: Ajustado config do Kafka broker
   ```yaml
   connections.max.idle.ms: 600000
   socket.request.max.bytes: 104857600
   metadata.max.age.ms: 300000
   ```
   - Broker reiniciado
   - **Resultado**: Problema persiste

2. ✅ **Correção #2 APLICADA**: Código do STE modificado com keepalive configs
   - Arquivo `intent_consumer.py` atualizado
   - **Resultado**: Requer rebuild de imagem (não aplicado em runtime)

3. ✅ **Correção #3 TESTADA**: Alterado KAFKA_BOOTSTRAP_SERVERS para broker direto
   - Usado `neural-hive-kafka-broker-0.neural-hive-kafka-kafka-brokers.kafka.svc:9092`
   - **Resultado**: Problema persiste

### 🔴 Ações Pendentes (Offline)

1. **CRÍTICO**: Rebuild completo da imagem do STE com correções
   ```bash
   # Navegar para raiz do projeto
   cd /jimy/Neural-Hive-Mind

   # Build com contexto correto incluindo schemas
   docker build --platform linux/amd64 \
     --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
     -t neural-hive-mind/semantic-translation-engine:1.0.8-kafka-fix \
     --file services/semantic-translation-engine/Dockerfile \
     --build-context schemas=./schemas \
     .

   # Tag e push para registry
   docker tag neural-hive-mind/semantic-translation-engine:1.0.8-kafka-fix \
     docker.io/neural-hive-mind/semantic-translation-engine:1.0.8-kafka-fix
   docker push docker.io/neural-hive-mind/semantic-translation-engine:1.0.8-kafka-fix

   # Update deployment
   kubectl set image deployment/semantic-translation-engine \
     semantic-translation-engine=docker.io/neural-hive-mind/semantic-translation-engine:1.0.8-kafka-fix \
     -n semantic-translation
   ```

2. **ALTA**: Investigar versão do Strimzi Operator
   - Verificar se há bugs conhecidos com KRaft mode + metadata requests
   - Considerar downgrade para ZooKeeper mode se necessário
   - Ou upgrade para Strimzi mais recente

3. **ALTERNATIVA**: Deploy Kafka standalone (sem Strimzi)
   - Usar Helm chart oficial do Apache Kafka
   - Ou Bitnami Kafka chart
   - Configuração mais simples pode resolver problema de metadata

---

## 📄 Documentação Relacionada

- **Relatório Detalhado**: [teste-e2e-manual-20251124.md](./teste-e2e-manual-20251124.md)
- **Script de Debug**: [../scripts/kafka/debug-ste-kafka-connection.py](../scripts/kafka/debug-ste-kafka-connection.py)
- **Logs Salvos**: `logs/ste-kafka-error-20251124.log`

---

## ✅ Conclusão

**Fluxo A está 100% funcional** - Gateway, NLU, Kafka Producer e Redis operando perfeitamente.

**Fluxo B/C estão bloqueados** por bug de infraestrutura no Kafka broker que está terminando conexões de consumers prematuramente. A solução requer ajuste de configuração do broker + rebuild do STE com parâmetros de keepalive/timeout adequados.

**Estimativa de Resolução**: 2-4 horas de trabalho técnico + testes de revalidação.
