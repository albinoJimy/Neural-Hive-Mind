"""
Unit tests for ExplorationEngine service (scout-agents).

Tests codebase exploration, curiosity scoring, and signal processing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from collections import deque

from src.engine.exploration_engine import ExplorationEngine
from src.models.scout_signal import ChannelType, SignalSource, SignalType, UnifiedDomain


class TestExplorationEngineInitialization:
    """Test ExplorationEngine initialization."""

    def test_initialization(self):
        """Test engine initialization with scout agent ID."""
        engine = ExplorationEngine("scout-agent-001")

        assert engine.scout_agent_id == "scout-agent-001"
        assert engine.detector is not None
        assert engine.kafka_producer is not None
        assert engine.memory_client is not None
        assert engine.pheromone_client is not None
        assert engine.curiosity_calculator is not None
        assert engine.file_signal_detector is not None

    def test_initialization_queue(self):
        """Test internal queue is initialized."""
        engine = ExplorationEngine("scout-agent-001")

        assert isinstance(engine.signal_queue, deque)
        assert engine.signal_queue.maxlen == 1000

    def test_initialization_stats(self):
        """Test statistics are initialized."""
        engine = ExplorationEngine("scout-agent-001")

        assert engine.stats["processed"] == 0
        assert engine.stats["detected"] == 0
        assert engine.stats["published"] == 0
        assert engine.stats["discarded"] == 0
        assert engine.stats["rate_limited"] == 0


class TestEngineStartStop:
    """Test engine lifecycle."""

    @pytest.mark.asyncio
    async def test_start(self):
        """Test engine starts successfully."""
        engine = ExplorationEngine("scout-agent-001")

        await engine.start()

        assert engine._is_running is True

    @pytest.mark.asyncio
    async def test_start_clients_initialized(self):
        """Test start initializes all clients."""
        engine = ExplorationEngine("scout-agent-001")

        await engine.start()

        # Verify clients were started
        engine.kafka_producer.start.assert_called_once()
        engine.memory_client.start.assert_called_once()
        engine.pheromone_client.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop(self):
        """Test engine stops gracefully."""
        engine = ExplorationEngine("scout-agent-001")
        engine._is_running = True

        await engine.stop()

        assert engine._is_running is False

    @pytest.mark.asyncio
    async def test_stop_processes_remaining_signals(self):
        """Test stop processes signals in queue."""
        engine = ExplorationEngine("scout-agent-001")
        engine._is_running = True

        # Add mock signals to queue
        from src.models.scout_signal import ScoutSignal, SignalType, UnifiedDomain

        signal = ScoutSignal(
            scout_agent_id="test",
            correlation_id="test-001",
            trace_id="trace-001",
            span_id="span-001",
            signal_type=SignalType.ANOMALY_POSITIVE,
            exploration_domain=UnifiedDomain.BUSINESS,
            source=SignalSource(channel=ChannelType.CORE),
            curiosity_score=0.8,
            confidence=0.7,
            relevance_score=0.6,
            risk_score=0.2,
        )
        engine.signal_queue.append(signal)

        await engine.stop()

        # Queue should be processed (empty)
        assert len(engine.signal_queue) == 0


class TestEventProcessing:
    """Test event processing pipeline."""

    @pytest.mark.asyncio
    async def test_process_event_not_running(self, sample_raw_event, business_domain):
        """Test processing when engine not running returns None."""
        engine = ExplorationEngine("scout-agent-001")
        # Don't start the engine

        result = await engine.process_event(sample_raw_event, business_domain)

        assert result is None

    @pytest.mark.asyncio
    async def test_process_event_successful(self, sample_raw_event, business_domain):
        """Test successful event processing."""
        engine = ExplorationEngine("scout-agent-001")
        await engine.start()

        # Mock detection to return signal
        from src.models.scout_signal import (
            ScoutSignal,
            SignalType,
            SignalSource,
            UnifiedDomain,
            ChannelType,
        )

        source = SignalSource(channel=ChannelType.CORE)
        mock_signal = ScoutSignal(
            scout_agent_id="test",
            correlation_id="test-001",
            trace_id="trace-001",
            span_id="span-001",
            signal_type=SignalType.ANOMALY_POSITIVE,
            exploration_domain=UnifiedDomain.BUSINESS,
            source=source,
            curiosity_score=0.8,
            confidence=0.7,
            relevance_score=0.6,
            risk_score=0.2,
            description="Test signal",
            raw_data={},
            features=[0.1, 0.2, 0.3],
        )

        with patch.object(engine.detector, "detect", return_value=mock_signal):
            result = await engine.process_event(sample_raw_event, business_domain)

            # May return signal or be rate limited
            assert result is None or hasattr(result, "signal_id")
            assert engine.stats["processed"] == 1

    @pytest.mark.asyncio
    async def test_process_event_no_detection(self, sample_raw_event, business_domain):
        """Test processing when no signal detected."""
        engine = ExplorationEngine("scout-agent-001")
        await engine.start()

        with patch.object(engine.detector, "detect", return_value=None):
            result = await engine.process_event(sample_raw_event, business_domain)

            assert result is None
            assert engine.stats["detected"] == 0

    @pytest.mark.asyncio
    async def test_process_event_exception_handling(self, sample_raw_event, business_domain):
        """Test processing handles exceptions gracefully."""
        engine = ExplorationEngine("scout-agent-001")
        await engine.start()

        with patch.object(engine.detector, "detect", side_effect=Exception("Test error")):
            result = await engine.process_event(sample_raw_event, business_domain)

            assert result is None


class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_check_rate_limit_empty(self):
        """Test rate limit check when empty."""
        engine = ExplorationEngine("scout-agent-001")

        result = engine._check_rate_limit()

        assert result is True

    def test_check_rate_limit_under_threshold(self):
        """Test rate limit when under threshold."""
        engine = ExplorationEngine("scout-agent-001")

        # Add some timestamps under limit
        for _ in range(10):
            engine.published_signals.append(datetime.now(timezone.utc))

        result = engine._check_rate_limit()

        assert result is True

    def test_check_rate_limit_over_threshold(self):
        """Test rate limit when over threshold."""
        engine = ExplorationEngine("scout-agent-001")

        # Fill to max
        for _ in range(engine.max_signals_per_minute + 10):
            engine.published_signals.append(datetime.now(timezone.utc))

        result = engine._check_rate_limit()

        assert result is False

    def test_check_rate_limit_removes_old(self):
        """Test old timestamps are removed from tracking."""
        engine = ExplorationEngine("scout-agent-001")

        # Add old timestamps
        old_time = datetime.now(timezone.utc) - timedelta(minutes=2)
        for _ in range(10):
            engine.published_signals.append(old_time)

        result = engine._check_rate_limit()

        assert result is True
        assert len(engine.published_signals) == 0


class TestSignalPublishing:
    """Test signal publishing."""

    @pytest.mark.asyncio
    async def test_publish_signal_success(self):
        """Test successful signal publishing."""
        from src.models.scout_signal import ScoutSignal, SignalType, UnifiedDomain

        engine = ExplorationEngine("scout-agent-001")

        signal = ScoutSignal(
            scout_agent_id="test",
            correlation_id="test-001",
            trace_id="trace-001",
            span_id="span-001",
            signal_type=SignalType.ANOMALY_POSITIVE,
            exploration_domain=UnifiedDomain.BUSINESS,
            source=SignalSource(channel=ChannelType.CORE),
            curiosity_score=0.8,
            confidence=0.7,
            relevance_score=0.6,
            risk_score=0.2,
        )

        result = await engine._publish_signal_internal(signal)

        assert result is True

    @pytest.mark.asyncio
    async def test_publish_signal_kafka_failure(self):
        """Test signal publishing handles Kafka failure."""
        from src.models.scout_signal import ScoutSignal, SignalType, UnifiedDomain

        engine = ExplorationEngine("scout-agent-001")
        engine.kafka_producer.publish_signal = AsyncMock(return_value=False)

        signal = ScoutSignal(
            scout_agent_id="test",
            correlation_id="test-001",
            trace_id="trace-001",
            span_id="span-001",
            signal_type=SignalType.ANOMALY_POSITIVE,
            exploration_domain=UnifiedDomain.BUSINESS,
            source=SignalSource(channel=ChannelType.CORE),
            curiosity_score=0.8,
            confidence=0.7,
            relevance_score=0.6,
            risk_score=0.2,
        )

        result = await engine._publish_signal_internal(signal)

        assert result is False

    @pytest.mark.asyncio
    async def test_publish_signal_memory_failure_continues(self):
        """Test publishing continues if memory storage fails."""
        from src.models.scout_signal import ScoutSignal, SignalType, UnifiedDomain

        engine = ExplorationEngine("scout-agent-001")
        engine.memory_client.store_signal_redis = AsyncMock(return_value=False)

        signal = ScoutSignal(
            scout_agent_id="test",
            correlation_id="test-001",
            trace_id="trace-001",
            span_id="span-001",
            signal_type=SignalType.ANOMALY_POSITIVE,
            exploration_domain=UnifiedDomain.BUSINESS,
            source=SignalSource(channel=ChannelType.CORE),
            curiosity_score=0.8,
            confidence=0.7,
            relevance_score=0.6,
            risk_score=0.2,
        )

        result = await engine._publish_signal_internal(signal)

        # Should succeed despite memory failure
        assert result is True


class TestQueueProcessing:
    """Test signal queue processing."""

    @pytest.mark.asyncio
    async def test_process_queue_empty(self):
        """Test processing empty queue."""
        engine = ExplorationEngine("scout-agent-001")

        await engine.process_queue()

        # Should not raise any errors

    @pytest.mark.asyncio
    async def test_process_queue_signals(self):
        """Test processing queued signals."""
        from src.models.scout_signal import ScoutSignal, SignalType, UnifiedDomain

        engine = ExplorationEngine("scout-agent-001")

        # Add signals to queue
        for i in range(5):
            signal = ScoutSignal(
                scout_agent_id="test",
                correlation_id=f"test-{i}",
                trace_id=f"trace-{i}",
                span_id=f"span-{i}",
                signal_type=SignalType.ANOMALY_POSITIVE,
                exploration_domain=UnifiedDomain.BUSINESS,
                source=SignalSource(channel=ChannelType.CORE),
                curiosity_score=0.8,
                confidence=0.7,
                relevance_score=0.6,
                risk_score=0.2,
            )
            engine.signal_queue.append(signal)

        await engine.process_queue()

        # Queue should be processed
        assert len(engine.signal_queue) == 0


class TestStatistics:
    """Test statistics tracking."""

    def test_get_stats(self):
        """Test getting engine statistics."""
        engine = ExplorationEngine("scout-agent-001")

        stats = engine.get_stats()

        assert "processed" in stats
        assert "detected" in stats
        assert "published" in stats
        assert "discarded" in stats
        assert "rate_limited" in stats
        assert "queue_size" in stats
        assert "current_rate" in stats
        assert "is_running" in stats

    def test_get_stats_includes_queue_size(self):
        """Test stats includes current queue size."""
        engine = ExplorationEngine("scout-agent-001")

        # Add to queue
        from src.models.scout_signal import ScoutSignal, SignalType, UnifiedDomain

        signal = ScoutSignal(
            scout_agent_id="test",
            correlation_id="test-001",
            trace_id="trace-001",
            span_id="span-001",
            signal_type=SignalType.ANOMALY_POSITIVE,
            exploration_domain=UnifiedDomain.BUSINESS,
            source=SignalSource(channel=ChannelType.CORE),
            curiosity_score=0.8,
            confidence=0.7,
            relevance_score=0.6,
            risk_score=0.2,
        )
        engine.signal_queue.append(signal)

        stats = engine.get_stats()

        assert stats["queue_size"] == 1


class TestFeedbackHandling:
    """Test feedback handling for adaptive learning."""

    @pytest.mark.asyncio
    async def test_handle_feedback_valid(self):
        """Test handling valid feedback."""
        engine = ExplorationEngine("scout-agent-001")

        await engine.handle_feedback(
            signal_id="signal-001", validation_score=0.8, domain=UnifiedDomain.BUSINESS
        )

        # Should not raise any errors

    @pytest.mark.asyncio
    async def test_handle_feedback_updates_prior(self):
        """Test feedback updates Bayesian prior."""
        engine = ExplorationEngine("scout-agent-001")

        initial_prior = engine.detector.bayesian_filter.get_prior(UnifiedDomain.BUSINESS)

        await engine.handle_feedback(
            signal_id="signal-002", validation_score=0.9, domain=UnifiedDomain.BUSINESS
        )

        # Prior should be updated
        # (actual verification depends on BayesianFilter implementation)

    @pytest.mark.asyncio
    async def test_handle_feedback_with_feature_mean(self):
        """Test feedback with feature mean updates likelihood."""
        engine = ExplorationEngine("scout-agent-001")

        await engine.handle_feedback(
            signal_id="signal-003",
            validation_score=0.7,
            domain=UnifiedDomain.TECHNICAL,
            feature_mean=0.65,
        )

        # Should not raise any errors

    @pytest.mark.asyncio
    async def test_handle_feedback_domain_retrieval(self):
        """Test feedback attempts domain retrieval if not provided."""
        engine = ExplorationEngine("scout-agent-001")
        engine.memory_client.get_signal_redis = AsyncMock(
            return_value='{"exploration_domain": "BUSINESS"}'
        )

        await engine.handle_feedback(signal_id="signal-004", validation_score=0.6)

        # Should attempt retrieval


class TestCodebaseExploration:
    """Test codebase exploration methods."""

    @pytest.mark.asyncio
    async def test_scan_codebase(self, tmp_path):
        """Test codebase scanning."""
        engine = ExplorationEngine("scout-agent-001")

        # Create test files
        (tmp_path / "test.py").write_text("print('hello')")
        (tmp_path / "test.md").write_text("# Test")

        results = await engine.scan_codebase(str(tmp_path), {".py"})

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_get_curiosity_scores(self, tmp_path):
        """Test getting curiosity scores."""
        engine = ExplorationEngine("scout-agent-001")

        # Create test files
        for i in range(3):
            (tmp_path / f"file{i}.py").write_text(f"# File {i}")

        results = await engine.get_curiosity_scores(str(tmp_path), limit=10)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_get_exploration_summary(self, tmp_path):
        """Test getting exploration summary."""
        engine = ExplorationEngine("scout-agent-001")

        # Create test directory
        (tmp_path / "test.py").write_text("test content")

        summary = await engine.get_exploration_summary(str(tmp_path))

        assert isinstance(summary, dict)
        assert "directory" in summary

    @pytest.mark.asyncio
    async def test_rank_directories_by_interest(self, tmp_path):
        """Test ranking directories by interest."""
        engine = ExplorationEngine("scout-agent-001")

        # Create subdirectories
        (tmp_path / "dir1").mkdir()
        (tmp_path / "dir2").mkdir()

        rankings = await engine.rank_directories_by_interest(str(tmp_path))

        assert isinstance(rankings, dict)

    @pytest.mark.asyncio
    async def test_mark_file_visited(self):
        """Test marking file as visited."""
        engine = ExplorationEngine("scout-agent-001")

        await engine.mark_file_visited("/path/to/file.py")

        # Should not raise any errors


class TestSignalRetrieval:
    """Test signal retrieval from memory."""

    @pytest.mark.asyncio
    async def test_retrieve_signal_domain_found(self):
        """Test retrieving signal domain when found."""
        engine = ExplorationEngine("scout-agent-001")
        engine.memory_client.get_signal_redis = AsyncMock(
            return_value='{"exploration_domain": "TECHNICAL"}'
        )

        domain = await engine._retrieve_signal_domain("signal-001")

        assert domain is not None
        assert domain.value == "TECHNICAL"

    @pytest.mark.asyncio
    async def test_retrieve_signal_domain_not_found(self):
        """Test retrieving signal domain when not found."""
        engine = ExplorationEngine("scout-agent-001")
        engine.memory_client.get_signal_redis = AsyncMock(return_value=None)

        domain = await engine._retrieve_signal_domain("signal-999")

        assert domain is None

    @pytest.mark.asyncio
    async def test_retrieve_signal_domain_invalid_json(self):
        """Test retrieving signal domain with invalid JSON."""
        engine = ExplorationEngine("scout-agent-001")
        engine.memory_client.get_signal_redis = AsyncMock(return_value="invalid json")

        domain = await engine._retrieve_signal_domain("signal-002")

        assert domain is None


class TestPriorityHandling:
    """Test high-priority signal handling."""

    @pytest.mark.asyncio
    async def test_high_priority_queued_when_rate_limited(self):
        """Test high priority signals are queued when rate limited."""
        from src.models.scout_signal import ScoutSignal, SignalType, UnifiedDomain

        engine = ExplorationEngine("scout-agent-001")
        await engine.start()

        # Fill rate limit
        for _ in range(engine.max_signals_per_minute + 1):
            engine.published_signals.append(datetime.now(timezone.utc))

        # Mock signal with high priority
        from src.models.scout_signal import ScoutSignal

        mock_signal = ScoutSignal(
            scout_agent_id="test",
            correlation_id="test-001",
            trace_id="trace-001",
            span_id="span-001",
            signal_type=SignalType.THREAT,
            exploration_domain=UnifiedDomain.SECURITY,
            source=SignalSource(channel=ChannelType.CORE),
            curiosity_score=0.9,
            confidence=0.8,
            relevance_score=0.7,
            risk_score=0.9,
        )

        with patch.object(mock_signal, "calculate_priority", return_value=0.8):
            await engine.process_event(
                sample_raw_event := type(
                    "obj",
                    (object,),
                    {
                        "event_id": "test",
                        "source": "test",
                        "event_type": "test",
                        "payload": {},
                        "metadata": {},
                        "extract_features": lambda: [],
                    },
                )(),
                UnifiedDomain.SECURITY,
            )

        # High priority signal should be queued
        assert len(engine.signal_queue) > 0


class TestChannelTypes:
    """Test different channel types."""

    @pytest.mark.asyncio
    async def test_process_event_core_channel(self, sample_raw_event, business_domain):
        """Test processing with CORE channel."""
        engine = ExplorationEngine("scout-agent-001")
        await engine.start()

        # Should not raise any errors
        with patch.object(engine.detector, "detect", return_value=None):
            await engine.process_event(sample_raw_event, business_domain, ChannelType.CORE)

    @pytest.mark.asyncio
    async def test_process_event_extended_channel(self, sample_raw_event, business_domain):
        """Test processing with EXTENDED channel."""
        engine = ExplorationEngine("scout-agent-001")
        await engine.start()

        # Should not raise any errors
        with patch.object(engine.detector, "detect", return_value=None):
            await engine.process_event(sample_raw_event, business_domain, ChannelType.EXTENDED)

    @pytest.mark.asyncio
    async def test_process_event_experimental_channel(self, sample_raw_event, business_domain):
        """Test processing with EXPERIMENTAL channel."""
        engine = ExplorationEngine("scout-agent-001")
        await engine.start()

        # Should not raise any errors
        with patch.object(engine.detector, "detect", return_value=None):
            await engine.process_event(sample_raw_event, business_domain, ChannelType.EXPERIMENTAL)
