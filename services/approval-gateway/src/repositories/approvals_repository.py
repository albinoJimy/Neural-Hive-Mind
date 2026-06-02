"""Repositório de solicitações de aprovação."""

from datetime import datetime, timezone
from typing import Optional

import structlog
from src.db.mongodb import get_mongodb_client
from src.models.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalType,
)

logger = structlog.get_logger(__name__)


class ApprovalsRepository:
    """Repositório para solicitações de aprovação."""

    def __init__(self):
        """Inicializa repositório."""
        self._db = get_mongodb_client()
        self._collection = "approvals"

    async def save_request(self, request: ApprovalRequest, decision: ApprovalDecision) -> str:
        """
        Salva solicitação e decisão no MongoDB.

        Returns:
            ID do documento inserido
        """
        await self._db.connect()

        doc = {
            "request": {
                "id": request.id,
                "type": request.type.value,
                "title": request.title,
                "description": request.description,
                "requested_by": request.requested_by,
                "context": request.context,
                "expires_at": request.expires_at.isoformat() if request.expires_at else None,
            },
            "decision": {
                "id": decision.id,
                "request_id": decision.request_id,
                "status": decision.status.value,
                "confidence_score": decision.confidence_score,
                "reasoning": decision.reasoning,
                "approved_by": decision.approved_by,
                "approved_at": decision.approved_at.isoformat() if decision.approved_at else None,
                "feedback": decision.feedback,
                "tags": decision.tags,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        result = await self._db.database[self._collection].insert_one(doc)
        logger.info("saved_approval", request_id=request.id, doc_id=str(result.inserted_id))
        return str(result.inserted_id)

    async def get_by_request_id(self, request_id: str) -> Optional[dict]:
        """Busca solicitação por ID."""
        await self._db.connect()

        doc = await self._db.database[self._collection].find_one({"request.id": request_id})

        return doc

    async def update_decision(
        self,
        request_id: str,
        status: ApprovalStatus,
        approved_by: str,
        feedback: Optional[str] = None,
    ) -> bool:
        """Atualiza decisão (intervenção humana)."""
        await self._db.connect()

        result = await self._db.database[self._collection].update_one(
            {"request.id": request_id},
            {
                "$set": {
                    "decision.status": status.value,
                    "decision.approved_by": approved_by,
                    "decision.feedback": feedback,
                    "decision.approved_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )

        return result.modified_count > 0

    async def list(
        self,
        status: Optional[ApprovalStatus] = None,
        approval_type: Optional[ApprovalType] = None,
        limit: int = 10,
        skip: int = 0,
    ) -> tuple[list[dict], int]:
        """
        Lista solicitações com filtros.

        Returns:
            Tupla (items, total)
        """
        await self._db.connect()

        filters = {}
        if status:
            filters["decision.status"] = status.value
        if approval_type:
            filters["request.type"] = approval_type.value

        total = await self._db.database[self._collection].count_documents(filters)

        cursor = (
            self._db.database[self._collection]
            .find(filters)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )

        items = await cursor.to_list(length=limit)

        return items, total

    async def count_by_status(self, status: ApprovalStatus) -> int:
        """Conta solicitações por status."""
        await self._db.connect()

        return await self._db.database[self._collection].count_documents(
            {"decision.status": status.value}
        )

    async def expire_old_pending(self, timeout_hours: int = 24) -> int:
        """Expira solicitações pendentes antigas."""
        await self._db.connect()

        cutoff = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - __import__("datetime").timedelta(hours=timeout_hours)

        result = await self._db.database[self._collection].update_many(
            {
                "decision.status": ApprovalStatus.PENDING.value,
                "created_at": {"$lt": cutoff.isoformat()},
            },
            {
                "$set": {
                    "decision.status": ApprovalStatus.EXPIRED.value,
                    "decision.reasoning": "Solicitação expirada por timeout",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )

        return result.modified_count

    async def get_metrics(self) -> dict:
        """Retorna métricas agregadas."""
        await self._db.connect()

        pipeline = [{"$group": {"_id": "$decision.status", "count": {"$sum": 1}}}]

        results = await self._db.database[self._collection].aggregate(pipeline).to_list(None)

        metrics = {r["_id"]: r["count"] for r in results}

        return {
            "total": sum(metrics.values()),
            "approved": metrics.get(ApprovalStatus.APPROVED.value, 0),
            "rejected": metrics.get(ApprovalStatus.REJECTED.value, 0),
            "pending": metrics.get(ApprovalStatus.PENDING.value, 0),
            "expired": metrics.get(ApprovalStatus.EXPIRED.value, 0),
        }
