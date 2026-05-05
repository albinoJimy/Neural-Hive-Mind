"""Configurações compartilhadas para os testes"""

import os
import sys
from enum import Enum
from unittest.mock import MagicMock


# Mock UnifiedDomain Enum before importing
class MockUnifiedDomain(str, Enum):
    """Mock de UnifiedDomain para testes"""

    BUSINESS = "business"
    TECHNICAL = "technical"
    SECURITY = "security"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"


# Mock external dependencies BEFORE importing our modules
sys.modules["whisper"] = MagicMock()
sys.modules["spacy"] = MagicMock()
sys.modules["thinc"] = MagicMock()
sys.modules["hvac"] = MagicMock()  # Mock hvac for VaultClient tests
sys.modules["neural_hive_domain"] = MagicMock()
sys.modules["neural_hive_domain"].UnifiedDomain = MockUnifiedDomain
sys.modules["neural_hive_observability"] = MagicMock()


# Create proper CORSConfig mock
class MockCORSConfig:
    """Mock de CORSConfig para testes"""

    DEV_ORIGINS = ["http://localhost:3000", "http://localhost:8000"]
    STAGING_ORIGINS = ["https://staging.neural-hive.local"]
    PROD_ORIGINS = ["https://neural-hive.com"]
    INTERNAL_SERVICES = []

    @classmethod
    def get_origins_for_environment(cls, environment: str, is_public_api: bool = True):
        if environment == "dev":
            return cls.DEV_ORIGINS
        elif environment in ["staging", "stage"]:
            return cls.STAGING_ORIGINS
        elif environment in ["prod", "production"]:
            return cls.PROD_ORIGINS
        return cls.DEV_ORIGINS

    @classmethod
    def validate_no_wildcard(cls, origins, environment):
        """Valida que não tem wildcard nas origens."""
        for origin in origins:
            if "*" in origin and "localhost" not in origin:
                raise ValueError(f"Wildcard not allowed in {environment}")
        return True


# Mock neural_hive_security properly - need to mock both module and submodule
mock_security_module = MagicMock()
mock_security_module.CORSConfig = MockCORSConfig
sys.modules["neural_hive_security"] = mock_security_module

# Also mock the submodule path since some imports use 'from neural_hive_security.cors import'
mock_cors_module = MagicMock()
mock_cors_module.CORSConfig = MockCORSConfig
sys.modules["neural_hive_security.cors"] = mock_cors_module

sys.modules["neural_hive_integration"] = MagicMock()

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import asyncio
from datetime import timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from kafka.producer import KafkaIntentProducer
from models.intent_envelope import Entity, IntentEnvelope, IntentRequest, NLUResult
from pipelines.asr_pipeline import ASRPipeline, ASRResult
from pipelines.nlu_pipeline_service import NLUPipeline


@pytest.fixture()
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
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
        processing_time_ms=150.0,
    )

    return mock


@pytest.fixture()
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
        entities=[Entity(entity_type="ACTION", value="teste", confidence=0.9, start=0, end=5)],
        keywords=["teste", "intenção"],
        processing_time_ms=80.0,
    )

    return mock


@pytest.fixture()
def mock_kafka_producer() -> AsyncMock:
    """Mock do producer Kafka"""
    mock = AsyncMock(spec=KafkaIntentProducer)

    # Configure default return values
    mock.is_ready.return_value = True
    mock.initialize.return_value = None
    mock.close.return_value = None
    mock.send_intent.return_value = None

    return mock


@pytest.fixture()
def sample_intent_request() -> IntentRequest:
    """Request de intenção de exemplo"""
    return IntentRequest(
        text="Preciso implementar um novo recurso de autenticação",
        language="pt-BR",
        correlation_id="test-correlation-123",
    )


@pytest.fixture()
def sample_user_context() -> dict[str, Any]:
    """Contexto do usuário de exemplo"""
    return {
        "userId": "user-123",
        "tenantId": "tenant-456",
        "sessionId": "session-789",
        "userName": "Usuário Teste",
    }


@pytest.fixture()
def sample_intent_envelope(sample_user_context) -> IntentEnvelope:
    """Envelope de intenção de exemplo"""
    from datetime import datetime

    return IntentEnvelope(
        id="intent-123",
        correlation_id="correlation-456",
        actor={
            "id": sample_user_context["userId"],
            "actor_type": "human",
            "name": sample_user_context["userName"],
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
                    "end": 11,
                }
            ],
            "keywords": ["implementar", "autenticação"],
        },
        confidence=0.85,
        context=sample_user_context,
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture()
def audio_file_mock():
    """Mock de arquivo de áudio"""
    mock = MagicMock()
    mock.content_type = "audio/wav"
    mock.size = 1024 * 50  # 50KB
    mock.read = AsyncMock(return_value=b"fake-audio-content")
    return mock


@pytest.fixture()
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
        max_text_length=10000,
    )
    return settings
