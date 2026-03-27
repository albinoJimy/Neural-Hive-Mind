# DIAGRAMA: Fluxo de Serialização/Deserialização Avro

## 1. FLUXO ATUAL (COM PROBLEMA)

```
┌─────────────────────────────────────────────────────────────────────┐
│ SEMANTIC TRANSLATION ENGINE (Producer)                              │
│                                                                     │
│ ┌─────────────────┐                                                │
│ │ CognitivePlan   │                                                │
│ │  .to_avro_dict()│                                                │
│ └────────┬────────┘                                                │
│          │                                                          │
│          ▼                                                          │
│ ┌─────────────────────────────────────────────────────┐            │
│ │ AvroSerializer (confluent-kafka)                    │            │
│ │ - Consulta Schema Registry                         │            │
│ │ - Obtém schema ID                                  │            │
│ │ - Serializa em Avro binary                         │            │
│ └────────────────────┬────────────────────────────────┘            │
│                      │                                              │
│                      ▼                                              │
│ ┌─────────────────────────────────────────────────────┐            │
│ │ Wire Format: [0x00][ID][ID][ID][ID][AVRO_BINARY]   │            │
│ │              magic ─┘     └─ schema ID (4 bytes)    │            │
│ └────────────────────┬────────────────────────────────┘            │
│                      │                                              │
└──────────────────────┼──────────────────────────────────────────────┘
                       │
                       │ Kafka Topic: plans.ready
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│ CONSENSUS ENGINE (Consumer) - PROBLEMA AQUI!                         │
│                                                                      │
│ ┌────────────────────────────────────────────────────────────┐      │
│ │ AIOKafkaConsumer                                           │      │
│ │  - Recebe bytes: [0x00][ID][ID][ID][ID][AVRO_BINARY]      │      │
│ │  - value_deserializer=self._deserialize_message            │      │
│ └───────────────────────┬────────────────────────────────────┘      │
│                         │                                            │
│                         ▼                                            │
│ ┌────────────────────────────────────────────────────────────┐      │
│ │ _deserialize_message(message_bytes)                        │      │
│ │                                                            │      │
│ │ ┌──────────────────────────────────────────────────────┐  │      │
│ │ │ if self.avro_deserializer:                           │  │      │
│ │ │   try:                                               │  │      │
│ │ │     ctx = SerializationContext(topic, VALUE)         │  │      │
│ │ │     result = self.avro_deserializer(bytes, ctx)      │  │      │
│ │ │                          ▲                            │  │      │
│ │ │                          │                            │  │      │
│ │ │                          │ FALHA! Incompatível        │  │      │
│ │ │                          │ aiokafka + AvroDeserializer│  │      │
│ │ └──────────────────────────┼───────────────────────────┘  │      │
│ │                            │                               │      │
│ │   except Exception:        │                               │      │
│ │     # Fallback para JSON   │                               │      │
│ │     ▼                      │                               │      │
│ │ ┌──────────────────────────────────────────────────────┐  │      │
│ │ │ json.loads(message_bytes.decode('utf-8'))            │  │      │
│ │ │              ▲                                        │  │      │
│ │ │              │                                        │  │      │
│ │ │              │ ERRO! Byte 0xe8 não é UTF-8 válido!   │  │      │
│ │ │              │                                        │  │      │
│ │ │ Tentando decodificar:                                │  │      │
│ │ │ [0x00][0x00][0x00][0x00][0x01][...0xe8...]           │  │      │
│ │ │                                    ▲                  │  │      │
│ │ │                                    │                  │  │      │
│ │ │                 Byte 120 ─────────┘                  │  │      │
│ │ │                 (parte do Avro binary)               │  │      │
│ │ │                                                       │  │      │
│ │ │ 'utf-8' codec can't decode byte 0xe8 in position 120 │  │      │
│ │ └──────────────────────────────────────────────────────┘  │      │
│ └───────────────────────────────────────────────────────────┘      │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. POR QUE O AVRO DESERIALIZER FALHA?

```
┌────────────────────────────────────────────────────────────────┐
│ INCOMPATIBILIDADE ARQUITETURAL                                 │
│                                                                │
│ ┌──────────────────────────┐  ┌──────────────────────────┐    │
│ │ aiokafka                 │  │ confluent-kafka          │    │
│ │                          │  │                          │    │
│ │ - Biblioteca async       │  │ - Biblioteca sync        │    │
│ │ - AIOKafkaConsumer       │  │ - AvroDeserializer       │    │
│ │ - Espera callable sync   │  │ - Projetado para         │    │
│ │   para value_deserializer│  │   Consumer confluent     │    │
│ │                          │  │ - NÃO para callbacks     │    │
│ └────────────┬─────────────┘  └──────────┬───────────────┘    │
│              │                           │                     │
│              └───────────┬───────────────┘                     │
│                          │                                     │
│                          ▼                                     │
│              ┌───────────────────────┐                         │
│              │ INCOMPATÍVEL!         │                         │
│              │                       │                         │
│              │ AvroDeserializer      │                         │
│              │ falha silenciosamente │                         │
│              │ ao ser chamado como   │                         │
│              │ value_deserializer    │                         │
│              └───────────────────────┘                         │
└────────────────────────────────────────────────────────────────┘
```

---

## 3. ANATOMIA DO CONFLUENT WIRE FORMAT

```
┌─────────────────────────────────────────────────────────────────┐
│ BYTES DA MENSAGEM KAFKA                                         │
│                                                                 │
│ Byte 0     Bytes 1-4              Bytes 5+                     │
│ ┌───┐     ┌──────────────┐       ┌────────────────────────┐   │
│ │0x00│     │Schema ID     │       │ Avro Binary Data       │   │
│ │    │     │(big-endian)  │       │                        │   │
│ │    │     │              │       │ - Encoded fields       │   │
│ │    │     │ 0x00000001   │       │ - Variable length      │   │
│ │    │     │ (ID = 1)     │       │ - Can contain any byte │   │
│ │    │     │              │       │   including 0xe8       │   │
│ └─┬─┘     └──────┬───────┘       └────────┬───────────────┘   │
│   │              │                         │                   │
│   │              │                         │                   │
│   │              │                         │                   │
│ Magic          Schema                   Binary                │
│ Byte           ID                       Avro                  │
│                                         Data                  │
│ Identifica    Referência               Dados                 │
│ formato       ao schema no              serializados          │
│ Confluent     Schema Registry           em Avro               │
│                                                                │
└─────────────────────────────────────────────────────────────────┘

EXEMPLO CONCRETO:
┌───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┐
│00 │00 │00 │00 │01 │0E │74 │65 │73 │74 │2D │31 │32 │33 │... │e8 │
└─┬─┴─┴─┴─┴─┴─┴─┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴─┬─┘
  │   └─┴─┴─┴─┘                                                 │
  │       │                                                      │
Magic   Schema ID                                          Byte 120
Byte    (ID=1)                                             (0xe8)
                                                           ▲
                                                           │
                                    Este byte NÃO é UTF-8 válido!
                                    É parte do encoding Avro binário
```

---

## 4. FLUXO CORRETO (SOLUÇÃO PROPOSTA - FASTAVRO)

```
┌──────────────────────────────────────────────────────────────────────┐
│ CONSENSUS ENGINE (Consumer) - COM CORREÇÃO                           │
│                                                                      │
│ ┌────────────────────────────────────────────────────────────┐      │
│ │ AIOKafkaConsumer                                           │      │
│ │  - Recebe bytes: [0x00][ID][ID][ID][ID][AVRO_BINARY]      │      │
│ │  - value_deserializer=self._deserialize_message            │      │
│ └───────────────────────┬────────────────────────────────────┘      │
│                         │                                            │
│                         ▼                                            │
│ ┌────────────────────────────────────────────────────────────┐      │
│ │ _deserialize_message(message_bytes)                        │      │
│ │                                                            │      │
│ │ ┌──────────────────────────────────────────────────────┐  │      │
│ │ │ # Check magic byte                                   │  │      │
│ │ │ if message_bytes[0] == 0x00:                         │  │      │
│ │ │   # Confluent wire format detected!                  │  │      │
│ │ │                                                       │  │      │
│ │ │   # Extract schema ID                                │  │      │
│ │ │   schema_id = struct.unpack('>I', bytes[1:5])[0]     │  │      │
│ │ │                                                       │  │      │
│ │ │   # Get Avro data (skip 5 bytes)                     │  │      │
│ │ │   avro_bytes = message_bytes[5:]                     │  │      │
│ │ │                                                       │  │      │
│ │ │   # Deserialize with fastavro                        │  │      │
│ │ │   return schemaless_reader(                          │  │      │
│ │ │       io.BytesIO(avro_bytes),                        │  │      │
│ │ │       self.avro_schema_parsed                        │  │      │
│ │ │   )                                                   │  │      │
│ │ │   ▲                                                   │  │      │
│ │ │   │                                                   │  │      │
│ │ │   │ SUCESSO! fastavro lê Avro binário corretamente   │  │      │
│ │ │                                                       │  │      │
│ │ │ else:                                                 │  │      │
│ │ │   # JSON fallback                                    │  │      │
│ │ │   return json.loads(message_bytes.decode('utf-8'))   │  │      │
│ │ └──────────────────────────────────────────────────────┘  │      │
│ └───────────────────────────────────────────────────────────┘      │
│                         │                                            │
│                         ▼                                            │
│                  ┌──────────────┐                                   │
│                  │ Dict[str,Any]│                                   │
│                  │ (CognitivePlan)                                  │
│                  └──────────────┘                                   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 5. COMPARAÇÃO: BIBLIOTECAS KAFKA

```
┌──────────────────────────────────────────────────────────────────────┐
│ COMPONENTE              │ BIBLIOTECA         │ SERIALIZAÇÃO          │
├─────────────────────────┼────────────────────┼───────────────────────┤
│ Gateway                 │ confluent-kafka    │ AvroSerializer        │
│                         │ (sync)             │ + Schema Registry     │
│                         │                    │                       │
│ Semantic Translation    │ confluent-kafka    │ AvroSerializer        │
│ Engine                  │ (sync)             │ + Schema Registry     │
│                         │                    │                       │
│ Consensus Engine        │ aiokafka           │ AvroDeserializer      │
│ (ATUAL - PROBLEMA)      │ (async)            │ (INCOMPATÍVEL!)       │
│                         │ + confluent-kafka  │                       │
│                         │                    │                       │
│ Consensus Engine        │ aiokafka           │ fastavro              │
│ (SOLUÇÃO CURTO PRAZO)   │ (async)            │ + manual wire format  │
│                         │                    │                       │
│ Consensus Engine        │ confluent-kafka    │ AvroDeserializer      │
│ (SOLUÇÃO LONGO PRAZO)   │ (sync)             │ + Schema Registry     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 6. DECISION TREE: QUAL SOLUÇÃO USAR?

```
                    ┌───────────────────────────┐
                    │ Precisa corrigir AGORA?   │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                   SIM                         NÃO
                    │                           │
                    ▼                           ▼
        ┌───────────────────────┐   ┌───────────────────────┐
        │ OPÇÃO 2: fastavro     │   │ Planejar refatoração  │
        │                       │   │ completa (Opção 1)    │
        │ Prós:                 │   │                       │
        │ - Rápido              │   │ Prós:                 │
        │ - Menos invasivo      │   │ - Consistência total  │
        │ - Mantém async        │   │ - Melhor performance  │
        │                       │   │ - Padrão com resto    │
        │ Contras:              │   │                       │
        │ - Código adicional    │   │ Contras:              │
        │ - Manutenção extra    │   │ - Mais trabalho       │
        │                       │   │ - Muda arquitetura    │
        └───────────────────────┘   └───────────────────────┘
                    │                           │
                    │                           │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │ RECOMENDAÇÃO:             │
                    │                           │
                    │ 1. Implementar Opção 2    │
                    │    (fastavro) AGORA       │
                    │                           │
                    │ 2. Planejar Opção 1       │
                    │    (confluent-kafka)      │
                    │    para próxima sprint    │
                    └───────────────────────────┘
```

---

## 7. TIMELINE DE IMPLEMENTAÇÃO

```
SPRINT ATUAL (2 semanas)
├── SEMANA 1
│   ├── [ ] Implementar deserialização fastavro
│   ├── [ ] Corrigir schema paths nos Dockerfiles
│   ├── [ ] Testes unitários
│   └── [ ] Deploy em dev/staging
│
└── SEMANA 2
    ├── [ ] Testes de integração
    ├── [ ] Validação de performance
    ├── [ ] Deploy em produção
    └── [ ] Monitoramento

PRÓXIMA SPRINT (2 semanas)
├── SEMANA 1
│   ├── [ ] Refatorar para confluent-kafka
│   ├── [ ] Remover aiokafka
│   └── [ ] Testes extensivos
│
└── SEMANA 2
    ├── [ ] Deploy em produção
    ├── [ ] Validação final
    └── [ ] Documentação
```

---

## 8. PONTOS DE FALHA IDENTIFICADOS

```
┌────────────────────────────────────────────────────────────────┐
│ PONTO DE FALHA 1: Schema Path Inconsistente                   │
│                                                                │
│ Producer Dockerfile:                                           │
│   COPY schemas/cognitive-plan/cognitive-plan.avsc              │
│        /app/schemas/cognitive-plan.avsc                        │
│        ────────────────────────┬──────────────────             │
│                                │                               │
│ Producer Code:                 │                               │
│   schema_path = '/app/schemas/cognitive-plan.avsc'             │
│                 ───────────────┴──────────────────             │
│                 ✓ MATCH!                                       │
│                                                                │
│ Consumer Dockerfile:                                           │
│   COPY schemas /app/schemas                                    │
│        ────────────────┬───────                                │
│                        │                                       │
│ Consumer Code:         │                                       │
│   schema_path = '/app/schemas/cognitive-plan/cognitive-plan.avsc'
│                 ───────┴──────────────────────────────         │
│                 ✓ MATCH!                                       │
│                                                                │
│ PROBLEMA: Diferentes estruturas de diretório                  │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│ PONTO DE FALHA 2: Incompatibilidade de Bibliotecas            │
│                                                                │
│ Producer: confluent-kafka (sync)                               │
│           └─> AvroSerializer                                   │
│                └─> Wire Format: [0x00][ID][AVRO]               │
│                                                                │
│ Consumer: aiokafka (async) + confluent-kafka (sync)            │
│           └─> value_deserializer expects sync callable         │
│                └─> AvroDeserializer expects confluent Consumer │
│                     └─> INCOMPATÍVEL!                          │
│                                                                │
│ Resultado: Falha silenciosa → fallback JSON → UTF-8 error     │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│ PONTO DE FALHA 3: Fallback JSON Inadequado                    │
│                                                                │
│ Quando AvroDeserializer falha:                                 │
│   → tenta json.loads(bytes.decode('utf-8'))                    │
│   → mas bytes = [0x00][ID][AVRO_BINARY]                        │
│   → AVRO_BINARY contém bytes não-UTF-8                         │
│   → erro: can't decode byte 0xe8                               │
│                                                                │
│ Solução:                                                       │
│   → verificar magic byte ANTES de tentar JSON                  │
│   → se 0x00: é Avro, não tenta JSON                           │
│   → se não 0x00: pode ser JSON                                │
└────────────────────────────────────────────────────────────────┘
```

---

## RESUMO EXECUTIVO

**PROBLEMA:** Incompatibilidade entre `aiokafka` + `AvroDeserializer` (confluent-kafka)

**SINTOMA:** `'utf-8' codec can't decode byte 0xe8 in position 120: invalid continuation byte`

**CAUSA RAIZ:**
1. `AvroDeserializer` não funciona como `value_deserializer` em `AIOKafkaConsumer`
2. Fallback JSON tenta decodificar Avro binary wire format como UTF-8
3. Byte 0xe8 é válido em Avro binary mas inválido em UTF-8

**SOLUÇÃO IMEDIATA:** Implementar deserialização manual com `fastavro`

**SOLUÇÃO DEFINITIVA:** Migrar Consensus Engine para `confluent-kafka` (como resto da arquitetura)
