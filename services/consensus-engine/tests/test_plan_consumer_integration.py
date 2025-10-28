'''Integration tests for PlanConsumer pipeline'''

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.consumers.plan_consumer import PlanConsumer
from src.models.consolidated_decision import ConsolidatedDecision, FinalDecision


class MockConfig:
    '''Mock configuration for testing'''
    kafka_plans_topic = 'plans.ready'
    kafka_bootstrap_servers = 'localhost:9092'
    kafka_consumer_group_id = 'consensus-engine-test'
    kafka_auto_offset_reset = 'earliest'
    kafka_enable_auto_commit = False
    enable_parallel_invocation = True
    grpc_timeout_ms = 5000


@pytest.fixture
def mock_config():
    return MockConfig()


@pytest.fixture
def mock_specialists_client():
    '''Mock SpecialistsGrpcClient'''
    client = AsyncMock()

    # Mock evaluate_plan_parallel response
    client.evaluate_plan_parallel = AsyncMock(return_value=[
        {
            'opinion_id': 'op-1',
            'specialist_type': 'business',
            'specialist_version': '1.0.0',
            'opinion': {
                'confidence_score': 0.9,
                'risk_score': 0.2,
                'recommendation': 'APPROVE',
                'reasoning_summary': 'Business case is strong',
                'reasoning_factors': [],
                'explainability_token': 'exp-token-1',
                'explainability': {
                    'method': 'SHAP',
                    'model_version': '1.0',
                    'model_type': 'neural'
                },
                'mitigations': [],
                'metadata': {}
            },
            'processing_time_ms': 100,
            'evaluated_at': '2024-01-01T00:00:00'
        },
        {
            'opinion_id': 'op-2',
            'specialist_type': 'technical',
            'specialist_version': '1.0.0',
            'opinion': {
                'confidence_score': 0.85,
                'risk_score': 0.3,
                'recommendation': 'APPROVE',
                'reasoning_summary': 'Technical feasibility confirmed',
                'reasoning_factors': [],
                'explainability_token': 'exp-token-2',
                'explainability': {
                    'method': 'SHAP',
                    'model_version': '1.0',
                    'model_type': 'neural'
                },
                'mitigations': [],
                'metadata': {}
            },
            'processing_time_ms': 120,
            'evaluated_at': '2024-01-01T00:00:00'
        },
        {
            'opinion_id': 'op-3',
            'specialist_type': 'behavior',
            'specialist_version': '1.0.0',
            'opinion': {
                'confidence_score': 0.88,
                'risk_score': 0.25,
                'recommendation': 'APPROVE',
                'reasoning_summary': 'Behavior patterns look good',
                'reasoning_factors': [],
                'explainability_token': 'exp-token-3',
                'explainability': {
                    'method': 'SHAP',
                    'model_version': '1.0',
                    'model_type': 'neural'
                },
                'mitigations': [],
                'metadata': {}
            },
            'processing_time_ms': 110,
            'evaluated_at': '2024-01-01T00:00:00'
        }
    ])

    # Mock evaluate_plan for sequential calls
    client.evaluate_plan = AsyncMock(return_value={
        'opinion_id': 'op-seq-1',
        'specialist_type': 'business',
        'specialist_version': '1.0.0',
        'opinion': {
            'confidence_score': 0.9,
            'risk_score': 0.2,
            'recommendation': 'APPROVE',
            'reasoning_summary': 'Business case is strong',
            'reasoning_factors': [],
            'explainability_token': 'exp-token-seq',
            'explainability': {
                'method': 'SHAP',
                'model_version': '1.0',
                'model_type': 'neural'
            },
            'mitigations': [],
            'metadata': {}
        },
        'processing_time_ms': 100,
        'evaluated_at': '2024-01-01T00:00:00'
    })

    return client


@pytest.fixture
def mock_mongodb_client():
    '''Mock MongoDBClient'''
    client = AsyncMock()
    client.save_consensus_decision = AsyncMock()
    return client


@pytest.fixture
def mock_pheromone_client():
    '''Mock PheromoneClient'''
    return AsyncMock()


@pytest.fixture
def mock_orchestrator():
    '''Mock ConsensusOrchestrator'''
    orchestrator = AsyncMock()

    # Mock process_consensus response
    mock_decision = ConsolidatedDecision(
        decision_id='dec-123',
        plan_id='plan-123',
        intent_id='intent-123',
        final_decision=FinalDecision.APPROVED,
        confidence_score=0.87,
        risk_score=0.25,
        specialist_opinions=[],
        reasoning_summary='Consensus achieved',
        explainability_token='exp-token-final',
        metadata={}
    )

    orchestrator.process_consensus = AsyncMock(return_value=mock_decision)
    return orchestrator


@pytest.mark.asyncio
async def test_plan_consumer_parallel_invocation_happy_path(
    mock_config,
    mock_specialists_client,
    mock_mongodb_client,
    mock_pheromone_client,
    mock_orchestrator
):
    '''Test PlanConsumer processes message end-to-end with parallel invocation'''

    # Create consumer
    consumer = PlanConsumer(
        mock_config,
        mock_specialists_client,
        mock_mongodb_client,
        mock_pheromone_client
    )

    # Replace orchestrator with mock
    consumer.orchestrator = mock_orchestrator

    # Create mock Kafka message
    mock_message = MagicMock()
    mock_message.topic = 'plans.ready'
    mock_message.partition = 0
    mock_message.offset = 100
    mock_message.value = {
        'plan_id': 'plan-123',
        'intent_id': 'intent-123',
        'correlation_id': 'corr-123',
        'trace_id': 'trace-123',
        'span_id': 'span-123',
        'version': '1.0.0',
        'content': 'Test cognitive plan'
    }

    # Mock decision queue
    decision_queue = asyncio.Queue()

    # Mock state module
    mock_state = MagicMock()
    mock_state.decision_queue = decision_queue

    with patch('src.consumers.plan_consumer.state', mock_state):
        # Process message
        await consumer._process_message(mock_message)

    # Verify specialist client was called with correct arguments
    mock_specialists_client.evaluate_plan_parallel.assert_called_once()
    call_args = mock_specialists_client.evaluate_plan_parallel.call_args

    # Verify cognitive plan was passed
    assert call_args[0][0] == mock_message.value

    # Verify trace context was passed
    trace_context = call_args[0][1]
    assert trace_context['trace_id'] == 'trace-123'
    assert trace_context['span_id'] == 'span-123'

    # Verify orchestrator was called
    mock_orchestrator.process_consensus.assert_called_once()

    # Verify MongoDB persistence was called
    mock_mongodb_client.save_consensus_decision.assert_called_once()
    saved_decision = mock_mongodb_client.save_consensus_decision.call_args[0][0]
    assert saved_decision.decision_id == 'dec-123'
    assert saved_decision.plan_id == 'plan-123'

    # Verify decision was enqueued
    assert decision_queue.qsize() == 1
    queued_decision = await decision_queue.get()
    assert queued_decision.decision_id == 'dec-123'


@pytest.mark.asyncio
async def test_plan_consumer_sequential_fallback(
    mock_specialists_client,
    mock_mongodb_client,
    mock_pheromone_client,
    mock_orchestrator
):
    '''Test PlanConsumer falls back to sequential invocation'''

    # Create config with parallel disabled
    config = MockConfig()
    config.enable_parallel_invocation = False

    # Create consumer
    consumer = PlanConsumer(
        config,
        mock_specialists_client,
        mock_mongodb_client,
        mock_pheromone_client
    )
    consumer.orchestrator = mock_orchestrator

    # Create mock message
    mock_message = MagicMock()
    mock_message.topic = 'plans.ready'
    mock_message.partition = 0
    mock_message.offset = 100
    mock_message.value = {
        'plan_id': 'plan-456',
        'intent_id': 'intent-456',
        'trace_id': 'trace-456',
        'span_id': 'span-456',
        'content': 'Test plan'
    }

    # Mock decision queue
    decision_queue = asyncio.Queue()
    mock_state = MagicMock()
    mock_state.decision_queue = decision_queue

    with patch('src.consumers.plan_consumer.state', mock_state):
        await consumer._process_message(mock_message)

    # Verify sequential calls were made
    assert mock_specialists_client.evaluate_plan.call_count == 5

    # Verify each specialist type was called
    called_types = [
        call[0][0] for call in mock_specialists_client.evaluate_plan.call_args_list
    ]
    assert 'business' in called_types
    assert 'technical' in called_types
    assert 'behavior' in called_types
    assert 'evolution' in called_types
    assert 'architecture' in called_types


@pytest.mark.asyncio
async def test_plan_consumer_handles_specialist_errors_gracefully(
    mock_config,
    mock_specialists_client,
    mock_mongodb_client,
    mock_pheromone_client,
    mock_orchestrator
):
    '''Test PlanConsumer handles specialist errors without crashing'''

    # Configure specialist client to return partial results
    mock_specialists_client.evaluate_plan_parallel = AsyncMock(return_value=[
        {
            'opinion_id': 'op-1',
            'specialist_type': 'business',
            'specialist_version': '1.0.0',
            'opinion': {
                'confidence_score': 0.9,
                'risk_score': 0.2,
                'recommendation': 'APPROVE',
                'reasoning_summary': 'Good',
                'reasoning_factors': [],
                'explainability_token': 'exp-1',
                'explainability': {
                    'method': 'SHAP',
                    'model_version': '1.0',
                    'model_type': 'neural'
                },
                'mitigations': [],
                'metadata': {}
            },
            'processing_time_ms': 100,
            'evaluated_at': '2024-01-01T00:00:00'
        }
    ])

    consumer = PlanConsumer(
        mock_config,
        mock_specialists_client,
        mock_mongodb_client,
        mock_pheromone_client
    )
    consumer.orchestrator = mock_orchestrator

    mock_message = MagicMock()
    mock_message.topic = 'plans.ready'
    mock_message.partition = 0
    mock_message.offset = 100
    mock_message.value = {
        'plan_id': 'plan-789',
        'intent_id': 'intent-789',
        'trace_id': 'trace-789',
        'span_id': 'span-789'
    }

    decision_queue = asyncio.Queue()
    mock_state = MagicMock()
    mock_state.decision_queue = decision_queue

    with patch('src.consumers.plan_consumer.state', mock_state):
        await consumer._process_message(mock_message)

    # Verify processing continued despite partial opinions
    mock_orchestrator.process_consensus.assert_called_once()
    mock_mongodb_client.save_consensus_decision.assert_called_once()


@pytest.mark.asyncio
async def test_plan_consumer_propagates_trace_context(
    mock_config,
    mock_specialists_client,
    mock_mongodb_client,
    mock_pheromone_client
):
    '''Test that trace context is correctly propagated from Kafka message'''

    consumer = PlanConsumer(
        mock_config,
        mock_specialists_client,
        mock_mongodb_client,
        mock_pheromone_client
    )

    cognitive_plan = {
        'plan_id': 'plan-trace-test',
        'trace_id': 'trace-abc-123',
        'span_id': 'span-xyz-789'
    }

    # Call _invoke_specialists directly to test trace context
    await consumer._invoke_specialists(cognitive_plan)

    # Verify trace context was passed correctly
    mock_specialists_client.evaluate_plan_parallel.assert_called_once()
    call_args = mock_specialists_client.evaluate_plan_parallel.call_args
    trace_context = call_args[0][1]

    assert trace_context['trace_id'] == 'trace-abc-123'
    assert trace_context['span_id'] == 'span-xyz-789'
