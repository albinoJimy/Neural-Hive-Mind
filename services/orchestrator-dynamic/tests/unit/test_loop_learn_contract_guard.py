"""
Guarda anti-regressão do contrato cruzado do loop OBSERVE→LEARN.

Spec: docs/specs/2026-06-22-fundacao-loop-learn — Fase 3 (Anti-regressão).

O loop só fecha se o FeedbackSink (escritor) e o DurationPredictor (leitor)
concordarem nos NOMES dos campos. Uma renomeação num lado quebraria o loop
silenciosamente (sem erro, mas o predictor voltaria a ficar cego). Este teste
cruza os dois lados e falha se o contrato divergir.

Também consolida as duas guardas de regressão da spec:
- tipo: o filtro temporal do predictor usa epoch millis (int), não datetime;
- anti-verde-falso: o predictor exclui result_simulated.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.ml.duration_predictor import DurationPredictor
from src.models.execution_feedback import ExecutionFeedback
from src.observability.feedback_sink import FeedbackSink

# Campos de que o leitor (predictor) depende e que o escritor (sink) tem de gravar.
SHARED_CONTRACT_FIELDS = {"completed_at", "actual_duration_ms", "result_simulated"}


async def _sink_set_keys() -> set:
    collection = MagicMock()
    collection.update_one = AsyncMock()
    db = MagicMock()
    db.__getitem__.return_value = collection
    mongo = MagicMock()
    mongo.db = db

    await FeedbackSink(mongo).record(
        ExecutionFeedback(
            feedback_id="t:1",
            feedback_persisted_at=1,
            capability="EXECUTE",
            ticket_id="t",
            plan_id="p",
            status="COMPLETED",
            actual_duration_ms=10,
            completed_at=20,
            simulated=False,
        )
    )
    return set(collection.update_one.call_args[0][1]["$set"].keys())


async def _predictor_filter() -> dict:
    config = MagicMock()
    config.ml_training_window_days = 30
    config.ml_min_training_samples = 10
    collection = MagicMock()
    collection.count_documents = AsyncMock(return_value=0)
    db = MagicMock()
    db.__getitem__.return_value = collection
    mongo = MagicMock()
    mongo.db = db

    await DurationPredictor(
        config, mongo, MagicMock(), MagicMock()
    )._check_training_data_availability()
    return collection.count_documents.call_args[0][0]


class TestLoopContractGuard:
    @pytest.mark.asyncio()
    async def test_sink_writes_every_field_predictor_reads(self):
        sink_keys = await _sink_set_keys()
        predictor_filter = await _predictor_filter()
        predictor_keys = set(predictor_filter.keys())

        # o escritor grava todos os campos partilhados de que o leitor depende
        assert sink_keys >= SHARED_CONTRACT_FIELDS
        # o leitor filtra exatamente por esses campos partilhados
        assert predictor_keys >= SHARED_CONTRACT_FIELDS

    @pytest.mark.asyncio()
    async def test_predictor_time_filter_is_epoch_millis_not_datetime(self):
        flt = await _predictor_filter()
        # guarda de tipo: regressão para datetime cegaria o predictor
        assert isinstance(flt["completed_at"]["$gte"], int)

    @pytest.mark.asyncio()
    async def test_predictor_excludes_simulated_from_training(self):
        flt = await _predictor_filter()
        assert flt["result_simulated"] == {"$ne": True}
