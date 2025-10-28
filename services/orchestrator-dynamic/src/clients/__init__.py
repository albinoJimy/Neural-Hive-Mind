"""
Clientes para integração com MongoDB e Kafka.
"""
from src.clients.mongodb_client import MongoDBClient
from src.clients.kafka_producer import KafkaProducerClient

__all__ = ['MongoDBClient', 'KafkaProducerClient']
