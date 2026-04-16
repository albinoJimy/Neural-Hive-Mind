"""Testes unitários para DocProducer."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from src.producers.doc_producer import DocProducer


@pytest.fixture
def mock_kafka_producer():
    """Cria mock do AIOKafkaProducer."""
    producer = Mock(spec=AIOKafkaProducer)
    producer.start = AsyncMock()
    producer.stop = AsyncMock()
    producer.send_and_wait = AsyncMock()
    return producer


@pytest.mark.asyncio
class TestDocProducer:
    """Testes unitários para DocProducer."""

    async def test_start_producer(self, mock_kafka_producer):
        """Testa inicialização do producer."""
        # Arrange
        with patch("src.producers.doc_producer.AIOKafkaProducer", return_value=mock_kafka_producer):
            producer = DocProducer()

            # Act
            await producer.start()

            # Assert
            mock_kafka_producer.start.assert_called_once()
            mock_kafka_producer.send_and_wait.assert_not_called()

    async def test_stop_producer(self, mock_kafka_producer):
        """Testa parada do producer."""
        # Arrange
        with patch("src.producers.doc_producer.AIOKafkaProducer", return_value=mock_kafka_producer):
            producer = DocProducer()
            await producer.start()

            # Act
            await producer.stop()

            # Assert
            mock_kafka_producer.stop.assert_called_once()

    async def test_publish_doc_uploaded(self, mock_kafka_producer):
        """Testa publicação de evento doc.uploaded."""
        # Arrange
        with patch("src.producers.doc_producer.AIOKafkaProducer", return_value=mock_kafka_producer):
            producer = DocProducer()
            await producer.start()

            # Act
            await producer.publish_doc_uploaded(
                document_id="DOC-001",
                filename="test.pdf",
                format_type="pdf",
                file_size_bytes=1024,
                uploaded_by="user@example.com",
                s3_key="docs/test.pdf",
                project_id="PROJ-001",
            )

            # Assert
            mock_kafka_producer.send_and_wait.assert_called_once()
            call_args = mock_kafka_producer.send_and_wait.call_args
            assert call_args[0][0] == "doc.events"
            event = call_args[1]["value"]
            assert event["event_type"] == "doc.uploaded"
            assert event["document_id"] == "DOC-001"
            assert event["filename"] == "test.pdf"

    async def test_publish_doc_parsed(self, mock_kafka_producer):
        """Testa publicação de evento doc.parsed."""
        # Arrange
        with patch("src.producers.doc_producer.AIOKafkaProducer", return_value=mock_kafka_producer):
            producer = DocProducer()
            await producer.start()

            # Act
            await producer.publish_doc_parsed(
                document_id="DOC-001",
                parsed_text_length=5000,
                parsing_duration_ms=1500,
                has_error=False,
            )

            # Assert
            mock_kafka_producer.send_and_wait.assert_called_once()
            call_args = mock_kafka_producer.send_and_wait.call_args
            event = call_args[1]["value"]
            assert event["event_type"] == "doc.parsed"
            assert event["document_id"] == "DOC-001"
            assert event["parsed_text_length"] == 5000
            assert event["has_error"] is False

    async def test_publish_doc_parsed_with_error(self, mock_kafka_producer):
        """Testa publicação de evento doc.parsed com erro."""
        # Arrange
        with patch("src.producers.doc_producer.AIOKafkaProducer", return_value=mock_kafka_producer):
            producer = DocProducer()
            await producer.start()

            # Act
            await producer.publish_doc_parsed(
                document_id="DOC-001",
                parsed_text_length=0,
                parsing_duration_ms=500,
                has_error=True,
                error_message="Failed to parse PDF",
            )

            # Assert
            call_args = mock_kafka_producer.send_and_wait.call_args
            event = call_args[1]["value"]
            assert event["has_error"] is True
            assert event["error_message"] == "Failed to parse PDF"

    async def test_publish_doc_entities_extracted(self, mock_kafka_producer):
        """Testa publicação de evento doc.entities_extracted."""
        # Arrange
        with patch("src.producers.doc_producer.AIOKafkaProducer", return_value=mock_kafka_producer):
            producer = DocProducer()
            await producer.start()

            # Act
            await producer.publish_doc_entities_extracted(
                document_id="DOC-001",
                entity_count=15,
                entity_types=["functionality", "api", "data_model"],
                extraction_duration_ms=3000,
            )

            # Assert
            call_args = mock_kafka_producer.send_and_wait.call_args
            event = call_args[1]["value"]
            assert event["event_type"] == "doc.entities_extracted"
            assert event["document_id"] == "DOC-001"
            assert event["entity_count"] == 15
            assert "functionality" in event["entity_types"]

    async def test_publish_doc_approved(self, mock_kafka_producer):
        """Testa publicação de evento doc.approved."""
        # Arrange
        with patch("src.producers.doc_producer.AIOKafkaProducer", return_value=mock_kafka_producer):
            producer = DocProducer()
            await producer.start()

            # Act
            await producer.publish_doc_approved(
                document_id="DOC-001",
                approved_by="admin@example.com",
                approval_notes="Ready for migration",
            )

            # Assert
            call_args = mock_kafka_producer.send_and_wait.call_args
            event = call_args[1]["value"]
            assert event["event_type"] == "doc.approved"
            assert event["document_id"] == "DOC-001"
            assert event["approved_by"] == "admin@example.com"
            assert event["approval_notes"] == "Ready for migration"

    async def test_send_to_dlq(self, mock_kafka_producer):
        """Testa envio para DLQ."""
        # Arrange
        with patch("src.producers.doc_producer.AIOKafkaProducer", return_value=mock_kafka_producer):
            producer = DocProducer()
            await producer.start()

            # Act
            await producer.send_to_dlq(
                original_value=b'{"test": "data"}',
                reason="Processing failed",
            )

            # Assert - send_to_dlq chama send_and_wait uma vez para DLQ
            assert mock_kafka_producer.send_and_wait.call_count == 1
            call_args = mock_kafka_producer.send_and_wait.call_args
            assert call_args[0][0] == "doc-ingestion.dlq"  # ou o tópico DLQ correto

    async def test_publish_without_start_raises_error(self):
        """Testa publicação sem start levanta RuntimeError."""
        # Arrange
        producer = DocProducer()

        # Act & Assert
        with pytest.raises(RuntimeError, match="Producer not started"):
            await producer.publish_doc_uploaded(
                document_id="DOC-001",
                filename="test.pdf",
                format_type="pdf",
                file_size_bytes=1024,
                uploaded_by="user@example.com",
                s3_key="docs/test.pdf",
            )

    async def test_kafka_error_handling(self, mock_kafka_producer):
        """Testa tratamento de erro do Kafka."""
        # Arrange
        mock_kafka_producer.send_and_wait = AsyncMock(side_effect=KafkaError("Connection lost"))
        with patch("src.producers.doc_producer.AIOKafkaProducer", return_value=mock_kafka_producer):
            producer = DocProducer()
            await producer.start()

            # Act & Assert
            with pytest.raises(KafkaError):
                await producer.publish_doc_uploaded(
                    document_id="DOC-001",
                    filename="test.pdf",
                    format_type="pdf",
                    file_size_bytes=1024,
                    uploaded_by="user@example.com",
                    s3_key="docs/test.pdf",
                )

    def test_create_event_base(self):
        """Testa criação de base do evento."""
        # Arrange
        producer = DocProducer()

        # Act
        event_base = producer._create_event_base("test.event")

        # Assert
        assert event_base["event_type"] == "test.event"
        assert "event_id" in event_base
        assert "timestamp" in event_base
        assert event_base["source_service"] == "doc-ingestion"

    def test_event_id_unique(self):
        """Testa que IDs de evento são únicos."""
        # Arrange
        producer = DocProducer()

        # Act
        event1 = producer._create_event_base("test.event")
        event2 = producer._create_event_base("test.event")

        # Assert
        assert event1["event_id"] != event2["event_id"]

    async def test_publish_doc_uploaded_without_project_id(self, mock_kafka_producer):
        """Testa publicação de doc.uploaded sem project_id."""
        # Arrange
        with patch("src.producers.doc_producer.AIOKafkaProducer", return_value=mock_kafka_producer):
            producer = DocProducer()
            await producer.start()

            # Act - Sem project_id (opcional)
            await producer.publish_doc_uploaded(
                document_id="DOC-001",
                filename="test.pdf",
                format_type="pdf",
                file_size_bytes=1024,
                uploaded_by="user@example.com",
                s3_key="docs/test.pdf",
            )

            # Assert
            call_args = mock_kafka_producer.send_and_wait.call_args
            event = call_args[1]["value"]
            assert event["project_id"] is None

    async def test_publish_doc_approved_without_notes(self, mock_kafka_producer):
        """Testa publicação de doc.approved sem notas."""
        # Arrange
        with patch("src.producers.doc_producer.AIOKafkaProducer", return_value=mock_kafka_producer):
            producer = DocProducer()
            await producer.start()

            # Act - Sem approval_notes (opcional)
            await producer.publish_doc_approved(
                document_id="DOC-001",
                approved_by="admin@example.com",
            )

            # Assert
            call_args = mock_kafka_producer.send_and_wait.call_args
            event = call_args[1]["value"]
            assert event["approval_notes"] is None
