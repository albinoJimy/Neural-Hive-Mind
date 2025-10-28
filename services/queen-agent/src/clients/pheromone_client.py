import structlog
from typing import Dict, List, Any
from datetime import datetime

from .redis_client import RedisClient
from ..config import Settings


logger = structlog.get_logger()


class PheromoneClient:
    """Cliente para feromônios digitais no Redis"""

    def __init__(self, redis_client: RedisClient, settings: Settings):
        self.redis_client = redis_client
        self.settings = settings
        self.prefix = settings.REDIS_PHEROMONE_PREFIX

    async def publish_pheromone(
        self,
        pheromone_type: str,
        domain: str,
        strength: float,
        metadata: Dict[str, Any]
    ) -> None:
        """Publicar feromônio"""
        try:
            key = f"{self.prefix}{domain}:{pheromone_type}"

            pheromone_data = {
                "strength": strength,
                "last_updated": int(datetime.now().timestamp() * 1000),
                "metadata": metadata
            }

            await self.redis_client.cache_strategic_context(
                key,
                pheromone_data,
                ttl_seconds=86400  # 24 horas
            )

            logger.debug(
                "pheromone_published",
                type=pheromone_type,
                domain=domain,
                strength=strength
            )

        except Exception as e:
            logger.error("pheromone_publish_failed", error=str(e))

    async def get_pheromone_strength(self, domain: str, pheromone_type: str) -> float:
        """Obter força de feromônio"""
        try:
            key = f"{self.prefix}{domain}:{pheromone_type}"
            data = await self.redis_client.get_cached_context(key)

            if data and 'strength' in data:
                return data['strength']

            return 0.0

        except Exception as e:
            logger.error("pheromone_get_failed", error=str(e))
            return 0.0

    async def get_domain_signals(self, domain: str) -> Dict[str, float]:
        """Obter todos os sinais de feromônio de um domínio"""
        signals = {}

        for pheromone_type in ['SUCCESS', 'FAILURE', 'WARNING']:
            strength = await self.get_pheromone_strength(domain, pheromone_type)
            signals[pheromone_type] = strength

        return signals

    async def get_success_trails(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Obter trilhas de sucesso mais fortes (stub simplificado)"""
        # TODO: Implementar scan de keys Redis com padrão pheromone:strategic:*:SUCCESS
        return []
