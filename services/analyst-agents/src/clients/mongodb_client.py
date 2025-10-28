import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from typing import List, Dict, Optional
from ..models.insight import AnalystInsight

logger = structlog.get_logger()


class MongoDBClient:
    def __init__(self, uri: str, database: str, collection: str):
        self.uri = uri
        self.database_name = database
        self.collection_name = collection
        self.client = None
        self.database = None
        self.collection = None

    async def initialize(self):
        """Conectar ao MongoDB"""
        try:
            self.client = AsyncIOMotorClient(self.uri)
            self.database = self.client[self.database_name]
            self.collection = self.database[self.collection_name]

            # Criar índices
            await self._create_indexes()

            logger.info('mongodb_client_initialized', database=self.database_name)
        except Exception as e:
            logger.error('mongodb_client_initialization_failed', error=str(e))
            raise

    async def _create_indexes(self):
        """Criar índices para otimizar consultas"""
        try:
            await self.collection.create_index('insight_id', unique=True)
            await self.collection.create_index('insight_type')
            await self.collection.create_index('priority')
            await self.collection.create_index('created_at')
            await self.collection.create_index('valid_until')
            await self.collection.create_index('related_entities.entity_id')
            await self.collection.create_index('tags')
            await self.collection.create_index([
                ('insight_type', 1),
                ('priority', 1),
                ('created_at', -1)
            ])
            logger.info('mongodb_indexes_created')
        except Exception as e:
            logger.warning('mongodb_indexes_creation_failed', error=str(e))

    async def close(self):
        """Fechar conexão"""
        if self.client:
            self.client.close()
            logger.info('mongodb_client_closed')

    async def save_insight(self, insight: AnalystInsight) -> str:
        """Salvar insight"""
        try:
            doc = insight.model_dump()
            await self.collection.insert_one(doc)
            logger.info('insight_saved', insight_id=insight.insight_id)
            return insight.insight_id
        except Exception as e:
            logger.error('insight_save_failed', error=str(e), insight_id=insight.insight_id)
            raise

    async def get_insight_by_id(self, insight_id: str) -> Optional[dict]:
        """Buscar insight por ID"""
        try:
            result = await self.collection.find_one({'insight_id': insight_id})
            return result
        except Exception as e:
            logger.error('get_insight_failed', error=str(e), insight_id=insight_id)
            return None

    async def query_insights(self, filters: dict, limit: int = 100, skip: int = 0) -> List[dict]:
        """Consultar insights com filtros"""
        try:
            cursor = self.collection.find(filters).limit(limit).skip(skip).sort('created_at', -1)
            results = await cursor.to_list(length=limit)
            return results
        except Exception as e:
            logger.error('query_insights_failed', error=str(e))
            return []

    async def get_insights_by_type(self, insight_type: str, limit: int = 100) -> List[dict]:
        """Buscar insights por tipo"""
        return await self.query_insights({'insight_type': insight_type}, limit=limit)

    async def get_insights_by_priority(self, priority: str, limit: int = 100) -> List[dict]:
        """Buscar insights por prioridade"""
        return await self.query_insights({'priority': priority}, limit=limit)

    async def get_insights_by_time_range(self, start: int, end: int, limit: int = 100) -> List[dict]:
        """Buscar insights por janela temporal"""
        filters = {
            'created_at': {'$gte': start, '$lte': end}
        }
        return await self.query_insights(filters, limit=limit)

    async def get_insights_by_entity(self, entity_type: str, entity_id: str, limit: int = 100) -> List[dict]:
        """Buscar insights por entidade relacionada"""
        filters = {
            'related_entities': {
                '$elemMatch': {
                    'entity_type': entity_type,
                    'entity_id': entity_id
                }
            }
        }
        return await self.query_insights(filters, limit=limit)

    async def get_insights_by_tags(self, tags: List[str], limit: int = 100) -> List[dict]:
        """Buscar insights por tags"""
        filters = {'tags': {'$in': tags}}
        return await self.query_insights(filters, limit=limit)

    async def update_insight(self, insight_id: str, updates: dict) -> bool:
        """Atualizar insight"""
        try:
            result = await self.collection.update_one(
                {'insight_id': insight_id},
                {'$set': updates}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error('update_insight_failed', error=str(e), insight_id=insight_id)
            return False

    async def delete_expired_insights(self) -> int:
        """Limpar insights expirados"""
        try:
            import time
            now = int(time.time() * 1000)
            result = await self.collection.delete_many({
                'valid_until': {'$ne': None, '$lt': now}
            })
            deleted_count = result.deleted_count
            logger.info('expired_insights_deleted', count=deleted_count)
            return deleted_count
        except Exception as e:
            logger.error('delete_expired_insights_failed', error=str(e))
            return 0
