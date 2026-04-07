"""
Testes para ScoutOrchestrator.

TDD: Testes escritos antes da implementação.
Espec: @.agent-os/specs/2026-03-17-gaps-05-scout-agents/
"""

import asyncio
import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timezone

# Import com skip automático se módulo não disponível
ScoutOrchestrator = pytest.importorskip("src.orchestration.scout_orchestrator").ScoutOrchestrator


class TestScoutOrchestratorInitialization:
    """Testes de inicialização do ScoutOrchestrator."""

    def test_orchestrator_initialization(self):
        """Testa que o orchestrator é inicializado corretamente."""
        mock_kafka_producer = AsyncMock()
        mock_mongo_client = AsyncMock()

        orchestrator = ScoutOrchestrator(
            scout_agent_id="scout-1",
            kafka_producer=mock_kafka_producer,
            mongo_client=mock_mongo_client,
        )

        assert orchestrator.scout_agent_id == "scout-1"
        assert orchestrator.kafka_producer == mock_kafka_producer
        assert orchestrator.mongo_client == mock_mongo_client

    def test_orchestrator_default_timeout(self):
        """Testa que timeout padrão é 30s."""
        mock_kafka_producer = AsyncMock()
        mock_mongo_client = AsyncMock()

        orchestrator = ScoutOrchestrator(
            scout_agent_id="scout-1",
            kafka_producer=mock_kafka_producer,
            mongo_client=mock_mongo_client,
        )

        assert orchestrator.default_timeout_ms == 30000

    def test_orchestrator_custom_timeout(self):
        """Testa que timeout customizado é configurado."""
        mock_kafka_producer = AsyncMock()
        mock_mongo_client = AsyncMock()

        orchestrator = ScoutOrchestrator(
            scout_agent_id="scout-1",
            kafka_producer=mock_kafka_producer,
            mongo_client=mock_mongo_client,
            default_timeout_ms=45000,
        )

        assert orchestrator.default_timeout_ms == 45000


class TestCoordinateExploration:
    """Testes do método coordinate_exploration."""

    @pytest.fixture
    def mock_scouts(self):
        """Mock de scouts disponíveis."""
        return {
            "pattern_matcher": AsyncMock(),
            "code_searcher": AsyncMock(),
            "dependency_analyzer": AsyncMock(),
        }

    @pytest.fixture
    def orchestrator(self, mock_scouts):
        """Orchestrator configurado com scouts mockados."""
        mock_kafka_producer = AsyncMock()
        mock_mongo_client = AsyncMock()

        orchestrator = ScoutOrchestrator(
            scout_agent_id="scout-1",
            kafka_producer=mock_kafka_producer,
            mongo_client=mock_mongo_client,
        )
        orchestrator.available_scouts = mock_scouts
        return orchestrator

    @pytest.mark.asyncio
    async def test_coordinate_exploration_deploys_all_scouts(self, orchestrator, mock_scouts):
        """Testa que todos os scouts são deployados por padrão."""
        mock_scouts["pattern_matcher"].explore = AsyncMock(return_value={"patterns": []})
        mock_scouts["code_searcher"].explore = AsyncMock(return_value={"solutions": []})
        mock_scouts["dependency_analyzer"].explore = AsyncMock(return_value={"deps": []})

        result = await orchestrator.coordinate_exploration(
            plan_id="plan-1", intent_text="Implementar API de usuários"
        )

        # Aguardar completar
        await asyncio.sleep(0.1)

        assert mock_scouts["pattern_matcher"].explore.called
        assert mock_scouts["code_searcher"].explore.called
        assert mock_scouts["dependency_analyzer"].explore.called

    @pytest.mark.asyncio
    async def test_coordinate_exploration_deploys_specific_scouts(self, orchestrator, mock_scouts):
        """Testa que scouts específicos são deployados quando solicitado."""
        mock_scouts["pattern_matcher"].explore = AsyncMock(return_value={"patterns": []})
        mock_scouts["code_searcher"].explore = AsyncMock(return_value={"solutions": []})

        result = await orchestrator.coordinate_exploration(
            plan_id="plan-1",
            intent_text="Implementar API de usuários",
            scouts=["pattern_matcher", "code_searcher"],
        )

        # Aguardar completar
        await asyncio.sleep(0.1)

        assert mock_scouts["pattern_matcher"].explore.called
        assert mock_scouts["code_searcher"].explore.called
        assert not mock_scouts["dependency_analyzer"].explore.called

    @pytest.mark.asyncio
    async def test_coordinate_exploration_returns_exploration_id(self, orchestrator, mock_scouts):
        """Testa que retorna exploration_id único."""
        mock_scouts["pattern_matcher"].explore.return_value = {"patterns": []}

        result = await orchestrator.coordinate_exploration(
            plan_id="plan-1", intent_text="Implementar API"
        )

        assert "exploration_id" in result
        assert result["exploration_id"].startswith("scout-exp-")

    @pytest.mark.asyncio
    async def test_coordinate_exploration_with_timeout(self, orchestrator, mock_scouts):
        """Testa que explorações com scouts que falham são marcadas corretamente."""

        # Scout que retorna erro
        async def failing_explore(*args, **kwargs):
            raise RuntimeError("Scout timeout simulado")

        mock_scouts["pattern_matcher"].explore = failing_explore

        result = await orchestrator.coordinate_exploration(
            plan_id="plan-1",
            intent_text="Implementar API",
            scouts=["pattern_matcher"],
            timeout_ms=5000,  # Timeout alto para não interferir
        )

        # Aguardar processamento
        await asyncio.sleep(0.2)

        status = await orchestrator.get_exploration_status(result["exploration_id"])

        # Exploração deve completar (mesmo com erro no scout)
        assert status["status"] in ["completed", "failed"]


class TestAggregateResults:
    """Testes do método aggregate_results."""

    @pytest.fixture
    def orchestrator(self):
        """Orchestrator configurado."""
        mock_kafka_producer = AsyncMock()
        mock_mongo_client = AsyncMock()

        orchestrator = ScoutOrchestrator(
            scout_agent_id="scout-1",
            kafka_producer=mock_kafka_producer,
            mongo_client=mock_mongo_client,
        )
        return orchestrator

    def test_aggregate_results_combines_multiple_outputs(self, orchestrator):
        """Testa que combina resultados de múltiplos scouts."""
        scout_results = {
            "pattern_matcher": {"patterns": [{"name": "repository", "occurrences": 5}]},
            "code_searcher": {"solutions": [{"approach": "FastAPI", "confidence": 0.9}]},
        }

        result = orchestrator.aggregate_results(scout_results)

        assert "patterns_discovered" in result
        assert "solutions_found" in result
        assert len(result["patterns_discovered"]) == 1
        assert len(result["solutions_found"]) == 1

    def test_aggregate_results_deduplicates_similar_findings(self, orchestrator):
        """Testa deduplicação de descobertas similares."""
        scout_results = {
            "pattern_matcher": {
                "patterns": [{"name": "repository", "occurrences": 1, "locations": ["service/a"]}]
            },
            "code_searcher": {
                "patterns": [{"name": "repository", "occurrences": 1, "locations": ["service/a"]}]
            },
        }

        result = orchestrator.aggregate_results(scout_results)

        # Deve deduplicar
        assert (
            len([p for p in result.get("patterns_discovered", []) if p["name"] == "repository"])
            == 1
        )

    def test_aggregate_results_calculates_confidence_scores(self, orchestrator):
        """Testa cálculo de confidence scores agregados."""
        scout_results = {"scout_a": {"confidence": 0.8}, "scout_b": {"confidence": 0.6}}

        result = orchestrator.aggregate_results(scout_results)

        assert "aggregate_confidence" in result
        assert abs(result["aggregate_confidence"] - 0.7) < 0.01


class TestPublishKafkaEvents:
    """Testes do método publish_kafka_events."""

    @pytest.fixture
    def orchestrator(self):
        """Orchestrator configurado."""
        mock_kafka_producer = AsyncMock()
        mock_mongo_client = AsyncMock()

        orchestrator = ScoutOrchestrator(
            scout_agent_id="scout-1",
            kafka_producer=mock_kafka_producer,
            mongo_client=mock_mongo_client,
        )
        return orchestrator

    @pytest.mark.asyncio
    async def test_publish_started_event(self, orchestrator):
        """Testa publicação de evento started."""
        await orchestrator.publish_kafka_events(
            exploration_id="scout-exp-1", event_type="started", plan_id="plan-1"
        )

        orchestrator.kafka_producer.publish.assert_called_once()
        call_args = orchestrator.kafka_producer.publish.call_args
        assert "started" in str(call_args)

    @pytest.mark.asyncio
    async def test_publish_completed_event(self, orchestrator):
        """Testa publicação de evento completed."""
        await orchestrator.publish_kafka_events(
            exploration_id="scout-exp-1",
            event_type="completed",
            plan_id="plan-1",
            results={"solutions": []},
        )

        orchestrator.kafka_producer.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_failed_event_on_error(self, orchestrator):
        """Testa publicação de evento failed em caso de erro."""
        await orchestrator.publish_kafka_events(
            exploration_id="scout-exp-1",
            event_type="failed",
            plan_id="plan-1",
            error="Timeout exceeded",
        )

        orchestrator.kafka_producer.publish.assert_called_once()


class TestGetExplorationStatus:
    """Testes do método get_exploration_status."""

    @pytest.fixture
    def orchestrator(self):
        """Orchestrator configurado."""
        mock_kafka_producer = AsyncMock()
        mock_mongo_client = AsyncMock()
        # Mock find_exploration to return None for unknown IDs
        mock_mongo_client.find_exploration = AsyncMock(return_value=None)

        orchestrator = ScoutOrchestrator(
            scout_agent_id="scout-1",
            kafka_producer=mock_kafka_producer,
            mongo_client=mock_mongo_client,
        )
        return orchestrator

    @pytest.mark.asyncio
    async def test_get_status_returns_running_exploration(self, orchestrator):
        """Testa consulta de exploração em andamento."""
        orchestrator.active_explorations = {
            "scout-exp-1": {"status": "running", "started_at": datetime.now(timezone.utc)}
        }

        status = await orchestrator.get_exploration_status("scout-exp-1")

        assert status["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_status_returns_completed_exploration(self, orchestrator):
        """Testa consulta de exploração completada."""
        orchestrator.completed_explorations = {
            "scout-exp-1": {"status": "completed", "results": {"solutions": []}}
        }

        status = await orchestrator.get_exploration_status("scout-exp-1")

        assert status["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_status_returns_none_for_unknown(self, orchestrator):
        """Testa consulta de exploração inexistente."""
        status = await orchestrator.get_exploration_status("unknown-id-xyz")

        assert status is None
