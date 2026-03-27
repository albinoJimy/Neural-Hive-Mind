# SUMÁRIO EXECUTIVO: Problema de Deserialização Avro

**Data:** 2025-11-06
**Severidade:** ALTA
**Status:** CAUSA RAIZ IDENTIFICADA - AGUARDANDO DECISÃO

---

## TL;DR

O Consensus Engine está usando **duas bibliotecas Kafka incompatíveis** (`aiokafka` + `confluent-kafka`), causando falha na deserialização de mensagens Avro. A tentativa de fallback para JSON falha porque tenta decodificar bytes binários Avro como UTF-8.

---

## O QUE ESTÁ ACONTECENDO

```
Producer (Semantic Engine)
  └─> Serializa com AvroSerializer (confluent-kafka)
      └─> Wire Format: [0x00][Schema_ID][Avro_Binary]
          └─> Publica no Kafka

Consumer (Consensus Engine)
  └─> Consome com AIOKafkaConsumer (aiokafka)
      └─> Tenta deserializar com AvroDeserializer (confluent-kafka)
          └─> FALHA (incompatibilidade arquitetural)
              └─> Fallback: json.loads(bytes.decode('utf-8'))
                  └─> ERRO: byte 0xe8 não é UTF-8 válido
```

**Byte 0xe8** é parte do encoding Avro binário, perfeitamente válido em Avro, mas inválido em UTF-8.

---

## POR QUE ESTÁ FALHANDO

### Problema 1: Incompatibilidade de Bibliotecas

| Componente | Biblioteca | Tipo | Compatível? |
|------------|-----------|------|-------------|
| Producer (Semantic Engine) | `confluent-kafka` | Sync | ✅ |
| Producer (Gateway) | `confluent-kafka` | Sync | ✅ |
| Consumer (Consensus) | `aiokafka` + `confluent-kafka` | Async + Sync | ❌ |

**Problema:** `AvroDeserializer` (confluent-kafka) não foi projetado para funcionar como `value_deserializer` em `AIOKafkaConsumer` (aiokafka).

### Problema 2: Fallback JSON Inadequado

Quando `AvroDeserializer` falha silenciosamente, o código tenta:
```python
json.loads(message_bytes.decode('utf-8'))
```

Mas `message_bytes` contém:
```
[0x00][0x00][0x00][0x00][0x01][...avro binary...][0xe8][...]
```

Tentar decodificar isso como UTF-8 = ERRO.

---

## OPÇÕES DE SOLUÇÃO

### OPÇÃO 1: Migrar para confluent-kafka (DEFINITIVA)

**Esforço:** ALTO (2 semanas)
**Benefício:** ALTO (alinhamento arquitetural)

```diff
- aiokafka>=0.8.1
+ confluent-kafka==2.3.0
```

**Prós:**
- ✅ Consistência com toda arquitetura Neural Hive-Mind
- ✅ Suporte nativo a Schema Registry
- ✅ Melhor performance (librdkafka em C)
- ✅ Transações Kafka nativas
- ✅ Solução permanente

**Contras:**
- ⚠️ Refatoração significativa (async → sync)
- ⚠️ Mudança no padrão do código
- ⚠️ Requer testes extensivos

**Recomendado para:** Próxima sprint

---

### OPÇÃO 2: Usar fastavro (WORKAROUND)

**Esforço:** MÉDIO (1 semana)
**Benefício:** MÉDIO (resolve problema, mantém async)

```diff
+ fastavro>=1.8.0
```

```python
import io
import struct
from fastavro import schemaless_reader

def _deserialize_message(self, message_bytes: bytes) -> Dict[str, Any]:
    if message_bytes[0] == 0x00:  # Confluent wire format
        schema_id = struct.unpack('>I', message_bytes[1:5])[0]
        avro_bytes = message_bytes[5:]
        return schemaless_reader(io.BytesIO(avro_bytes), self.avro_schema_parsed)
    else:
        return json.loads(message_bytes.decode('utf-8'))
```

**Prós:**
- ✅ Solução rápida (implementação em 1 dia)
- ✅ Mantém aiokafka (async)
- ✅ Funciona com Confluent Wire Format
- ✅ Menos invasivo

**Contras:**
- ⚠️ Código adicional para manter
- ⚠️ Não usa Schema Registry diretamente
- ⚠️ Não é a solução "ideal"

**Recomendado para:** Sprint atual (solução temporária)

---

### OPÇÃO 3: Desabilitar Schema Registry (GAMBIARRA)

**Esforço:** BAIXO (1 hora)
**Benefício:** BAIXO (apenas temporário)

```bash
# Desabilitar Schema Registry
SCHEMA_REGISTRY_URL=""

# Forçar producer a usar JSON
self.avro_serializer = None
```

**Prós:**
- ✅ Funciona imediatamente
- ✅ Zero mudanças de código

**Contras:**
- ❌ Perde validação de schema
- ❌ Perde versionamento
- ❌ JSON menos eficiente que Avro
- ❌ Não é solução real

**Recomendado para:** NUNCA (apenas emergência)

---

## RECOMENDAÇÃO

### ESTRATÉGIA EM 2 FASES

```
FASE 1 (SPRINT ATUAL - 1 semana)
├─ Implementar OPÇÃO 2 (fastavro)
├─ Corrigir schema paths nos Dockerfiles
├─ Testes unitários e integração
└─ Deploy em produção

FASE 2 (PRÓXIMA SPRINT - 2 semanas)
├─ Implementar OPÇÃO 1 (confluent-kafka)
├─ Refatorar Consensus Engine
├─ Testes extensivos
└─ Deploy em produção
```

**Justificativa:**
- Fase 1 resolve o problema AGORA sem grandes mudanças
- Fase 2 alinha a arquitetura permanentemente
- Risco minimizado com validação em cada fase

---

## IMPACTO NOS COMPONENTES

| Componente | Impacto | Ação Necessária |
|------------|---------|-----------------|
| Semantic Translation Engine | ✅ Nenhum | Apenas corrigir Dockerfile (schema path) |
| Consensus Engine | 🔴 Alto | Implementar nova deserialização |
| Gateway | ✅ Nenhum | Nenhuma |
| Orchestrator | ⚠️ Verificar | Se consome Kafka Avro, aplicar mesma correção |
| Specialists | ✅ Nenhum | Usam gRPC |

---

## CORREÇÕES NECESSÁRIAS (OPÇÃO 2)

### 1. Adicionar fastavro

**Arquivo:** `services/consensus-engine/requirements.txt`
```diff
+ fastavro>=1.8.0
```

### 2. Atualizar deserialização

**Arquivo:** `services/consensus-engine/src/consumers/plan_consumer.py`

```python
import io
import struct
import json
from typing import Dict, Any, Optional
from fastavro import schemaless_reader, parse_schema

class PlanConsumer:
    def __init__(self, ...):
        self.avro_schema_parsed = None

    def _deserialize_message(self, message_bytes: bytes) -> Dict[str, Any]:
        if not message_bytes:
            raise ValueError('Mensagem vazia')

        # Check for Confluent wire format (magic byte 0x00)
        if message_bytes[0] == 0x00:
            try:
                # Extract schema ID
                schema_id = struct.unpack('>I', message_bytes[1:5])[0]

                # Deserialize Avro (skip 5 bytes)
                avro_bytes = message_bytes[5:]
                result = schemaless_reader(
                    io.BytesIO(avro_bytes),
                    self.avro_schema_parsed
                )
                logger.debug('Mensagem deserializada com Avro')
                return result
            except Exception as e:
                logger.error('Erro deserializando Avro', error=str(e))
                raise ValueError(f'Erro deserializando Avro: {e}')
        else:
            # JSON fallback
            try:
                return json.loads(message_bytes.decode('utf-8'))
            except Exception as e:
                logger.error('Erro deserializando JSON', error=str(e))
                raise ValueError(f'Erro deserializando JSON: {e}')

    async def initialize(self):
        schema_path = '/app/schemas/cognitive-plan/cognitive-plan.avsc'

        if os.path.exists(schema_path):
            with open(schema_path, 'r') as f:
                schema_dict = json.loads(f.read())

            self.avro_schema_parsed = parse_schema(schema_dict)
            logger.info('Schema Avro carregado', path=schema_path)
        else:
            logger.warning('Schema Avro não encontrado', path=schema_path)

        # Rest of initialization...
```

### 3. Corrigir Dockerfile (se necessário)

**Arquivo:** `services/consensus-engine/Dockerfile`
```dockerfile
# Garantir que schemas estão no lugar certo
COPY --chown=consensus:consensus schemas/cognitive-plan/cognitive-plan.avsc \
     /app/schemas/cognitive-plan/cognitive-plan.avsc
```

---

## TESTES NECESSÁRIOS

### Testes Unitários
```python
def test_deserialize_confluent_wire_format():
    """Testa deserialização de Confluent wire format"""
    # Mock de mensagem Avro com wire format
    # Verificar que deserializa corretamente

def test_deserialize_json_fallback():
    """Testa fallback para JSON"""
    # Mock de mensagem JSON pura
    # Verificar que deserializa corretamente

def test_deserialize_invalid_format():
    """Testa erro em formato inválido"""
    # Mock de mensagem inválida
    # Verificar que lança exceção apropriada
```

### Testes de Integração
```python
async def test_end_to_end_avro_serialization():
    """Testa producer → Kafka → consumer"""
    # Producer serializa com AvroSerializer
    # Consumer deserializa com fastavro
    # Verificar que dados batem
```

---

## CHECKLIST DE VALIDAÇÃO

- [ ] fastavro instalado no requirements.txt
- [ ] Código de deserialização atualizado
- [ ] Schema carregado e parseado na inicialização
- [ ] Testes unitários passando
- [ ] Testes de integração passando
- [ ] Dockerfile correto (schema path)
- [ ] Deploy em dev/staging funcionando
- [ ] Logs indicam formato usado (Avro ou JSON)
- [ ] Métricas de deserialização ok
- [ ] Performance aceitável (< 10ms)
- [ ] Deploy em produção
- [ ] Monitoramento 24h sem erros

---

## CRONOGRAMA ESTIMADO

### Sprint Atual (Opção 2 - fastavro)
```
DIA 1-2: Implementação
  - Adicionar fastavro
  - Atualizar deserialização
  - Testes unitários

DIA 3-4: Validação
  - Testes de integração
  - Build e deploy em staging
  - Testes manuais

DIA 5: Deploy produção
  - Deploy gradual
  - Monitoramento intensivo
  - Rollback plan preparado
```

### Próxima Sprint (Opção 1 - confluent-kafka)
```
SEMANA 1: Refatoração
  - Migrar para confluent-kafka
  - Converter async → sync
  - Testes unitários

SEMANA 2: Validação e Deploy
  - Testes de integração
  - Performance testing
  - Deploy produção
```

---

## RISCOS E MITIGAÇÕES

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Deserialização falha em alguns casos | MÉDIA | ALTO | Testes extensivos com dados reais |
| Performance degradada | BAIXA | MÉDIO | Benchmark antes/depois |
| Bugs em produção | BAIXA | ALTO | Deploy gradual, rollback preparado |
| Refatoração (Fase 2) complexa | MÉDIA | MÉDIO | POC antes, testes extensivos |

---

## DECISÃO NECESSÁRIA

**QUESTÃO:** Qual opção implementar?

- [ ] **OPÇÃO 1:** Migrar direto para confluent-kafka (2 semanas)
- [ ] **OPÇÃO 2:** fastavro agora + confluent-kafka depois (1 semana + 2 semanas)
- [ ] **OPÇÃO 3:** Desabilitar Schema Registry (1 hora - não recomendado)

**RECOMENDAÇÃO:** ✅ OPÇÃO 2 (fastavro em 2 fases)

---

## PRÓXIMOS PASSOS (SE OPÇÃO 2 APROVADA)

1. ✅ **VOCÊ ESTÁ AQUI** - Análise completa realizada
2. ⏭️ Criar branch `fix/consensus-avro-deserialization`
3. ⏭️ Implementar código (1-2 dias)
4. ⏭️ Testes unitários (1 dia)
5. ⏭️ Testes de integração (1 dia)
6. ⏭️ Deploy staging (1 dia)
7. ⏭️ Deploy produção (1 dia)
8. ⏭️ Monitoramento (contínuo)

---

## ARQUIVOS DE REFERÊNCIA

- **Análise completa:** `/jimy/Neural-Hive-Mind/ANALISE_PROFUNDA_DESERIALIZACAO_AVRO.md`
- **Diagrama de fluxo:** `/jimy/Neural-Hive-Mind/DIAGRAMA_FLUXO_SERIALIZACAO.md`
- **Este sumário:** `/jimy/Neural-Hive-Mind/SUMARIO_EXECUTIVO_DESERIALIZACAO.md`

---

## CONCLUSÃO

Problema bem definido, causa raiz identificada, soluções propostas com prós/contras claros.

**Aguardando decisão para prosseguir com implementação.**
