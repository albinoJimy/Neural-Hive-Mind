# Correção: Incompatibilidade de Serialização Kafka

**Data**: 2025-11-06
**Problema**: Semantic Translation Engine não conseguia deserializar mensagens do Gateway

## Diagnóstico

### Sintoma
```
'utf-8' codec can't decode byte 0xb8 in position 97: invalid start byte
```

### Causa Raiz
- **Gateway**: Serializando mensagens em **Avro** (Schema Registry configurado)
- **Semantic Translation**: Tentando deserializar como **JSON** (Schema Registry não configurado)

### Evidências
```bash
# Gateway tinha:
SCHEMA_REGISTRY_URL=http://schema-registry.kafka.svc.cluster.local:8081/apis/ccompat/v6

# Semantic Translation tinha:
SCHEMA_REGISTRY_URL=  # VAZIO
```

## Solução Aplicada

### 1. Configurar Schema Registry URL

**Arquivo**: `helm-charts/semantic-translation-engine/values-local.yaml`

```yaml
schemaRegistry:
  url: "http://schema-registry.kafka.svc.cluster.local:8081/apis/ccompat/v6"
```

### 2. Adicionar Variável ao ConfigMap

**Arquivo**: `helm-charts/semantic-translation-engine/templates/configmap.yaml`

```yaml
# Schema Registry Configuration
SCHEMA_REGISTRY_URL: {{ .Values.config.schemaRegistry.url | quote }}
```

### 3. Reinstalar Serviço

```bash
helm uninstall semantic-translation-engine -n semantic-translation-engine
helm install semantic-translation-engine ./helm-charts/semantic-translation-engine \
  --namespace semantic-translation-engine \
  --create-namespace \
  --values ./helm-charts/semantic-translation-engine/values-local.yaml
```

## Resultado

### Antes
```
❌ Erro ao deserializar mensagem
❌ Pipeline bloqueado no Semantic Translation
```

### Depois
```
✅ Schema Registry enabled for consumer
✅ Mensagem deserializada (Avro)
✅ Intent processado corretamente
```

### Logs de Sucesso
```
2025-11-06 14:35:50 [info] Schema Registry enabled for producer
2025-11-06 14:35:50 [info] Schema Registry enabled for consumer
2025-11-06 14:36:17 [debug] Mensagem deserializada (Avro) domain=SECURITY
```

## Validação

### Teste Realizado
```json
{
  "text": "Criar dashboard para monitoramento de performance",
  "correlation_id": "test-fix-avro-001"
}
```

### Resultado
```json
{
  "intent_id": "5359bf86-0c81-4ebf-bb5e-b45f04050659",
  "status": "processed",
  "confidence": 0.95,
  "domain": "business"
}
```

**Status**: ✅ Mensagem deserializada com sucesso

## Arquivos Modificados

1. `helm-charts/semantic-translation-engine/values-local.yaml` (linha 60)
2. `helm-charts/semantic-translation-engine/templates/configmap.yaml` (linhas 20-21)

## Observações

- Problema de serialização **resolvido**
- Fluxo Gateway → Semantic Translation **funcionando**
- Novo erro de event loop detectado no Semantic Translation (problema separado)

---

**Correção concluída com sucesso**
