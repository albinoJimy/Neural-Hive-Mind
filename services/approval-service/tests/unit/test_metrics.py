"""
Testes unitarios para metricas do Approval Service

Testa atualizacao de gauges e contadores.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from src.observability.metrics import NeuralHiveMetrics, approval_requests_pending_gauge


class TestNeuralHiveMetricsGauge:
    """Testes para update_pending_gauge"""

    def test_update_pending_gauge_without_mongodb_client(self):
        """Teste que gauge update e ignorado sem MongoDB client"""
        metrics = NeuralHiveMetrics(mongodb_client=None)

        # Deve executar sem erro
        metrics.update_pending_gauge()

    def test_update_pending_gauge_sets_mongodb_client(self):
        """Teste que set_mongodb_client configura cliente"""
        metrics = NeuralHiveMetrics()
        mock_client = MagicMock()

        metrics.set_mongodb_client(mock_client)

        assert metrics._mongodb_client == mock_client

    @pytest.mark.asyncio
    async def test_update_pending_gauge_queries_mongodb(self):
        """Teste que gauge update faz query no MongoDB"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.collection = mock_collection

        # Simula resultado da agregacao
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {'_id': 'high', 'count': 5},
            {'_id': 'critical', 'count': 2}
        ])
        mock_collection.aggregate.return_value = mock_cursor

        metrics = NeuralHiveMetrics(mongodb_client=mock_client)

        # Executa update
        metrics.update_pending_gauge()

        # Aguarda task async completar
        await asyncio.sleep(0.1)

        # Verifica que aggregate foi chamado com pipeline correto
        mock_collection.aggregate.assert_called_once()
        call_args = mock_collection.aggregate.call_args[0][0]
        assert call_args[0] == {'$match': {'status': 'pending'}}
        assert call_args[1] == {'$group': {'_id': '$risk_band', 'count': {'$sum': 1}}}

    @pytest.mark.asyncio
    async def test_update_pending_gauge_handles_empty_results(self):
        """Teste que gauge update lida com resultados vazios"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.collection = mock_collection

        # Simula resultado vazio
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_collection.aggregate.return_value = mock_cursor

        metrics = NeuralHiveMetrics(mongodb_client=mock_client)

        # Deve executar sem erro
        metrics.update_pending_gauge()

        # Aguarda task async completar
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_update_pending_gauge_handles_exception(self):
        """Teste que gauge update lida com excecoes gracefully"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.collection = mock_collection

        # Simula erro na query
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(side_effect=Exception('MongoDB error'))
        mock_collection.aggregate.return_value = mock_cursor

        metrics = NeuralHiveMetrics(mongodb_client=mock_client)

        # Deve executar sem propagar erro
        metrics.update_pending_gauge()

        # Aguarda task async completar
        await asyncio.sleep(0.1)


class TestNeuralHiveMetricsCounters:
    """Testes para contadores de metricas"""

    def test_increment_approval_requests_received_normalizes_enum(self):
        """Teste que risk_band enum e normalizado para string"""
        from src.models.approval import RiskBand

        metrics = NeuralHiveMetrics()

        # Deve executar sem erro com enum
        metrics.increment_approval_requests_received(
            risk_band=RiskBand.HIGH,
            is_destructive=True
        )

        # Deve executar sem erro com string
        metrics.increment_approval_requests_received(
            risk_band='medium',
            is_destructive=False
        )

    def test_increment_approvals_total_normalizes_enum(self):
        """Teste que risk_band enum e normalizado para string"""
        from src.models.approval import RiskBand

        metrics = NeuralHiveMetrics()

        # Deve executar sem erro com enum
        metrics.increment_approvals_total(
            decision='approved',
            risk_band=RiskBand.CRITICAL
        )

    def test_observe_time_to_decision_normalizes_enum(self):
        """Teste que risk_band enum e normalizado para string"""
        from src.models.approval import RiskBand

        metrics = NeuralHiveMetrics()

        # Deve executar sem erro com enum
        metrics.observe_time_to_decision(
            time_seconds=120.5,
            decision='approved',
            risk_band=RiskBand.HIGH
        )
