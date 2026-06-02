"""
Testes para ErasureService - Corrigidos com AsyncMock
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.models.erasure import (
    DataType,
    ErasureScope,
    ErasureStatus,
)
from src.services.erasure_service import ErasureService


@pytest.fixture
def mock_settings():
    """Settings mock"""
    settings = MagicMock()
    settings.mongodb_database = "test_nhmgdpr"
    settings.redis_token_ttl = 3600
    settings.kafka_erasure_commands_topic = "gdpr.erasure.commands"
    settings.verification_token_salt = "test-salt"
    settings.erasure_retention_days = 90
    return settings


@pytest.fixture
def mock_collection():
    """MongoDB collection mock com AsyncMock"""
    collection = AsyncMock()
    return collection


@pytest.fixture
def mock_db(mock_collection):
    """MongoDB database mock"""
    db = MagicMock()
    db.erasure_requests = mock_collection
    return db


@pytest.fixture
def mock_mongodb_client(mock_db):
    """MongoDB client mock"""
    client = MagicMock()
    client.client = MagicMock()
    client.client.__getitem__ = lambda self, name: mock_db
    return client


@pytest.fixture
def mock_redis_client():
    """Redis client mock"""
    client = MagicMock()
    client.client = AsyncMock()
    return client


@pytest.fixture
def mock_kafka_producer():
    """Kafka producer mock"""
    producer = MagicMock()
    producer.produce = AsyncMock()
    return producer


@pytest.fixture
def erasure_service(
    mock_settings, mock_mongodb_client, mock_redis_client, mock_kafka_producer, mock_db
):
    """ErasureService fixture"""
    service = ErasureService(
        settings=mock_settings,
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client,
        kafka_producer=mock_kafka_producer,
    )
    # Sobrescrever db com o mock correto
    service.db = mock_db
    service.collection = mock_db.erasure_requests
    return service


class TestErasureServiceCreateRequest:
    """Testes para create_erasure_request"""

    @pytest.mark.asyncio
    async def test_create_request_success(
        self, erasure_service, mock_collection, mock_redis_client
    ):
        """Testa criacao de solicitacao com sucesso"""
        user_id = "user-123"
        input_data = {
            "email": "test@example.com",
            "scope": ErasureScope.STANDARD,
            "data_types": [DataType.APPROVALS, DataType.SPECIALIST_FEEDBACK],
            "reason": "Testing erasure",
        }

        # Mock MongoDB - sem solicitacao existente
        mock_collection.find_one = AsyncMock(return_value=None)
        mock_collection.insert_one = AsyncMock()

        # Mock Redis
        mock_redis_client.client.setex = AsyncMock()

        result = await erasure_service.create_erasure_request(user_id, input_data)

        assert result.user_id == user_id
        assert result.status == ErasureStatus.PENDING_VERIFICATION
        assert result.verification_token is not None
        assert len(result.data_types) == 2
        mock_collection.insert_one.assert_called_once()
        mock_redis_client.client.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_request_existing_pending(self, erasure_service, mock_collection):
        """Testa erro ao criar solicitacao quando ja existe pendente"""
        user_id = "user-123"
        input_data = {"email": "test@example.com"}

        # Mock MongoDB com solicitacao existente
        mock_collection.find_one = AsyncMock(
            return_value={
                "request_id": "existing-123",
                "status": ErasureStatus.PENDING_VERIFICATION,
            }
        )

        # Usa regex mais flexivel
        with pytest.raises(ValueError, match="solicitacao"):
            await erasure_service.create_erasure_request(user_id, input_data)


class TestErasureServiceVerifyRequest:
    """Testes para verify_erasure_request"""

    @pytest.mark.asyncio
    async def test_verify_request_success(
        self, erasure_service, mock_collection, mock_redis_client
    ):
        """Testa verificacao com sucesso"""
        request_id = "req-123"
        token = "valid-token-12345678"

        # Mock Redis
        mock_redis_client.client.get = AsyncMock(return_value=f"{request_id}:user-123".encode())
        mock_redis_client.client.delete = AsyncMock()

        # Mock MongoDB - request atualizado
        mock_collection.update_one = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={
                "request_id": request_id,
                "status": ErasureStatus.VERIFIED,
                "user_id": "user-123",
                "email": "test@example.com",
                "scope": ErasureScope.STANDARD,
                "data_types": [],
                "results": [],
                "created_at": datetime.now(timezone.utc),
            }
        )

        result = await erasure_service.verify_erasure_request(request_id, token)

        assert result.request_id == request_id
        mock_redis_client.client.delete.assert_called_once()
        mock_collection.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_request_invalid_token(self, erasure_service, mock_redis_client):
        """Testa erro com token invalido"""
        mock_redis_client.client.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Token invalido ou expirado"):
            await erasure_service.verify_erasure_request("req-123", "invalid-token")


class TestErasureServiceProcessRequest:
    """Testes para process_erasure_request"""

    @pytest.mark.asyncio
    async def test_process_request_success(
        self, erasure_service, mock_collection, mock_kafka_producer
    ):
        """Testa processamento com sucesso"""
        request_id = "req-123"

        # Mock MongoDB - dados completos do modelo
        mock_collection.find_one = AsyncMock(
            return_value={
                "request_id": request_id,
                "user_id": "user-123",
                "email": "test@example.com",
                "status": ErasureStatus.VERIFIED,
                "scope": ErasureScope.STANDARD,
                "data_types": ["approvals", "specialist_feedback"],
                "results": [],
                "created_at": datetime.now(timezone.utc),
                "verification_token": "token",
                "reason": None,
                "verified_at": datetime.now(timezone.utc),
                "processing_started_at": None,
                "completed_at": None,
                "expires_at": None,
            }
        )
        mock_collection.update_one = AsyncMock()

        result = await erasure_service.process_erasure_request(request_id)

        assert result.request_id == request_id
        mock_kafka_producer.produce.assert_called()

    @pytest.mark.asyncio
    async def test_process_request_not_verified(self, erasure_service, mock_collection):
        """Testa erro quando solicitacao nao verificada"""
        request_id = "req-123"

        mock_collection.find_one = AsyncMock(
            return_value={
                "request_id": request_id,
                "user_id": "user-123",
                "email": "test@example.com",
                "status": ErasureStatus.PENDING_VERIFICATION,
                "scope": ErasureScope.STANDARD,
                "data_types": [],
                "results": [],
                "created_at": datetime.now(timezone.utc),
                "verification_token": "token",
                "reason": None,
                "verified_at": None,
                "processing_started_at": None,
                "completed_at": None,
                "expires_at": None,
            }
        )

        with pytest.raises(ValueError, match="verificada"):
            await erasure_service.process_erasure_request(request_id)


class TestErasureServiceHandleReport:
    """Testes para handle_erasure_report"""

    @pytest.mark.asyncio
    async def test_handle_report_success(self, erasure_service, mock_collection):
        """Testa processamento de relatorio"""
        request_id = "req-123"
        report_data = {
            "request_id": request_id,
            "service": "approval-service",
            "status": "success",
            "records_affected": 42,
        }

        mock_collection.update_one = AsyncMock()
        mock_collection.find_one = AsyncMock(return_value=None)

        await erasure_service.handle_erasure_report(report_data)

        mock_collection.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_report_completion(self, erasure_service, mock_collection):
        """Testa conclusao quando todos services respondem"""
        request_id = "req-123"

        # Mock com results existentes
        mock_collection.find_one = AsyncMock(
            return_value={
                "request_id": request_id,
                "data_types": ["approvals", "specialist_feedback"],
                "results": [
                    {"service": "approval-service", "status": "success", "records_affected": 0}
                ],
            }
        )
        mock_collection.update_one = AsyncMock()

        report_data = {
            "request_id": request_id,
            "service": "consensus-engine",
            "status": "success",
            "records_affected": 10,
        }

        await erasure_service.handle_erasure_report(report_data)

        # Verifica se atualizou para COMPLETED
        assert mock_collection.update_one.call_count == 2


class TestErasureServiceGetStatus:
    """Testes para get_erasure_status"""

    @pytest.mark.asyncio
    async def test_get_status_success(self, erasure_service, mock_collection):
        """Testa obter status com sucesso"""
        request_id = "req-123"

        # MongoDB retorna strings, não enums
        mock_collection.find_one = AsyncMock(
            return_value={
                "request_id": request_id,
                "user_id": "user-123",
                "email": "test@example.com",
                "status": ErasureStatus.COMPLETED,
                "scope": ErasureScope.STANDARD,
                "data_types": ["approvals"],
                "results": [
                    {
                        "service": "approval-service",
                        "data_type": "approvals",  # String do MongoDB, não enum
                        "status": "success",
                        "records_affected": 100,
                        "error_message": None,
                        "completed_at": datetime.now(timezone.utc),
                    }
                ],
                "created_at": datetime.now(timezone.utc),
                "verified_at": datetime.now(timezone.utc),
                "completed_at": datetime.now(timezone.utc),
                "verification_token": "token",
                "reason": None,
                "processing_started_at": None,
                "expires_at": None,
            }
        )

        result = await erasure_service.get_erasure_status(request_id)

        assert result["request_id"] == request_id
        assert result["status"] == ErasureStatus.COMPLETED
        assert result["results_summary"]["approval-service"] == 100

    @pytest.mark.asyncio
    async def test_get_status_not_found(self, erasure_service, mock_collection):
        """Testa erro quando solicitacao nao encontrada"""
        mock_collection.find_one = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="nao encontrada"):
            await erasure_service.get_erasure_status("req-999")


class TestErasureServiceCleanup:
    """Testes para cleanup_expired_requests"""

    @pytest.mark.asyncio
    async def test_cleanup_success(self, erasure_service, mock_collection):
        """Testa limpeza de solicitacoes expiradas"""
        mock_result = MagicMock()
        mock_result.deleted_count = 5
        mock_collection.delete_many = AsyncMock(return_value=mock_result)

        count = await erasure_service.cleanup_expired_requests()

        assert count == 5
        mock_collection.delete_many.assert_called_once()


class TestErasureServiceGetTargetServices:
    """Testes para _get_target_services"""

    def test_get_target_services(self, erasure_service):
        """Testa mapeamento de data types para services"""
        data_types = [DataType.APPROVALS, DataType.CONSENSUS_HISTORY]
        services = erasure_service._get_target_services(data_types)

        assert "approval-service" in services
        assert "consensus-engine" in services
        assert len(services) == 2

    def test_get_target_services_all(self, erasure_service):
        """Testa mapeamento de todos data types"""
        data_types = list(DataType)
        services = erasure_service._get_target_services(data_types)

        # 8 DataTypes mas 6 servicos únicos (3 DataTypes → approval-service)
        assert len(services) == 8  # Todos os 8 DataTypes mapeiam
        assert len(set(services)) == 6  # Mas apenas 6 servicos únicos

        # Verifica que os principais services estao presentes
        expected_services = {
            "approval-service",
            "consensus-engine",
            "execution-ticket-service",
            "memory-layer-api",
            "gateway-intencoes",
            "observability",
        }
        assert set(services) == expected_services
