# Usar RedisRegistryClient em vez de EtcdClient para evitar conflito de protobuf
from .pheromone_client import PheromoneClient
from .redis_registry_client import RedisRegistryClient as EtcdClient

__all__ = ["EtcdClient", "PheromoneClient"]
