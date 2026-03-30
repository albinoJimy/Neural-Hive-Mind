"""
Testes para o servico de Validacao do Code Forge.

Cobre validacao de codigo, seguranca e qualidade.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import uuid


@pytest.mark.asyncio
async def test_validator_init():
    """Validator deve inicializar com clientes de validacao."""
    from src.services.validator import Validator

    mock_sonar = AsyncMock()
    mock_snyk = AsyncMock()
    mock_trivy = AsyncMock()
    mock_mcp = AsyncMock()
    mock_metrics = MagicMock()

    validator = Validator(
        sonarqube_client=mock_sonar,
        snyk_client=mock_snyk,
        trivy_client=mock_trivy,
        mcp_client=mock_mcp,
        metrics=mock_metrics
    )

    assert validator.sonarqube_client == mock_sonar
    assert validator.snyk_client == mock_snyk
    assert validator.trivy_client == mock_trivy


@pytest.mark.asyncio
async def test_validate_success():
    """Validacao deve retornar resultado com sucesso."""
    from src.services.validator import Validator
    from src.models.pipeline_context import PipelineContext
    from src.models.execution_ticket import (
        ExecutionTicket, TaskType, TicketStatus, Priority, RiskBand,
        SLA, QoS, SecurityLevel, DeliveryMode, Consistency, Durability
    )
    from src.models.artifact import ValidationStatus

    mock_sonar = AsyncMock()
    mock_snyk = AsyncMock()
    mock_trivy = AsyncMock()
    mock_mcp = AsyncMock()
    mock_metrics = MagicMock()

    mock_sonar.analyze_code = AsyncMock(return_value=MagicMock(
        status=ValidationStatus.PASSED,
        score=0.85
    ))

    validator = Validator(
        sonarqube_client=mock_sonar,
        snyk_client=mock_snyk,
        trivy_client=mock_trivy,
        mcp_client=mock_mcp,
        metrics=mock_metrics
    )

    ticket = ExecutionTicket(
        ticket_id="ticket-123",
        plan_id="plan-123",
        intent_id="intent-123",
        task_type=TaskType.BUILD,
        status=TicketStatus.RUNNING,
        priority=Priority.NORMAL,
        risk_band=RiskBand.MEDIUM,
        parameters={},
        sla=SLA(datetime.now(), 300000, 1),
        qos=QoS(DeliveryMode.AT_LEAST_ONCE, Consistency.EVENTUAL, Durability.PERSISTENT),
        security_level=SecurityLevel.INTERNAL,
        created_at=datetime.now()
    )

    context = PipelineContext(
        pipeline_id="pipeline-123",
        ticket=ticket,
        trace_id="trace-123",
        span_id="span-123"
    )

    result = await validator.validate(context)

    assert context is not None


@pytest.mark.asyncio
async def test_validate_with_sonarqube():
    """Validacao com SonarQube deve analisar codigo."""
    from src.services.validator import Validator
    from src.models.artifact import ValidationType, ValidationStatus

    mock_sonar = AsyncMock()
    mock_snyk = AsyncMock()
    mock_trivy = AsyncMock()
    mock_mcp = AsyncMock()
    mock_metrics = MagicMock()

    mock_result = MagicMock()
    mock_result.validation_type = ValidationType.SAST
    mock_result.status = ValidationStatus.PASSED
    mock_result.score = 0.85
    mock_result.issues_count = 3

    mock_sonar.analyze_code = AsyncMock(return_value=mock_result)

    validator = Validator(
        sonarqube_client=mock_sonar,
        snyk_client=mock_snyk,
        trivy_client=mock_trivy,
        mcp_client=mock_mcp,
        metrics=mock_metrics
    )

    result = await validator.run_sonarqube_analysis(
        "code.py",
        "python"
    )

    assert result.status == ValidationStatus.PASSED
    assert result.score >= 0.8


@pytest.mark.asyncio
async def test_validate_with_snyk():
    """Validacao com Snyk deve escanear dependencias."""
    from src.services.validator import Validator
    from src.models.artifact import ValidationType, ValidationStatus

    mock_sonar = AsyncMock()
    mock_snyk = AsyncMock()
    mock_trivy = AsyncMock()
    mock_mcp = AsyncMock()
    mock_metrics = MagicMock()

    mock_result = MagicMock()
    mock_result.validation_type = ValidationType.SECURITY_SCAN
    mock_result.status = ValidationStatus.PASSED
    mock_result.score = 0.9
    mock_result.issues_count = 0

    mock_snyk.scan_dependencies = AsyncMock(return_value=mock_result)

    validator = Validator(
        sonarqube_client=mock_sonar,
        snyk_client=mock_snyk,
        trivy_client=mock_trivy,
        mcp_client=mock_mcp,
        metrics=mock_metrics
    )

    result = await validator.run_snyk_scan(
        "requirements.txt",
        ["fastapi", "uvicorn"]
    )

    assert result.status == ValidationStatus.PASSED
    mock_snyk.scan_dependencies.assert_called_once()


@pytest.mark.asyncio
async def test_validate_with_trivy():
    """Validacao com Trivy deve escanear filesystem."""
    from src.services.validator import Validator
    from src.models.artifact import ValidationType, ValidationStatus

    mock_sonar = AsyncMock()
    mock_snyk = AsyncMock()
    mock_trivy = AsyncMock()
    mock_mcp = AsyncMock()
    mock_metrics = MagicMock()

    mock_result = MagicMock()
    mock_result.validation_type = ValidationType.SECURITY_SCAN
    mock_result.status = ValidationStatus.PASSED
    mock_result.score = 0.88
    mock_result.critical_issues = 0

    mock_trivy.scan_filesystem = AsyncMock(return_value=mock_result)

    validator = Validator(
        sonarqube_client=mock_sonar,
        snyk_client=mock_snyk,
        trivy_client=mock_trivy,
        mcp_client=mock_mcp,
        metrics=mock_metrics
    )

    result = await validator.run_trivy_scan("/tmp/code")

    assert result.status == ValidationStatus.PASSED
    assert result.critical_issues == 0


@pytest.mark.asyncio
async def test_validate_with_mcp():
    """Validacao com MCP deve usar ferramentas selecionadas."""
    from src.services.validator import Validator

    mock_sonar = AsyncMock()
    mock_snyk = AsyncMock()
    mock_trivy = AsyncMock()
    mock_mcp = AsyncMock()
    mock_metrics = MagicMock()

    mock_mcp.request_tool_selection = AsyncMock(return_value={
        "selected_tools": [
            {"tool_name": "Pylint", "category": "LINTING"}
        ]
    })

    validator = Validator(
        sonarqube_client=mock_sonar,
        snyk_client=mock_snyk,
        trivy_client=mock_trivy,
        mcp_client=mock_mcp,
        metrics=mock_metrics
    )

    result = await validator.run_mcp_validation("code.py")

    mock_mcp.request_tool_selection.assert_called_once()


@pytest.mark.asyncio
async def test_validate_all_disabled():
    """Validacao deve retornar sucesso quando todos estao disabled."""
    from src.services.validator import Validator
    from src.models.pipeline_context import PipelineContext
    from src.models.execution_ticket import (
        ExecutionTicket, TaskType, TicketStatus, Priority, RiskBand,
        SLA, QoS, SecurityLevel, DeliveryMode, Consistency, Durability
    )

    mock_sonar = MagicMock()
    mock_sonar.enabled = False
    mock_snyk = MagicMock()
    mock_snyk.enabled = False
    mock_trivy = MagicMock()
    mock_trivy.enabled = False
    mock_mcp = AsyncMock()
    mock_metrics = MagicMock()

    validator = Validator(
        sonarqube_client=mock_sonar,
        snyk_client=mock_snyk,
        trivy_client=mock_trivy,
        mcp_client=mock_mcp,
        metrics=mock_metrics
    )

    ticket = ExecutionTicket(
        ticket_id="ticket-123",
        plan_id="plan-123",
        intent_id="intent-123",
        task_type=TaskType.BUILD,
        status=TicketStatus.RUNNING,
        priority=Priority.NORMAL,
        risk_band=RiskBand.LOW,
        parameters={},
        sla=SLA(datetime.now(), 300000, 1),
        qos=QoS(DeliveryMode.AT_LEAST_ONCE, Consistency.EVENTUAL, Durability.PERSISTENT),
        security_level=SecurityLevel.INTERNAL,
        created_at=datetime.now()
    )

    context = PipelineContext(
        pipeline_id="pipeline-123",
        ticket=ticket,
        trace_id="trace-123",
        span_id="span-123"
    )

    result = await validator.validate(context)

    # Nao deve falhar mesmo sem validadores habilitados
    assert context is not None


@pytest.mark.asyncio
async def test_calculate_quality_score():
    """Calculo de quality score deve ponderar validacoes."""
    from src.services.validator import Validator

    mock_sonar = AsyncMock()
    mock_snyk = AsyncMock()
    mock_trivy = AsyncMock()
    mock_mcp = AsyncMock()
    mock_metrics = MagicMock()

    validator = Validator(
        sonarqube_client=mock_sonar,
        snyk_client=mock_snyk,
        trivy_client=mock_trivy,
        mcp_client=mock_mcp,
        metrics=mock_metrics
    )

    validations = [
        MagicMock(score=0.85, critical_issues=0, high_issues=1),
        MagicMock(score=0.90, critical_issues=0, high_issues=0),
        MagicMock(score=0.75, critical_issues=0, high_issues=2)
    ]

    score = validator.calculate_quality_score(validations)

    assert 0 <= score <= 1


@pytest.mark.asyncio
async def test_validate_failure_handling():
    """Validacao deve tratar falhas graciosamente."""
    from src.services.validator import Validator
    from src.models.pipeline_context import PipelineContext
    from src.models.execution_ticket import (
        ExecutionTicket, TaskType, TicketStatus, Priority, RiskBand,
        SLA, QoS, SecurityLevel, DeliveryMode, Consistency, Durability
    )

    mock_sonar = AsyncMock()
    mock_snyk = AsyncMock()
    mock_trivy = AsyncMock()
    mock_mcp = AsyncMock()
    mock_metrics = MagicMock()

    # Simular falha no SonarQube
    mock_sonar.analyze_code = AsyncMock(side_effect=Exception("SonarQube unavailable"))
    mock_trivy.scan_filesystem = AsyncMock(side_effect=Exception("Trivy error"))

    validator = Validator(
        sonarqube_client=mock_sonar,
        snyk_client=mock_snyk,
        trivy_client=mock_trivy,
        mcp_client=mock_mcp,
        metrics=mock_metrics
    )

    ticket = ExecutionTicket(
        ticket_id="ticket-123",
        plan_id="plan-123",
        intent_id="intent-123",
        task_type=TaskType.BUILD,
        status=TicketStatus.RUNNING,
        priority=Priority.NORMAL,
        risk_band=RiskBand.MEDIUM,
        parameters={},
        sla=SLA(datetime.now(), 300000, 1),
        qos=QoS(DeliveryMode.AT_LEAST_ONCE, Consistency.EVENTUAL, Durability.PERSISTENT),
        security_level=SecurityLevel.INTERNAL,
        created_at=datetime.now()
    )

    context = PipelineContext(
        pipeline_id="pipeline-123",
        ticket=ticket,
        trace_id="trace-123",
        span_id="span-123"
    )

    # Nao deve lancar excecao
    result = await validator.validate(context)

    assert context is not None
