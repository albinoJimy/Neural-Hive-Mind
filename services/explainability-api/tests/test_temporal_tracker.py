"""
Testes para TemporalTracker.

Verifica operacoes de tracking temporal de decisoes e mudancas de senioridade.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class AsyncCursorMock:
    """Mock cursor MongoDB que suporta sort() e é async iterável."""

    def __init__(self, items):
        self.items = items
        self._iter = None  # Inicializado em __aiter__

    def sort(self, *args, **kwargs):
        """Mock sort - retorna self para encadeamento."""
        # Se sort direction é -1, ordenar descending por changed_at
        if args and len(args) > 1:
            field, direction = args
            if field == "changed_at" and direction == -1:
                self.items = sorted(self.items, key=lambda x: x.get("changed_at", ""), reverse=True)
        return self

    def limit(self, *args, **kwargs):
        """Mock limit - retorna self."""
        return self

    def __aiter__(self):
        # Criar iterador aqui para garantir ordem correta após sort()
        self._iter = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class AsyncIteratorMock:
    """Mock iterator for async for loops."""

    def __init__(self, items):
        self.items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.items)
        except StopIteration:
            raise StopAsyncIteration


def _create_mock_mongo_client(explainability_data=None, seniority_data=None):
    """Cria mock do MongoDB client para testes."""
    if explainability_data is None:
        explainability_data = []
    if seniority_data is None:
        seniority_data = []

    # Mock explainability_ledger collection
    explainability_collection = MagicMock()
    explainability_collection.find_one = AsyncMock()

    def create_explainability_cursor(*args, **kwargs):
        # Filtrar dados baseado na query
        filtered_data = list(explainability_data)

        if args and isinstance(args[0], dict):
            query = args[0]
            # Filtrar por plan_id
            if "plan_id" in query:
                filtered_data = [d for d in filtered_data if d.get("plan_id") == query["plan_id"]]
            # Filtrar por generated_at
            if "generated_at" in query and "$gte" in query["generated_at"]:
                cutoff = query["generated_at"]["$gte"]
                # Converter cutoff para ISO string se for datetime
                if isinstance(cutoff, datetime):
                    cutoff = cutoff.isoformat()
                filtered_data = [d for d in filtered_data if d.get("generated_at", "") >= cutoff]

        return AsyncCursorMock(filtered_data)

    explainability_collection.find = MagicMock(side_effect=create_explainability_cursor)

    # Mock seniority_history collection
    seniority_collection = MagicMock()

    def create_seniority_cursor(*args, **kwargs):
        filtered_data = list(seniority_data)

        if args and isinstance(args[0], dict):
            query = args[0]
            # Filtrar por specialist_id com $in
            if "specialist_id" in query and "$in" in query["specialist_id"]:
                specialist_list = query["specialist_id"]["$in"]
                filtered_data = [d for d in filtered_data if d.get("specialist_id") in specialist_list]
            # Filtrar por changed_at
            if "changed_at" in query and "$gte" in query["changed_at"]:
                cutoff = query["changed_at"]["$gte"]
                # Converter cutoff para ISO string se for datetime
                if isinstance(cutoff, datetime):
                    cutoff = cutoff.isoformat()
                filtered_data = [d for d in filtered_data if d.get("changed_at", "") >= cutoff]

        return AsyncCursorMock(filtered_data)

    seniority_collection.find = MagicMock(side_effect=create_seniority_cursor)

    # Mock database
    db = MagicMock()
    db.explainability_ledger = explainability_collection
    db.seniority_history = seniority_collection
    db.__getitem__.return_value = seniority_collection

    # Mock client
    client = MagicMock()
    client.__getitem__.return_value = db
    client.neural_hive = db

    return client, explainability_collection, seniority_collection


@pytest.fixture
def mongo_client():
    """Mock MongoDB client."""
    return _create_mock_mongo_client()[0]


@pytest.fixture
def tracker(mongo_client):
    """TemporalTracker instance."""
    from src.services.temporal_tracker import TemporalTracker
    return TemporalTracker(mongo_client)


class TestGetCurrentSession:
    """Testes de análise de sessão atual."""

    @pytest.mark.asyncio
    async def test_get_current_session_with_plan_id(self):
        """Testa análise de sessão com plan_id."""
        # Setup test data
        now = datetime.utcnow()
        plan_id = "plan_123"

        test_data = [
            {
                "_id": "dec_1",
                "decision_id": "decision_1",
                "plan_id": plan_id,
                "generated_at": (now - timedelta(hours=2)).isoformat(),
                "final_decision": {"decision": "approve"},
            },
            {
                "_id": "dec_2",
                "decision_id": "decision_2",
                "plan_id": plan_id,
                "generated_at": (now - timedelta(hours=1)).isoformat(),
                "final_decision": {"decision": "approve"},
            },
            {
                "_id": "dec_3",
                "decision_id": "decision_3",
                "plan_id": plan_id,
                "generated_at": now.isoformat(),
                "final_decision": {"decision": "reject"},
            },
        ]

        mongo_client, explainability_collection, _ = _create_mock_mongo_client(test_data)
        from src.services.temporal_tracker import TemporalTracker
        tracker_instance = TemporalTracker(mongo_client)

        # Configure find_one to return reference decision
        explainability_collection.find_one = AsyncMock(return_value=test_data[0])

        result = await tracker_instance.get_current_session("decision_1")

        assert result["session_id"] == plan_id
        assert result["decision_count"] == 3
        assert len(result["timeline"]) == 3
        assert result["first_decision"]["decision_id"] == "decision_1"
        assert result["last_decision"]["decision_id"] == "decision_3"
        assert result["duration_hours"] > 0

    @pytest.mark.asyncio
    async def test_get_current_session_reference_not_found(self):
        """Testa sessão quando decisão de referência não existe."""
        mongo_client, explainability_collection, _ = _create_mock_mongo_client()
        from src.services.temporal_tracker import TemporalTracker
        tracker_instance = TemporalTracker(mongo_client)

        explainability_collection.find_one = AsyncMock(return_value=None)

        result = await tracker_instance.get_current_session("nonexistent_decision")

        assert result["session_id"] is None
        assert result["decision_count"] == 0
        assert result["timeline"] == []
        assert result["duration_hours"] == 0.0

    @pytest.mark.asyncio
    async def test_get_current_session_without_plan_id(self):
        """Testa sessão quando decisão não tem plan_id."""
        test_data = [
            {
                "_id": "dec_1",
                "decision_id": "decision_1",
                "generated_at": datetime.utcnow().isoformat(),
                "final_decision": {"decision": "approve"},
            }
        ]

        mongo_client, explainability_collection, _ = _create_mock_mongo_client()
        from src.services.temporal_tracker import TemporalTracker
        tracker_instance = TemporalTracker(mongo_client)

        explainability_collection.find_one = AsyncMock(return_value=test_data[0])

        result = await tracker_instance.get_current_session("decision_1")

        # Usa decision_id como session_id quando não há plan_id
        assert result["session_id"] == "decision_1"
        assert result["decision_count"] == 0  # Nenhuma outra decisão


class TestGetWindowAnalysis:
    """Testes de análise de janela temporal."""

    @pytest.mark.asyncio
    async def test_get_window_analysis_7_days(self):
        """Testa análise de janela de 7 dias."""
        now = datetime.utcnow()

        test_data = [
            {
                "_id": "dec_1",
                "decision_id": "decision_1",
                "generated_at": (now - timedelta(days=1)).isoformat(),
                "final_decision": {"decision": "approve"},
            },
            {
                "_id": "dec_2",
                "decision_id": "decision_2",
                "generated_at": (now - timedelta(days=2)).isoformat(),
                "final_decision": {"decision": "reject"},
            },
            {
                "_id": "dec_3",
                "decision_id": "decision_3",
                "generated_at": (now - timedelta(days=5)).isoformat(),
                "final_decision": {"decision": "approve"},
            },
        ]

        mongo_client, _, _ = _create_mock_mongo_client(test_data)
        from src.services.temporal_tracker import TemporalTracker
        tracker_instance = TemporalTracker(mongo_client)

        result = await tracker_instance.get_window_analysis(days=7)

        assert result["window_days"] == 7
        assert result["decision_count"] == 3
        assert result["approve_count"] == 2
        assert result["reject_count"] == 1
        # approve_rate é arredondado para 3 casas decimais
        assert abs(result["approve_rate"] - 2/3) < 0.001
        assert len(result["daily_breakdown"]) == 3

    @pytest.mark.asyncio
    async def test_get_window_analysis_30_days(self):
        """Testa análise de janela de 30 dias."""
        now = datetime.utcnow()

        test_data = [
            {
                "_id": "dec_1",
                "decision_id": "decision_1",
                "generated_at": now.isoformat(),
                "final_decision": {"decision": "approve"},
            }
        ]

        mongo_client, _, _ = _create_mock_mongo_client(test_data)
        from src.services.temporal_tracker import TemporalTracker
        tracker_instance = TemporalTracker(mongo_client)

        result = await tracker_instance.get_window_analysis(days=30)

        assert result["window_days"] == 30
        assert result["decision_count"] == 1
        assert result["approve_count"] == 1
        assert result["reject_count"] == 0
        assert result["approve_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_get_window_analysis_empty(self):
        """Testa análise de janela vazia."""
        mongo_client, _, _ = _create_mock_mongo_client([])
        from src.services.temporal_tracker import TemporalTracker
        tracker_instance = TemporalTracker(mongo_client)

        result = await tracker_instance.get_window_analysis(days=7)

        assert result["window_days"] == 7
        assert result["decision_count"] == 0
        assert result["approve_count"] == 0
        assert result["reject_count"] == 0
        assert result["approve_rate"] == 0.0
        assert result["daily_breakdown"] == {}

    @pytest.mark.asyncio
    async def test_get_window_analysis_daily_breakdown(self):
        """Testa breakdown diário das decisões."""
        now = datetime.utcnow()

        test_data = [
            {
                "_id": "dec_1",
                "decision_id": "decision_1",
                "generated_at": (now - timedelta(days=1)).isoformat(),
                "final_decision": {"decision": "approve"},
            },
            {
                "_id": "dec_2",
                "decision_id": "decision_2",
                "generated_at": (now - timedelta(days=1)).isoformat(),
                "final_decision": {"decision": "reject"},
            },
            {
                "_id": "dec_3",
                "decision_id": "decision_3",
                "generated_at": now.isoformat(),
                "final_decision": {"decision": "approve"},
            },
        ]

        mongo_client, _, _ = _create_mock_mongo_client(test_data)
        from src.services.temporal_tracker import TemporalTracker
        tracker_instance = TemporalTracker(mongo_client)

        result = await tracker_instance.get_window_analysis(days=7)

        assert len(result["daily_breakdown"]) > 0
        # Verificar que os dias estão agregados
        total_daily = sum(result["daily_breakdown"].values())
        assert total_daily == 3


class TestGetSeniorityChanges:
    """Testes de mudanças de senioridade."""

    @pytest.mark.asyncio
    async def test_get_seniority_changes_recent(self):
        """Testa busca de mudanças recentes de senioridade."""
        now = datetime.utcnow()

        seniority_data = [
            {
                "_id": "sen_1",
                "specialist_id": "spec_1",
                "specialist_name": "Specialist 1",
                "domain": "BUSINESS",
                "previous_level": "mid_level",
                "new_level": "senior",
                "changed_at": (now - timedelta(days=5)).isoformat(),
            },
            {
                "_id": "sen_2",
                "specialist_id": "spec_2",
                "specialist_name": "Specialist 2",
                "domain": "TECHNICAL",
                "previous_level": "senior",
                "new_level": "expert",
                "changed_at": (now - timedelta(days=10)).isoformat(),
            },
        ]

        mongo_client, _, _ = _create_mock_mongo_client(seniority_data=seniority_data)
        from src.services.temporal_tracker import TemporalTracker
        tracker_instance = TemporalTracker(mongo_client)

        result = await tracker_instance.get_seniority_changes(
            specialists=["spec_1", "spec_2"],
            days=30
        )

        assert result["period_days"] == 30
        assert result["change_count"] == 2
        assert len(result["changes"]) == 2
        assert "spec_1" in result["specialists_with_changes"]
        assert "spec_2" in result["specialists_with_changes"]

    @pytest.mark.asyncio
    async def test_get_seniority_changes_no_changes(self):
        """Testa quando não há mudanças de senioridade."""
        mongo_client, _, _ = _create_mock_mongo_client(seniority_data=[])
        from src.services.temporal_tracker import TemporalTracker
        tracker_instance = TemporalTracker(mongo_client)

        result = await tracker_instance.get_seniority_changes(
            specialists=["spec_1", "spec_2"],
            days=30
        )

        assert result["period_days"] == 30
        assert result["change_count"] == 0
        assert result["changes"] == []
        assert result["specialists_with_changes"] == []

    @pytest.mark.asyncio
    async def test_get_seniority_changes_filtered_by_specialist(self):
        """Testa filtro por lista de especialistas."""
        now = datetime.utcnow()

        seniority_data = [
            {
                "_id": "sen_1",
                "specialist_id": "spec_1",
                "new_level": "senior",
                "changed_at": now.isoformat(),
            },
            {
                "_id": "sen_2",
                "specialist_id": "spec_3",  # Não está na lista
                "new_level": "expert",
                "changed_at": now.isoformat(),
            },
        ]

        # Criar mock que filtra por specialist_id
        def create_filtered_cursor(*args, **kwargs):
            filtered = [d for d in seniority_data if d.get("specialist_id") in ["spec_1", "spec_2"]]
            return AsyncCursorMock(filtered)

        mongo_client, _, seniority_collection = _create_mock_mongo_client(seniority_data=seniority_data)
        seniority_collection.find = MagicMock(side_effect=create_filtered_cursor)

        from src.services.temporal_tracker import TemporalTracker
        tracker_instance = TemporalTracker(mongo_client)

        result = await tracker_instance.get_seniority_changes(
            specialists=["spec_1", "spec_2"],
            days=30
        )

        # Apenas spec_1 deve estar nos resultados (spec_3 foi filtrado)
        assert result["change_count"] == 1
        assert result["changes"][0]["specialist_id"] == "spec_1"


class TestGetSeniorityDistribution:
    """Testes de distribuição de senioridade."""

    @pytest.mark.asyncio
    async def test_get_seniority_distribution_all_levels(self):
        """Testa distribuição de senioridade com todos os níveis."""
        now = datetime.utcnow()

        seniority_data = [
            {
                "_id": "sen_1",
                "specialist_id": "spec_1",
                "new_level": "trainee",
                "changed_at": now.isoformat(),
            },
            {
                "_id": "sen_2",
                "specialist_id": "spec_2",
                "new_level": "junior",
                "changed_at": now.isoformat(),
            },
            {
                "_id": "sen_3",
                "specialist_id": "spec_3",
                "new_level": "mid_level",
                "changed_at": now.isoformat(),
            },
            {
                "_id": "sen_4",
                "specialist_id": "spec_4",
                "new_level": "senior",
                "changed_at": now.isoformat(),
            },
            {
                "_id": "sen_5",
                "specialist_id": "spec_5",
                "new_level": "expert",
                "changed_at": now.isoformat(),
            },
        ]

        mongo_client, _, _ = _create_mock_mongo_client(seniority_data=seniority_data)
        from src.services.temporal_tracker import TemporalTracker
        tracker_instance = TemporalTracker(mongo_client)

        since = now - timedelta(days=30)
        result = await tracker_instance._get_seniority_distribution(since)

        assert result["total_count"] == 5
        assert result["by_level"]["trainee"] == 1
        assert result["by_level"]["junior"] == 1
        assert result["by_level"]["mid_level"] == 1
        assert result["by_level"]["senior"] == 1
        assert result["by_level"]["expert"] == 1
        assert result["percentages"]["trainee"] == 0.2

    @pytest.mark.asyncio
    async def test_get_seniority_distribution_with_duplicates(self):
        """Testa que mudanças recentes sobrescrevem antigas."""
        now = datetime.utcnow()

        seniority_data = [
            {
                "_id": "sen_1",
                "specialist_id": "spec_1",
                "new_level": "mid_level",
                "changed_at": (now - timedelta(days=10)).isoformat(),
            },
            {
                "_id": "sen_2",
                "specialist_id": "spec_1",
                "new_level": "senior",  # Promoção mais recente
                "changed_at": (now - timedelta(days=1)).isoformat(),
            },
        ]

        # Need to create ordered cursor (most recent first)
        sorted_data = sorted(seniority_data, key=lambda x: x.get("changed_at", ""), reverse=True)

        mongo_client, _, _ = _create_mock_mongo_client(seniority_data=sorted_data)
        from src.services.temporal_tracker import TemporalTracker
        tracker_instance = TemporalTracker(mongo_client)

        since = now - timedelta(days=30)
        result = await tracker_instance._get_seniority_distribution(since)

        # Deve contar apenas o nível mais recente (senior)
        assert result["total_count"] == 1
        assert result["by_level"]["senior"] == 1
        assert result["by_level"]["mid_level"] == 0

    @pytest.mark.asyncio
    async def test_get_seniority_distribution_empty(self):
        """Testa distribuição com dados vazios."""
        mongo_client, _, _ = _create_mock_mongo_client(seniority_data=[])
        from src.services.temporal_tracker import TemporalTracker
        tracker_instance = TemporalTracker(mongo_client)

        since = datetime.utcnow() - timedelta(days=30)
        result = await tracker_instance._get_seniority_distribution(since)

        assert result["total_count"] == 0
        assert all(v == 0 for v in result["by_level"].values())


class TestParseCursor:
    """Testes do helper _parse_cursor."""

    @pytest.mark.asyncio
    async def test_parse_cursor_removes_id(self):
        """Testa que _id é removido dos resultados."""
        test_data = [
            {
                "_id": "doc_123",
                "decision_id": "decision_1",
                "final_decision": {"decision": "approve"},
            }
        ]

        cursor = AsyncIteratorMock(test_data)

        mongo_client, _, _ = _create_mock_mongo_client()
        from src.services.temporal_tracker import TemporalTracker
        tracker_instance = TemporalTracker(mongo_client)

        results = await tracker_instance._parse_cursor(cursor)

        assert len(results) == 1
        assert "_id" not in results[0]
        assert results[0]["decision_id"] == "decision_1"

    @pytest.mark.asyncio
    async def test_parse_cursor_empty(self):
        """Testa cursor vazio."""
        cursor = AsyncIteratorMock([])

        mongo_client, _, _ = _create_mock_mongo_client()
        from src.services.temporal_tracker import TemporalTracker
        tracker_instance = TemporalTracker(mongo_client)

        results = await tracker_instance._parse_cursor(cursor)

        assert results == []

    @pytest.mark.asyncio
    async def test_parse_cursor_multiple_items(self):
        """Testa cursor com múltiplos itens."""
        test_data = [
            {"_id": "1", "decision_id": "d1"},
            {"_id": "2", "decision_id": "d2"},
            {"_id": "3", "decision_id": "d3"},
        ]

        cursor = AsyncIteratorMock(test_data)

        mongo_client, _, _ = _create_mock_mongo_client()
        from src.services.temporal_tracker import TemporalTracker
        tracker_instance = TemporalTracker(mongo_client)

        results = await tracker_instance._parse_cursor(cursor)

        assert len(results) == 3
        assert all("_id" not in r for r in results)
