#!/bin/bash
# Script de Validação - intent_raw_text Implementation
# Data: 2026-03-16
# Uso: ./validate_intent_raw_text.sh

set -e

echo "=============================================="
echo "VALIDAÇÃO: intent_raw_text Pipeline"
echo "=============================================="
echo ""

APPROVAL_POD="approval-service-586bb5bd7-s2hrs"
STE_POD="semantic-translation-engine-64fd87fb99-2sr5l"
APPROVAL_NS="approval"
STE_NS="neural-hive"

# Cores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo "1. Verificando se campo original_intent_text existe nos modelos..."
echo ""

# Verificar STE
echo -n "[STE] Checking CognitivePlan model... "
STE_CHECK=$(kubectl exec -n $STE_NS $STE_POD -- python3 -c "
import sys
sys.path.insert(0, '/app')
from src.models.cognitive_plan import CognitivePlan
import inspect
sig = inspect.signature(CognitivePlan.__init__)
params = list(sig.parameters.keys())
print('OK' if 'original_intent_text' in params else 'MISSING')
" 2>/dev/null)

if [ "$STE_CHECK" = "OK" ]; then
    echo -e "${GREEN}✓ PASS${NC} - Campo existe no modelo"
else
    echo -e "${RED}✗ FAIL${NC} - Campo NÃO existe no modelo"
    echo "   → PRECISA: fazer rebuild do semantic-translation-engine"
fi

# Verificar approval-service
echo -n "[APPROVAL] Checking ApprovalRequest model... "
APPROVAL_CHECK=$(kubectl exec -n $APPROVAL_NS $APPROVAL_POD -- python3 -c "
import sys
sys.path.insert(0, '/app')
from src.models.approval import ApprovalRequest
import inspect
sig = inspect.signature(ApprovalRequest.__init__)
params = list(sig.parameters.keys())
print('OK' if 'original_intent_text' in params else 'MISSING')
" 2>/dev/null)

if [ "$APPROVAL_CHECK" = "OK" ]; then
    echo -e "${GREEN}✓ PASS${NC} - Campo existe no modelo"
else
    echo -e "${RED}✗ FAIL${NC} - Campo NÃO existe no modelo"
    echo "   → PRECISA: fazer rebuild do approval-service"
fi

echo ""
echo "2. Verificando persistência no MongoDB..."
echo ""

MONGO_CHECK=$(kubectl exec -n $APPROVAL_NS $APPROVAL_POD -- python3 -c "
from pymongo import MongoClient
client = MongoClient('mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin')
db = client['neural_hive']
count = db['plan_approvals'].count_documents({'original_intent_text': {'\$exists': True, '\$ne': None}})
print(count)
" 2>/dev/null)

if [ "$MONGO_CHECK" -gt 0 ]; then
    echo -e "${GREEN}✓ PASS${NC} - Encontrados $MONGO_CHECK plan_approvals com original_intent_text"

    # Mostrar exemplo
    echo ""
    kubectl exec -n $APPROVAL_NS $APPROVAL_POD -- python3 -c "
from pymongo import MongoClient
import json
client = MongoClient('mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin')
db = client['neural_hive']
sample = db['plan_approvals'].find_one({'original_intent_text': {'\$exists': True, '\$ne': None}})
if sample:
    text = sample.get('original_intent_text', '')
    print('Exemplo de texto salvo:')
    print('  ', text[:100] if len(text) > 100 else text)
" 2>/dev/null
else
    echo -e "${YELLOW}⚠ INFO${NC} - Nenhum plan_approvals com original_intent_text encontrado"
    echo "   → Pode indicar que: (a) deploy não foi feito OU (b) nenhum plano novo foi criado após deploy"
fi

echo ""
echo "3. Verificando specialist_feedback com intent_raw_text..."
echo ""

FEEDBACK_CHECK=$(kubectl exec -n $APPROVAL_NS $APPROVAL_POD -- python3 -c "
from pymongo import MongoClient
client = MongoClient('mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin')
db = client['neural_hive']
count = db['specialist_feedback'].count_documents({'intent_raw_text': {'\$exists': True, '\$ne': None}})
print(count)
" 2>/dev/null)

if [ "$FEEDBACK_CHECK" -gt" ]; then
    echo -e "${GREEN}✓ PASS${NC} - Encontrados $FEEDBACK_CHECK feedbacks com intent_raw_text"

    echo ""
    kubectl exec -n $APPROVAL_NS $APPROVAL_POD -- python3 -c "
from pymongo import MongoClient
import json
client = MongoClient('mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin')
db = client['neural_hive']
feedback = db['specialist_feedback'].find_one({'intent_raw_text': {'\$exists': True, '\$ne': None}, {'nlp_features': {'\$exists': True}})
if feedback:
    nlp = feedback.get('nlp_features', {})
    print('Exemplo com NLP features:')
    print('  intent_raw_text:', feedback.get('intent_raw_text', '')[:80])
    print('  nlp_features:', len(nlp), 'features')
    print('  domain_security:', nlp.get('domain_security'))
    print('  primary_domain:', nlp.get('primary_domain'))
else:
    print('  (necessário buscar exemplo com NLP features)')
" 2>/dev/null
else
    echo -e "${YELLOW}⚠ INFO${NC} - Nenhum feedback com intent_raw_text encontrado"
    echo "   → Execute aprovações manuais para gerar feedbacks com texto"
fi

echo ""
echo "4. Resumo do status dos modelos..."
echo ""

echo "[STE] CognitivePlan.original_intent_text:"
kubectl exec -n $STE_NS $STE_POD -- python3 -c "
import sys
sys.path.insert(0, '/app')
from src.models.cognitive_plan import CognitivePlan
import inspect
sig = inspect.signature(CognitivePlan.__init__)
print('  ✅ Presente' if 'original_intent_text' in sig.parameters else '  ❌ Ausente')
" 2>/dev/null

echo "[APPROVAL] ApprovalRequest.original_intent_text:"
kubectl exec -n $APPROVAL_NS $APPROVAL_POD -- python3 -c "
import sys
sys.path.insert(0, '/app')
from src.models.approval import ApprovalRequest
import inspect
sig = inspect.signature(ApprovalRequest.__init__)
print('  ✅ Presente' if 'original_intent_text' in sig.parameters else '  ❌ Ausente')
" 2>/dev/null

echo ""
echo "=============================================="
echo "VALIDAÇÃO CONCLUÍDA"
echo "=============================================="
echo ""
echo "Se todos os testes passarem, o pipeline está funcionando."
echo "Próximos passos:"
echo "1. Coletar 50+ feedbacks com texto da intenção"
echo "2. Executar retraining com NLP features"
echo "3. Validar melhoria da confiança do modelo"
