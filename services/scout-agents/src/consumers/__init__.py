"""Kafka consumers para Scout Agents."""

from src.consumers.signal_consumer import SignalFeedbackConsumer
from src.consumers.digital_events_consumer import DigitalEventsConsumer

__all__ = [
    "SignalFeedbackConsumer",
    "DigitalEventsConsumer",
]
