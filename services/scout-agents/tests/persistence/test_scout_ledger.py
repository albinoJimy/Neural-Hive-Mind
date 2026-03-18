"""
Testes para ScoutLedger.

TDD: Testes escritos antes da implementação.
Espec: GAPS-05 Scout Agents
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock
from datetime import datetime, timedelta
from typing import Dict, List

# Import com skip automático se módulo não disponível
ScoutLedger = pytest.importorskip('src.persistence.scout_ledger').ScoutLedger


@pytest.fixture
def mock_collection():
    """Mock de coleção MongoDB para testes."""
    return AsyncMock()


@pytest.fixture
def ledger(mock_collection):
    """Ledger com collection mockada."""
    mock_mongo = AsyncMock()
    ledger = ScoutLedger(mongo_client=mock_mongo)
    ledger._test_collection = mock_collection
    return ledger


class TestScoutLedgerInitialization:
    """Testes de inicialização do ScoutLedger."""

    def test_ledger_initialization(self):
        """Testa que o ledger é inicializado corretamente."""
        mock_mongo = AsyncMock()
        ledger = ScoutLedger(mongo_client=mock_mongo)

        assert ledger is not None
        assert ledger.mongo_client == mock_mongo

    def test_ledger_default_collection_name(self):
        """Testa nome padrão da coleção."""
        mock_mongo = AsyncMock()
        ledger = ScoutLedger(mongo_client=mock_mongo)

        assert ledger.collection_name == 'scout_explorations'

    def test_ledger_custom_collection_name(self):
        """Testa nome customizado da coleção."""
        mock_mongo = AsyncMock()
        ledger = ScoutLedger(
            mongo_client=mock_mongo,
            collection_name='custom_explorations'
        )

        assert ledger.collection_name == 'custom_explorations'


class TestSaveExploration:
    """Testes do método save_exploration."""

    @pytest.mark.asyncio
    async def test_save_exploration_creates_document(self, ledger, mock_collection):
        """Testa que save cria documento no MongoDB."""
        exploration_data = {
            'exploration_id': 'scout-exp-1',
            'plan_id': 'plan-1',
            'intent_text': 'Implementar API',
            'status': 'started',
            'scouts_deployed': ['pattern_matcher', 'code_searcher'],
            'started_at': datetime.utcnow()
        }

        mock_result = MagicMock()
        mock_result.upserted_id = '507f1f77bcf86cd799439011'
        mock_collection.update_one = AsyncMock(return_value=mock_result)

        result = await ledger.save_exploration(exploration_data)

        assert result['exploration_id'] == 'scout-exp-1'

    @pytest.mark.asyncio
    async def test_save_exploration_with_results(self, ledger, mock_collection):
        """Testa save com resultados de scouts."""
        exploration_data = {
            'exploration_id': 'scout-exp-2',
            'plan_id': 'plan-2',
            'status': 'completed',
            'results': {
                'patterns': [{'name': 'repository', 'count': 5}],
                'recommendations': []
            }
        }

        mock_result = MagicMock()
        mock_result.upserted_id = None  # Update, não insert
        mock_result.modified_count = 1
        mock_collection.update_one = AsyncMock(return_value=mock_result)

        result = await ledger.save_exploration(exploration_data)

        assert result['status'] == 'completed'
        assert 'results' in result


class TestGetExploration:
    """Testes do método get_exploration."""

    @pytest.mark.asyncio
    async def test_get_existing_exploration(self, ledger, mock_collection):
        """Testa recuperação de exploração existente."""
        exploration_id = 'scout-exp-1'

        mock_doc = {
            '_id': '507f1f77bcf86cd799439011',
            'exploration_id': exploration_id,
            'status': 'completed'
        }
        mock_collection.find_one = AsyncMock(return_value=mock_doc)

        result = await ledger.get_exploration(exploration_id)

        assert result is not None
        assert result['exploration_id'] == exploration_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_exploration(self, ledger, mock_collection):
        """Testa recuperação de exploração inexistente."""
        mock_collection.find_one = AsyncMock(return_value=None)

        result = await ledger.get_exploration('nonexistent-id')

        assert result is None


class TestListExplorations:
    """Testes do método list_explorations."""

    @pytest.mark.asyncio
    async def test_list_all_explorations(self, ledger, mock_collection):
        """Testa listagem de todas as explorações."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {'exploration_id': 'exp-1', 'status': 'completed'},
            {'exploration_id': 'exp-2', 'status': 'running'}
        ])
        mock_cursor.limit = Mock(return_value=mock_cursor)
        mock_cursor.skip = Mock(return_value=mock_cursor)
        mock_cursor.sort = Mock(return_value=mock_cursor)
        mock_collection.find = Mock(return_value=mock_cursor)

        result = await ledger.list_explorations()

        assert len(result) == 2
        assert result[0]['exploration_id'] == 'exp-1'

    @pytest.mark.asyncio
    async def test_list_with_limit(self, ledger, mock_collection):
        """Testa listagem com limite."""
        mock_cursor = AsyncMock()
        mock_cursor.limit = Mock(return_value=mock_cursor)
        mock_cursor.skip = Mock(return_value=mock_cursor)
        mock_cursor.sort = Mock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=[
            {'exploration_id': 'exp-1'},
            {'exploration_id': 'exp-2'}
        ])
        mock_collection.find = Mock(return_value=mock_cursor)

        result = await ledger.list_explorations(limit=10)

        mock_cursor.limit.assert_called_once_with(10)


class TestUpdateExplorationStatus:
    """Testes do método update_exploration_status."""

    @pytest.mark.asyncio
    async def test_update_status_to_completed(self, ledger, mock_collection):
        """Testa atualização de status para completed."""
        exploration_id = 'scout-exp-1'

        mock_result = MagicMock()
        mock_result.modified_count = 1
        mock_collection.update_one = AsyncMock(return_value=mock_result)

        result = await ledger.update_exploration_status(
            exploration_id,
            'completed'
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_update_status_with_results(self, ledger, mock_collection):
        """Testa atualização com resultados."""
        exploration_id = 'scout-exp-1'

        mock_result = MagicMock()
        mock_result.modified_count = 1
        mock_collection.update_one = AsyncMock(return_value=mock_result)

        results = {'patterns': [], 'recommendations': []}
        result = await ledger.update_exploration_status(
            exploration_id,
            'completed',
            results=results
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_false(self, ledger, mock_collection):
        """Testa update de exploração inexistente."""
        mock_result = MagicMock()
        mock_result.modified_count = 0
        mock_collection.update_one = AsyncMock(return_value=mock_result)

        result = await ledger.update_exploration_status(
            'nonexistent',
            'completed'
        )

        assert result is False


class TestDeleteExploration:
    """Testes do método delete_exploration."""

    @pytest.mark.asyncio
    async def test_delete_existing_exploration(self, ledger, mock_collection):
        """Testa deleção de exploração existente."""
        mock_result = MagicMock()
        mock_result.deleted_count = 1
        mock_collection.delete_one = AsyncMock(return_value=mock_result)

        result = await ledger.delete_exploration('scout-exp-1')

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, ledger, mock_collection):
        """Testa deleção de exploração inexistente."""
        mock_result = MagicMock()
        mock_result.deleted_count = 0
        mock_collection.delete_one = AsyncMock(return_value=mock_result)

        result = await ledger.delete_exploration('nonexistent')

        assert result is False


class TestGetExplorationStats:
    """Testes do método get_exploration_stats."""

    @pytest.mark.asyncio
    async def test_get_overall_stats(self, ledger, mock_collection):
        """Testa obtenção de estatísticas gerais."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {'_id': 'completed', 'count': 10},
            {'_id': 'running', 'count': 3},
            {'_id': 'failed', 'count': 1}
        ])
        mock_collection.aggregate = Mock(return_value=mock_cursor)

        stats = await ledger.get_exploration_stats()

        assert stats['total'] == 14
        assert stats['by_status']['completed'] == 10

    @pytest.mark.asyncio
    async def test_get_stats_for_plan(self, ledger, mock_collection):
        """Testa estatísticas filtradas por plano."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {'_id': 'completed', 'count': 5}
        ])
        mock_collection.aggregate = Mock(return_value=mock_cursor)

        stats = await ledger.get_exploration_stats(plan_id='plan-1')

        assert stats['total'] == 5
        assert stats['plan_id'] == 'plan-1'


class TestCleanupOldExplorations:
    """Testes do método cleanup_old_explorations."""

    @pytest.mark.asyncio
    async def test_cleanup_explorations_older_than_days(self, ledger, mock_collection):
        """Testa cleanup de explorações antigas."""
        mock_result = MagicMock()
        mock_result.deleted_count = 5
        mock_collection.delete_many = AsyncMock(return_value=mock_result)

        result = await ledger.cleanup_old_explorations(days_older_than=30)

        assert result == 5

    @pytest.mark.asyncio
    async def test_cleanup_only_completed_explorations(self, ledger, mock_collection):
        """Testa cleanup apenas de explorações completadas."""
        mock_result = MagicMock()
        mock_result.deleted_count = 3
        mock_collection.delete_many = AsyncMock(return_value=mock_result)

        result = await ledger.cleanup_old_explorations(
            days_older_than=30,
            status='completed'
        )

        assert result == 3


class TestQueryExplorations:
    """Testes de consultas complexas."""

    @pytest.mark.asyncio
    async def test_query_by_date_range(self, ledger, mock_collection):
        """Testa consulta por intervalo de datas."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {'exploration_id': 'exp-1', 'created_at': datetime.utcnow()}
        ])
        mock_cursor.limit = Mock(return_value=mock_cursor)
        mock_cursor.sort = Mock(return_value=mock_cursor)
        mock_collection.find = Mock(return_value=mock_cursor)

        start_date = datetime.utcnow() - timedelta(days=7)
        end_date = datetime.utcnow()

        result = await ledger.query_explorations(
            start_date=start_date,
            end_date=end_date
        )

        mock_collection.find.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_by_scouts_used(self, ledger, mock_collection):
        """Testa consulta por scouts utilizados."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {'exploration_id': 'exp-1', 'scouts_deployed': ['pattern_matcher']}
        ])
        mock_cursor.limit = Mock(return_value=mock_cursor)
        mock_cursor.sort = Mock(return_value=mock_cursor)
        mock_collection.find = Mock(return_value=mock_cursor)

        result = await ledger.query_explorations(
            scouts_deployed=['pattern_matcher']
        )

        assert len(result) == 1
