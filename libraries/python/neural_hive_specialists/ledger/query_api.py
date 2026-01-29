"""
LedgerQueryAPI: APIs semânticas para consultas no ledger cognitivo.

Fornece métodos de alto nível para evitar queries manuais direto no MongoDB,
com suporte a filtros semânticos, agregações e cache.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pymongo import MongoClient, DESCENDING, ASCENDING
from pymongo.errors import PyMongoError
import structlog
from functools import lru_cache
import hashlib
import json

logger = structlog.get_logger(__name__)


class LedgerQueryAPI:
    """API de alto nível para consultas semânticas no ledger."""

    def __init__(self, config: Dict[str, Any]):
        """
        Inicializa query API.

        Args:
            config: Configuração com mongodb_uri, mongodb_database, mongodb_opinions_collection
        """
        self.config = config
        self.mongodb_uri = config.get("mongodb_uri")
        self.mongodb_database = config.get("mongodb_database", "neural_hive")
        self.mongodb_opinions_collection = config.get(
            "mongodb_opinions_collection", "specialist_opinions"
        )
        self._mongo_client: Optional[MongoClient] = None

        # Cache TTL em segundos (padrão: 5 minutos)
        self.cache_ttl = config.get("query_cache_ttl_seconds", 300)

        logger.info(
            "LedgerQueryAPI initialized",
            database=self.mongodb_database,
            collection=self.mongodb_opinions_collection,
            cache_ttl=self.cache_ttl,
        )

    @property
    def mongo_client(self) -> MongoClient:
        """Lazy initialization do cliente MongoDB."""
        if self._mongo_client is None:
            self._mongo_client = MongoClient(
                self.mongodb_uri, serverSelectionTimeoutMS=5000
            )
        return self._mongo_client

    @property
    def collection(self):
        """Retorna collection de opiniões."""
        db = self.mongo_client[self.mongodb_database]
        return db[self.mongodb_opinions_collection]

    def get_opinions_by_specialist(
        self, specialist_type: str, limit: int = 100, skip: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Busca opiniões por tipo de especialista.

        Args:
            specialist_type: Tipo do especialista (technical, business, etc.)
            limit: Número máximo de resultados
            skip: Número de documentos a pular (paginação)

        Returns:
            Lista de documentos de opinião
        """
        try:
            cursor = (
                self.collection.find({"specialist_type": specialist_type})
                .sort("evaluated_at", DESCENDING)
                .limit(limit)
                .skip(skip)
            )

            opinions = list(cursor)

            # Remover _id do MongoDB
            for opinion in opinions:
                opinion.pop("_id", None)

            logger.debug(
                "Opinions retrieved by specialist",
                specialist_type=specialist_type,
                count=len(opinions),
            )

            return opinions

        except PyMongoError as e:
            logger.error(
                "Failed to query opinions by specialist",
                specialist_type=specialist_type,
                error=str(e),
            )
            return []

    def get_opinions_by_plan(self, plan_id: str) -> List[Dict[str, Any]]:
        """
        Busca todas as opiniões relacionadas a um plano cognitivo.

        Args:
            plan_id: ID do plano cognitivo

        Returns:
            Lista de opiniões de todos os especialistas
        """
        try:
            cursor = self.collection.find({"plan_id": plan_id}).sort(
                "evaluated_at", ASCENDING
            )

            opinions = list(cursor)

            for opinion in opinions:
                opinion.pop("_id", None)

            logger.debug(
                "Opinions retrieved by plan", plan_id=plan_id, count=len(opinions)
            )

            return opinions

        except PyMongoError as e:
            logger.error(
                "Failed to query opinions by plan", plan_id=plan_id, error=str(e)
            )
            return []

    def get_opinions_by_recommendation(
        self, recommendation: str, time_range_hours: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Busca opiniões por tipo de recomendação.

        Args:
            recommendation: Recomendação (approve, reject, review_required, conditional)
            time_range_hours: Janela de tempo em horas (opcional)

        Returns:
            Lista de opiniões
        """
        try:
            query: Dict[str, Any] = {"opinion.recommendation": recommendation}

            # Filtro temporal se especificado
            if time_range_hours:
                cutoff_time = datetime.utcnow() - timedelta(hours=time_range_hours)
                query["evaluated_at"] = {"$gte": cutoff_time}

            cursor = self.collection.find(query).sort("evaluated_at", DESCENDING)

            opinions = list(cursor)

            for opinion in opinions:
                opinion.pop("_id", None)

            logger.debug(
                "Opinions retrieved by recommendation",
                recommendation=recommendation,
                time_range_hours=time_range_hours,
                count=len(opinions),
            )

            return opinions

        except PyMongoError as e:
            logger.error(
                "Failed to query opinions by recommendation",
                recommendation=recommendation,
                error=str(e),
            )
            return []

    def get_high_risk_opinions(
        self, risk_threshold: float = 0.7, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Busca opiniões com alto risco.

        Args:
            risk_threshold: Threshold mínimo de risco (0.0-1.0)
            limit: Número máximo de resultados

        Returns:
            Lista de opiniões de alto risco
        """
        try:
            cursor = (
                self.collection.find({"opinion.risk_score": {"$gte": risk_threshold}})
                .sort("opinion.risk_score", DESCENDING)
                .limit(limit)
            )

            opinions = list(cursor)

            for opinion in opinions:
                opinion.pop("_id", None)

            logger.info(
                "High-risk opinions retrieved",
                risk_threshold=risk_threshold,
                count=len(opinions),
            )

            return opinions

        except PyMongoError as e:
            logger.error("Failed to query high-risk opinions", error=str(e))
            return []

    def get_opinions_by_correlation_id(
        self, correlation_id: str
    ) -> List[Dict[str, Any]]:
        """
        Busca todas as opiniões de uma transação (correlation_id).

        Args:
            correlation_id: ID de correlação da transação

        Returns:
            Lista de opiniões da mesma transação
        """
        try:
            cursor = self.collection.find({"correlation_id": correlation_id}).sort(
                "evaluated_at", ASCENDING
            )

            opinions = list(cursor)

            for opinion in opinions:
                opinion.pop("_id", None)

            logger.debug(
                "Opinions retrieved by correlation",
                correlation_id=correlation_id,
                count=len(opinions),
            )

            return opinions

        except PyMongoError as e:
            logger.error(
                "Failed to query opinions by correlation",
                correlation_id=correlation_id,
                error=str(e),
            )
            return []

    def aggregate_consensus_metrics(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """
        Calcula métricas de consenso para um plano.

        Args:
            plan_id: ID do plano cognitivo

        Returns:
            Métricas agregadas de consenso
        """
        try:
            pipeline = [
                {"$match": {"plan_id": plan_id}},
                {
                    "$group": {
                        "_id": "$plan_id",
                        "avg_confidence": {"$avg": "$opinion.confidence_score"},
                        "avg_risk": {"$avg": "$opinion.risk_score"},
                        "total_specialists": {"$sum": 1},
                        "recommendations": {"$push": "$opinion.recommendation"},
                    }
                },
            ]

            result = list(self.collection.aggregate(pipeline))

            if not result:
                return None

            consensus = result[0]

            # Contar recomendações
            recommendations = consensus.get("recommendations", [])
            consensus["recommendation_counts"] = {
                "approve": recommendations.count("approve"),
                "reject": recommendations.count("reject"),
                "review_required": recommendations.count("review_required"),
                "conditional": recommendations.count("conditional"),
            }

            # Determinar consenso majoritário
            max_count = max(consensus["recommendation_counts"].values())
            consensus["majority_recommendation"] = [
                rec
                for rec, count in consensus["recommendation_counts"].items()
                if count == max_count
            ][0]

            # Calcular grau de consenso (0.0-1.0)
            consensus["consensus_degree"] = (
                max_count / len(recommendations) if recommendations else 0.0
            )

            consensus.pop("_id", None)
            consensus.pop("recommendations", None)

            logger.info(
                "Consensus metrics calculated",
                plan_id=plan_id,
                consensus_degree=consensus["consensus_degree"],
            )

            return consensus

        except PyMongoError as e:
            logger.error("Failed to aggregate consensus", plan_id=plan_id, error=str(e))
            return None

    def get_specialist_performance_stats(
        self, specialist_type: str, time_range_hours: int = 168  # 7 dias padrão
    ) -> Optional[Dict[str, Any]]:
        """
        Calcula estatísticas de performance de um especialista.

        Args:
            specialist_type: Tipo do especialista
            time_range_hours: Janela de tempo em horas

        Returns:
            Estatísticas de performance
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=time_range_hours)

            pipeline = [
                {
                    "$match": {
                        "specialist_type": specialist_type,
                        "evaluated_at": {"$gte": cutoff_time},
                    }
                },
                {
                    "$group": {
                        "_id": "$specialist_type",
                        "total_evaluations": {"$sum": 1},
                        "avg_confidence": {"$avg": "$opinion.confidence_score"},
                        "avg_risk": {"$avg": "$opinion.risk_score"},
                        "avg_processing_time_ms": {"$avg": "$processing_time_ms"},
                        "buffered_count": {"$sum": {"$cond": ["$buffered", 1, 0]}},
                    }
                },
            ]

            result = list(self.collection.aggregate(pipeline))

            if not result:
                return None

            stats = result[0]
            stats["specialist_type"] = specialist_type
            stats["time_range_hours"] = time_range_hours
            stats["buffered_percentage"] = (
                stats["buffered_count"] / stats["total_evaluations"] * 100
                if stats["total_evaluations"] > 0
                else 0.0
            )

            stats.pop("_id", None)

            logger.info(
                "Specialist performance stats calculated",
                specialist_type=specialist_type,
                total_evaluations=stats["total_evaluations"],
            )

            return stats

        except PyMongoError as e:
            logger.error(
                "Failed to calculate specialist stats",
                specialist_type=specialist_type,
                error=str(e),
            )
            return None

    def search_opinions_by_reasoning(
        self, search_term: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Busca opiniões por termo no raciocínio.

        Args:
            search_term: Termo a buscar no reasoning_summary
            limit: Número máximo de resultados

        Returns:
            Lista de opiniões correspondentes
        """
        try:
            # Text search requer index text no MongoDB
            cursor = (
                self.collection.find(
                    {
                        "opinion.reasoning_summary": {
                            "$regex": search_term,
                            "$options": "i",
                        }
                    }
                )
                .sort("evaluated_at", DESCENDING)
                .limit(limit)
            )

            opinions = list(cursor)

            for opinion in opinions:
                opinion.pop("_id", None)

            logger.debug(
                "Opinions searched by reasoning",
                search_term=search_term,
                count=len(opinions),
            )

            return opinions

        except PyMongoError as e:
            logger.error(
                "Failed to search opinions by reasoning",
                search_term=search_term,
                error=str(e),
            )
            return []

    def verify_document_integrity(self, opinion_id: str) -> Optional[bool]:
        """
        Verifica integridade de um documento por opinion_id.

        Args:
            opinion_id: ID da opinião

        Returns:
            True se íntegro, False se adulterado, None se não encontrado
        """
        try:
            document = self.collection.find_one({"opinion_id": opinion_id})

            if not document:
                logger.warning(
                    "Opinion not found for integrity check", opinion_id=opinion_id
                )
                return None

            # Verificar hash de conteúdo
            from .digital_signer import DigitalSigner

            signer = DigitalSigner(self.config)
            is_tampered = signer.detect_tampering(document)

            logger.info(
                "Document integrity checked",
                opinion_id=opinion_id,
                tampered=is_tampered,
            )

            return not is_tampered

        except Exception as e:
            logger.error(
                "Failed to verify document integrity",
                opinion_id=opinion_id,
                error=str(e),
            )
            return None

    def get_opinions_by_domain(
        self, domain: str, limit: int = 100, skip: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Busca opiniões por domínio original do plano cognitivo.

        Args:
            domain: Domínio original (ex: 'data_processing', 'api_integration')
            limit: Número máximo de resultados
            skip: Número de documentos a pular (paginação)

        Returns:
            Lista de opiniões do domínio especificado
        """
        try:
            cursor = (
                self.collection.find({"opinion.metadata.domain": domain})
                .sort("evaluated_at", DESCENDING)
                .limit(limit)
                .skip(skip)
            )

            opinions = list(cursor)
            for opinion in opinions:
                opinion.pop("_id", None)

            logger.debug(
                "Opinions retrieved by domain", domain=domain, count=len(opinions)
            )

            return opinions

        except PyMongoError as e:
            logger.error(
                "Failed to query opinions by domain", domain=domain, error=str(e)
            )
            return []

    def get_opinions_by_feature(
        self, feature_name: str, min_score: Optional[float] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Busca opiniões por fator de raciocínio (reasoning_factor).

        Args:
            feature_name: Nome do fator (ex: 'security_analysis', 'architecture_patterns')
            min_score: Score mínimo do fator (opcional)
            limit: Número máximo de resultados

        Returns:
            Lista de opiniões que contêm o fator especificado
        """
        try:
            query: Dict[str, Any] = {
                "opinion.reasoning_factors": {
                    "$elemMatch": {"factor_name": feature_name}
                }
            }

            # Filtro de score mínimo se especificado
            if min_score is not None:
                query["opinion.reasoning_factors"]["$elemMatch"]["score"] = {
                    "$gte": min_score
                }

            cursor = (
                self.collection.find(query)
                .sort("evaluated_at", DESCENDING)
                .limit(limit)
            )

            opinions = list(cursor)
            for opinion in opinions:
                opinion.pop("_id", None)

            logger.debug(
                "Opinions retrieved by feature",
                feature_name=feature_name,
                min_score=min_score,
                count=len(opinions),
            )

            return opinions

        except PyMongoError as e:
            logger.error(
                "Failed to query opinions by feature",
                feature_name=feature_name,
                error=str(e),
            )
            return []

    def get_opinions_by_metadata_field(
        self, field_path: str, field_value: Any, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Busca opiniões por campo customizado no metadata.

        Args:
            field_path: Caminho do campo (ex: 'metadata.priority', 'metadata.num_tasks')
            field_value: Valor a buscar
            limit: Número máximo de resultados

        Returns:
            Lista de opiniões correspondentes
        """
        try:
            # Construir query dinâmica
            query = {f"opinion.{field_path}": field_value}

            cursor = (
                self.collection.find(query)
                .sort("evaluated_at", DESCENDING)
                .limit(limit)
            )

            opinions = list(cursor)
            for opinion in opinions:
                opinion.pop("_id", None)

            logger.debug(
                "Opinions retrieved by metadata field",
                field_path=field_path,
                field_value=field_value,
                count=len(opinions),
            )

            return opinions

        except PyMongoError as e:
            logger.error(
                "Failed to query opinions by metadata field",
                field_path=field_path,
                error=str(e),
            )
            return []

    def get_opinions_with_mitigations(
        self,
        mitigation_type: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Busca opiniões que contêm mitigações recomendadas.

        Args:
            mitigation_type: Tipo de mitigação (opcional)
            priority: Prioridade da mitigação (high, medium, low) (opcional)
            limit: Número máximo de resultados

        Returns:
            Lista de opiniões com mitigações
        """
        try:
            query: Dict[str, Any] = {
                "opinion.mitigations": {"$exists": True, "$ne": []}
            }

            # Filtros opcionais
            if mitigation_type or priority:
                elem_match: Dict[str, Any] = {}
                if mitigation_type:
                    elem_match["mitigation_type"] = mitigation_type
                if priority:
                    elem_match["priority"] = priority
                query["opinion.mitigations"] = {"$elemMatch": elem_match}

            cursor = (
                self.collection.find(query)
                .sort("evaluated_at", DESCENDING)
                .limit(limit)
            )

            opinions = list(cursor)
            for opinion in opinions:
                opinion.pop("_id", None)

            logger.debug(
                "Opinions with mitigations retrieved",
                mitigation_type=mitigation_type,
                priority=priority,
                count=len(opinions),
            )

            return opinions

        except PyMongoError as e:
            logger.error("Failed to query opinions with mitigations", error=str(e))
            return []

    def create_indexes(self):
        """
        Cria indexes otimizados para queries comuns.

        Sincronizado com LedgerClient._create_indexes() para garantir consistência.
        Deve ser chamado uma vez durante inicialização.
        """
        try:
            # Index único por opinion_id
            self.collection.create_index(
                [("opinion_id", ASCENDING)], unique=True, name="idx_opinion_id"
            )

            # Index por plan_id
            self.collection.create_index([("plan_id", ASCENDING)], name="idx_plan_id")

            # Index por intent_id
            self.collection.create_index(
                [("intent_id", ASCENDING)], name="idx_intent_id"
            )

            # Index composto specialist_type + evaluated_at
            self.collection.create_index(
                [("specialist_type", ASCENDING), ("evaluated_at", DESCENDING)],
                name="idx_specialist_evaluated_at",
            )

            # Index por correlation_id
            self.collection.create_index(
                [("correlation_id", ASCENDING)], name="idx_correlation_id"
            )

            # Index por domain (v2)
            self.collection.create_index(
                [("opinion.metadata.domain", ASCENDING)], name="idx_domain"
            )

            # Index por reasoning_factors.factor_name (v2)
            self.collection.create_index(
                [("opinion.reasoning_factors.factor_name", ASCENDING)],
                name="idx_reasoning_factors",
            )

            # Index por mitigations.priority (v2)
            self.collection.create_index(
                [("opinion.mitigations.priority", ASCENDING)],
                name="idx_mitigations_priority",
            )

            # Index por schema_version (v2)
            self.collection.create_index(
                [("schema_version", ASCENDING)], name="idx_schema_version"
            )

            # Index por digital_signature (sparse, v2)
            self.collection.create_index(
                [("digital_signature", ASCENDING)],
                sparse=True,
                name="idx_digital_signature",
            )

            logger.info("Ledger indexes created successfully")

        except PyMongoError as e:
            logger.error("Failed to create indexes", error=str(e))
