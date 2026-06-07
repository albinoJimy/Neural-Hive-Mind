"""
Testes unitarios para coercao de datas no MongoDBClient (BUG P1-stats).

Cobre:
- _coerce_to_datetime: conversao de string ISO -> datetime, passthrough de
  datetime/None e tolerancia a strings invalidas.
- save_approval_request / update_approval_decision: gravam datas como datetime BSON.
- get_approval_stats: pipeline defensivo usa $toDate, tolerando docs legados
  com datas em string sem voltar a falhar.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.clients.mongodb_client import MongoDBClient, _coerce_to_datetime

from neural_hive_approval_common import ApprovalDecision, ApprovalRequest, RiskBand


class TestCoerceToDatetime:
    """Testes do helper de coercao de datas"""

    def test_string_iso_convertida_para_datetime(self):
        result = _coerce_to_datetime("2026-06-07T12:30:00")
        assert isinstance(result, datetime)
        assert result == datetime(2026, 6, 7, 12, 30, 0)

    def test_string_iso_com_sufixo_z(self):
        result = _coerce_to_datetime("2026-06-07T12:30:00Z")
        assert isinstance(result, datetime)
        assert result == datetime(2026, 6, 7, 12, 30, 0, tzinfo=timezone.utc)

    def test_datetime_passa_inalterado(self):
        value = datetime(2026, 6, 7, 12, 30, 0)
        assert _coerce_to_datetime(value) is value

    def test_none_passa_inalterado(self):
        assert _coerce_to_datetime(None) is None

    def test_string_invalida_mantida(self):
        # Pipeline e defensiva; helper nao deve lancar excecao
        assert _coerce_to_datetime("nao-e-uma-data") == "nao-e-uma-data"


def _make_client_with_mock_collection() -> MongoDBClient:
    """Cria MongoDBClient com collection mockada (AsyncMock) para escrita."""
    settings = MagicMock()
    client = MongoDBClient(settings)
    client.collection = AsyncMock()
    return client


class TestEscritaCoerceDatas:
    """Garante que novas escritas gravam datas como datetime BSON"""

    @pytest.mark.asyncio()
    async def test_save_approval_request_grava_datetime(self):
        client = _make_client_with_mock_collection()

        approval = ApprovalRequest(
            plan_id="plan-001",
            intent_id="intent-001",
            risk_score=0.9,
            risk_band=RiskBand.HIGH,
            is_destructive=True,
            requested_at=datetime(2026, 6, 7, 10, 0, 0),
            cognitive_plan={"plan_id": "plan-001", "tasks": []},
        )

        await client.save_approval_request(approval)

        client.collection.insert_one.assert_awaited_once()
        document = client.collection.insert_one.call_args.args[0]
        assert isinstance(document["requested_at"], datetime)
        # approved_at e None neste cenario e deve permanecer None
        assert document["approved_at"] is None

    @pytest.mark.asyncio()
    async def test_update_approval_decision_grava_datetime(self):
        client = _make_client_with_mock_collection()
        client.collection.update_one.return_value = MagicMock(modified_count=1)

        decision = ApprovalDecision(
            plan_id="plan-001",
            decision="approved",
            approved_by="user@example.com",
            approved_at=datetime(2026, 6, 7, 11, 0, 0),
        )

        await client.update_approval_decision("plan-001", decision)

        client.collection.update_one.assert_awaited_once()
        update_doc = client.collection.update_one.call_args.args[1]["$set"]
        assert isinstance(update_doc["approved_at"], datetime)


class TestPipelineStatsDefensivo:
    """Garante que get_approval_stats nao falha com datas string (legado)"""

    @pytest.mark.asyncio()
    async def test_pipeline_usa_to_date(self):
        client = _make_client_with_mock_collection()

        # Mock do cursor de agregacao
        aggregate_cursor = MagicMock()
        aggregate_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "status_counts": [{"_id": "approved", "count": 2}],
                    "risk_band_pending": [],
                    "avg_approval_time": [{"_id": None, "avg": 60000}],
                }
            ]
        )
        client.collection.aggregate = MagicMock(return_value=aggregate_cursor)

        result = await client.get_approval_stats()

        # Verifica que o resultado e processado sem erro
        assert result.approved_count == 2
        assert result.avg_approval_time_seconds == 60.0  # 60000 ms -> 60 s

        # Verifica que o pipeline aplica $toDate antes do $subtract (defensivo)
        pipeline = client.collection.aggregate.call_args.args[0]
        avg_stage = pipeline[0]["$facet"]["avg_approval_time"]
        project_stage = next(s for s in avg_stage if "$project" in s)
        subtract_args = project_stage["$project"]["approval_time"]["$subtract"]
        assert subtract_args[0] == {"$toDate": "$approved_at"}
        assert subtract_args[1] == {"$toDate": "$requested_at"}

    @pytest.mark.asyncio()
    async def test_stats_vazio_retorna_defaults(self):
        client = _make_client_with_mock_collection()
        aggregate_cursor = MagicMock()
        aggregate_cursor.to_list = AsyncMock(return_value=[])
        client.collection.aggregate = MagicMock(return_value=aggregate_cursor)

        result = await client.get_approval_stats()

        assert result.pending_count == 0
        assert result.approved_count == 0
        assert result.rejected_count == 0
        assert result.avg_approval_time_seconds is None
        assert result.by_risk_band == {}
