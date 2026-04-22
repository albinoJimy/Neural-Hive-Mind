"""
Testes unitários para o modelo ExecutionTicket.

Cobre:
- Validação de campos (priority, metadata, dependencies, completed_at)
- Conversão Avro (to_avro_dict, from_avro_dict)
- Métodos utilitários (calculate_hash, is_expired, can_retry)
- Enums (TaskType, TicketStatus, Priority, RiskBand, SecurityLevel, etc.)
"""

# Configure path
import sys
from datetime import datetime
from pathlib import Path

import pytest

src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from src.models.execution_ticket import (
    SLA,
    Consistency,
    DeliveryMode,
    Durability,
    ExecutionTicket,
    Priority,
    QoS,
    RiskBand,
    SecurityLevel,
    TaskType,
    TicketStatus,
)


class TestEnums:
    """Testes para enums do ExecutionTicket."""

    def test_task_type_uppercase_values(self):
        """Testa valores em uppercase para TaskType."""
        assert TaskType.BUILD == "BUILD"
        assert TaskType.DEPLOY == "DEPLOY"
        assert TaskType.TEST == "TEST"
        assert TaskType.VALIDATE == "VALIDATE"
        assert TaskType.EXECUTE == "EXECUTE"
        assert TaskType.COMPENSATE == "COMPENSATE"
        assert TaskType.QUERY == "QUERY"
        assert TaskType.TRANSFORM == "TRANSFORM"

    def test_task_type_lowercase_legacy(self):
        """Testa valores legados em lowercase."""
        assert TaskType.query == "query"
        assert TaskType.transform == "transform"
        assert TaskType.validate_legacy == "validate"

    def test_ticket_status_values(self):
        """Testa valores de TicketStatus."""
        assert TicketStatus.PENDING == "PENDING"
        assert TicketStatus.RUNNING == "RUNNING"
        assert TicketStatus.COMPLETED == "COMPLETED"
        assert TicketStatus.FAILED == "FAILED"
        assert TicketStatus.COMPENSATING == "COMPENSATING"
        assert TicketStatus.COMPENSATED == "COMPENSATED"

    def test_priority_values(self):
        """Testa valores de Priority."""
        assert Priority.LOW == "LOW"
        assert Priority.NORMAL == "NORMAL"
        assert Priority.HIGH == "HIGH"
        assert Priority.CRITICAL == "CRITICAL"

    def test_risk_band_values(self):
        """Testa valores de RiskBand."""
        assert RiskBand.low == "low"
        assert RiskBand.medium == "medium"
        assert RiskBand.high == "high"
        assert RiskBand.critical == "critical"

    def test_security_level_values(self):
        """Testa valores de SecurityLevel."""
        assert SecurityLevel.PUBLIC == "PUBLIC"
        assert SecurityLevel.INTERNAL == "INTERNAL"
        assert SecurityLevel.CONFIDENTIAL == "CONFIDENTIAL"
        assert SecurityLevel.RESTRICTED == "RESTRICTED"


class TestSLA:
    """Testes para modelo SLA."""

    def test_sla_creation(self):
        """Testa criação de SLA."""
        sla = SLA(
            deadline=1234567890000,
            timeout_ms=30000,
            max_retries=3,
        )
        assert sla.deadline == 1234567890000
        assert sla.timeout_ms == 30000
        assert sla.max_retries == 3

    def test_sla_model_dump(self):
        """Testa serialização de SLA."""
        sla = SLA(
            deadline=1234567890000,
            timeout_ms=30000,
            max_retries=3,
        )
        data = sla.model_dump()
        assert data["deadline"] == 1234567890000
        assert data["timeout_ms"] == 30000
        assert data["max_retries"] == 3


class TestQoS:
    """Testes para modelo QoS."""

    def test_qos_creation(self):
        """Testa criação de QoS."""
        qos = QoS(
            delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            consistency=Consistency.STRONG,
            durability=Durability.PERSISTENT,
        )
        assert qos.delivery_mode == DeliveryMode.AT_LEAST_ONCE
        assert qos.consistency == Consistency.STRONG
        assert qos.durability == Durability.PERSISTENT


class TestExecutionTicketValidation:
    """Testes para validações do ExecutionTicket."""

    def test_priority_validation_int_to_enum(self):
        """Testa conversão de int para Priority enum."""
        ticket = ExecutionTicket(
            ticket_id="ticket-123",
            plan_id="plan-456",
            intent_id="intent-789",
            decision_id="decision-abc",
            task_id="task-1",
            task_type=TaskType.BUILD,
            description="Build task",
            dependencies=[],
            priority=1,  # Deve converter para LOW
            risk_band=RiskBand.low,
            sla=SLA(deadline=1234567890000, timeout_ms=30000, max_retries=3),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.STRONG,
                durability=Durability.PERSISTENT,
            ),
            required_capabilities=[],
            security_level=SecurityLevel.PUBLIC,
            created_at=1234567890000,
        )
        assert ticket.priority == Priority.LOW

    def test_priority_validation_int_2_to_low(self):
        """Testa que priority 2 converte para LOW."""
        ticket = ExecutionTicket(
            ticket_id="ticket-123",
            plan_id="plan-456",
            intent_id="intent-789",
            decision_id="decision-abc",
            task_id="task-1",
            task_type=TaskType.BUILD,
            description="Build task",
            dependencies=[],
            priority=2,
            risk_band=RiskBand.low,
            sla=SLA(deadline=1234567890000, timeout_ms=30000, max_retries=3),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.STRONG,
                durability=Durability.PERSISTENT,
            ),
            required_capabilities=[],
            security_level=SecurityLevel.PUBLIC,
            created_at=1234567890000,
        )
        assert ticket.priority == Priority.LOW

    def test_priority_validation_int_3_to_5_normal(self):
        """Testa que priority 3-5 converte para NORMAL."""
        for p in [3, 4, 5]:
            ticket = ExecutionTicket(
                ticket_id="ticket-123",
                plan_id="plan-456",
                intent_id="intent-789",
                decision_id="decision-abc",
                task_id="task-1",
                task_type=TaskType.BUILD,
                description="Build task",
                dependencies=[],
                priority=p,
                risk_band=RiskBand.low,
                sla=SLA(deadline=1234567890000, timeout_ms=30000, max_retries=3),
                qos=QoS(
                    delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                    consistency=Consistency.STRONG,
                    durability=Durability.PERSISTENT,
                ),
                required_capabilities=[],
                security_level=SecurityLevel.PUBLIC,
                created_at=1234567890000,
            )
            assert ticket.priority == Priority.NORMAL

    def test_priority_validation_int_6_to_8_high(self):
        """Testa que priority 6-8 converte para HIGH."""
        for p in [6, 7, 8]:
            ticket = ExecutionTicket(
                ticket_id="ticket-123",
                plan_id="plan-456",
                intent_id="intent-789",
                decision_id="decision-abc",
                task_id="task-1",
                task_type=TaskType.BUILD,
                description="Build task",
                dependencies=[],
                priority=p,
                risk_band=RiskBand.low,
                sla=SLA(deadline=1234567890000, timeout_ms=30000, max_retries=3),
                qos=QoS(
                    delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                    consistency=Consistency.STRONG,
                    durability=Durability.PERSISTENT,
                ),
                required_capabilities=[],
                security_level=SecurityLevel.PUBLIC,
                created_at=1234567890000,
            )
            assert ticket.priority == Priority.HIGH

    def test_priority_validation_int_9_to_10_critical(self):
        """Testa que priority 9-10 converte para CRITICAL."""
        for p in [9, 10]:
            ticket = ExecutionTicket(
                ticket_id="ticket-123",
                plan_id="plan-456",
                intent_id="intent-789",
                decision_id="decision-abc",
                task_id="task-1",
                task_type=TaskType.BUILD,
                description="Build task",
                dependencies=[],
                priority=p,
                risk_band=RiskBand.low,
                sla=SLA(deadline=1234567890000, timeout_ms=30000, max_retries=3),
                qos=QoS(
                    delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                    consistency=Consistency.STRONG,
                    durability=Durability.PERSISTENT,
                ),
                required_capabilities=[],
                security_level=SecurityLevel.PUBLIC,
                created_at=1234567890000,
            )
            assert ticket.priority == Priority.CRITICAL

    def test_priority_validation_string(self):
        """Testa que string priority é convertida corretamente."""
        ticket = ExecutionTicket(
            ticket_id="ticket-123",
            plan_id="plan-456",
            intent_id="intent-789",
            decision_id="decision-abc",
            task_id="task-1",
            task_type=TaskType.BUILD,
            description="Build task",
            dependencies=[],
            priority="high",
            risk_band=RiskBand.low,
            sla=SLA(deadline=1234567890000, timeout_ms=30000, max_retries=3),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.STRONG,
                durability=Durability.PERSISTENT,
            ),
            required_capabilities=[],
            security_level=SecurityLevel.PUBLIC,
            created_at=1234567890000,
        )
        assert ticket.priority == Priority.HIGH

    def test_metadata_validation_cleanup(self):
        """Testa que metadados não-string são limpos."""
        ticket = ExecutionTicket(
            ticket_id="ticket-123",
            plan_id="plan-456",
            intent_id="intent-789",
            decision_id="decision-abc",
            task_id="task-1",
            task_type=TaskType.BUILD,
            description="Build task",
            dependencies=[],
            priority=Priority.NORMAL,
            risk_band=RiskBand.low,
            sla=SLA(deadline=1234567890000, timeout_ms=30000, max_retries=3),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.STRONG,
                durability=Durability.PERSISTENT,
            ),
            required_capabilities=[],
            security_level=SecurityLevel.PUBLIC,
            created_at=1234567890000,
            metadata={
                "string_key": "value",
                "int_key": 123,
                "list_key": [1, 2, 3],
                "dict_key": {"nested": "value"},
                "none_key": None,
            },
        )
        # Valores não-string devem ser convertidos para JSON string
        assert ticket.metadata["string_key"] == "value"
        assert ticket.metadata["int_key"] == "123"
        assert "list_key" in ticket.metadata
        assert ticket.metadata["none_key"] == ""

    def test_dependencies_validation_no_self_reference(self):
        """Testa que ticket não pode depender de si mesmo."""
        with pytest.raises(ValueError, match="não pode depender de si mesmo"):
            ExecutionTicket(
                ticket_id="ticket-123",
                plan_id="plan-456",
                intent_id="intent-789",
                decision_id="decision-abc",
                task_id="task-1",
                task_type=TaskType.BUILD,
                description="Build task",
                dependencies=["ticket-123"],  # Auto-referência
                priority=Priority.NORMAL,
                risk_band=RiskBand.low,
                sla=SLA(deadline=1234567890000, timeout_ms=30000, max_retries=3),
                qos=QoS(
                    delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                    consistency=Consistency.STRONG,
                    durability=Durability.PERSISTENT,
                ),
                required_capabilities=[],
                security_level=SecurityLevel.PUBLIC,
                created_at=1234567890000,
            )

    def test_completed_at_validation(self):
        """Testa que completed_at deve ser maior que started_at."""
        with pytest.raises(ValueError, match="deve ser maior que started_at"):
            ExecutionTicket(
                ticket_id="ticket-123",
                plan_id="plan-456",
                intent_id="intent-789",
                decision_id="decision-abc",
                task_id="task-1",
                task_type=TaskType.BUILD,
                description="Build task",
                dependencies=[],
                priority=Priority.NORMAL,
                risk_band=RiskBand.low,
                sla=SLA(deadline=1234567890000, timeout_ms=30000, max_retries=3),
                qos=QoS(
                    delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                    consistency=Consistency.STRONG,
                    durability=Durability.PERSISTENT,
                ),
                required_capabilities=[],
                security_level=SecurityLevel.PUBLIC,
                created_at=1234567890000,
                started_at=10000,
                completed_at=9000,  # Menor que started_at
            )


class TestExecutionTicketMethods:
    """Testes para métodos do ExecutionTicket."""

    def test_to_avro_dict(self):
        """Testa conversão para dicionário Avro."""
        now_ms = int(datetime.now().timestamp() * 1000)
        ticket = ExecutionTicket(
            ticket_id="ticket-123",
            plan_id="plan-456",
            intent_id="intent-789",
            decision_id="decision-abc",
            task_id="task-1",
            task_type=TaskType.BUILD,
            description="Build task",
            dependencies=[],
            priority=Priority.HIGH,
            risk_band=RiskBand.low,
            sla=SLA(deadline=now_ms + 300000, timeout_ms=30000, max_retries=3),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.STRONG,
                durability=Durability.PERSISTENT,
            ),
            required_capabilities=[],
            security_level=SecurityLevel.PUBLIC,
            created_at=now_ms,
        )

        avro_dict = ticket.to_avro_dict()

        assert avro_dict["ticket_id"] == "ticket-123"
        assert avro_dict["task_type"] == "BUILD"
        assert avro_dict["priority"] == "HIGH"
        assert avro_dict["risk_band"] == "low"
        assert "sla" in avro_dict
        assert "qos" in avro_dict

    def test_from_avro_dict(self):
        """Testa criação a partir de dicionário Avro."""
        now_ms = int(datetime.now().timestamp() * 1000)
        data = {
            "ticket_id": "ticket-123",
            "plan_id": "plan-456",
            "intent_id": "intent-789",
            "decision_id": "decision-abc",
            "task_id": "task-1",
            "task_type": "BUILD",
            "description": "Build task",
            "dependencies": [],
            "status": "PENDING",
            "priority": "HIGH",
            "risk_band": "low",
            "sla": {
                "deadline": now_ms + 300000,
                "timeout_ms": 30000,
                "max_retries": 3,
            },
            "qos": {
                "delivery_mode": "AT_LEAST_ONCE",
                "consistency": "STRONG",
                "durability": "PERSISTENT",
            },
            "required_capabilities": [],
            "security_level": "PUBLIC",
            "created_at": now_ms,
        }

        ticket = ExecutionTicket.from_avro_dict(data)

        assert ticket.ticket_id == "ticket-123"
        assert ticket.task_type == TaskType.BUILD
        assert ticket.priority == Priority.HIGH
        assert ticket.sla.timeout_ms == 30000

    def test_calculate_hash(self):
        """Testa cálculo de hash SHA-256."""
        ticket = ExecutionTicket(
            ticket_id="ticket-123",
            plan_id="plan-456",
            intent_id="intent-789",
            decision_id="decision-abc",
            task_id="task-1",
            task_type=TaskType.BUILD,
            description="Build task",
            dependencies=[],
            priority=Priority.NORMAL,
            risk_band=RiskBand.low,
            sla=SLA(deadline=1234567890000, timeout_ms=30000, max_retries=3),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.STRONG,
                durability=Durability.PERSISTENT,
            ),
            required_capabilities=[],
            security_level=SecurityLevel.PUBLIC,
            created_at=1234567890000,
        )

        hash_value = ticket.calculate_hash()

        # Hash deve ter 64 caracteres hexadecimais (SHA-256)
        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_calculate_hash_deterministic(self):
        """Testa que hash é determinístico."""
        data = {
            "ticket_id": "ticket-123",
            "plan_id": "plan-456",
            "intent_id": "intent-789",
            "decision_id": "decision-abc",
            "task_id": "task-1",
            "task_type": TaskType.BUILD,
            "description": "Build task",
            "dependencies": [],
            "priority": Priority.NORMAL,
            "risk_band": RiskBand.low,
            "sla": SLA(deadline=1234567890000, timeout_ms=30000, max_retries=3),
            "qos": QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.STRONG,
                durability=Durability.PERSISTENT,
            ),
            "required_capabilities": [],
            "security_level": SecurityLevel.PUBLIC,
            "created_at": 1234567890000,
        }

        ticket1 = ExecutionTicket(**data)
        ticket2 = ExecutionTicket(**data)

        assert ticket1.calculate_hash() == ticket2.calculate_hash()

    def test_is_expired_true(self):
        """Testa detecção de ticket expirado."""
        past_ms = int(datetime.now().timestamp() * 1000) - 100000
        ticket = ExecutionTicket(
            ticket_id="ticket-123",
            plan_id="plan-456",
            intent_id="intent-789",
            decision_id="decision-abc",
            task_id="task-1",
            task_type=TaskType.BUILD,
            description="Build task",
            dependencies=[],
            priority=Priority.NORMAL,
            risk_band=RiskBand.low,
            sla=SLA(deadline=past_ms, timeout_ms=30000, max_retries=3),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.STRONG,
                durability=Durability.PERSISTENT,
            ),
            required_capabilities=[],
            security_level=SecurityLevel.PUBLIC,
            created_at=past_ms - 10000,
        )

        assert ticket.is_expired() is True

    def test_is_expired_false(self):
        """Testa detecção de ticket não expirado."""
        future_ms = int(datetime.now().timestamp() * 1000) + 100000
        ticket = ExecutionTicket(
            ticket_id="ticket-123",
            plan_id="plan-456",
            intent_id="intent-789",
            decision_id="decision-abc",
            task_id="task-1",
            task_type=TaskType.BUILD,
            description="Build task",
            dependencies=[],
            priority=Priority.NORMAL,
            risk_band=RiskBand.low,
            sla=SLA(deadline=future_ms, timeout_ms=30000, max_retries=3),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.STRONG,
                durability=Durability.PERSISTENT,
            ),
            required_capabilities=[],
            security_level=SecurityLevel.PUBLIC,
            created_at=future_ms - 10000,
        )

        assert ticket.is_expired() is False

    def test_can_retry_true(self):
        """Testa que retry é possível quando count < max_retries."""
        ticket = ExecutionTicket(
            ticket_id="ticket-123",
            plan_id="plan-456",
            intent_id="intent-789",
            decision_id="decision-abc",
            task_id="task-1",
            task_type=TaskType.BUILD,
            description="Build task",
            dependencies=[],
            priority=Priority.NORMAL,
            risk_band=RiskBand.low,
            sla=SLA(deadline=9999999999999, timeout_ms=30000, max_retries=3),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.STRONG,
                durability=Durability.PERSISTENT,
            ),
            required_capabilities=[],
            security_level=SecurityLevel.PUBLIC,
            created_at=1234567890000,
            retry_count=2,
        )

        assert ticket.can_retry() is True

    def test_can_retry_false(self):
        """Testa que retry não é possível quando count == max_retries."""
        ticket = ExecutionTicket(
            ticket_id="ticket-123",
            plan_id="plan-456",
            intent_id="intent-789",
            decision_id="decision-abc",
            task_id="task-1",
            task_type=TaskType.BUILD,
            description="Build task",
            dependencies=[],
            priority=Priority.NORMAL,
            risk_band=RiskBand.low,
            sla=SLA(deadline=9999999999999, timeout_ms=30000, max_retries=3),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.STRONG,
                durability=Durability.PERSISTENT,
            ),
            required_capabilities=[],
            security_level=SecurityLevel.PUBLIC,
            created_at=1234567890000,
            retry_count=3,
        )

        assert ticket.can_retry() is False

    def test_calculate_sla_remaining_seconds_positive(self):
        """Testa cálculo de tempo restante positivo."""
        future_ms = int(datetime.now().timestamp() * 1000) + 60000  # 60 segundos
        ticket = ExecutionTicket(
            ticket_id="ticket-123",
            plan_id="plan-456",
            intent_id="intent-789",
            decision_id="decision-abc",
            task_id="task-1",
            task_type=TaskType.BUILD,
            description="Build task",
            dependencies=[],
            priority=Priority.NORMAL,
            risk_band=RiskBand.low,
            sla=SLA(deadline=future_ms, timeout_ms=30000, max_retries=3),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.STRONG,
                durability=Durability.PERSISTENT,
            ),
            required_capabilities=[],
            security_level=SecurityLevel.PUBLIC,
            created_at=future_ms - 10000,
        )

        remaining = ticket.calculate_sla_remaining_seconds()
        assert remaining > 50  # ~60 segundos

    def test_calculate_sla_remaining_seconds_negative(self):
        """Testa cálculo de tempo restante negativo (expirado)."""
        past_ms = int(datetime.now().timestamp() * 1000) - 60000  # -60 segundos
        ticket = ExecutionTicket(
            ticket_id="ticket-123",
            plan_id="plan-456",
            intent_id="intent-789",
            decision_id="decision-abc",
            task_id="task-1",
            task_type=TaskType.BUILD,
            description="Build task",
            dependencies=[],
            priority=Priority.NORMAL,
            risk_band=RiskBand.low,
            sla=SLA(deadline=past_ms, timeout_ms=30000, max_retries=3),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.STRONG,
                durability=Durability.PERSISTENT,
            ),
            required_capabilities=[],
            security_level=SecurityLevel.PUBLIC,
            created_at=past_ms - 10000,
        )

        remaining = ticket.calculate_sla_remaining_seconds()
        assert remaining < 0

    def test_is_sla_critical_true(self):
        """Testa detecção de SLA crítico."""
        now_ms = int(datetime.now().timestamp() * 1000)
        ticket = ExecutionTicket(
            ticket_id="ticket-123",
            plan_id="plan-456",
            intent_id="intent-789",
            decision_id="decision-abc",
            task_id="task-1",
            task_type=TaskType.BUILD,
            description="Build task",
            dependencies=[],
            priority=Priority.NORMAL,
            risk_band=RiskBand.low,
            sla=SLA(deadline=now_ms + 10000, timeout_ms=10000, max_retries=3),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.STRONG,
                durability=Durability.PERSISTENT,
            ),
            required_capabilities=[],
            security_level=SecurityLevel.PUBLIC,
            created_at=now_ms - 10000,
            started_at=now_ms - 9000,  # 90% do tempo consumido
        )

        # Com threshold 0.8 (80%), deve ser crítico
        assert ticket.is_sla_critical(0.8) is True

    def test_is_sla_critical_false_not_started(self):
        """Testa que SLA não é crítico se não iniciado."""
        ticket = ExecutionTicket(
            ticket_id="ticket-123",
            plan_id="plan-456",
            intent_id="intent-789",
            decision_id="decision-abc",
            task_id="task-1",
            task_type=TaskType.BUILD,
            description="Build task",
            dependencies=[],
            priority=Priority.NORMAL,
            risk_band=RiskBand.low,
            sla=SLA(deadline=9999999999999, timeout_ms=30000, max_retries=3),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.STRONG,
                durability=Durability.PERSISTENT,
            ),
            required_capabilities=[],
            security_level=SecurityLevel.PUBLIC,
            created_at=1234567890000,
            started_at=None,
        )

        assert ticket.is_sla_critical() is False
