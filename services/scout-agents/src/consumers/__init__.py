"""Kafka consumers para Scout Agents."""

from src.consumers.digital_events_consumer import DigitalEventsConsumer
from src.consumers.signal_consumer import SignalFeedbackConsumer

__all__ = [
    "SignalFeedbackConsumer",
    "DigitalEventsConsumer",
]
