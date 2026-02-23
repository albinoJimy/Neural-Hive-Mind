# RELATÓRIO DIAGNÓSTICO - COMPATIBILIDADE GATEWAY/STE - 2026-02-23

## Resumo Executivo

**Status:** 🔍 DIAGNÓSTICO PARCIALMENTE CONCLUÍDO
**Investigação:** Incompatibilidade na deserialização Avro entre Gateway e STE

---

## 1. PROBLEMA IDENTIFICADO

### 1.1 Sintoma
- Gateway envia intenção com sucesso (HTTP 200, intent_id gerado)
- STE consome mensagem (LAG=0 no Kafka)
- STE não processa a intenção ("0 msgs processadas" nos logs)

### 1.2 Raiz Raiz Identificada

**Erro de Deserialização Avro:**
```
'utf-8' codec can't decode byte 0xee in position 204: invalid continuation byte
```

**Causa:**
O STE estava configurado com:
- `SCHEMA_REGISTRY_URL: http://schema-registry.kafka.svc.cluster.local:8081` (INCORRETO)

Gateway está configurado com:
- `schema_registry_url: https://schema-registry.kafka.svc.cluster.local:8081/apis/ccompat/v7` (CORRETO)

---

## 2. CORREÇÕES APLICADAS

### 2.1 Atualização ConfigMap STE

**Antes:**
```yaml
SCHEMA_REGISTRY_URL: http://schema-registry.kafka.svc.cluster.local:8080/apis/ccompat/v7
```

**Depois (Patch):**
```yaml
SCHEMA_REGISTRY_URL: https://schema-registry.kafka.svc.cluster.local:8081/apis/ccompat/v7
SCHEMA_REGISTRY_TLS_ENABLED: "true"
SCHEMA_REGISTRY_TLS_VERIFY: "false"
```

### 2.2 Atualização Deployment

**Env vars aplicadas:**
```bash
kubectl set env deployment/semantic-translation-engine \
  SCHEMA_REGISTRY_URL=https://schema-registry.kafka.svc.cluster.local:8081/apis/ccompat/v7 \
  SCHEMA_REGISTRY_TLS_ENABLED=true \
  SCHEMA_REGISTRY_TLS_VERIFY=false
```

### 2.3 Debug Log Adicionado

Commit `d27828d`: Adicionado log DEBUG no consumer para mostrar keys do envelope recebido.

---

## 3. STATUS APÓS CORREÇÕES

### 3.1 Pods STE
- ✅ 2/2 Running
- ✅ Schema Registry habilitado nos logs
- ✅ Consumer inicializado com 9 assignments

### 3.2 Teste Pós-Correção

**Intenção Enviada:**
- Intent ID: `21f80700-1025-45a2-8cb0-895cfe2ddccd`
- Gateway: ✅ Processado com sucesso

**Consumidor STE:**
- LAG: 0 (mensagem consumida)
- Logs: ❌ Sem logs de processamento
- DEBUG: ❌ Log de keys não apareceu

---

## 4. INVESTIGAÇÃO ADICIONAL NECESSÁRIA

### 4.1 Avro Deserializer

**Problema:** O AvroDeserializer do `confluent_kafka` pode não estar funcionando corretamente com o Schema Registry Apicurio.

**Sintomas:**
1. STE mostra "Connection aborted" ao tentar deserializar Avro
2. Content-type header é `application/avro`
3. Aversão para JSON fallback falha porque o conteúdo é binário Avro

### 4.2 Possíveis Causas

1. **Compatibilidade Apicurio vs Confluent:**
   - Gateway usa `confluent_kafka` Schema Registry client
   - Cluster Kafka usa Apicio Registry
   - Pode haver incompatibilidade

2. **Schema ID Mismatch:**
   - Gateway pode estar registrando schema com um ID
   - STE pode estar esperando outro ID

3. **TLS Configuration:**
   - Gateway usa HTTPS com certificado
   - STE pode não estar configurado corretamente para TLS

### 4.3 Logs Recentes Pós-Correção

```
timestamp: "2026-02-23T09:35:50.377212"
event: "Schema Registry enabled for consumer"
url: "https://schema-registry.kafka.svc.cluster.local:8081/apis/ccompat/v7"
```

Schema Registry está habilitado corretamente no STE.

---

## 5. PRÓXIMOS PASSOS RECOMENDADOS

### Prioridade 1 - Investigação Avro Deserializer

1. **Adicionar logs detalhados no STE:**
   - Logar resultado do `AvroSerializer.__call__`
   - Verificar se o schema está sendo buscado corretamente
   - Logar o schema ID recebido do Schema Registry

2. **Testar deserialização manual:**
   - Criar script Python para testar deserialização da mensagem
   - Comparar schema do Gateway com schema do STE

3. **Verificar Schema Registry:**
   - Listar schemas registrados para `intentions.technical-value`
   - Verificar se o schema é compatível

### Prioridade 2 - Alternativa JSON Fallback

Se Avro continuar falhando:

1. **Remover content-type header do Gateway:**
   - Gateway não deve enviar `content-type: application/avro`
   - STE deve fazer auto-detecção

2. **Forçar JSON em dev:**
   - Desabilitar Schema Registry temporariamente
   - Usar JSON com formato correto

### Prioridade 3 - Correção Permanente

1. **Uniformizar Schema Registry:**
   - Usar apenas um Schema Registry (Apicurio ou Confluent)
   - Documentar configuração correta

2. **Validação de Schema:**
   - Criar testes automatizados para validar compatibilidade
   - CI/CD deve verificar schema compatibility

---

## 6. ARTEFATOS GERADOS

### Commits
- `5c5cc8e` - Fix STE neural_hive_observability
- `d27828d` - Debug log for envelope keys
- ConfigMap atualizada (via `kubectl patch`)

### Documentos
- `docs/test-raw-data/2026-02-23/RELATORIO_FINAL_TESTE_PIPELINE.md`
- `docs/test-raw-data/2026-02-23/EXECUCAO_TESTE_PIPELINE_COMPLETO.md`

---

## 7. CONCLUSÃO

O diagnóstico identificou que:
1. ✅ Configuração do Schema Registry foi corrigida
2. ⚠️ A deserialização Avro ainda não está funcionando
3. ⚠️ Mais investigação é necessária no AvroDeserializer

**Recomendação:** Priorizar investigação do AvroDeserializer antes de testes adicionais, pois este é um bloqueio fundamental para o funcionamento do pipeline.

---

**FIM DO RELATÓRIO**
