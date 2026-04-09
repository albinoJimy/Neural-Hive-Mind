"""Testes unitários para LearningEventConsumer"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from aiokafka import AIOKafkaConsumer

from src.consumers.learning_event_consumer import LearningEventConsumer


@pytest.fixture
def mock_repository():
    """Mock do DocumentRepository"""
    repo = AsyncMock()
    repo.save = AsyncMock(return_value="test_doc_id")
    return repo


@pytest.fixture
def mock_insight_extractor():
    """Mock do ExperimentInsightExtractor"""
    extractor = AsyncMock()
    extractor.get_run_by_id = AsyncMock(return_value=None)
    extractor.get_runs_by_period = AsyncMock(return_value=[])
    extractor.extract_insights_from_runs = AsyncMock(return_value=[])
    return extractor


@pytest.fixture
def mock_report_generator():
    """Mock do MarkdownReportGenerator"""
    generator = AsyncMock()
    generator.initialize = AsyncMock()
    return generator


@pytest.fixture
def mock_kafka_producer():
    """Mock do KafkaLearningDocProducer"""
    producer = AsyncMock()
    producer.publish_doc_generated = AsyncMock(return_value=True)
    return producer


@pytest.fixture
def consumer(mock_repository, mock_insight_extractor, mock_report_generator, mock_kafka_producer):
    """Fixture do LearningEventConsumer"""
    return LearningEventConsumer(
        repository=mock_repository,
        insight_extractor=mock_insight_extractor,
        report_generator=mock_report_generator,
        kafka_producer=mock_kafka_producer,
    )


@pytest.fixture
def mock_kafka_message():
    """Cria uma mensagem Kafka mock"""
    message = Mock()
    message.topic = "experiment.completed"
    message.partition = 0
    message.offset = 123
    message.headers = []
    message.value = json.dumps({"run_id": "test_run_123"}).encode("utf-8")
    return message


class TestLearningEventConsumer:
    """Testes para LearningEventConsumer"""

    def test_consumer_initialization(self, consumer):
        """Testa inicialização do consumer"""
        assert consumer.repository is not None
        assert consumer.insight_extractor is not None
        assert consumer.report_generator is not None
        assert consumer.kafka_producer is not None
        assert not consumer.is_running()

    def test_deserialize_json_message(self, consumer):
        """Testa deserialização de mensagem JSON"""
        data = {"run_id": "test123", "status": "FINISHED"}
        message = Mock(value=json.dumps(data).encode("utf-8"))

        result = consumer._deserialize(message.value)

        assert result == data

    @pytest.mark.asyncio
    async def test_handle_experiment_completed_no_run_id(self, consumer):
        """Testa handler de experiment.completed sem run_id"""
        event_data = {"invalid": "data"}

        await consumer._handle_experiment_completed(event_data)

        # Não deve chamar get_run_by_id
        consumer.insight_extractor.get_run_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_experiment_completed_run_not_found(self, consumer):
        """Testa handler de experiment.completed com run não encontrado"""
        event_data = {"run_id": "nonexistent_run"}
        consumer.insight_extractor.get_run_by_id = AsyncMock(return_value=None)

        await consumer._handle_experiment_completed(event_data)

        consumer.insight_extractor.get_run_by_id.assert_called_once_with("nonexistent_run")
        # Não deve salvar documento
        consumer.repository.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_experiment_completed_success(
        self, consumer, mock_insight_extractor, mock_repository
    ):
        """Testa handler de experiment.completed com sucesso"""
        from src.models import Insight, InsightConfidence

        # Criar mock run do MLflow
        mock_mlflow_run = MagicMock()
        mock_mlflow_run.info.run_id = "test_run_123"
        mock_mlflow_run.info.experiment_id = 1
        mock_mlflow_run.info.status = "FINISHED"
        mock_mlflow_run.info.start_time = int((datetime.utcnow().timestamp() - 3600) * 1000)
        mock_mlflow_run.info.end_time = int(datetime.utcnow().timestamp() * 1000)
        mock_mlflow_run.info.artifact_uri = "s3://mlflow/artifacts/test_run_123"
        mock_mlflow_run.data.metrics = {"accuracy": 0.85, "val_accuracy": 0.82}
        mock_mlflow_run.data.params = [MagicMock(key="lr", value="0.001")]
        mock_mlflow_run.data.tags = {"mlflow.runName": "test_experiment"}

        mock_insight_extractor.get_run_by_id = AsyncMock(return_value=mock_mlflow_run)

        # Mock insights
        mock_insight = Insight(
            title="High Accuracy",
            description="Model achieved high accuracy",
            evidence={"accuracy": 0.85},
            confidence=InsightConfidence.HIGH,
            experiment_ids=["test_run_123"],
            category="performance",
        )
        mock_insight_extractor.extract_insights_from_runs = AsyncMock(return_value=[mock_insight])

        event_data = {"run_id": "test_run_123"}

        await consumer._handle_experiment_completed(event_data)

        # Deve salvar documento
        mock_repository.save.assert_called_once()
        # Deve publicar evento
        consumer.kafka_producer.publish_doc_generated.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_model_promoted(self, consumer):
        """Testa handler de model.promoted"""
        from src.models import Insight, InsightConfidence

        # Mock run promovido
        mock_mlflow_run = MagicMock()
        mock_mlflow_run.info.run_id = "promoted_run"
        mock_mlflow_run.info.experiment_id = 1
        mock_mlflow_run.info.status = "FINISHED"
        mock_mlflow_run.info.start_time = int((datetime.utcnow().timestamp() - 3600) * 1000)
        mock_mlflow_run.info.end_time = int(datetime.utcnow().timestamp() * 1000)
        mock_mlflow_run.info.artifact_uri = "s3://mlflow/artifacts/promoted_run"
        mock_mlflow_run.data.metrics = {"val_accuracy": 0.92}
        mock_mlflow_run.data.params = []
        mock_mlflow_run.data.tags = {"mlflow.runName": "promoted_model"}

        consumer.insight_extractor.get_run_by_id = AsyncMock(return_value=mock_mlflow_run)
        consumer.insight_extractor.get_runs_by_period = AsyncMock(return_value=[])
        consumer.insight_extractor.extract_insights_from_runs = AsyncMock(return_value=[])

        event_data = {
            "run_id": "promoted_run",
            "approved_by": "data_scientist",
            "approved_at": "2026-04-08T10:00:00Z",
        }

        await consumer._handle_model_promoted(event_data)

        # Deve salvar documento
        consumer.repository.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_deployment_rollback(self, consumer):
        """Testa handler de deployment.rolled_back"""
        from src.models import Insight, InsightConfidence

        # Mock run problemático
        mock_mlflow_run = MagicMock()
        mock_mlflow_run.info.run_id = "problematic_run"
        mock_mlflow_run.info.experiment_id = 1
        mock_mlflow_run.info.status = "FINISHED"
        mock_mlflow_run.info.start_time = int((datetime.utcnow().timestamp() - 3600) * 1000)
        mock_mlflow_run.info.end_time = int(datetime.utcnow().timestamp() * 1000)
        mock_mlflow_run.info.artifact_uri = "s3://mlflow/artifacts/problematic_run"
        mock_mlflow_run.data.metrics = {}
        mock_mlflow_run.data.params = []
        mock_mlflow_run.data.tags = {"mlflow.runName": "problematic_model"}

        consumer.insight_extractor.get_run_by_id = AsyncMock(return_value=mock_mlflow_run)
        consumer.insight_extractor.get_runs_by_period = AsyncMock(return_value=[])

        event_data = {
            "run_id": "problematic_run",
            "reason": "High error rate in production",
            "detected_by": "monitoring_system",
        }

        await consumer._handle_deployment_rollback(event_data)

        # Deve salvar documento
        consumer.repository.save.assert_called_once()

    def test_generate_experiment_summary(self, consumer):
        """Testa geração de resumo do experimento"""
        from src.models import ExperimentRun, Insight, InsightConfidence

        run = ExperimentRun(
            run_id="r1",
            experiment_id=1,
            name="test_exp",
            status="FINISHED",
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            metrics={"accuracy": 0.85, "val_accuracy": 0.82},
            params={},
            tags={},
        )

        insights = [
            Insight(
                title="Good Performance",
                description="Model performed well",
                evidence={"accuracy": 0.85},
                confidence=InsightConfidence.HIGH,
                experiment_ids=["r1"],
                category="performance",
            )
        ]

        summary = consumer._generate_experiment_summary(run, insights)

        assert "test_exp" in summary
        assert "FINISHED" in summary
        assert "1 insights" in summary

    def test_generate_experiment_recommendations(self, consumer):
        """Testa geração de recomendações do experimento"""
        from src.models import DocumentStatus, DocumentFormat, Insight, InsightConfidence

        insights = [
            Insight(
                title="High Performance",
                description="",
                evidence={},
                confidence=InsightConfidence.HIGH,
                experiment_ids=[],
                category="performance",
            ),
            Insight(
                title="Significant Improvement",
                description="",
                evidence={},
                confidence=InsightConfidence.HIGH,
                experiment_ids=[],
                category="improvement",
            ),
        ]

        recommendations = consumer._generate_experiment_recommendations(insights)

        assert len(recommendations) > 0
        assert any("produção" in r.lower() for r in recommendations)

    @pytest.mark.asyncio
    async def test_publish_doc_generated_event(self, consumer):
        """Testa publicação de evento doc.generated"""
        from src.models import LearningDocument, DocumentType, DocumentStatus, DocumentFormat

        document = LearningDocument(
            title="Test Document",
            type=DocumentType.EXPERIMENT_REPORT,
            status=DocumentStatus.COMPLETED,
            format=DocumentFormat.MARKDOWN,
            generated_at=datetime.utcnow(),
            metadata={"run_id": "test_run"},
        )

        await consumer._publish_doc_generated_event(document, "doc_123")

        consumer.kafka_producer.publish_doc_generated.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_message_routing(self, consumer, mock_kafka_message):
        """Testa roteamento de mensagens baseado no tópico"""
        # Teste para tópico experiment.completed
        mock_kafka_message.topic = consumer.settings.kafka_experiment_completed_topic
        consumer.settings.kafka_experiment_completed_topic = "experiment.completed"

        consumer._handle_experiment_completed = AsyncMock()

        await consumer._process_message(mock_kafka_message)

        consumer._handle_experiment_completed.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_consumer(self, consumer):
        """Testa parada do consumer"""
        # Marcar como rodando
        consumer._running = True

        await consumer.stop()

        assert not consumer.is_running()

    def test_is_running(self, consumer):
        """Testa verificação de status"""
        assert not consumer.is_running()

        consumer._running = True
        assert consumer.is_running()
