"""
Testes unitários para validação de correlation_id no DecisionProducer.

Verifica que o DecisionProducer rejeita decisões com correlation_id None ou vazio,
garantindo que apenas decisões válidas sejam publicadas no Kafka.
"""

import pytest
import uuid
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from src.producers.decision_producer import DecisionProducer
from src.models.consolidated_decision import (
    ConsolidatedDecision,
    DecisionType,
    ConsensusMethod,
    SpecialistVote,
    ConsensusMetrics
)


@pytest.fixture
def mock_producer_config():
    """Configuração mock para o DecisionProducer."""
    config = MagicMock()
    config.kafka_bootstrap_servers = 'localhost:9092'
    config.kafka_enable_idempotence = True
    config.kafka_consensus_topic = 'plans.consensus'
    return config


@pytest.fixture
def sample_specialist_votes():
    """Votos de especialistas para testes."""
    return [
        SpecialistVote(
            specialist_type='business',
            opinion_id=str(uuid.uuid4()),
            confidence_score=0.85,
            risk_score=0.2,
            recommendation='approve',
            weight=0.2,
            processing_time_ms=100
        ),
        SpecialistVote(
            specialist_type='technical',
            opinion_id=str(uuid.uuid4()),
            confidence_score=0.88,
            risk_score=0.15,
            recommendation='approve',
            weight=0.2,
            processing_time_ms=120
        )
    ]


@pytest.fixture
def sample_consensus_metrics():
    """Métricas de consenso para testes."""
    return ConsensusMetrics(
        divergence_score=0.1,
        convergence_time_ms=500,
        unanimous=True,
        fallback_used=False,
        pheromone_strength=0.5,
        bayesian_confidence=0.85,
        voting_confidence=0.9
    )


@pytest.fixture
def valid_consolidated_decision(sample_specialist_votes, sample_consensus_metrics):
    """Decisão consolidada válida com correlation_id."""
    return ConsolidatedDecision(
        plan_id=str(uuid.uuid4()),
        intent_id=str(uuid.uuid4()),
        correlation_id=str(uuid.uuid4()),
        final_decision=DecisionType.APPROVE,
        consensus_method=ConsensusMethod.UNANIMOUS,
        aggregated_confidence=0.85,
        aggregated_risk=0.15,
        specialist_votes=sample_specialist_votes,
        consensus_metrics=sample_consensus_metrics,
        explainability_token='explain-test',
        reasoning_summary='Decisão unânime de aprovação'
    )


@pytest.fixture
def decision_with_none_correlation_id(sample_specialist_votes, sample_consensus_metrics):
    """Decisão consolidada com correlation_id=None."""
    return ConsolidatedDecision(
        plan_id=str(uuid.uuid4()),
        intent_id=str(uuid.uuid4()),
        correlation_id=None,
        final_decision=DecisionType.APPROVE,
        consensus_method=ConsensusMethod.UNANIMOUS,
        aggregated_confidence=0.85,
        aggregated_risk=0.15,
        specialist_votes=sample_specialist_votes,
        consensus_metrics=sample_consensus_metrics,
        explainability_token='explain-test',
        reasoning_summary='Decisão unânime de aprovação'
    )


@pytest.fixture
def decision_with_empty_correlation_id(sample_specialist_votes, sample_consensus_metrics):
    """Decisão consolidada com correlation_id vazio."""
    return ConsolidatedDecision(
        plan_id=str(uuid.uuid4()),
        intent_id=str(uuid.uuid4()),
        correlation_id='',
        final_decision=DecisionType.APPROVE,
        consensus_method=ConsensusMethod.UNANIMOUS,
        aggregated_confidence=0.85,
        aggregated_risk=0.15,
        specialist_votes=sample_specialist_votes,
        consensus_metrics=sample_consensus_metrics,
        explainability_token='explain-test',
        reasoning_summary='Decisão unânime de aprovação'
    )


@pytest.fixture
def decision_with_whitespace_correlation_id(sample_specialist_votes, sample_consensus_metrics):
    """Decisão consolidada com correlation_id apenas espaços."""
    return ConsolidatedDecision(
        plan_id=str(uuid.uuid4()),
        intent_id=str(uuid.uuid4()),
        correlation_id='   ',
        final_decision=DecisionType.APPROVE,
        consensus_method=ConsensusMethod.UNANIMOUS,
        aggregated_confidence=0.85,
        aggregated_risk=0.15,
        specialist_votes=sample_specialist_votes,
        consensus_metrics=sample_consensus_metrics,
        explainability_token='explain-test',
        reasoning_summary='Decisão unânime de aprovação'
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestDecisionProducerCorrelationIdValidation:
    """Testes para validação de correlation_id no DecisionProducer."""

    @patch('src.producers.decision_producer.Producer')
    async def test_publish_decision_accepts_valid_correlation_id(
        self,
        mock_producer_class,
        mock_producer_config,
        valid_consolidated_decision,
        caplog
    ):
        """Verifica que decisão com correlation_id válido é publicada."""
        mock_producer = MagicMock()
        mock_producer.produce = MagicMock()
        mock_producer.poll = MagicMock()
        mock_producer_class.return_value = mock_producer

        producer = DecisionProducer(mock_producer_config)
        producer.producer = mock_producer
        producer.avro_serializer = None  # Usar JSON fallback

        await producer._publish_decision(valid_consolidated_decision)

        mock_producer.produce.assert_called_once()
        assert 'Decisão publicada' in caplog.text
        assert valid_consolidated_decision.correlation_id in caplog.text

    @patch('src.producers.decision_producer.Producer')
    async def test_publish_decision_rejects_none_correlation_id(
        self,
        mock_producer_class,
        mock_producer_config,
        decision_with_none_correlation_id,
        caplog
    ):
        """Verifica que decisão com correlation_id=None é rejeitada."""
        mock_producer = MagicMock()
        mock_producer.produce = MagicMock()
        mock_producer_class.return_value = mock_producer

        producer = DecisionProducer(mock_producer_config)
        producer.producer = mock_producer
        producer.avro_serializer = None

        with pytest.raises(ValueError) as exc_info:
            await producer._publish_decision(decision_with_none_correlation_id)

        assert 'correlation_id não pode ser None/vazio' in str(exc_info.value)
        assert 'CRITICAL: correlation_id ausente na decisão' in caplog.text
        mock_producer.produce.assert_not_called()

    @patch('src.producers.decision_producer.Producer')
    async def test_publish_decision_rejects_empty_correlation_id(
        self,
        mock_producer_class,
        mock_producer_config,
        decision_with_empty_correlation_id,
        caplog
    ):
        """Verifica que decisão com correlation_id vazio é rejeitada."""
        mock_producer = MagicMock()
        mock_producer.produce = MagicMock()
        mock_producer_class.return_value = mock_producer

        producer = DecisionProducer(mock_producer_config)
        producer.producer = mock_producer
        producer.avro_serializer = None

        with pytest.raises(ValueError) as exc_info:
            await producer._publish_decision(decision_with_empty_correlation_id)

        assert 'correlation_id não pode ser None/vazio' in str(exc_info.value)
        mock_producer.produce.assert_not_called()

    @patch('src.producers.decision_producer.Producer')
    async def test_publish_decision_rejects_whitespace_correlation_id(
        self,
        mock_producer_class,
        mock_producer_config,
        decision_with_whitespace_correlation_id,
        caplog
    ):
        """Verifica que decisão com correlation_id apenas espaços é rejeitada."""
        mock_producer = MagicMock()
        mock_producer.produce = MagicMock()
        mock_producer_class.return_value = mock_producer

        producer = DecisionProducer(mock_producer_config)
        producer.producer = mock_producer
        producer.avro_serializer = None

        with pytest.raises(ValueError) as exc_info:
            await producer._publish_decision(decision_with_whitespace_correlation_id)

        assert 'correlation_id não pode ser None/vazio' in str(exc_info.value)
        mock_producer.produce.assert_not_called()

    @patch('src.producers.decision_producer.Producer')
    async def test_publish_decision_logs_correlation_id_on_success(
        self,
        mock_producer_class,
        mock_producer_config,
        valid_consolidated_decision,
        caplog
    ):
        """Verifica que correlation_id é logado no sucesso da publicação."""
        mock_producer = MagicMock()
        mock_producer.produce = MagicMock()
        mock_producer.poll = MagicMock()
        mock_producer_class.return_value = mock_producer

        producer = DecisionProducer(mock_producer_config)
        producer.producer = mock_producer
        producer.avro_serializer = None

        await producer._publish_decision(valid_consolidated_decision)

        # Verificar que o log contém correlation_id
        assert valid_consolidated_decision.correlation_id in caplog.text

    def test_serialize_value_includes_correlation_id(
        self,
        mock_producer_config,
        valid_consolidated_decision
    ):
        """Verifica que serialização inclui correlation_id."""
        producer = DecisionProducer(mock_producer_config)
        producer.avro_serializer = None  # Usar JSON fallback

        serialized = producer._serialize_value(valid_consolidated_decision)

        # Deserializar para verificar
        import json
        deserialized = json.loads(serialized.decode('utf-8'))

        assert 'correlation_id' in deserialized
        assert deserialized['correlation_id'] == valid_consolidated_decision.correlation_id
        assert deserialized['correlation_id'] is not None
