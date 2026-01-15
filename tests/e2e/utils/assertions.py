from typing import Dict


def assert_ticket_valid(ticket: dict) -> None:
    required_fields = ["ticket_id", "correlation_id", "task", "status", "sla_deadline_ms"]
    missing = [field for field in required_fields if field not in ticket]
    assert not missing, f"Ticket missing fields: {missing}"


def assert_workflow_completed(workflow: dict) -> None:
    assert workflow is not None, "Workflow not found"
    assert workflow.get("status") == "COMPLETED", f"Workflow status is {workflow.get('status')}"


def assert_slo_met(latency_ms: float, slo_ms: float) -> None:
    assert latency_ms < slo_ms, f"Latency {latency_ms}ms exceeds SLO {slo_ms}ms"


# ============================================
# Validações Avro
# ============================================


def assert_avro_message_valid(message: bytes, schema_id: int) -> None:
    """
    Valida que mensagem contém magic byte Avro e schema ID correto.

    Formato Avro: 0x00 + 4 bytes de schema ID (big-endian) + payload
    """
    assert len(message) >= 5, f"Mensagem muito curta para Avro: {len(message)} bytes"
    assert message[0] == 0x00, f"Magic byte inválido: {hex(message[0])}"

    actual_schema_id = int.from_bytes(message[1:5], byteorder="big")
    assert actual_schema_id == schema_id, (
        f"Schema ID não confere: esperado {schema_id}, recebido {actual_schema_id}"
    )


def assert_avro_magic_byte(message: bytes) -> int:
    """
    Valida magic byte Avro e retorna o schema ID.

    Returns:
        Schema ID extraído da mensagem
    """
    assert len(message) >= 5, f"Mensagem muito curta para Avro: {len(message)} bytes"
    assert message[0] == 0x00, f"Magic byte inválido: {hex(message[0])}"

    return int.from_bytes(message[1:5], byteorder="big")


def assert_cognitive_plan_structure(plan: Dict) -> None:
    """
    Valida estrutura completa de CognitivePlan conforme schema Avro.

    Campos obrigatórios:
    - plan_id, version, intent_id, tasks, execution_order
    - risk_score, risk_band, risk_factors
    - explainability_token, reasoning_summary, status
    - created_at, complexity_score
    - original_domain, original_priority, original_security_level
    """
    required_fields = [
        "plan_id",
        "version",
        "intent_id",
        "tasks",
        "execution_order",
        "risk_score",
        "risk_band",
        "risk_factors",
        "explainability_token",
        "reasoning_summary",
        "status",
        "created_at",
        "complexity_score",
        "original_domain",
        "original_priority",
        "original_security_level",
    ]

    for field in required_fields:
        assert field in plan, f"Campo obrigatório ausente em CognitivePlan: {field}"

    # Validar tasks
    assert isinstance(plan["tasks"], list), "tasks deve ser um array"
    assert len(plan["tasks"]) > 0, "tasks não pode estar vazio"

    for task in plan["tasks"]:
        assert "task_id" in task, "Task sem task_id"
        assert "task_type" in task, "Task sem task_type"
        assert "description" in task, "Task sem description"

    # Validar enums
    assert plan["risk_band"] in ["low", "medium", "high", "critical"], (
        f"risk_band inválido: {plan['risk_band']}"
    )
    assert plan["status"] in ["draft", "validated", "approved", "rejected"], (
        f"status inválido: {plan['status']}"
    )

    # Validar ranges
    assert 0.0 <= plan["risk_score"] <= 1.0, (
        f"risk_score fora do range [0,1]: {plan['risk_score']}"
    )
    assert 0.0 <= plan["complexity_score"] <= 1.0, (
        f"complexity_score fora do range [0,1]: {plan['complexity_score']}"
    )


def assert_consolidated_decision_structure(decision: Dict) -> None:
    """
    Valida estrutura completa de ConsolidatedDecision conforme schema Avro.

    Campos obrigatórios:
    - decision_id, plan_id, intent_id
    - final_decision, consensus_method
    - aggregated_confidence, aggregated_risk
    - specialist_votes, consensus_metrics
    - explainability_token, reasoning_summary
    - created_at, hash
    """
    required_fields = [
        "decision_id",
        "plan_id",
        "intent_id",
        "final_decision",
        "consensus_method",
        "aggregated_confidence",
        "aggregated_risk",
        "specialist_votes",
        "consensus_metrics",
        "explainability_token",
        "reasoning_summary",
        "created_at",
        "hash",
    ]

    for field in required_fields:
        assert field in decision, f"Campo obrigatório ausente em ConsolidatedDecision: {field}"

    # Validar enums
    assert decision["final_decision"] in ["approve", "reject", "review_required", "conditional"], (
        f"final_decision inválido: {decision['final_decision']}"
    )
    assert decision["consensus_method"] in ["bayesian", "voting", "unanimous", "fallback"], (
        f"consensus_method inválido: {decision['consensus_method']}"
    )

    # Validar ranges
    assert 0.0 <= decision["aggregated_confidence"] <= 1.0, (
        f"aggregated_confidence fora do range [0,1]: {decision['aggregated_confidence']}"
    )
    assert 0.0 <= decision["aggregated_risk"] <= 1.0, (
        f"aggregated_risk fora do range [0,1]: {decision['aggregated_risk']}"
    )

    # Validar specialist_votes
    assert isinstance(decision["specialist_votes"], list), "specialist_votes deve ser um array"
    for vote in decision["specialist_votes"]:
        assert "specialist_type" in vote, "Vote sem specialist_type"
        assert "opinion_id" in vote, "Vote sem opinion_id"
        assert "confidence_score" in vote, "Vote sem confidence_score"
        assert "recommendation" in vote, "Vote sem recommendation"

    # Validar consensus_metrics
    metrics = decision["consensus_metrics"]
    assert "divergence_score" in metrics, "consensus_metrics sem divergence_score"
    assert "convergence_time_ms" in metrics, "consensus_metrics sem convergence_time_ms"


def assert_execution_ticket_structure(ticket: Dict) -> None:
    """
    Valida estrutura completa de ExecutionTicket conforme schema Avro.

    Campos obrigatórios:
    - ticket_id, plan_id, intent_id, decision_id
    - task_id, task_type, description
    - status, priority, risk_band
    - sla, qos
    - security_level, created_at
    """
    required_fields = [
        "ticket_id",
        "plan_id",
        "intent_id",
        "decision_id",
        "task_id",
        "task_type",
        "description",
        "status",
        "priority",
        "risk_band",
        "sla",
        "qos",
        "security_level",
        "created_at",
    ]

    for field in required_fields:
        assert field in ticket, f"Campo obrigatório ausente em ExecutionTicket: {field}"

    # Validar enums
    assert ticket["task_type"] in ["BUILD", "DEPLOY", "TEST", "VALIDATE", "EXECUTE", "COMPENSATE"], (
        f"task_type inválido: {ticket['task_type']}"
    )
    assert ticket["status"] in ["PENDING", "RUNNING", "COMPLETED", "FAILED", "COMPENSATING", "COMPENSATED"], (
        f"status inválido: {ticket['status']}"
    )
    assert ticket["priority"] in ["LOW", "NORMAL", "HIGH", "CRITICAL"], (
        f"priority inválido: {ticket['priority']}"
    )
    assert ticket["risk_band"] in ["low", "medium", "high", "critical"], (
        f"risk_band inválido: {ticket['risk_band']}"
    )
    assert ticket["security_level"] in ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"], (
        f"security_level inválido: {ticket['security_level']}"
    )

    # Validar SLA
    sla = ticket["sla"]
    assert "deadline" in sla, "sla sem deadline"
    assert "timeout_ms" in sla, "sla sem timeout_ms"
    assert "max_retries" in sla, "sla sem max_retries"

    # Validar QoS
    qos = ticket["qos"]
    assert "delivery_mode" in qos, "qos sem delivery_mode"
    assert "consistency" in qos, "qos sem consistency"
    assert "durability" in qos, "qos sem durability"


async def assert_specialist_invoked(
    k8s_client,
    specialist_type: str,
    plan_id: str,
    timeout: int = 60,
) -> None:
    """
    Valida que specialist foi invocado via gRPC.

    Verifica logs do pod do specialist para confirmar recebimento de request.
    """
    import asyncio
    import time

    from tests.e2e.utils.k8s_helpers import get_pod_logs

    namespace = "neural-hive-specialists"
    label_selector = f"app=specialist-{specialist_type}"

    start_time = time.time()
    while time.time() - start_time < timeout:
        logs = get_pod_logs(
            k8s_client,
            namespace=namespace,
            label_selector=label_selector,
            tail_lines=200,
        )

        if "Received EvaluatePlan request" in logs and plan_id in logs:
            return

        await asyncio.sleep(2)

    raise AssertionError(
        f"Specialist {specialist_type} não foi invocado para plan {plan_id}"
    )
