"""
Testes unitários para ApprovalResponseConsumer

Testa deserialização de mensagens, extração de trace context,
inicialização e health check do consumer.
"""

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch


class TestApprovalResponseConsumerDeserialization:
    """Testes para deserialização de mensagens"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.kafka_bootstrap_servers = 'localhost:9092'
        settings.kafka_consumer_group_id = 'semantic-translation-engine'
        settings.kafka_auto_offset_reset = 'earliest'
        settings.kafka_session_timeout_ms = 30000
        settings.kafka_security_protocol = 'PLAINTEXT'
        settings.kafka_approval_responses_topic = 'cognitive-plans-approval-responses'
        settings.schema_registry_url = None
        return settings

    @pytest.fixture
    def consumer(self, settings):
        """Create consumer instance (sem inicializar Kafka)"""
        from src.consumers.approval_response_consumer import ApprovalResponseConsumer
        return ApprovalResponseConsumer(settings)

    def test_deserialize_json_message(self, consumer):
        """Deserialização JSON deve funcionar corretamente"""
        approval_response = {
            'plan_id': 'plan-123',
            'intent_id': 'intent-456',
            'decision': 'approved',
            'approved_by': 'user@example.com',
            'approved_at': 1705000000000
        }

        mock_msg = MagicMock()
        mock_msg.headers.return_value = [
            ('content-type', b'application/json')
        ]
        mock_msg.value.return_value = json.dumps(approval_response).encode('utf-8')

        result = consumer._deserialize_message(mock_msg)

        assert result['plan_id'] == 'plan-123'
        assert result['intent_id'] == 'intent-456'
        assert result['decision'] == 'approved'
        assert result['approved_by'] == 'user@example.com'

    def test_deserialize_json_fallback_without_content_type(self, consumer):
        """Fallback para JSON quando content-type ausente"""
        approval_response = {
            'plan_id': 'plan-123',
            'decision': 'rejected',
            'rejection_reason': 'Risco muito alto'
        }

        mock_msg = MagicMock()
        mock_msg.headers.return_value = []
        mock_msg.value.return_value = json.dumps(approval_response).encode('utf-8')

        result = consumer._deserialize_message(mock_msg)

        assert result['plan_id'] == 'plan-123'
        assert result['decision'] == 'rejected'
        assert result['rejection_reason'] == 'Risco muito alto'

    def test_deserialize_parses_cognitive_plan_json(self, consumer):
        """cognitive_plan_json deve ser parseado para dict"""
        cognitive_plan = {
            'plan_id': 'plan-123',
            'tasks': [],
            'risk_score': 0.8
        }
        approval_response = {
            'plan_id': 'plan-123',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': 1705000000000,
            'cognitive_plan_json': json.dumps(cognitive_plan)
        }

        mock_msg = MagicMock()
        mock_msg.headers.return_value = []
        mock_msg.value.return_value = json.dumps(approval_response).encode('utf-8')

        result = consumer._deserialize_message(mock_msg)

        assert result['cognitive_plan'] is not None
        assert result['cognitive_plan']['plan_id'] == 'plan-123'
        assert result['cognitive_plan']['risk_score'] == 0.8

    def test_deserialize_handles_invalid_cognitive_plan_json(self, consumer):
        """cognitive_plan_json inválido não deve causar erro"""
        approval_response = {
            'plan_id': 'plan-123',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': 1705000000000,
            'cognitive_plan_json': 'invalid json {'
        }

        mock_msg = MagicMock()
        mock_msg.headers.return_value = []
        mock_msg.value.return_value = json.dumps(approval_response).encode('utf-8')

        result = consumer._deserialize_message(mock_msg)

        assert result['plan_id'] == 'plan-123'
        assert result['cognitive_plan'] is None


class TestApprovalResponseConsumerTraceContext:
    """Testes para extração de trace context"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.kafka_bootstrap_servers = 'localhost:9092'
        settings.kafka_consumer_group_id = 'semantic-translation-engine'
        settings.kafka_auto_offset_reset = 'earliest'
        settings.kafka_session_timeout_ms = 30000
        settings.kafka_security_protocol = 'PLAINTEXT'
        settings.kafka_approval_responses_topic = 'cognitive-plans-approval-responses'
        settings.schema_registry_url = None
        return settings

    @pytest.fixture
    def consumer(self, settings):
        """Create consumer instance"""
        from src.consumers.approval_response_consumer import ApprovalResponseConsumer
        return ApprovalResponseConsumer(settings)

    def test_extract_trace_context_all_headers(self, consumer):
        """Extrai todos os headers de trace"""
        headers = [
            ('trace-id', b'trace-abc123'),
            ('span-id', b'span-def456'),
            ('correlation-id', b'corr-ghi789')
        ]

        result = consumer._extract_trace_context(headers)

        assert result['trace_id'] == 'trace-abc123'
        assert result['span_id'] == 'span-def456'
        assert result['correlation_id'] == 'corr-ghi789'

    def test_extract_trace_context_partial_headers(self, consumer):
        """Extrai apenas headers presentes"""
        headers = [
            ('correlation-id', b'corr-only')
        ]

        result = consumer._extract_trace_context(headers)

        assert result.get('correlation_id') == 'corr-only'
        assert 'trace_id' not in result
        assert 'span_id' not in result

    def test_extract_trace_context_empty_headers(self, consumer):
        """Lista vazia de headers retorna dict vazio"""
        result = consumer._extract_trace_context([])

        assert result == {}


class TestApprovalResponseConsumerHealthCheck:
    """Testes para health check do consumer"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.kafka_bootstrap_servers = 'localhost:9092'
        settings.kafka_consumer_group_id = 'semantic-translation-engine'
        settings.kafka_auto_offset_reset = 'earliest'
        settings.kafka_session_timeout_ms = 30000
        settings.kafka_security_protocol = 'PLAINTEXT'
        settings.kafka_approval_responses_topic = 'cognitive-plans-approval-responses'
        settings.schema_registry_url = None
        return settings

    @pytest.fixture
    def consumer(self, settings):
        """Create consumer instance"""
        from src.consumers.approval_response_consumer import ApprovalResponseConsumer
        return ApprovalResponseConsumer(settings)

    def test_is_healthy_not_running(self, consumer):
        """Consumer não running deve ser não saudável"""
        consumer.running = False
        consumer.consumer = MagicMock()

        is_healthy, reason = consumer.is_healthy()

        assert is_healthy is False
        assert 'running' in reason.lower()

    def test_is_healthy_no_consumer(self, consumer):
        """Consumer não inicializado deve ser não saudável"""
        consumer.running = True
        consumer.consumer = None

        is_healthy, reason = consumer.is_healthy()

        assert is_healthy is False
        assert 'inicializado' in reason.lower()

    def test_is_healthy_no_poll_time(self, consumer):
        """Consumer sem poll deve ser não saudável"""
        consumer.running = True
        consumer.consumer = MagicMock()
        consumer.last_poll_time = None

        is_healthy, reason = consumer.is_healthy()

        assert is_healthy is False
        assert 'polling' in reason.lower()

    def test_is_healthy_stale_poll(self, consumer):
        """Poll antigo deve indicar não saudável"""
        import time

        consumer.running = True
        consumer.consumer = MagicMock()
        consumer.last_poll_time = time.time() - 120  # 2 minutos atrás

        is_healthy, reason = consumer.is_healthy(max_poll_age_seconds=60)

        assert is_healthy is False
        assert 'poll' in reason.lower()

    def test_is_healthy_active_consumer(self, consumer):
        """Consumer ativo deve ser saudável"""
        import time

        consumer.running = True
        consumer.consumer = MagicMock()
        consumer.last_poll_time = time.time() - 5  # 5 segundos atrás
        consumer.messages_processed = 10

        is_healthy, reason = consumer.is_healthy(max_poll_age_seconds=60)

        assert is_healthy is True
        assert 'ativo' in reason.lower()


class TestApprovalResponseConsumerConfiguration:
    """Testes para configuração do consumer"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.kafka_bootstrap_servers = 'kafka:9092'
        settings.kafka_consumer_group_id = 'ste-group'
        settings.kafka_auto_offset_reset = 'latest'
        settings.kafka_session_timeout_ms = 45000
        settings.kafka_security_protocol = 'PLAINTEXT'
        settings.kafka_approval_responses_topic = 'approval-responses'
        settings.schema_registry_url = 'http://schema-registry:8081'
        return settings

    def test_consumer_group_suffix(self, settings):
        """Consumer group deve ter sufixo -approval-responses"""
        from src.consumers.approval_response_consumer import ApprovalResponseConsumer
        consumer = ApprovalResponseConsumer(settings)

        assert consumer._consumer_group == 'ste-group-approval-responses'

    def test_topic_from_settings(self, settings):
        """Topic deve vir do settings"""
        from src.consumers.approval_response_consumer import ApprovalResponseConsumer
        consumer = ApprovalResponseConsumer(settings)

        assert consumer._topic == 'approval-responses'
