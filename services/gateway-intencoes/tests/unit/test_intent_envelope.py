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
            actor={"id": "user-123", "actor_type": "human", "name": "Test User"},
            intent={
                "text": "test intent",
                "domain": "BUSINESS",
                "classification": "request",
                "original_language": "pt-BR",
                "processed_text": "test intent processed",
                "entities": [],
                "keywords": ["test"],
            },
            confidence=0.85,
            context=sample_user_context,
            timestamp=datetime.now(timezone.utc),
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
            actor={"id": "user-123", "actor_type": "human"},
            intent={
                "text": "test",
                "domain": "BUSINESS",
                "classification": "request",
                "entities": [],
                "keywords": [],
            },
            confidence=0.85,
            timestamp=datetime.now(timezone.utc),
        )

        partition_key = envelope.get_partition_key()
        assert partition_key == "user-123"

    def test_intent_envelope_idempotency_key(self):
        """Teste da geração de chave de idempotência"""
        envelope = IntentEnvelope(
            id="test-id-123",
            correlation_id="test-correlation",
            actor={"id": "user-123", "actor_type": "human"},
            intent={
                "text": "test",
                "domain": "BUSINESS",
                "classification": "request",
                "entities": [],
                "keywords": [],
            },
            confidence=0.85,
            timestamp=datetime.now(timezone.utc),
        )

        idempotency_key = envelope.get_idempotency_key()
        assert idempotency_key == "test-id-123"

    def test_intent_envelope_to_avro_dict(self, sample_user_context):
        """Teste de serialização para Avro"""
        timestamp = datetime.now(timezone.utc)
        envelope = IntentEnvelope(
            id="test-id",
            correlation_id="test-correlation",
            actor={"id": "user-123", "actor_type": "human", "name": "Test User"},
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
                        "end": 4,
                    }
                ],
                "keywords": ["test", "intent"],
            },
            confidence=0.85,
            context=sample_user_context,
            timestamp=timestamp,
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
                timestamp=datetime.now(timezone.utc),
            )

    def test_confidence_bounds(self):
        """Teste dos limites de confiança"""
        # Test valid confidence values
        envelope = IntentEnvelope(
            id="test-id",
            actor={"id": "user-123", "actor_type": "human"},
            intent={
                "text": "test",
                "domain": "BUSINESS",
                "classification": "request",
                "entities": [],
                "keywords": [],
            },
            confidence=0.5,  # Valid range [0, 1]
            timestamp=datetime.now(timezone.utc),
        )
        assert 0.0 <= envelope.confidence <= 1.0

        # Test boundary values
        envelope_min = IntentEnvelope(
            id="test-id-min",
            actor={"id": "user-123", "actor_type": "human"},
            intent={
                "text": "test",
                "domain": "BUSINESS",
                "classification": "request",
                "entities": [],
                "keywords": [],
            },
            confidence=0.0,
            timestamp=datetime.now(timezone.utc),
        )
        assert envelope_min.confidence == 0.0

        envelope_max = IntentEnvelope(
            id="test-id-max",
            actor={"id": "user-123", "actor_type": "human"},
            intent={
                "text": "test",
                "domain": "BUSINESS",
                "classification": "request",
                "entities": [],
                "keywords": [],
            },
            confidence=1.0,
            timestamp=datetime.now(timezone.utc),
        )
        assert envelope_max.confidence == 1.0


class TestIntentRequest:
    """Testes para a classe IntentRequest"""

    def test_intent_request_creation(self):
        """Teste de criação do request de intenção"""
        request = IntentRequest(
            text="Implementar nova funcionalidade",
            language="pt-BR",
            correlation_id="correlation-123",
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
            audio_file=audio_file_mock, language="pt-BR", correlation_id="voice-correlation-123"
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


class TestSecurityValidation:
    """Testes de validação de segurança para IntentRequest"""

    def test_text_with_xss_script_tag_rejected(self):
        """XSS com <script> deve ser rejeitado."""
        with pytest.raises(ValueError, match="padrão potencialmente perigoso"):
            IntentRequest(text="<script>alert('xss')</script> teste")

    def test_text_with_javascript_uri_rejected(self):
        """javascript: URI deve ser rejeitado."""
        with pytest.raises(ValueError, match="padrão potencialmente perigoso"):
            IntentRequest(text="click here javascript:alert('xss')")

    def test_text_with_onerror_rejected(self):
        """Event handler onerror deve ser rejeitado."""
        with pytest.raises(ValueError, match="padrão potencialmente perigoso"):
            IntentRequest(text="<img src=x onerror=alert('xss')>")

    def test_text_with_eval_rejected(self):
        """Função eval() deve ser rejeitada."""
        with pytest.raises(ValueError, match="padrão potencialmente perigoso"):
            IntentRequest(text="test text with eval(malicious_code)")

    def test_text_with_exec_rejected(self):
        """Função exec() deve ser rejeitada."""
        with pytest.raises(ValueError, match="padrão potencialmente perigoso"):
            IntentRequest(text="test text with exec('malicious')")

    def test_text_with_template_injection_dollar_rejected(self):
        """Template injection ${} deve ser rejeitado."""
        with pytest.raises(ValueError, match="padrão potencialmente perigoso"):
            IntentRequest(text="test text ${malicious_code}")

    def test_text_with_template_injection_hash_rejected(self):
        """Template injection #{} deve ser rejeitado."""
        with pytest.raises(ValueError, match="padrão potencialmente perigoso"):
            IntentRequest(text="test text #{malicious_code}")

    def test_text_with_null_bytes_sanitized(self):
        """Null bytes devem ser removidos."""
        request = IntentRequest(text="test\x00text")
        assert "\x00" not in request.text
        assert request.text == "testtext"

    def test_empty_text_rejected(self):
        """Texto vazio deve ser rejeitado."""
        # Pydantic levanta ValidationError para campos com tamanho mínimo
        with pytest.raises((ValueError, Exception)):  # ValidationError herda de Exception
            IntentRequest(text="")

    def test_whitespace_only_text_rejected(self):
        """Apenas whitespace deve ser rejeitado."""
        with pytest.raises(ValueError, match="não pode ser vazio"):
            IntentRequest(text="   \t\n   ")

    def test_invalid_language_rejected(self):
        """Idiomas inválidos devem ser rejeitados."""
        with pytest.raises(ValueError, match="não é suportado"):
            IntentRequest(text="test text", language="xx-YY")

    def test_valid_language_accepted(self):
        """Idiomas válidos devem ser aceitos."""
        valid_languages = ["pt-BR", "pt-PT", "pt", "en-US", "en-GB", "en", "es-ES", "es"]
        for lang in valid_languages:
            request = IntentRequest(text="test text", language=lang)
            assert request.language == lang

    def test_invalid_correlation_id_rejected(self):
        """UUIDs inválidos devem ser rejeitados."""
        with pytest.raises(ValueError, match="UUID válido"):
            IntentRequest(text="test text", correlation_id="not-a-uuid")

    def test_valid_correlation_id_accepted(self):
        """UUIDs válidos devem ser aceitos."""
        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        request = IntentRequest(text="test text", correlation_id=valid_uuid)
        assert request.correlation_id == valid_uuid

    def test_none_correlation_id_accepted(self):
        """correlation_id None deve ser aceito."""
        request = IntentRequest(text="test text", correlation_id=None)
        assert request.correlation_id is None


class TestVoiceSecurityValidation:
    """Testes de validação de segurança para VoiceIntentRequest"""

    def test_voice_invalid_language_rejected(self):
        """Idiomas inválidos devem ser rejeitados."""
        with pytest.raises(ValueError, match="não é suportado"):
            VoiceIntentRequest(language="xx-YY")

    def test_voice_valid_language_accepted(self):
        """Idiomas válidos devem ser aceitos."""
        valid_languages = ["pt-BR", "en-US", "es-ES"]
        for lang in valid_languages:
            request = VoiceIntentRequest(language=lang)
            assert request.language == lang

    def test_voice_invalid_correlation_id_rejected(self):
        """UUIDs inválidos devem ser rejeitados."""
        with pytest.raises(ValueError, match="UUID válido"):
            VoiceIntentRequest(correlation_id="not-a-uuid")
