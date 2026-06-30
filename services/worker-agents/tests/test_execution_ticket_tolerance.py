"""Testes do desserializador tolerante do ExecutionTicket (worker-agents) — Fase 2.

Worker e code-forge devem validar o MESMO contrato canónico (task_type MAIÚSCULAS,
priority enum string) e normalizar legado sem rejeitar:
- task_type minúsculo -> MAIÚSCULAS (inclui TRANSFORM, antes ausente do enum)
- priority int 1-10 -> enum (1-2 LOW, 3-5 NORMAL, 6-8 HIGH, 9-10 CRITICAL)
"""

import pytest

from src.models.execution_ticket import ExecutionTicket, TaskType


def _base_ticket(**overrides) -> dict:
    data = {
        "ticket_id": "ticket-0001",
        "plan_id": "plan-00001",
        "intent_id": "intent-001",
        "decision_id": "decision-1",
        "task_id": "task-0001",
        "task_type": "BUILD",
        "description": "desc",
        "status": "PENDING",
        "priority": "NORMAL",
        "risk_band": "low",
        "sla": {"deadline": 1782300000, "timeout_ms": 1000, "max_retries": 3},
        "qos": {
            "delivery_mode": "at-least-once",
            "consistency": "eventual",
            "durability": "persistent",
        },
        "created_at": 1782290000,
    }
    data.update(overrides)
    return data


def test_transform_in_enum():
    """TRANSFORM passa a existir no enum do worker (estava em falta)."""
    assert TaskType.TRANSFORM == "TRANSFORM"


class TestLegacyTaskTypeNormalization:
    @pytest.mark.parametrize(
        "legacy,expected",
        [("transform", "TRANSFORM"), ("query", "QUERY"), ("validate", "VALIDATE")],
    )
    def test_lowercase_task_type_normalized(self, legacy, expected):
        t = ExecutionTicket(**_base_ticket(task_type=legacy))
        assert t.task_type == expected

    def test_unknown_task_type_rejected(self):
        with pytest.raises(Exception):
            ExecutionTicket(**_base_ticket(task_type="bogus"))


class TestLegacyPriorityNormalization:
    @pytest.mark.parametrize(
        "legacy_int,expected",
        [(1, "LOW"), (5, "NORMAL"), (6, "HIGH"), (9, "CRITICAL")],
    )
    def test_int_priority_normalized(self, legacy_int, expected):
        t = ExecutionTicket(**_base_ticket(priority=legacy_int))
        assert t.priority == expected


class TestMixedLegacy:
    def test_lowercase_task_type_and_int_priority(self):
        t = ExecutionTicket(**_base_ticket(task_type="transform", priority=5))
        assert t.task_type == "TRANSFORM"
        assert t.priority == "NORMAL"
