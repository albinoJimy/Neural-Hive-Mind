"""Testes unitários para MigrationProducer."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from src.producers.migration_producer import MigrationProducer, get_migration_producer


@pytest.fixture
def mock_kafka_producer():
    """Cria mock do AIOKafkaProducer."""
    producer = Mock(spec=AIOKafkaProducer)
    producer.start = AsyncMock()
    producer.stop = AsyncMock()
    producer.send_and_wait = AsyncMock()
    return producer


class TestMigrationProducerAsync:
    """Testes assíncronos para MigrationProducer."""

    @pytest.mark.asyncio
    async def test_start_producer(self, mock_kafka_producer):
        """Testa inicialização do producer."""
        # Arrange
        with patch(
            "src.producers.migration_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = MigrationProducer()

            # Act
            await producer.start()

            # Assert
            mock_kafka_producer.start.assert_called_once()
            assert producer._running is True

    @pytest.mark.asyncio
    async def test_stop_producer(self, mock_kafka_producer):
        """Testa parada do producer."""
        # Arrange
        with patch(
            "src.producers.migration_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = MigrationProducer()
            await producer.start()

            # Act
            await producer.stop()

            # Assert
            mock_kafka_producer.stop.assert_called_once()
            assert producer._running is False

    @pytest.mark.asyncio
    async def test_publish_migration_started(self, mock_kafka_producer):
        """Testa publicação de evento migration.started."""
        # Arrange
        with patch(
            "src.producers.migration_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = MigrationProducer()
            await producer.start()

            # Act
            await producer.publish_migration_started(
                job_id="job-001",
                legacy_db="postgresql://localhost:5432/legacy",
                tables=["users", "orders"],
            )

            # Assert
            mock_kafka_producer.send_and_wait.assert_called_once()
            call_args = mock_kafka_producer.send_and_wait.call_args
            assert call_args[0][0] == "migration.events"
            event = call_args[1]["value"]
            assert event["event_type"] == "migration.started"
            assert event["job_id"] == "job-001"
            assert event["tables"] == ["users", "orders"]
            assert "timestamp" in event

    @pytest.mark.asyncio
    async def test_publish_migration_started_sanitizes_db(self, mock_kafka_producer):
        """Testa que connection string é sanitizada no evento."""
        # Arrange
        with patch(
            "src.producers.migration_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = MigrationProducer()
            await producer.start()

            # Act
            await producer.publish_migration_started(
                job_id="job-001",
                legacy_db="postgresql://user:password@localhost:5432/legacy",
                tables=["users"],
            )

            # Assert
            call_args = mock_kafka_producer.send_and_wait.call_args
            event = call_args[1]["value"]
            assert "password" not in event["legacy_db"]
            assert "***" in event["legacy_db"]

    @pytest.mark.asyncio
    async def test_publish_migration_progress(self, mock_kafka_producer):
        """Testa publicação de evento migration.progress."""
        # Arrange
        with patch(
            "src.producers.migration_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = MigrationProducer()
            await producer.start()

            # Act
            await producer.publish_migration_progress(
                job_id="job-001",
                phase="batch_migration",
                table="users",
                offset=5000,
                batch_size=1000,
                total_migrated=5000,
                total_expected=10000,
                progress_percent=50.0,
            )

            # Assert
            call_args = mock_kafka_producer.send_and_wait.call_args
            event = call_args[1]["value"]
            assert event["event_type"] == "migration.progress"
            assert event["job_id"] == "job-001"
            assert event["phase"] == "batch_migration"
            assert event["table"] == "users"
            assert event["total_migrated"] == 5000
            assert event["total_expected"] == 10000
            assert event["progress_percent"] == 50.0

    @pytest.mark.asyncio
    async def test_publish_migration_progress_minimal(self, mock_kafka_producer):
        """Testa publicação de evento migration.progress com dados mínimos."""
        # Arrange
        with patch(
            "src.producers.migration_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = MigrationProducer()
            await producer.start()

            # Act
            await producer.publish_migration_progress(
                job_id="job-001",
                phase="cdc",
            )

            # Assert
            call_args = mock_kafka_producer.send_and_wait.call_args
            event = call_args[1]["value"]
            assert event["phase"] == "cdc"
            assert event["table"] is None
            assert event["total_migrated"] == 0

    @pytest.mark.asyncio
    async def test_publish_batch_completed(self, mock_kafka_producer):
        """Testa publicação de evento migration.batch_completed."""
        # Arrange
        with patch(
            "src.producers.migration_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = MigrationProducer()
            await producer.start()

            # Act
            await producer.publish_batch_completed(
                job_id="job-001",
                tables_completed=["users", "orders"],
                total_rows=10000,
                duration_seconds=300.5,
            )

            # Assert
            call_args = mock_kafka_producer.send_and_wait.call_args
            event = call_args[1]["value"]
            assert event["event_type"] == "migration.batch_completed"
            assert event["job_id"] == "job-001"
            assert event["tables_completed"] == ["users", "orders"]
            assert event["total_rows"] == 10000
            assert event["duration_seconds"] == 300.5

    @pytest.mark.asyncio
    async def test_publish_cdc_started(self, mock_kafka_producer):
        """Testa publicação de evento migration.cdc_started."""
        # Arrange
        with patch(
            "src.producers.migration_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = MigrationProducer()
            await producer.start()

            # Act
            await producer.publish_cdc_started(
                job_id="job-001",
                connector_id="postgres-connector-job-001",
                kafka_topic="pg-legacy.public.users",
            )

            # Assert
            call_args = mock_kafka_producer.send_and_wait.call_args
            event = call_args[1]["value"]
            assert event["event_type"] == "migration.cdc_started"
            assert event["job_id"] == "job-001"
            assert event["connector_id"] == "postgres-connector-job-001"
            assert event["kafka_topic"] == "pg-legacy.public.users"

    @pytest.mark.asyncio
    async def test_publish_migration_completed(self, mock_kafka_producer):
        """Testa publicação de evento migration.completed."""
        # Arrange
        with patch(
            "src.producers.migration_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = MigrationProducer()
            await producer.start()

            # Act
            await producer.publish_migration_completed(
                job_id="job-001",
                status="completed",
                total_rows=10500,
                cdc_lag=0,
            )

            # Assert
            call_args = mock_kafka_producer.send_and_wait.call_args
            event = call_args[1]["value"]
            assert event["event_type"] == "migration.completed"
            assert event["job_id"] == "job-001"
            assert event["status"] == "completed"
            assert event["total_rows"] == 10500
            assert event["cdc_lag"] == 0

    @pytest.mark.asyncio
    async def test_publish_migration_completed_default_values(self, mock_kafka_producer):
        """Testa publicação de migration.completed com valores padrão."""
        # Arrange
        with patch(
            "src.producers.migration_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = MigrationProducer()
            await producer.start()

            # Act
            await producer.publish_migration_completed(job_id="job-001")

            # Assert
            call_args = mock_kafka_producer.send_and_wait.call_args
            event = call_args[1]["value"]
            assert event["status"] == "completed"
            assert event["total_rows"] == 0
            assert event["cdc_lag"] == 0

    @pytest.mark.asyncio
    async def test_publish_migration_failed(self, mock_kafka_producer):
        """Testa publicação de evento migration.failed."""
        # Arrange
        with patch(
            "src.producers.migration_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = MigrationProducer()
            await producer.start()

            # Act
            await producer.publish_migration_failed(
                job_id="job-001",
                error="Connection timeout",
                phase="batch_migration",
            )

            # Assert
            call_args = mock_kafka_producer.send_and_wait.call_args
            event = call_args[1]["value"]
            assert event["event_type"] == "migration.failed"
            assert event["job_id"] == "job-001"
            assert event["error"] == "Connection timeout"
            assert event["phase"] == "batch_migration"

    @pytest.mark.asyncio
    async def test_publish_without_start_raises_error(self):
        """Testa publicação sem start levanta RuntimeError."""
        # Arrange
        producer = MigrationProducer()

        # Act & Assert
        with pytest.raises(RuntimeError, match="Producer not started"):
            await producer.publish_migration_started(
                job_id="job-001",
                legacy_db="postgresql://localhost/legacy",
                tables=["users"],
            )

    @pytest.mark.asyncio
    async def test_kafka_error_handling(self, mock_kafka_producer):
        """Testa tratamento de erro do Kafka."""
        # Arrange
        from tenacity import RetryError

        mock_kafka_producer.send_and_wait = AsyncMock(side_effect=KafkaError("Connection lost"))
        with patch(
            "src.producers.migration_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = MigrationProducer()
            await producer.start()

            # Act & Assert - Tenacity RetryError após esgotar retries
            with pytest.raises(RetryError):
                await producer.publish_migration_started(
                    job_id="job-001",
                    legacy_db="postgresql://localhost/legacy",
                    tables=["users"],
                )

    @pytest.mark.asyncio
    async def test_retry_on_kafka_error(self, mock_kafka_producer):
        """Testa que producer faz retry em caso de erro Kafka."""
        # Arrange
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise KafkaError("Temporary failure")
            return None

        mock_kafka_producer.send_and_wait = AsyncMock(side_effect=side_effect)

        with patch(
            "src.producers.migration_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = MigrationProducer()
            await producer.start()

            # Act - Não deve levantar exceção após retry bem-sucedido
            await producer.publish_migration_started(
                job_id="job-001",
                legacy_db="postgresql://localhost/legacy",
                tables=["users"],
            )

            # Assert - Deve ter tentado 2 vezes
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_multiple_events_sequence(self, mock_kafka_producer):
        """Testa sequência de múltiplos eventos de migração."""
        # Arrange
        with patch(
            "src.producers.migration_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = MigrationProducer()
            await producer.start()

            # Act - Simular ciclo de vida completo
            await producer.publish_migration_started(
                job_id="job-001",
                legacy_db="postgresql://localhost/legacy",
                tables=["users"],
            )

            await producer.publish_migration_progress(
                job_id="job-001",
                phase="batch_migration",
                table="users",
                total_migrated=5000,
                total_expected=10000,
                progress_percent=50.0,
            )

            await producer.publish_migration_progress(
                job_id="job-001",
                phase="batch_migration",
                table="users",
                total_migrated=10000,
                total_expected=10000,
                progress_percent=100.0,
            )

            await producer.publish_batch_completed(
                job_id="job-001",
                tables_completed=["users"],
                total_rows=10000,
                duration_seconds=300,
            )

            await producer.publish_cdc_started(
                job_id="job-001",
                connector_id="postgres-connector-job-001",
                kafka_topic="pg-legacy.public.users",
            )

            await producer.publish_migration_completed(
                job_id="job-001",
                total_rows=10000,
            )

            # Assert - 6 eventos publicados
            assert mock_kafka_producer.send_and_wait.call_count == 6


class TestMigrationProducerSync:
    """Testes síncronos para MigrationProducer."""

    def test_create_event_base(self):
        """Testa criação de base do evento."""
        # Arrange
        producer = MigrationProducer()

        # Act
        event_base = producer._create_event_base("test.event", "job-123")

        # Assert
        assert event_base["event_type"] == "test.event"
        assert event_base["job_id"] == "job-123"
        assert "timestamp" in event_base
        assert event_base["source_service"] == "data-migration"

    def test_json_serializer_datetime(self):
        """Testa serialização JSON de datetime."""
        # Arrange
        producer = MigrationProducer()
        test_datetime = datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc)

        # Act
        result = producer._json_serializer(test_datetime)

        # Assert
        assert result == "2026-04-16T10:00:00+00:00"

    def test_json_serializer_unsupported_type(self):
        """Testa que tipo não suportado levanta TypeError."""
        # Arrange
        producer = MigrationProducer()

        # Act & Assert
        with pytest.raises(TypeError, match="not serializable"):
            producer._json_serializer(object())

    def test_sanitize_connection_string_with_password(self):
        """Testa sanitização de connection string com senha."""
        # Arrange
        producer = MigrationProducer()
        connection = "postgresql://user:secret123@localhost:5432/legacy"

        # Act
        result = producer._sanitize_connection_string(connection)

        # Assert
        assert "secret123" not in result
        assert "***" in result
        assert "@localhost:5432/legacy" in result

    def test_sanitize_connection_string_without_password(self):
        """Testa sanitização de connection string sem senha."""
        # Arrange
        producer = MigrationProducer()
        connection = "postgresql://localhost/legacy"

        # Act
        result = producer._sanitize_connection_string(connection)

        # Assert
        assert result == connection

    def test_get_singleton_migration_producer(self):
        """Testa que get_migration_producer retorna singleton."""
        # Act
        producer1 = get_migration_producer()
        producer2 = get_migration_producer()

        # Assert
        assert producer1 is producer2
        assert isinstance(producer1, MigrationProducer)
