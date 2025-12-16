import uuid
from datetime import datetime

import pytest


@pytest.fixture
def sample_intent_request():
    return {
        "text": "Implementar sistema de autenticação OAuth2 com refresh tokens e integração com Google/GitHub",
        "language": "pt-BR",
        "correlation_id": f"e2e-test-{uuid.uuid4()}",
        "context": {"source": "e2e_test", "timestamp": datetime.utcnow().isoformat()},
    }


@pytest.fixture
def sample_cognitive_plan():
    return {
        "plan_id": str(uuid.uuid4()),
        "intent_id": str(uuid.uuid4()),
        "tasks": [
            {"id": "t1", "type": "analysis", "dependencies": []},
            {"id": "t2", "type": "execution", "dependencies": ["t1"]},
        ],
        "risk_band": "low",
        "priority": "high",
    }


@pytest.fixture
def sample_execution_ticket():
    return {
        "ticket_id": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
        "task": {"type": "code_generation", "template_id": "test_template", "parameters": {"test": True}},
        "status": "PENDING",
        "sla_deadline_ms": int(datetime.utcnow().timestamp() * 1000) + 3_600_000,
        "worker_id": str(uuid.uuid4()),
    }


@pytest.fixture
def sample_opa_policy_violation():
    return {
        "ticket_id": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
        "task": {"type": "compute_heavy", "template_id": "violation", "parameters": {"cpu": "8000m"}},
        "status": "PENDING",
        "sla_deadline_ms": int(datetime.utcnow().timestamp() * 1000) + 60_000,
        "worker_id": str(uuid.uuid4()),
    }
