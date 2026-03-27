"""Repositório para relatórios de validação."""

from typing import List, Optional
from datetime import datetime, timezone
from pymongo.errors import DuplicateKeyError

from src.models.validation import ValidationReport
from src.repositories.base import BaseRepository
from src.config.settings import get_settings


class ValidationRepository(BaseRepository[ValidationReport]):
    """Repositório para relatórios de validação."""

    def __init__(self):
        """Inicializa repositório de validação."""
        settings = get_settings()
        super().__init__(settings.mongodb.collection_validation, ValidationReport)

    def _doc_to_model(self, doc: dict) -> ValidationReport:
        """Converte documento MongoDB para modelo Pydantic."""
        doc_copy = doc.copy()
        doc_id = doc_copy.pop("_id", None)
        if doc_id:
            doc_copy["report_id"] = doc_id
        return ValidationReport(**doc_copy)

    async def create(self, report: ValidationReport) -> str:
        """Cria novo relatório de validação."""
        doc = report.model_dump(by_alias=True, exclude_none=True)
        doc["_id"] = report.report_id
        doc["created_at"] = datetime.now(timezone.utc)

        try:
            await self.collection.insert_one(doc)
            return report.report_id
        except DuplicateKeyError as e:
            raise ValueError(f"Report com ID {report.report_id} já existe") from e

    async def get_by_report_id(self, report_id: str) -> Optional[ValidationReport]:
        """Busca relatório por report_id."""
        doc = await self.collection.find_one({"_id": report_id})
        if doc:
            return self._doc_to_model(doc)
        return None

    async def get_by_repo_url(
        self, repo_url: str, limit: int = 10
    ) -> List[ValidationReport]:
        """Busca relatórios por URL de repositório."""
        cursor = (
            self.collection.find({"repo_url": repo_url})
            .sort("created_at", -1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [self._doc_to_model(doc) for doc in docs]

    async def get_latest_by_repo(self, repo_url: str) -> Optional[ValidationReport]:
        """Obtém relatório mais recente de um repositório."""
        doc = await self.collection.find_one(
            {"repo_url": repo_url}, sort=[("created_at", -1)]
        )
        if doc:
            return self._doc_to_model(doc)
        return None

    async def get_low_health_scores(
        self, threshold: int = 50, limit: int = 20
    ) -> List[ValidationReport]:
        """Busca relatórios com health score baixo."""
        cursor = (
            self.collection.find({"health_score": {"$lt": threshold}})
            .sort("health_score", 1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [self._doc_to_model(doc) for doc in docs]

    async def get_average_health_score(self, repo_url: str | None = None) -> float:
        """Calcula health score médio."""
        pipeline: List[dict] = []
        if repo_url:
            pipeline.append({"$match": {"repo_url": repo_url}})
        pipeline.append(
            {"$group": {"_id": None, "avg_score": {"$avg": "$health_score"}}}
        )

        cursor = self.collection.aggregate(pipeline)
        result = await cursor.to_list(length=1)
        if result and result[0].get("avg_score"):
            return round(result[0]["avg_score"], 2)
        return 0.0
