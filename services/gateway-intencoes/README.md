# Gateway de Intenções - Neural Hive-Mind

Gateway para captura e processamento de intenções do Neural Hive-Mind, com suporte a texto e voz.

## Funcionalidades

- **Processamento de Texto**: Pipeline NLU com classificação de domínio e extração de entidades
- **Processamento de Voz**: Pipeline ASR + NLU para transcrição e análise de áudio
- **Roteamento Adaptativo**: Sistema de roteamento baseado em níveis de confiança
- **Cache Distribuído**: Integração com Redis Cluster para cache de resultados NLU
- **Observabilidade**: Métricas Prometheus e tracing OpenTelemetry
- **Segurança**: Autenticação OAuth2/Keycloak e mascaramento de PII

## Configurações NLU

O serviço oferece configurações avançadas para o pipeline de Natural Language Understanding (NLU):

### Thresholds de Confiança

```yaml
# Threshold padrão para confiança mínima aceitável
NLU_CONFIDENCE_THRESHOLD: "0.5"

# Threshold estrito para alta confiança
NLU_CONFIDENCE_THRESHOLD_STRICT: "0.75"

# Habilitar threshold adaptativo baseado em contexto
NLU_ADAPTIVE_THRESHOLD_ENABLED: "true"
```

#### Thresholds Adaptativos

Quando `NLU_ADAPTIVE_THRESHOLD_ENABLED=true`, o sistema ajusta dinamicamente o threshold de confiança baseado em:

- **Comprimento do texto**: Textos mais longos (>20 palavras) reduzem o threshold em até 10%
- **Presença de entidades**: 3+ entidades extraídas reduzem o threshold em até 10%
- **Contexto rico**: Presença de informações contextuais reduz o threshold em 5%

### Regras de Classificação Externas

Configure regras customizadas de classificação através do arquivo `nlu_rules.yaml`:

```yaml
# Caminho para arquivo de regras NLU customizado
NLU_RULES_CONFIG_PATH: "/app/config/nlu_rules.yaml"
```

#### Estrutura do `nlu_rules.yaml`

```yaml
domains:
  BUSINESS:
    keywords:
      - negócio
      - venda
      - cliente
      - relatório
    patterns:
      - '\b(relatório|dashboard|report)\b'
      - '\b(vendas?|sales)\b'
    subcategories:
      reporting:
        - relatório
        - dashboard
      sales:
        - venda
        - vendas

  TECHNICAL:
    keywords:
      - api
      - bug
      - código
    patterns:
      - '\b(api|rest|graphql)\b'
      - '\b(bug|erro|error)\b'
    subcategories:
      bug:
        - bug
        - erro
      development:
        - código
        - desenvolver

quality_thresholds:
  min_text_length: 3
  max_text_length: 10000
  min_words: 2
  spam_patterns:
    - '^(.)\1{10,}$'  # Caracteres repetidos

confidence_boosters:
  text_length_boost:
    threshold: 50  # caracteres
    boost: 0.05    # +5% confiança
  entity_presence_boost:
    threshold: 2   # mínimo de entidades
    boost: 0.05    # +5% confiança
  multiple_subcategories_boost:
    threshold: 2
    boost: 0.05
  context_role_match_boost:
    boost: 0.10    # +10% quando role corresponde ao domínio
```

### Cache de Resultados NLU

```yaml
# Habilitar cache de resultados NLU em Redis
NLU_CACHE_ENABLED: "true"

# TTL do cache em segundos (1 hora)
NLU_CACHE_TTL_SECONDS: "3600"
```

O cache armazena:
- Texto processado
- Domínio classificado
- Classificação específica
- Score de confiança
- **Status de confiança** (high/medium/low)
- Entidades extraídas
- Palavras-chave
- Flag de validação manual

### Roteamento por Confiança

O gateway roteia intenções automaticamente baseado no nível de confiança:

#### Alta Confiança (≥ 0.75)
- **Status**: `high`
- **Roteamento**: Tópico de domínio normal
- **Validação**: Não requerida

#### Média Confiança (0.50 - 0.74)
- **Status**: `medium`
- **Roteamento**: Tópico de domínio normal
- **Validação**: Opcional (flag enviada para downstream)
- **Nota**: "Processado com confiança média - pode requerer revisão posterior"

#### Baixa Confiança (0.30 - 0.49)
- **Status**: `low`
- **Roteamento**: Tópico de domínio normal
- **Validação**: Requerida
- **Nota**: "Processado com confiança baixa - recomenda-se validação"

#### Confiança Muito Baixa (< 0.30)
- **Status**: `low`
- **Roteamento**: `intentions.validation` (tópico especial)
- **Validação**: Obrigatória
- **Nota**: "Confiança muito baixa - requer validação manual"

### Headers Kafka

As mensagens publicadas no Kafka incluem headers com metadados de confiança:

```
confidence-score: "0.85"
confidence-status: "high"
requires-validation: "false"
adaptive-threshold-used: "true"
```

## Variáveis de Ambiente

### NLU Pipeline

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `NLU_LANGUAGE_MODEL` | `pt_core_news_sm` | Modelo spaCy para processamento |
| `NLU_CONFIDENCE_THRESHOLD` | `0.5` | Threshold padrão de confiança |
| `NLU_CONFIDENCE_THRESHOLD_STRICT` | `0.75` | Threshold estrito para alta confiança |
| `NLU_ADAPTIVE_THRESHOLD_ENABLED` | `true` | Habilitar threshold adaptativo |
| `NLU_RULES_CONFIG_PATH` | `/app/config/nlu_rules.yaml` | Caminho para regras customizadas |
| `NLU_CACHE_ENABLED` | `true` | Habilitar cache de resultados |
| `NLU_CACHE_TTL_SECONDS` | `3600` | TTL do cache (1 hora) |

### Redis Cache

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `REDIS_CLUSTER_NODES` | `neural-hive-cache.redis-cluster.svc.cluster.local:6379` | Nodes do Redis Cluster |
| `REDIS_PASSWORD` | - | Senha de autenticação |
| `REDIS_DEFAULT_TTL` | `600` | TTL padrão (10 minutos) |

### Kafka

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `KAFKA_BOOTSTRAP_SERVERS` | `neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local:9092` | Servidores Kafka |
| `SCHEMA_REGISTRY_URL` | `http://schema-registry.neural-hive-kafka.svc.cluster.local:8081` | Schema Registry |

## Exemplos de Uso

### Configuração via Helm

```yaml
# values.yaml
gateway:
  nlu:
    confidenceThreshold: "0.5"
    confidenceThresholdStrict: "0.75"
    adaptiveThresholdEnabled: true
    cacheEnabled: true
    cacheTtlSeconds: 3600
    rulesConfigPath: "/app/config/nlu_rules.yaml"
```

### Configuração via Variáveis de Ambiente

```bash
export NLU_CONFIDENCE_THRESHOLD="0.5"
export NLU_CONFIDENCE_THRESHOLD_STRICT="0.75"
export NLU_ADAPTIVE_THRESHOLD_ENABLED="true"
export NLU_CACHE_ENABLED="true"
export NLU_CACHE_TTL_SECONDS="3600"
export NLU_RULES_CONFIG_PATH="/app/config/nlu_rules.yaml"
```

## Resposta da API

### Valores Possíveis do Campo `status`

O campo `status` na resposta indica o resultado do processamento e roteamento:

- **`processed`**: Intenção processada com confiança adequada (≥ routingThresholdHigh). Enviada para tópico normal.
- **`processed_low_confidence`**: Intenção processada com confiança baixa mas aceitável (routingThresholdLow ≤ confidence < routingThresholdHigh). Enviada para tópico normal com flag `requires_validation=true`.
- **`routed_to_validation`**: Intenção com confiança muito baixa (< routingThresholdLow). Enviada para tópico `intentions.validation` para validação manual.
- **`duplicate_detected`**: Intenção duplicada detectada via deduplicação Redis.
- **`error`**: Erro durante processamento.
- **`record_too_large`**: Intenção rejeitada por exceder limite de tamanho.

**Compatibilidade**: Consumidores devem estar preparados para aceitar todos os valores acima, especialmente `processed_low_confidence` que foi introduzido para suportar roteamento granular.

### Campos de Rastreamento (traceId e spanId)

Todas as respostas da API incluem campos de rastreamento OpenTelemetry:

- **`traceId`**: String hexadecimal de 32 caracteres que identifica a trace completa da requisição
- **`spanId`**: String hexadecimal de 16 caracteres que identifica o span específico da operação

Ambos os campos são `null` quando o tracing está desabilitado (`OTEL_ENABLED=false`).

### Processamento de Texto

```json
{
  "intent_id": "123e4567-e89b-12d3-a456-426614174000",
  "correlation_id": "abc-123",
  "status": "processed",
  "confidence": 0.85,
  "confidence_status": "high",
  "domain": "BUSINESS",
  "classification": "reporting",
  "processing_time_ms": 45.2,
  "requires_manual_validation": false,
  "adaptive_threshold_used": true,
  "traceId": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "spanId": "1a2b3c4d5e6f7a8b"
}
```

### Processamento com Baixa Confiança

```json
{
  "intent_id": "123e4567-e89b-12d3-a456-426614174000",
  "correlation_id": "abc-123",
  "status": "processed_low_confidence",
  "confidence": 0.42,
  "confidence_status": "low",
  "domain": "TECHNICAL",
  "classification": "general",
  "processing_time_ms": 52.1,
  "requires_manual_validation": true,
  "adaptive_threshold_used": true,
  "processing_notes": [
    "Processado com confiança baixa - recomenda-se validação"
  ],
  "traceId": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "spanId": "1a2b3c4d5e6f7a8b"
}
```

### Roteamento para Validação

```json
{
  "intent_id": "123e4567-e89b-12d3-a456-426614174000",
  "correlation_id": "abc-123",
  "status": "routed_to_validation",
  "confidence": 0.25,
  "confidence_status": "low",
  "domain": "TECHNICAL",
  "classification": "general",
  "processing_time_ms": 48.7,
  "requires_manual_validation": true,
  "adaptive_threshold_used": true,
  "processing_notes": [
    "Confiança muito baixa - requer validação manual"
  ],
  "validation_reason": "confidence_below_threshold",
  "confidence_threshold": 0.5,
  "traceId": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "spanId": "1a2b3c4d5e6f7a8b"
}
```

## Monitoramento

### Métricas Prometheus

- `gateway_intent_total{domain, channel, status}` - Total de intenções processadas
- `gateway_intent_processing_duration_seconds{domain, channel}` - Tempo de processamento
- `gateway_intent_confidence_score{domain, channel}` - Distribuição de confiança
- `gateway_low_confidence_routed_total{domain, channel, route_target}` - Roteamentos por baixa confiança

### Logs Estruturados

```json
{
  "timestamp": "2025-11-10T12:34:56Z",
  "level": "info",
  "message": "NLU processado",
  "domínio": "BUSINESS",
  "classificação": "reporting",
  "confidence": 0.85,
  "status": "high",
  "threshold": 0.5,
  "idioma": "pt"
}
```

## Health Checks

- `GET /health` - Status de todos os componentes
- `GET /ready` - Readiness probe para Kubernetes
- `GET /status` - Status detalhado do serviço

## Desenvolvimento

### Build Local

```bash
docker build -t gateway-intencoes:latest \
  -f services/gateway-intencoes/Dockerfile .
```

### Executar Localmente

```bash
docker run -p 8000:8000 \
  -e NLU_CONFIDENCE_THRESHOLD=0.5 \
  -e NLU_ADAPTIVE_THRESHOLD_ENABLED=true \
  gateway-intencoes:latest
```

## Testes

```bash
# Testes unitários
pytest services/gateway-intencoes/tests/unit/

# Testes de integração
pytest services/gateway-intencoes/tests/integration/
```
