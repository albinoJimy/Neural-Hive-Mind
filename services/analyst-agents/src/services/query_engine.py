import structlog
import asyncio
import hashlib
import json
from typing import Dict, List, Optional

logger = structlog.get_logger()


class QueryEngine:
    def __init__(self, clickhouse_client, neo4j_client, elasticsearch_client, prometheus_client, redis_client):
        self.clickhouse = clickhouse_client
        self.neo4j = neo4j_client
        self.elasticsearch = elasticsearch_client
        self.prometheus = prometheus_client
        self.redis = redis_client

    async def query_multi_source(self, query_spec: Dict) -> Dict:
        """Consultar múltiplas fontes em paralelo"""
        try:
            sources = query_spec.get('sources', [])
            use_cache = query_spec.get('use_cache', True)

            # Gerar chave de cache
            query_key = self._generate_query_key(query_spec)

            # Verificar cache
            if use_cache:
                cached = await self.redis.get_cached_query_result(query_key)
                if cached:
                    logger.debug('query_cache_hit', query_key=query_key)
                    return {'results': cached, 'cached': True}

            # Executar consultas em paralelo
            tasks = []
            for source in sources:
                if source == 'clickhouse':
                    tasks.append(self._query_clickhouse(query_spec))
                elif source == 'neo4j':
                    tasks.append(self._query_neo4j(query_spec))
                elif source == 'elasticsearch':
                    tasks.append(self._query_elasticsearch(query_spec))
                elif source == 'prometheus':
                    tasks.append(self._query_prometheus(query_spec))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Consolidar resultados
            consolidated = self.consolidate_results(dict(zip(sources, results)))

            # Cachear resultado
            if use_cache:
                await self.redis.cache_query_result(query_key, consolidated, ttl=600)

            return {'results': consolidated, 'cached': False}

        except Exception as e:
            logger.error('query_multi_source_failed', error=str(e))
            return {'results': {}, 'error': str(e)}

    async def _query_clickhouse(self, query_spec: Dict) -> Dict:
        """Consultar ClickHouse"""
        try:
            time_window = query_spec.get('time_window', {})
            metrics = query_spec.get('metrics', [])

            result = self.clickhouse.get_execution_statistics(
                time_window.get('start'),
                time_window.get('end')
            )
            return {'source': 'clickhouse', 'data': result}
        except Exception as e:
            logger.error('clickhouse_query_failed', error=str(e))
            return {'source': 'clickhouse', 'error': str(e)}

    async def _query_neo4j(self, query_spec: Dict) -> Dict:
        """Consultar Neo4j"""
        try:
            filters = query_spec.get('filters', {})
            intent_id = filters.get('intent_id')

            if intent_id:
                result = await self.neo4j.analyze_intent_flow(intent_id)
                return {'source': 'neo4j', 'data': result}
            return {'source': 'neo4j', 'data': []}
        except Exception as e:
            logger.error('neo4j_query_failed', error=str(e))
            return {'source': 'neo4j', 'error': str(e)}

    async def _query_elasticsearch(self, query_spec: Dict) -> Dict:
        """Consultar Elasticsearch"""
        try:
            time_window = query_spec.get('time_window', {})
            filters = query_spec.get('filters', {})

            result = await self.elasticsearch.search_logs(
                time_window.get('start'),
                time_window.get('end'),
                filters
            )
            return {'source': 'elasticsearch', 'data': result}
        except Exception as e:
            logger.error('elasticsearch_query_failed', error=str(e))
            return {'source': 'elasticsearch', 'error': str(e)}

    async def _query_prometheus(self, query_spec: Dict) -> Dict:
        """Consultar Prometheus"""
        try:
            time_window = query_spec.get('time_window', {})
            metrics = query_spec.get('metrics', [])

            results = {}
            for metric in metrics:
                stat = await self.prometheus.get_metric_statistics(
                    metric,
                    time_window.get('start'),
                    time_window.get('end')
                )
                results[metric] = stat

            return {'source': 'prometheus', 'data': results}
        except Exception as e:
            logger.error('prometheus_query_failed', error=str(e))
            return {'source': 'prometheus', 'error': str(e)}

    def consolidate_results(self, results: Dict) -> Dict:
        """Consolidar resultados de múltiplas fontes"""
        consolidated = {}

        for source, result in results.items():
            if isinstance(result, Exception):
                consolidated[source] = {'error': str(result)}
            elif 'error' in result:
                consolidated[source] = result
            else:
                consolidated[source] = result.get('data', {})

        return consolidated

    def _generate_query_key(self, query_spec: Dict) -> str:
        """Gerar chave de cache para consulta"""
        query_str = json.dumps(query_spec, sort_keys=True)
        return hashlib.md5(query_str.encode()).hexdigest()
