# ANÁLISE PROFUNDA: Problema de Deserialização Avro no Consensus Engine

**Data:** 2025-11-06
**Erro:** `'utf-8' codec can't decode byte 0xe8 in position 120: invalid continuation byte`
**Status:** CAUSA RAIZ IDENTIFICADA

---

## 1. MAPEAMENTO COMPLETO DO FLUXO DE SERIALIZAÇÃO/DESERIALIZAÇÃO

### 1.1. Producer (Semantic Translation Engine)

**Arquivo:** `/jimy/Neural-Hive-Mind/services/semantic-translation-engine/src/producers/plan_producer.py`

```python
# Linha 60: Schema path
schema_path = '/app/schemas/cognitive-plan.avsc'

# Linhas 69-72: Criação do AvroSerializer
self.avro_serializer = AvroSerializer(
    self.schema_registry_client,
    schema_str
)

# Linhas 115-120: Serialização
if self.avro_serializer:
    avro_data = cognitive_plan.to_avro_dict()
    serialization_context = SerializationContext(topic, MessageField.VALUE)
    value = self.avro_serializer(avro_data, serialization_context)
    content_type = 'application/avro'
else:
    # Fallback JSON
    value = json.dumps(cognitive_plan.to_avro_dict(), default=str).encode('utf-8')
    content_type = 'application/json'

# Linha 135: Header indicando content-type
headers.append(('content-type', content_type.encode('utf-8')))
```

**Biblioteca:** `confluent-kafka==2.3.0`
**Wire Format:** Confluent Wire Format (magic byte 0x00 + 4 bytes schema ID + avro binary)
**Schema Registry:** SIM (quando configurado)

---

### 1.2. Consumer (Consensus Engine)

**Arquivo:** `/jimy/Neural-Hive-Mind/services/consensus-engine/src/consumers/plan_consumer.py`

```python
# Linha 61: Schema path DIFERENTE!
schema_path = '/app/schemas/cognitive-plan/cognitive-plan.avsc'

# Linhas 73-76: Criação do AvroDeserializer
self.avro_deserializer = AvroDeserializer(
    schema_registry_client,
    schema_str
)

# Linhas 93-100: Configuração do AIOKafkaConsumer
self.consumer = AIOKafkaConsumer(
    self.config.kafka_plans_topic,
    bootstrap_servers=self.config.kafka_bootstrap_servers,
    group_id=self.config.kafka_consumer_group_id,
    auto_offset_reset=self.config.kafka_auto_offset_reset,
    enable_auto_commit=self.config.kafka_enable_auto_commit,
    value_deserializer=self._deserialize_message  # <-- PROBLEMA AQUI!
)

# Linhas 38-43: Método _deserialize_message
if self.avro_deserializer:
    try:
        ctx = SerializationContext(self.config.kafka_plans_topic, MessageField.VALUE)
        result = self.avro_deserializer(message_bytes, ctx)  # <-- FALHA AQUI
        logger.debug('Mensagem deserializada com Avro')
        return result
    except Exception as e:
        logger.warning('Falha ao deserializar Avro, tentando JSON', error=str(e))

# Linhas 49-50: Fallback JSON
return json.loads(message_bytes.decode('utf-8'))  # <-- ERRO UTF-8 AQUI!
```

**Biblioteca:** `aiokafka>=0.8.1` + `confluent-kafka>=2.3.0`
**Problema:** INCOMPATIBILIDADE DE INTEGRAÇÃO

---

### 1.3. Gateway (Referência)

**Arquivo:** `/jimy/Neural-Hive-Mind/services/gateway-intencoes/src/kafka/producer.py`

```python
# Linha 115: Schema path
with open('/app/schemas/intent-envelope.avsc', 'r') as f:
    schema_str = f.read()

# Linhas 118-121: AvroSerializer
self.avro_serializer = AvroSerializer(
    self.schema_registry_client,
    schema_str
)

# Linhas 218-227: Serialização
if self.avro_serializer:
    avro_data = intent_envelope.to_avro_dict()
    serialization_context = SerializationContext(topic, MessageField.VALUE)
    serialized_value = self.avro_serializer(avro_data, serialization_context)
    content_type = 'application/avro'
else:
    # Fallback JSON
    avro_data = intent_envelope.to_avro_dict()
    serialized_value = json.dumps(avro_data, ensure_ascii=False).encode('utf-8')
    content_type = 'application/json'
```

**Biblioteca:** `confluent-kafka==2.3.0`
**Padrão:** IGUAL ao Semantic Translation Engine

---

## 2. IDENTIFICAÇÃO PRECISA DA CAUSA RAIZ

### 2.1. Wire Format do Confluent

Quando `AvroSerializer` (confluent-kafka) serializa uma mensagem:

```
Byte 0:        0x00 (magic byte)
Bytes 1-4:     Schema ID (big-endian)
Bytes 5+:      Avro binary data
```

**Exemplo real:**
- Byte 0: `0x00` (magic)
- Bytes 1-4: `0x00 0x00 0x00 0x01` (schema ID = 1)
- Byte 120 poderia ser: `0xe8` (parte do encoding Avro binário)

O byte `0xe8` NÃO É UTF-8 válido quando isolado - é parte do wire format binário Avro!

---

### 2.2. Incompatibilidade Arquitetural

**PROBLEMA CRÍTICO:** `aiokafka` + `confluent_kafka.AvroDeserializer` são INCOMPATÍVEIS quando usados como `value_deserializer`!

#### Por que?

1. **aiokafka** espera que `value_deserializer` seja uma função/callable SÍNCRONA
2. **AvroDeserializer** do confluent-kafka foi projetado para:
   - Funcionar com `Consumer` (confluent-kafka)
   - Ser chamado MANUALMENTE em mensagens já consumidas
   - NÃO para ser usado como callback em `AIOKafkaConsumer`

3. **Fluxo atual (ERRADO):**
   ```
   AIOKafkaConsumer recebe bytes
     → chama value_deserializer(_deserialize_message)
       → tenta AvroDeserializer(message_bytes, ctx)
         → FALHA (incompatibilidade de integração)
       → fallback: json.loads(message_bytes.decode('utf-8'))
         → ERRO: 'utf-8' codec can't decode byte 0xe8
   ```

4. **Por que o fallback JSON falha?**
   - Os bytes recebidos estão em Confluent Wire Format (0x00 + schema ID + avro binary)
   - Tentar fazer `.decode('utf-8')` em dados binários Avro = ERRO

---

### 2.3. Diferenças nos Schema Paths

**Semantic Translation Engine (Producer):**
```python
schema_path = '/app/schemas/cognitive-plan.avsc'
```

**Consensus Engine (Consumer):**
```python
schema_path = '/app/schemas/cognitive-plan/cognitive-plan.avsc'
```

**Dockerfile Semantic Translation Engine:**
```dockerfile
COPY --chown=app:app schemas/cognitive-plan/cognitive-plan.avsc /app/schemas/cognitive-plan.avsc
```

**Dockerfile Consensus Engine:**
```dockerfile
COPY schemas /app/schemas
```

**Resultado:** O producer copia o schema para um path DIFERENTE do que está no código!

---

### 2.4. Verificação de Bibliotecas

| Componente | confluent-kafka | aiokafka | Comentário |
|------------|----------------|----------|------------|
| Semantic Translation Engine | 2.3.0 | ❌ | Usa apenas confluent-kafka |
| Consensus Engine | >=2.3.0 | >=0.8.1 | Usa AMBOS (problema!) |
| Gateway | 2.3.0 | ❌ | Usa apenas confluent-kafka |

---

## 3. VALIDAÇÃO DO PROBLEMA

### 3.1. Schema Avro Verificado

**Arquivo:** `/jimy/Neural-Hive-Mind/schemas/cognitive-plan/cognitive-plan.avsc`

✅ Schema válido e bem definido
✅ Contém todos os campos necessários
✅ Tipos compatíveis com Avro

### 3.2. Modelo Python Verificado

**Arquivo:** `/jimy/Neural-Hive-Mind/services/semantic-translation-engine/src/models/cognitive_plan.py`

```python
def to_avro_dict(self) -> Dict[str, Any]:
    """Convert to Avro-compatible dictionary"""
    return {
        'plan_id': self.plan_id,
        'version': self.version,
        # ... todos os campos mapeados corretamente
        'created_at': int(self.created_at.timestamp() * 1000),  # timestamp-millis
        'risk_band': self.risk_band.value if hasattr(self.risk_band, 'value') else self.risk_band,
        # ... etc
    }
```

✅ Conversão correta para Avro
✅ Tipos compatíveis
✅ Timestamps em milliseconds (logicalType timestamp-millis)

---

## 4. PROPOSTA DE CORREÇÃO (COM JUSTIFICATIVA)

### Opção 1: Migrar Consensus Engine para confluent-kafka (RECOMENDADO)

**Vantagens:**
- ✅ Consistência com outros componentes (Gateway, Semantic Engine)
- ✅ Suporte nativo a Schema Registry
- ✅ Wire format compatível
- ✅ Transações Kafka nativas
- ✅ Melhor performance (C librdkafka)

**Desvantagens:**
- ⚠️ Requer refatoração do consumer (síncrono em vez de async)
- ⚠️ Mudança significativa na arquitetura

**Justificativa:**
Esta é a solução mais robusta e alinhada com o resto da arquitetura. Todo o ecossistema Neural Hive-Mind já usa `confluent-kafka`, manter `aiokafka` em apenas um componente cria complexidade desnecessária.

---

### Opção 2: Usar fastavro para deserialização (WORKAROUND)

**Vantagens:**
- ✅ Mantém aiokafka
- ✅ Suporte completo a Avro
- ✅ Pode decodificar Confluent Wire Format
- ✅ Mudança menos invasiva

**Desvantagens:**
- ⚠️ Requer implementação manual do wire format
- ⚠️ Não usa Schema Registry diretamente
- ⚠️ Mais código para manter

**Implementação:**

```python
import io
import struct
from fastavro import schemaless_reader

def _deserialize_message(self, message_bytes: bytes) -> Dict[str, Any]:
    if not message_bytes:
        raise ValueError('Mensagem vazia')

    # Check for Confluent wire format
    if message_bytes[0] == 0x00:
        # Extract schema ID (bytes 1-4, big-endian)
        schema_id = struct.unpack('>I', message_bytes[1:5])[0]

        # Get schema from registry or cache
        schema = self._get_schema(schema_id)

        # Deserialize Avro (skip 5 bytes: magic + schema ID)
        avro_bytes = message_bytes[5:]
        return schemaless_reader(io.BytesIO(avro_bytes), schema)
    else:
        # JSON fallback
        return json.loads(message_bytes.decode('utf-8'))
```

---

### Opção 3: Desabilitar Schema Registry no Consensus Engine (TEMPORÁRIO)

**Vantagens:**
- ✅ Solução imediata
- ✅ Zero mudanças de código

**Desvantagens:**
- ❌ Perde validação de schema
- ❌ Perde versionamento
- ❌ Usa JSON (menos eficiente)
- ❌ Não é solução definitiva

**Como fazer:**
```bash
# No Helm values ou ConfigMap
SCHEMA_REGISTRY_URL: ""  # ou remover a variável
```

Forçar producer a usar JSON:
```python
# No producer (temporário)
self.avro_serializer = None  # Força JSON
```

---

## 5. RECOMENDAÇÃO FINAL

### Solução em 2 fases:

#### Fase 1 (IMEDIATO): Workaround com fastavro
- Implementar deserialização manual com fastavro
- Corrigir schema path no Dockerfile
- Validar funcionamento

#### Fase 2 (PRÓXIMA SPRINT): Refatoração completa
- Migrar Consensus Engine para confluent-kafka
- Remover aiokafka
- Padronizar todos os consumidores

---

## 6. LISTA DE MUDANÇAS NECESSÁRIAS

### Para Opção 1 (confluent-kafka - RECOMENDADO):

**Arquivo:** `services/consensus-engine/requirements.txt`
```diff
- aiokafka>=0.8.1
+ confluent-kafka==2.3.0
```

**Arquivo:** `services/consensus-engine/src/consumers/plan_consumer.py`
```diff
- from aiokafka import AIOKafkaConsumer
+ from confluent_kafka import Consumer, KafkaError
+ from confluent_kafka.serialization import SerializationContext, MessageField

class PlanConsumer:
-   async def initialize(self):
+   def initialize(self):
        # ...
-       self.consumer = AIOKafkaConsumer(
+       self.consumer = Consumer({
+           'bootstrap.servers': self.config.kafka_bootstrap_servers,
+           'group.id': self.config.kafka_consumer_group_id,
+           'auto.offset.reset': self.config.kafka_auto_offset_reset,
+           'enable.auto.commit': self.config.kafka_enable_auto_commit,
-           value_deserializer=self._deserialize_message
-       )
+       })
+       self.consumer.subscribe([self.config.kafka_plans_topic])

-   async def start(self):
+   def start(self):
        self.running = True

-       async for message in self.consumer:
+       while self.running:
+           msg = self.consumer.poll(timeout=1.0)
+           if msg is None:
+               continue
+           if msg.error():
+               if msg.error().code() == KafkaError._PARTITION_EOF:
+                   continue
+               else:
+                   logger.error('Consumer error', error=msg.error())
+                   break
+
+           # Deserializar manualmente
+           value = self._deserialize_message(msg.value())
-           await self._process_message(message)
+           self._process_message(msg, value)
```

**Arquivo:** `services/consensus-engine/Dockerfile`
```diff
# Corrigir path do schema
- COPY schemas /app/schemas
+ COPY --chown=consensus:consensus schemas/cognitive-plan/cognitive-plan.avsc /app/schemas/cognitive-plan/cognitive-plan.avsc
```

---

### Para Opção 2 (fastavro - WORKAROUND):

**Arquivo:** `services/consensus-engine/requirements.txt`
```diff
+ fastavro>=1.8.0
```

**Arquivo:** `services/consensus-engine/src/consumers/plan_consumer.py`
```python
import io
import struct
from typing import Dict, Any, Optional
from fastavro import schemaless_reader, parse_schema

class PlanConsumer:
    def __init__(self, config, specialists_client, mongodb_client, pheromone_client):
        # ...
        self.avro_schema_parsed = None
        self.schema_cache: Dict[int, Any] = {}  # Cache de schemas por ID

    def _deserialize_message(self, message_bytes: bytes) -> Dict[str, Any]:
        '''
        Deserializa mensagem Kafka (Avro Confluent Wire Format ou JSON)
        '''
        if not message_bytes:
            raise ValueError('Mensagem vazia')

        # Check for Confluent wire format (magic byte 0x00)
        if message_bytes[0] == 0x00:
            try:
                # Extract schema ID (bytes 1-4, big-endian)
                schema_id = struct.unpack('>I', message_bytes[1:5])[0]
                logger.debug('Detectado Confluent wire format', schema_id=schema_id)

                # Use cached parsed schema
                if not self.avro_schema_parsed:
                    raise ValueError('Schema Avro não carregado')

                # Deserialize Avro (skip 5 bytes: magic + schema ID)
                avro_bytes = message_bytes[5:]
                result = schemaless_reader(io.BytesIO(avro_bytes), self.avro_schema_parsed)
                logger.debug('Mensagem deserializada com Avro (fastavro)')
                return result

            except Exception as e:
                logger.warning('Falha ao deserializar Avro wire format', error=str(e))
                # Não tenta JSON - wire format Avro não é JSON válido
                raise ValueError(f'Erro deserializando Avro: {e}')
        else:
            # Fallback para JSON (mensagens sem wire format)
            try:
                return json.loads(message_bytes.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error('Erro deserializando mensagem', error=str(e))
                raise ValueError(f'Não foi possível deserializar mensagem: {e}')

    async def initialize(self):
        '''Inicializa consumer Kafka com suporte a Avro'''

        # Carregar e parsear schema Avro
        schema_path = '/app/schemas/cognitive-plan/cognitive-plan.avsc'

        if os.path.exists(schema_path):
            try:
                with open(schema_path, 'r') as f:
                    schema_str = f.read()

                # Parsear schema com fastavro
                self.avro_schema_parsed = parse_schema(json.loads(schema_str))
                logger.info('Schema Avro carregado e parseado', schema_path=schema_path)

            except Exception as e:
                logger.warning('Falha carregando schema Avro', error=str(e))
                self.avro_schema_parsed = None
        else:
            logger.warning('Schema Avro não encontrado', path=schema_path)
            self.avro_schema_parsed = None

        # Inicializar consumer (sem mudanças)
        self.consumer = AIOKafkaConsumer(
            self.config.kafka_plans_topic,
            bootstrap_servers=self.config.kafka_bootstrap_servers,
            group_id=self.config.kafka_consumer_group_id,
            auto_offset_reset=self.config.kafka_auto_offset_reset,
            enable_auto_commit=self.config.kafka_enable_auto_commit,
            value_deserializer=self._deserialize_message
        )

        await self.consumer.start()
        logger.info('Plan consumer inicializado')
```

**Arquivo:** `services/consensus-engine/Dockerfile`
```diff
# Corrigir path do schema
- COPY schemas /app/schemas
+ COPY --chown=consensus:consensus schemas/cognitive-plan/cognitive-plan.avsc /app/schemas/cognitive-plan/cognitive-plan.avsc
```

---

## 7. VALIDAÇÃO PÓS-CORREÇÃO

### 7.1. Testes Unitários

```python
# test_plan_consumer.py

import pytest
import struct
import io
from fastavro import schemaless_writer, parse_schema

def test_deserialize_confluent_wire_format(plan_consumer):
    """Testa deserialização de mensagens no Confluent Wire Format"""

    # Criar mensagem de teste
    schema = parse_schema({
        "type": "record",
        "name": "TestPlan",
        "fields": [
            {"name": "plan_id", "type": "string"},
            {"name": "version", "type": "string"}
        ]
    })

    data = {"plan_id": "test-123", "version": "1.0.0"}

    # Serializar em Avro
    avro_bytes = io.BytesIO()
    schemaless_writer(avro_bytes, schema, data)

    # Adicionar wire format
    schema_id = 1
    wire_format = struct.pack('>BI', 0x00, schema_id) + avro_bytes.getvalue()

    # Deserializar
    result = plan_consumer._deserialize_message(wire_format)

    assert result['plan_id'] == 'test-123'
    assert result['version'] == '1.0.0'

def test_deserialize_json_fallback(plan_consumer):
    """Testa fallback para JSON"""

    json_data = '{"plan_id": "test-456", "version": "2.0.0"}'
    json_bytes = json_data.encode('utf-8')

    result = plan_consumer._deserialize_message(json_bytes)

    assert result['plan_id'] == 'test-456'
    assert result['version'] == '2.0.0'

def test_deserialize_invalid_wire_format(plan_consumer):
    """Testa erro em wire format inválido"""

    invalid_bytes = b'\x00\x00\x00\x00\x01INVALID'

    with pytest.raises(ValueError):
        plan_consumer._deserialize_message(invalid_bytes)
```

---

### 7.2. Teste de Integração

```python
# test_kafka_integration.py

import pytest
from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import SerializationContext, MessageField

@pytest.mark.integration
async def test_end_to_end_serialization(kafka_config, consensus_consumer):
    """Testa serialização no producer e deserialização no consumer"""

    # Setup producer
    producer = Producer({'bootstrap.servers': kafka_config.bootstrap_servers})
    schema_registry = SchemaRegistryClient({'url': kafka_config.schema_registry_url})

    with open('/app/schemas/cognitive-plan/cognitive-plan.avsc', 'r') as f:
        schema_str = f.read()

    serializer = AvroSerializer(schema_registry, schema_str)

    # Criar plano de teste
    plan_data = {
        'plan_id': 'integration-test',
        'version': '1.0.0',
        'intent_id': 'test-intent',
        # ... outros campos
    }

    # Serializar e publicar
    ctx = SerializationContext('plans.ready', MessageField.VALUE)
    value = serializer(plan_data, ctx)

    producer.produce(
        topic='plans.ready',
        key=b'test',
        value=value
    )
    producer.flush()

    # Consumir e verificar
    # (aguardar consumer processar)
    await asyncio.sleep(2)

    # Verificar que foi processado sem erros
    # (checkar logs, métricas, etc)
```

---

### 7.3. Checklist de Validação

- [ ] Schema carregado corretamente no consumer
- [ ] Path do schema correto no Dockerfile
- [ ] Deserialização de wire format Avro funciona
- [ ] Fallback JSON funciona para mensagens JSON
- [ ] Erro claro quando wire format é inválido
- [ ] Logs indicam qual formato foi usado (Avro ou JSON)
- [ ] Métricas de deserialização funcionam
- [ ] Teste end-to-end passa (producer → consumer)
- [ ] Performance aceitável (< 10ms para deserialização)
- [ ] Sem memory leaks (testar com carga)

---

## 8. IMPACTO EM OUTROS COMPONENTES

### 8.1. Semantic Translation Engine (Producer)
- ✅ NENHUMA MUDANÇA necessária
- Continua usando `confluent-kafka` com `AvroSerializer`
- Schema path precisa ser corrigido no Dockerfile

### 8.2. Gateway
- ✅ NENHUMA MUDANÇA necessária
- Padrão de referência está correto

### 8.3. Orchestrator
- ⚠️ Verificar se consome do tópico `decisions.consolidated`
- Se sim, aplicar mesma correção

### 8.4. Specialists
- ✅ NENHUMA MUDANÇA necessária
- Usam gRPC, não Kafka Avro

---

## 9. CRONOGRAMA PROPOSTO

### Sprint Atual (Semana 1)
- [ ] Implementar Opção 2 (fastavro workaround)
- [ ] Corrigir schema paths nos Dockerfiles
- [ ] Testes unitários
- [ ] Deploy em dev/staging

### Sprint Atual (Semana 2)
- [ ] Testes de integração
- [ ] Validação de performance
- [ ] Deploy em produção
- [ ] Monitoramento

### Próxima Sprint
- [ ] Planejamento da migração para confluent-kafka
- [ ] Refatoração do Consensus Engine
- [ ] Remoção do aiokafka
- [ ] Testes extensivos

---

## 10. REFERÊNCIAS

1. **Confluent Wire Format:**
   - https://docs.confluent.io/platform/current/schema-registry/fundamentals/serdes-develop/serdes-avro.html
   - Magic byte: 0x00
   - Schema ID: 4 bytes big-endian
   - Avro binary data

2. **aiokafka + confluent-kafka incompatibility:**
   - https://stackoverflow.com/questions/44407780/how-to-decode-deserialize-avro-with-python-from-kafka
   - Deserializer não pode ser coroutine
   - value_deserializer precisa ser síncrono

3. **fastavro:**
   - https://fastavro.readthedocs.io/
   - schemaless_reader para deserialização
   - parse_schema para schemas

4. **Código Neural Hive-Mind:**
   - Producer: `/services/semantic-translation-engine/src/producers/plan_producer.py`
   - Consumer: `/services/consensus-engine/src/consumers/plan_consumer.py`
   - Schema: `/schemas/cognitive-plan/cognitive-plan.avsc`

---

## CONCLUSÃO

O problema é uma **incompatibilidade arquitetural** entre:
1. `aiokafka` (async consumer)
2. `confluent_kafka.AvroDeserializer` (sync deserializer)
3. Confluent Wire Format (binary format com magic bytes)

A tentativa de usar `AvroDeserializer` como `value_deserializer` no `AIOKafkaConsumer` falha silenciosamente, caindo no fallback JSON que tenta fazer `.decode('utf-8')` em dados binários Avro, causando o erro `'utf-8' codec can't decode byte 0xe8`.

**Solução recomendada:** Implementar deserialização manual com `fastavro` (curto prazo) e migrar para `confluent-kafka` (longo prazo).
