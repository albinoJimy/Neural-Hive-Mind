"""
Testes para QueenAgentServicer - cobertura completa dos métodos gRPC

Testa os seguintes métodos:
- GetStrategicDecision: busca decisão por ID
- ListStrategicDecisions: lista decisões com filtros e paginação
- GetSystemStatus: status agregado do sistema
- GetActiveConflicts: conflitos ativos no Neo4j
"""

from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest
from src.grpc_server.queen_servicer import QueenAgentServicer
from src.proto import queen_agent_pb2

# =============================================================================
# MOCK DE MÉTRICAS - nível módulo
# =============================================================================


def _create_mock_metrics():
    """Cria mock completo de QueenAgentMetrics."""

    def create_counter_mock():
        counter = MagicMock()
        counter.inc = MagicMock()
        counter.labels = MagicMock(return_value=counter)
        return counter

    def create_histogram_mock():
        histogram = MagicMock()
        histogram.observe = MagicMock()
        histogram.labels = MagicMock(return_value=histogram)
        return histogram

    def create_gauge_mock():
        gauge = MagicMock()
        gauge.set = MagicMock()
        gauge.inc = MagicMock()
        gauge.labels = MagicMock(return_value=gauge)
        return gauge

    metrics = MagicMock()
    # Counter metrics
    metrics.strategic_decisions_total = create_counter_mock()
    metrics.strategic_decision_duration_seconds = create_histogram_mock()
    metrics.strategic_decision_confidence = create_histogram_mock()
    metrics.strategic_decision_risk = create_histogram_mock()
    metrics.conflicts_detected_total = create_counter_mock()
    metrics.conflicts_resolved_total = create_counter_mock()
    metrics.replannings_triggered_total = create_counter_mock()
    metrics.replannings_rejected_cooldown_total = create_counter_mock()
    metrics.active_replannings = create_gauge_mock()
    metrics.exception_requests_total = create_counter_mock()
    metrics.exception_approvals_total = create_counter_mock()
    metrics.exception_rejections_total = create_counter_mock()

    # System metrics
    metrics.system_status_queries_total = create_counter_mock()
    metrics.grpc_requests_total = create_counter_mock()
    metrics.grpc_request_duration_seconds = create_histogram_mock()
    metrics.active_conflicts = create_gauge_mock()
    metrics.active_decisions = create_gauge_mock()
    metrics.system_health_score = create_gauge_mock()
    metrics.sla_compliance_ratio = create_gauge_mock()
    metrics.active_incidents = create_gauge_mock()
    metrics.insights_received_total = create_counter_mock()

    return metrics


# Patch módulo metrics para todos os testes deste arquivo
_patch_metrics = patch(
    "src.observability.metrics.QueenAgentMetrics", return_value=_create_mock_metrics()
)
_patch_metrics.start()
_mock_metrics_instance = _create_mock_metrics()
_patch_servicer_metrics = patch(
    "src.grpc_server.queen_servicer.metrics", return_value=_mock_metrics_instance
)
_patch_servicer_metrics.start()


def _create_mock_metrics():
    """Cria mock completo de QueenAgentMetrics."""

    def create_counter_mock():
        counter = MagicMock()
        counter.inc = MagicMock()
        counter.labels = MagicMock(return_value=counter)
        return counter

    def create_histogram_mock():
        histogram = MagicMock()
        histogram.observe = MagicMock()
        histogram.labels = MagicMock(return_value=histogram)
        return histogram

    def create_gauge_mock():
        gauge = MagicMock()
        gauge.set = MagicMock()
        gauge.inc = MagicMock()
        gauge.labels = MagicMock(return_value=gauge)
        return gauge

    metrics = MagicMock()
    # Counter metrics
    metrics.strategic_decisions_total = create_counter_mock()
    metrics.strategic_decision_duration_seconds = create_histogram_mock()
    metrics.strategic_decision_confidence = create_histogram_mock()
    metrics.strategic_decision_risk = create_histogram_mock()
    metrics.conflicts_detected_total = create_counter_mock()
    metrics.conflicts_resolved_total = create_counter_mock()
    metrics.replannings_triggered_total = create_counter_mock()
    metrics.replannings_rejected_cooldown_total = create_counter_mock()
    metrics.active_replannings = create_gauge_mock()
    metrics.exception_requests_total = create_counter_mock()
    metrics.exception_approvals_total = create_counter_mock()
    metrics.exception_rejections_total = create_counter_mock()

    # System metrics
    metrics.system_status_queries_total = create_counter_mock()
    metrics.grpc_requests_total = create_counter_mock()
    metrics.grpc_request_duration_seconds = create_histogram_mock()
    metrics.active_conflicts = create_gauge_mock()
    metrics.active_decisions = create_gauge_mock()
    metrics.system_health_score = create_gauge_mock()
    metrics.sla_compliance_ratio = create_gauge_mock()
    metrics.active_incidents = create_gauge_mock()
    metrics.insights_received_total = create_counter_mock()

    return metrics


@pytest.fixture(autouse=True)
def mock_metrics():
    """Mock das métricas Prometheus - autouse para patch persistente"""
    mock = _create_mock_metrics()
    # Patch module-level metrics antes de qualquer import
    with patch("src.observability.metrics.QueenAgentMetrics", return_value=mock):
        with patch("src.grpc_server.queen_servicer.metrics", mock):
            yield mock


@pytest.fixture()
def mock_metrics():
    """Mock das métricas Prometheus"""

    def create_counter_mock():
        counter = MagicMock()
        counter.inc = MagicMock()
        counter.labels = MagicMock(return_value=counter)
        return counter

    def create_histogram_mock():
        histogram = MagicMock()
        histogram.observe = MagicMock()
        histogram.labels = MagicMock(return_value=histogram)
        return histogram

    def create_gauge_mock():
        gauge = MagicMock()
        gauge.set = MagicMock()
        gauge.inc = MagicMock()
        gauge.labels = MagicMock(return_value=gauge)
        return gauge

    metrics = MagicMock()
    # Counter metrics
    metrics.strategic_decisions_total = create_counter_mock()
    metrics.strategic_decision_duration_seconds = create_histogram_mock()
    metrics.strategic_decision_confidence = create_histogram_mock()
    metrics.strategic_decision_risk = create_histogram_mock()
    metrics.conflicts_detected_total = create_counter_mock()
    metrics.conflicts_resolved_total = create_counter_mock()
    metrics.replannings_triggered_total = create_counter_mock()
    metrics.replannings_rejected_cooldown_total = create_counter_mock()
    metrics.active_replannings = create_gauge_mock()
    metrics.exception_requests_total = create_counter_mock()
    metrics.exception_approvals_total = create_counter_mock()
    metrics.exception_rejections_total = create_counter_mock()

    # System metrics
    metrics.system_status_queries_total = create_counter_mock()
    metrics.grpc_requests_total = create_counter_mock()
    metrics.grpc_request_duration_seconds = create_histogram_mock()
    metrics.active_conflicts = create_gauge_mock()
    metrics.active_decisions = create_gauge_mock()
    metrics.system_health_score = create_gauge_mock()
    metrics.sla_compliance_ratio = create_gauge_mock()
    metrics.active_incidents = create_gauge_mock()
    metrics.insights_received_total = create_counter_mock()

    return metrics


@pytest.fixture()
def mock_clients():
    """Mock dos clientes"""
    mongodb = AsyncMock()
    mongodb.db = MagicMock()
    mongodb.db.analyst_insights = MagicMock()
    mongodb.db.analyst_insights.insert_one = AsyncMock()
    # Métodos para decisões estratégicas
    mongodb.list_strategic_decisions = AsyncMock(return_value=[])
    mongodb.count_strategic_decisions = AsyncMock(return_value=0)
    mongodb.get_strategic_decision = AsyncMock(return_value=None)

    return {
        "mongodb": mongodb,
        "neo4j": AsyncMock(),
        "exception_service": AsyncMock(),
        "telemetry_aggregator": AsyncMock(),
    }


@pytest.fixture()
def servicer(mock_clients):
    """Instância do servicer com mocks"""
    return QueenAgentServicer(
        mongodb_client=mock_clients["mongodb"],
        neo4j_client=mock_clients["neo4j"],
        exception_service=mock_clients["exception_service"],
        telemetry_aggregator=mock_clients["telemetry_aggregator"],
    )


@pytest.fixture()
def mock_context():
    """Mock do contexto gRPC"""
    context = MagicMock()
    context.set_code = MagicMock()
    context.set_details = MagicMock()
    context.invocation_metadata = MagicMock(return_value=[])
    return context


# =============================================================================
# TESTES: GetStrategicDecision
# =============================================================================


@pytest.mark.asyncio()
async def test_get_strategic_decision_success(servicer, mock_clients, mock_context):
    """Testa busca de decisão estratégica por ID com sucesso"""
    mock_decision = {
        "decision_id": "dec-123",
        "decision_type": "REPLANNING",
        "confidence_score": 0.95,
        "risk_assessment": {"risk_score": 0.15},
        "reasoning_summary": "Replanning necessário devido a falhas",
        "created_at": 1638360000000,
        "decision": {"target_entities": ["plan-001", "plan-002"], "action": "trigger_replanning"},
    }
    mock_clients["mongodb"].get_strategic_decision.return_value = mock_decision

    request = queen_agent_pb2.GetStrategicDecisionRequest(decision_id="dec-123")
    response = await servicer.GetStrategicDecision(request, mock_context)

    assert response.decision_id == "dec-123"
    assert response.decision_type == "REPLANNING"
    assert response.confidence_score == 0.95
    assert response.risk_score == 0.15
    assert response.reasoning_summary == "Replanning necessário devido a falhas"
    assert response.created_at == 1638360000000
    assert list(response.target_entities) == ["plan-001", "plan-002"]
    assert response.action == "trigger_replanning"
    mock_context.set_code.assert_not_called()


@pytest.mark.asyncio()
async def test_get_strategic_decision_not_found(servicer, mock_clients, mock_context):
    """Testa busca de decisão não encontrada"""
    mock_clients["mongodb"].get_strategic_decision.return_value = None

    request = queen_agent_pb2.GetStrategicDecisionRequest(decision_id="dec-inexistente")
    response = await servicer.GetStrategicDecision(request, mock_context)

    mock_context.set_code.assert_called_once_with(grpc.StatusCode.NOT_FOUND)
    mock_context.set_details.assert_called_once()
    assert response.decision_id == ""


@pytest.mark.asyncio()
async def test_get_strategic_decision_internal_error(servicer, mock_clients, mock_context):
    """Testa erro interno ao buscar decisão"""
    mock_clients["mongodb"].get_strategic_decision.side_effect = Exception(
        "MongoDB connection failed"
    )

    request = queen_agent_pb2.GetStrategicDecisionRequest(decision_id="dec-123")
    response = await servicer.GetStrategicDecision(request, mock_context)

    mock_context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)
    mock_context.set_details.assert_called_once_with("MongoDB connection failed")
    assert response.decision_id == ""


@pytest.mark.asyncio()
async def test_get_strategic_decision_partial_data(servicer, mock_clients, mock_context):
    """Testa decisão com dados parciais (campos faltando)"""
    mock_decision = {
        "decision_id": "dec-456",
        "decision_type": "ESCALATION",
        # Campos faltando: confidence_score, risk_assessment, reasoning_summary, etc
    }
    mock_clients["mongodb"].get_strategic_decision.return_value = mock_decision

    request = queen_agent_pb2.GetStrategicDecisionRequest(decision_id="dec-456")
    response = await servicer.GetStrategicDecision(request, mock_context)

    assert response.decision_id == "dec-456"
    assert response.decision_type == "ESCALATION"
    assert response.confidence_score == 0.0  # Valor padrão
    assert response.risk_score == 0.0  # Valor padrão
    assert response.reasoning_summary == ""  # Valor padrão
    assert response.created_at == 0  # Valor padrão
    assert list(response.target_entities) == []  # Lista vazia
    assert response.action == ""  # Valor padrão
    mock_context.set_code.assert_not_called()


# =============================================================================
# TESTES: ListStrategicDecisions
# =============================================================================


@pytest.mark.asyncio()
async def test_list_strategic_decisions_success(servicer, mock_clients, mock_context):
    """Testa listagem de decisões com sucesso"""
    mock_decisions = [
        {
            "decision_id": "dec-001",
            "decision_type": "REPLANNING",
            "confidence_score": 0.92,
            "risk_assessment": {"risk_score": 0.18},
            "reasoning_summary": "Primeira decisão",
            "created_at": 1638360000000,
            "decision": {"target_entities": ["plan-001"], "action": "replanning"},
        },
        {
            "decision_id": "dec-002",
            "decision_type": "ESCALATION",
            "confidence_score": 0.88,
            "risk_assessment": {"risk_score": 0.25},
            "reasoning_summary": "Segunda decisão",
            "created_at": 1638360001000,
            "decision": {"target_entities": ["incident-001"], "action": "escalate"},
        },
    ]
    mock_clients["mongodb"].list_strategic_decisions.return_value = mock_decisions
    mock_clients["mongodb"].count_strategic_decisions.return_value = 2

    request = queen_agent_pb2.ListStrategicDecisionsRequest(limit=10, offset=0)
    response = await servicer.ListStrategicDecisions(request, mock_context)

    assert len(response.decisions) == 2
    assert response.total == 2
    assert response.decisions[0].decision_id == "dec-001"
    assert response.decisions[0].decision_type == "REPLANNING"
    assert response.decisions[1].decision_id == "dec-002"
    assert response.decisions[1].decision_type == "ESCALATION"
    mock_context.set_code.assert_not_called()


@pytest.mark.asyncio()
async def test_list_strategic_decisions_with_filters(servicer, mock_clients, mock_context):
    """Testa listagem com filtros de tipo e data"""
    mock_decisions = [
        {
            "decision_id": "dec-003",
            "decision_type": "REPLANNING",
            "confidence_score": 0.90,
            "risk_assessment": {"risk_score": 0.20},
            "reasoning_summary": "Decisão filtrada",
            "created_at": 1638360002000,
            "decision": {"target_entities": [], "action": "replanning"},
        }
    ]
    mock_clients["mongodb"].list_strategic_decisions.return_value = mock_decisions
    mock_clients["mongodb"].count_strategic_decisions.return_value = 1

    request = queen_agent_pb2.ListStrategicDecisionsRequest(
        decision_type="REPLANNING",
        start_date=1638360000000,
        end_date=1638360003000,
        limit=50,
        offset=0,
    )
    response = await servicer.ListStrategicDecisions(request, mock_context)

    # Verificar que os filtros foram passados corretamente
    call_args = mock_clients["mongodb"].list_strategic_decisions.call_args
    filters = call_args[0][0]
    assert filters["decision_type"] == "REPLANNING"
    assert filters["created_at"]["$gte"] == 1638360000000
    assert filters["created_at"]["$lte"] == 1638360003000
    assert len(response.decisions) == 1
    mock_context.set_code.assert_not_called()


@pytest.mark.asyncio()
async def test_list_strategic_decisions_pagination(servicer, mock_clients, mock_context):
    """Testa paginação com limit e offset"""
    mock_decisions = [
        {
            "decision_id": "dec-021",
            "decision_type": "REPLANNING",
            "confidence_score": 0.9,
            "risk_assessment": {},
            "reasoning_summary": "",
            "created_at": 0,
            "decision": {},
        }
    ]
    mock_clients["mongodb"].list_strategic_decisions.return_value = mock_decisions
    mock_clients["mongodb"].count_strategic_decisions.return_value = 100

    request = queen_agent_pb2.ListStrategicDecisionsRequest(limit=20, offset=40)
    await servicer.ListStrategicDecisions(request, mock_context)

    call_args = mock_clients["mongodb"].list_strategic_decisions.call_args
    assert call_args.kwargs["limit"] == 20
    assert call_args.kwargs["skip"] == 40


@pytest.mark.asyncio()
async def test_list_strategic_decisions_default_limit(servicer, mock_clients, mock_context):
    """Testa limite padrão de 50 quando não especificado"""
    mock_clients["mongodb"].list_strategic_decisions.return_value = []
    mock_clients["mongodb"].count_strategic_decisions.return_value = 0

    request = queen_agent_pb2.ListStrategicDecisionsRequest()
    await servicer.ListStrategicDecisions(request, mock_context)

    call_args = mock_clients["mongodb"].list_strategic_decisions.call_args
    assert call_args.kwargs["limit"] == 50
    assert call_args.kwargs["skip"] == 0


@pytest.mark.asyncio()
async def test_list_strategic_decisions_empty(servicer, mock_clients, mock_context):
    """Testa listagem vazia"""
    mock_clients["mongodb"].list_strategic_decisions.return_value = []
    mock_clients["mongodb"].count_strategic_decisions.return_value = 0

    request = queen_agent_pb2.ListStrategicDecisionsRequest(limit=10)
    response = await servicer.ListStrategicDecisions(request, mock_context)

    assert len(response.decisions) == 0
    assert response.total == 0
    mock_context.set_code.assert_not_called()


@pytest.mark.asyncio()
async def test_list_strategic_decisions_internal_error(servicer, mock_clients, mock_context):
    """Testa erro interno ao listar decisões"""
    mock_clients["mongodb"].list_strategic_decisions.side_effect = Exception("Database timeout")

    request = queen_agent_pb2.ListStrategicDecisionsRequest()
    response = await servicer.ListStrategicDecisions(request, mock_context)

    mock_context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)
    mock_context.set_details.assert_called_once_with("Database timeout")
    assert len(response.decisions) == 0


# =============================================================================
# TESTES: GetSystemStatus
# =============================================================================


@pytest.mark.asyncio()
async def test_get_system_status_success(servicer, mock_clients, mock_context):
    """Testa obtenção de status do sistema com sucesso"""
    mock_health = {
        "system_score": 0.95,
        "sla_compliance": 0.98,
        "error_rate": 0.02,
        "resource_saturation": 0.45,
        "active_incidents": 2,
        "timestamp": 1638360000000,
    }
    mock_clients["telemetry_aggregator"].aggregate_system_health.return_value = mock_health

    request = queen_agent_pb2.GetSystemStatusRequest()
    response = await servicer.GetSystemStatus(request, mock_context)

    assert response.system_score == 0.95
    assert response.sla_compliance == 0.98
    assert response.error_rate == 0.02
    assert response.resource_saturation == 0.45
    assert response.active_incidents == 2
    assert response.timestamp == 1638360000000
    mock_context.set_code.assert_not_called()


@pytest.mark.asyncio()
async def test_get_system_status_default_values(servicer, mock_clients, mock_context):
    """Testa valores padrão quando TelemetryAggregator retorna dados parciais"""
    mock_health = {
        "system_score": 0.80,
        "sla_compliance": 0.92,
        # Campos faltando: error_rate, resource_saturation, active_incidents, timestamp
    }
    mock_clients["telemetry_aggregator"].aggregate_system_health.return_value = mock_health

    request = queen_agent_pb2.GetSystemStatusRequest()
    response = await servicer.GetSystemStatus(request, mock_context)

    assert response.system_score == 0.80
    assert response.sla_compliance == 0.92
    assert response.error_rate == 0.0  # Valor padrão
    assert response.resource_saturation == 0.0  # Valor padrão
    assert response.active_incidents == 0  # Valor padrão
    assert response.timestamp == 0  # Valor padrão
    mock_context.set_code.assert_not_called()


@pytest.mark.asyncio()
async def test_get_system_status_internal_error(servicer, mock_clients, mock_context):
    """Testa erro ao agregar métricas do sistema"""
    mock_clients["telemetry_aggregator"].aggregate_system_health.side_effect = Exception(
        "Prometheus unavailable"
    )

    request = queen_agent_pb2.GetSystemStatusRequest()
    response = await servicer.GetSystemStatus(request, mock_context)

    mock_context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)
    mock_context.set_details.assert_called_once_with("Prometheus unavailable")
    assert response.system_score == 0.0


@pytest.mark.asyncio()
async def test_get_system_status_critical_values(servicer, mock_clients, mock_context):
    """Testa status do sistema com valores críticos"""
    mock_health = {
        "system_score": 0.35,
        "sla_compliance": 0.65,
        "error_rate": 0.45,
        "resource_saturation": 0.95,
        "active_incidents": 15,
        "timestamp": 1638360000000,
    }
    mock_clients["telemetry_aggregator"].aggregate_system_health.return_value = mock_health

    request = queen_agent_pb2.GetSystemStatusRequest()
    response = await servicer.GetSystemStatus(request, mock_context)

    assert response.system_score == 0.35
    assert response.sla_compliance == 0.65
    assert response.error_rate == 0.45
    assert response.resource_saturation == 0.95
    assert response.active_incidents == 15
    mock_context.set_code.assert_not_called()


# =============================================================================
# TESTES: GetActiveConflicts
# =============================================================================


@pytest.mark.asyncio()
async def test_get_active_conflicts_success(servicer, mock_clients, mock_context):
    """Testa obtenção de conflitos ativos com sucesso"""
    # Configurar mock do Neo4j client
    mock_conflicts = [
        {"decision_id": "dec-001", "conflicts_with": "dec-002", "created_at": 1638360000000},
        {"decision_id": "dec-003", "conflicts_with": "dec-004", "created_at": 1638360001000},
    ]
    mock_clients["neo4j"].list_active_conflicts.return_value = mock_conflicts

    # Criar request
    request = queen_agent_pb2.GetActiveConflictsRequest()

    # Executar método
    response = await servicer.GetActiveConflicts(request, mock_context)

    # Verificar resposta
    assert len(response.conflicts) == 2
    assert response.conflicts[0].decision_id == "dec-001"
    assert response.conflicts[0].conflicts_with == "dec-002"
    assert response.conflicts[0].created_at == 1638360000000
    assert response.conflicts[1].decision_id == "dec-003"

    # Verificar que o método correto foi chamado
    mock_clients["neo4j"].list_active_conflicts.assert_called_once()

    # Verificar que não houve erro
    mock_context.set_code.assert_not_called()
    mock_context.set_details.assert_not_called()


@pytest.mark.asyncio()
async def test_get_active_conflicts_empty(servicer, mock_clients, mock_context):
    """Testa obtenção quando não há conflitos"""
    mock_clients["neo4j"].list_active_conflicts.return_value = []

    request = queen_agent_pb2.GetActiveConflictsRequest()
    response = await servicer.GetActiveConflicts(request, mock_context)

    assert len(response.conflicts) == 0
    mock_context.set_code.assert_not_called()


@pytest.mark.asyncio()
async def test_get_active_conflicts_handles_exception(servicer, mock_clients, mock_context):
    """Testa tratamento de exceção"""
    # Simular exceção no Neo4j
    mock_clients["neo4j"].list_active_conflicts.side_effect = Exception("Neo4j error")

    request = queen_agent_pb2.GetActiveConflictsRequest()
    response = await servicer.GetActiveConflicts(request, mock_context)

    # Deve retornar resposta vazia
    assert len(response.conflicts) == 0

    # Deve ter configurado código de erro
    mock_context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)
    mock_context.set_details.assert_called_once()


@pytest.mark.asyncio()
async def test_get_active_conflicts_handles_partial_data(servicer, mock_clients, mock_context):
    """Testa tratamento de dados parciais"""
    # Conflitos com campos faltando
    mock_conflicts = [
        {
            "decision_id": "dec-001",
            # conflicts_with faltando
            "created_at": 1638360000000,
        },
        {
            "decision_id": "dec-002",
            "conflicts_with": "dec-003",
            # created_at faltando
        },
    ]
    mock_clients["neo4j"].list_active_conflicts.return_value = mock_conflicts

    request = queen_agent_pb2.GetActiveConflictsRequest()
    response = await servicer.GetActiveConflicts(request, mock_context)

    # Deve processar mesmo com dados faltando (usando valores padrão)
    assert len(response.conflicts) == 2
    assert response.conflicts[0].decision_id == "dec-001"
    assert response.conflicts[0].conflicts_with == ""  # Valor padrão para string
    assert response.conflicts[1].created_at == 0  # Valor padrão para int
