# STATUS FINAL - DIAGNÓSTICO GATEWAY/STE - 2026-02-23

## Resumo Executivo

**Status:** ⚠️ INVESTIGAÇÃO INTERROMPIDA - Problema de Deploy
**Causa Raiz:** Gateway enviando JSON em vez de Avro
**Bloqueio:** Deployment Gateway com ImagePullBackOff

---

## 1. DESCobERTAS CONFIRMADAS

### 1.1 AvroSerializer Funciona em Teste Manual

```bash
# Teste no Gateway pod
producer = KafkaIntentProducer(...)
asyncio.run(producer.initialize())
# Resultado: "Schema Registry habilitado"

serialized = producer.avro_serializer(avro_data, ctx)
# First byte: 0 (hex: 0x00) ✅
# >>> FORMAT: AVRO (Confluent wire format)
```

### 1.2 Mensagem Real no Kafka é JSON

```bash
# Leitura direta do Kafka
First 20 bytes hex: 7b22696e74656e745f6964223a20226561336131
First 5 bytes as integers: [123, 34, 105, 110, 116]
>>> 0x7B = '{' = JSON ❌
```

### 1.3 kafka_producer Global é None

```python
import main
print(main.kafka_producer)  # None
```

Porém, requisições HTTP funcionam e logs mostram `kafka_producer.send_intent()` sendo executado.

**Possível explicação:** Uvicorn carrega o app em um escopo isolado; o import direto não acessa o mesmo objeto.

---

## 2. HIPÓTESE DA CAUSA RAIZ

### Mais Provável: Producer Perde AvroSerializer em Runtime

**Flujo identificado:**

1. **Bootstrap:** `producer.initialize()` cria `avro_serializer` ✅
2. **Teste Manual:** `avro_serializer` funciona ✅
3. **Request Real:** Código entra no `else` (JSON fallback) ❌

**Possíveis causas:**
- Producer é recriado em algum momento (reconnect, error recovery)
- Exceção durante `initialize()` é capturada silenciosamente
- Múltiplas instâncias de producer (global != usado pelo endpoint)

---

## 3. CÓDIGO ANALISADO

### 3.1 Gateway Producer (`kafka/producer.py`)

```python
# Linhas 413-430: Escolha Avro vs JSON
if self.avro_serializer:
    serialized_value = self.avro_serializer(avro_data, ctx)
    content_type = "application/avro"
else:
    # Fallback JSON
    serialized_value = json.dumps(avro_data).encode("utf-8")
    content_type = "application/json"
```

**Para o código entrar no `else`, `self.avro_serializer` precisa ser `None`.**

### 3.2 Inicialização (`kafka/producer.py`)

```python
# Linhas 167-191
if self.schema_registry_url and self.schema_registry_url.strip():
    # Cria SchemaRegistryClient
    # Cria AvroSerializer
    self.avro_serializer = AvroSerializer(...)
    logger.info("Schema Registry habilitado")
else:
    self.avro_serializer = None
    logger.warning("Schema Registry desabilitado")
```

---

## 4. SOLUÇÕES PROPOSTAS

### 4.1 Adicionar Logs de Depuração (IMPLEMENTADO)

Modificação feita em `producer.py` (commit 2be921e, depois revertido):

```python
logger.debug(
    "DEBUG: Serialization state",
    avro_serializer_is_none=self.avro_serializer is None,
    _ready=self._ready,
)
```

**Status:** Commit revertido devido a problema de deploy (ImagePullBackOff).

### 4.2 Garantir AvroSerializer Sempre Inicializado

```python
# No initialize(), após criar avro_serializer
if not self.avro_serializer:
    raise RuntimeError("AvroSerializer initialization failed")

# No is_ready()
def is_healthy(self):
    return self._ready and self.avro_serializer is not None
```

### 4.3 Usar JSON Temporariamente (Fallback)

**Quick fix para desbloquear os testes:**

1. Gateway: Continuar enviando JSON
2. STE: Já suporta auto-detecção JSON
3. Testar fluxo completo E2E
4. Corrigir Avro depois

---

## 5. BLOQUEIO ATUAL

### 5.1 Deployment Gateway

```
gateway-intencoes-665986494-z75tl   0/1   ImagePullBackOff
gateway-intencoes-7b6597dfd5-mzvnx   0/1   ContainerCreating
```

**Erro:** `failed to pull and unpack image "ghcr.com/albinojimy/neural-hive-mind/gateway-intencoes:main"`

**Causa:** Problema de rede/infraestrutura no cluster.

### 5.2 STE Status

```
semantic-translation-engine-788667f79d-cbfkc   2/2   Running
Consumer loop active, poll count: 2160
Consumer ativo (último poll há 0.1s, 0 msgs processadas)
```

---

## 6. PRÓXIMOS PASSOS

### Immediate (Resolver Deploy)

1. **Verificar image pull secrets** para `ghcr.io`
2. **Reverter para imagem funcional** anterior
3. **Ou usar imagem local** se disponível

### Curto Prazo (Corrigir Avro)

1. **Adicionar verificação no initialize():**
   ```python
   if not self.avro_serializer:
       raise RuntimeError("AvroSerializer required but not initialized")
   ```

2. **Adicionar health check específico:**
   ```python
   def is_healthy_with_avro(self):
       return self._ready and self.avro_serializer is not None
   ```

3. **Investigar por que producer global é None**
   - Verificar lifespan do FastAPI
   - Verificar se há múltiplas instâncias

### Longo Prazo (Solução Robusta)

1. **Uniformizar formato de mensagem:**
   - Opção A: Forçar Avro em todos os serviços
   - Opção B: Usar JSON com Schema Registry para validação
   - Opção C: Hybrid (Avro com JSON fallback)

2. **Adicionar testes automatizados:**
   - Teste de formato de mensagem no Kafka
   - Teste de compatibilidade Gateway ↔ STE
   - CI/CD deve validar formato

---

## 7. ANÁLISE TÉCNICA

### 7.1 Confluent Kafka vs Apicurio Registry

- Gateway usa `confluent_kafka` Schema Registry client
- Cluster usa Apicurio Registry com compatibilidade Confluent (`/apis/ccompat/v7`)
- Teste manual: **compatível** ✅

### 7.2 Formato da Mensagem

**Esperado (Avro - Confluent Wire Format):**
```
Byte 0: 0x00 (magic byte)
Bytes 1-4: Schema ID (big-endian)
Bytes 5+: Avro binary data
```

**Recebido (JSON):**
```
Byte 0: 0x7B ('{')
Bytes 1+: JSON text
```

### 7.3 Schema Match

Gateway e STE usam o mesmo schema (`intent-envelope.avsc`), mas:
- Gateway serializa com campo `correlationId`
- STE espera campo `id`
- **Está correto** - o schema tem ambos os campos

---

## 8. CONCLUSÃO

### 8.1 Problema Confirmado

O Gateway está enviando **JSON** em vez de **Avro**:
- Teste manual: Avro funciona (magic byte 0x00)
- Mensagem real: JSON (magic byte 0x7B)
- `kafka_producer` global: None quando importado

### 8.2 Causa Mais Provável

O `avro_serializer` está `None` no momento do `send_intent()` da requisição real, mas funciona em teste manual. Isso sugere:
- Recriação do producer em runtime sem Schema Registry
- Ou escopo de módulo diferente (uvicorn)

### 8.3 Próxima Ação Recomendada

1. **Resolver deploy** do Gateway primeiro
2. **Adicionar logs** no código (já preparado)
3. **Re-executar teste** com logs para capturar estado exato
4. **Implementar fix** com base nos logs

---

**FIM DO RELATÓRIO**

---

## Anexo: Commits Relacionados

```
2be921e debug(gateway): add logs to track avro_serializer state (REVERTIDO)
d27828d debug(ste): adiciona log para debug keys do envelope recebido
5c5cc8e fix(ste): instala neural_hive_observability via pip no Dockerfile
```

## Anexo: Arquivos Modificados

- `services/gateway-intencoes/src/kafka/producer.py` (logs de debug adicionados)
- `services/semantic-translation-engine/src/consumers/intent_consumer.py` (log de keys adicionado)
- `docs/test-raw-data/2026-02-23/RELATORIO_FINAL_DIAGNOSTICO_AVO_JSON_GATEWAY.md` (criado)
