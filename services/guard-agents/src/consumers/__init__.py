"""Kafka consumers para Guard Agents."""

from src.consumers.incident_feedback_consumer import IncidentFeedbackConsumer
from src.consumers.ticket_consumer import TicketConsumer

__all__ = [
    "TicketConsumer",
    "IncidentFeedbackConsumer",
]
