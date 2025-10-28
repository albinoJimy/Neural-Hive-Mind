"""Client modules for external integrations."""
from .mongodb_client import MongoDBClient
from .redis_client import RedisClient
from .kafka_request_consumer import KafkaRequestConsumer
from .kafka_response_producer import KafkaResponseProducer
from .service_registry_client import ServiceRegistryClient

__all__ = [
    "MongoDBClient",
    "RedisClient",
    "KafkaRequestConsumer",
    "KafkaResponseProducer",
    "ServiceRegistryClient",
]
