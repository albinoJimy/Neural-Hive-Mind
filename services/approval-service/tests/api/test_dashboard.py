"""
Testes para Dashboard API

Testa endpoints de dashboard com métricas e estatísticas.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.api.routers import dashboard


@pytest.fixture()
def mock_approval_service():
    """Mock do ApprovalService"""
    service = AsyncMock()

    # Mock do MongoDB
    service.db = MagicMock()
    service.db.plan_approvals = MagicMock()
    service.db.specialist_feedback = MagicMock()

    return service


@pytest.fixture()
def mock_user():
    """Mock de usuário autenticado"""
    return {
        "user_id": "test-admin",
        "role": "neural-hive-admin",
        "exp": (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp(),
    }


@pytest.mark.asyncio()
async def test_get_dashboard_stats(mock_approval_service, mock_user):
    """Testa obtenção de estatísticas gerais"""
    # Configurar mocks
    mock_approval_service.db.plan_approvals.count_documents = AsyncMock(
        side_effect=[
            100,  # total_approvals
            5,  # pending_approvals
            10,  # approved_today
            2,  # rejected_today
            70,  # total_week
            35,  # auto_approved
        ]
    )

    with patch("src.api.routers.dashboard.get_current_admin_user", return_value=mock_user):
        with patch(
            "src.api.routers.dashboard.get_approval_service", return_value=mock_approval_service
        ):
            result = await dashboard.get_dashboard_stats(
                days=7, user=mock_user, service=mock_approval_service
            )

    assert result.total_approvals == 100
    assert result.pending_approvals == 5
    assert result.approved_today == 10
    assert result.rejected_today == 2
    assert result.auto_approved_rate == 50.0


@pytest.mark.asyncio()
async def test_get_dashboard_stats_empty_db(mock_approval_service, mock_user):
    """Testa estatísticas com base de dados vazia"""
    # Simular erro/exceção
    mock_approval_service.db.plan_approvals.count_documents = AsyncMock(
        side_effect=Exception("DB connection error")
    )

    with patch("src.api.routers.dashboard.get_current_admin_user", return_value=mock_user):
        with patch(
            "src.api.routers.dashboard.get_approval_service", return_value=mock_approval_service
        ):
            result = await dashboard.get_dashboard_stats(
                days=7, user=mock_user, service=mock_approval_service
            )

    # Deve retornar valores vazios em caso de erro
    assert result.total_approvals == 0
    assert result.pending_approvals == 0
    assert result.auto_approved_rate == 0.0


@pytest.mark.asyncio()
async def test_get_approval_trends(mock_approval_service, mock_user):
    """Testa obtenção de tendências de aprovação"""

    # Configurar mock para retornar valores fixos por dia
    async def mock_count(query):
        # Retornar valores fixos para todas as queries
        return 10

    mock_approval_service.db.plan_approvals.count_documents = AsyncMock(side_effect=mock_count)

    with patch("src.api.routers.dashboard.get_current_admin_user", return_value=mock_user):
        with patch(
            "src.api.routers.dashboard.get_approval_service", return_value=mock_approval_service
        ):
            result = await dashboard.get_approval_trends(
                days=3, user=mock_user, service=mock_approval_service
            )

    # 3 dias de tendências
    assert len(result) == 3
    # Verificar que temos todos os campos esperados
    assert all(hasattr(t, "date") for t in result)
    assert all(hasattr(t, "total") for t in result)
    assert all(hasattr(t, "approved") for t in result)


@pytest.mark.asyncio()
async def test_get_stats_by_risk_band(mock_approval_service, mock_user):
    """Testa estatísticas por banda de risco"""
    # Configurar mocks para cada banda
    call_count = [0]

    async def mock_count(query):
        call_count[0] += 1
        # Retornar valores baseados na banda de risco
        if "critical" in str(query):
            return 10
        elif "high" in str(query):
            return 20
        elif "normal" in str(query):
            return 50
        elif "low" in str(query):
            return 30
        return 5

    mock_approval_service.db.plan_approvals.count_documents = AsyncMock(side_effect=mock_count)

    with patch("src.api.routers.dashboard.get_current_admin_user", return_value=mock_user):
        with patch(
            "src.api.routers.dashboard.get_approval_service", return_value=mock_approval_service
        ):
            result = await dashboard.get_stats_by_risk_band(
                user=mock_user, service=mock_approval_service
            )

    assert len(result) == 4
    assert all(hasattr(stat, "risk_band") for stat in result)
    assert all(hasattr(stat, "approval_rate") for stat in result)


@pytest.mark.asyncio()
async def test_get_ml_performance_stats(mock_approval_service, mock_user):
    """Testa métricas de performance do modelo ML"""
    mock_approval_service.db.specialist_feedback.count_documents = AsyncMock(
        side_effect=[
            100,  # total_predictions
            85,  # correct_predictions
            50,  # predicted_approve
            40,  # true_positive
            45,  # actual_approve
        ]
    )

    mock_approval_service.db.plan_approvals.count_documents = AsyncMock(
        side_effect=[20, 15, 5]  # total_auto  # auto_approve  # auto_reject
    )

    with patch("src.api.routers.dashboard.get_current_admin_user", return_value=mock_user):
        with patch(
            "src.api.routers.dashboard.get_approval_service", return_value=mock_approval_service
        ):
            result = await dashboard.get_ml_performance_stats(
                user=mock_user, service=mock_approval_service
            )

    assert result.total_predictions == 100
    assert result.correct_predictions == 85
    assert result.accuracy == 85.0
    assert result.auto_approve_rate == 75.0


@pytest.mark.asyncio()
async def test_get_ml_performance_stats_error(mock_approval_service, mock_user):
    """Testa métricas ML com erro de conexão"""
    mock_approval_service.db.specialist_feedback.count_documents = AsyncMock(
        side_effect=Exception("DB error")
    )

    with patch("src.api.routers.dashboard.get_current_admin_user", return_value=mock_user):
        with patch(
            "src.api.routers.dashboard.get_approval_service", return_value=mock_approval_service
        ):
            result = await dashboard.get_ml_performance_stats(
                user=mock_user, service=mock_approval_service
            )

    assert result.total_predictions == 0
    assert result.accuracy == 0.0


@pytest.mark.asyncio()
async def test_get_recent_activity(mock_approval_service, mock_user):
    """Testa obtenção de atividade recente"""
    # Mock do cursor
    mock_cursor = AsyncMock()
    mock_cursor.to_list = AsyncMock(
        return_value=[
            {
                "plan_id": "plan-001",
                "status": "approved",
                "risk_band": "normal",
                "is_destructive": False,
                "created_at": datetime.now(timezone.utc),
                "auto_decided": True,
                "specialist_id": "spec-001",
            },
            {
                "plan_id": "plan-002",
                "status": "pending",
                "risk_band": "high",
                "is_destructive": True,
                "created_at": datetime.now(timezone.utc) - timedelta(hours=1),
                "auto_decided": False,
                "specialist_id": "spec-002",
            },
        ]
    )

    mock_approval_service.db.plan_approvals.find = MagicMock(return_value=mock_cursor)
    mock_approval_service.db.plan_approvals.find.return_value.sort = MagicMock(
        return_value=mock_cursor
    )
    mock_approval_service.db.plan_approvals.find.return_value.sort.return_value.limit = MagicMock(
        return_value=mock_cursor
    )

    with patch("src.api.routers.dashboard.get_current_admin_user", return_value=mock_user):
        with patch(
            "src.api.routers.dashboard.get_approval_service", return_value=mock_approval_service
        ):
            result = await dashboard.get_recent_activity(
                limit=10, user=mock_user, service=mock_approval_service
            )

    assert len(result) == 2
    assert result[0]["plan_id"] == "plan-001"
    assert result[0]["status"] == "approved"


@pytest.mark.asyncio()
async def test_get_recent_activity_error(mock_approval_service, mock_user):
    """Testa atividade recente com erro"""
    mock_approval_service.db.plan_approvals.find = MagicMock(side_effect=Exception("DB error"))

    with patch("src.api.routers.dashboard.get_current_admin_user", return_value=mock_user):
        with patch(
            "src.api.routers.dashboard.get_approval_service", return_value=mock_approval_service
        ):
            result = await dashboard.get_recent_activity(
                limit=10, user=mock_user, service=mock_approval_service
            )

    assert result == []


def test_dashboard_models_pydantic():
    """Testa se os modelos Pydantic são válidos"""
    # DashboardStats
    stats = dashboard.DashboardStats(
        total_approvals=100,
        pending_approvals=5,
        approved_today=10,
        rejected_today=2,
        auto_approved_rate=50.0,
        avg_response_time_minutes=15.0,
    )
    assert stats.total_approvals == 100

    # ApprovalTrend
    trend = dashboard.ApprovalTrend(
        date="2026-03-31", approved=10, rejected=2, auto_approved=5, total=12
    )
    assert trend.date == "2026-03-31"

    # RiskBandStats
    risk_stats = dashboard.RiskBandStats(
        risk_band="high", total=20, approved=15, rejected=3, pending=2, approval_rate=75.0
    )
    assert risk_stats.risk_band == "high"

    # MLPerformanceStats
    ml_stats = dashboard.MLPerformanceStats(
        model_version="v7.0",
        total_predictions=100,
        correct_predictions=85,
        accuracy=85.0,
        precision=80.0,
        recall=75.0,
        auto_approve_rate=70.0,
        auto_reject_rate=20.0,
    )
    assert ml_stats.model_version == "v7.0"
