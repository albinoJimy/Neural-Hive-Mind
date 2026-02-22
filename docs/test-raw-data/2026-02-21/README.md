# Dados Brutos do Teste Manual - 2026-02-21

## Descrição

Este diretório contém todos os dados brutos capturados durante o teste manual profundo do Neural Hive-Mind (Fluxos A-B-C) executado em 21 de fevereiro de 2026.

## Estrutura de Diretórios

### 📄 Documentação do Teste
- **TESTE_MANUAL_PROFUNDO.md** (34KB)
  - Documento original do plano de teste
  - Estrutura completa de 7 seções

### 🔍 Gateway (Fluxo A)
- **intent-response.json** (510B)
  - Resposta RAW do Gateway ao receber a intenção
  - Contém: intent_id, correlation_id, trace_id, span_id, confidence, domain
  
- **kafka-message-raw.txt** (216B)
  - Confirmação de publicação da mensagem no Kafka
  - Output bruto do produtor Kafka

### 📡 Kafka
- **kafka-message-consumed.txt** (111B)
  - Mensagem específica consumida do Kafka topic `intentions.technical`
  - Offset: 207, Partition: 0

- **kafka-messages-consumed.txt** (3.0KB)
  - Histórico de mensagens do Kafka topic `intentions.technical`
  - Mostra 10 mensagens mais recentes
  - Formato Avro binário não legível

### 🗄️ MongoDB (Fluxo B)
- **consensus-decision-raw.txt** (6.1KB)
  - Documento RAW do MongoDB (collection: consensus_decisions)
  - Decisão completa com todos os campos
  - Votos detalhados dos 5 especialistas
  - Cognitive plan gerado
  - Metrics de consenso e guardrails acionados

### 🔍 Jaeger (Tracing)
- **jaeger-trace.json** (0B - vazio)
  - Trace específico não encontrado no Jaeger
  - Sampling rate muito baixo ou não exportado

- **jaeger-traces-consensus.json** (4.8KB)
  - Traces do serviço consensus-engine do Jaeger
  - Apenas health check traces disponíveis
  - Sem traces de processamento de intenções

- **jaeger-traces-recent.json** (26KB)
  - Traces recentes de todos os serviços
  - Apenas health check traces capturados
  - Traces de negócio ausentes

### 📍 Tracking & IDs
- **current_intent_id.txt** (37B)
  - Intent ID gerado para o teste: 431cbef5-9c05-4476-82fa-7db00139e447

- **current_correlation_id.txt** (37B)
  - Correlation ID usado no teste: c3f7e2ca-0d2f-4662-bb9b-58b415c7dad1

- **test_tracking_ids.txt** (266B)
  - Todos os IDs de rastreabilidade usados no teste
  - Contém: INTENT_ID, CORRELATION_ID, TRACE_ID, PLAN_ID, DECISION_ID

### 📝 Intents de Teste (todos os payloads)
- **intent-technical.json** (451B)
  - Payload de teste para domínio TECHNICAL
  - Prioridade: HIGH
  - Tipo: INFRASTRUCTURE_ALERT

- **intent-business.json** (460B)
  - Payload de teste para domínio BUSINESS
  - Prioridade: NORMAL
  - Tipo: FEATURE_REQUEST

- **intent-infrastructure.json** (441B)
  - Payload de teste para domínio INFRASTRUCTURE
  - Prioridade: HIGH
  - Tipo: SYSTEM_UPDATE

- **intent-response.json** (510B)
  - Resposta final do Gateway para a intenção processada
  - Status: processed, confidence: 0.95

- **intent-gateway-test.json** (367B)
  - Payload de teste para validar Gateway
  - Texto: "Teste validação Gateway"

- **intent-kafka.json** (470B)
  - Payload de teste para validação de Kafka
  - Verifica publicação de mensagens

- **intent-direct.json** (354B)
  - Payload de teste direto (sem middleware)
  - Teste de bypass de validação

- **intent-correct.json** (442B)
  - Payload corrigido após validação
  - Formato corrigido para API

- **intent-test-final.json** (334B)
  - Payload final de teste
  - Iteração corrigida

- **intent-test-correct.json** (574B)
  - Payload corrigido para formato correto
  - Validação de esquema

- **intent-test-fix.json** (291B)
  - Payload com fix aplicado
  - Correção de bug no formato

- **intent-test-fix2.json** (289B)
  - Payload com fix aplicado (segunda versão)
  - Correção adicional

- **intent-test-2026-02-21.json** (414B)
  - Payload de teste de 2026-02-21
  - Teste de data/hora

- **intent-test-2026-02-21-03.json** (421B)
  - Payload de teste (03h)
  - Teste de timestamp

- **intent-test-traces.json** (378B)
  - Payload de teste para geração de traces
  - Validação de tracing

- **intent-test2.json** (268B)
  - Segundo payload de teste
  - Iteração adicional

## IDs de Rastreabilidade

```
INTENT_ID (usado): 327403ce-8292-46cb-a13a-d863de64cc5e
CORRELATION_ID: c3f7e2ca-0d2f-4662-bb9b-58b415c7dad1
TRACE_ID: 53f92ad9258b95fc0e6e7a1d05e39c86
PLAN_ID: d7e564dc-8319-41d0-8411-f636b3cbca46
DECISION_ID: e4457805-4266-49a5-b4d5-f26e72867871
```

## Credenciais Usadas

```bash
# MongoDB
mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017
Database: neural_hive
Collection: consensus_decisions

# Kafka
Bootstrap: neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092
Topics: intentions.technical, plans.consensus

# Redis
Host: redis-66b84474ff-tv686.redis-cluster.svc.cluster.local
Port: 6379
Password: (não configurado)

# Jaeger
Endpoint: http://neural-hive-jaeger.observability.svc.cluster.local:16686
API: http://localhost:16686/api/traces

# Prometheus
Endpoint: http://neural-hive-prometheus-kub-prometheus.observability.svc.cluster.local:9090
API: http://localhost:9090/api/v1/query
```

## Formato dos Dados

### MongoDB Documents
Formato JavaScript (printjson) do MongoDB shell, não JSON válido.
Contém campos como ObjectId, Date, e outros tipos específicos do MongoDB.

### Kafka Messages
Formato binário Avro não legível quando consumido.
Contém headers (timestamp, partition, offset) e payload binário.

### Jaeger Traces
Formato JSON válido do Jaeger API.
Contém estrutura de spans com timestamps, tags, logs e parent-child relationships.

### Gateway Responses
Formato JSON válido da API FastAPI.
Contém status, métricas e IDs de rastreabilidade.

## Observações Importantes

1. **Jaeger Traces Ausentes**: Traces de processamento de intenções não estão disponíveis. Apenas health check traces foram capturados.

2. **Avro Binário**: Mensagens do Kafka estão em formato binário Avro não legível diretamente.

3. **MongoDB Format**: Documentos do MongoDB estão em formato JavaScript, não JSON puro.

4. **Sampling Rate**: Baixa sampling rate no Jaeger pode ter causado ausência de traces.

## Como Usar Estes Dados

### Para investigar a decisão do consenso:
```bash
cat mongodb/consensus-decision-raw.txt | grep -A50 "decision_id"
```

### Para ver a resposta do Gateway:
```bash
cat gateway/intent-response.json | jq '.'
```

### Para verificar IDs de rastreabilidade:
```bash
cat tracking/test_tracking_ids.txt
```

### Para ler traces do Jaeger:
```bash
cat jaeger/jaeger-traces-consensus.json | jq '.data[0]'
```

---
*Dados capturados em 2026-02-21*
*Teste: Fluxos A-B-C do Neural Hive-Mind*
*Total de arquivos: 26*
*Tamanho total: ~75KB*
