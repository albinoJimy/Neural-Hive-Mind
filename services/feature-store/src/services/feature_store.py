"""
Feature Store Service

Gerencia armazenamento, recuperação e computação de features.
Coordena MongoDB, Redis cache e pipeline de computação.
"""

import structlog
from typing import Dict, Any, Optional, List
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError, PyMongoError

from src.config.settings import Settings
from src.models.feature import (
    FeatureVector,
    FeatureComputationRequest,
    ComputationStatus,
    FeatureResponse,
    FeatureListResponse
)
from src.services.cache_service import RedisCacheService
from src.services.computation import FeatureComputationPipeline

logger = structlog.get_logger()


class FeatureStoreService:
    """Serviço principal de Feature Store"""

    def __init__(
        self,
        settings: Settings,
        mongodb_client: AsyncIOMotorClient,
        cache_service: RedisCacheService
    ):
        self.settings = settings
        self.mongodb_client = mongodb_client
        self.cache_service = cache_service
        self.computation_pipeline = FeatureComputationPipeline(
            timeout_seconds=settings.computation_timeout_seconds
        )

        # Coleção MongoDB
        self.db = self.mongodb_client[settings.mongodb_database]
        self.collection = self.db[settings.mongodb_features_collection]

        # Métricas
        self._computation_count = 0
        self._cache_hits = 0
        self._cache_misses = 0

    async def create_indexes(self):
        """Cria índices MongoDB necessários"""
        await self.collection.create_index('plan_id', unique=True)
        await self.collection.create_index('computed_at')
        await self.collection.create_index([('metadata.num_tasks', 1)])
        await self.collection.create_index('computation_status')
        logger.info('Índices MongoDB criados')

    async def get_features(
        self,
        plan_id: str,
        use_cache: bool = True
    ) -> Optional[FeatureVector]:
        """
        Busca features para um plano

        Args:
            plan_id: ID do plano
            use_cache: Se deve usar cache

        Returns:
            FeatureVector ou None se não encontrado
        """
        # Tenta cache primeiro
        if use_cache and self.cache_service.is_available():
            cached = await self.cache_service.get(plan_id)
            if cached:
                self._cache_hits += 1
                cached['cache_hit'] = True
                return FeatureVector(**cached)

        self._cache_misses += 1

        # Busca no MongoDB
        document = await self.collection.find_one({'plan_id': plan_id})
        if document:
            document.pop('_id', None)
            feature_vector = FeatureVector(**document)

            # Salva no cache
            if use_cache and self.cache_service.is_available():
                await self.cache_service.set(
                    plan_id,
                    document,
                    ttl_seconds=self.settings.redis_cache_ttl_seconds
                )

            return feature_vector

        return None

    async def save_features(
        self,
        features: FeatureVector,
        update_cache: bool = True
    ) -> bool:
        """
        Salva features no MongoDB e cache

        Args:
            features: FeatureVector a salvar
            update_cache: Se deve atualizar cache

        Returns:
            True se salvo com sucesso
        """
        try:
            document = features.model_dump(mode='json')

            # Upsert no MongoDB
            result = await self.collection.update_one(
                {'plan_id': features.plan_id},
                {'$set': document},
                upsert=True
            )

            # Atualiza cache
            if update_cache and self.cache_service.is_available():
                await self.cache_service.set(
                    features.plan_id,
                    document,
                    ttl_seconds=self.settings.redis_cache_ttl_seconds
                )

            logger.info(
                'Features salvas',
                plan_id=features.plan_id,
                upserted=result.upserted_id is not None
            )

            return True

        except PyMongoError as e:
            logger.error('Erro ao salvar features', plan_id=features.plan_id, error=str(e))
            return False

    async def compute_and_save(
        self,
        request: FeatureComputationRequest
    ) -> FeatureVector:
        """
        Computa e salva features para um plano

        Args:
            request: FeatureComputationRequest

        Returns:
            FeatureVector com features computadas
        """
        plan_id = request.plan_id

        # Verifica se já existe e não deve forçar recomputação
        if not request.force_recompute:
            existing = await self.get_features(
                plan_id,
                use_cache=not request.skip_cache
            )
            if existing:
                logger.info('Features já existem', plan_id=plan_id)
                return existing

        # Computa features
        logger.info('Computando features', plan_id=plan_id)
        self._computation_count += 1

        try:
            feature_vector = await self.computation_pipeline.compute_all(
                plan_id,
                request.cognitive_plan
            )

            # Salva
            await self.save_features(feature_vector)

            return feature_vector

        except Exception as e:
            logger.error('Erro na computação', plan_id=plan_id, error=str(e))
            # Retorna features com status FAILED
            return FeatureVector(
                plan_id=plan_id,
                metadata=self.computation_pipeline._default_metadata(),
                computation_status=ComputationStatus.FAILED,
                computation_error=str(e)
            )

    async def delete_features(
        self,
        plan_id: str,
        clear_cache: bool = True
    ) -> bool:
        """
        Deleta features de um plano

        Args:
            plan_id: ID do plano
            clear_cache: Se deve limpar cache também

        Returns:
            True se deletado com sucesso
        """
        # Deleta do MongoDB
        result = await self.collection.delete_one({'plan_id': plan_id})
        deleted_mongo = result.deleted_count > 0

        # Deleta do cache
        deleted_cache = False
        if clear_cache and self.cache_service.is_available():
            deleted_cache = await self.cache_service.delete(plan_id)

        logger.info(
            'Features deletadas',
            plan_id=plan_id,
            deleted_mongo=deleted_mongo,
            deleted_cache=deleted_cache
        )

        return deleted_mongo or deleted_cache

    async def list_features(
        self,
        limit: int = 50,
        offset: int = 0,
        status_filter: Optional[ComputationStatus] = None
    ) -> FeatureListResponse:
        """
        Lista features com paginação

        Args:
            limit: Limite de resultados
            offset: Offset para paginação
            status_filter: Filtro por status

        Returns:
            FeatureListResponse
        """
        query = {}
        if status_filter:
            query['computation_status'] = status_filter.value

        cursor = self.collection.find(query).sort(
            'computed_at', -1
        ).skip(offset).limit(limit)

        features = []
        async for document in cursor:
            document.pop('_id', None)
            features.append(document)

        return FeatureListResponse(
            success=True,
            count=len(features),
            features=features,
            message=f"Listados {len(features)} features"
        )

    async def get_metrics(self) -> Dict[str, Any]:
        """
        Retorna métricas do Feature Store

        Returns:
            Dict com métricas
        """
        # Total de features no MongoDB
        total_features = await self.collection.count_documents({})

        # Cache stats
        cache_stats = await self.cache_service.get_stats() if self.cache_service.is_available() else {}

        # Cache hit rate
        total_requests = self._cache_hits + self._cache_misses
        cache_hit_rate = (
            self._cache_hits / total_requests
            if total_requests > 0
            else 0.0
        )

        return {
            'total_features': total_features,
            'cached_features': cache_stats.get('keys_count', 0),
            'computation_count': self._computation_count,
            'cache_hits': self._cache_hits,
            'cache_misses': self._cache_misses,
            'cache_hit_rate': cache_hit_rate,
            'cache_available': self.cache_service.is_available()
        }

    async def get_features_by_plan_ids(
        self,
        plan_ids: List[str]
    ) -> Dict[str, FeatureVector]:
        """
        Busca features para múltiplos planos

        Args:
            plan_ids: Lista de IDs de planos

        Returns:
            Dict mapeando plan_id -> FeatureVector
        """
        cursor = self.collection.find({'plan_id': {'$in': plan_ids}})

        result = {}
        async for document in cursor:
            document.pop('_id', None)
            plan_id = document['plan_id']
            result[plan_id] = FeatureVector(**document)

        return result
