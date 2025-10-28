import structlog
import httpx
from typing import Dict, List, Optional

logger = structlog.get_logger()


class MemoryLayerAPIClient:
    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url
        self.timeout = timeout
        self.client = None

    async def initialize(self):
        """Inicializar cliente HTTP"""
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        logger.info('memory_layer_client_initialized', base_url=self.base_url)

    async def close(self):
        """Fechar cliente"""
        if self.client:
            await self.client.aclose()
        logger.info('memory_layer_client_closed')

    async def query_memory(
        self,
        query_type: str,
        entity_id: str,
        time_range: Optional[Dict] = None,
        use_cache: bool = True
    ) -> Dict:
        """Consultar memória unificada"""
        try:
            payload = {
                'query_type': query_type,
                'entity_id': entity_id,
                'use_cache': use_cache
            }
            if time_range:
                payload['time_range'] = time_range

            response = await self.client.post('/api/v1/memory/query', json=payload)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.error('memory_query_failed', error=str(e), entity_id=entity_id)
            return {}
        except Exception as e:
            logger.error('memory_query_error', error=str(e))
            return {}

    async def get_context(self, entity_id: str, context_type: str) -> Dict:
        """Obter contexto de entidade"""
        try:
            response = await self.client.get(
                f'/api/v1/memory/context/{entity_id}',
                params={'type': context_type}
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.error('get_context_failed', error=str(e), entity_id=entity_id)
            return {}
        except Exception as e:
            logger.error('get_context_error', error=str(e))
            return {}

    async def get_lineage(self, entity_id: str, depth: int = 3) -> Dict:
        """Obter lineage de dados"""
        try:
            response = await self.client.get(
                f'/api/v1/memory/lineage/{entity_id}',
                params={'depth': depth}
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.error('get_lineage_failed', error=str(e), entity_id=entity_id)
            return {}
        except Exception as e:
            logger.error('get_lineage_error', error=str(e))
            return {}

    async def get_quality_stats(self, data_type: str) -> Dict:
        """Obter estatísticas de qualidade de dados"""
        try:
            response = await self.client.get(
                '/api/v1/memory/quality/stats',
                params={'data_type': data_type}
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.error('get_quality_stats_failed', error=str(e))
            return {}
        except Exception as e:
            logger.error('get_quality_stats_error', error=str(e))
            return {}

    async def invalidate_cache(self, pattern: str, cascade: bool = False) -> bool:
        """Invalidar cache"""
        try:
            payload = {'pattern': pattern, 'cascade': cascade}
            response = await self.client.post('/api/v1/memory/invalidate', json=payload)
            response.raise_for_status()
            return True

        except httpx.HTTPError as e:
            logger.error('invalidate_cache_failed', error=str(e))
            return False
        except Exception as e:
            logger.error('invalidate_cache_error', error=str(e))
            return False

    async def list_data_assets(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Listar ativos de dados catalogados"""
        try:
            response = await self.client.get(
                '/api/v1/memory/assets',
                params={'limit': limit, 'offset': offset}
            )
            response.raise_for_status()
            data = response.json()
            return data.get('assets', [])

        except httpx.HTTPError as e:
            logger.error('list_data_assets_failed', error=str(e))
            return []
        except Exception as e:
            logger.error('list_data_assets_error', error=str(e))
            return []
