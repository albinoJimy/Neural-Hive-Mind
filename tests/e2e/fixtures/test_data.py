import time
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


# ============================================
# Fixtures para Fluxo Avro Completo
# ============================================


@pytest.fixture
def complete_cognitive_plan_avro():
    """
    CognitivePlan completo compatível com schema Avro.

    Inclui todos os campos obrigatórios do schema cognitive-plan.avsc.
    """
    plan_id = str(uuid.uuid4())
    intent_id = str(uuid.uuid4())
    correlation_id = f"e2e-avro-{uuid.uuid4().hex[:8]}"
    now_ms = int(time.time() * 1000)

    return {
        "plan_id": plan_id,
        "version": "1.0.0",
        "intent_id": intent_id,
        "correlation_id": correlation_id,
        "trace_id": f"trace-{uuid.uuid4().hex[:16]}",
        "span_id": f"span-{uuid.uuid4().hex[:8]}",
        "tasks": [
            {
                "task_id": f"task-{uuid.uuid4().hex[:8]}",
                "task_type": "VALIDATE",
                "description": "Validar requisitos e dependências do sistema",
                "dependencies": [],
                "estimated_duration_ms": 30000,
                "required_capabilities": ["python", "validation"],
                "parameters": {"strict_mode": "true"},
                "metadata": {"priority": "high"},
            },
            {
                "task_id": f"task-{uuid.uuid4().hex[:8]}",
                "task_type": "BUILD",
                "description": "Construir componentes de autenticação JWT",
                "dependencies": [],
                "estimated_duration_ms": 60000,
                "required_capabilities": ["python", "security"],
                "parameters": {"algorithm": "RS256"},
                "metadata": {"component": "auth"},
            },
            {
                "task_id": f"task-{uuid.uuid4().hex[:8]}",
                "task_type": "TEST",
                "description": "Executar testes unitários e de integração",
                "dependencies": [],
                "estimated_duration_ms": 45000,
                "required_capabilities": ["pytest", "testing"],
                "parameters": {"coverage_threshold": "80"},
                "metadata": {"test_type": "integration"},
            },
            {
                "task_id": f"task-{uuid.uuid4().hex[:8]}",
                "task_type": "DEPLOY",
                "description": "Deploy automatizado em ambiente staging",
                "dependencies": [],
                "estimated_duration_ms": 120000,
                "required_capabilities": ["kubernetes", "helm"],
                "parameters": {"environment": "staging"},
                "metadata": {"rollback_enabled": "true"},
            },
        ],
        "execution_order": [],  # Será preenchido dinamicamente
        "risk_score": 0.35,
        "risk_band": "medium",
        "risk_factors": {
            "complexity": 0.4,
            "security": 0.3,
            "dependencies": 0.2,
        },
        "explainability_token": f"explain-{uuid.uuid4().hex[:12]}",
        "reasoning_summary": "Plano gerado para implementação de API REST com autenticação JWT. "
                           "Risco médio devido à complexidade de segurança envolvida.",
        "status": "validated",
        "created_at": now_ms,
        "valid_until": now_ms + 3600000,  # +1 hora
        "estimated_total_duration_ms": 255000,
        "complexity_score": 0.65,
        "original_domain": "INFRASTRUCTURE",
        "original_priority": "HIGH",
        "original_security_level": "CONFIDENTIAL",
        "metadata": {
            "source": "e2e_test",
            "test_run_id": str(uuid.uuid4()),
        },
        "schema_version": 1,
    }


@pytest.fixture
def complete_cognitive_plan_avro_with_order(complete_cognitive_plan_avro):
    """
    CognitivePlan com execution_order preenchido corretamente.
    """
    plan = complete_cognitive_plan_avro.copy()
    plan["tasks"] = [task.copy() for task in plan["tasks"]]

    # Configurar dependências entre tasks
    task_ids = [task["task_id"] for task in plan["tasks"]]
    if len(task_ids) >= 4:
        plan["tasks"][1]["dependencies"] = [task_ids[0]]  # BUILD depende de VALIDATE
        plan["tasks"][2]["dependencies"] = [task_ids[1]]  # TEST depende de BUILD
        plan["tasks"][3]["dependencies"] = [task_ids[2]]  # DEPLOY depende de TEST

    plan["execution_order"] = task_ids
    return plan


@pytest.fixture
def sample_intent_for_avro_flow():
    """
    Intent que gera plano cognitivo complexo para teste de fluxo Avro.
    """
    return {
        "text": "Implementar API REST com autenticação JWT, validação de schemas, "
               "testes unitários e integração, documentação OpenAPI, e deploy automatizado",
        "language": "pt-BR",
        "domain": "INFRASTRUCTURE",
        "priority": "HIGH",
        "security_level": "CONFIDENTIAL",
        "correlation_id": f"e2e-avro-{uuid.uuid4().hex[:8]}",
        "context": {
            "source": "e2e_avro_test",
            "timestamp": datetime.utcnow().isoformat(),
            "force_complex_plan": "true",
        },
        "metadata": {
            "test_type": "avro_flow",
            "expected_tasks": "4",
        },
    }


@pytest.fixture
def sample_specialist_opinions():
    """
    Lista de 5 opiniões (uma por specialist) para teste de consenso.

    Estrutura compatível com protobuf SpecialistOpinion.
    """
    specialists = ["technical", "business", "architecture", "behavior", "evolution"]
    opinions = []

    confidence_scores = [0.92, 0.88, 0.95, 0.85, 0.90]
    risk_scores = [0.25, 0.30, 0.20, 0.35, 0.28]

    reasonings = {
        "technical": "Implementação tecnicamente viável com stack moderna. "
                    "Recomendo aprovação com atenção às práticas de segurança.",
        "business": "Alinhado com objetivos de negócio. ROI esperado em 3 meses. "
                   "Custo de implementação dentro do orçamento.",
        "architecture": "Arquitetura proposta segue padrões SOLID e Clean Architecture. "
                       "Escalabilidade garantida com design modular.",
        "behavior": "Comportamento esperado do sistema está bem definido. "
                   "Casos de uso cobertos adequadamente nos testes.",
        "evolution": "Sistema preparado para evolução futura. "
                    "Baixo acoplamento permite extensões sem refatoração.",
    }

    for i, specialist in enumerate(specialists):
        opinions.append({
            "specialist_type": specialist,
            "opinion_id": f"opinion-{specialist}-{uuid.uuid4().hex[:8]}",
            "confidence_score": confidence_scores[i],
            "risk_score": risk_scores[i],
            "recommendation": "approve",
            "reasoning": reasonings[specialist],
            "weight": 1.0 / len(specialists),
            "processing_time_ms": 150 + (i * 25),
            "metadata": {
                "model_version": "v2.1.0",
                "evaluation_depth": "comprehensive",
            },
        })

    return opinions


@pytest.fixture
def sample_consolidated_decision_avro(complete_cognitive_plan_avro, sample_specialist_opinions):
    """
    ConsolidatedDecision completa compatível com schema Avro.
    """
    import json

    now_ms = int(time.time() * 1000)
    plan = complete_cognitive_plan_avro

    return {
        "decision_id": f"decision-{uuid.uuid4().hex[:8]}",
        "plan_id": plan["plan_id"],
        "intent_id": plan["intent_id"],
        "correlation_id": plan["correlation_id"],
        "trace_id": plan.get("trace_id"),
        "span_id": plan.get("span_id"),
        "final_decision": "approve",
        "consensus_method": "bayesian",
        "aggregated_confidence": 0.90,
        "aggregated_risk": 0.28,
        "specialist_votes": sample_specialist_opinions,
        "consensus_metrics": {
            "divergence_score": 0.08,
            "convergence_time_ms": 450,
            "unanimous": False,
            "fallback_used": False,
            "pheromone_strength": 0.85,
            "bayesian_confidence": 0.92,
            "voting_confidence": 0.88,
        },
        "explainability_token": f"explain-decision-{uuid.uuid4().hex[:12]}",
        "reasoning_summary": "Consenso alcançado via método Bayesiano. "
                           "Todos os especialistas recomendam aprovação com alta confiança.",
        "compliance_checks": {
            "security_review": True,
            "cost_analysis": True,
            "risk_assessment": True,
        },
        "guardrails_triggered": [],
        "cognitive_plan": json.dumps(plan),
        "requires_human_review": False,
        "created_at": now_ms,
        "valid_until": now_ms + 7200000,  # +2 horas
        "metadata": {
            "source": "e2e_test",
            "consensus_version": "v1.0.0",
        },
        "hash": f"sha256:{uuid.uuid4().hex}",
        "schema_version": 1,
    }


@pytest.fixture
def sample_execution_ticket_avro(complete_cognitive_plan_avro):
    """
    ExecutionTicket completo compatível com schema Avro.
    """
    now_ms = int(time.time() * 1000)
    plan = complete_cognitive_plan_avro
    task = plan["tasks"][0] if plan["tasks"] else {}

    return {
        "ticket_id": f"ticket-{uuid.uuid4().hex[:8]}",
        "plan_id": plan["plan_id"],
        "intent_id": plan["intent_id"],
        "decision_id": f"decision-{uuid.uuid4().hex[:8]}",
        "correlation_id": plan["correlation_id"],
        "trace_id": plan.get("trace_id"),
        "span_id": plan.get("span_id"),
        "task_id": task.get("task_id", f"task-{uuid.uuid4().hex[:8]}"),
        "task_type": "VALIDATE",
        "description": task.get("description", "Tarefa de teste"),
        "dependencies": [],
        "status": "PENDING",
        "priority": "HIGH",
        "risk_band": "medium",
        "sla": {
            "deadline": now_ms + 3600000,
            "timeout_ms": 300000,
            "max_retries": 3,
        },
        "qos": {
            "delivery_mode": "EXACTLY_ONCE",
            "consistency": "STRONG",
            "durability": "PERSISTENT",
        },
        "parameters": task.get("parameters", {}),
        "required_capabilities": task.get("required_capabilities", []),
        "security_level": "CONFIDENTIAL",
        "created_at": now_ms,
        "started_at": None,
        "completed_at": None,
        "estimated_duration_ms": task.get("estimated_duration_ms", 30000),
        "actual_duration_ms": None,
        "retry_count": 0,
        "error_message": None,
        "compensation_ticket_id": None,
        "metadata": {
            "source": "e2e_test",
            "task_index": "0",
        },
        "schema_version": 1,
    }
