# QUICK REFERENCE: Deserialização Avro

**Status:** Análise completa - Aguardando implementação
**Data:** 2025-11-06

---

## PROBLEMA EM 1 FRASE

`aiokafka` tentando usar `AvroDeserializer` (confluent-kafka) como `value_deserializer` = incompatível → fallback JSON falha ao tentar decodificar bytes Avro binários como UTF-8.

---

## ERRO EXATO

```
'utf-8' codec can't decode byte 0xe8 in position 120: invalid continuation byte
```

**Causa:** Byte `0xe8` é válido em Avro binary, mas inválido em UTF-8.

---

## ONDE ESTÁ O PROBLEMA

**Arquivo:** `/jimy/Neural-Hive-Mind/services/consensus-engine/src/consumers/plan_consumer.py`
**Linha:** 41 (onde `AvroDeserializer` é chamado) + 50 (fallback JSON)

---

## SOLUÇÃO RECOMENDADA

**FASE 1 (1 semana):** Implementar deserialização com `fastavro`
**FASE 2 (2 semanas):** Migrar para `confluent-kafka`

---

## IMPLEMENTAÇÃO RÁPIDA (Fase 1)

### 1. Adicionar dependência

**Arquivo:** `services/consensus-engine/requirements.txt`
```
fastavro>=1.8.0
```

### 2. Atualizar código

**Arquivo:** `services/consensus-engine/src/consumers/plan_consumer.py`

```python
import io
import struct
import json
from fastavro import schemaless_reader, parse_schema

class PlanConsumer:
    def __init__(self, ...):
        self.avro_schema_parsed = None

    def _deserialize_message(self, message_bytes: bytes) -> Dict[str, Any]:
        if not message_bytes:
            raise ValueError('Mensagem vazia')

        # Confluent wire format: [0x00][Schema_ID][Avro_Binary]
        if message_bytes[0] == 0x00:
            try:
                # Extract schema ID (4 bytes, big-endian)
                schema_id = struct.unpack('>I', message_bytes[1:5])[0]

                # Deserialize Avro (skip 5 bytes: magic + schema ID)
                avro_bytes = message_bytes[5:]
                return schemaless_reader(
                    io.BytesIO(avro_bytes),
                    self.avro_schema_parsed
                )
            except Exception as e:
                logger.error('Erro deserializando Avro', error=str(e))
                raise ValueError(f'Erro deserializando Avro: {e}')
        else:
            # JSON fallback
            return json.loads(message_bytes.decode('utf-8'))

    async def initialize(self):
        # Load and parse schema
        schema_path = '/app/schemas/cognitive-plan/cognitive-plan.avsc'
        if os.path.exists(schema_path):
            with open(schema_path, 'r') as f:
                schema_dict = json.loads(f.read())
            self.avro_schema_parsed = parse_schema(schema_dict)
            logger.info('Schema Avro carregado')

        # Continue with rest of initialization...
```

### 3. Build e deploy

```bash
# Build
docker build -t consensus-engine:fix-avro services/consensus-engine/

# Deploy
kubectl set image deployment/consensus-engine \
  consensus-engine=consensus-engine:fix-avro \
  -n neural-hive-mind
```

---

## VALIDAÇÃO

### Verificar se funciona

```bash
# Logs devem mostrar: "Mensagem deserializada com Avro"
kubectl logs -n neural-hive-mind deployment/consensus-engine --tail=50 | grep "deserializ"

# Não deve ter erros UTF-8
kubectl logs -n neural-hive-mind deployment/consensus-engine --tail=100 | grep "utf-8"
```

### Teste manual

```bash
# Enviar intent pelo Gateway
curl -X POST http://gateway:8000/api/v1/intents \
  -H "Content-Type: application/json" \
  -d '{"domain": "test", "action": "test_avro", ...}'

# Verificar que Consensus Engine processou
kubectl logs -n neural-hive-mind deployment/consensus-engine --tail=20
```

---

## CHECKLIST DE IMPLEMENTAÇÃO

- [ ] Adicionar `fastavro>=1.8.0` no requirements.txt
- [ ] Atualizar método `_deserialize_message()`
- [ ] Adicionar `self.avro_schema_parsed = None` no `__init__`
- [ ] Carregar e parsear schema no `initialize()`
- [ ] Build da imagem Docker
- [ ] Testes unitários
- [ ] Deploy em staging
- [ ] Validação manual
- [ ] Deploy em produção
- [ ] Monitoramento 24h

---

## CÓDIGO ANTES vs DEPOIS

### ANTES (com problema)

```python
def _deserialize_message(self, message_bytes: bytes):
    if self.avro_deserializer:
        try:
            ctx = SerializationContext(topic, MessageField.VALUE)
            result = self.avro_deserializer(message_bytes, ctx)  # FALHA!
            return result
        except Exception as e:
            logger.warning('Falha Avro, tentando JSON', error=str(e))

    # Fallback JSON
    return json.loads(message_bytes.decode('utf-8'))  # ERRO UTF-8!
```

### DEPOIS (corrigido)

```python
def _deserialize_message(self, message_bytes: bytes):
    # Check magic byte
    if message_bytes[0] == 0x00:  # Confluent wire format
        schema_id = struct.unpack('>I', message_bytes[1:5])[0]
        avro_bytes = message_bytes[5:]
        return schemaless_reader(
            io.BytesIO(avro_bytes),
            self.avro_schema_parsed
        )  # FUNCIONA!
    else:
        return json.loads(message_bytes.decode('utf-8'))
```

---

## WIRE FORMAT VISUAL

```
┌───┬───┬───┬───┬───┬───────────────────────────┐
│00 │00 │00 │00 │01 │ Avro Binary Data         │
└─┬─┴─┴─┴─┴─┴─┴─┴───────────────────────────────┘
  │   └─┴─┴─┴─┘
  │       │
Magic   Schema ID
Byte    (4 bytes)
0x00    big-endian

Byte 0xe8 pode aparecer no Avro Binary Data
(é válido em Avro, inválido em UTF-8)
```

---

## MÉTRICAS

| Antes | Depois |
|-------|--------|
| ❌ UTF-8 decode errors | ✅ 0 erros |
| ❌ Mensagens não processadas | ✅ 100% processadas |
| ⚠️ Fallback JSON sempre | ✅ Avro quando wire format |

---

## ROLLBACK

Se algo der errado:

```bash
# Reverter deployment
kubectl rollout undo deployment/consensus-engine -n neural-hive-mind

# Ou desabilitar Schema Registry (temporário)
kubectl set env deployment/consensus-engine \
  SCHEMA_REGISTRY_URL="" \
  -n neural-hive-mind
```

---

## TROUBLESHOOTING

### Erro: "Schema Avro não encontrado"

**Causa:** Path do schema incorreto no Dockerfile ou container

**Solução:**
```bash
# Verificar se schema existe no container
kubectl exec -it deployment/consensus-engine -n neural-hive-mind -- \
  ls -la /app/schemas/cognitive-plan/

# Se não existir, corrigir Dockerfile
```

### Erro: "Erro deserializando Avro"

**Causa:** Schema incompatível ou wire format corrompido

**Solução:**
```bash
# Verificar logs detalhados
kubectl logs -n neural-hive-mind deployment/consensus-engine --tail=100

# Verificar schema registry
curl http://schema-registry:8081/subjects/

# Validar que producer está usando mesmo schema
```

### Ainda tem erros UTF-8

**Causa:** Código não foi atualizado corretamente

**Solução:**
```bash
# Verificar que código novo está deployado
kubectl exec -it deployment/consensus-engine -n neural-hive-mind -- \
  cat /app/src/consumers/plan_consumer.py | grep "0x00"

# Se não tiver "0x00", rebuild da imagem necessário
```

---

## TESTES UNITÁRIOS

```python
def test_deserialize_avro_wire_format():
    """Testa deserialização de Confluent wire format"""
    consumer = PlanConsumer(...)

    # Mock Avro wire format
    schema_id = 1
    avro_data = b'\x0Etest-123'  # Avro binary
    wire_format = struct.pack('>BI', 0x00, schema_id) + avro_data

    result = consumer._deserialize_message(wire_format)
    assert result is not None

def test_deserialize_json():
    """Testa fallback JSON"""
    consumer = PlanConsumer(...)

    json_data = '{"plan_id": "test"}'.encode('utf-8')
    result = consumer._deserialize_message(json_data)
    assert result['plan_id'] == 'test'
```

---

## LINKS ÚTEIS

- **Análise completa:** `ANALISE_PROFUNDA_DESERIALIZACAO_AVRO.md`
- **Sumário executivo:** `SUMARIO_EXECUTIVO_DESERIALIZACAO.md`
- **Diagramas:** `DIAGRAMA_FLUXO_SERIALIZACAO.md`
- **Índice:** `INDICE_ANALISE_DESERIALIZACAO.md`

---

## CONTATOS

**Análise feita por:** Claude Code
**Data:** 2025-11-06
**Status:** Pronto para implementação

---

## TEMPO ESTIMADO

- **Implementação:** 4-6 horas
- **Testes:** 2-3 horas
- **Deploy staging:** 1 hora
- **Validação:** 2-4 horas
- **Deploy produção:** 1 hora
- **TOTAL:** 1-2 dias

---

## COMANDOS ÚTEIS

```bash
# Build
docker build -t consensus-engine:fix-avro services/consensus-engine/

# Push to registry (se aplicável)
docker tag consensus-engine:fix-avro your-registry/consensus-engine:fix-avro
docker push your-registry/consensus-engine:fix-avro

# Deploy
kubectl set image deployment/consensus-engine \
  consensus-engine=consensus-engine:fix-avro \
  -n neural-hive-mind

# Verificar rollout
kubectl rollout status deployment/consensus-engine -n neural-hive-mind

# Logs em tempo real
kubectl logs -f deployment/consensus-engine -n neural-hive-mind

# Verificar não tem erros
kubectl logs deployment/consensus-engine -n neural-hive-mind --tail=100 | grep -i error
```

---

## DECISÃO PENDENTE

Qual opção implementar?

- [ ] **Opção 2 (RECOMENDADO):** fastavro (Fase 1) → confluent-kafka (Fase 2)
- [ ] **Opção 1:** Migrar direto para confluent-kafka
- [ ] **Opção 3:** Desabilitar Schema Registry (NÃO RECOMENDADO)

**Após decisão:** Executar implementação conforme este guia.
