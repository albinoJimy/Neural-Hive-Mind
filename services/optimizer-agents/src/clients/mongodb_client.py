from datetime import datetime, timedelta, timezone

UTC = timezone.utc  # type: ignore, timedelta
from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from src.config.settings import get_settings
from src.models.experiment_request import ExperimentRequest
from src.models.optimization_event import OptimizationEvent, OptimizationType

logger = structlog.get_logger()


class MongoDBClient:
    """Cliente MongoDB para persistência de otimizações e experimentos."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.client: AsyncIOMotorClient | None = None
        self.db: AsyncIOMotorDatabase | None = None
        self.optimization_collection = None
        self.experiments_collection = None
        self.ab_test_results_collection = None

    async def connect(self):
        """Estabelecer conexão com MongoDB."""
        try:
            self.client = AsyncIOMotorClient(
                self.settings.mongodb_uri,
                maxPoolSize=self.settings.mongodb_max_pool_size,
                minPoolSize=self.settings.mongodb_min_pool_size,
            )
            self.db = self.client[self.settings.mongodb_database]
            self.optimization_collection = self.db[self.settings.mongodb_optimization_collection]
            self.experiments_collection = self.db[self.settings.mongodb_experiments_collection]
            self.ab_test_results_collection = self.db[
                self.settings.mongodb_ab_test_results_collection
            ]

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
        await self.optimization_collection.create_index(
            [("optimization_id", ASCENDING)], unique=True
        )
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
        await insights_collection.create_index(
            [("priority", ASCENDING), ("created_at", DESCENDING)]
        )

        # A/B Test Results collection indexes
        await self.ab_test_results_collection.create_index(
            [("experiment_id", ASCENDING)], unique=True
        )
        await self.ab_test_results_collection.create_index([("created_at", DESCENDING)])
        await self.ab_test_results_collection.create_index(
            [("status", ASCENDING), ("created_at", DESCENDING)]
        )
        await self.ab_test_results_collection.create_index(
            [("statistical_recommendation", ASCENDING)]
        )
        await self.ab_test_results_collection.create_index([("experiment_name", ASCENDING)])

        logger.info("mongodb_indexes_created")

    async def save_optimization(self, optimization_event: OptimizationEvent) -> bool:
        """Salvar evento de otimização no ledger."""
        try:
            doc = optimization_event.to_avro_dict()
            doc["_created_at"] = datetime.now(timezone.utc)

            await self.optimization_collection.insert_one(doc)

            logger.info(
                "optimization_saved",
                optimization_id=optimization_event.optimization_id,
                type=optimization_event.optimization_type.value,
                component=optimization_event.target_component,
            )
            return True
        except Exception as e:
            logger.error(
                "optimization_save_failed",
                optimization_id=optimization_event.optimization_id,
                error=str(e),
            )
            return False

    async def get_optimization(self, optimization_id: str) -> dict | None:
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
        self, filters: dict | None = None, limit: int = 100, skip: int = 0
    ) -> list[dict]:
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

            cursor = (
                self.optimization_collection.find(query)
                .sort("applied_at", DESCENDING)
                .skip(skip)
                .limit(limit)
            )

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
            doc["_created_at"] = datetime.now(timezone.utc)
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
            logger.error(
                "experiment_save_failed",
                experiment_id=experiment_request.experiment_id,
                error=str(e),
            )
            return False

    async def update_experiment_status(
        self, experiment_id: str, status: str, results: dict | None = None
    ) -> bool:
        """Atualizar status de experimento."""
        try:
            update_doc = {"status": status, "_updated_at": datetime.now(timezone.utc)}

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

    async def get_experiment(self, experiment_id: str) -> dict | None:
        """Recuperar experimento por ID."""
        try:
            doc = await self.experiments_collection.find_one({"experiment_id": experiment_id})
            if doc:
                doc.pop("_id", None)
            return doc
        except Exception as e:
            logger.error("experiment_get_failed", experiment_id=experiment_id, error=str(e))
            return None

    async def set_hypothesis_library_id(
        self, experiment_id: str, hypothesis_library_id: str
    ) -> bool:
        """Associar hypothesis_library_id ao experimento."""
        try:
            result = await self.experiments_collection.update_one(
                {"experiment_id": experiment_id},
                {
                    "$set": {
                        "hypothesis_library_id": hypothesis_library_id,
                        "_updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            if result.modified_count > 0:
                logger.info(
                    "hypothesis_library_id_set",
                    experiment_id=experiment_id,
                    hypothesis_library_id=hypothesis_library_id,
                )
                return True
            return False
        except Exception as e:
            logger.error(
                "set_hypothesis_library_id_failed",
                experiment_id=experiment_id,
                hypothesis_library_id=hypothesis_library_id,
                error=str(e),
            )
            return False

    async def get_optimization_history(self, component: str, days: int = 30) -> list[dict]:
        """Histórico de otimizações por componente."""
        try:
            cutoff_date = datetime.now(timezone.utc).timestamp() * 1000 - (
                days * 24 * 60 * 60 * 1000
            )

            cursor = (
                self.optimization_collection.find(
                    {"target_component": component, "applied_at": {"$gte": cutoff_date}}
                )
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
            cutoff_date = datetime.now(timezone.utc).timestamp() * 1000 - (
                days * 24 * 60 * 60 * 1000
            )

            pipeline = [
                {
                    "$match": {
                        "optimization_type": optimization_type.value,
                        "applied_at": {"$gte": cutoff_date},
                    }
                },
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
                logger.info(
                    "success_rate_calculated", type=optimization_type.value, rate=success_rate
                )
                return success_rate

            return 0.0
        except Exception as e:
            logger.error(
                "success_rate_calculation_failed", type=optimization_type.value, error=str(e)
            )
            return 0.0

    async def list_experiments(
        self, filters: dict | None = None, limit: int = 100, skip: int = 0
    ) -> list[dict]:
        """Listar experimentos com filtros."""
        try:
            query = {}
            if filters:
                if "status" in filters:
                    query["status"] = filters["status"]
                if "target_component" in filters:
                    query["target_component"] = filters["target_component"]

            cursor = (
                self.experiments_collection.find(query)
                .sort("created_at", DESCENDING)
                .skip(skip)
                .limit(limit)
            )

            results = []
            async for doc in cursor:
                doc.pop("_id", None)
                results.append(doc)

            logger.info("experiments_listed", count=len(results), filters=filters)
            return results
        except Exception as e:
            logger.error("experiments_list_failed", error=str(e))
            return []

    async def find_recent_insights(
        self, limit: int = 50, priority: list[str] | None = None
    ) -> list[dict]:
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
            cutoff_timestamp = datetime.now(timezone.utc).timestamp() * 1000 - (
                hours * 60 * 60 * 1000
            )

            count = await self.optimization_collection.count_documents(
                {"applied_at": {"$gte": cutoff_timestamp}}
            )

            logger.info("recent_optimizations_counted", count=count, hours=hours)
            return count
        except Exception as e:
            logger.error("count_recent_optimizations_failed", hours=hours, error=str(e))
            return 0

    # -------------------------------------------------------------------------
    # Métodos de A/B Testing Persistence
    # -------------------------------------------------------------------------

    async def save_ab_test_results(self, results: dict[str, Any]) -> str:
        """
        Salvar resultados de A/B testing no MongoDB.

        Args:
            results: Dicionário com dados completos do ABTestResults:
                - experiment_id: ID do experimento
                - experiment_name: Nome do experimento
                - status: Status do experimento
                - control_size: Tamanho do grupo controle
                - treatment_size: Tamanho do grupo tratamento
                - primary_metrics_analysis: Lista de análises de métricas primárias
                - secondary_metrics_analysis: Lista de análises de métricas secundárias
                - bayesian_analysis: Lista de análises bayesianas (opcional)
                - guardrails_status: Status dos guardrails
                - statistical_recommendation: Recomendação estatística
                - confidence_level: Nível de confiança
                - early_stopped: Se parou antecipadamente
                - early_stop_reason: Razão da parada antecipada
                - analysis_timestamp: Timestamp da análise

        Returns:
            str: ID do documento inserido no MongoDB

        Raises:
            ValueError: Se experiment_id ou experiment_name não fornecidos
        """
        try:
            experiment_id = results.get("experiment_id")
            if not experiment_id:
                raise ValueError("experiment_id é obrigatório")

            experiment_name = results.get("experiment_name", "Unnamed Experiment")

            # Preparar documento com timestamps
            now = datetime.now(timezone.utc)
            doc = {
                "experiment_id": experiment_id,
                "experiment_name": experiment_name,
                "created_at": now,
                "completed_at": now,
                "analysis_timestamp": results.get("analysis_timestamp", now),
                "status": results.get("status", "running"),
                "control_size": results.get("control_size", 0),
                "treatment_size": results.get("treatment_size", 0),
                "primary_metrics_analysis": results.get("primary_metrics_analysis", []),
                "secondary_metrics_analysis": results.get("secondary_metrics_analysis", []),
                "bayesian_analysis": results.get("bayesian_analysis"),
                "guardrails_status": results.get("guardrails_status", {}),
                "statistical_recommendation": results.get(
                    "statistical_recommendation", "INCONCLUSIVE"
                ),
                "confidence_level": results.get("confidence_level", 0.0),
                "early_stopped": results.get("early_stopped", False),
                "early_stop_reason": results.get("early_stop_reason"),
                "metadata": results.get("metadata", {}),
            }

            # Upsert: atualizar se já existe, inserir se não
            result = await self.ab_test_results_collection.update_one(
                {"experiment_id": experiment_id}, {"$set": doc}, upsert=True
            )

            if result.upserted_id:
                doc_id = str(result.upserted_id)
            else:
                # Se atualizou, retornar o ID existente
                existing = await self.ab_test_results_collection.find_one(
                    {"experiment_id": experiment_id}
                )
                doc_id = str(existing["_id"])

            logger.info(
                "ab_test_results_saved",
                experiment_id=experiment_id,
                doc_id=doc_id,
                recommendation=doc["statistical_recommendation"],
                confidence=doc["confidence_level"],
            )
            return doc_id

        except Exception as e:
            logger.error(
                "save_ab_test_results_failed",
                experiment_id=results.get("experiment_id"),
                error=str(e),
            )
            raise

    async def get_ab_test_results(self, experiment_id: str) -> dict | None:
        """
        Recuperar resultados de A/B testing por experiment_id.

        Args:
            experiment_id: ID do experimento

        Returns:
            Dicionário com resultados completos ou None se não encontrado
        """
        try:
            doc = await self.ab_test_results_collection.find_one({"experiment_id": experiment_id})
            if doc:
                # Remover _id do retorno (não é serializável diretamente)
                doc.pop("_id", None)
                logger.debug("ab_test_results_retrieved", experiment_id=experiment_id)
            else:
                logger.debug("ab_test_results_not_found", experiment_id=experiment_id)
            return doc
        except Exception as e:
            logger.error("get_ab_test_results_failed", experiment_id=experiment_id, error=str(e))
            return None

    async def list_ab_test_results(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        skip: int = 0,
    ) -> list[dict]:
        """
        Listar resultados de A/B testing com filtros opcionais.

        Args:
            filters: Filtros opcionais:
                - status: "running", "completed", "aborted"
                - statistical_recommendation: "APPLY", "REJECT", "INCONCLUSIVE"
                - experiment_name: Nome parcial do experimento (case-insensitive)
            limit: Limite de resultados (default: 100)
            skip: Numero de resultados para pular (paginação)

        Returns:
            Lista de dicionários com resumo dos resultados
        """
        try:
            query = {}

            if filters:
                if "status" in filters:
                    query["status"] = filters["status"]
                if "statistical_recommendation" in filters:
                    query["statistical_recommendation"] = filters["statistical_recommendation"]
                if "experiment_name" in filters:
                    # Busca case-insensitive por nome parcial
                    query["experiment_name"] = {
                        "$regex": filters["experiment_name"],
                        "$options": "i",
                    }

            cursor = (
                self.ab_test_results_collection.find(query)
                .sort("created_at", DESCENDING)
                .skip(skip)
                .limit(limit)
            )

            results = []
            async for doc in cursor:
                doc.pop("_id", None)
                results.append(doc)

            logger.info("ab_test_results_listed", count=len(results), filters=filters)
            return results

        except Exception as e:
            logger.error("list_ab_test_results_failed", filters=filters, error=str(e))
            return []

    async def get_ab_test_history(
        self,
        experiment_id: str,
        days: int = 30,
    ) -> list[dict]:
        """
        Recuperar histórico de snapshots de um experimento.

        Nota: Como a coleção usa upsert (atualização), este método retorna
        o estado atual do experimento. Para histórico temporal completo,
        seria necessário uma coleção separada de snapshots.

        Args:
            experiment_id: ID do experimento
            days: Numero de dias para buscar (default: 30)

        Returns:
            Lista com snapshot atual do experimento (ou vazia se não encontrado)
        """
        try:
            since = datetime.now(timezone.utc) - timedelta(days=days)

            doc = await self.ab_test_results_collection.find_one(
                {"experiment_id": experiment_id, "created_at": {"$gte": since}}
            )

            if doc:
                doc.pop("_id", None)
                logger.debug("ab_test_history_retrieved", experiment_id=experiment_id, days=days)
                return [doc]
            else:
                logger.debug("ab_test_history_not_found", experiment_id=experiment_id)
                return []

        except Exception as e:
            logger.error("get_ab_test_history_failed", experiment_id=experiment_id, error=str(e))
            return []

    async def get_ab_test_aggregations(
        self,
        metric_name: str | None = None,
        days: int = 30,
    ) -> dict[str, Any]:
        """
        Calcular agregações estatísticas de resultados de A/B testing.

        Args:
            metric_name: Nome da métrica para filtrar (opcional)
            days: Numero de dias para agregação (default: 30)

        Returns:
            Dicionário com agregações:
                - total_experiments: Total de experimentos no período
                - completed_experiments: Experimentos concluídos
                - recommendations_count: Contagem por recomendação
                - avg_confidence: Confiança média
                - win_rate: Proporção de recomendações "APPLY"
                - avg_lift: Lift médio (se metric_name fornecido)
                - metric_breakdown: Breakdown por métrica (se metric_name fornecido)
        """
        try:
            since = datetime.now(timezone.utc) - timedelta(days=days)

            # Pipeline de agregação base
            pipeline = [
                {"$match": {"created_at": {"$gte": since}}},
                {
                    "$group": {
                        "_id": None,
                        "total_experiments": {"$sum": 1},
                        "completed_experiments": {
                            "$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}
                        },
                        "apply_count": {
                            "$sum": {
                                "$cond": [{"$eq": ["$statistical_recommendation", "APPLY"]}, 1, 0]
                            }
                        },
                        "reject_count": {
                            "$sum": {
                                "$cond": [{"$eq": ["$statistical_recommendation", "REJECT"]}, 1, 0]
                            }
                        },
                        "inconclusive_count": {
                            "$sum": {
                                "$cond": [
                                    {"$eq": ["$statistical_recommendation", "INCONCLUSIVE"]},
                                    1,
                                    0,
                                ]
                            }
                        },
                        "total_confidence": {"$sum": "$confidence_level"},
                        "total_sample_size": {
                            "$sum": {"$add": ["$control_size", "$treatment_size"]}
                        },
                    }
                },
            ]

            cursor = self.ab_test_results_collection.aggregate(pipeline)
            result = await cursor.to_list(length=1)

            if not result:
                return {
                    "period": {
                        "days": days,
                        "from": since.isoformat(),
                        "to": datetime.now(timezone.utc).isoformat(),
                    },
                    "total_experiments": 0,
                    "completed_experiments": 0,
                    "recommendations_count": {"APPLY": 0, "REJECT": 0, "INCONCLUSIVE": 0},
                    "avg_confidence": 0.0,
                    "win_rate": 0.0,
                    "avg_sample_size": 0,
                }

            agg = result[0]
            total = agg["total_experiments"]

            # Calcular win rate
            win_rate = agg["apply_count"] / total if total > 0 else 0.0
            avg_confidence = agg["total_confidence"] / total if total > 0 else 0.0
            avg_sample_size = agg["total_sample_size"] / total if total > 0 else 0

            response = {
                "period": {
                    "days": days,
                    "from": since.isoformat(),
                    "to": datetime.now(timezone.utc).isoformat(),
                },
                "total_experiments": total,
                "completed_experiments": agg["completed_experiments"],
                "recommendations_count": {
                    "APPLY": agg["apply_count"],
                    "REJECT": agg["reject_count"],
                    "INCONCLUSIVE": agg["inconclusive_count"],
                },
                "avg_confidence": round(avg_confidence, 4),
                "win_rate": round(win_rate, 4),
                "avg_sample_size": int(avg_sample_size),
            }

            # Se metric_name fornecido, calcular agregações específicas da métrica
            if metric_name:
                response["metric_name"] = metric_name

                # Buscar experimentos que analisaram esta métrica
                metric_pipeline = [
                    {
                        "$match": {
                            "created_at": {"$gte": since},
                            "primary_metrics_analysis.metric_name": metric_name,
                        }
                    },
                    {"$unwind": "$primary_metrics_analysis"},
                    {"$match": {"primary_metrics_analysis.metric_name": metric_name}},
                    {
                        "$group": {
                            "_id": None,
                            "avg_effect_size": {"$avg": "$primary_metrics_analysis.effect_size"},
                            "avg_p_value": {"$avg": "$primary_metrics_analysis.p_value"},
                            "significant_count": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$eq": [
                                                "$primary_metrics_analysis.statistically_significant",
                                                True,
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "experiments_with_metric": {"$sum": 1},
                        }
                    },
                ]

                metric_cursor = self.ab_test_results_collection.aggregate(metric_pipeline)
                metric_result = await metric_cursor.to_list(length=1)

                if metric_result:
                    mr = metric_result[0]
                    response["metric_breakdown"] = {
                        "metric_name": metric_name,
                        "avg_effect_size": (
                            round(mr["avg_effect_size"], 4) if mr["avg_effect_size"] else 0.0
                        ),
                        "avg_p_value": round(mr["avg_p_value"], 4) if mr["avg_p_value"] else 0.0,
                        "significant_rate": (
                            round(mr["significant_count"] / mr["experiments_with_metric"], 4)
                            if mr["experiments_with_metric"] > 0
                            else 0.0
                        ),
                        "experiments": mr["experiments_with_metric"],
                    }

            logger.info("ab_test_aggregations_calculated", days=days, metric_name=metric_name)
            return response

        except Exception as e:
            logger.error("get_ab_test_aggregations_failed", metric_name=metric_name, error=str(e))
            return {
                "period": {"days": days},
                "error": str(e),
            }

    async def get_ab_test_dashboard(
        self,
        days: int = 30,
    ) -> dict[str, Any]:
        """
        Retornar dados agregados para dashboard de A/B testing.

        Args:
            days: Numero de dias para o dashboard (default: 30)

        Returns:
            Dicionário com dados completos do dashboard
        """
        try:
            # Obter agregações gerais
            aggregations = await self.get_ab_test_aggregations(days=days)

            # Top experimentos (maior efeito positivo)
            top_pipeline = [
                {
                    "$match": {
                        "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(days=days)}
                    }
                },
                {"$unwind": "$primary_metrics_analysis"},
                {
                    "$match": {
                        "primary_metrics_analysis.statistically_significant": True,
                        "primary_metrics_analysis.effect_size": {"$gt": 0},
                    }
                },
                {
                    "$project": {
                        "experiment_id": 1,
                        "experiment_name": 1,
                        "metric_name": "$primary_metrics_analysis.metric_name",
                        "effect_size": "$primary_metrics_analysis.effect_size",
                        "p_value": "$primary_metrics_analysis.p_value",
                        "recommendation": 1,
                        "created_at": 1,
                    }
                },
                {"$sort": {"effect_size": DESCENDING}},
                {"$limit": 10},
            ]

            top_cursor = self.ab_test_results_collection.aggregate(top_pipeline)
            top_experiments = await top_cursor.to_list(length=10)

            # Remover _id dos resultados
            for exp in top_experiments:
                exp.pop("_id", None)

            # Breakdown por métrica (todas as métricas primárias)
            metrics_pipeline = [
                {
                    "$match": {
                        "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(days=days)}
                    }
                },
                {"$unwind": "$primary_metrics_analysis"},
                {
                    "$group": {
                        "_id": "$primary_metrics_analysis.metric_name",
                        "experiments": {"$sum": 1},
                        "avg_effect_size": {"$avg": "$primary_metrics_analysis.effect_size"},
                        "avg_p_value": {"$avg": "$primary_metrics_analysis.p_value"},
                        "significant_count": {
                            "$sum": {
                                "$cond": [
                                    {
                                        "$eq": [
                                            "$primary_metrics_analysis.statistically_significant",
                                            True,
                                        ]
                                    },
                                    1,
                                    0,
                                ]
                            }
                        },
                    }
                },
                {"$sort": {"avg_effect_size": DESCENDING}},
            ]

            metrics_cursor = self.ab_test_results_collection.aggregate(metrics_pipeline)
            metrics_breakdown = await metrics_cursor.to_list(length=50)

            metric_breakdown_dict = {}
            for mb in metrics_breakdown:
                metric_breakdown_dict[mb["_id"]] = {
                    "avg_effect_size": (
                        round(mb["avg_effect_size"], 4) if mb["avg_effect_size"] else 0.0
                    ),
                    "avg_p_value": round(mb["avg_p_value"], 4) if mb["avg_p_value"] else 0.0,
                    "experiments": mb["experiments"],
                    "significant_rate": (
                        round(mb["significant_count"] / mb["experiments"], 4)
                        if mb["experiments"] > 0
                        else 0.0
                    ),
                }

            dashboard = {
                **aggregations,
                "top_experiments": top_experiments,
                "metric_breakdown": metric_breakdown_dict,
            }

            logger.info("ab_test_dashboard_generated", days=days)
            return dashboard

        except Exception as e:
            logger.error("get_ab_test_dashboard_failed", days=days, error=str(e))
            return {
                "period": {"days": days},
                "error": str(e),
            }
