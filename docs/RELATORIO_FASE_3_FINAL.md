# Relatório FASE 3 - Implementação de intent_raw_text

**Data:** 2026-03-16
**Status:** ✅ CÓDIGO COMPLETO, ⏳ PENDING DEPLOY/TESTE

## 📋 Resumo

Implementação completa da captura do texto original da intenção (`intent_raw_text`) através de todo o pipeline, desde a criação do CognitivePlan até o feedback ML. Isso permite que o NLPFeatureExtractor processe o texto e gere features discriminativas para treinar modelos ML melhores.

## 🔧 Mudanças Implementadas

### 1. semantic-translation-engine (STE)

#### Arquivo: `src/models/cognitive_plan.py`
- ✅ Adicionado campo `original_intent_text: Optional[str]`
- ✅ Atualizado `to_avro_dict()` para incluir o campo

#### Arquivo: `src/services/orchestrator.py`
- ✅ Modificado `process_intent()` para passar `intent.get('text')` como `original_intent_text`

```python
return CognitivePlan(
    intent_id=intent_envelope.get('id'),
    original_intent_text=intent.get('text'),  # ← ADICIONADO
    correlation_id=correlation_id,
    ...
)
```

### 2. approval-service

#### Arquivo: `src/models/approval.py`
- ✅ Adicionado campo `original_intent_text: Optional[str]` ao ApprovalRequest

#### Arquivo: `src/consumers/approval_request_consumer.py`
- ✅ Modificado deserialização para extrair `original_intent_text` do plan_data

```python
approval_request = ApprovalRequest(
    ...
    original_intent_text=plan_data.get('original_intent_text'),  # ← ADICIONADO
    ...
)
```

#### Arquivo: `src/clients/mongodb_client.py`
- ✅ Modificado `save_approval_request()` para persistir `original_intent_text`

```python
document = {
    ...
    'original_intent_text': approval.original_intent_text,  # ← ADICIONADO
    ...
}
```

#### Arquivo: `src/services/approval_service.py`
- ✅ Modificado `_submit_feedback_for_plan()` para:
  1. Buscar `original_intent_text` do plan_approvals
  2. Incluir `intent_raw_text` no feedback_data

```python
# Buscar texto original
approval = await self.mongodb_client.get_approval_by_plan_id(plan_id)
intent_raw_text = approval.original_intent_text if approval else None

# Incluir no feedback
feedback_data = {
    ...
    'intent_raw_text': intent_raw_text,  # ← ADICIONADO
    ...
}
```

## 🔄 Fluxo Completo de Dados

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Gateway de Intenções                                           │
│    - Recebe intenção do usuário com texto                           │
│    - Envia para STE via Kafka                                      │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. Semantic Translation Engine (orchestrator.py)                  │
│    - process_intent() é chamado                                  │
│    - intent.get('text') é extraído                                │
│    - CognitivePlan criado com original_intent_text                 │
│    - to_avro_dict() inclui o texto no JSON/Avro                   │
└────────────────────────────┬────────────────────────────────────────┘
                             │ Kafka (cognitive-plans-approval-requests)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. Approval Service Consumer                                      │
│    - Deserializa ApprovalRequest com original_intent_text         │
│    - MongoDBClient salva em plan_approvals                         │
└────────────────────────────┬────────────────────────────────────────┘
                             │ Usuário aprova/rejeita
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. Approval Service (approve_plan/reject_plan)                   │
│    - Busca original_intent_text do plan_approvals                  │
│    - Inclui intent_raw_text no feedback_data                        │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 5. FeedbackCollector (neural_hive_specialists)                    │
│    - Recebe feedback_data com intent_raw_text                       │
│    - enrich_with_nlp_features() processa o texto                    │
│    - Salva nlp_features no specialist_feedback                      │
└─────────────────────────────────────────────────────────────────────┘
```

## 📊 Arquivos Modificados (Total: 6)

| Service | Arquivo | Linhas |
|---------|---------|-------|
| semantic-translation-engine | `src/models/cognitive_plan.py` | +2 |
| semantic-translation-engine | `src/services/orchestrator.py` | +1 |
| approval-service | `src/models/approval.py` | +3 |
| approval-service | `src/consumers/approval_request_consumer.py` | +1 |
| approval-service | `src/clients/mongodb_client.py` | +1 |
| approval-service | `src/services/approval_service.py` | ~20 |

## ⏳ Próximos Passos

### 1. Deploy e Teste (IMEDIATO)

```bash
# 1. Rebuild e deploy approval-service
kubectl rollout restart deployment/approval-service -n approval

# 2. Rebuild e deploy semantic-translation-engine
kubectl rollout restart deployment/semantic-translation-engine -n default

# 3. Testar fluxo com nova intenção
# Enviar intenção de teste e verificar se original_intent_text é salvo
```

### 2. Validação

```bash
# Verificar se texto está sendo salvo no plan_approvals
kubectl exec -n approval approval-service-586bb5bd7-s2hrs -- python3 -c "
from pymongo import MongoClient
client = MongoClient('mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin')
db = client['neural_hive']
approval = db['plan_approvals'].find_one({'original_intent_text': {'\$exists': true}})
if approval:
    print('✅ original_intent_text encontrado:')
    print('   ', approval.get('original_intent_text')[:100])
else:
    print('❌ Nenhum plan_approvals com original_intent_text encontrado')
"
```

### 3. Coletar Feedbacks com Texto

Após deploy validado, coletar pelo menos 50 feedbacks com:
- Aproximadamente 15 "approve"
- Aproximadamente 15 "reject"
- Aproximadamente 20 "review_required"

### 4. Retreinar Modelo

```bash
kubectl exec -n approval approval-service-586bb5bd7-s2hrs -- python3 /tmp/retrain_v6_with_nlp.py
```

## 📝 Notas Técnicas

### Compatibilidade com Schema Existente

- O campo `original_intent_text` é `Optional[str]`, então não quebra código legado
- Planos antigos sem o campo continuam funcionando (valor padrão: None)
- O campo é incluído no `to_avro_dict()` para serialização Kafka

### Preservação de Texto

- O texto é armazenado em 3 lugares:
  1. CognitivePlan (memória do STE)
  2. plan_approvals (MongoDB - approval-service)
  3. specialist_feedback (MongoDB - via FeedbackCollector)

- Isso garante que o texto não é perdido mesmo se um dos serviços falhar

## 🎯 Critérios de Sucesso

| Critério | Status | Valor Esperado |
|----------|--------|-----------------|
| Campo adicionado ao CognitivePlan | ✅ | Sim |
| Campo adicionado ao ApprovalRequest | ✅ | Sim |
 approval-service salva texto | ✅ | Sim |
| FeedbackCollector recebe texto | ✅ | Sim |
| Deploy completo | ⏳ | Pending |
| Texto salvo no plan_approvals | ⏳ | Validar após deploy |
| NLP features geradas | ⏳ | Validar após deploy |
| Modelo retrinado com NLP | ⏳ | Pós-coleta |

## 📚 Relatórios Relacionados

- `docs/RELATORIO_INTENT_RAW_TEXT_IMPLEMENTACAO.md` - Implementação detalhada
- `docs/RELATORIO_FASE_2_CONCLUSAO.md` - Análise de limitações anteriores
- `docs/RESUMO_PROGRESSO_ML.md` - Progresso consolidado
