#!/usr/bin/env python3
"""
Script para criar plan_approvals de teste com original_intent_text
e depois aprová-los para gerar feedbacks com NLP features
"""

import uuid
from datetime import datetime, timezone

def create_test_plan_approvals():
    """Cria plan_approvals de teste com original_intent_text"""

    # Lista de planos de teste
    test_plans = [
        {
            "intent_text": "Create new user with email verification and password hashing",
            "expected_decision": "approve",
            "risk_score": 0.3,
            "risk_band": "low"
        },
        {
            "intent_text": "Delete all records from users table without backup",
            "expected_decision": "reject",
            "risk_score": 0.95,
            "risk_band": "critical"
        },
        {
            "intent_text": "Add index to email column for query performance",
            "expected_decision": "approve",
            "risk_score": 0.2,
            "risk_band": "low"
        },
        {
            "intent_text": "Remove SSL certificate validation to speed up requests",
            "expected_decision": "reject",
            "risk_score": 0.9,
            "risk_band": "high"
        },
        {
            "intent_text": "Enable two-factor authentication for all users",
            "expected_decision": "approve",
            "risk_score": 0.25,
            "risk_band": "low"
        },
        {
            "intent_text": "Grant admin privileges to all authenticated users",
            "expected_decision": "reject",
            "risk_score": 0.95,
            "risk_band": "critical"
        },
        {
            "intent_text": "Implement rate limiting to prevent API abuse",
            "expected_decision": "approve",
            "risk_score": 0.2,
            "risk_band": "low"
        },
        {
            "intent_text": "Drop production database and recreate from scratch",
            "expected_decision": "reject",
            "risk_score": 1.0,
            "risk_band": "critical"
        },
        {
            "intent_text": "Run database backup before schema migration",
            "expected_decision": "approve",
            "risk_score": 0.1,
            "risk_band": "low"
        },
        {
            "intent_text": "Deploy code with known vulnerabilities to production",
            "expected_decision": "reject",
            "risk_score": 0.95,
            "risk_band": "high"
        },
    ]

    created_plan_ids = []

    for i, test in enumerate(test_plans):
        plan_id = str(uuid.uuid4())
        intent_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())

        # Criar cognitive_plan mock
        cognitive_plan = {
            "plan_id": plan_id,
            "intent_id": intent_id,
            "original_intent_text": test["intent_text"],  # Campo chave!
            "correlation_id": correlation_id,
            "tasks": [
                {"task_id": f"task-{i}-1", "task_type": "create", "description": test["intent_text"][:50]}
            ],
            "execution_order": [f"task-{i}-1"],
            "risk_score": test["risk_score"],
            "risk_band": test["risk_band"],
            "status": "validated",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # Criar approval request
        approval_request = {
            "approval_id": str(uuid.uuid4()),
            "plan_id": plan_id,
            "intent_id": intent_id,
            "risk_score": test["risk_score"],
            "risk_band": test["risk_band"],
            "status": "pending",
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "cognitive_plan": cognitive_plan,
            # Campo chave que deve ser persistido
            "original_intent_text": test["intent_text"]
        }

        created_plan_ids.append({
            "plan_id": plan_id,
            "intent_text": test["intent_text"],
            "expected_decision": test["expected_decision"]
        })

        print(f"{i+1}. Plan: {plan_id}")
        print(f"   Text: {test['intent_text'][:50]}...")
        print(f"   Expected: {test['expected_decision']} | Risk: {test['risk_band']}")

    return created_plan_ids

if __name__ == "__main__":
    import json
    import sys

    print("=" * 60)
    print("CRIANDO PLAN_APPROVALS DE TESTE")
    print("=" * 60)
    print()

    plans = create_test_plan_approvals()

    print()
    print("=" * 60)
    print(f"Total: {len(plans)} plan_approvals criados")
    print()
    print("Use este script dentro do pod approval-service:")
    print("kubectl exec -it -n neural-hive <approval-pod> -- python3 -c \"<script>\"")
    print()

    # Salvar para referência
    with open("scripts/test_plan_ids.json", "w") as f:
        json.dump(plans, f, indent=2)
    print(f"Plan IDs salvos em: scripts/test_plan_ids.json")
