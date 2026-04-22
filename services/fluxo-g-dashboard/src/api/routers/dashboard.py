"""Router API para Fluxo G Dashboard."""

from typing import Optional

from fastapi import APIRouter, HTTPException
from src.models.dashboard import DashboardMetrics, FluxoGWorkflowDetail
from src.services.monitor_service import FluxoGMonitorService

router = APIRouter(prefix="/api", tags=["api"])

# Singleton
_monitor_service: Optional[FluxoGMonitorService] = None


def get_monitor_service() -> FluxoGMonitorService:
    """Retorna instância singleton."""
    global _monitor_service
    if _monitor_service is None:
        _monitor_service = FluxoGMonitorService()
    return _monitor_service


@router.get("/metrics", response_model=DashboardMetrics)
async def get_metrics() -> DashboardMetrics:
    """Retorna métricas do dashboard."""
    service = get_monitor_service()
    return await service.get_metrics()


@router.get("/workflows")
async def list_workflows(
    limit: int = 50,
    status: Optional[str] = None,
) -> dict:
    """Lista workflows recentes."""
    service = get_monitor_service()
    workflows = await service.get_recent_workflows(limit)

    if status:
        workflows = [w for w in workflows if w.get("status") == status]

    return {"workflows": workflows, "total": len(workflows)}


@router.get("/workflows/{workflow_id}", response_model=FluxoGWorkflowDetail)
async def get_workflow_detail(workflow_id: str) -> FluxoGWorkflowDetail:
    """Retorna detalhes de um workflow."""
    service = get_monitor_service()
    detail = await service.get_workflow_detail(workflow_id)

    if not detail:
        raise HTTPException(status_code=404, detail="Workflow não encontrado")

    return detail


@router.get("/approvals/pending")
async def get_pending_approvals(limit: int = 20) -> dict:
    """Lista aprovações pendentes."""
    service = get_monitor_service()
    approvals = await service.get_pending_approvals(limit)

    return {"approvals": approvals, "total": len(approvals)}


@router.get("/graph/stats")
async def get_graph_stats() -> dict:
    """Retorna estatísticas do grafo de conhecimento."""
    service = get_monitor_service()
    stats = await service.get_knowledge_graph_stats()

    return stats


@router.get("/health")
async def health_check() -> dict:
    """Health check do dashboard."""
    service = get_monitor_service()
    health = await service._check_services_health()

    all_healthy = all(health.values()) if health else False

    return {
        "status": "healthy" if all_healthy else "degraded",
        "services": health,
    }
