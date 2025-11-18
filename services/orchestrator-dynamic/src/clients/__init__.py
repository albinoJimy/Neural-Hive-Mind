"""
Clientes para integração com MongoDB, Kafka, Redis e Service Registry.
"""
from src.clients.mongodb_client import MongoDBClient
from src.clients.kafka_producer import KafkaProducerClient
from src.clients.service_registry_client import ServiceRegistryClient
from src.clients.redis_client import get_redis_client, close_redis_client

__all__ = [
    'MongoDBClient',
    'KafkaProducerClient',
    'ServiceRegistryClient',
    'get_redis_client',
    'close_redis_client'
]
