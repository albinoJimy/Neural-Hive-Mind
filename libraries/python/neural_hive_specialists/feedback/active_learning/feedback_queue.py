"""
Priority Feedback Queue - Gerencia fila de casos prioritários para revisão.

Fila ordenada por valor informacional para priorizar coleta de feedback
de forma estratégica.
"""

import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from enum import Enum
import structlog

from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

logger = structlog.get_logger()

# Claim expira após X horas
DEFAULT_CLAIM_EXPIRY_HOURS = 1


class QueueStatus(str, Enum):
    """Status de um caso na fila."""

    PENDING = "pending"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class QueuedCase(BaseModel):
    """Caso enfileirado para revisão prioritária."""

    queue_id: str = Field(default_factory=lambda: f"queue-{uuid.uuid4().hex[:12]}")
    plan_id: str = Field(..., description="ID do plano cognitivo")
    intent_text: Optional[str] = Field(None, description="Texto completo da intenção")
    intent_preview: str = Field(..., description="Primeiros 100 caracteres da intenção")
    information_value: float = Field(
        ..., ge=0.0, le=1.0, description="Valor informacional"
    )
    priority_reason: str = Field(..., description="Razão da prioridade")
    domain: Optional[str] = Field(None, description="Domínio NLP")
    confidence: Optional[float] = Field(None, description="Confiança da predição")
    predicted_decision: Optional[str] = Field(None, description="Decisão predita")
    status: QueueStatus = Field(
        default=QueueStatus.PENDING, description="Status na fila"
    )
    assigned_to: Optional[str] = Field(None, description="Usuário que fez claim")
    claimed_at: Optional[datetime] = Field(None, description="Timestamp do claim")
    expires_at: Optional[datetime] = Field(None, description="Expiração do claim")
    completed_at: Optional[datetime] = Field(None, description="Timestamp de conclusão")
    feedback_id: Optional[str] = Field(None, description="ID do feedback submetido")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return self.model_dump()


class PriorityFeedbackQueue:
    """
    Gerencia fila de casos prioritários para revisão manual.

    Responsável por:
    - Enfileirar casos com cálculo de valor informacional
    - Desenfileirar próximo caso prioritário
    - Gerenciar claims e expiração
    - Marcar casos como completos
    """

    def __init__(
        self,
        collection,
        strategy=None,
        claim_expiry_hours: int = DEFAULT_CLAIM_EXPIRY_HOURS,
    ):
        """
        Inicializa a fila.

        Args:
            collection: Coleção MongoDB (active_learning_queue)
            strategy: ActiveLearningStrategy opcional
            claim_expiry_hours: Horas para expirar claim (padrão: 1)
        """
        self.collection = collection
        self.strategy = strategy
        self.claim_expiry_hours = claim_expiry_hours

        logger.info(
            "PriorityFeedbackQueue initialized", claim_expiry_hours=claim_expiry_hours
        )

    def enqueue_plan_for_review(
        self,
        plan_id: str,
        intent_text: str,
        prediction: Dict[str, Any],
        dataset_stats: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Adiciona plano à fila de revisão.

        Args:
            plan_id: ID do plano cognitivo
            intent_text: Texto da intenção
            prediction: Predição ML (decision, confidence, nlp_features)
            dataset_stats: Estatísticas do dataset para cálculo de valor

        Returns:
            Dicionário com caso criado

        Raises:
            ValueError: Se plano já está na fila
        """
        # Calcular valor informacional
        if self.strategy and dataset_stats:
            information_value = self.strategy.calculate_from_prediction(
                prediction, dataset_stats
            )
        else:
            # Usar heurística simples se não tiver strategy
            confidence = prediction.get("confidence", 0.5)
            information_value = 1.0 - confidence

        # Gerar razão de prioridade
        priority_reason = self._generate_priority_reason(information_value, prediction)

        # Extrair domínio
        nlp_features = prediction.get("nlp_features", {}) or {}
        domain = nlp_features.get("primary_domain", "unknown")

        # Criar documento
        doc = {
            "queue_id": f"queue-{uuid.uuid4().hex[:12]}",
            "plan_id": plan_id,
            "intent_text": intent_text,
            "intent_preview": intent_text[:100] if intent_text else "",
            "information_value": round(information_value, 3),
            "priority_reason": priority_reason,
            "domain": domain,
            "confidence": prediction.get("confidence"),
            "predicted_decision": prediction.get("decision"),
            "status": QueueStatus.PENDING,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "metadata": {"nlp_features": nlp_features},
        }

        try:
            self.collection.insert_one(doc)
            logger.info(
                "Plan enqueued for review",
                queue_id=doc["queue_id"],
                plan_id=plan_id,
                information_value=information_value,
            )
            return doc

        except DuplicateKeyError:
            raise ValueError(f"Plano {plan_id} já está na fila de revisão")

    def dequeue_next_case(self) -> Optional[Dict[str, Any]]:
        """
        Retorna próximo caso prioritário.

        Busca caso com maior information_value que esteja PENDING.

        Returns:
            Dicionário com caso ou None se fila vazia
        """
        try:
            # Buscar caso com maior valor informacional
            query = {"status": QueueStatus.PENDING}
            sort = [("information_value", -1), ("created_at", 1)]

            case = self.collection.find_one(query, sort=sort)

            if case:
                # Remover _id do MongoDB
                case.pop("_id", None)
                return case

            return None

        except Exception as e:
            logger.error("Failed to dequeue case", error=str(e))
            return None

    def claim_case(self, queue_id: str, assigned_to: str) -> Optional[Dict[str, Any]]:
        """
        Marca caso como "em revisão" para um usuário.

        Args:
            queue_id: ID do caso na fila
            assigned_to: Email do usuário

        Returns:
            Caso atualizado ou None se não encontrado
        """
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=self.claim_expiry_hours)

        update = {
            "$set": {
                "status": QueueStatus.IN_REVIEW,
                "assigned_to": assigned_to,
                "claimed_at": now,
                "expires_at": expires_at,
                "updated_at": now,
            }
        }

        result = self.collection.update_one(
            {"queue_id": queue_id, "status": QueueStatus.PENDING}, update
        )

        if result.matched_count == 0:
            return None

        # Buscar caso atualizado
        case = self.collection.find_one({"queue_id": queue_id})
        if case:
            case.pop("_id", None)

        logger.info("Case claimed", queue_id=queue_id, assigned_to=assigned_to)

        return case

    def release_case(self, queue_id: str) -> Optional[Dict[str, Any]]:
        """
        Libera caso da fila (ex: usuário decidiu não revisar).

        Args:
            queue_id: ID do caso na fila

        Returns:
            Caso atualizado ou None se não encontrado
        """
        now = datetime.utcnow()

        update = {
            "$set": {
                "status": QueueStatus.PENDING,
                "assigned_to": None,
                "claimed_at": None,
                "expires_at": None,
                "updated_at": now,
            }
        }

        result = self.collection.update_one({"queue_id": queue_id}, update)

        if result.matched_count == 0:
            return None

        logger.info("Case released", queue_id=queue_id)

        return {"queue_id": queue_id, "status": QueueStatus.PENDING}

    def mark_feedback_submitted(
        self, queue_id: str, feedback_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Marca feedback como submetido e caso como completo.

        Args:
            queue_id: ID do caso na fila
            feedback_id: ID do feedback submetido

        Returns:
            Caso atualizado ou None se não encontrado
        """
        now = datetime.utcnow()

        update = {
            "$set": {
                "status": QueueStatus.COMPLETED,
                "feedback_id": feedback_id,
                "completed_at": now,
                "updated_at": now,
            }
        }

        result = self.collection.update_one({"queue_id": queue_id}, update)

        if result.matched_count == 0:
            return None

        logger.info(
            "Case marked as completed", queue_id=queue_id, feedback_id=feedback_id
        )

        return {
            "queue_id": queue_id,
            "status": QueueStatus.COMPLETED,
            "feedback_id": feedback_id,
        }

    def get_queue_size(self, status: Optional[QueueStatus] = None) -> int:
        """
        Retorna tamanho da fila.

        Args:
            status: Filtrar por status (opcional)

        Returns:
            Contagem de documentos
        """
        query = {"status": status} if status else {}
        return self.collection.count_documents(query)

    def get_pending_cases(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retorna lista de casos pendentes.

        Args:
            limit: Máximo de casos a retornar

        Returns:
            Lista de casos ordenados por valor informacional
        """
        query = {"status": QueueStatus.PENDING}
        sort = [("information_value", -1), ("created_at", 1)]

        cursor = self.collection.find(query, sort=sort).limit(limit)

        cases = []
        for doc in cursor:
            doc.pop("_id", None)
            cases.append(doc)

        return cases

    def expire_claims(self) -> int:
        """
        Expira claims antigos que não foram processados.

        Retorna casos expirados para PENDING.

        Returns:
            Número de casos expirados
        """
        now = datetime.utcnow()

        update = {
            "$set": {
                "status": QueueStatus.PENDING,
                "assigned_to": None,
                "claimed_at": None,
                "expires_at": None,
                "updated_at": now,
            }
        }

        result = self.collection.update_many(
            {"status": QueueStatus.IN_REVIEW, "expires_at": {"$lt": now}}, update
        )

        count = result.modified_count
        if count > 0:
            logger.info("Claims expired", count=count)

        return count

    def cleanup_completed(self, older_than_hours: int = 24) -> int:
        """
        Limpa casos completos antigos.

        Args:
            older_than_hours: Remover casos completados mais antigos que X horas

        Returns:
            Número de casos removidos
        """
        cutoff = datetime.utcnow() - timedelta(hours=older_than_hours)

        result = self.collection.delete_many(
            {"status": QueueStatus.COMPLETED, "completed_at": {"$lt": cutoff}}
        )

        count = result.deleted_count
        if count > 0:
            logger.info(
                "Completed cases cleaned up",
                count=count,
                older_than_hours=older_than_hours,
            )

        return count

    def _generate_priority_reason(
        self, information_value: float, prediction: Dict[str, Any]
    ) -> str:
        """Gera descrição do porquê é prioritário."""
        parts = []

        if information_value > 0.7:
            parts.append("alto valor informacional")
        elif information_value > 0.5:
            parts.append("valor informacional moderado")

        confidence = prediction.get("confidence", 0.5)
        if confidence < 0.3:
            parts.append("alta incerteza")
        elif confidence < 0.6:
            parts.append("incerteza moderada")

        decision = prediction.get("decision", "")
        if decision == "reject":
            parts.append("rejeição (sub-representado)")

        return ", ".join(parts) if parts else "prioritário"
