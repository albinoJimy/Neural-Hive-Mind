"""
Unit tests para o FeedbackSink (plano-Z transversal do loop OBSERVE→LEARN).

Spec: docs/specs/2026-06-22-fundacao-loop-learn — Fase 0 (Fundação).

O FeedbackSink é capability-agnostic: EXECUTE/GENERATE/MIGRATE emitem o MESMO
contrato (ExecutionFeedback) através do MESMO sink. Estes testes provam que a
Fundação é transversal (não acoplada a nenhuma capacidade), idempotente, e que
uma falha de persistência nunca propaga (o workflow não pode ficar refém de
telemetria).
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.models.execution_feedback import ExecutionFeedback
from src.observability.feedback_sink import FeedbackSink


def _make_mongo_client():
    """Cria um mongodb_client mock com db['execution_tickets'].update_one async."""
    collection = MagicMock()
    collection.update_one = AsyncMock()
    db = MagicMock()
    db.__getitem__.return_value = collection
    mongo_client = MagicMock()
    mongo_client.db = db
    return mongo_client, collection


def _feedback(**overrides):
    base = {
        "feedback_id": "t1:1700",
        "capability": "EXECUTE",
        "ticket_id": "t1",
        "plan_id": "p1",
        "status": "COMPLETED",
        "actual_duration_ms": 1500,
        "started_at": 100,
        "completed_at": 1600,
        "simulated": False,
        "feedback_persisted_at": 1700,
    }
    base.update(overrides)
    return ExecutionFeedback(**base)


class TestExecutionFeedbackModel:
    def test_simulated_defaults_to_false(self):
        fb = ExecutionFeedback(
            feedback_id="x",
            capability="EXECUTE",
            ticket_id="t",
            plan_id="p",
            status="COMPLETED",
            feedback_persisted_at=1,
        )
        assert fb.simulated is False

    def test_journey_id_optional_for_routing_hook(self):
        # gancho de Roteamento: preenchível depois pelo journey router, hoje opcional
        fb = _feedback(journey_id=None)
        assert fb.journey_id is None

    def test_carries_capability_hook(self):
        # gancho de Capacidade: o contrato identifica a capacidade emissora
        assert _feedback(capability="EXECUTE").capability == "EXECUTE"


class TestFeedbackSinkRecord:
    @pytest.mark.asyncio()
    async def test_persists_by_ticket_id_with_set(self):
        mongo, collection = _make_mongo_client()
        sink = FeedbackSink(mongo)

        await sink.record(_feedback())

        collection.update_one.assert_awaited_once()
        args, kwargs = collection.update_one.call_args
        flt, update = args[0], args[1]
        assert flt == {"ticket_id": "t1"}
        assert update["$set"]["actual_duration_ms"] == 1500
        assert update["$set"]["status"] == "COMPLETED"
        assert update["$set"]["result_simulated"] is False
        # update, nunca upsert — o documento do ticket já existe
        assert kwargs.get("upsert", False) is False

    @pytest.mark.asyncio()
    async def test_completed_at_persisted_as_bson_date(self):
        # No cluster, execution_tickets.completed_at/started_at são BSON Date.
        # O contrato ExecutionFeedback usa epoch millis (portável); o sink converte
        # para datetime ao gravar, para casar com o filtro do predictor.
        mongo, collection = _make_mongo_client()
        sink = FeedbackSink(mongo)

        await sink.record(_feedback(completed_at=1600, started_at=100))

        update = collection.update_one.call_args[0][1]
        assert isinstance(update["$set"]["completed_at"], datetime)
        assert isinstance(update["$set"]["started_at"], datetime)
        # actual_duration_ms NÃO é timestamp — permanece int
        assert isinstance(update["$set"]["actual_duration_ms"], int)

    @pytest.mark.asyncio()
    async def test_marks_simulated_for_green_false_guard(self):
        mongo, collection = _make_mongo_client()
        sink = FeedbackSink(mongo)

        await sink.record(_feedback(simulated=True))

        update = collection.update_one.call_args[0][1]
        assert update["$set"]["result_simulated"] is True

    @pytest.mark.asyncio()
    async def test_transversal_accepts_generate_without_change(self):
        # PROVA ARQUITETURAL: o sink aceita outra capacidade sem qualquer alteração
        # (Fundação transversal — encaixe de Capacidades sem reabrir a Fundação).
        mongo, collection = _make_mongo_client()
        sink = FeedbackSink(mongo)

        await sink.record(_feedback(capability="GENERATE"))

        update = collection.update_one.call_args[0][1]
        assert update["$set"]["capability"] == "GENERATE"

    @pytest.mark.asyncio()
    async def test_idempotent_uses_update_by_ticket_id(self):
        # 2ª chamada reaplica o mesmo $set por ticket_id — não duplica (at-least-once safe)
        mongo, collection = _make_mongo_client()
        sink = FeedbackSink(mongo)

        await sink.record(_feedback())
        await sink.record(_feedback())

        assert collection.update_one.await_count == 2
        for call in collection.update_one.call_args_list:
            assert call[0][0] == {"ticket_id": "t1"}

    @pytest.mark.asyncio()
    async def test_missing_ticket_id_does_not_touch_mongo(self):
        mongo, collection = _make_mongo_client()
        sink = FeedbackSink(mongo)

        await sink.record(_feedback(ticket_id=None))

        collection.update_one.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_persist_failure_does_not_propagate(self):
        # O workflow não pode ficar refém de telemetria: falha de Mongo é engolida.
        mongo, collection = _make_mongo_client()
        collection.update_one.side_effect = RuntimeError("mongo down")
        sink = FeedbackSink(mongo)

        # não deve levantar
        await sink.record(_feedback())
