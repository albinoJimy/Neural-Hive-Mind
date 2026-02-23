# RELATÓRIO FINAL DIAGNÓSTICO - GATEWAY/STE COMPATIBILIDADE - 2026-02-23

## Resumo Executivo

**Status:** 🔍 DIAGNÓSTICO COMPLETO - BLOQUEIO IDENTIFICADO
**Investigação:** Gateway serializando JSON em vez de Avro
**Causa Raiz:** `kafka_producer` global está `None` ou perde o `avro_serializer` antes das requisições

---

## 1. PROBLEMA CONFIRMADO

### 1.1 Sintoma
- Gateway envia intenção com sucesso (HTTP 200, intent_id gerado)
- STE consome mensagem (LAG=0 no Kafka)
- STE não processa a intenção ("0 msgs processadas" nos logs)

### 1.2 Raiz Descoberta

**Gateway está enviando JSON, não Avro:**

```
Teste manual do AvroSerializer:
  First byte: 0 (hex: 0x00)
  >>> FORMAT: AVRO (Confluent wire format) ✅

Mensagem real no Kafka:
  First byte: 123 (hex: 0x7B = '{')
  >>> FORMAT: JSON ❌
```

---

## 2. DIAGNÓSTICO DETALHADO

### 2.1 AvroSerializer Funciona Corretamente

Teste manual no Gateway pod:
```bash
producer = KafkaIntentProducer(settings.kafka_bootstrap_servers, settings.schema_registry_url)
asyncio.run(producer.initialize())
# Result: "Schema Registry habilitado url=https://schema-registry..."

serialized = producer.avro_serializer(avro_data, ctx)
# First 5 bytes hex: 000000000d
# First byte: 0 (hex: 0x00)
# >>> FORMAT: AVRO (Confluent wire format) ✅
```

**Conclusão:** O AvroSerializer está funcionando perfeitamente quando testado manualmente.

### 2.2 Configurações Estão Corretas

```bash
SCHEMA_REGISTRY_URL: https://schema-registry.kafka.svc.cluster.local:8081/apis/ccompat/v7
SCHEMA_REGISTRY_TLS_ENABLED: true
SCHEMA_REGISTRY_TLS_VERIFY: false
```

Gateway e STE ambos têm as mesmas configurações de Schema Registry.

### 2.3 Mensagem no Kafka é JSON

Ao ler a mensagem diretamente do Kafka:
```bash
First 20 bytes hex: 7b22696e74656e745f6964223a20226561336131
First 5 bytes as integers: [123, 34, 105, 110, 116]
>>> JSON format (opening brace 0x7B)
UTF-8 decode success: {"intent_id": "ea3a16bf...", ...}
```

**Conclusão:** A mensagem real no Kafka é JSON, não Avro.

### 2.4 kafka_producer Global é None

```bash
import main
print(main.kafka_producer)
# Result: None
```

Porém, o health check reporta `kafka_producer: healthy` e requisições funcionam.

**Possível causa:** Uvicorn carrega o app em um escopo isolado, e o import direto não acessa o mesmo objeto.

---

## 3. ANÁLISE DO CÓDIGO

### 3.1 Fluxo de Serialização no Gateway

**Arquivo:** `services/gateway-intencoes/src/kafka/producer.py`

```python
# Linhas 413-430: Escolha entre Avro e JSON
if self.avro_serializer:
    avro_data = intent_envelope.to_avro_dict()
    serialization_context = SerializationContext(topic, MessageField.VALUE)
    serialized_value = self.avro_serializer(avro_data, ctx)
    content_type = "application/avro"
else:
    # Fallback para JSON
    avro_data = intent_envelope.to_avro_dict()
    if USE_ORJSON:
        serialized_value = orjson.dumps(avro_data)
    else:
        serialized_value = json.dumps(avro_data).encode("utf-8")
    content_type = "application/json"
```

**Para o código entrar no `else` (JSON), `self.avro_serializer` deve ser `None`.**

### 3.2 Inicialização do AvroSerializer

**Arquivo:** `services/gateway-intencoes/src/kafka/producer.py`

```python
# Linhas 167-191
if self.schema_registry_url and self.schema_registry_url.strip():
    sr_conf = {"url": self.schema_registry_url}
    if (self.settings.schema_registry_tls_enabled
            and not self.settings.schema_registry_tls_verify):
        sr_conf["ssl.ca.location"] = ""
    self.schema_registry_client = SchemaRegistryClient(sr_conf)

    with open("/app/schemas/intent-envelope.avsc", "r") as f:
        schema_str = f.read()

    self.avro_serializer = AvroSerializer(
        self.schema_registry_client, schema_str
    )
    logger.info("Schema Registry habilitado", url=self.schema_registry_url)
else:
    logger.warning("Schema Registry desabilitado")
    self.avro_serializer = None
```

---

## 4. HIPÓTESES PARA O BLOQUEIO

### 4.1 Hipótese 1: Producer Recriado Perde AvroSerializer

**Possível cenário:**
1. `kafka_producer` é inicializado durante bootstrap com `avro_serializer` configurado
2. Algum evento (reconnect, error, reload) faz o producer ser recriado
3. O novo producer não tem `avro_serializer` (fallback para JSON)
4. Mensagens subsequentes são JSON

**Evidência suportando:**
- Teste manual mostra AvroSerializer funciona
- Mensagens reais são JSON

### 4.2 Hipótese 2: Exceção durante Inicialização

**Possível cenário:**
1. `initialize()` é chamado mas AvroSerializer lança exceção
2. Exceção é capturada silenciosamente
3. `avro_serializer` fica como `None`
4. `producer._ready` é setado para `True` mesmo sem avro_serializer

**Problema:** Não vemos logs de erro na inicialização.

### 4.3 Hipótese 3: Múltiplas Instâncias de Producer

**Possível cenário:**
1. O código usa um `kafka_producer` diferente do que testamos manualmente
2. Pode haver lazy initialization que cria um producer sem Schema Registry
3. Ou o producer usado pela API é diferente do global

---

## 5. PRÓXIMOS PASSOS RECOMENDADOS

### Prioridade 1 - Adicionar Logs de Depuração

**No Gateway (`producer.py`):**

```python
# Em send_intent(), antes da serialização
logger.debug(
    "DEBUG send_intent",
    avro_serializer_is_none=self.avro_serializer is None,
    avro_serializer_type=type(self.avro_serializer),
    _ready=self._ready,
)

# Após serialização
if content_type == "application/avro":
    logger.info("Message serialized as Avro", len=len(serialized_value))
else:
    logger.warning("Message serialized as JSON (fallback)", len=len(serialized_value))
```

### Prioridade 2 - Verificar Estado Runtime

**Script para executar no pod:**
```python
# Acessar o producer via FastAPI app state
import main
app = main.app  # FastAPI app
# Verificar se producer está em app.state ou em outro lugar
```

### Prioridade 3 - Testar com Avro Desabilitado

Temporariamente desabilitar Schema Registry no Gateway para ver se JSON funciona:
```yaml
schema_registry_url: ""  # Forçar JSON
```

Se funcionar, confirmamos que o problema está no AvroSerializer.

---

## 6. SOLUÇÃO PROPOSTA

### Opção A: Garantir AvroSerializer Sempre Inicializado

1. Adicionar verificação explícita no `initialize()`:
   ```python
   if not self.avro_serializer:
       raise RuntimeError("AvroSerializer initialization failed")
   ```

2. Adicionar health check específico:
   ```python
   def is_healthy(self):
       return self._ready and self.avro_serializer is not None
   ```

### Opção B: Usar JSON Temporariamente

1. Configurar Gateway para usar JSON explicitamente
2. Configurar STE para aceitar JSON (já faz auto-detecção)
3. Testar fluxo completo E2E

---

## 7. STATUS INVESTIGAÇÃO

| Componente | Status | Observação |
|------------|--------|------------|
| Gateway Schema Registry | ✅ Configurado corretamente | URL válida |
| Gateway AvroSerializer | ✅ Funciona em teste | Magic byte 0x00 |
| Gateway Mensagem Real | ❌ JSON não Avro | Magic byte 0x7B |
| STE Consumer | ✅ Consome mensagens | LAG=0 |
| STE Deserialização | ❌ Falha (espera Avro, recebe JSON) | "Unexpected magic byte 123" |
| kafka_producer global | ❓ None (scope issue?) | Requisições funcionam |

---

## 8. CONCLUSÃO

**O problema NÃO é:**
- ❌ Configuração de Schema Registry (igual em Gateway e STE)
- ❌ Incompatibilidade AvroSerializer/Apicurio (funciona em teste)
- ❌ Schema Registry conectividade (testes OK)

**O problema É:**
- ✅ Gateway está enviando JSON em vez de Avro
- ✅ `kafka_producer` global não acessível via import direto
- ✅ `avro_serializer` está `None` ou não está sendo usado no momento do send

**Recomendação:** Adicionar logs detalhados no fluxo `send_intent()` para identificar exatamente quando e por que o AvroSerializer não está sendo usado.

---

**FIM DO RELATÓRIO**
