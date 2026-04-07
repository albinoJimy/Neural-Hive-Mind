"""
MongoDB repository for pattern registry.

Este módulo implementa o repositório MongoDB para armazenar e buscar
padrões de avaliação do Evolution Specialist, permitindo o
meta-learning baseado em histórico.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import structlog

try:
    from motor.motor_async import AsyncIOMotorClient

    MOTOR_AVAILABLE = True
except ImportError:
    AsyncIOMotorClient = None
    MOTOR_AVAILABLE = False

from .models import Fingerprint, PatternRecord, EvolutionEvaluation, FeedbackData

logger = structlog.get_logger()


class PatternRegistry:
    """
    Repository para armazenar e buscar padrões de avaliação.

    Responsável por:
    - Armazenar avaliações com fingerprints
    - Buscar padrões similares baseado em fingerprint
    - Adicionar feedback a avaliações existentes
    - Atualizar métricas de aprendizado
    """

    COLLECTION_NAME = "evolution_pattern_registry"
    TTL_SECONDS = 90 * 24 * 3600  # 90 dias

    def __init__(self, mongo_client, database: str = "neural_hive"):
        """
        Inicializa repository.

        Args:
            mongo_client: Cliente MongoDB (motor async ou pymongo sync)
            database: Nome do database
        """
        self.client = mongo_client
        self.db = self.client[database]
        self.collection = self.db[self.COLLECTION_NAME]

        logger.info(
            "PatternRegistry initialized",
            collection=self.COLLECTION_NAME,
            database=database,
            motor_available=MOTOR_AVAILABLE,
        )

    async def store_evaluation(
        self, plan_id: str, fingerprint: Fingerprint, evaluation: EvolutionEvaluation
    ) -> str:
        """
        Armazena avaliação com fingerprint.

        Args:
            plan_id: ID do plano cognitivo
            fingerprint: Fingerprint extraído do plano
            evaluation: Avaliação do Evolution Specialist

        Returns:
            ID do documento inserido
        """
        doc = {
            "plan_id": plan_id,
            "fingerprint": fingerprint.model_dump(),
            "evaluation": evaluation.model_dump(),
            "metrics": {
                "times_matched": 0,
                "success_rate": 0.5,
                "last_updated": datetime.now(timezone.utc),
            },
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        result = await self.collection.insert_one(doc)
        logger.info(
            "Stored evaluation pattern", pattern_id=str(result.inserted_id), plan_id=plan_id
        )
        return str(result.inserted_id)

    async def add_feedback(
        self, plan_id: str, feedback: FeedbackData, corrected_weights: Optional[dict] = None
    ) -> bool:
        """
        Adiciona feedback a uma avaliação existente.

        Args:
            plan_id: ID do plano
            feedback: Dados do feedback
            corrected_weights: Pesos corrigidos após feedback

        Returns:
            True se atualizado, False se não encontrado
        """
        feedback_dict = feedback.model_dump()
        # Adicionar pesos corrigidos ao dict de feedback antes de criar o update
        if corrected_weights:
            feedback_dict["corrected_weights"] = corrected_weights

        update_doc = {"$set": {"feedback": feedback_dict, "updated_at": datetime.now(timezone.utc)}}

        result = await self.collection.update_one({"plan_id": plan_id}, update_doc)

        if result.modified_count > 0:
            logger.info(
                "Added feedback to pattern", plan_id=plan_id, outcome=feedback.outcome.value
            )
            return True

        logger.warning("Pattern not found for feedback", plan_id=plan_id)
        return False

    async def find_similar_patterns(
        self, fingerprint: Fingerprint, limit: int = 50, min_similarity: float = 0.0
    ) -> List[PatternRecord]:
        """
        Busca padrões similares baseado em fingerprint.

        A busca utiliza:
        1. Match exato em domain
        2. Prefixo de complexity_signature (primeiros 3 caracteres)
        3. Similaridade Jaccard de task_types

        Args:
            fingerprint: Fingerprint para buscar similares
            limit: Máximo de resultados
            min_similarity: Similaridade Jaccard mínima (0-1)

        Returns:
            Lista de PatternRecord ordenados por similaridade
        """
        # Query base: mesmo domain, prefixo de complexity_signature
        query = {
            "fingerprint.domain": fingerprint.domain,
            "fingerprint.complexity_signature": {
                "$regex": f"^{fingerprint.complexity_signature[:3]}"
            },
        }

        # Buscar candidatos (limit * 2 para filtrar depois)
        cursor = self.collection.find(query).sort("created_at", -1).limit(limit * 2)
        docs = await cursor.to_list(length=limit * 2)

        # Calcular similaridade Jaccard e filtrar
        similar = []
        for doc in docs:
            doc_fingerprint = doc["fingerprint"]
            jaccard = self._calculate_jaccard(
                set(fingerprint.task_types), set(doc_fingerprint.get("task_types", []))
            )

            if jaccard >= min_similarity:
                # Criar PatternRecord e adicionar score de similaridade
                record = PatternRecord(**doc)
                object.__setattr__(record, "_similarity_score", jaccard)
                similar.append(record)

        # Ordenar por similaridade
        similar.sort(key=lambda x: getattr(x, "_similarity_score", 0), reverse=True)

        logger.debug(
            "Found similar patterns",
            fingerprint_domain=fingerprint.domain,
            candidates_found=len(docs),
            similar_filtered=len(similar),
            returned=min(limit, len(similar)),
        )

        return similar[:limit]

    def _calculate_jaccard(self, set1: set, set2: set) -> float:
        """
        Calcula índice Jaccard: |A ∩ B| / |A ∪ B|.

        Args:
            set1: Primeiro conjunto
            set2: Segundo conjunto

        Returns:
            Similaridade Jaccard (0-1)
        """
        if not set1 and not set2:
            return 1.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    async def update_metrics(self, pattern_id: str, success: bool) -> None:
        """
        Atualiza métricas após feedback.

        Args:
            pattern_id: ID do padrão no MongoDB
            success: True se feedback foi positivo, False caso contrário
        """
        # Buscar padrão atual
        pattern = await self.collection.find_one({"_id": pattern_id})
        if not pattern:
            logger.warning("Pattern not found for metrics update", pattern_id=pattern_id)
            return

        current_metrics = pattern.get("metrics", {})
        current_rate = current_metrics.get("success_rate", 0.5)
        times_matched = current_metrics.get("times_matched", 0)

        # Calcular nova success rate (moving average)
        new_rate = (current_rate * times_matched + (1.0 if success else 0.0)) / (times_matched + 1)

        # Atualizar métricas
        update_doc = {
            "$inc": {"metrics.times_matched": 1},
            "$set": {
                "metrics.success_rate": new_rate,
                "metrics.last_updated": datetime.now(timezone.utc),
            },
        }

        await self.collection.update_one({"_id": pattern_id}, update_doc)

        logger.debug(
            "Updated pattern metrics",
            pattern_id=pattern_id,
            success=success,
            new_success_rate=new_rate,
            times_matched=times_matched + 1,
        )

    async def get_pattern_by_plan_id(self, plan_id: str) -> Optional[PatternRecord]:
        """
        Busca padrão por plan_id.

        Args:
            plan_id: ID do plano cognitivo

        Returns:
            PatternRecord se encontrado, None caso contrário
        """
        doc = await self.collection.find_one({"plan_id": plan_id})
        if doc:
            return PatternRecord(**doc)
        return None

    async def count_patterns_by_domain(self, domain: str) -> int:
        """
        Conta padrões por domínio.

        Args:
            domain: Domínio para contar

        Returns:
            Número de padrões no domínio
        """
        count = await self.collection.count_documents({"fingerprint.domain": domain})

        return count

    async def get_statistics(self) -> Dict[str, Any]:
        """
        Retorna estatísticas gerais do registry.

        Returns:
            Dict com estatísticas
        """
        total_patterns = await self.collection.count_documents({})

        # Contar por domínio
        pipeline = [{"$group": {"_id": "$fingerprint.domain", "count": {"$sum": 1}}}]
        domain_counts = await self.collection.aggregate(pipeline).to_list(None)

        # Contar com feedback
        with_feedback = await self.collection.count_documents({"feedback": {"$exists": True}})

        # Contar aprovados vs rejeitados
        approved = await self.collection.count_documents({"feedback.outcome": "approve"})
        rejected = await self.collection.count_documents({"feedback.outcome": "reject"})

        return {
            "total_patterns": total_patterns,
            "patterns_with_feedback": with_feedback,
            "approved_count": approved,
            "rejected_count": rejected,
            "domain_distribution": {doc["_id"]: doc["count"] for doc in domain_counts},
        }


# Synchronous version for non-async contexts (fallback)
class SyncPatternRegistry:
    """
    Versão síncrona do PatternRegistry para uso em contextos não-async.

    Utiliza pymongo síncrono em vez de motor.
    """

    COLLECTION_NAME = "evolution_pattern_registry"

    def __init__(self, mongo_client, database: str = "neural_hive"):
        """
        Inicializa repository síncrono.

        Args:
            mongo_client: Cliente pymongo síncrono
            database: Nome do database
        """
        self.client = mongo_client
        self.db = self.client[database]
        self.collection = self.db[self.COLLECTION_NAME]

        logger.info(
            "SyncPatternRegistry initialized", collection=self.COLLECTION_NAME, database=database
        )

    def store_evaluation(
        self, plan_id: str, fingerprint: Fingerprint, evaluation: EvolutionEvaluation
    ) -> str:
        """
        Armazena avaliação com fingerprint (síncrono).

        Returns:
            ID do documento inserido
        """
        doc = {
            "plan_id": plan_id,
            "fingerprint": fingerprint.model_dump(),
            "evaluation": evaluation.model_dump(),
            "metrics": {
                "times_matched": 0,
                "success_rate": 0.5,
                "last_updated": datetime.now(timezone.utc),
            },
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        result = self.collection.insert_one(doc)
        logger.info(
            "Stored evaluation pattern (sync)", pattern_id=str(result.inserted_id), plan_id=plan_id
        )
        return str(result.inserted_id)

    def add_feedback(
        self, plan_id: str, feedback: FeedbackData, corrected_weights: Optional[dict] = None
    ) -> bool:
        """
        Adiciona feedback a uma avaliação existente (síncrono).

        Returns:
            True se atualizado, False se não encontrado
        """
        feedback_dict = feedback.model_dump()
        # Adicionar pesos corrigidos ao dict de feedback antes de criar o update
        if corrected_weights:
            feedback_dict["corrected_weights"] = corrected_weights

        update_doc = {"$set": {"feedback": feedback_dict, "updated_at": datetime.now(timezone.utc)}}

        result = self.collection.update_one({"plan_id": plan_id}, update_doc)

        if result.modified_count > 0:
            logger.info(
                "Added feedback to pattern (sync)", plan_id=plan_id, outcome=feedback.outcome.value
            )
            return True

        return False

    def find_similar_patterns(
        self, fingerprint: Fingerprint, limit: int = 50, min_similarity: float = 0.0
    ) -> List[PatternRecord]:
        """
        Busca padrões similares (síncrono).

        Returns:
            Lista de PatternRecord ordenados por similaridade
        """
        query = {
            "fingerprint.domain": fingerprint.domain,
            "fingerprint.complexity_signature": {
                "$regex": f"^{fingerprint.complexity_signature[:3]}"
            },
        }

        cursor = self.collection.find(query).sort("created_at", -1).limit(limit * 2)
        docs = list(cursor)

        # Calcular similaridade Jaccard
        similar = []
        for doc in docs:
            doc_fingerprint = doc["fingerprint"]
            jaccard = self._calculate_jaccard(
                set(fingerprint.task_types), set(doc_fingerprint.get("task_types", []))
            )

            if jaccard >= min_similarity:
                record = PatternRecord(**doc)
                object.__setattr__(record, "_similarity_score", jaccard)
                similar.append(record)

        similar.sort(key=lambda x: getattr(x, "_similarity_score", 0), reverse=True)
        return similar[:limit]

    def _calculate_jaccard(self, set1: set, set2: set) -> float:
        """Calcula índice Jaccard."""
        if not set1 and not set2:
            return 1.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def update_metrics(self, pattern_id: str, success: bool) -> None:
        """Atualiza métricas após feedback (síncrono)."""
        pattern = self.collection.find_one({"_id": pattern_id})
        if not pattern:
            return

        current_metrics = pattern.get("metrics", {})
        current_rate = current_metrics.get("success_rate", 0.5)
        times_matched = current_metrics.get("times_matched", 0)

        new_rate = (current_rate * times_matched + (1.0 if success else 0.0)) / (times_matched + 1)

        update_doc = {
            "$inc": {"metrics.times_matched": 1},
            "$set": {
                "metrics.success_rate": new_rate,
                "metrics.last_updated": datetime.now(timezone.utc),
            },
        }

        self.collection.update_one({"_id": pattern_id}, update_doc)
