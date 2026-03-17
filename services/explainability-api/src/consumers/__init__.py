"""
Consumers Kafka para Explainability API.

Este módulo contém consumers Kafka que escutam eventos de decisão
e geram explicações automaticamente.
"""

from src.consumers.consensus_decision_consumer import ConsensusDecisionConsumer

__all__ = ['ConsensusDecisionConsumer']
