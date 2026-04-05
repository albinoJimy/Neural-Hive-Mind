# Guia de Schemas Avro - ML Inference API

Este guia documenta o uso de schemas Avro no ML Inference API do Neural Hive-Mind.

## Visão Geral

O ML Inference API suporta serialização Avro para compatibilidade com Kafka Schema Registry. Isso permite:

- Comunicação eficiente com serviços Kafka
- Validação de schemas em tempo de compilação
- Evolução compatível de schemas
- Integração com ferramentas de dados

## Localização dos Schemas

Os schemas Avro estão definidos em:

```
schemas/
├── ml-inference-request/
│   └── ml-inference-request.avsc
├── ml-inference-response/
│   └── ml-inference-response.avsc
├── ml-inference-batch-request/
│   └── ml-inference-batch-request.avsc
└── ml-inference-batch-response/
    └── ml-inference-batch-response.avsc
```

## Schemas Disponíveis

### 1. InferenceRequest

**Nome:** `InferenceRequest`
**Namespace:** `io.neuralhive.inference`
**Arquivo:** `ml-inference-request.avsc`

Campos:
- `request_id` (string): UUID único do request
- `intent_text` (string, nullable): Texto da intenção
- `features` (map<string,double>, nullable): Features extraídas
- `specialist_confidence` (double): Confiança do especialista (0.0-1.0)
- `specialist_type` (string, nullable): Tipo do especialista
- `model_version` (string, nullable): Versão do modelo (default: "latest")
- `options` (InferenceOptions, nullable): Opções de inferência
- `timestamp` (long, nullable): Timestamp em millis

### 2. InferenceResponse

**Nome:** `InferenceResponse`
**Namespace:** `io.neuralhive.inference`
**Arquivo:** `ml-inference-response.avsc`

Campos:
- `request_id` (string): ID do request original
- `decision` (enum): "approve", "reject", "review_required"
- `confidence` (double): Confiança da predição (0.0-1.0)
- `probabilities` (map<string,double>, nullable): Probabilidades por classe
- `features` (map<string,double>, nullable): Features usadas
- `model_version` (string): Versão do modelo
- `inference_time_ms` (double): Tempo de inferência em ms
- `timestamp` (long): Timestamp em millis
- `error` (string, nullable): Mensagem de erro

### 3. BatchInferenceRequest

**Nome:** `BatchInferenceRequest`
**Namespace:** `io.neuralhive.inference`
**Arquivo:** `ml-inference-batch-request.avsc`

Campos:
- `batch_id` (string): UUID único do batch
- `requests` (array<InferenceRequest>): Lista de requests
- `options` (BatchOptions, nullable): Opções de processamento
- `timestamp` (long): Timestamp em millis

### 4. BatchInferenceResponse

**Nome:** `BatchInferenceResponse`
**Namespace:** `io.neuralhive.inference`
**Arquivo:** `ml-inference-batch-response.avsc`

Campos:
- `batch_id` (string): ID do batch original
- `results` (array<InferenceResponse>): Resultados individuais
- `total_processed` (int): Total de itens
- `successful` (int): Bem-sucedidos
- `failed` (int): Falhados
- `aggregate_stats` (map<string,double>, nullable): Estatísticas
- `total_inference_time_ms` (double): Tempo total em ms
- `timestamp` (long): Timestamp em millis

## Uso na API

### Endpoints JSON (existentes)

```bash
# Predição individual
POST /api/v1/inference/predict
Content-Type: application/json

{
  "intent_text": "Create new user",
  "specialist_confidence": 0.8,
  "options": {
    "return_probabilities": true
  }
}
```

### Endpoints Avro (novos)

```bash
# Predição individual com Avro
POST /api/v1/inference/predict/avro
Content-Type: application/avro
Accept: application/avro

<dados binários Avro>

# Predição em batch com Avro
POST /api/v1/inference/predict-batch/avro
Content-Type: application/avro
Accept: application/avro

<dados binários Avro>
```

### Listar e Obter Schemas

```bash
# Listar todos os schemas
GET /api/v1/inference/schemas

# Obter definição de schema específico
GET /api/v1/inference/schemas/inference_request

# Download arquivo .avsc
GET /api/v1/inference/schemas/inference_request.avsc
```

## Uso Programático (Python)

### Conversão Pydantic <-> Avro

```python
from src.schemas.avro_schemas import (
    pydantic_to_avro,
    avro_to_pydantic,
    pydantic_response_to_avro,
    avro_to_pydantic_response,
    AvroSchemaRegistry,
)
from src.models.schemas import PredictRequest, PredictResponse

# Pydantic -> Avro
request = PredictRequest(
    intent_text="Create user",
    specialist_confidence=0.8,
)
avro_dict = pydantic_to_avro(request)

# Avro -> Pydantic
restored = avro_to_pydantic(avro_dict)

# Response
response = PredictResponse(
    decision="approve",
    confidence=0.95,
    model_version="v7",
    inference_time_ms=42.0,
)
response_avro = pydantic_response_to_avro(response, request_id="req-123")

# Registry para serialização binária
registry = AvroSchemaRegistry()

# Serializar para binário
avro_bytes = registry.serialize(avro_dict, "inference_request")

# Desserializar de binário
restored_dict = registry.deserialize(avro_bytes, "inference_request")
```

### Helper Functions

```python
from src.schemas.avro_schemas import (
    create_inference_request,
    create_inference_response,
)

# Criar request Avro diretamente
request = create_inference_request(
    intent_text="Test intent",
    specialist_confidence=0.75,
    specialist_type="security",
    include_probabilities=True,
)

# Criar response Avro diretamente
response = create_inference_response(
    request_id="req-123",
    decision="approve",
    confidence=0.92,
    model_version="v7",
    inference_time_ms=30.5,
)
```

## Integração com Kafka

### Producer

```python
from confluent_kafka import Producer
from src.schemas.avro_schemas import AvroSchemaRegistry, pydantic_to_avro

registry = AvroSchemaRegistry()
producer = Producer({"bootstrap.servers": "localhost:9092"})

# Criar request Pydantic
request = PredictRequest(intent_text="Test", specialist_confidence=0.8)

# Converter para Avro
avro_dict = pydantic_to_avro(request)

# Serializar
avro_bytes = registry.serialize(avro_dict, "inference_request")

# Publicar no Kafka
producer.produce(
    topic="ml-inference-requests",
    value=avro_bytes,
    key=request_id.encode("utf-8"),
)
producer.flush()
```

### Consumer

```python
from conflient_kafka import Consumer
from src.schemas.avro_schemas import AvroSchemaRegistry, avro_to_pydantic

registry = AvroSchemaRegistry()
consumer = Consumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "ml-inference-consumer",
    "auto.offset.reset": "earliest",
})
consumer.subscribe(["ml-inference-responses"])

while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue

    # Desserializar
    avro_dict = registry.deserialize(msg.value(), "inference_response")

    # Converter para Pydantic
    response = avro_to_pydantic_response(avro_dict)

    print(f"Decision: {response.decision}, Confidence: {response.confidence}")
```

## Validação de Schema

```python
from src.schemas.avro_schemas import AvroSchemaRegistry

registry = AvroSchemaRegistry()

# Validar dados
data = {
    "request_id": "test-123",
    "intent_text": "Test",
    "specialist_confidence": 0.8,
    "specialist_type": None,
    "model_version": "latest",
    "options": None,
    "timestamp": None,
}

is_valid = registry.validate(data, "inference_request")
print(f"Valid: {is_valid}")
```

## Configuração

### Variáveis de Ambiente

Nenhuma configuração adicional é necessária. O Avro usa fallback automático para JSON se a biblioteca `avro-python3` não estiver instalada.

### Dependência

```toml
dependencies = [
    # ...
    "avro-python3>=1.10.0",
]
```

## Boas Práticas

1. **Use Avro para comunicação entre serviços** - Mais eficiente que JSON
2. **Versionamento de schemas** - Ao modificar schemas, mantenha compatibilidade retroativa
3. **Valide schemas em dev** - Use `registry.validate()` antes de deploy
4. **Fallback JSON** - A API suporta ambos os formatos para compatibilidade

## Evolução de Schema

### Regras de Compatibilidade

1. **Adicionar campos** com `default` - OK
2. **Remover campos** - Use `default` no novo schema
3. **Modificar tipos** - Requer nova versão do schema
4. **Renomear** - Não é suportado, crie novo campo

### Exemplo de Evolução

```json
// Versão 1
{
  "name": "confidence",
  "type": "double"
}

// Versão 2 (compatível)
{
  "name": "confidence",
  "type": ["null", "double"],
  "default": null
}
```

## Troubleshooting

### Erro: "Avro not available"

**Causa:** Biblioteca `avro-python3` não instalada

**Solução:**
```bash
pip install avro-python3
```

A API usa JSON como fallback automaticamente.

### Erro: "Schema not found"

**Causa:** Nome de schema incorreto

**Solução:** Use um dos nomes válidos:
- `inference_request`
- `inference_response`
- `batch_request`
- `batch_response`

### Erro de Validação Pydantic

**Causa:** Timestamp `None` não é aceito

**Solução:** O módulo Avro usa `datetime.utcnow()` como default para timestamps `None`.

## Referências

- [Spec ML Inference](../../../.agent-os/specs/2026-04-03-gaps-criticos/spec-ml-inference.md)
- [Apache Avro](https://avro.apache.org/docs/current/)
- [Confluent Schema Registry](https://docs.confluent.io/platform/current/schema-registry/index.html)
