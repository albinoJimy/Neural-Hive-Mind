#!/usr/bin/env python3
"""
Script de Validação - intent_raw_text Implementation

Data: 2026-03-16
Uso: python3 validate_intent_raw_text.py
"""

import subprocess

APPROVAL_POD = "approval-service-76b976f8c8-pr499"
STE_POD = "semantic-translation-engine-5cb5dffcf5-2w77k"
APPROVAL_NS = "neural-hive"
STE_NS = "neural-hive"


def kubectl_exec(namespace, pod, cmd):
    """Executa comando kubectl e retorna output"""
    full_cmd = f'kubectl exec -n {namespace} {pod} -- python3 -c "{cmd}" 2>/dev/null'
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    # Pega apenas a última linha que deve ser OK ou MISSING
    lines = result.stdout.strip().split("\n")
    return lines[-1] if lines else "", result.returncode


def check_ste_model():
    """Verifica se campo existe no modelo STE"""
    print("[STE] Checking CognitivePlan model...")
    cmd = """
import sys
sys.path.insert(0, '/app')
from src.models.cognitive_plan import CognitivePlan
fields = getattr(CognitivePlan, 'model_fields', getattr(CognitivePlan, '__fields__', {}))
print('OK' if 'original_intent_text' in fields else 'MISSING')
"""
    out, code = kubectl_exec(STE_NS, STE_POD, cmd)
    return out == "OK"


def check_approval_model():
    """Verifica se campo existe no modelo Approval"""
    print("[APPROVAL] Checking ApprovalRequest model...")
    cmd = """
import sys
sys.path.insert(0, '/app')
from src.models.approval import ApprovalRequest
fields = getattr(ApprovalRequest, 'model_fields', getattr(ApprovalRequest, '__fields__', {}))
print('OK' if 'original_intent_text' in fields else 'MISSING')
"""
    out, code = kubectl_exec(APPROVAL_NS, APPROVAL_POD, cmd)
    return out == "OK"


def count_mongo_plans():
    """Conta plan_approvals com original_intent_text"""
    cmd = """
from pymongo import MongoClient
client = MongoClient('mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin')
db = client['neural_hive']
count = db['plan_approvals'].count_documents({'original_intent_text': {'$exists': True, '$ne': None}})
print(count)
"""
    out, code = kubectl_exec(APPROVAL_NS, APPROVAL_POD, cmd)
    try:
        return int(out) if out else 0
    except ValueError:
        return 0


def count_mongo_feedbacks():
    """Conta specialist_feedback com intent_raw_text"""
    cmd = """
from pymongo import MongoClient
client = MongoClient('mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin')
db = client['neural_hive']
count = db['specialist_feedback'].count_documents({'intent_raw_text': {'$exists': True, '$ne': None}})
print(count)
"""
    out, code = kubectl_exec(APPROVAL_NS, APPROVAL_POD, cmd)
    try:
        return int(out) if out else 0
    except ValueError:
        return 0


def main():
    print("=" * 60)
    print("VALIDAÇÃO: intent_raw_text Pipeline")
    print("=" * 60)
    print()

    # 1. Verificar modelos
    print("1. Verificando se campo original_intent_text existe nos modelos...")
    print()

    ste_ok = check_ste_model()
    approval_ok = check_approval_model()

    if ste_ok and approval_ok:
        print("  ✓ Ambos modelos têm o campo - PODE ESTAR DEPLOYED")
    else:
        print("  ✗ Pelo menos um modelo NÃO tem o campo - PRECISA DEPLOY")
        return

    print()
    print("2. Verificando persistência no MongoDB...")
    print()

    plans_count = count_mongo_plans()
    if plans_count > 0:
        print(f"  ✓ {plans_count} plan_approvals com original_intent_text")
    else:
        print(
            "  ⚠ Nenhum plano com texto encontrado (pode indicar que não há planos novos pós-deploy)"
        )

    print()
    print("3. Verificando specialist_feedback com intent_raw_text...")
    print()

    feedbacks_count = count_mongo_feedbacks()
    if feedbacks_count > 0:
        print(f"  ✓ {feedbacks_count} feedbacks com intent_raw_text")
    else:
        print("  ⚠ Nenhum feedback com texto encontrado")

    print()
    print("=" * 60)
    print("VALIDAÇÃO CONCLUÍDA")
    print("=" * 60)


if __name__ == "__main__":
    main()
