# Usar RedisRegistryClient em vez de EtcdClient para evitar conflito de protobuf
from .redis_registry_client import RedisRegistryClient as EtcdClient
from .pheromone_client import PheromoneClient

__all__ = ["EtcdClient", "PheromoneClient"]
