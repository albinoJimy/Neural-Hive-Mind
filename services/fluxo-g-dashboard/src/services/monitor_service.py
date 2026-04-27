"""Serviço de monitoramento do Fluxo G."""

from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import structlog
from src.config.settings import get_settings
from src.models.dashboard import (
    ApprovalItem,
    DashboardMetrics,
    FluxoGStage,
    FluxoGWorkflowDetail,
    StageProgress,
    StageStatus,
    WorkflowStatus,
)

logger = structlog.get_logger(__name__)


class FluxoGMonitorService:
    """Serviço de monitoramento do Fluxo G."""

    def __init__(self):
        """Inicializa o serviço."""
        settings = get_settings()
        self._settings = settings
        self._http_client: Optional[httpx.AsyncClient] = None
        self._logger = logger

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Retorna cliente HTTP."""
        if self._http_client is None:
            timeout = httpx.Timeout(10.0)
            self._http_client = httpx.AsyncClient(timeout=timeout)
        return self._http_client

    async def get_metrics(self) -> DashboardMetrics:
        """
        Retorna métricas agregadas do dashboard.

        Busca:
        - Workflows ativos/completados no Temporal
        - Health dos serviços
        - Estatísticas de aprovações
        """
        metrics = DashboardMetrics()

        # TODO: Buscar métricas reais do Temporal
        # Por ora, retorna stub
        metrics.total_workflows = 100
        metrics.running_workflows = 5
        metrics.completed_workflows = 90
        metrics.failed_workflows = 5

        metrics.fluxo_g_workflows = 30
        metrics.orchestration_workflows = 70

        success_rate = (
            metrics.completed_workflows / metrics.total_workflows
            if metrics.total_workflows > 0
            else 0
        )
        metrics.success_rate = success_rate

        # Health check dos serviços
        metrics.services_health = await self._check_services_health()

        return metrics

    async def _check_services_health(self) -> dict[str, bool]:
        """Verifica saúde dos serviços."""
        health = {}

        client = await self._get_http_client()

        services = {
            "orchestrator": self._settings.orchestrator_url,
            "requirements": self._settings.requirements_url,
            "documentation": self._settings.documentation_url,
            "knowledge_graph": self._settings.knowledge_graph_url,
            "approval": self._settings.approval_url,
        }

        for name, url in services.items():
            try:
                response = await client.get(f"{url}/health", timeout=5.0)
                health[name] = response.status_code == 200
            except Exception as e:
                self._logger.warning("health_check_failed", service=name, error=str(e))
                health[name] = False

        return health

    async def get_recent_workflows(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Retorna workflows recentes.

        TODO: Implementar query real no Temporal.
        """
        # Stub implementation
        return [
            {
                "workflow_id": "orch-001",
                "workflow_type": "FluxoGWorkflow",
                "plan_id": "PLAN-001",
                "status": "completed",
                "started_at": "2026-04-16T10:00:00",
                "completed_at": "2026-04-16T10:05:00",
                "duration_seconds": 300,
            },
            {
                "workflow_id": "orch-002",
                "workflow_type": "FluxoGWorkflow",
                "plan_id": "PLAN-002",
                "status": "running",
                "started_at": "2026-04-16T10:05:00",
                "completed_at": None,
                "duration_seconds": None,
            },
        ]

    async def get_workflow_detail(self, workflow_id: str) -> Optional[FluxoGWorkflowDetail]:
        """
        Retorna detalhes de um workflow específico.

        TODO: Implementar query real no Temporal e buscar histórico.
        """
        # Stub implementation
        return FluxoGWorkflowDetail(
            workflow_id=workflow_id,
            plan_id="PLAN-001",
            intent_id="INTENT-001",
            status=WorkflowStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            stages=[
                StageProgress(
                    stage=FluxoGStage.G1_REQUIREMENTS,
                    status=StageStatus.COMPLETED,
                ),
                StageProgress(
                    stage=FluxoGStage.G2_DOCUMENTATION,
                    status=StageStatus.COMPLETED,
                ),
                StageProgress(
                    stage=FluxoGStage.G3_KNOWLEDGE_GRAPH,
                    status=StageStatus.COMPLETED,
                ),
                StageProgress(
                    stage=FluxoGStage.G4_APPROVALS,
                    status=StageStatus.COMPLETED,
                ),
                StageProgress(
                    stage=FluxoGStage.G5_RAG_ENRICHMENT,
                    status=StageStatus.COMPLETED,
                ),
            ],
            requirements_result={"set_id": "REQ-SET-001", "count": 5},
            documentation_result={"doc_id": "DOC-001", "readme_generated": True},
            knowledge_graph_result={"nodes_created": 10, "relations_created": 8},
            total_duration_seconds=300,
            stages_completed=5,
        )

    async def get_pending_approvals(self, limit: int = 20) -> list[ApprovalItem]:
        """
        Retorna aprovações pendentes.

        Busca do approval-gateway.
        """
        approvals = []

        client = await self._get_http_client()

        try:
            response = await client.get(
                f"{self._settings.approval_url}/api/v1/approvals",
                params={"status": "pending", "limit": limit},
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                for item in data.get("items", []):
                    approvals.append(
                        ApprovalItem(
                            request_id=item.get("request_id", ""),
                            type=item.get("type", "unknown"),
                            title=item.get("title", ""),
                            status=item.get("status", "pending"),
                            confidence_score=item.get("confidence_score", 0.0),
                            requires_human_review=item.get("requires_human_review", False),
                            created_at=datetime.fromisoformat(
                                item.get("created_at", datetime.now(timezone.utc).isoformat())
                            ),
                            plan_id=item.get("context", {}).get("plan_id"),
                        )
                    )
        except Exception as e:
            self._logger.error("failed_to_fetch_approvals", error=str(e))

        return approvals

    async def get_knowledge_graph_stats(self) -> dict[str, int]:
        """
        Retorna estatísticas do grafo de conhecimento.

        Busca do knowledge-graph-rag.
        """
        stats = {"nodes": 0, "relations": 0, "requirements": 0, "user_stories": 0}

        client = await self._get_http_client()

        try:
            response = await client.get(
                f"{self._settings.knowledge_graph_url}/api/v1/graph/health",
                timeout=10.0,
            )

            if response.status_code == 200:
                # TODO: Implementar endpoint de stats no knowledge-graph-rag
                pass
        except Exception as e:
            self._logger.error("failed_to_fetch_graph_stats", error=str(e))

        return stats

    async def close(self):
        """Fecha conexões."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
