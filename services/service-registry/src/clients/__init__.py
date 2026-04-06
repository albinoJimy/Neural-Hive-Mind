# Clientes do Service Registry
from .pheromone_client import PheromoneClient
from .redis_registry_client import RedisRegistryClient

__all__ = ["PheromoneClient", "RedisRegistryClient"]
