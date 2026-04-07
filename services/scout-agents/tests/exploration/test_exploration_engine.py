"""Testes para ExplorationEngine."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from collections import deque

from src.engine.exploration_engine import ExplorationEngine
from src.models.raw_event import RawEvent
from src.models.scout_signal import ChannelType
from neural_hive_domain import UnifiedDomain


@pytest.fixture
def mock_settings():
    """Mock settings."""
    settings = Mock()
    settings.detection.curiosity_decay_factor = 0.8
    settings.detection.max_signals_per_minute = 100
    settings.detection.curiosity_threshold = 0.5
    settings.detection.confidence_threshold = 0.6
    settings.detection.relevance_threshold = 0.4
    settings.detection.risk_threshold = 0.7
    return settings


@pytest.fixture
def exploration_engine(mock_settings):
    """Fixture para ExplorationEngine."""
    with patch("src.engine.exploration_engine.get_settings", return_value=mock_settings):
        with patch("src.engine.exploration_engine.SignalDetector"):
            with patch("src.engine.exploration_engine.KafkaSignalProducer"):
                with patch("src.engine.exploration_engine.MemoryLayerClient"):
                    with patch("src.engine.exploration_engine.PheromoneClient"):
                        with patch("src.engine.exploration_engine.CuriosityCalculator"):
                            with patch("src.engine.exploration_engine.FileSignalDetector"):
                                engine = ExplorationEngine("scout-123")
                                yield engine


@pytest.fixture
def sample_raw_event():
    """RawEvent de exemplo."""
    return RawEvent(
        event_id="event-123",
        event_type="code_change",
        source="scout-agent",
        timestamp=datetime.now(),
        payload={
            "file_path": "src/test.py",
            "change_type": "modified",
            "lines_added": 10,
            "lines_removed": 5,
        },
        metadata={"trace_id": "trace-123", "span_id": "span-123"},
    )


class TestExplorationEngineInit:
    """Testes de inicialização."""

    def test_init_creates_engine(self, mock_settings):
        """Testa criação do engine."""
        with patch("src.engine.exploration_engine.get_settings", return_value=mock_settings):
            with patch("src.engine.exploration_engine.SignalDetector"):
                with patch("src.engine.exploration_engine.KafkaSignalProducer"):
                    with patch("src.engine.exploration_engine.MemoryLayerClient"):
                        with patch("src.engine.exploration_engine.PheromoneClient"):
                            with patch("src.engine.exploration_engine.CuriosityCalculator"):
                                with patch("src.engine.exploration_engine.FileSignalDetector"):
                                    engine = ExplorationEngine("scout-123")

                                    assert engine.scout_agent_id == "scout-123"
                                    assert engine._is_running is False
                                    assert engine.stats["processed"] == 0
                                    assert len(engine.signal_queue) == 0

    def test_stats_initialization(self, mock_settings):
        """Testa que estatísticas são inicializadas corretamente."""
        with patch("src.engine.exploration_engine.get_settings", return_value=mock_settings):
            with patch("src.engine.exploration_engine.SignalDetector"):
                with patch("src.engine.exploration_engine.KafkaSignalProducer"):
                    with patch("src.engine.exploration_engine.MemoryLayerClient"):
                        with patch("src.engine.exploration_engine.PheromoneClient"):
                            with patch("src.engine.exploration_engine.CuriosityCalculator"):
                                with patch("src.engine.exploration_engine.FileSignalDetector"):
                                    engine = ExplorationEngine("scout-123")

                                    expected_keys = {
                                        "processed",
                                        "detected",
                                        "published",
                                        "discarded",
                                        "rate_limited",
                                        "files_scanned",
                                        "high_activity_detected",
                                    }
                                    assert set(engine.stats.keys()) == expected_keys


class TestStartStop:
    """Testes de start/stop."""

    @pytest.mark.asyncio
    async def test_start_initializes_components(self, exploration_engine):
        """Testa que start inicializa componentes."""
        exploration_engine.kafka_producer.start = AsyncMock()
        exploration_engine.memory_client.start = AsyncMock()
        exploration_engine.pheromone_client.start = AsyncMock()

        await exploration_engine.start()

        assert exploration_engine._is_running is True
        exploration_engine.kafka_producer.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_stops_components(self, exploration_engine):
        """Testa que stop para componentes."""
        exploration_engine._is_running = True
        exploration_engine.kafka_producer.stop = AsyncMock()
        exploration_engine.memory_client.stop = AsyncMock()
        exploration_engine.pheromone_client.stop = AsyncMock()

        await exploration_engine.stop()

        assert exploration_engine._is_running is False


class TestProcessEvent:
    """Testes de process_event."""

    @pytest.mark.asyncio
    async def test_process_event_when_not_running(self, exploration_engine, sample_raw_event):
        """Testa processamento quando engine não está rodando."""
        result = await exploration_engine.process_event(
            sample_raw_event, UnifiedDomain.CODEBASE, ChannelType.CORE
        )

        assert result is None
        assert exploration_engine.stats["processed"] == 1

    @pytest.mark.asyncio
    async def test_process_event_no_signal_detected(self, exploration_engine, sample_raw_event):
        """Testa quando nenhum sinal é detectado."""
        exploration_engine._is_running = True
        exploration_engine.detector.detect = AsyncMock(return_value=None)

        result = await exploration_engine.process_event(
            sample_raw_event, UnifiedDomain.CODEBASE, ChannelType.CORE
        )

        assert result is None
        assert exploration_engine.stats["processed"] == 1

    @pytest.mark.asyncio
    async def test_process_event_signal_detected(self, exploration_engine, sample_raw_event):
        """Testa quando sinal é detectado."""
        exploration_engine._is_running = True

        # Mock signal
        mock_signal = Mock()
        mock_signal.signal_id = "signal-123"
        mock_signal.should_publish = Mock(return_value=True)
        mock_signal.curiosity_score = 0.8
        mock_signal.confidence = 0.7
        mock_signal.relevance_score = 0.6
        mock_signal.risk_score = 0.3

        exploration_engine.detector.detect = AsyncMock(return_value=mock_signal)
        exploration_engine._publish_signal_internal = AsyncMock()

        result = await exploration_engine.process_event(
            sample_raw_event, UnifiedDomain.CODEBASE, ChannelType.CORE
        )

        assert result is not None
        assert exploration_engine.stats["detected"] == 1


class TestRateLimiting:
    """Testes de rate limiting."""

    @pytest.mark.asyncio
    async def test_check_rate_limit_within_limit(self, exploration_engine):
        """Testa rate limit dentro do permitido."""
        exploration_engine.published_signals = deque()

        result = exploration_engine._check_rate_limit()

        assert result is True

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self, exploration_engine):
        """Testa rate limit excedido."""
        # Preencher com 100 sinais no último minuto
        now = datetime.now()
        exploration_engine.published_signals = deque(
            [now - timedelta(seconds=i) for i in range(100)]
        )

        result = exploration_engine._check_rate_limit()

        assert result is False


class TestStats:
    """Testes de estatísticas."""

    @pytest.mark.asyncio
    async def test_get_stats(self, exploration_engine):
        """Testa obtenção de estatísticas."""
        exploration_engine.stats = {
            "processed": 100,
            "detected": 50,
            "published": 40,
            "discarded": 10,
            "rate_limited": 5,
            "files_scanned": 200,
            "high_activity_detected": 3,
        }

        stats = exploration_engine.get_stats()

        assert stats["processed"] == 100
        assert stats["detected"] == 50
        assert stats["published"] == 40

    @pytest.mark.asyncio
    async def test_reset_stats(self, exploration_engine):
        """Testa reset de estatísticas."""
        exploration_engine.stats["processed"] = 100

        exploration_engine.reset_stats()

        assert exploration_engine.stats["processed"] == 0


class TestSignalQueue:
    """Testes da fila de sinais."""

    @pytest.mark.asyncio
    async def test_signal_queue_max_length(self, exploration_engine):
        """Testa que fila respeita maxlen."""
        # Tentar adicionar mais sinais que o limite
        for i in range(1100):  # Mais que maxlen=1000
            signal = Mock()
            signal.signal_id = f"signal-{i}"
            exploration_engine.signal_queue.append(signal)

        # Deve ter no máximo 1000
        assert len(exploration_engine.signal_queue) <= 1000

    @pytest.mark.asyncio
    async def test_process_remaining_signals_on_stop(self, exploration_engine):
        """Testa processamento de sinais restantes no stop."""
        exploration_engine._is_running = True
        exploration_engine.kafka_producer.stop = AsyncMock()
        exploration_engine.memory_client.stop = AsyncMock()
        exploration_engine.pheromone_client.stop = AsyncMock()

        # Adicionar sinais na fila
        for i in range(5):
            signal = Mock()
            signal.signal_id = f"signal-{i}"
            exploration_engine.signal_queue.append(signal)

        exploration_engine._publish_signal_internal = AsyncMock()

        await exploration_engine.stop()

        # Todos os sinais devem ter sido processados
        assert exploration_engine._publish_signal_internal.call_count == 5


class TestCodebaseScanning:
    """Testes de scan de codebase."""

    @pytest.mark.asyncio
    async def test_scan_codebase_directory(self, exploration_engine, tmp_path):
        """Testa scan de diretório de codebase."""
        # Criar arquivos de teste
        (tmp_path / "test1.py").write_text("x = 1")
        (tmp_path / "test2.py").write_text("y = 2")

        exploration_engine.file_signal_detector = Mock()
        exploration_engine.file_signal_detector.scan_directory = Mock(return_value=[])

        await exploration_engine.scan_codebase(str(tmp_path))

        exploration_engine.file_signal_detector.scan_directory.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_codebase_with_filters(self, exploration_engine, tmp_path):
        """Testa scan com filtros de extensão."""
        (tmp_path / "test.py").write_text("x = 1")
        (tmp_path / "test.txt").write_text("text")

        exploration_engine.file_signal_detector = Mock()
        exploration_engine.file_signal_detector.scan_directory = Mock(return_value=[])

        await exploration_engine.scan_codebase(str(tmp_path), extensions={".py"})

        exploration_engine.file_signal_detector.scan_directory.assert_called_once()


class TestCuriosityScoring:
    """Testes de pontuação de curiosidade."""

    def test_calculate_curiosity_score_new_domain(self, exploration_engine):
        """Testa cálculo de curiosidade para novo domínio."""
        event = Mock()
        event.event_type = "new_domain_discovery"
        event.payload = {"domain": "ai/ml"}

        score = exploration_engine._calculate_curiosity_score(event, UnifiedDomain.ML)

        assert score > 0.5  # Novo domínio deve ter curiosidade alta

    def test_calculate_curiosity_score_familiar_domain(self, exploration_engine):
        """Testa cálculo de curiosidade para domínio familiar."""
        event = Mock()
        event.event_type = "routine_change"
        event.payload = {"domain": "codebase"}

        score = exploration_engine._calculate_curiosity_score(event, UnifiedDomain.CODEBASE)

        assert 0 <= score <= 1


class TestDomainExploration:
    """Testes de exploração de domínios."""

    @pytest.mark.asyncio
    async def test_explore_domain_success(self, exploration_engine):
        """Testa exploração de domínio com sucesso."""
        exploration_engine._is_running = True

        results = await exploration_engine.explore_domain(UnifiedDomain.ML, duration_seconds=1)

        assert "domain" in results
        assert "signals_detected" in results
        assert "duration_seconds" in results

    @pytest.mark.asyncio
    async def test_explore_multiple_domains(self, exploration_engine):
        """Testa exploração de múltiplos domínios."""
        exploration_engine._is_running = True

        domains = [UnifiedDomain.CODEBASE, UnifiedDomain.INFRASTRUCTURE]

        results = await exploration_engine.explore_domains(domains, duration_seconds=1)

        assert len(results) == 2


class TestHealthCheck:
    """Testes de health check."""

    def test_health_check_when_running(self, exploration_engine):
        """Testa health check quando rodando."""
        exploration_engine._is_running = True

        health = exploration_engine.health_check()

        assert health["status"] == "healthy"
        assert health["scout_agent_id"] == "scout-123"

    def test_health_check_when_stopped(self, exploration_engine):
        """Testa health check quando parado."""
        exploration_engine._is_running = False

        health = exploration_engine.health_check()

        assert health["status"] == "stopped"
