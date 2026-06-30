"""Testes do desserializador tolerante do ExecutionTicket (code-forge) — Fase 2.

O code-forge consome `execution.tickets` (partilhado com worker-agents). Antes da
Fase 2 da spec j3-build-generate, `ExecutionTicket(**data)` rejeitava (Pydantic enum
estrito) tickets legados com `task_type` minúsculo (ex.: 'transform') ou `priority`
inteiro (ex.: 5), enviando-os para DLQ (`message_deserialization_error`).

O contrato canónico é `task_type` enum MAIÚSCULAS e `priority` enum string
{LOW,NORMAL,HIGH,CRITICAL}. O modelo passa a NORMALIZAR legado (sem rejeitar):
- task_type string -> UPPER
- priority int -> enum (1-2 LOW, 3-5 NORMAL, 6-8 HIGH, 9-10 CRITICAL); string -> UPPER

Valores genuinamente inválidos (desconhecidos) continuam a falhar (anti-verde-falso).
"""

import pytest

from src.models.execution_ticket import ExecutionTicket


def _base_ticket(**overrides) -> dict:
    """Ticket canónico mínimo válido; overrides substituem campos."""
    data = {
        "ticket_id": "t-1",
        "plan_id": "p-1",
        "task_type": "BUILD",
        "status": "PENDING",
        "priority": "NORMAL",
        "risk_band": "low",
        "sla": {
            "deadline": "2026-06-24T12:00:00+00:00",
            "timeout_ms": 1000,
            "max_retries": 3,
        },
        "qos": {
            "delivery_mode": "AT_LEAST_ONCE",
            "consistency": "EVENTUAL",
            "durability": "PERSISTENT",
        },
        "security_level": "INTERNAL",
        "created_at": "2026-06-24T11:00:00+00:00",
    }
    data.update(overrides)
    return data


class TestCanonical:
    def test_canonical_ticket_ok(self):
        t = ExecutionTicket(**_base_ticket(task_type="BUILD", priority="HIGH"))
        # use_enum_values=True -> guarda o .value (string)
        assert t.task_type == "BUILD"
        assert t.priority == "HIGH"


class TestLegacyTaskTypeNormalization:
    @pytest.mark.parametrize(
        "legacy,expected",
        [
            ("transform", "TRANSFORM"),
            ("query", "QUERY"),
            ("validate", "VALIDATE"),
            ("build", "BUILD"),
            ("Deploy", "DEPLOY"),
        ],
    )
    def test_lowercase_task_type_is_normalized(self, legacy, expected):
        t = ExecutionTicket(**_base_ticket(task_type=legacy))
        assert t.task_type == expected

    def test_unknown_task_type_still_rejected(self):
        """Valor desconhecido NÃO é silenciosamente aceite (anti-verde-falso)."""
        with pytest.raises(Exception):
            ExecutionTicket(**_base_ticket(task_type="bogus_type"))


class TestLegacyPriorityNormalization:
    @pytest.mark.parametrize(
        "legacy_int,expected",
        [
            (1, "LOW"),
            (2, "LOW"),
            (3, "NORMAL"),
            (5, "NORMAL"),
            (6, "HIGH"),
            (8, "HIGH"),
            (9, "CRITICAL"),
            (10, "CRITICAL"),
        ],
    )
    def test_int_priority_is_normalized(self, legacy_int, expected):
        t = ExecutionTicket(**_base_ticket(priority=legacy_int))
        assert t.priority == expected

    def test_lowercase_priority_string_is_normalized(self):
        t = ExecutionTicket(**_base_ticket(priority="high"))
        assert t.priority == "HIGH"

    def test_invalid_priority_string_still_rejected(self):
        with pytest.raises(Exception):
            ExecutionTicket(**_base_ticket(priority="urgent"))


class TestMixedLegacyTicket:
    def test_lowercase_task_type_and_int_priority_accepted(self):
        """Caso real do DLQ: task_type='transform' + priority=5 -> aceite e normalizado."""
        t = ExecutionTicket(**_base_ticket(task_type="transform", priority=5))
        assert t.task_type == "TRANSFORM"
        assert t.priority == "NORMAL"
