"""Testes de integração MCP Tool Catalog"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.services.template_selector import TemplateSelector
from src.services.code_composer import CodeComposer
from src.services.validator import Validator
from src.models.pipeline_context import PipelineContext
from src.models.execution_ticket import (
    ExecutionTicket,
    TaskType,
    TicketStatus,
    Priority,
    RiskBand,
    SLA,
    QoS,
    DeliveryMode,
    Consistency,
    Durability,
    SecurityLevel,
)
from src.models.artifact import ValidationResult, ValidationType, ValidationStatus


@pytest.fixture
def sample_execution_ticket():
    """Cria ExecutionTicket de teste."""
    return ExecutionTicket(
        ticket_id="ticket-123",
        plan_id="plan-1",
        intent_id="intent-1",
        decision_id="decision-1",
        correlation_id="corr-1",
        trace_id="trace-1",
        span_id="span-1",
        task_type=TaskType.BUILD,
        status=TicketStatus.PENDING,
        priority=Priority.NORMAL,
        risk_band=RiskBand.LOW,
        parameters={
            "artifact_type": "MICROSERVICE",
            "language": "python",
            "service_name": "test-service",
            "description": "Test MCP integration",
            "tasks": ["setup", "build"]
        },
        sla=SLA(deadline=datetime.now() + timedelta(hours=1), timeout_ms=600000, max_retries=1),
        qos=QoS(delivery_mode=DeliveryMode.AT_LEAST_ONCE, consistency=Consistency.EVENTUAL, durability=Durability.PERSISTENT),
        security_level=SecurityLevel.INTERNAL,
        dependencies=[],
        created_at=datetime.now()
    )


@pytest.fixture
def pipeline_context(sample_execution_ticket):
    """Instancia PipelineContext básico."""
    return PipelineContext(
        pipeline_id="pipeline-123",
        ticket=sample_execution_ticket,
        trace_id="trace-1",
        span_id="span-1"
    )


@pytest.fixture
def mock_git_client():
    client = AsyncMock()
    client.clone_templates_repo = AsyncMock()
    return client


@pytest.fixture
def mock_redis_client():
    client = AsyncMock()
    client.get_cached_template = AsyncMock(return_value=None)
    client.cache_template = AsyncMock()
    return client


@pytest.fixture
def mock_mcp_client():
    client = AsyncMock()
    client.request_tool_selection = AsyncMock()
    client.send_tool_feedback = AsyncMock(return_value=True)
    return client


def _validation_result(tool_name: str) -> ValidationResult:
    return ValidationResult(
        validation_type=ValidationType.SAST,
        tool_name=tool_name,
        tool_version="1.0",
        status=ValidationStatus.PASSED,
        score=0.9,
        issues_count=0,
        critical_issues=0,
        high_issues=0,
        medium_issues=0,
        low_issues=0,
        report_uri=None,
        executed_at=datetime.now(),
        duration_ms=1000
    )


@pytest.mark.asyncio
async def test_template_selector_with_mcp_success(pipeline_context, mock_git_client, mock_redis_client, mock_mcp_client):
    """Mock mcp_client.request_tool_selection retornando ferramentas e populando contexto."""
    mock_mcp_client.request_tool_selection.return_value = {
        "request_id": "sel-1",
        "selected_tools": [
            {"tool_id": "t1", "tool_name": "GitHub Copilot", "category": "GENERATION"},
            {"tool_id": "t2", "tool_name": "Cookiecutter", "category": "VALIDATION"}
        ],
        "selection_method": "genetic"
    }

    selector = TemplateSelector(mock_git_client, mock_redis_client, mock_mcp_client)
    template = await selector.select(pipeline_context)

    assert template is not None
    assert pipeline_context.mcp_selection_id == "sel-1"
    assert len(pipeline_context.selected_tools) == 2
    assert pipeline_context.generation_method in ("HYBRID", "LLM", "TEMPLATE")


@pytest.mark.asyncio
async def test_template_selector_mcp_timeout_fallback(pipeline_context, mock_git_client, mock_redis_client, mock_mcp_client):
    """Timeout do MCP deve acionar fallback para template padrão."""
    mock_mcp_client.request_tool_selection.side_effect = asyncio.TimeoutError("timeout")

    selector = TemplateSelector(mock_git_client, mock_redis_client, mock_mcp_client)
    template = await selector.select(pipeline_context)

    assert template is not None
    assert template.template_id == 'microservice-python-v1'
    assert pipeline_context.selected_tools == []


@pytest.mark.asyncio
async def test_code_composer_uses_mcp_generation_method(pipeline_context):
    """CodeComposer deve usar geração LLM quando generation_method='LLM'."""
    mock_mongodb_client = AsyncMock()
    mock_mongodb_client.save_artifact_content = AsyncMock()
    mock_llm_client = AsyncMock()
    mock_llm_client.generate_code = AsyncMock(return_value={
        "code": "print('hello')",
        "confidence_score": 0.9
    })

    composer = CodeComposer(mock_mongodb_client, mock_llm_client, None, None)
    composer._generate_via_llm = AsyncMock(return_value=("print('hello')", 0.9, "LLM"))

    pipeline_context.generation_method = "LLM"
    pipeline_context.mcp_selection_id = "sel-1"
    pipeline_context.selected_tools = [{"tool_name": "GitHub Copilot"}]
    pipeline_context.selected_template = MagicMock(template_id="tmpl-1")

    await composer.compose(pipeline_context)

    composer._generate_via_llm.assert_awaited_once()
    assert pipeline_context.generated_artifacts
    assert pipeline_context.generated_artifacts[0].metadata.get('mcp_selection_id') == "sel-1"


@pytest.mark.asyncio
async def test_validator_uses_mcp_tools(pipeline_context):
    """Validator deve executar apenas ferramentas VALIDATION selecionadas pelo MCP."""
    sonar_client = AsyncMock()
    sonar_client.analyze_code = AsyncMock(return_value=_validation_result("sonarqube"))

    snyk_client = AsyncMock()
    snyk_client.scan_dependencies = AsyncMock(return_value=_validation_result("snyk"))

    trivy_client = AsyncMock()
    trivy_client.scan_filesystem = AsyncMock(return_value=_validation_result("trivy"))

    mcp_client = AsyncMock()
    mcp_client.send_tool_feedback = AsyncMock(return_value=True)

    pipeline_context.selected_tools = [
        {"tool_id": "sonar", "tool_name": "SonarQube", "category": "VALIDATION"},
        {"tool_id": "snyk", "tool_name": "Snyk", "category": "VALIDATION"},
    ]
    pipeline_context.mcp_selection_id = "sel-2"

    validator = Validator(sonar_client, snyk_client, trivy_client, mcp_client)
    await validator.validate(pipeline_context)

    sonar_client.analyze_code.assert_awaited_once()
    snyk_client.scan_dependencies.assert_awaited_once()
    trivy_client.scan_filesystem.assert_not_called()
    mcp_client.send_tool_feedback.assert_awaited()
    assert len(pipeline_context.validation_results) == 2


@pytest.mark.asyncio
async def test_validator_mcp_feedback_failure_non_blocking(pipeline_context):
    """Falha no feedback não deve bloquear validações."""
    sonar_client = AsyncMock()
    sonar_client.analyze_code = AsyncMock(return_value=_validation_result("sonarqube"))

    snyk_client = AsyncMock()
    snyk_client.scan_dependencies = AsyncMock(return_value=_validation_result("snyk"))

    trivy_client = AsyncMock()
    trivy_client.scan_filesystem = AsyncMock(return_value=_validation_result("trivy"))

    mcp_client = AsyncMock()
    mcp_client.send_tool_feedback = AsyncMock(return_value=False)

    pipeline_context.selected_tools = [
        {"tool_id": "sonar", "tool_name": "SonarQube", "category": "VALIDATION"}
    ]
    pipeline_context.mcp_selection_id = "sel-3"

    validator = Validator(sonar_client, snyk_client, trivy_client, mcp_client)
    await validator.validate(pipeline_context)

    assert pipeline_context.validation_results
    mcp_client.send_tool_feedback.assert_awaited_once()


@pytest.mark.asyncio
async def test_pipeline_end_to_end_with_mcp(pipeline_context, mock_git_client, mock_redis_client, mock_mcp_client):
    """Fluxo completo com MCP preenchendo metadados no PipelineResult."""
    mock_mcp_client.request_tool_selection.return_value = {
        "request_id": "sel-99",
        "selected_tools": [
            {"tool_id": "sonar", "tool_name": "SonarQube", "category": "VALIDATION"}
        ],
        "selection_method": "genetic"
    }

    selector = TemplateSelector(mock_git_client, mock_redis_client, mock_mcp_client)
    await selector.select(pipeline_context)

    mongodb_client = AsyncMock()
    mongodb_client.save_artifact_content = AsyncMock()
    composer = CodeComposer(mongodb_client, None, None, mock_mcp_client)
    await composer.compose(pipeline_context)

    sonar_client = AsyncMock()
    sonar_client.analyze_code = AsyncMock(return_value=_validation_result("sonarqube"))
    snyk_client = AsyncMock()
    snyk_client.scan_dependencies = AsyncMock(return_value=_validation_result("snyk"))
    trivy_client = AsyncMock()
    trivy_client.scan_filesystem = AsyncMock(return_value=_validation_result("trivy"))

    mock_mcp_client.send_tool_feedback = AsyncMock(return_value=True)
    validator = Validator(sonar_client, snyk_client, trivy_client, mock_mcp_client)
    await validator.validate(pipeline_context)

    pipeline_context.completed_at = datetime.now()
    result = pipeline_context.to_pipeline_result(0.9, 0.5)

    assert result.metadata.get('mcp_selection_id') == "sel-99"
    assert result.metadata.get('mcp_tools_count') == 1
    assert pipeline_context.generated_artifacts


# =============================================================================
# Testes de Health Check
# =============================================================================

class TestCodeForgeHealthCheck:
    """Testes para health check do Code Forge."""

    def test_readiness_check_with_all_connected(self):
        """Validar que readiness retorna ready quando todos os clients estão conectados."""
        from fastapi.testclient import TestClient
        from src.api.http_server import create_app

        app = create_app()

        # Mock dos clients no app.state
        mock_postgres = MagicMock()
        mock_mongodb = MagicMock()
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_kafka_consumer = MagicMock()
        mock_kafka_producer = MagicMock()
        mock_git = MagicMock()

        app.state.postgres_client = mock_postgres
        app.state.mongodb_client = mock_mongodb
        app.state.redis_client = mock_redis
        app.state.kafka_consumer = mock_kafka_consumer
        app.state.kafka_producer = mock_kafka_producer
        app.state.git_client = mock_git
        app.state.mcp_client = None
        app.state.llm_client = None
        app.state.analyst_client = None

        client = TestClient(app)
        response = client.get('/ready')

        assert response.status_code == 200
        data = response.json()
        assert data['ready'] is True
        assert data['status'] == 'ready'
        assert data['dependencies']['postgres'] == 'connected'
        assert data['dependencies']['mongodb'] == 'connected'
        assert data['dependencies']['redis'] == 'connected'

    def test_readiness_check_with_disconnected_postgres(self):
        """Validar que readiness retorna not_ready quando Postgres está desconectado."""
        from fastapi.testclient import TestClient
        from src.api.http_server import create_app

        app = create_app()

        # Postgres None = desconectado
        mock_mongodb = MagicMock()
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_kafka_consumer = MagicMock()
        mock_kafka_producer = MagicMock()
        mock_git = MagicMock()

        app.state.postgres_client = None
        app.state.mongodb_client = mock_mongodb
        app.state.redis_client = mock_redis
        app.state.kafka_consumer = mock_kafka_consumer
        app.state.kafka_producer = mock_kafka_producer
        app.state.git_client = mock_git
        app.state.mcp_client = None
        app.state.llm_client = None
        app.state.analyst_client = None

        client = TestClient(app)
        response = client.get('/ready')

        assert response.status_code == 200
        data = response.json()
        assert data['ready'] is False
        assert data['status'] == 'not_ready'
        assert data['dependencies']['postgres'] == 'disconnected'

    def test_readiness_check_with_optional_clients(self):
        """Validar que clientes opcionais (MCP, LLM, Analyst) não afetam readiness."""
        from fastapi.testclient import TestClient
        from src.api.http_server import create_app

        app = create_app()

        # Todos os core clients conectados
        mock_postgres = MagicMock()
        mock_mongodb = MagicMock()
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_kafka_consumer = MagicMock()
        mock_kafka_producer = MagicMock()
        mock_git = MagicMock()

        # Clientes opcionais conectados
        mock_mcp = MagicMock()
        mock_llm = MagicMock()
        mock_analyst = MagicMock()

        app.state.postgres_client = mock_postgres
        app.state.mongodb_client = mock_mongodb
        app.state.redis_client = mock_redis
        app.state.kafka_consumer = mock_kafka_consumer
        app.state.kafka_producer = mock_kafka_producer
        app.state.git_client = mock_git
        app.state.mcp_client = mock_mcp
        app.state.llm_client = mock_llm
        app.state.analyst_client = mock_analyst

        client = TestClient(app)
        response = client.get('/ready')

        assert response.status_code == 200
        data = response.json()
        assert data['ready'] is True
        # Clientes opcionais devem aparecer nas dependencies
        assert data['dependencies'].get('mcp') == 'connected'
        assert data['dependencies'].get('llm') == 'connected'
        assert data['dependencies'].get('analyst') == 'connected'

    def test_health_check_liveness(self):
        """Validar que health check liveness retorna healthy."""
        from fastapi.testclient import TestClient
        from src.api.http_server import create_app

        app = create_app()
        client = TestClient(app)
        response = client.get('/health')

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'code-forge'
