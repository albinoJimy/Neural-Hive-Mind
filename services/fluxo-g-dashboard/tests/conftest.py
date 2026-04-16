"""Configuração pytest para Fluxo G Dashboard."""

import pytest


@pytest.fixture
def mock_monitor_service():
    """Mock do monitor service."""
    from unittest.mock import AsyncMock
    from src.models.dashboard import DashboardMetrics, FluxoGWorkflowDetail

    service = AsyncMock()
    service.get_metrics = AsyncMock(
        return_value=DashboardMetrics(
            total_workflows=100,
            running_workflows=5,
            completed_workflows=90,
            failed_workflows=5,
            success_rate=0.9,
            services_health={
                "orchestrator": True,
                "requirements": True,
                "documentation": True,
                "knowledge_graph": True,
                "approval": True,
            }
        )
    )
    service.get_recent_workflows = AsyncMock(
        return_value=[
            {
                "workflow_id": "orch-001",
                "status": "completed",
                "plan_id": "PLAN-001",
            }
        ]
    )
    service.get_workflow_detail = AsyncMock(
        return_value=FluxoGWorkflowDetail(
            workflow_id="orch-001",
            plan_id="PLAN-001",
            status="completed",
            started_at="2026-04-16T10:00:00",
        )
    )
    service.get_pending_approvals = AsyncMock(return_value=[])
    service.get_knowledge_graph_stats = AsyncMock(
        return_value={"nodes": 100, "relations": 80}
    )
    service._check_services_health = AsyncMock(
        return_value={
            "orchestrator": True,
            "requirements": True,
            "documentation": True,
            "knowledge_graph": True,
            "approval": True,
        }
    )

    return service


@pytest.fixture
def mock_http_client():
    """Mock do cliente HTTP."""
    from unittest.mock import AsyncMock

    client = AsyncMock()
    return client
