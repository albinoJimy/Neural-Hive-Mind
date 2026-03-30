"""Kafka consumers para Guard Agents."""

from src.consumers.ticket_consumer import TicketConsumer
from src.consumers.incident_feedback_consumer import IncidentFeedbackConsumer

__all__ = [
    "TicketConsumer",
    "IncidentFeedbackConsumer",
]
