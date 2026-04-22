"""
Clientes para integração com MongoDB, Kafka, Redis, Service Registry e Agentic Delegation.
"""

from src.clients.agentic_delegation_client import AgenticDelegationClient
from src.clients.execution_ticket_client import ExecutionTicketClient
from src.clients.kafka_producer import KafkaProducerClient
from src.clients.mongodb_client import MongoDBClient
from src.clients.pagerduty_client import PagerDutyClient
from src.clients.redis_client import close_redis_client, get_redis_client
from src.clients.self_healing_client import SelfHealingClient
from src.clients.service_registry_client import ServiceRegistryClient
from src.clients.slack_client import SlackClient

__all__ = [
    "ExecutionTicketClient",
    "KafkaProducerClient",
    "MongoDBClient",
    "SelfHealingClient",
    "ServiceRegistryClient",
    "SlackClient",
    "PagerDutyClient",
    "AgenticDelegationClient",
    "close_redis_client",
    "get_redis_client",
]
