from datetime import datetime, timezone, timedelta

from motor.motor_asyncio import AsyncIOMotorClient

from src.models.pipeline import (
    Anomaly,
    InsightsReport,
    PipelineManifest,
    PipelineRun,
)
from src.models.schemas import PipelineStatus
from src.repositories.base import BaseRepository


class PipelineManifestRepository(BaseRepository[PipelineManifest]):
    """Repositório para manifests de pipeline."""

    def __init__(self, client: AsyncIOMotorClient | None = None):
        super().__init__(client, collection="pipeline_manifests")

    async def find_by_repo(self, repo_url: str, branch: str = "main") -> dict | None:
        """Encontra o manifesto mais recente para um repositório."""
        return await self.find_one(
            {
                "repo_url": repo_url,
                "branch": branch,
            }
        )

    async def upsert_by_repo(self, repo_url: str, branch: str, manifest: PipelineManifest) -> str:
        """Insere ou atualiza um manifesto para um repositório."""
        existing = await self.find_by_repo(repo_url, branch)

        if existing:
            await self.update(existing["_id"], manifest.model_dump(exclude_unset=True))
            return existing["_id"]

        return await self.create(manifest)


class PipelineRunRepository(BaseRepository[PipelineRun]):
    """Repositório para execuções de pipeline."""

    def __init__(self, client: AsyncIOMotorClient | None = None):
        super().__init__(client, collection="pipeline_runs")
        # Note: Index creation is deferred to avoid async in __init__

    async def _create_indexes(self) -> None:
        """Cria índices para consultas comuns."""
        try:
            await self.create_index([("repo_url", 1), ("started_at", -1)])
            await self.create_index([("git_sha", 1)])
            await self.create_index([("status", 1), ("started_at", -1)])
            await self.create_index([("finished_at", 1)], expireAfterSeconds=2592000)  # 30 days TTL
        except Exception:
            # Indexes might already exist, ignore
            pass

    async def find_recent_by_repo(self, repo_url: str, limit: int = 10) -> list[dict]:
        """Encontra execuções recentes para um repositório."""
        return await self.find_many(
            filter_dict={"repo_url": repo_url},
            sort=[("started_at", -1)],
            limit=limit,
        )

    async def find_by_status(self, status: PipelineStatus, limit: int = 100) -> list[dict]:
        """Encontra execuções com um status específico."""
        return await self.find_many(
            filter_dict={"status": status.value},
            sort=[("started_at", -1)],
            limit=limit,
        )

    async def find_by_date_range(
        self,
        repo_url: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict]:
        """Encontra execuções dentro de um intervalo de datas."""
        return await self.find_many(
            filter_dict={
                "repo_url": repo_url,
                "started_at": {"$gte": start_date, "$lte": end_date},
            },
            sort=[("started_at", -1)],
        )

    async def update_status(self, run_id: str, status: PipelineStatus, **kwargs) -> bool:
        """Atualiza o status de uma execução."""
        updates = {"status": status.value, **kwargs}
        return await self.update(run_id, updates)

    async def get_success_rate(self, repo_url: str, days: int = 30) -> float:
        """Calcula taxa de sucesso para um repositório nos últimos N dias."""
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        pipeline = [
            {
                "$match": {
                    "repo_url": repo_url,
                    "started_at": {"$gte": start_date},
                }
            },
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                }
            },
        ]

        results = await self.aggregate(pipeline)

        total = sum(r["count"] for r in results)
        if total == 0:
            return 0.0

        successful = next(
            (r["count"] for r in results if r["_id"] == PipelineStatus.SUCCESS.value),
            0,
        )

        return successful / total


class AnomalyRepository(BaseRepository[Anomaly]):
    """Repositório para anomalias."""

    def __init__(self, client: AsyncIOMotorClient | None = None):
        super().__init__(client, collection="anomalies")
        # Note: Index creation is deferred to avoid async in __init__

    async def _create_indexes(self) -> None:
        """Cria índices para consultas comuns."""
        try:
            await self.create_index([("repo_url", 1), ("detected_at", -1)])
            await self.create_index([("resolved", 1), ("detected_at", -1)])
            await self.create_index([("type", 1)])
        except Exception:
            # Indexes might already exist, ignore
            pass

    async def find_unresolved(self, repo_url: str) -> list[dict]:
        """Encontra anomalias não resolvidas para um repositório."""
        return await self.find_many(
            filter_dict={
                "repo_url": repo_url,
                "resolved": False,
            },
            sort=[("detected_at", -1)],
        )

    async def find_by_type(self, repo_url: str, anomaly_type: str) -> list[dict]:
        """Encontra anomalias de um tipo específico."""
        return await self.find_many(
            filter_dict={
                "repo_url": repo_url,
                "type": anomaly_type,
            },
            sort=[("detected_at", -1)],
        )

    async def mark_resolved(self, anomaly_id: str) -> bool:
        """Marca uma anomalia como resolvida."""
        return await self.update(
            anomaly_id,
            {"resolved": True, "resolved_at": datetime.now(timezone.utc)},
        )


class InsightsRepository(BaseRepository[InsightsReport]):
    """Repositório para relatórios de insights."""

    def __init__(self, client: AsyncIOMotorClient | None = None):
        super().__init__(client, collection="insights_reports")
        # Note: Index creation is deferred to avoid async in __init__

    async def _create_indexes(self) -> None:
        """Cria índices para consultas comuns."""
        try:
            await self.create_index(
                [("repo_url", 1), ("timeframe_end", -1)],
                unique=True,
            )
        except Exception:
            # Indexes might already exist, ignore
            pass

    async def find_latest(self, repo_url: str, limit: int = 10) -> list[dict]:
        """Encontra os relatórios de insights mais recentes para um repositório."""
        return await self.find_many(
            filter_dict={"repo_url": repo_url},
            sort=[("timeframe_end", -1)],
            limit=limit,
        )
