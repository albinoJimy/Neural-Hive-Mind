# Análise de Schema Mismatch - Causa Raiz Identificada

**Data:** 2025-12-04 11:00 UTC
**Analista:** Claude Code
**Status:** CAUSA RAIZ IDENTIFICADA E CORRIGIDA

---

## Problema Reportado

O teste E2E estava falhando com a mensagem:
```
Pareceres insuficientes: 0/5
```

Logs do Consensus Engine mostravam:
```
RetryError[<Future at 0x... state=finished raised TypeError>]
```

Erro de validação no specialist indicava campos ausentes:
```
{'type': 'missing', 'loc': ('original_domain',), 'msg': 'Field required'}
{'type': 'missing', 'loc': ('original_priority',), 'msg': 'Field required'}
```

---

## Investigação Realizada

### 1. Verificação do Schema Avro
**Arquivo:** `schemas/cognitive-plan/cognitive-plan.avsc`

Os campos `original_domain` e `original_priority` estão presentes (linhas 130-137):
```json
{
  "name": "original_domain",
  "type": "string",
  "doc": "Domínio da intenção original"
},
{
  "name": "original_priority",
  "type": "string",
  "doc": "Prioridade original"
}
```

**Resultado:** ✅ Schema correto

### 2. Verificação do Modelo Python do STE
**Arquivo:** `services/semantic-translation-engine/src/models/cognitive_plan.py`

Campos presentes como obrigatórios (linhas 119-120):
```python
original_domain: str = Field(..., description='Original intent domain')
original_priority: str = Field(..., description='Original priority')
```

**Resultado:** ✅ Modelo correto

### 3. Verificação do Orchestrator do STE
**Arquivo:** `services/semantic-translation-engine/src/services/orchestrator.py`

Campos corretamente populados (linhas 297-298):
```python
original_domain=intent.get('domain', 'unknown'),
original_priority=constraints.get('priority', 'normal'),
```

**Resultado:** ✅ Campos populados corretamente

### 4. Leitura Direta da Mensagem Kafka

Executado script de debug que lê diretamente o offset 10 do tópico `plans.ready`:

```python
# Resultado da leitura Avro
plan_id: 2e101ecb-d90a-466b-b372-1fd8701c5450
original_domain: TECHNICAL
original_priority: normal
tasks count: 1
```

**Resultado:** ✅ Dados presentes na mensagem Kafka

---

## Causa Raiz Identificada

**O problema NÃO é schema mismatch!**

### Erro Real
```
TypeError: Object of type datetime is not JSON serializable
```

### Explicação

1. O **STE** publica o plano cognitivo no Kafka usando formato **Avro**
2. O schema Avro define campos `created_at` e `valid_until` como `timestamp-millis`
3. O **Consensus Engine** usa `AvroDeserializer` do `confluent-kafka` para ler as mensagens
4. O deserializer converte `timestamp-millis` para objetos Python `datetime`
5. Quando o CE tenta enviar o plano para os specialists via gRPC, ele serializa com:
   ```python
   plan_bytes = json.dumps(cognitive_plan).encode('utf-8')
   ```
6. O `json.dumps()` **falha** porque `datetime` não é serializável por padrão
7. O erro é capturado pelo retry (`tenacity.AsyncRetrying`) e propagado como `RetryError[TypeError]`

### Arquivo Afetado
`services/consensus-engine/src/clients/specialists_grpc_client.py:76`

---

## Correção Aplicada

### Diff da Correção

```diff
 import grpc
 import asyncio
 import json
+from datetime import datetime
 from typing import List, Dict, Any, Optional
 from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential, RetryError
 import structlog
 from google.protobuf.timestamp_pb2 import Timestamp


+def _json_datetime_serializer(obj):
+    """
+    Custom JSON serializer for objects not serializable by default json code.
+
+    Handles datetime objects returned by Avro deserializer for timestamp-millis fields.
+    """
+    if isinstance(obj, datetime):
+        return obj.isoformat()
+    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')
+

 # Na linha 76:
-                plan_bytes = json.dumps(cognitive_plan).encode('utf-8')
+                plan_bytes = json.dumps(
+                    cognitive_plan,
+                    default=_json_datetime_serializer
+                ).encode('utf-8')
```

---

## Próximos Passos

1. [x] Aplicar correção no código
2. [ ] Build da imagem `consensus-engine:1.0.9`
3. [ ] Exportar imagem para workers
4. [ ] Deploy via Helm com nova tag
5. [ ] Retest E2E

---

## Lições Aprendidas

1. **Logs podem ser enganosos**: O log inicial indicava `TypeError` mas o stack trace completo não estava visível
2. **A deserialização Avro pode alterar tipos**: `timestamp-millis` → `datetime` é uma conversão automática do `confluent-kafka`
3. **JSON serialization precisa de cuidado**: Sempre usar `default=` quando há tipos não-primitivos

---

*Relatório gerado em 2025-12-04 11:00 UTC*
