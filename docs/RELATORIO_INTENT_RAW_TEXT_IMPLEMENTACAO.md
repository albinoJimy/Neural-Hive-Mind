# Relatório: Implementação de Captura de intent_raw_text

**Data:** 2026-03-16
**Status:** ✅ IMPLEMENTADO (Pendente de Deploy)

## 📋 Resumo das Mudanças

Foram implementadas modificações para capturar o texto original da intenção (`intent_raw_text`) no pipeline de feedback ML, permitindo que o NLPFeatureExtractor processe o texto e gere features discriminativas.

## 🔧 Mudanças Implementadas

### 1. CognitivePlan Model (semantic-translation-engine)

**Arquivo:** `services/semantic-translation-engine/src/models/cognitive_plan.py`

**Mudanças:**
- Adicionado campo `original_intent_text: Optional[str]` ao modelo CognitivePlan
- Atualizado método `to_avro_dict()` para incluir `original_intent_text`

```python
# Campo adicionado
original_intent_text: Optional[str] = Field(
    None,
    description='Original intent text for ML feedback analysis'
)

# In to_avro_dict()
'original_intent_text': self.original_intent_text,
```

### 2. ApprovalRequest Model (approval-service)

**Arquivo:** `services/approval-service/src/models/approval.py`

**Mudanças:**
- Adicionado campo `original_intent_text: Optional[str]` ao ApprovalRequest

```python
original_intent_text: Optional[str] = Field(
    None,
    description='Texto original da intenção para análise ML'
)
```

### 3. Approval Request Consumer (approval-service)

**Arquivo:** `services/approval-service/src/consumers/approval_request_consumer.py`

**Mudanças:**
- Modificado deserialização para extrair `original_intent_text` do plan_data

```python
approval_request = ApprovalRequest(
    ...
    original_intent_text=plan_data.get('original_intent_text'),
    ...
)
```

### 4. MongoDB Client (approval-service)

**Arquivo:** `services/approval-service/src/clients/mongodb_client.py`

**Mudanças:**
- Modificado `save_approval_request()` para persistir `original_intent_text` no plan_approvals

```python
document = {
    ...
    'original_intent_text': approval.original_intent_text,
    ...
}
```

### 5. Approval Service (approval-service)

**Arquivo:** `services/approval-service/src/services/approval_service.py`

**Mudanças:**
- Modificado `_submit_feedback_for_plan()` para:
  1. Buscar `original_intent_text` do plan_approvals
  2. Incluir `intent_raw_text` no feedback_data

```python
# 1. Buscar texto original da intenção
intent_raw_text = None
try:
    approval = await self.mongodb_client.get_approval_by_plan_id(plan_id)
    if approval:
        intent_raw_text = approval.original_intent_text
except Exception as e:
    logger.debug('Nao foi possivel buscar original_intent_text...')

# 2. Incluir no feedback
feedback_data = {
    ...
    'intent_raw_text': intent_raw_text,
    ...
}
```

## 🔄 Fluxo Completo

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. STE (semantic-translation-engine)                               │
│    - CognitivePlan criado com original_intent_text                   │
│    - to_avro_dict() inclui o texto                                   │
└────────────────────────────┬────────────────────────────────────────┘
                             │ Kafka (cognitive-plans-approval-requests)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. Approval Service Consumer                                        │
│    - Deserializa ApprovalRequest com original_intent_text            │
│    - Salva no MongoDB (plan_approvals)                               │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. Approval Service (approve/reject)                                │
│    - Busca original_intent_text do plan_approvals                   │
│    - Inclui intent_raw_text no feedback_data                         │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. FeedbackCollector (neural_hive_specialists)                      │
│    - Recebe intent_raw_text no feedback_data                         │
│    - Chama enrich_with_nlp_features()                                │
│    - Salva nlp_features no specialist_feedback                       │
└─────────────────────────────────────────────────────────────────────┘
```

## 📊 Arquivos Modificados

| Arquivo | Service | Mudança |
|---------|---------|---------|
| `src/models/cognitive_plan.py` | semantic-translation-engine | + campo original_intent_text |
| `src/models/approval.py` | approval-service | + campo original_intent_text |
| `src/consumers/approval_request_consumer.py` | approval-service | + extração do campo |
| `src/clients/mongodb_client.py` | approval-service | + persistência do campo |
| `src/services/approval_service.py` | approval-service | + busca e envio no feedback |

## ⚠️ Pré-requisitos para Funcionamento

### 1. STE precisa popular o campo

O semantic-translation-engine precisa popular o campo `original_intent_text` quando criar o `CognitivePlan`. Isso requer:

```python
# No código que cria o CognitivePlan
cognitive_plan = CognitivePlan(
    ...
    original_intent_text=intent.raw_text,  # ADICIONAR
    ...
)
```

### 2. Deploy em Ordem

1. **Deploy approval-service** com as mudanças
2. **Deploy semantic-translation-engine** com as mudanças
3. **Validar** que intent_raw_text está sendo salvo no plan_approvals
4. **Validar** que intent_raw_text está sendo salvo no specialist_feedback

## 🧪 Como Validar

### 1. Verificar se texto está sendo salvo no plan_approvals

```bash
kubectl exec -n approval approval-service-586bb5bd7-s2hrs -- python3 -c "
from pymongo import MongoClient
client = MongoClient('mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin')
db = client['neural_hive']
approval = db['plan_approvals'].find_one({})
if approval:
    print('original_intent_text:', approval.get('original_intent_text', 'NOT FOUND'))
"
```

### 2. Verificar se texto está sendo salvo no specialist_feedback

```bash
kubectl exec -n approval approval-service-586bb5bd7-s2hrs -- python3 -c "
from pymongo import MongoClient
client = MongoClient('mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin')
db = client['neural_hive']
feedback = db['specialist_feedback'].find_one({'schema_version': '2.0.0'})
if feedback:
    print('intent_raw_text:', feedback.get('intent_raw_text', 'NOT FOUND'))
    nlp_features = feedback.get('nlp_features', {})
    print('nlp_features:', len(nlp_features), 'features')
"
```

### 3. Verificar se NLP features estão sendo geradas

```bash
kubectl exec -n approval approval-service-586bb5bd7-s2hrs -- python3 -c "
from pymongo import MongoClient
client = MongoClient('mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin')
db = client['neural_hive']

# Buscar feedback com nlp_features
pipeline = [
    {'\$match': {'nlp_features': {'\$ne': {}}}},
    {'\$limit': 1}
]
feedback = db['specialist_feedback'].find_one(pipeline)
if feedback:
    print('NLP features encontradas!')
    print('domain_security:', feedback['nlp_features'].get('domain_security'))
    print('primary_domain:', feedback['nlp_features'].get('primary_domain'))
else:
    print('Nenhum feedback com nlp_features encontrado')
"
```

## 🎯 Próximos Passos

1. **Identificar onde CognitivePlan é criado** no STE
2. **Adicionar original_intent_text** na criação do plano
3. **Deploy e testar** as mudanças
4. **Coletar novos feedbacks** com texto da intenção
5. **Retreinar modelo** com features NLP populadas

## 📝 Notas

- O `intent_id` no specialist_opinion está encriptado (enc:...), então não é possível buscar o texto original de lá
- A única fonte confiável do texto é o approval request que vem do STE
- O texto precisa ser incluído no CognitivePlan antes de ser enviado ao Kafka
