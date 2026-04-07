"""
Clients do Service Registry

Notas de migração etcd→Redis (OPS-003):
- RedisRegistryClient é o cliente atual para registro de agentes
- EtcdClient foi removido (era apenas um alias)
- Ver docs/service-registry/MIGRATION_ETCD_TO_REDIS.md para detalhes
"""

from .autocura_producer import AutocuraEventProducer
from .pheromone_client import PheromoneClient
from .redis_registry_client import RedisRegistryClient

__all__ = ["AutocuraEventProducer", "RedisRegistryClient", "PheromoneClient"]
