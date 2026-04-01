"""
Clientes para integração com MongoDB, Kafka, Redis e Service Registry.
"""
from src.clients.execution_ticket_client import ExecutionTicketClient
from src.clients.kafka_producer import KafkaProducerClient
from src.clients.mongodb_client import MongoDBClient
from src.clients.redis_client import close_redis_client, get_redis_client
from src.clients.self_healing_client import SelfHealingClient
from src.clients.service_registry_client import ServiceRegistryClient

__all__ = [
    "ExecutionTicketClient",
    "KafkaProducerClient",
    "MongoDBClient",
    "SelfHealingClient",
    "ServiceRegistryClient",
    "close_redis_client",
    "get_redis_client",
]
