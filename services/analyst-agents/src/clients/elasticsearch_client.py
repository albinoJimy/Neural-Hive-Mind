import structlog
from elasticsearch import AsyncElasticsearch
from typing import List, Dict, Optional

logger = structlog.get_logger()


class ElasticsearchClient:
    def __init__(self, hosts: List[str], user: Optional[str], password: Optional[str]):
        self.hosts = hosts
        self.user = user
        self.password = password
        self.client = None

    async def initialize(self):
        """Conectar ao Elasticsearch"""
        try:
            auth = (self.user, self.password) if self.user and self.password else None
            self.client = AsyncElasticsearch(hosts=self.hosts, basic_auth=auth)
            await self.client.ping()
            logger.info('elasticsearch_client_initialized', hosts=self.hosts)
        except Exception as e:
            logger.error('elasticsearch_client_initialization_failed', error=str(e))
            raise

    async def close(self):
        """Fechar conexão"""
        if self.client:
            await self.client.close()
            logger.info('elasticsearch_client_closed')

    async def search(self, index: str, query: dict, size: int = 100, from_: int = 0) -> List[dict]:
        """Executar consulta DSL"""
        try:
            result = await self.client.search(index=index, body=query, size=size, from_=from_)
            return [hit['_source'] for hit in result['hits']['hits']]
        except Exception as e:
            logger.error('elasticsearch_search_failed', error=str(e))
            return []

    async def search_logs(self, start: int, end: int, filters: dict, size: int = 100) -> List[dict]:
        """Buscar logs por janela temporal e filtros"""
        query = {
            'query': {
                'bool': {
                    'must': [
                        {'range': {'@timestamp': {'gte': start, 'lte': end}}}
                    ],
                    'filter': [{'term': {k: v}} for k, v in filters.items()]
                }
            },
            'sort': [{'@timestamp': {'order': 'desc'}}]
        }
        return await self.search('logs-*', query, size=size)

    async def get_error_patterns(self, start: int, end: int, min_occurrences: int = 5) -> List[dict]:
        """Identificar padrões de erro recorrentes"""
        query = {
            'query': {
                'bool': {
                    'must': [
                        {'range': {'@timestamp': {'gte': start, 'lte': end}}},
                        {'term': {'level': 'error'}}
                    ]
                }
            },
            'aggs': {
                'error_patterns': {
                    'terms': {'field': 'message.keyword', 'min_doc_count': min_occurrences, 'size': 20}
                }
            }
        }

        result = await self.client.search(index='logs-*', body=query, size=0)
        return result.get('aggregations', {}).get('error_patterns', {}).get('buckets', [])

    async def search_by_correlation_id(self, correlation_id: str) -> List[dict]:
        """Buscar todos os logs/eventos de uma correlação"""
        query = {'query': {'term': {'correlation_id': correlation_id}}, 'sort': [{'@timestamp': {'order': 'asc'}}]}
        return await self.search('logs-*', query, size=1000)
