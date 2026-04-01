"""
Feature Store Service

Gerencia armazenamento, recuperação e computação de features.
Coordena MongoDB, Redis cache, pipeline de computação e lineage tracker.
"""

from typing import Any, Dict, List, Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError
from src.config.settings import Settings
from src.models import (
    ComputationStatus,
    FeatureComputationRequest,
    FeatureListResponse,
    FeatureVector,
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
        cache_service: RedisCacheService,
        neo4j_client=None,
        lineage_tracker=None,
    ):
        self.settings = settings
        self.mongodb_client = mongodb_client
        self.cache_service = cache_service
        self.neo4j_client = neo4j_client
        self.computation_pipeline = FeatureComputationPipeline(
            timeout_seconds=settings.computation_timeout_seconds
        )

        # Coleção MongoDB
        self.db = self.mongodb_client[settings.mongodb_database]
        self.collection = self.db[settings.mongodb_features_collection]

        # Lineage Tracker (opcional)
        self.lineage_tracker = lineage_tracker

        # Métricas
        self._computation_count = 0
        self._cache_hits = 0
        self._cache_misses = 0

    async def create_indexes(self):
        """Cria índices MongoDB necessários"""
        await self.collection.create_index("plan_id", unique=True)
        await self.collection.create_index("computed_at")
        await self.collection.create_index([("metadata.num_tasks", 1)])
        await self.collection.create_index("computation_status")

        # Criar índices para lineage (se disponível)
        if self.lineage_tracker:
            await self.lineage_tracker.create_indexes()

        logger.info("Índices MongoDB criados")

    async def get_features(self, plan_id: str, use_cache: bool = True) -> Optional[FeatureVector]:
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
                cached["cache_hit"] = True
                return FeatureVector(**cached)

        self._cache_misses += 1

        # Busca no MongoDB
        document = await self.collection.find_one({"plan_id": plan_id})
        if document:
            document.pop("_id", None)
            feature_vector = FeatureVector(**document)

            # Salva no cache
            if use_cache and self.cache_service.is_available():
                await self.cache_service.set(
                    plan_id, document, ttl_seconds=self.settings.redis_cache_ttl_seconds
                )

            return feature_vector

        return None

    async def save_features(self, features: FeatureVector, update_cache: bool = True) -> bool:
        """
        Salva features no MongoDB e cache

        Args:
            features: FeatureVector a salvar
            update_cache: Se deve atualizar cache

        Returns:
            True se salvo com sucesso
        """
        try:
            document = features.model_dump(mode="json")

            # Upsert no MongoDB
            result = await self.collection.update_one(
                {"plan_id": features.plan_id}, {"$set": document}, upsert=True
            )

            # Atualiza cache
            if update_cache and self.cache_service.is_available():
                await self.cache_service.set(
                    features.plan_id, document, ttl_seconds=self.settings.redis_cache_ttl_seconds
                )

            logger.info(
                "Features salvas", plan_id=features.plan_id, upserted=result.upserted_id is not None
            )

            return True

        except PyMongoError as e:
            logger.error("Erro ao salvar features", plan_id=features.plan_id, error=str(e))
            return False

    async def compute_and_save(self, request: FeatureComputationRequest) -> FeatureVector:
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
            existing = await self.get_features(plan_id, use_cache=not request.skip_cache)
            if existing:
                logger.info("Features já existem", plan_id=plan_id)
                return existing

        # Computa features
        logger.info("Computando features", plan_id=plan_id)
        self._computation_count += 1

        try:
            feature_vector = await self.computation_pipeline.compute_all(
                plan_id, request.cognitive_plan
            )

            # Rastrear lineage (se disponível)
            if self.lineage_tracker:
                # Importar SourceType e TransformationType localmente para evitar circular
                from src.models.lineage import SourceType, TransformationType

                lineage = await self.lineage_tracker.track_feature(
                    feature_id=feature_vector.feature_id,
                    plan_id=plan_id,
                    source_type=SourceType.COGNITIVE_PLAN,
                    transformation_type=TransformationType.COMPUTED,
                    data_sources=["mongodb", "neo4j"],
                    transformation_metadata={
                        "computation_duration_ms": feature_vector.metadata.get(
                            "computation_duration_ms"
                        ),
                    },
                )

                # Adicionar lineage_id ao feature_vector
                feature_vector.lineage_id = lineage.lineage_id

                logger.info(
                    "Features computadas e salvas",
                    plan_id=plan_id,
                    lineage_id=lineage.lineage_id,
                )
            else:
                logger.info(
                    "Features computadas e salvas",
                    plan_id=plan_id,
                )

            # Salva
            await self.save_features(feature_vector)

            return feature_vector

        except Exception as e:
            logger.error("Erro na computação", plan_id=plan_id, error=str(e))
            # Retorna features com status FAILED
            return FeatureVector(
                plan_id=plan_id,
                metadata=self.computation_pipeline._default_metadata(),
                computation_status=ComputationStatus.FAILED,
                computation_error=str(e),
            )

    async def delete_features(self, plan_id: str, clear_cache: bool = True) -> bool:
        """
        Deleta features de um plano

        Args:
            plan_id: ID do plano
            clear_cache: Se deve limpar cache também

        Returns:
            True se deletado com sucesso
        """
        # Deleta do MongoDB
        result = await self.collection.delete_one({"plan_id": plan_id})
        deleted_mongo = result.deleted_count > 0

        # Deleta do cache
        deleted_cache = False
        if clear_cache and self.cache_service.is_available():
            deleted_cache = await self.cache_service.delete(plan_id)

        logger.info(
            "Features deletadas",
            plan_id=plan_id,
            deleted_mongo=deleted_mongo,
            deleted_cache=deleted_cache,
        )

        return deleted_mongo or deleted_cache

    async def list_features(
        self, limit: int = 50, offset: int = 0, status_filter: Optional[ComputationStatus] = None
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
            query["computation_status"] = status_filter.value

        cursor = self.collection.find(query).sort("computed_at", -1).skip(offset).limit(limit)

        features = []
        async for document in cursor:
            document.pop("_id", None)
            features.append(document)

        return FeatureListResponse(
            success=True,
            count=len(features),
            features=features,
            message=f"Listados {len(features)} features",
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
        cache_stats = (
            await self.cache_service.get_stats() if self.cache_service.is_available() else {}
        )

        # Cache hit rate
        total_requests = self._cache_hits + self._cache_misses
        cache_hit_rate = self._cache_hits / total_requests if total_requests > 0 else 0.0

        return {
            "total_features": total_features,
            "cached_features": cache_stats.get("keys_count", 0),
            "computation_count": self._computation_count,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": cache_hit_rate,
            "cache_available": self.cache_service.is_available(),
        }

    async def get_features_by_plan_ids(self, plan_ids: List[str]) -> Dict[str, FeatureVector]:
        """
        Busca features para múltiplos planos

        Args:
            plan_ids: Lista de IDs de planos

        Returns:
            Dict mapeando plan_id -> FeatureVector
        """
        cursor = self.collection.find({"plan_id": {"$in": plan_ids}})

        result = {}
        async for document in cursor:
            document.pop("_id", None)
            plan_id = document["plan_id"]
            result[plan_id] = FeatureVector(**document)

        return result

    # -------------------------------------------------------------------------
    # Métodos de Lineage
    # -------------------------------------------------------------------------

    async def get_feature_lineage(
        self, plan_id: str, feature_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Obtém lineage de uma feature

        Args:
            plan_id: ID do plano
            feature_id: ID da feature (opcional, busca do features se não fornecido)

        Returns:
            Dict com lineage ou None
        """
        if not self.lineage_tracker:
            return None

        # Se feature_id não fornecido, buscar das features
        if not feature_id:
            feature_vector = await self.get_features(plan_id, use_cache=False)
            if feature_vector:
                feature_id = feature_vector.feature_id
            else:
                return None

        lineage = await self.lineage_tracker.get_lineage(feature_id)
        if lineage:
            return lineage.model_dump(mode="json")

        return None

    async def get_lineage_tree(self, plan_id: str, max_depth: int = 5) -> Optional[Dict[str, Any]]:
        """
        Obtém árvore completa de lineage de uma feature

        Args:
            plan_id: ID do plano
            max_depth: Profundidade máxima da árvore

        Returns:
            Dict com árvore de lineage ou None
        """
        if not self.lineage_tracker:
            return None

        feature_vector = await self.get_features(plan_id, use_cache=False)
        if not feature_vector:
            return None

        tree = await self.lineage_tracker.get_lineage_tree(feature_vector.feature_id, max_depth)
        return tree.model_dump(mode="json")

    async def get_lineage_impact(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """
        Analisa impacto downstream de uma feature

        Args:
            plan_id: ID do plano

        Returns:
            Dict com análise de impacto ou None
        """
        if not self.lineage_tracker:
            return None

        feature_vector = await self.get_features(plan_id, use_cache=False)
        if not feature_vector:
            return None

        impact = await self.lineage_tracker.get_impact_analysis(feature_vector.feature_id)
        return impact.model_dump(mode="json")

    async def validate_lineage_integrity(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """
        Valida integridade do lineage de uma feature

        Args:
            plan_id: ID do plano

        Returns:
            Dict com relatório de validação ou None
        """
        if not self.lineage_tracker:
            return None

        feature_vector = await self.get_features(plan_id, use_cache=False)
        if not feature_vector:
            return None

        report = await self.lineage_tracker.validate_integrity(feature_vector.feature_id)
        return report.model_dump(mode="json")
