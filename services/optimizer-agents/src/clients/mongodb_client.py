from datetime import datetime
from typing import Dict, List, Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from src.config.settings import get_settings
from src.models.optimization_event import OptimizationEvent, OptimizationType
from src.models.experiment_request import ExperimentRequest

logger = structlog.get_logger()


class MongoDBClient:
    """Cliente MongoDB para persistência de otimizações e experimentos."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.optimization_collection = None
        self.experiments_collection = None

    async def connect(self):
        """Estabelecer conexão com MongoDB."""
        try:
            self.client = AsyncIOMotorClient(self.settings.mongodb_uri)
            self.db = self.client[self.settings.mongodb_database]
            self.optimization_collection = self.db[self.settings.mongodb_optimization_collection]
            self.experiments_collection = self.db[self.settings.mongodb_experiments_collection]

            # Criar índices
            await self._create_indexes()

            logger.info("mongodb_connected", database=self.settings.mongodb_database)
        except Exception as e:
            logger.error("mongodb_connection_failed", error=str(e))
            raise

    async def disconnect(self):
        """Fechar conexão com MongoDB."""
        if self.client:
            self.client.close()
            logger.info("mongodb_disconnected")

    async def _create_indexes(self):
        """Criar índices otimizados."""
        # Optimization collection indexes
        await self.optimization_collection.create_index([("optimization_id", ASCENDING)], unique=True)
        await self.optimization_collection.create_index([("target_component", ASCENDING)])
        await self.optimization_collection.create_index([("optimization_type", ASCENDING)])
        await self.optimization_collection.create_index([("applied_at", DESCENDING)])
        await self.optimization_collection.create_index(
            [("target_component", ASCENDING), ("applied_at", DESCENDING)]
        )
        await self.optimization_collection.create_index([("experiment_id", ASCENDING)])

        # Experiments collection indexes
        await self.experiments_collection.create_index([("experiment_id", ASCENDING)], unique=True)
        await self.experiments_collection.create_index([("target_component", ASCENDING)])
        await self.experiments_collection.create_index([("created_at", DESCENDING)])
        await self.experiments_collection.create_index([("status", ASCENDING)])

        # Insights collection indexes (para suportar find_recent_insights)
        insights_collection = self.db["insights"]
        await insights_collection.create_index([("created_at", DESCENDING)])
        await insights_collection.create_index([("priority", ASCENDING)])
        await insights_collection.create_index([("priority", ASCENDING), ("created_at", DESCENDING)])

        logger.info("mongodb_indexes_created")

    async def save_optimization(self, optimization_event: OptimizationEvent) -> bool:
        """Salvar evento de otimização no ledger."""
        try:
            doc = optimization_event.to_avro_dict()
            doc["_created_at"] = datetime.utcnow()

            await self.optimization_collection.insert_one(doc)

            logger.info(
                "optimization_saved",
                optimization_id=optimization_event.optimization_id,
                type=optimization_event.optimization_type.value,
                component=optimization_event.target_component,
            )
            return True
        except Exception as e:
            logger.error("optimization_save_failed", optimization_id=optimization_event.optimization_id, error=str(e))
            return False

    async def get_optimization(self, optimization_id: str) -> Optional[Dict]:
        """Recuperar otimização por ID."""
        try:
            doc = await self.optimization_collection.find_one({"optimization_id": optimization_id})
            if doc:
                doc.pop("_id", None)
                doc.pop("_created_at", None)
            return doc
        except Exception as e:
            logger.error("optimization_get_failed", optimization_id=optimization_id, error=str(e))
            return None

    async def list_optimizations(
        self, filters: Optional[Dict] = None, limit: int = 100, skip: int = 0
    ) -> List[Dict]:
        """Listar otimizações com filtros."""
        try:
            query = {}
            if filters:
                if "component" in filters:
                    query["target_component"] = filters["component"]
                if "optimization_type" in filters:
                    query["optimization_type"] = filters["optimization_type"]
                if "approval_status" in filters:
                    query["approval_status"] = filters["approval_status"]

            cursor = self.optimization_collection.find(query).sort("applied_at", DESCENDING).skip(skip).limit(limit)

            results = []
            async for doc in cursor:
                doc.pop("_id", None)
                doc.pop("_created_at", None)
                results.append(doc)

            logger.info("optimizations_listed", count=len(results), filters=filters)
            return results
        except Exception as e:
            logger.error("optimizations_list_failed", error=str(e))
            return []

    async def save_experiment(self, experiment_request: ExperimentRequest) -> bool:
        """Salvar requisição de experimento."""
        try:
            doc = experiment_request.to_avro_dict()
            doc["_created_at"] = datetime.utcnow()
            doc["status"] = "PENDING"
            doc["results"] = None

            await self.experiments_collection.insert_one(doc)

            logger.info(
                "experiment_saved",
                experiment_id=experiment_request.experiment_id,
                type=experiment_request.experiment_type.value,
            )
            return True
        except Exception as e:
            logger.error("experiment_save_failed", experiment_id=experiment_request.experiment_id, error=str(e))
            return False

    async def update_experiment_status(self, experiment_id: str, status: str, results: Optional[Dict] = None) -> bool:
        """Atualizar status de experimento."""
        try:
            update_doc = {"status": status, "_updated_at": datetime.utcnow()}

            if results:
                update_doc["results"] = results

            result = await self.experiments_collection.update_one(
                {"experiment_id": experiment_id}, {"$set": update_doc}
            )

            if result.modified_count > 0:
                logger.info("experiment_status_updated", experiment_id=experiment_id, status=status)
                return True
            return False
        except Exception as e:
            logger.error("experiment_update_failed", experiment_id=experiment_id, error=str(e))
            return False

    async def get_experiment(self, experiment_id: str) -> Optional[Dict]:
        """Recuperar experimento por ID."""
        try:
            doc = await self.experiments_collection.find_one({"experiment_id": experiment_id})
            if doc:
                doc.pop("_id", None)
            return doc
        except Exception as e:
            logger.error("experiment_get_failed", experiment_id=experiment_id, error=str(e))
            return None

    async def get_optimization_history(self, component: str, days: int = 30) -> List[Dict]:
        """Histórico de otimizações por componente."""
        try:
            cutoff_date = datetime.utcnow().timestamp() * 1000 - (days * 24 * 60 * 60 * 1000)

            cursor = (
                self.optimization_collection.find({"target_component": component, "applied_at": {"$gte": cutoff_date}})
                .sort("applied_at", DESCENDING)
                .limit(100)
            )

            results = []
            async for doc in cursor:
                doc.pop("_id", None)
                doc.pop("_created_at", None)
                results.append(doc)

            logger.info("optimization_history_retrieved", component=component, count=len(results))
            return results
        except Exception as e:
            logger.error("optimization_history_failed", component=component, error=str(e))
            return []

    async def get_success_rate(self, optimization_type: OptimizationType, days: int = 30) -> float:
        """Taxa de sucesso por tipo de otimização."""
        try:
            cutoff_date = datetime.utcnow().timestamp() * 1000 - (days * 24 * 60 * 60 * 1000)

            pipeline = [
                {"$match": {"optimization_type": optimization_type.value, "applied_at": {"$gte": cutoff_date}}},
                {
                    "$group": {
                        "_id": None,
                        "total": {"$sum": 1},
                        "successful": {
                            "$sum": {"$cond": [{"$gte": ["$improvement_percentage", 0]}, 1, 0]}
                        },
                    }
                },
            ]

            cursor = self.optimization_collection.aggregate(pipeline)
            result = await cursor.to_list(length=1)

            if result:
                total = result[0]["total"]
                successful = result[0]["successful"]
                success_rate = successful / total if total > 0 else 0.0
                logger.info("success_rate_calculated", type=optimization_type.value, rate=success_rate)
                return success_rate

            return 0.0
        except Exception as e:
            logger.error("success_rate_calculation_failed", type=optimization_type.value, error=str(e))
            return 0.0

    async def list_experiments(
        self, filters: Optional[Dict] = None, limit: int = 100, skip: int = 0
    ) -> List[Dict]:
        """Listar experimentos com filtros."""
        try:
            query = {}
            if filters:
                if "status" in filters:
                    query["status"] = filters["status"]
                if "target_component" in filters:
                    query["target_component"] = filters["target_component"]

            cursor = self.experiments_collection.find(query).sort("created_at", DESCENDING).skip(skip).limit(limit)

            results = []
            async for doc in cursor:
                doc.pop("_id", None)
                results.append(doc)

            logger.info("experiments_listed", count=len(results), filters=filters)
            return results
        except Exception as e:
            logger.error("experiments_list_failed", error=str(e))
            return []

    async def find_recent_insights(self, limit: int = 50, priority: Optional[List[str]] = None) -> List[Dict]:
        """
        Buscar insights recentes com filtros de prioridade.

        Args:
            limit: Número máximo de insights a retornar
            priority: Lista de prioridades para filtrar (ex: ["HIGH", "CRITICAL"])

        Returns:
            Lista de insights ordenados por freshness (mais recentes primeiro)
        """
        try:
            # Assumir que insights estão em uma collection separada
            insights_collection = self.db["insights"]

            query = {}
            if priority:
                query["priority"] = {"$in": priority}

            # Ordenar por timestamp de criação (campo 'created_at' ou 'timestamp')
            cursor = insights_collection.find(query).sort("created_at", DESCENDING).limit(limit)

            results = []
            async for doc in cursor:
                doc.pop("_id", None)
                results.append(doc)

            logger.info("recent_insights_retrieved", count=len(results), priority=priority)
            return results
        except Exception as e:
            logger.error("find_recent_insights_failed", error=str(e))
            return []

    async def count_recent_optimizations(self, hours: int = 24) -> int:
        """
        Contar otimizações aplicadas nas últimas N horas.

        Args:
            hours: Janela de tempo em horas

        Returns:
            Contagem de otimizações aplicadas
        """
        try:
            # Calcular timestamp de corte (milissegundos desde epoch)
            cutoff_timestamp = datetime.utcnow().timestamp() * 1000 - (hours * 60 * 60 * 1000)

            count = await self.optimization_collection.count_documents(
                {"applied_at": {"$gte": cutoff_timestamp}}
            )

            logger.info("recent_optimizations_counted", count=count, hours=hours)
            return count
        except Exception as e:
            logger.error("count_recent_optimizations_failed", hours=hours, error=str(e))
            return 0
