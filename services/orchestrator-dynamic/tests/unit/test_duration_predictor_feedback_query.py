"""
Unit tests para o leitor LEARN — contrato de query do DurationPredictor.

Spec: docs/specs/2026-06-22-fundacao-loop-learn — Fase 2 (Leitor LEARN).

Dois bugs de contrato a fechar:
1. completed_at é gravado como epoch millis (int), mas o predictor filtrava com
   datetime — `$gte` entre tipos BSON distintos nunca casa. O filtro tem de usar
   epoch millis (int).
2. Execuções simuladas (result_simulated=True) têm de ser EXCLUÍDAS do treino
   (anti-verde-falso), senão o modelo aprende durações falsas.

Estes testes verificam o contrato da query Mongo em ambos os pontos de leitura.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.ml.duration_predictor import DurationPredictor


def _config():
    config = MagicMock()
    config.ml_training_window_days = 30
    config.ml_min_training_samples = 10
    config.ml_use_clickhouse_for_features = False
    return config


class TestAvailabilityQueryContract:
    @pytest.mark.asyncio()
    async def test_uses_epoch_millis_and_excludes_simulated(self):
        collection = MagicMock()
        collection.count_documents = AsyncMock(return_value=42)
        db = MagicMock()
        db.__getitem__.return_value = collection
        mongo = MagicMock()
        mongo.db = db

        predictor = DurationPredictor(_config(), mongo, MagicMock(), MagicMock())
        has_sufficient, count = await predictor._check_training_data_availability()

        assert count == 42
        flt = collection.count_documents.call_args[0][0]
        # tipo: completed_at é BSON Date no cluster → filtro tem de usar datetime
        assert isinstance(flt["completed_at"]["$gte"], datetime)
        # anti-verde-falso: exclui simulados do treino
        assert flt["result_simulated"] == {"$ne": True}


class TestTrainQueryContract:
    @pytest.mark.asyncio()
    async def test_train_uses_datetime_and_excludes_simulated(self):
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=[])  # 0 tickets → early return
        collection = MagicMock()
        collection.find = MagicMock(return_value=cursor)
        db = MagicMock()
        db.__getitem__.return_value = collection
        mongo = MagicMock()
        mongo.db = db

        # clickhouse_client=None → cai direto no Mongo find
        predictor = DurationPredictor(_config(), mongo, MagicMock(), MagicMock())
        result = await predictor.train_model()

        assert result["promoted"] is False  # early return (sem dados)
        flt = collection.find.call_args[0][0]
        assert isinstance(flt["completed_at"]["$gte"], datetime)
        assert flt["result_simulated"] == {"$ne": True}
