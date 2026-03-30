"""Kafka consumers para Scout Agents."""

from src.consumers.signal_consumer import SignalFeedbackConsumer

__all__ = [
    "SignalFeedbackConsumer",
]
