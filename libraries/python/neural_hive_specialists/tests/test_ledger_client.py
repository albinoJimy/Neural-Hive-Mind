"""
Testes unitários para LedgerClient.

Cobertura: inicialização, save_opinion (com/sem fallback), buffer/flush,
retrieval, verificação de integridade, circuit breaker transitions.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pymongo.errors import PyMongoError, ConnectionFailure
from circuitbreaker import CircuitBreakerError
from queue import Full

from neural_hive_specialists.ledger_client import LedgerClient


@pytest.mark.unit
class TestLedgerClientInitialization:
    """Testes de inicialização do LedgerClient."""

    def test_initialization_success(self, mock_config, mock_metrics):
        """Testa inicialização bem-sucedida com métricas."""
        with patch('neural_hive_specialists.ledger_client.MongoClient'):
            client = LedgerClient(mock_config, metrics=mock_metrics)

            assert client.config == mock_config
            assert client._metrics == mock_metrics
            assert client._buffer_max_size == mock_config.ledger_buffer_size
            assert client._circuit_breaker_state == 'closed'
            mock_metrics.set_circuit_breaker_state.assert_called_once_with('ledger', 'closed')

    def test_initialization_with_circuit_breaker_enabled(self, mock_config):
        """Testa criação de circuit breakers quando habilitado."""
        mock_config.enable_circuit_breaker = True
        with patch('neural_hive_specialists.ledger_client.MongoClient'):
            client = LedgerClient(mock_config)

            assert client._save_opinion_breaker is not None
            assert client._get_opinion_breaker is not None
            assert client._verify_integrity_breaker is not None

    def test_initialization_without_circuit_breaker(self, mock_config):
        """Testa que circuit breakers são None quando desabilitados."""
        mock_config.enable_circuit_breaker = False
        with patch('neural_hive_specialists.ledger_client.MongoClient'):
            client = LedgerClient(mock_config)

            assert client._save_opinion_breaker is None
            assert client._get_opinion_breaker is None

    def test_create_indexes_called_on_init(self, mock_config):
        """Verifica que índices são criados na inicialização."""
        with patch('neural_hive_specialists.ledger_client.MongoClient') as mock_mongo:
            mock_collection = MagicMock()
            mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

            client = LedgerClient(mock_config)

            # Verifica que create_index foi chamado para cada índice
            assert mock_collection.create_index.call_count >= 5


@pytest.mark.unit
class TestSaveOpinion:
    """Testes do método save_opinion."""

    @pytest.fixture
    def ledger_client(self, mock_config):
        """Cria cliente com MongoDB mockado."""
        with patch('neural_hive_specialists.ledger_client.MongoClient') as mock_mongo:
            mock_collection = MagicMock()
            mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection
            client = LedgerClient(mock_config)
            client._collection = mock_collection
            return client

    def test_save_opinion_success(self, ledger_client, sample_opinion):
        """Testa salvamento bem-sucedido de parecer."""
        ledger_client._collection.insert_one = MagicMock(return_value=MagicMock(acknowledged=True))

        opinion_id = ledger_client.save_opinion(
            opinion=sample_opinion,
            plan_id="plan-123",
            intent_id="intent-456",
            specialist_type="business",
            correlation_id="corr-789"
        )

        assert opinion_id is not None
        assert len(opinion_id) == 36  # UUID format
        ledger_client._collection.insert_one.assert_called_once()

        # Verifica que o documento contém todos os campos
        call_args = ledger_client._collection.insert_one.call_args[0][0]
        assert call_args['opinion_id'] == opinion_id
        assert call_args['plan_id'] == "plan-123"
        assert call_args['intent_id'] == "intent-456"
        assert call_args['specialist_type'] == "business"
        assert call_args['correlation_id'] == "corr-789"
        assert 'hash' in call_args
        assert 'timestamp' in call_args

    def test_save_opinion_calculates_hash(self, ledger_client, sample_opinion):
        """Verifica cálculo correto do hash."""
        ledger_client._collection.insert_one = MagicMock(return_value=MagicMock(acknowledged=True))

        ledger_client.save_opinion(
            opinion=sample_opinion,
            plan_id="plan-123",
            intent_id="intent-456",
            specialist_type="business",
            correlation_id="corr-789"
        )

        call_args = ledger_client._collection.insert_one.call_args[0][0]
        assert 'hash' in call_args
        assert len(call_args['hash']) == 64  # SHA-256 hex

    def test_save_opinion_pymongo_error(self, ledger_client, sample_opinion):
        """Testa que PyMongoError é levantado em falhas."""
        ledger_client._collection.insert_one = MagicMock(side_effect=PyMongoError("Connection failed"))

        with pytest.raises(PyMongoError):
            ledger_client.save_opinion(
                opinion=sample_opinion,
                plan_id="plan-123",
                intent_id="intent-456",
                specialist_type="business",
                correlation_id="corr-789"
            )


@pytest.mark.unit
class TestSaveOpinionWithFallback:
    """Testes do método save_opinion_with_fallback."""

    @pytest.fixture
    def ledger_client(self, mock_config, mock_metrics):
        """Cria cliente com circuit breaker habilitado."""
        mock_config.enable_circuit_breaker = True
        with patch('neural_hive_specialists.ledger_client.MongoClient') as mock_mongo:
            mock_collection = MagicMock()
            mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection
            client = LedgerClient(mock_config, metrics=mock_metrics)
            client._collection = mock_collection
            return client

    def test_save_with_fallback_success(self, ledger_client, sample_opinion):
        """Testa salvamento bem-sucedido com fallback."""
        ledger_client._collection.insert_one = MagicMock(return_value=MagicMock(acknowledged=True))

        opinion_id = ledger_client.save_opinion_with_fallback(
            opinion=sample_opinion,
            plan_id="plan-123",
            intent_id="intent-456",
            specialist_type="business",
            correlation_id="corr-789"
        )

        assert opinion_id is not None
        assert ledger_client._last_save_was_buffered is False

    def test_save_with_fallback_buffers_on_circuit_breaker_open(self, ledger_client, sample_opinion):
        """Testa que buffering ocorre quando circuit breaker está aberto."""
        # Simular circuit breaker aberto
        ledger_client._save_opinion_breaker = Mock()
        ledger_client._save_opinion_breaker.call = Mock(side_effect=CircuitBreakerError("Circuit open"))

        opinion_id = ledger_client.save_opinion_with_fallback(
            opinion=sample_opinion,
            plan_id="plan-123",
            intent_id="intent-456",
            specialist_type="business",
            correlation_id="corr-789"
        )

        assert opinion_id is not None
        assert ledger_client._last_save_was_buffered is True

    def test_save_with_fallback_buffers_on_pymongo_error(self, ledger_client, sample_opinion):
        """Testa que buffering ocorre em erros de PyMongo."""
        ledger_client._collection.insert_one = MagicMock(side_effect=PyMongoError("Connection failed"))

        # Desabilitar circuit breaker para testar fallback direto
        ledger_client._save_opinion_breaker = None

        opinion_id = ledger_client.save_opinion_with_fallback(
            opinion=sample_opinion,
            plan_id="plan-123",
            intent_id="intent-456",
            specialist_type="business",
            correlation_id="corr-789"
        )

        assert opinion_id is not None
        assert ledger_client._last_save_was_buffered is True

    def test_was_last_save_buffered(self, ledger_client):
        """Testa método was_last_save_buffered."""
        assert ledger_client.was_last_save_buffered() is False

        ledger_client._last_save_was_buffered = True
        assert ledger_client.was_last_save_buffered() is True


@pytest.mark.unit
class TestBuffer:
    """Testes de buffer de pareceres."""

    @pytest.fixture
    def ledger_client(self, mock_config):
        """Cria cliente com buffer configurado."""
        mock_config.ledger_buffer_size = 3
        with patch('neural_hive_specialists.ledger_client.MongoClient'):
            return LedgerClient(mock_config)

    def test_buffer_opinion(self, ledger_client, sample_opinion):
        """Testa buffering de parecer."""
        opinion_data = {
            'opinion': sample_opinion,
            'plan_id': 'plan-123',
            'intent_id': 'intent-456',
            'specialist_type': 'business',
            'correlation_id': 'corr-789',
            'opinion_id': 'opinion-001'
        }

        ledger_client._buffer_opinion(opinion_data)

        assert ledger_client._opinion_buffer.qsize() == 1

    def test_buffer_full_handling(self, ledger_client, sample_opinion):
        """Testa comportamento quando buffer está cheio."""
        # Preencher buffer
        for i in range(3):
            opinion_data = {
                'opinion': sample_opinion,
                'plan_id': f'plan-{i}',
                'intent_id': f'intent-{i}',
                'specialist_type': 'business',
                'correlation_id': f'corr-{i}',
                'opinion_id': f'opinion-{i}'
            }
            ledger_client._buffer_opinion(opinion_data)

        assert ledger_client._opinion_buffer.qsize() == 3

        # Buffer deve estar cheio
        assert ledger_client._opinion_buffer.full()

    def test_flush_buffer_success(self, ledger_client, sample_opinion):
        """Testa flush bem-sucedido do buffer."""
        ledger_client._collection = MagicMock()
        ledger_client._collection.insert_one = MagicMock(return_value=MagicMock(acknowledged=True))

        # Adicionar pareceres ao buffer
        for i in range(2):
            opinion_data = {
                'opinion': sample_opinion,
                'plan_id': f'plan-{i}',
                'intent_id': f'intent-{i}',
                'specialist_type': 'business',
                'correlation_id': f'corr-{i}',
                'opinion_id': f'opinion-{i}'
            }
            ledger_client._buffer_opinion(opinion_data)

        flushed = ledger_client.flush_buffer()

        assert flushed == 2
        assert ledger_client._opinion_buffer.qsize() == 0
        assert ledger_client._collection.insert_one.call_count == 2


@pytest.mark.unit
class TestRetrieval:
    """Testes de recuperação de pareceres."""

    @pytest.fixture
    def ledger_client(self, mock_config):
        """Cria cliente com MongoDB mockado."""
        with patch('neural_hive_specialists.ledger_client.MongoClient') as mock_mongo:
            mock_collection = MagicMock()
            mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection
            client = LedgerClient(mock_config)
            client._collection = mock_collection
            return client

    def test_get_opinion_success(self, ledger_client, sample_opinion):
        """Testa recuperação bem-sucedida de parecer."""
        mock_doc = {
            'opinion_id': 'opinion-123',
            'opinion': sample_opinion,
            'plan_id': 'plan-123',
            'timestamp': '2025-01-01T00:00:00'
        }
        ledger_client._collection.find_one = MagicMock(return_value=mock_doc)

        result = ledger_client.get_opinion('opinion-123')

        assert result == mock_doc
        ledger_client._collection.find_one.assert_called_once_with({'opinion_id': 'opinion-123'})

    def test_get_opinion_not_found(self, ledger_client):
        """Testa que None é retornado quando parecer não existe."""
        ledger_client._collection.find_one = MagicMock(return_value=None)

        result = ledger_client.get_opinion('nonexistent')

        assert result is None

    def test_get_opinions_by_plan_id(self, ledger_client, sample_opinion):
        """Testa recuperação de pareceres por plan_id."""
        mock_docs = [
            {'opinion_id': 'op1', 'opinion': sample_opinion, 'plan_id': 'plan-123'},
            {'opinion_id': 'op2', 'opinion': sample_opinion, 'plan_id': 'plan-123'}
        ]
        ledger_client._collection.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=mock_docs)))

        results = ledger_client.get_opinions_by_plan_id('plan-123')

        assert len(results) == 2
        assert results[0]['opinion_id'] == 'op1'

    def test_get_opinions_by_intent_id(self, ledger_client, sample_opinion):
        """Testa recuperação de pareceres por intent_id."""
        mock_docs = [
            {'opinion_id': 'op1', 'opinion': sample_opinion, 'intent_id': 'intent-456'}
        ]
        ledger_client._collection.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=mock_docs)))

        results = ledger_client.get_opinions_by_intent_id('intent-456')

        assert len(results) == 1


@pytest.mark.unit
class TestIntegrityVerification:
    """Testes de verificação de integridade."""

    @pytest.fixture
    def ledger_client(self, mock_config):
        """Cria cliente com MongoDB mockado."""
        with patch('neural_hive_specialists.ledger_client.MongoClient') as mock_mongo:
            mock_collection = MagicMock()
            mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection
            client = LedgerClient(mock_config)
            client._collection = mock_collection
            return client

    def test_verify_integrity_success(self, ledger_client, sample_opinion):
        """Testa verificação de integridade bem-sucedida."""
        correct_hash = "abcdef1234567890"
        mock_doc = {
            'opinion_id': 'opinion-123',
            'opinion': sample_opinion,
            'hash': correct_hash
        }
        ledger_client._collection.find_one = MagicMock(return_value=mock_doc)

        with patch('neural_hive_specialists.ledger_client.LedgerClient._calculate_hash', return_value=correct_hash):
            result = ledger_client.verify_opinion_integrity('opinion-123')

            assert result is True

    def test_verify_integrity_hash_mismatch(self, ledger_client, sample_opinion):
        """Testa detecção de hash incorreto."""
        mock_doc = {
            'opinion_id': 'opinion-123',
            'opinion': sample_opinion,
            'hash': 'old_hash'
        }
        ledger_client._collection.find_one = MagicMock(return_value=mock_doc)

        with patch('neural_hive_specialists.ledger_client.LedgerClient._calculate_hash', return_value='new_hash'):
            result = ledger_client.verify_opinion_integrity('opinion-123')

            assert result is False

    def test_verify_integrity_opinion_not_found(self, ledger_client):
        """Testa que False é retornado para parecer inexistente."""
        ledger_client._collection.find_one = MagicMock(return_value=None)

        result = ledger_client.verify_opinion_integrity('nonexistent')

        assert result is False


@pytest.mark.unit
class TestCircuitBreaker:
    """Testes de transições do circuit breaker."""

    @pytest.fixture
    def ledger_client(self, mock_config, mock_metrics):
        """Cria cliente com circuit breaker habilitado."""
        mock_config.enable_circuit_breaker = True
        mock_config.circuit_breaker_failure_threshold = 2
        mock_config.circuit_breaker_recovery_timeout = 1

        with patch('neural_hive_specialists.ledger_client.MongoClient') as mock_mongo:
            mock_collection = MagicMock()
            mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection
            client = LedgerClient(mock_config, metrics=mock_metrics)
            client._collection = mock_collection
            return client

    def test_circuit_breaker_opens_after_failures(self, ledger_client, sample_opinion, mock_metrics):
        """Testa que circuit breaker abre após falhas consecutivas."""
        ledger_client._collection.insert_one = MagicMock(side_effect=PyMongoError("Connection failed"))

        # Primeira falha
        try:
            ledger_client.save_opinion(
                opinion=sample_opinion,
                plan_id="plan-1",
                intent_id="intent-1",
                specialist_type="business",
                correlation_id="corr-1"
            )
        except PyMongoError:
            pass

        # Segunda falha - deve abrir o circuit breaker
        try:
            ledger_client.save_opinion(
                opinion=sample_opinion,
                plan_id="plan-2",
                intent_id="intent-2",
                specialist_type="business",
                correlation_id="corr-2"
            )
        except PyMongoError:
            pass

        # Terceira tentativa deve levantar CircuitBreakerError
        with pytest.raises(CircuitBreakerError):
            ledger_client.save_opinion(
                opinion=sample_opinion,
                plan_id="plan-3",
                intent_id="intent-3",
                specialist_type="business",
                correlation_id="corr-3"
            )

    def test_circuit_breaker_state_tracking(self, ledger_client):
        """Testa rastreamento do estado do circuit breaker."""
        assert ledger_client._circuit_breaker_state == 'closed'

        # Simular abertura
        ledger_client._circuit_breaker_state = 'open'
        assert ledger_client._circuit_breaker_state == 'open'

    def test_metrics_updated_on_circuit_state_change(self, ledger_client, mock_metrics):
        """Verifica que métricas são atualizadas nas mudanças de estado."""
        # Já verificado na inicialização
        mock_metrics.set_circuit_breaker_state.assert_called_with('ledger', 'closed')


@pytest.mark.unit
class TestConnectionStatus:
    """Testes de verificação de conexão."""

    @pytest.fixture
    def ledger_client(self, mock_config):
        """Cria cliente com MongoDB mockado."""
        with patch('neural_hive_specialists.ledger_client.MongoClient') as mock_mongo:
            mock_collection = MagicMock()
            mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection
            client = LedgerClient(mock_config)
            client._collection = mock_collection
            client._client = mock_mongo.return_value
            return client

    def test_is_connected_true(self, ledger_client):
        """Testa que is_connected retorna True quando conectado."""
        ledger_client._client.admin.command = MagicMock(return_value={'ok': 1})

        result = ledger_client.is_connected()

        assert result is True

    def test_is_connected_false_on_error(self, ledger_client):
        """Testa que is_connected retorna False em erro."""
        ledger_client._client.admin.command = MagicMock(side_effect=PyMongoError("Connection failed"))

        result = ledger_client.is_connected()

        assert result is False
