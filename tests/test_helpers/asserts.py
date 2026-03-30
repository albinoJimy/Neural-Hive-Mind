"""
Custom assertions para testes.

Este módulo fornece assertions reutilizáveis e específicos
para o domínio Neural Hive Mind.
"""

import re
from typing import Any, Dict, List, Optional


# =============================================================================
# ID Validations
# =============================================================================

def assert_valid_plan_id(plan_id: str, prefix: str = "plan-") -> None:
    """
    Valida formato de plan_id.

    Args:
        plan_id: ID do plano a validar
        prefix: Prefixo esperado (default: "plan-")

    Raises:
        AssertionError: Se o formato for inválido
    """
    assert isinstance(plan_id, str), f"plan_id deve ser string, got {type(plan_id)}"
    assert plan_id.startswith(prefix), f"plan_id deve começar com '{prefix}', got: {plan_id}"
    assert len(plan_id) > len(prefix), f"plan_id muito curto: {plan_id}"


def assert_valid_ticket_id(ticket_id: str, prefix: str = "ticket-") -> None:
    """
    Valida formato de ticket_id.

    Args:
        ticket_id: ID do ticket a validar
        prefix: Prefixo esperado (default: "ticket-")
    """
    assert isinstance(ticket_id, str), f"ticket_id deve ser string, got {type(ticket_id)}"
    assert ticket_id.startswith(prefix), f"ticket_id deve começar com '{prefix}', got: {ticket_id}"


def assert_valid_opinion_id(opinion_id: str, prefix: str = "opinion-") -> None:
    """
    Valida formato de opinion_id.

    Args:
        opinion_id: ID da opinião a validar
        prefix: Prefixo esperado (default: "opinion-")
    """
    assert isinstance(opinion_id, str), f"opinion_id deve ser string, got {type(opinion_id)}"
    assert opinion_id.startswith(prefix), f"opinion_id deve começar com '{prefix}', got: {opinion_id}"


def assert_valid_specialist_id(specialist_id: str) -> None:
    """
    Valida formato de specialist_id.

    Aceita formatos como "specialist-technical" ou "specialist-business".
    """
    assert isinstance(specialist_id, str), f"specialist_id deve ser string, got {type(specialist_id)}"
    assert "specialist" in specialist_id.lower(), f"specialist_id deve conter 'specialist', got: {specialist_id}"


def assert_valid_workflow_id(workflow_id: str, prefix: str = "workflow-") -> None:
    """
    Valida formato de workflow_id.

    Args:
        workflow_id: ID do workflow a validar
        prefix: Prefixo esperado (default: "workflow-")
    """
    assert isinstance(workflow_id, str), f"workflow_id deve ser string, got {type(workflow_id)}"
    assert workflow_id.startswith(prefix), f"workflow_id deve começar com '{prefix}', got: {workflow_id}"


# =============================================================================
# Value Range Validations
# =============================================================================

def assert_valid_confidence(
    confidence: float,
    min_val: float = 0.0,
    max_val: float = 1.0,
) -> None:
    """
    Valida range de confiança.

    Args:
        confidence: Valor de confiança a validar
        min_val: Valor mínimo aceitável (default: 0.0)
        max_val: Valor máximo aceitável (default: 1.0)

    Raises:
        AssertionError: Se o valor estiver fora do range
    """
    assert isinstance(confidence, (int, float)), f"confidence deve ser numérico, got {type(confidence)}"
    assert min_val <= confidence <= max_val, (
        f"confidence deve estar entre {min_val} e {max_val}, got: {confidence}"
    )


def assert_valid_percentage(value: float, name: str = "percentage") -> None:
    """
    Valida que um valor representa uma percentagem válida (0-100).

    Args:
        value: Valor a validar
        name: Nome do campo para mensagem de erro
    """
    assert isinstance(value, (int, float)), f"{name} deve ser numérico, got {type(value)}"
    assert 0 <= value <= 100, f"{name} deve estar entre 0 e 100, got: {value}"


def assert_valid_duration_ms(duration_ms: int, min_ms: int = 0, max_ms: Optional[int] = None) -> None:
    """
    Valida uma duração em milissegundos.

    Args:
        duration_ms: Duração em milissegundos
        min_ms: Valor mínimo (default: 0)
        max_ms: Valor máximo opcional
    """
    assert isinstance(duration_ms, int), f"duration_ms deve ser int, got {type(duration_ms)}"
    assert duration_ms >= min_ms, f"duration_ms deve ser >= {min_ms}, got: {duration_ms}"
    if max_ms is not None:
        assert duration_ms <= max_ms, f"duration_ms deve ser <= {max_ms}, got: {duration_ms}"


# =============================================================================
# Domain Validations
# =============================================================================

VALID_DOMAINS = {"TECHNICAL", "BUSINESS", "ARCHITECTURE", "BEHAVIOR", "EVOLUTION", "SECURITY"}


def assert_valid_domain(domain: str) -> None:
    """
    Valida que o domínio é um dos valores aceites.

    Args:
        domain: Domínio a validar

    Raises:
        AssertionError: Se o domínio for inválido
    """
    assert isinstance(domain, str), f"domain deve ser string, got {type(domain)}"
    assert domain in VALID_DOMAINS, f"domain deve ser um de {VALID_DOMAINS}, got: {domain}"


VALID_RISK_BANDS = {"low", "medium", "high", "critical"}


def assert_valid_risk_band(risk_band: str) -> None:
    """
    Valida que a banda de risco é um dos valores aceites.

    Args:
        risk_band: Banda de risco a validar
    """
    assert isinstance(risk_band, str), f"risk_band deve ser string, got {type(risk_band)}"
    assert risk_band in VALID_RISK_BANDS, f"risk_band deve ser um de {VALID_RISK_BANDS}, got: {risk_band}"


VALID_PRIORITIES = {"low", "normal", "high", "critical"}


def assert_valid_priority(priority: str) -> None:
    """
    Valida que a prioridade é um dos valores aceites.

    Args:
        priority: Prioridade a validar
    """
    assert isinstance(priority, str), f"priority deve ser string, got {type(priority)}"
    assert priority in VALID_PRIORITIES, f"priority deve ser um de {VALID_PRIORITIES}, got: {priority}"


VALID_STATUSES = {
    "PENDING",
    "IN_PROGRESS",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "APPROVED",
    "REJECTED",
    "TIMEOUT",
}


def assert_valid_status(status: str) -> None:
    """
    Valida que o status é um dos valores aceites.

    Args:
        status: Status a validar
    """
    assert isinstance(status, str), f"status deve ser string, got {type(status)}"
    assert status in VALID_STATUSES, f"status deve ser um de {VALID_STATUSES}, got: {status}"


# =============================================================================
# Task/Dependency Validations
# =============================================================================

def assert_tasks_dependent(task_a: Dict[str, Any], task_b: Dict[str, Any]) -> None:
    """
    Verifica que task_b depende de task_a.

    Args:
        task_a: Tarefa que deve ser dependência
        task_b: Tarefa que deve depender de task_a
    """
    assert "task_id" in task_a, "task_a deve ter field 'task_id'"
    assert "dependencies" in task_b, "task_b deve ter field 'dependencies'"
    assert task_a["task_id"] in task_b["dependencies"], (
        f"task_b deve depender de task_a ({task_a['task_id']}), "
        f"mas dependencies são: {task_b['dependencies']}"
    )


def assert_no_circular_dependencies(tasks: List[Dict[str, Any]]) -> None:
    """
    Verifica que não existem dependências circulares entre tarefas.

    Args:
        tasks: Lista de tarefas com task_id e dependencies

    Raises:
        AssertionError: Se encontrar dependência circular
    """
    task_map = {task["task_id"]: task for task in tasks}
    visited = set()
    rec_stack = set()

    def dfs(task_id: str, path: List[str]) -> None:
        if task_id in rec_stack:
            cycle = " -> ".join(path + [task_id])
            raise AssertionError(f"Circular dependency detected: {cycle}")

        if task_id in visited:
            return

        visited.add(task_id)
        rec_stack.add(task_id)

        task = task_map.get(task_id)
        if task:
            for dep_id in task.get("dependencies", []):
                dfs(dep_id, path + [task_id])

        rec_stack.remove(task_id)

    for task in tasks:
        task_id = task["task_id"]
        if task_id not in visited:
            dfs(task_id, [])


# =============================================================================
# Decision/Opinion Validations
# =============================================================================

def assert_consolidated_decision(
    decision: Dict[str, Any],
    expected_decision: Optional[bool] = None,
) -> None:
    """
    Valida que uma decisão consolidada tem campos obrigatórios.

    Args:
        decision: Dicionário de decisão a validar
        expected_decision: Decisão esperada (opcional)
    """
    required_fields = [
        "decision_id",
        "plan_id",
        "final_decision",
        "consensus_score",
        "approval_rate",
    ]

    for field in required_fields:
        assert field in decision, f"decision deve ter field '{field}'"

    assert_valid_confidence(decision["consensus_score"])
    assert_valid_confidence(decision["approval_rate"])

    if expected_decision is not None:
        assert decision["final_decision"] == expected_decision, (
            f"Expected final_decision={expected_decision}, got: {decision['final_decision']}"
        )


def assert_specialist_opinion(
    opinion: Dict[str, Any],
    expected_recommendation: Optional[bool] = None,
) -> None:
    """
    Valida que uma opinião de especialista tem campos obrigatórios.

    Args:
        opinion: Dicionário de opinião a validar
        expected_recommendation: Recomendação esperada (opcional)
    """
    required_fields = [
        "opinion_id",
        "plan_id",
        "specialist_id",
        "recommendation",
        "confidence",
        "domain",
    ]

    for field in required_fields:
        assert field in opinion, f"opinion deve ter field '{field}'"

    assert_valid_confidence(opinion["confidence"])
    assert_valid_domain(opinion["domain"])

    if expected_recommendation is not None:
        assert opinion["recommendation"] == expected_recommendation, (
            f"Expected recommendation={expected_recommendation}, "
            f"got: {opinion['recommendation']}"
        )


def assert_approve_reject_balance(
    approve_count: int,
    reject_count: int,
    min_total: int = 3,
) -> None:
    """
    Valida balanceamento entre aprovações e rejeições.

    Args:
        approve_count: Número de aprovações
        reject_count: Número de rejeições
        min_total: Mínimo total de opiniões
    """
    total = approve_count + reject_count
    assert total >= min_total, (
        f"Total de opiniões ({total}) deve ser >= {min_total}"
    )


# =============================================================================
# CognitivePlan Validations
# =============================================================================

def assert_cognitive_plan(plan: Dict[str, Any]) -> None:
    """
    Valida que um CognitivePlan tem campos obrigatórios.

    Args:
        plan: Dicionário de plano a validar
    """
    required_fields = [
        "plan_id",
        "intent_id",
        "intent",
        "domain",
        "status",
        "tasks",
    ]

    for field in required_fields:
        assert field in plan, f"plan deve ter field '{field}'"

    assert_valid_plan_id(plan["plan_id"])
    assert_valid_domain(plan["domain"])
    assert_valid_status(plan["status"])

    assert isinstance(plan["tasks"], list), "plan.tasks deve ser uma lista"
    assert len(plan["tasks"]) > 0, "plan.tasks deve ter pelo menos uma tarefa"

    for task in plan["tasks"]:
        assert "task_id" in task, "cada task deve ter field 'task_id'"
        assert "task_type" in task, "cada task deve ter field 'task_type'"


# =============================================================================
# HTTP Response Validations
# =============================================================================

def assert_http_response(
    response: Dict[str, Any],
    expected_status: int = 200,
    expected_fields: Optional[List[str]] = None,
) -> None:
    """
    Valida uma resposta HTTP padrão.

    Args:
        response: Resposta a validar
        expected_status: Status HTTP esperado
        expected_fields: Campos esperados no body (opcional)
    """
    assert "status_code" in response, "response deve ter field 'status_code'"
    assert response["status_code"] == expected_status, (
        f"Expected status={expected_status}, got: {response['status_code']}"
    )

    if expected_fields:
        body = response.get("json", response.get("body", {}))
        for field in expected_fields:
            assert field in body, f"response body deve ter field '{field}'"


# =============================================================================
# Kafka Message Validations
# =============================================================================

def assert_kafka_message(
    message: Dict[str, Any],
    required_headers: Optional[List[str]] = None,
) -> None:
    """
    Valida uma mensagem Kafka.

    Args:
        message: Mensagem a validar
        required_headers: Headers obrigatórios (opcional)
    """
    assert "key" in message or "value" in message, (
        "message deve ter field 'key' ou 'value'"
    )

    if required_headers:
        headers = message.get("headers", {})
        for header in required_headers:
            assert header in headers, f"message headers deve ter '{header}'"


# =============================================================================
# ML Feedback Validations
# =============================================================================

def assert_feedback_structure(feedback: Dict[str, Any]) -> None:
    """
    Valida estrutura de feedback para treino ML.

    Args:
        feedback: Feedback a validar
    """
    required_fields = [
        "specialist_id",
        "plan_id",
        "human_decision",
        "specialist_confidence",
        "domain",
    ]

    for field in required_fields:
        assert field in feedback, f"feedback deve ter field '{field}'"

    # Validar que human_decision é approve/reject
    assert feedback["human_decision"] in {"approve", "reject"}, (
        f"human_decision deve ser 'approve' ou 'reject', got: {feedback['human_decision']}"
    )

    assert_valid_confidence(feedback["specialist_confidence"])
    assert_valid_domain(feedback["domain"])


def assert_feedback_semantic_features(feedback: Dict[str, Any]) -> None:
    """
    Valida que feedback tem features semânticas para ML.

    Args:
        feedback: Feedback a validar
    """
    assert "intent_raw_text" in feedback, "feedback deve ter 'intent_raw_text' para features semânticas"

    assert isinstance(feedback["intent_raw_text"], str), (
        f"intent_raw_text deve ser string, got: {type(feedback['intent_raw_text'])}"
    )

    assert len(feedback["intent_raw_text"]) > 0, "intent_raw_text não pode estar vazio"

    # Validar reasoning_factors se presentes
    if "reasoning_factors" in feedback:
        factors = feedback["reasoning_factors"]
        assert isinstance(factors, dict), "reasoning_factors deve ser dict"
        assert len(factors) > 0, "reasoning_factors não pode estar vazio"
