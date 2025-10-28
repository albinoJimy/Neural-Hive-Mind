"""Configurações compartilhadas para os testes"""
import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from models.intent_envelope import IntentEnvelope, IntentRequest
from pipelines.asr_pipeline import ASRPipeline, ASRResult
from pipelines.nlu_pipeline import NLUPipeline, NLUResult, Entity
from kafka.producer import KafkaIntentProducer


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_asr_pipeline() -> AsyncMock:
    """Mock do pipeline ASR"""
    mock = AsyncMock(spec=ASRPipeline)

    # Configure default return values
    mock.is_ready.return_value = True
    mock.initialize.return_value = None
    mock.close.return_value = None

    # Mock successful ASR result
    mock.process.return_value = ASRResult(
        text="teste de intenção de áudio",
        confidence=0.95,
        language="pt-BR",
        duration=2.5,
        processing_time_ms=150.0
    )

    return mock


@pytest.fixture
def mock_nlu_pipeline() -> AsyncMock:
    """Mock do pipeline NLU"""
    mock = AsyncMock(spec=NLUPipeline)

    # Configure default return values
    mock.is_ready.return_value = True
    mock.initialize.return_value = None
    mock.close.return_value = None

    # Mock successful NLU result
    mock.process.return_value = NLUResult(
        domain="business",
        classification="request",
        confidence=0.88,
        processed_text="teste de intenção processada",
        entities=[
            Entity(
                entity_type="ACTION",
                value="teste",
                confidence=0.9,
                start=0,
                end=5
            )
        ],
        keywords=["teste", "intenção"],
        processing_time_ms=80.0
    )

    return mock


@pytest.fixture
def mock_kafka_producer() -> AsyncMock:
    """Mock do producer Kafka"""
    mock = AsyncMock(spec=KafkaIntentProducer)

    # Configure default return values
    mock.is_ready.return_value = True
    mock.initialize.return_value = None
    mock.close.return_value = None
    mock.send_intent.return_value = None

    return mock


@pytest.fixture
def sample_intent_request() -> IntentRequest:
    """Request de intenção de exemplo"""
    return IntentRequest(
        text="Preciso implementar um novo recurso de autenticação",
        language="pt-BR",
        correlation_id="test-correlation-123"
    )


@pytest.fixture
def sample_user_context() -> Dict[str, Any]:
    """Contexto do usuário de exemplo"""
    return {
        "userId": "user-123",
        "tenantId": "tenant-456",
        "sessionId": "session-789",
        "userName": "Usuário Teste"
    }


@pytest.fixture
def sample_intent_envelope(sample_user_context) -> IntentEnvelope:
    """Envelope de intenção de exemplo"""
    from datetime import datetime

    return IntentEnvelope(
        id="intent-123",
        correlation_id="correlation-456",
        actor={
            "id": sample_user_context["userId"],
            "actor_type": "human",
            "name": sample_user_context["userName"]
        },
        intent={
            "text": "Implementar autenticação",
            "domain": "technical",
            "classification": "implementation",
            "original_language": "pt-BR",
            "processed_text": "implementar autenticação",
            "entities": [
                {
                    "entity_type": "ACTION",
                    "value": "implementar",
                    "confidence": 0.9,
                    "start": 0,
                    "end": 11
                }
            ],
            "keywords": ["implementar", "autenticação"]
        },
        confidence=0.85,
        context=sample_user_context,
        timestamp=datetime.utcnow()
    )


@pytest.fixture
def audio_file_mock():
    """Mock de arquivo de áudio"""
    mock = MagicMock()
    mock.content_type = "audio/wav"
    mock.size = 1024 * 50  # 50KB
    mock.read = AsyncMock(return_value=b"fake-audio-content")
    return mock


@pytest.fixture
def settings_override():
    """Override das configurações para testes"""
    from config.settings import Settings

    settings = Settings(
        environment="test",
        debug=True,
        kafka_bootstrap_servers="localhost:9092",
        schema_registry_url="http://localhost:8081",
        asr_model_name="base",
        nlu_confidence_threshold=0.75,
        max_audio_size_mb=10,
        max_text_length=10000
    )
    return settings