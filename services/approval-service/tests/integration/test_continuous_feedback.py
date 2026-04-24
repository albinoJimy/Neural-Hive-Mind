"""
Integration Tests para Continuous Feedback (EPIC 3.3)

Testa o fluxo completo de feedback continuo desde a API ate o Kafka.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

# Set env vars before importing Settings
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("APPROVAL_SERVICE_REQUIRE_AUTH", "false")

from src.config.settings import Settings
from src.models.continuous_feedback import (
    ContinuousFeedbackRequest,
    ContinuousFeedbackResponse,
)
from src.services.continuous_feedback_service import ContinuousFeedbackService
from src.producers.training_data_producer import TrainingDataProducer

# Create minimal FastAPI app for testing
from fastapi import FastAPI
from src.api.routers import continuous_feedback as cf_router_module
from src.api.routers.continuous_feedback import (
    router as cf_router,
    set_continuous_feedback_service,
)

# Mock auth dependency in the router module
cf_router_module.get_current_admin_user = lambda: {"user_id": "test-admin", "email": "admin@test.com"}

test_app = FastAPI()
test_app.include_router(cf_router)


@pytest.fixture
async def settings():
    """Configuracoes de teste"""
    os.environ["KAFKA_BOOTSTRAP_SERVERS"] = "localhost:9092"
    os.environ["MONGODB_URI"] = "mongodb://localhost:27017"
    os.environ["APPROVAL_SERVICE_REQUIRE_AUTH"] = "false"

    return Settings(
        environment="test",
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="test_neural_hive",
        mongodb_collection="test_plan_approvals",
        kafka_bootstrap_servers="localhost:9092",
        kafka_enable_idempotence=False,
        kafka_security_protocol="PLAINTEXT",
        enable_feedback_collection=False,
    )


@pytest.fixture
async def mock_mongodb_client():
    """Mock MongoDB client"""
    client = MagicMock()
    client.db = MagicMock()
    client.db.__getitem__ = MagicMock(return_value=MagicMock())

    # Mock collection methods
    collection = MagicMock()
    collection.create_index = AsyncMock()
    collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="test-id"))
    collection.find_one = AsyncMock(return_value=None)
    collection.aggregate = AsyncMock(return_value=[])
    collection.find = MagicMock()

    # Setup async iterator for find
    async def async_find_iterator(*args, **kwargs):
        return
        yield  # Generator vazio

    collection.find.return_value.sort.return_value.skip.return_value.limit.return_value.__aiter__ = (
        lambda: async_find_iterator()
    )

    # Setup aggregate to return async result
    async def mock_to_list(length):
        return []

    async def mock_aggregate_pipeline(pipeline):
        # Return mock command with to_list
        result = MagicMock()
        result.to_list = AsyncMock(return_value=[])
        return result

    collection.aggregate = AsyncMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))

    client.db.__getitem__.return_value = collection
    client.db.test_plan_approvals_continuous_feedback = collection

    return client


@pytest.fixture
async def mock_training_data_producer():
    """Mock Training Data Producer"""
    producer = MagicMock()
    producer.send_training_data = AsyncMock()
    producer.flush = AsyncMock()
    producer.close = AsyncMock()
    return producer


@pytest.fixture
async def continuous_feedback_service(settings, mock_mongodb_client, mock_training_data_producer):
    """Servico de continuous feedback para teste"""
    # Mock MongoDBClient
    with patch("src.services.continuous_feedback_service.MongoDBClient") as mock_mongo:
        mock_mongo.return_value = mock_mongodb_client

        service = ContinuousFeedbackService(
            settings=settings,
            mongodb_client=mock_mongodb_client,
            training_data_producer=mock_training_data_producer,
        )

        # Setup collection manualmente
        service.collection = mock_mongodb_client.db.test_plan_approvals_continuous_feedback

        # Mock NLP extractor
        service._nlp_extractor = MagicMock()
        service._nlp_extractor.extract_features = MagicMock(
            return_value={
                "primary_domain": "security",
                "domain_security": 0.3,
                "text_length_chars": 50,
                "text_length_words": 8,
            }
        )

        await service.initialize()
        yield service


@pytest.mark.asyncio
class TestContinuousFeedbackService:
    """Testes do servico de continuous feedback"""

    async def test_submit_feedback_basic(
        self, continuous_feedback_service, mock_training_data_producer
    ):
        """Testa submissao basica de feedback"""
        request = ContinuousFeedbackRequest(
            prediction_id="pred-123",
            prediction="approve",
            actual_result="approve",
            intent_text="Adicionar autenticacao JWT",
            plan_id="plan-456",
            user_id="user-789",
            confidence=0.85,
            model_version="v1.0",
        )

        response = await continuous_feedback_service.submit_feedback(request)

        assert response.feedback_id is not None
        assert response.prediction_id == "pred-123"
        assert response.enrolled is True
        assert response.nlp_features_enriched is True
        assert response.kafka_published is True

        # Verifica que Kafka producer foi chamado
        mock_training_data_producer.send_training_data.assert_called_once()

        # Verifica que NLP features foram extraidas
        continuous_feedback_service._nlp_extractor.extract_features.assert_called_once_with(
            "Adicionar autenticacao JWT"
        )

    async def test_submit_feedback_without_intent_text(
        self, continuous_feedback_service, mock_training_data_producer
    ):
        """Testa feedback sem texto de intent (sem features NLP)"""
        request = ContinuousFeedbackRequest(
            prediction_id="pred-124",
            prediction="approve",
            actual_result="reject",
            plan_id="plan-457",
        )

        response = await continuous_feedback_service.submit_feedback(request)

        assert response.nlp_features_enriched is False
        assert response.enrolled is True

        # NLP extractor nao deve ser chamado
        continuous_feedback_service._nlp_extractor.extract_features.assert_not_called()

    async def test_get_feedback_by_prediction_id(
        self, continuous_feedback_service, mock_mongodb_client
    ):
        """Testa busca de feedback por prediction_id"""
        # Mock retorno do MongoDB
        mock_mongodb_client.db.test_plan_approvals_continuous_feedback.find_one = AsyncMock(
            return_value={
                "feedback_id": "fb-123",
                "prediction_id": "pred-123",
                "prediction": "approve",
                "actual_result": "approve",
            }
        )

        feedback = await continuous_feedback_service.get_feedback_by_prediction_id("pred-123")

        assert feedback is not None
        assert feedback["feedback_id"] == "fb-123"
        assert feedback["prediction_id"] == "pred-123"

    async def test_get_stats_empty(self, continuous_feedback_service):
        """Testa estatisticas com dataset vazio"""
        # Mock aggregate para retornar vazio (com to_list)
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[{}])
        continuous_feedback_service.collection.aggregate = MagicMock(return_value=mock_cursor)

        stats = await continuous_feedback_service.get_stats()

        assert stats.total_feedbacks == 0
        assert stats.accuracy == 0.0
        assert stats.with_nlp_features == 0

    async def test_get_stats_with_data(self, continuous_feedback_service):
        """Testa estatisticas com dados"""
        # Mock aggregate com dados (com to_list)
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "total_count": [{"count": 100}],
                    "prediction_matches": [
                        {"_id": ("approve", "approve"), "count": 70},
                        {"_id": ("approve", "reject"), "count": 10},
                        {"_id": ("reject", "reject"), "count": 15},
                        {"_id": ("reject", "approve"), "count": 5},
                    ],
                    "avg_confidence": [{"avg": 0.75}],
                    "nlp_enriched": [{"count": 80}],
                }
            ]
        )
        continuous_feedback_service.collection.aggregate = MagicMock(return_value=mock_cursor)

        stats = await continuous_feedback_service.get_stats()

        assert stats.total_feedbacks == 100
        assert stats.approvals_correct == 70
        assert stats.approvals_incorrect == 10
        assert stats.rejections_correct == 15
        assert stats.rejections_incorrect == 5
        assert stats.accuracy == 0.85
        assert stats.avg_confidence == 0.75
        assert stats.with_nlp_features == 80


@pytest.mark.asyncio
class TestContinuousFeedbackAPI:
    """Testes da API de continuous feedback"""

    async def test_submit_continuous_feedback_endpoint(
        self, continuous_feedback_service
    ):
        """Testa endpoint POST /api/v1/feedback/continuous"""
        # Configura servico no router
        set_continuous_feedback_service(continuous_feedback_service)

        # Cria client HTTP
        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/feedback/continuous",
                json={
                    "prediction_id": "pred-api-123",
                    "prediction": "approve",
                    "actual_result": "reject",
                    "intent_text": "Teste de feedback continuo via API",
                    "plan_id": "plan-api-456",
                    "confidence": 0.9,
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["prediction_id"] == "pred-api-123"
            assert data["enrolled"] is True
            assert data["nlp_features_enriched"] is True

    async def test_submit_invalid_prediction(self, continuous_feedback_service):
        """Testa validacao de predicao invalida"""
        set_continuous_feedback_service(continuous_feedback_service)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/feedback/continuous",
                json={
                    "prediction_id": "pred-invalid",
                    "prediction": "invalid",
                    "actual_result": "approve",
                },
            )

            assert response.status_code == 400

    async def test_submit_invalid_actual_result(self, continuous_feedback_service):
        """Testa validacao de resultado invalido"""
        set_continuous_feedback_service(continuous_feedback_service)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/feedback/continuous",
                json={
                    "prediction_id": "pred-invalid",
                    "prediction": "approve",
                    "actual_result": "maybe",
                },
            )

            assert response.status_code == 400

    async def test_submit_invalid_confidence(self, continuous_feedback_service):
        """Testa validacao de confianca fora do range"""
        set_continuous_feedback_service(continuous_feedback_service)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/feedback/continuous",
                json={
                    "prediction_id": "pred-invalid",
                    "prediction": "approve",
                    "actual_result": "reject",
                    "confidence": 1.5,  # Invalido
                },
            )

            # Pydantic valida primeiro, retorna 422
            assert response.status_code in (400, 422)

    async def test_get_stats_endpoint(self, continuous_feedback_service):
        """Testa endpoint GET /api/v1/feedback/continuous/stats"""
        set_continuous_feedback_service(continuous_feedback_service)

        # Mock stats
        continuous_feedback_service.get_stats = AsyncMock(
            return_value=MagicMock(
                total_feedbacks=100,
                approvals_correct=70,
                approvals_incorrect=10,
                rejections_correct=15,
                rejections_incorrect=5,
                accuracy=0.85,
                avg_confidence=0.75,
                with_nlp_features=80,
            )
        )

        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/feedback/continuous/stats")

            assert response.status_code == 200
            data = response.json()
            assert data["total_feedbacks"] == 100
            assert data["accuracy"] == 0.85
            assert data["with_nlp_features"] == 80

    async def test_health_check_endpoint(self, continuous_feedback_service):
        """Testa endpoint GET /api/v1/feedback/continuous/health"""
        set_continuous_feedback_service(continuous_feedback_service)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/feedback/continuous/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["nlp_extractor_enabled"] is True
            assert data["service"] == "continuous-feedback"


@pytest.mark.asyncio
class TestTrainingDataProducer:
    """Testes do Training Data Producer"""

    async def test_send_training_data(self, settings):
        """Testa envio de dados de treinamento para Kafka"""
        from src.models.continuous_feedback import TrainingDataKafkaMessage

        # Mock Kafka producer
        with patch("src.producers.training_data_producer.Producer") as mock_producer_class:
            mock_producer = MagicMock()
            mock_producer.produce = MagicMock()
            mock_producer.poll = MagicMock()
            mock_producer_class.return_value = mock_producer

            producer = TrainingDataProducer(settings)
            await producer.initialize()

            message = TrainingDataKafkaMessage(
                prediction_id="pred-123",
                prediction="approve",
                actual_result="approve",
                timestamp=datetime.now(timezone.utc),
                intent_text="Teste",
                nlp_features={"primary_domain": "security"},
            )

            await producer.send_training_data(message)

            # Verifica que produce foi chamado
            mock_producer.produce.assert_called_once()

            # Verifica topic
            call_args = mock_producer.produce.call_args
            assert call_args[1]["topic"] == "ml.training_data"

    async def test_kafka_config_with_security(self, settings):
        """Testa configuracao Kafka com seguranca"""
        os.environ["KAFKA_SECURITY_PROTOCOL"] = "SASL_SSL"
        os.environ["KAFKA_SASL_MECHANISM"] = "PLAIN"
        os.environ["KAFKA_SASL_USERNAME"] = "user"
        os.environ["KAFKA_SASL_PASSWORD"] = "pass"

        settings_security = Settings(
            environment="test",
            kafka_bootstrap_servers="localhost:9092",
            kafka_security_protocol="SASL_SSL",
            kafka_sasl_mechanism="PLAIN",
            kafka_sasl_username="user",
            kafka_sasl_password="pass",
        )

        with patch("src.producers.training_data_producer.Producer") as mock_producer_class:
            mock_producer = MagicMock()
            mock_producer_class.return_value = mock_producer

            producer = TrainingDataProducer(settings_security)
            await producer.initialize()

            # Verifica configuracao de seguranca
            call_args = mock_producer_class.call_args
            config = call_args[0][0]

            assert config["security.protocol"] == "SASL_SSL"
            assert config["sasl.mechanism"] == "PLAIN"
            assert config["sasl.username"] == "user"
            assert config["sasl.password"] == "pass"


@pytest.mark.asyncio
class TestContinuousFeedbackE2E:
    """Testes End-to-End do fluxo de continuous feedback"""

    async def test_e2e_feedback_flow(
        self, continuous_feedback_service, mock_training_data_producer
    ):
        """
        Testa fluxo E2E:
        1. API recebe feedback
        2. Service processa com NLP
        3. Producer envia para Kafka
        4. MongoDB persiste dados
        """
        request = ContinuousFeedbackRequest(
            prediction_id="e2e-pred-1",
            prediction="reject",
            actual_result="reject",
            intent_text="Remover usuario sem autenticacao",
            confidence=0.92,
        )

        # Processa feedback
        response = await continuous_feedback_service.submit_feedback(request)

        # Verifica resposta
        assert response.feedback_id is not None
        assert response.kafka_published is True

        # Verifica Kafka
        mock_training_data_producer.send_training_data.assert_called_once()
        kafka_message = mock_training_data_producer.send_training_data.call_args[0][0]

        assert kafka_message.prediction_id == "e2e-pred-1"
        assert kafka_message.nlp_features is not None
        assert kafka_message.nlp_features["primary_domain"] in (
            "security",
            "unknown",
            "authentication",
        )

    async def test_e2e_feedback_with_correction(
        self, continuous_feedback_service, mock_training_data_producer
    ):
        """
        Testa fluxo de correcao: modelo errou a predicao.
        Esse e o caso mais valioso para aprendizado.
        """
        request = ContinuousFeedbackRequest(
            prediction_id="correction-pred-1",
            prediction="approve",  # Modelo aprovou
            actual_result="reject",  # Mas deveria ter rejeitado
            intent_text="Deploy de codigo sem testes",
            confidence=0.65,  # Confianca baixa
        )

        response = await continuous_feedback_service.submit_feedback(request)

        assert response.enrolled is True
        assert response.nlp_features_enriched is True

        # Verifica que Kafka recebeu a correcao
        kafka_message = mock_training_data_producer.send_training_data.call_args[0][0]
        assert kafka_message.prediction == "approve"
        assert kafka_message.actual_result == "reject"
        assert kafka_message.confidence == 0.65
