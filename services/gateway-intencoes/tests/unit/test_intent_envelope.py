"""Testes unitários para o modelo IntentEnvelope"""
import pytest
from datetime import datetime, timezone
from typing import Dict, Any
import json

from models.intent_envelope import IntentEnvelope, IntentRequest, VoiceIntentRequest


class TestIntentEnvelope:
    """Testes para a classe IntentEnvelope"""

    def test_intent_envelope_creation(self, sample_user_context):
        """Teste de criação básica do envelope"""
        envelope = IntentEnvelope(
            id="test-id",
            correlation_id="test-correlation",
            actor={
                "id": "user-123",
                "actor_type": "human",
                "name": "Test User"
            },
            intent={
                "text": "test intent",
                "domain": "BUSINESS",
                "classification": "request",
                "original_language": "pt-BR",
                "processed_text": "test intent processed",
                "entities": [],
                "keywords": ["test"]
            },
            confidence=0.85,
            context=sample_user_context,
            timestamp=datetime.now(timezone.utc)
        )

        assert envelope.id == "test-id"
        assert envelope.correlation_id == "test-correlation"
        assert envelope.actor["id"] == "user-123"
        assert envelope.intent["text"] == "test intent"
        assert envelope.confidence == 0.85

    def test_intent_envelope_partition_key(self):
        """Teste da geração de chave de partição"""
        envelope = IntentEnvelope(
            id="test-id",
            correlation_id="test-correlation",
            actor={
                "id": "user-123",
                "actor_type": "human"
            },
            intent={
                "text": "test",
                "domain": "BUSINESS",
                "classification": "request",
                "entities": [],
                "keywords": []
            },
            confidence=0.85,
            timestamp=datetime.now(timezone.utc)
        )

        partition_key = envelope.get_partition_key()
        assert partition_key == "user-123"

    def test_intent_envelope_idempotency_key(self):
        """Teste da geração de chave de idempotência"""
        envelope = IntentEnvelope(
            id="test-id-123",
            correlation_id="test-correlation",
            actor={
                "id": "user-123",
                "actor_type": "human"
            },
            intent={
                "text": "test",
                "domain": "BUSINESS",
                "classification": "request",
                "entities": [],
                "keywords": []
            },
            confidence=0.85,
            timestamp=datetime.now(timezone.utc)
        )

        idempotency_key = envelope.get_idempotency_key()
        assert idempotency_key == "test-id-123"

    def test_intent_envelope_to_avro_dict(self, sample_user_context):
        """Teste de serialização para Avro"""
        timestamp = datetime.now(timezone.utc)
        envelope = IntentEnvelope(
            id="test-id",
            correlation_id="test-correlation",
            actor={
                "id": "user-123",
                "actor_type": "human",
                "name": "Test User"
            },
            intent={
                "text": "test intent",
                "domain": "BUSINESS",
                "classification": "request",
                "original_language": "pt-BR",
                "processed_text": "test intent processed",
                "entities": [
                    {
                        "entity_type": "ACTION",
                        "value": "test",
                        "confidence": 0.9,
                        "start": 0,
                        "end": 4
                    }
                ],
                "keywords": ["test", "intent"]
            },
            confidence=0.85,
            context=sample_user_context,
            timestamp=timestamp
        )

        avro_dict = envelope.to_avro_dict()

        assert avro_dict["id"] == "test-id"
        assert avro_dict["correlationId"] == "test-correlation"
        assert avro_dict["actor"]["id"] == "user-123"
        assert avro_dict["actor"]["actorType"] == "HUMAN"
        assert avro_dict["intent"]["domain"] == "BUSINESS"
        assert avro_dict["confidence"] == 0.85
        assert avro_dict["timestamp"] == int(timestamp.timestamp() * 1000)

    def test_intent_envelope_validation_errors(self):
        """Teste de validação de campos obrigatórios"""
        with pytest.raises((ValueError, TypeError)):
            IntentEnvelope(
                # Missing required fields
                id="",
                timestamp=datetime.now(timezone.utc)
            )

    def test_confidence_bounds(self):
        """Teste dos limites de confiança"""
        # Test valid confidence values
        envelope = IntentEnvelope(
            id="test-id",
            actor={
                "id": "user-123",
                "actor_type": "human"
            },
            intent={
                "text": "test",
                "domain": "BUSINESS",
                "classification": "request",
                "entities": [],
                "keywords": []
            },
            confidence=0.5,  # Valid range [0, 1]
            timestamp=datetime.now(timezone.utc)
        )
        assert 0.0 <= envelope.confidence <= 1.0

        # Test boundary values
        envelope_min = IntentEnvelope(
            id="test-id-min",
            actor={
                "id": "user-123",
                "actor_type": "human"
            },
            intent={
                "text": "test",
                "domain": "BUSINESS",
                "classification": "request",
                "entities": [],
                "keywords": []
            },
            confidence=0.0,
            timestamp=datetime.now(timezone.utc)
        )
        assert envelope_min.confidence == 0.0

        envelope_max = IntentEnvelope(
            id="test-id-max",
            actor={
                "id": "user-123",
                "actor_type": "human"
            },
            intent={
                "text": "test",
                "domain": "BUSINESS",
                "classification": "request",
                "entities": [],
                "keywords": []
            },
            confidence=1.0,
            timestamp=datetime.now(timezone.utc)
        )
        assert envelope_max.confidence == 1.0


class TestIntentRequest:
    """Testes para a classe IntentRequest"""

    def test_intent_request_creation(self):
        """Teste de criação do request de intenção"""
        request = IntentRequest(
            text="Implementar nova funcionalidade",
            language="pt-BR",
            correlation_id="correlation-123"
        )

        assert request.text == "Implementar nova funcionalidade"
        assert request.language == "pt-BR"
        assert request.correlation_id == "correlation-123"

    def test_intent_request_defaults(self):
        """Teste dos valores padrão"""
        request = IntentRequest(text="test text")

        assert request.text == "test text"
        assert request.language == "pt-BR"  # Default
        assert request.correlation_id is None
        assert request.constraints is None
        assert request.qos is None

    def test_intent_request_validation(self):
        """Teste de validação de campos obrigatórios"""
        # Valid request
        request = IntentRequest(text="valid text")
        assert len(request.text.strip()) > 0

        # Invalid request - empty text
        with pytest.raises(ValueError):
            IntentRequest(text="")

        # Invalid request - whitespace only
        with pytest.raises(ValueError):
            IntentRequest(text="   ")


class TestVoiceIntentRequest:
    """Testes para a classe VoiceIntentRequest"""

    def test_voice_intent_request_creation(self, audio_file_mock):
        """Teste de criação do request de voz"""
        request = VoiceIntentRequest(
            audio_file=audio_file_mock,
            language="pt-BR",
            correlation_id="voice-correlation-123"
        )

        assert request.audio_file == audio_file_mock
        assert request.language == "pt-BR"
        assert request.correlation_id == "voice-correlation-123"

    def test_voice_intent_request_defaults(self, audio_file_mock):
        """Teste dos valores padrão para voice request"""
        request = VoiceIntentRequest(audio_file=audio_file_mock)

        assert request.audio_file == audio_file_mock
        assert request.language == "pt-BR"  # Default
        assert request.correlation_id is None

    def test_voice_request_validation(self):
        """Teste de validação do arquivo de áudio"""
        # Invalid request - no audio file
        with pytest.raises((ValueError, TypeError)):
            VoiceIntentRequest(audio_file=None)