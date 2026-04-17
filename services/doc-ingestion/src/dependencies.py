"""Dependency injection container for doc-ingestion service."""

from typing import Optional

from src.producers.doc_producer import DocProducer

# Global instances
_kafka_producer: Optional[DocProducer] = None


def set_doc_producer(producer: DocProducer):
    """Set the global Kafka producer instance."""
    global _kafka_producer
    _kafka_producer = producer


def get_doc_producer() -> Optional[DocProducer]:
    """Get the global Kafka producer instance."""
    return _kafka_producer


def clear_doc_producer():
    """Clear the global Kafka producer instance (for testing)."""
    global _kafka_producer
    _kafka_producer = None
