"""
Producers Kafka para Explainability API.

Este módulo contém producers Kafka que publicam eventos de explicação.
"""

from src.producers.explanation_producer import ExplanationProducer

__all__ = ["ExplanationProducer"]
