"""
MongoDB Client para Explainability API.

Fornece interface async para MongoDB para coleta de decisões
históricas de consenso para treinamento do modelo SHAP.

EPIC-204-01: Modelo ML para SHAP
"""

from typing import Any, Dict, List, Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorClient

logger = structlog.get_logger(__name__)


class MongoDBClient:
    """Cliente async MongoDB para coleta de decisões históricas."""

    def __init__(
        self,
        uri: str = "mongodb://localhost:27017",
        database: str = "neural_hive_mind",
        consensus_collection: str = "consensus_decisions",
    ):
        """
        Inicializa cliente MongoDB.

        Args:
            uri: URI de conexão MongoDB
            database: Nome do banco de dados
            consensus_collection: Coleção de decisões de consenso
        """
        self.uri = uri
        self.database_name = database
        self.consensus_collection_name = consensus_collection

        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.consensus_collection = None

    async def connect(self):
        """Estabelece conexão com MongoDB."""
        self.client = AsyncIOMotorClient(
            self.uri,
            maxPoolSize=50,
            serverSelectionTimeoutMS=30000,
            connectTimeoutMS=30000,
            socketTimeoutMS=30000,
            retryWrites=True,
            w="majority",
        )

        self.db = self.client[self.database_name]
        self.consensus_collection = self.db[self.consensus_collection_name]

        # Verificar conectividade
        await self.client.admin.command("ping")

        logger.info(
            "mongodb_connected",
            uri=self.uri,
            database=self.database_name,
            collection=self.consensus_collection_name,
        )

    async def get_recent_decisions(self, limit: int = 1000, skip: int = 0) -> List[Dict[str, Any]]:
        """
        Coleta decisões recentes do MongoDB.

        Args:
            limit: Número máximo de decisões a retornar
            skip: Numero de documentos a pular (paginação)

        Returns:
            Lista de decisões (dicionários)
        """
        if not self.consensus_collection:
            await self.connect()

        cursor = self.consensus_collection.find().sort("created_at", -1).skip(skip).limit(limit)

        decisions = []
        async for doc in cursor:
            # Remover campos internos do MongoDB
            doc.pop("_id", None)
            doc.pop("immutable", None)
            decisions.append(doc)

        logger.info("recent_decisions_collected", count=len(decisions), limit=limit, skip=skip)

        return decisions

    async def get_decision_by_id(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """
        Busca decisão por ID.

        Args:
            decision_id: ID da decisão

        Returns:
            Decisão ou None
        """
        if not self.consensus_collection:
            await self.connect()

        doc = await self.consensus_collection.find_one({"decision_id": decision_id})

        if doc:
            doc.pop("_id", None)
            doc.pop("immutable", None)

        return doc

    async def get_decisions_by_date_range(
        self, start_date, end_date, limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Busca decisões por intervalo de datas.

        Args:
            start_date: Data inicial
            end_date: Data final
            limit: Limite de resultados

        Returns:
            Lista de decisões
        """
        if not self.consensus_collection:
            await self.connect()

        cursor = (
            self.consensus_collection.find({"created_at": {"$gte": start_date, "$lte": end_date}})
            .sort("created_at", -1)
            .limit(limit)
        )

        decisions = []
        async for doc in cursor:
            doc.pop("_id", None)
            doc.pop("immutable", None)
            decisions.append(doc)

        logger.info(
            "decisions_by_date_range",
            count=len(decisions),
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )

        return decisions

    async def count_decisions(self) -> int:
        """
        Conta total de decisões disponíveis.

        Returns:
            Número de decisões
        """
        if not self.consensus_collection:
            await self.connect()

        count = await self.consensus_collection.count_documents({})
        logger.info("decisions_counted", total=count)

        return count

    async def get_decision_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas das decisões disponíveis.

        Returns:
            Dicionário com estatísticas
        """
        if not self.consensus_collection:
            await self.connect()

        pipeline = [
            {
                "$facet": {
                    "decision_counts": [
                        {"$group": {"_id": "$final_decision", "count": {"$sum": 1}}}
                    ],
                    "consensus_method_counts": [
                        {"$group": {"_id": "$consensus_method", "count": {"$sum": 1}}}
                    ],
                    "date_range": [
                        {
                            "$group": {
                                "_id": None,
                                "oldest": {"$min": "$created_at"},
                                "newest": {"$max": "$created_at"},
                            }
                        }
                    ],
                    "confidence_ranges": [
                        {
                            "$group": {
                                "_id": None,
                                "avg_confidence": {"$avg": "$aggregated_confidence"},
                                "avg_risk": {"$avg": "$aggregated_risk"},
                            }
                        }
                    ],
                }
            }
        ]

        result = await self.consensus_collection.aggregate(pipeline).to_list(length=1)

        if not result:
            return {
                "total_decisions": 0,
                "decision_distribution": {},
                "consensus_method_distribution": {},
                "date_range": None,
                "averages": {"confidence": 0, "risk": 0},
            }

        data = result[0]

        # Processar contagens de decisão
        decision_dist = {item["_id"]: item["count"] for item in data.get("decision_counts", [])}

        # Processar contagens de método
        method_dist = {
            item["_id"]: item["count"] for item in data.get("consensus_method_counts", [])
        }

        # Processar intervalo de datas
        date_range = None
        if data.get("date_range") and data["date_range"]:
            dr = data["date_range"][0]
            if dr.get("oldest") and dr.get("newest"):
                date_range = {
                    "oldest": dr["oldest"].isoformat(),
                    "newest": dr["newest"].isoformat(),
                }

        # Processar médias
        averages = None
        if data.get("confidence_ranges") and data["confidence_ranges"]:
            avg = data["confidence_ranges"][0]
            averages = {"confidence": avg.get("avg_confidence", 0), "risk": avg.get("avg_risk", 0)}

        return {
            "total_decisions": await self.count_decisions(),
            "decision_distribution": decision_dist,
            "consensus_method_distribution": method_dist,
            "date_range": date_range,
            "averages": averages,
        }

    async def close(self):
        """Fecha conexão com MongoDB."""
        if self.client:
            self.client.close()
            logger.info("mongodb_closed")

    async def __aenter__(self):
        """Context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()
