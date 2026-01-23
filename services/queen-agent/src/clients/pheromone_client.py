import structlog
import time
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from datetime import datetime

from neural_hive_domain import DomainMapper, UnifiedDomain

if TYPE_CHECKING:
    from .redis_client import RedisClient
    from ..config import Settings


logger = structlog.get_logger()


# Constante de TTL do cache
CACHE_TTL_SECONDS = 60


class PheromoneClient:
    """Cliente para feromônios digitais no Redis"""

    def __init__(self, redis_client: 'RedisClient', settings: 'Settings'):
        self.redis_client = redis_client
        self.settings = settings
        # Cache local para trilhas de sucesso
        self._success_trails_cache: Optional[List[Dict[str, Any]]] = None
        self._cache_timestamp: float = 0

    async def publish_pheromone(
        self,
        pheromone_type: str,
        domain: str,
        strength: float,
        metadata: Dict[str, Any]
    ) -> None:
        """Publicar feromônio usando chave padronizada via DomainMapper"""
        try:
            # Normalizar domain para UnifiedDomain
            normalized_domain = DomainMapper.normalize(domain, 'intent_envelope')
            key = DomainMapper.to_pheromone_key(
                domain=normalized_domain,
                layer='strategic',
                pheromone_type=pheromone_type
            )

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

            # Invalidar cache de trilhas de sucesso quando publicar SUCCESS
            if pheromone_type == 'SUCCESS':
                self.invalidate_success_trails_cache()

            logger.debug(
                "pheromone_published",
                type=pheromone_type,
                domain=normalized_domain.value,
                strength=strength,
                key=key
            )

        except Exception as e:
            logger.error("pheromone_publish_failed", error=str(e))

    async def get_pheromone_strength(self, domain: str, pheromone_type: str) -> float:
        """Obter força de feromônio usando chave padronizada via DomainMapper"""
        try:
            # Normalizar domain para UnifiedDomain
            normalized_domain = DomainMapper.normalize(domain, 'intent_envelope')
            key = DomainMapper.to_pheromone_key(
                domain=normalized_domain,
                layer='strategic',
                pheromone_type=pheromone_type
            )
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

    def invalidate_success_trails_cache(self) -> None:
        """Invalidar cache de trilhas de sucesso"""
        self._success_trails_cache = None
        self._cache_timestamp = 0
        logger.debug("success_trails_cache_invalidated")

    async def get_success_trails(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Obter trilhas de sucesso mais fortes.

        Utiliza scan_iter() para iterar eficientemente sobre chaves Redis
        que correspondem ao padrão pheromone:strategic:*:SUCCESS.
        Os resultados são ordenados por força (strength) em ordem decrescente.

        Args:
            limit: Número máximo de trilhas a retornar (default: 10)

        Returns:
            Lista de trilhas de sucesso ordenadas por strength
        """
        from ..observability.metrics import QueenAgentMetrics

        try:
            # Verificar se cache é válido
            cache_age = time.time() - self._cache_timestamp
            if self._success_trails_cache is not None and cache_age < CACHE_TTL_SECONDS:
                QueenAgentMetrics.pheromone_trails_cache_hits_total.inc()
                logger.debug(
                    "success_trails_cache_hit",
                    cache_age_seconds=cache_age,
                    cached_count=len(self._success_trails_cache)
                )
                return self._success_trails_cache[:limit]

            QueenAgentMetrics.pheromone_trails_cache_misses_total.inc()

            # Padrão de busca para trilhas SUCCESS (formato unificado)
            # Formato: pheromone:strategic:{domain}:SUCCESS
            pattern = "pheromone:strategic:*:SUCCESS"
            trails: List[Dict[str, Any]] = []
            keys_scanned = 0

            start_time = time.time()

            # Usar scan_iter para evitar bloqueio do Redis
            async for key in self.redis_client.client.scan_iter(match=pattern):
                keys_scanned += 1

                # Tratar chaves malformadas
                try:
                    # Formato esperado: pheromone:strategic:{domain}:SUCCESS
                    key_parts = key.split(':')
                    if len(key_parts) != 4:
                        logger.warning("malformed_pheromone_key", key=key)
                        continue

                    # Extrair domain (UnifiedDomain não contém ':')
                    # pheromone:strategic:{domain}:SUCCESS
                    domain = key_parts[2]

                except Exception as parse_error:
                    logger.warning(
                        "pheromone_key_parse_failed",
                        key=key,
                        error=str(parse_error)
                    )
                    continue

                # Buscar dados do feromônio
                pheromone_data = await self.redis_client.get_cached_context(key)
                if not pheromone_data:
                    continue

                trail = {
                    'domain': domain,
                    'strength': pheromone_data.get('strength', 0.0),
                    'last_updated': pheromone_data.get('last_updated', 0),
                    'metadata': pheromone_data.get('metadata', {}),
                    'key': key
                }
                trails.append(trail)

            # Ordenar por strength em ordem decrescente
            trails.sort(key=lambda t: t['strength'], reverse=True)

            # Atualizar cache com lista completa ordenada
            self._success_trails_cache = trails
            self._cache_timestamp = time.time()

            # Métricas
            scan_duration = time.time() - start_time
            QueenAgentMetrics.pheromone_trails_scan_duration_seconds.observe(scan_duration)
            QueenAgentMetrics.pheromone_trails_keys_scanned_total.inc(keys_scanned)

            logger.debug(
                "success_trails_retrieved",
                count=len(trails),
                returned=min(limit, len(trails)),
                limit=limit,
                keys_scanned=keys_scanned,
                scan_duration_ms=scan_duration * 1000
            )

            # Retornar fatiado pelo limite solicitado
            return trails[:limit]

        except Exception as e:
            logger.error("get_success_trails_failed", error=str(e))
            return []
