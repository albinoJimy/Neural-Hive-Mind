"""
Clientes para integração com MongoDB, Kafka, Redis e Service Registry.
"""
from src.clients.execution_ticket_client import ExecutionTicketClient
from src.clients.kafka_producer import KafkaProducerClient
from src.clients.mongodb_client import MongoDBClient
from src.clients.rate_limit_redis import (
    REFILL_AND_ACQUIRE_LUA,
    RedisTokenBucketBackend,
    generate_rate_limit_key,
)
from src.clients.redis_client import close_redis_client, get_redis_client
from src.clients.self_healing_client import SelfHealingClient
from src.clients.service_registry_client import ServiceRegistryClient
from src.clients.slack_client import SlackClient
from src.clients.pagerduty_client import PagerDutyClient

__all__ = [
    "REFILL_AND_ACQUIRE_LUA",
    "ExecutionTicketClient",
    "KafkaProducerClient",
    "MongoDBClient",
    "RedisTokenBucketBackend",
    "SelfHealingClient",
    "ServiceRegistryClient",
    "SlackClient",
    "PagerDutyClient",
    "close_redis_client",
    "generate_rate_limit_key",
    "get_redis_client",
]
