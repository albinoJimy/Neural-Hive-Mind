"""Kafka consumers para geração de documentos on-demand."""

from src.kafka.document_event_consumer import (
    DocumentEventConsumer,
    create_document_event_consumer,
)

__all__ = [
    "DocumentEventConsumer",
    "create_document_event_consumer",
]
