"""
Fixtures compartilhadas para testes E2E do Execution Ticket Service.

Este módulo fornece factories e helpers para criação de dados de teste.
"""
from datetime import datetime, timezone
from typing import Dict, Any, List
from uuid import uuid4

from faker import Faker

from src.models import ExecutionTicket, TicketStatus, TaskType, Priority, RiskBand, QoS, SLA


fake = Faker()


class TicketFactory:
    """Factory para criar tickets de teste."""

    @staticmethod
    def create_ticket_data(**overrides) -> Dict[str, Any]:
        """
        Cria dados de ticket com valores aleatórios.

        Args:
            **overrides: Valores para sobrescrever defaults

        Returns:
            Dict com dados do ticket
        """
        ticket_id = overrides.get("ticket_id", f"ticket-{fake.uuid4()}")
        plan_id = overrides.get("plan_id", f"plan-{fake.uuid4()}")
        intent_id = overrides.get("intent_id", f"intent-{fake.uuid4()}")
        decision_id = overrides.get("decision_id", f"decision-{fake.uuid4()}")

        return {
            "ticket_id": ticket_id,
            "plan_id": plan_id,
            "intent_id": intent_id,
            "decision_id": decision_id,
            "correlation_id": overrides.get("correlation_id", f"corr-{fake.uuid4()}"),
            "trace_id": overrides.get("trace_id", fake.uuid4()),
            "span_id": overrides.get("span_id", fake.uuid4()[:32]),
            "task_id": overrides.get("task_id", f"task-{fake.word()}"),
            "task_type": overrides.get("task_type", fake.random_element(["BUILD", "QUERY", "TRANSFORM", "VALIDATE"])),
            "description": overrides.get("description", fake.sentence()),
            "dependencies": overrides.get("dependencies", []),
            "status": overrides.get("status", "PENDING"),
            "priority": overrides.get("priority", fake.random_element(["LOW", "NORMAL", "HIGH", "URGENT"])),
            "risk_band": overrides.get("risk_band", fake.random_element(["low", "medium", "high", "critical"])),
            "sla": overrides.get("sla", {
                "deadline": None,
                "timeout_ms": fake.random_int(10000, 60000),
                "max_retries": fake.random_int(1, 5),
            }),
            "qos": overrides.get("qos", {
                "delivery_mode": fake.random_element(["AT_MOST_ONCE", "AT_LEAST_ONCE"]),
                "consistency": fake.random_element(["EVENTUAL", "STRONG"]),
                "durability": fake.random_element(["TRANSIENT", "PERSISTENT"]),
            }),
            "parameters": overrides.get("parameters", {fake.word(): fake.word() for _ in range(3)}),
            "required_capabilities": overrides.get("required_capabilities", fake.words(nb=fake.random_int(0, 5))),
            "security_level": overrides.get("security_level", fake.random_element(["INTERNAL", "CONFIDENTIAL", "PUBLIC"])),
            "created_at": overrides.get("created_at", int(datetime.now(timezone.utc).timestamp() * 1000)),
            "started_at": overrides.get("started_at", None),
            "completed_at": overrides.get("completed_at", None),
            "estimated_duration_ms": overrides.get("estimated_duration_ms", fake.random_int(1000, 30000)),
            "actual_duration_ms": overrides.get("actual_duration_ms", None),
            "retry_count": overrides.get("retry_count", 0),
            "error_message": overrides.get("error_message", None),
            "compensation_ticket_id": overrides.get("compensation_ticket_id", None),
            "metadata": overrides.get("metadata", {
                "idempotency_key": f"idemp-{fake.uuid4()}",
                "source": "e2e-test",
                "test_case": fake.word(),
            }),
            "schema_version": overrides.get("schema_version", 1),
        }

    @staticmethod
    def create_failed_ticket_data(**overrides) -> Dict[str, Any]:
        """Cria dados de ticket em estado FAILED."""
        return TicketFactory.create_ticket_data(
            status="FAILED",
            retry_count=fake.random_int(1, 3),
            error_message=fake.sentence(),
            **overrides
        )

    @staticmethod
    def create_running_ticket_data(**overrides) -> Dict[str, Any]:
        """Cria dados de ticket em estado RUNNING."""
        return TicketFactory.create_ticket_data(
            status="RUNNING",
            started_at=int((datetime.now(timezone.utc).timestamp() - fake.random_int(1, 100)) * 1000),
            **overrides
        )

    @staticmethod
    def create_completed_ticket_data(**overrides) -> Dict[str, Any]:
        """Cria dados de ticket em estado COMPLETED."""
        started_at = int((datetime.now(timezone.utc).timestamp() - fake.random_int(10, 100)) * 1000)
        return TicketFactory.create_ticket_data(
            status="COMPLETED",
            started_at=started_at,
            completed_at=int(datetime.now(timezone.utc).timestamp() * 1000),
            actual_duration_ms=fake.random_int(1000, 10000),
            **overrides
        )

    @staticmethod
    def create_compensation_ticket_data(original_ticket_id: str, **overrides) -> Dict[str, Any]:
        """Cria dados de ticket de compensação."""
        return TicketFactory.create_ticket_data(
            task_type="COMPENSATE",
            task_id=f"compensate-{original_ticket_id[:8]}",
            description=f"Compensation for ticket {original_ticket_id}",
            priority="HIGH",
            risk_band="high",
            status="PENDING",
            parameters={
                "action": overrides.get("action", "rollback"),
                "reason": overrides.get("reason", "Original ticket failed"),
                "original_ticket_id": original_ticket_id,
                **overrides.get("parameters", {})
            },
            dependencies=[],
            **overrides
        )

    @staticmethod
    def create_multi_step_ticket_data(step_count: int, **overrides) -> Dict[str, Any]:
        """Cria dados de ticket com múltiplas dependências."""
        dependencies = [
            {"ticket_id": f"dep-{i}-{fake.uuid4()}", "task_type": fake.random_element(["VALIDATE", "PREPARE", "EXECUTE"])}
            for i in range(step_count)
        ]

        return TicketFactory.create_ticket_data(
            description=f"Multi-step workflow with {step_count} dependencies",
            dependencies=dependencies,
            required_capabilities=[f"capability_{i}" for i in range(step_count)],
            **overrides
        )


class WebhookEventFactory:
    """Factory para criar eventos de webhook de teste."""

    @staticmethod
    def create_webhook_event_data(**overrides) -> Dict[str, Any]:
        """Cria dados de evento de webhook."""
        return {
            "event_id": overrides.get("event_id", str(uuid4())),
            "event_type": overrides.get("event_type", fake.random_element([
                "ticket.created",
                "ticket.started",
                "ticket.completed",
                "ticket.failed",
                "ticket.compensated"
            ])),
            "ticket_id": overrides.get("ticket_id", f"ticket-{fake.uuid4()}"),
            "webhook_url": overrides.get("webhook_url", f"https://example.com/webhook/{fake.uuid4()}"),
            "timestamp": overrides.get("timestamp", int(datetime.now(timezone.utc).timestamp() * 1000)),
            "status": overrides.get("status", "pending"),
            "retry_count": overrides.get("retry_count", 0),
            "next_retry_at": overrides.get("next_retry_at", None),
            "error_message": overrides.get("error_message", None),
        }


class KafkaMessageFactory:
    """Factory para criar mensagens Kafka de teste."""

    @staticmethod
    def create_ticket_message(**overrides) -> Dict[str, Any]:
        """Cria mensagem Kafka de ticket."""
        ticket_data = TicketFactory.create_ticket_data(**overrides.get("ticket", {}))

        return {
            "key": overrides.get("key", ticket_data["ticket_id"]),
            "value": ticket_data,
            "topic": overrides.get("topic", "execution.tickets"),
            "partition": overrides.get("partition", 0),
            "offset": overrides.get("offset", 0),
        }

    @staticmethod
    def create_batch_messages(count: int, **overrides) -> List[Dict[str, Any]]:
        """Cria lote de mensagens Kafka."""
        return [
            KafkaMessageFactory.create_ticket_message(
                ticket=overrides.get("ticket", {}),
                **overrides
            )
            for _ in range(count)
        ]


def assert_ticket_valid(ticket_data: Dict[str, Any]) -> None:
    """
    Valida que dados de ticket são válidos.

    Args:
        ticket_data: Dados do ticket para validar

    Raises:
        AssertionError: Se dados inválidos
    """
    required_fields = [
        "ticket_id", "plan_id", "intent_id", "decision_id",
        "task_id", "task_type", "description", "status",
        "priority", "risk_band", "sla", "qos",
        "security_level", "created_at"
    ]

    for field in required_fields:
        assert field in ticket_data, f"Campo obrigatório ausente: {field}"

    # Validar status
    valid_statuses = ["PENDING", "RUNNING", "COMPLETED", "FAILED", "COMPENSATING", "COMPENSATED"]
    assert ticket_data["status"] in valid_statuses, f"Status inválido: {ticket_data['status']}"

    # Validar SLA
    assert "timeout_ms" in ticket_data["sla"]
    assert "max_retries" in ticket_data["sla"]

    # Validar QoS
    assert "delivery_mode" in ticket_data["qos"]
    assert "consistency" in ticket_data["qos"]
    assert "durability" in ticket_data["qos"]


def assert_webhook_event_valid(event_data: Dict[str, Any]) -> None:
    """
    Valida que dados de evento webhook são válidos.

    Args:
        event_data: Dados do evento para validar

    Raises:
        AssertionError: Se dados inválidos
    """
    required_fields = ["event_id", "event_type", "ticket_id", "webhook_url", "timestamp"]

    for field in required_fields:
        assert field in event_data, f"Campo obrigatório ausente: {field}"

    # Validar event_type
    valid_event_types = [
        "ticket.created", "ticket.started", "ticket.completed",
        "ticket.failed", "ticket.compensated"
    ]
    assert event_data["event_type"] in valid_event_types, f"Event type inválido: {event_data['event_type']}"

    # Validar URL
    assert event_data["webhook_url"].startswith("http"), f"URL inválida: {event_data['webhook_url']}"


# ===== Helpers para medição de performance =====

class PerformanceMetrics:
    """Helper para coletar métricas de performance durante testes."""

    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.operation_count = 0

    def start(self):
        """Inicia medição."""
        import time
        self.start_time = time.time()

    def stop(self):
        """Para medição."""
        import time
        self.end_time = time.time()

    def record_operation(self):
        """Registra operação."""
        self.operation_count += 1

    @property
    def duration_seconds(self) -> float:
        """Duração total em segundos."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0

    @property
    def throughput_ops_per_second(self) -> float:
        """Throughput em operações por segundo."""
        if self.duration_seconds > 0:
            return self.operation_count / self.duration_seconds
        return 0.0

    @property
    def avg_latency_ms(self) -> float:
        """Latência média em milissegundos."""
        if self.operation_count > 0:
            return (self.duration_seconds * 1000) / self.operation_count
        return 0.0

    def summary(self) -> Dict[str, Any]:
        """Retorna resumo das métricas."""
        return {
            "duration_seconds": self.duration_seconds,
            "operation_count": self.operation_count,
            "throughput_ops_per_second": self.throughput_ops_per_second,
            "avg_latency_ms": self.avg_latency_ms,
        }
