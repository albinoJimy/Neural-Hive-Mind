"""Consumidores Kafka para Architect Agent."""

from src.consumers.base import BaseKafkaConsumer
from src.consumers.cognitive_plan_consumer import CognitivePlanConsumer

__all__ = [
    "BaseKafkaConsumer",
    "CognitivePlanConsumer",
]
