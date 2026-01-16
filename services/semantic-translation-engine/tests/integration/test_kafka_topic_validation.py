"""
Testes de integração para validação de tópicos Kafka.

Testa a função validate_kafka_topics_exist() que implementa
validação fail-fast de tópicos durante o startup do serviço.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestKafkaTopicValidation:
    """Testes para validação de tópicos Kafka no startup."""

    @pytest.fixture
    def mock_settings(self):
        """Settings mock com configuração padrão."""
        settings = MagicMock()
        settings.kafka_bootstrap_servers = 'localhost:9092'
        settings.kafka_topics = [
            'intentions.business',
            'intentions.technical',
            'intentions.infrastructure'
        ]
        settings.kafka_security_protocol = 'PLAINTEXT'
        settings.kafka_sasl_mechanism = None
        settings.kafka_sasl_username = None
        settings.kafka_sasl_password = None
        return settings

    @pytest.fixture
    def mock_cluster_metadata_with_topics(self):
        """Mock de metadados do cluster com tópicos existentes."""
        metadata = MagicMock()
        metadata.topics = {
            'intentions.business': MagicMock(),
            'intentions.technical': MagicMock(),
            'intentions.infrastructure': MagicMock(),
            'intentions.security': MagicMock(),
            'plans.ready': MagicMock(),
        }
        return metadata

    @pytest.fixture
    def mock_cluster_metadata_missing_topics(self):
        """Mock de metadados do cluster sem alguns tópicos."""
        metadata = MagicMock()
        metadata.topics = {
            'intentions.business': MagicMock(),
            'plans.ready': MagicMock(),
            'other.topic': MagicMock(),
        }
        return metadata

    @pytest.mark.asyncio
    async def test_validate_kafka_topics_exist_raises_on_missing_topics(
        self, mock_settings, mock_cluster_metadata_missing_topics
    ):
        """Verifica que RuntimeError é lançado quando tópicos estão ausentes."""
        from src.main import validate_kafka_topics_exist

        with patch('src.main.AdminClient') as MockAdminClient:
            mock_admin = MagicMock()
            mock_admin.list_topics.return_value = mock_cluster_metadata_missing_topics
            MockAdminClient.return_value = mock_admin

            with pytest.raises(RuntimeError) as exc_info:
                await validate_kafka_topics_exist(mock_settings)

            # Verifica mensagem de erro contém tópicos faltantes
            error_msg = str(exc_info.value)
            assert 'intentions.technical' in error_msg or 'intentions.infrastructure' in error_msg
            assert 'Tópicos Kafka obrigatórios não encontrados' in error_msg

    @pytest.mark.asyncio
    async def test_validate_kafka_topics_exist_succeeds_when_all_exist(
        self, mock_settings, mock_cluster_metadata_with_topics
    ):
        """Verifica que nenhuma exceção é lançada quando todos os tópicos existem."""
        from src.main import validate_kafka_topics_exist

        with patch('src.main.AdminClient') as MockAdminClient:
            mock_admin = MagicMock()
            mock_admin.list_topics.return_value = mock_cluster_metadata_with_topics
            MockAdminClient.return_value = mock_admin

            # Não deve lançar exceção
            await validate_kafka_topics_exist(mock_settings)

            # Verifica que AdminClient foi chamado corretamente
            MockAdminClient.assert_called_once()
            mock_admin.list_topics.assert_called_once_with(timeout=10)

    @pytest.mark.asyncio
    async def test_validate_kafka_topics_exist_handles_connection_error(
        self, mock_settings
    ):
        """Verifica tratamento de erro de conexão com Kafka."""
        from src.main import validate_kafka_topics_exist

        with patch('src.main.AdminClient') as MockAdminClient:
            mock_admin = MagicMock()
            mock_admin.list_topics.side_effect = Exception('Connection refused')
            MockAdminClient.return_value = mock_admin

            with pytest.raises(RuntimeError) as exc_info:
                await validate_kafka_topics_exist(mock_settings)

            error_msg = str(exc_info.value)
            assert 'Não foi possível conectar ao Kafka' in error_msg
            assert 'Connection refused' in error_msg

    @pytest.mark.asyncio
    async def test_validate_kafka_topics_with_security_config(self):
        """Verifica que configurações de segurança são passadas ao AdminClient."""
        from src.main import validate_kafka_topics_exist

        settings = MagicMock()
        settings.kafka_bootstrap_servers = 'localhost:9092'
        settings.kafka_topics = ['test.topic']
        settings.kafka_security_protocol = 'SASL_SSL'
        settings.kafka_sasl_mechanism = 'PLAIN'
        settings.kafka_sasl_username = 'user'
        settings.kafka_sasl_password = 'password'

        metadata = MagicMock()
        metadata.topics = {'test.topic': MagicMock()}

        with patch('src.main.AdminClient') as MockAdminClient:
            mock_admin = MagicMock()
            mock_admin.list_topics.return_value = metadata
            MockAdminClient.return_value = mock_admin

            await validate_kafka_topics_exist(settings)

            # Verifica que AdminClient foi criado com config de segurança
            call_args = MockAdminClient.call_args[0][0]
            assert call_args['security.protocol'] == 'SASL_SSL'
            assert call_args['sasl.mechanism'] == 'PLAIN'
            assert call_args['sasl.username'] == 'user'
            assert call_args['sasl.password'] == 'password'

    @pytest.mark.asyncio
    async def test_validate_kafka_topics_logs_available_topics_on_error(
        self, mock_settings
    ):
        """Verifica que logs incluem tópicos disponíveis quando há erro."""
        from src.main import validate_kafka_topics_exist

        metadata = MagicMock()
        metadata.topics = {
            'available.topic.1': MagicMock(),
            'available.topic.2': MagicMock(),
        }

        with patch('src.main.AdminClient') as MockAdminClient:
            mock_admin = MagicMock()
            mock_admin.list_topics.return_value = metadata
            MockAdminClient.return_value = mock_admin

            with patch('src.main.logger') as mock_logger:
                with pytest.raises(RuntimeError):
                    await validate_kafka_topics_exist(mock_settings)

                # Verifica que logger.error foi chamado com campos corretos
                mock_logger.error.assert_called()
                call_kwargs = mock_logger.error.call_args[1]
                assert 'missing_topics' in call_kwargs
                assert 'configured_topics' in call_kwargs
                assert 'available_topics' in call_kwargs
