"""
Fixtures específicos para testes D3 (Build + Geração de Artefatos).

Estas fixtures suportam os testes conforme MODELO_TESTE_WORKER_AGENT.md seção D3.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_mock import MockerFixture


# ============================================================================
# Fixtures de Tickets D3
# ============================================================================


@pytest.fixture
def d3_build_ticket():
    """Ticket BUILD conforme especificação D3."""
    from src.models.execution_ticket import (
        ExecutionTicket, TaskType, TicketStatus, Priority, RiskBand,
        SLA, QoS, SecurityLevel, DeliveryMode, Consistency, Durability
    )

    ticket_id = str(uuid.uuid4())
    return ExecutionTicket(
        ticket_id=ticket_id,
        plan_id='plan-test-d3',
        intent_id='intent-test-d3',
        decision_id='decision-test-d3',
        correlation_id=str(uuid.uuid4()),
        trace_id=str(uuid.uuid4()),
        span_id=str(uuid.uuid4()),
        task_type=TaskType.BUILD,
        status=TicketStatus.PENDING,
        priority=Priority.NORMAL,
        risk_band=RiskBand.MEDIUM,
        parameters={
            'artifact_id': 'myapp-api',
            'branch': 'feature/oauth2',
            'commit_sha': 'abc123def456',
            'build_args': {'dockerfile': 'Dockerfile.prod'},
            'env': {'NODE_ENV': 'production'},
            'timeout_seconds': 7200,
            'poll_interval_seconds': 60
        },
        sla=SLA(
            deadline=datetime.now() + timedelta(hours=4),
            timeout_ms=14400000,  # 4 horas
            max_retries=3
        ),
        qos=QoS(
            delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            consistency=Consistency.EVENTUAL,
            durability=Durability.PERSISTENT
        ),
        security_level=SecurityLevel.INTERNAL,
        dependencies=[],
        created_at=datetime.now()
    )


@pytest.fixture
def d3_build_ticket_with_container():
    """Ticket BUILD com parâmetros para geração de container."""
    from src.models.execution_ticket import (
        ExecutionTicket, TaskType, TicketStatus, Priority, RiskBand,
        SLA, QoS, SecurityLevel, DeliveryMode, Consistency, Durability
    )

    ticket_id = str(uuid.uuid4())
    return ExecutionTicket(
        ticket_id=ticket_id,
        plan_id='plan-test-d3-container',
        intent_id='intent-test-d3-container',
        decision_id='decision-test-d3-container',
        correlation_id=str(uuid.uuid4()),
        trace_id=str(uuid.uuid4()),
        span_id=str(uuid.uuid4()),
        task_type=TaskType.BUILD,
        status=TicketStatus.PENDING,
        priority=Priority.HIGH,
        risk_band=RiskBand.LOW,
        parameters={
            'artifact_type': 'MICROSERVICE',
            'language': 'python',
            'service_name': 'myapp-api',
            'container_image': 'ghcr.io/neural-hive/myapp-api:latest',
            'dockerfile': 'Dockerfile.prod',
            'build_context': '/app/build',
            'registry_url': 'ghcr.io/neural-hive',
            'generate_sbom': True,
            'sign_artifact': True,
            'timeout_seconds': 3600
        },
        sla=SLA(
            deadline=datetime.now() + timedelta(hours=2),
            timeout_ms=7200000,  # 2 horas
            max_retries=3
        ),
        qos=QoS(
            delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            consistency=Consistency.EVENTUAL,
            durability=Durability.PERSISTENT
        ),
        security_level=SecurityLevel.INTERNAL,
        dependencies=[],
        created_at=datetime.now()
    )


@pytest.fixture
def d3_build_ticket_with_sbom():
    """Ticket BUILD com parâmetros para geração de SBOM."""
    from src.models.execution_ticket import (
        ExecutionTicket, TaskType, TicketStatus, Priority, RiskBand,
        SLA, QoS, SecurityLevel, DeliveryMode, Consistency, Durability
    )

    ticket_id = str(uuid.uuid4())
    return ExecutionTicket(
        ticket_id=ticket_id,
        plan_id='plan-test-d3-sbom',
        intent_id='intent-test-d3-sbom',
        decision_id='decision-test-d3-sbom',
        correlation_id=str(uuid.uuid4()),
        trace_id=str(uuid.uuid4()),
        span_id=str(uuid.uuid4()),
        task_type=TaskType.BUILD,
        status=TicketStatus.PENDING,
        priority=Priority.NORMAL,
        risk_band=RiskBand.MEDIUM,
        parameters={
            'artifact_type': 'LIBRARY',
            'language': 'python',
            'service_name': 'my-lib',
            'sbom_format': 'SPDX',
            'sbom_version': '2.3',
            'sbom_output_uri': 'gs://artifacts/myapp/sbom.spdx.json'
        },
        sla=SLA(
            deadline=datetime.now() + timedelta(hours=1),
            timeout_ms=3600000,  # 1 hora
            max_retries=3
        ),
        qos=QoS(
            delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            consistency=Consistency.EVENTUAL,
            durability=Durability.PERSISTENT
        ),
        security_level=SecurityLevel.INTERNAL,
        dependencies=[],
        created_at=datetime.now()
    )


# ============================================================================
# Fixtures de PipelineContext D3
# ============================================================================


@pytest.fixture
def d3_pipeline_context(d3_build_ticket):
    """PipelineContext para testes D3."""
    from src.models.pipeline_context import PipelineContext

    return PipelineContext(
        pipeline_id=str(uuid.uuid4()),
        ticket=d3_build_ticket,
        trace_id=d3_build_ticket.trace_id,
        span_id=d3_build_ticket.span_id,
        metadata={
            'test_mode': 'd3',
            'artifact_type': 'CONTAINER'
        }
    )


@pytest.fixture
def d3_pipeline_context_with_artifacts(d3_pipeline_context):
    """PipelineContext com artefatos D3 gerados."""
    from src.models.artifact import (
        CodeForgeArtifact, ArtifactType, GenerationMethod,
        ValidationResult, ValidationType, ValidationStatus
    )

    # Artefato CONTAINER
    container_artifact = CodeForgeArtifact(
        artifact_id=str(uuid.uuid4()),
        ticket_id=d3_pipeline_context.ticket.ticket_id,
        plan_id=d3_pipeline_context.ticket.plan_id,
        intent_id=d3_pipeline_context.ticket.intent_id,
        correlation_id=d3_pipeline_context.ticket.correlation_id,
        trace_id=d3_pipeline_context.trace_id,
        span_id=d3_pipeline_context.span_id,
        artifact_type=ArtifactType.CONTAINER,
        language='python',
        template_id='microservice-python-v1',
        confidence_score=0.95,
        generation_method=GenerationMethod.TEMPLATE,
        content_uri='ghcr.io/neural-hive/myapp-api:latest',
        content_hash='sha256:abc123def456',
        sbom_uri='s3://code-forge/sboms/myapp-api.spdx.json',
        signature='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...',
        validation_results=[
            ValidationResult(
                validation_type=ValidationType.SECURITY_SCAN,
                tool_name='Trivy',
                tool_version='0.50.0',
                status=ValidationStatus.PASSED,
                score=0.95,
                issues_count=0,
                critical_issues=0,
                high_issues=0,
                medium_issues=0,
                low_issues=0,
                executed_at=datetime.now(),
                duration_ms=2000
            )
        ],
        metadata={
            'image_size_bytes': '123456789',
            'registry': 'ghcr.io',
            'digest': 'sha256:abc123def456'
        },
        created_at=datetime.now()
    )

    # Artefato MANIFEST
    manifest_artifact = CodeForgeArtifact(
        artifact_id=str(uuid.uuid4()),
        ticket_id=d3_pipeline_context.ticket.ticket_id,
        plan_id=d3_pipeline_context.ticket.plan_id,
        intent_id=d3_pipeline_context.ticket.intent_id,
        correlation_id=d3_pipeline_context.ticket.correlation_id,
        trace_id=d3_pipeline_context.trace_id,
        span_id=d3_pipeline_context.span_id,
        artifact_type=ArtifactType.IAC,
        language='yaml',
        template_id='kubernetes-deployment-v1',
        confidence_score=0.90,
        generation_method=GenerationMethod.TEMPLATE,
        content_uri='s3://code-forge/manifests/myapp-api-deployment.yaml',
        content_hash='sha256:manifest123',
        validation_results=[],
        metadata={
            'k8s_version': '1.28',
            'namespace': 'production'
        },
        created_at=datetime.now()
    )

    d3_pipeline_context.add_artifact(container_artifact)
    d3_pipeline_context.add_artifact(manifest_artifact)

    return d3_pipeline_context


# ============================================================================
# Mocks de Kafka para D3
# ============================================================================


@pytest.fixture
def mock_d3_kafka_producer():
    """Mock Kafka producer para publicação de resultados D3."""
    producer = AsyncMock()
    producer.start = AsyncMock(return_value=True)
    producer.stop = AsyncMock(return_value=True)
    producer.publish_result = AsyncMock(return_value=True)
    producer.publish = AsyncMock(return_value=True)

    # Rastrear mensagens publicadas
    producer.published_messages = []

    async def _publish_and_track(result):
        producer.published_messages.append(result)
        return True

    producer.publish_result.side_effect = _publish_and_track
    producer.publish.side_effect = _publish_and_track

    return producer


@pytest.fixture
def mock_d3_kafka_consumer():
    """Mock Kafka consumer para consumo de tickets D3."""
    consumer = AsyncMock()
    consumer.start = AsyncMock(return_value=True)
    consumer.stop = AsyncMock(return_value=True)

    # Simular consumo de ticket BUILD
    async def _consume_ticket():
        return {
            'ticket_id': str(uuid.uuid4()),
            'task_type': 'BUILD',
            'parameters': {
                'artifact_id': 'myapp-api',
                'branch': 'feature/test'
            }
        }

    consumer.consume_ticket = AsyncMock(side_effect=_consume_ticket)
    consumer.consume_topic = AsyncMock(return_value=[
        {'ticket_id': 'test-ticket', 'task_type': 'BUILD'}
    ])
    consumer.commit_offset = AsyncMock(return_value=True)

    return consumer


# ============================================================================
# Mocks de Pipeline Stages para D3
# ============================================================================


@pytest.fixture
def mock_d3_template_selector():
    """Mock TemplateSelector para D3."""
    selector = AsyncMock()

    async def _select(context):
        from src.models.template import (
            Template, TemplateMetadata, TemplateType, TemplateLanguage
        )
        context.selected_template = Template(
            template_id='microservice-python-v1',
            metadata=TemplateMetadata(
                name='Python Microservice',
                version='1.0.0',
                description='Template base para microservico Python',
                author='Neural Hive Team',
                tags=['microservice', 'python', 'fastapi'],
                language=TemplateLanguage.PYTHON,
                type=TemplateType.MICROSERVICE
            ),
            parameters=[],
            content_path='/app/templates/microservice-python',
            examples={}
        )
        context.metadata['template_selected'] = 'microservice-python-v1'

    selector.select = AsyncMock(side_effect=_select)
    return selector


@pytest.fixture
def mock_d3_code_composer():
    """Mock CodeComposer para D3."""
    composer = AsyncMock()

    async def _compose(context):
        context.metadata['code_composed'] = 'true'
        context.code_workspace_path = '/tmp/workspace/test'
        context.metadata['files_generated'] = '5'

    composer.compose = AsyncMock(side_effect=_compose)
    return composer


@pytest.fixture
def mock_d3_validator():
    """Mock Validator para D3."""
    validator = AsyncMock()

    async def _validate(context):
        from src.models.artifact import (
            ValidationResult, ValidationType, ValidationStatus
        )
        validation = ValidationResult(
            validation_type=ValidationType.SAST,
            tool_name='SonarQube',
            tool_version='10.0.0',
            status=ValidationStatus.PASSED,
            score=0.95,
            issues_count=0,
            critical_issues=0,
            high_issues=0,
            medium_issues=0,
            low_issues=0,
            executed_at=datetime.now(),
            duration_ms=5000
        )
        context.add_validation(validation)
        context.metadata['validation_passed'] = 'true'

    validator.validate = AsyncMock(side_effect=_validate)
    return validator


@pytest.fixture
def mock_d3_test_runner():
    """Mock TestRunner para D3."""
    runner = AsyncMock()

    async def _run_tests(context):
        context.metadata['tests_run'] = '10'
        context.metadata['tests_passed'] = '10'
        context.metadata['tests_failed'] = '0'

    runner.run_tests = AsyncMock(side_effect=_run_tests)
    return runner


@pytest.fixture
def mock_d3_packager():
    """Mock Packager para D3."""
    packager = AsyncMock()

    async def _package(context):
        from src.models.artifact import (
            CodeForgeArtifact, ArtifactType, GenerationMethod
        )

        # Criar artefato CONTAINER
        container = CodeForgeArtifact(
            artifact_id=str(uuid.uuid4()),
            ticket_id=context.ticket.ticket_id,
            plan_id=context.ticket.plan_id,
            intent_id=context.ticket.intent_id,
            correlation_id=context.ticket.correlation_id,
            trace_id=context.trace_id,
            span_id=context.span_id,
            artifact_type=ArtifactType.CONTAINER,
            language='python',
            confidence_score=0.95,
            generation_method=GenerationMethod.TEMPLATE,
            content_uri='ghcr.io/neural-hive/myapp-api:latest',
            content_hash='sha256:abc123',
            sbom_uri='s3://sboms/test.spdx.json',
            signature='test-signature',
            metadata={
                'image_size_bytes': '123456789',
                'digest': 'sha256:abc123'
            },
            created_at=datetime.now()
        )
        context.add_artifact(container)
        context.metadata['container_built'] = 'true'
        context.metadata['sbom_generated'] = 'true'
        context.metadata['artifact_signed'] = 'true'

    packager.package = AsyncMock(side_effect=_package)
    return packager


@pytest.fixture
def mock_d3_approval_gate():
    """Mock ApprovalGate para D3 (auto-aprovação em testes)."""
    gate = AsyncMock()

    async def _check_approval(context):
        context.metadata['approval_status'] = 'AUTO_APPROVED'
        return True

    gate.check_approval = AsyncMock(side_effect=_check_approval)
    return gate


# ============================================================================
# Mock de PipelineEngine D3 Completo
# ============================================================================


@pytest.fixture
def mock_d3_pipeline_engine(
    mock_d3_template_selector,
    mock_d3_code_composer,
    mock_d3_validator,
    mock_d3_test_runner,
    mock_d3_packager,
    mock_d3_approval_gate,
    mock_d3_kafka_producer,
    mock_ticket_client,
    mock_postgres_client,
    mock_mongodb_client,
    request
):
    """Mock completo do PipelineEngine para testes D3."""
    from src.services.pipeline_engine import PipelineEngine

    # Try to get fixtures from conftest, use defaults if not available
    ticket_client = request.getfixturevalue('mock_ticket_client') if 'mock_ticket_client' in request.fixturenames else mock_ticket_client
    postgres_client = request.getfixturevalue('mock_postgres_client') if 'mock_postgres_client' in request.fixturenames else mock_postgres_client
    mongodb_client = request.getfixturevalue('mock_mongodb_client') if 'mock_mongodb_client' in request.fixturenames else mock_mongodb_client

    engine = PipelineEngine(
        template_selector=mock_d3_template_selector,
        code_composer=mock_d3_code_composer,
        validator=mock_d3_validator,
        test_runner=mock_d3_test_runner,
        packager=mock_d3_packager,
        approval_gate=mock_d3_approval_gate,
        kafka_producer=mock_d3_kafka_producer,
        ticket_client=ticket_client,
        postgres_client=postgres_client,
        mongodb_client=mongodb_client,
        max_concurrent=3,
        pipeline_timeout=60,
        auto_approval_threshold=0.0,  # Auto-aprovação em testes
        min_quality_score=0.0,
        metrics=None
    )

    return engine


# ============================================================================
# Fixtures de Métricas D3
# ============================================================================


@pytest.fixture
def mock_d3_metrics():
    """Mock de métricas Prometheus para testes D3."""
    metrics = MagicMock()

    # Métricas de build
    metrics.build_tasks_executed_total = MagicMock()
    metrics.build_tasks_executed_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))

    metrics.build_duration_seconds = MagicMock()
    metrics.build_duration_seconds.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))

    metrics.build_artifacts_generated_total = MagicMock()
    metrics.build_artifacts_generated_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))

    metrics.build_failures_total = MagicMock()
    metrics.build_failures_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))

    # Métricas de API
    metrics.code_forge_api_calls_total = MagicMock()
    metrics.code_forge_api_calls_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))

    metrics.code_forge_api_duration_seconds = MagicMock()
    metrics.code_forge_api_duration_seconds.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))

    # Métricas de pipeline
    metrics.pipelines_total = MagicMock()
    metrics.pipelines_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))

    metrics.pipeline_duration_seconds = MagicMock()
    metrics.pipeline_duration_seconds.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))

    # Métricas de stage
    metrics.stage_duration_seconds = MagicMock()
    metrics.stage_duration_seconds.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))

    metrics.stage_failures_total = MagicMock()
    metrics.stage_failures_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))

    return metrics


# ============================================================================
# Fixtures de Resultados Esperados D3
# ============================================================================


@pytest.fixture
def d3_expected_pipeline_result():
    """Resultado esperado de um pipeline D3 bem-sucedido."""
    from src.models.artifact import (
        PipelineResult, PipelineStatus, PipelineStage, StageStatus,
        CodeForgeArtifact, ArtifactType, GenerationMethod
    )

    pipeline_id = str(uuid.uuid4())
    ticket_id = str(uuid.uuid4())

    return PipelineResult(
        pipeline_id=pipeline_id,
        ticket_id=ticket_id,
        plan_id='plan-test-d3',
        intent_id='intent-test-d3',
        decision_id='decision-test-d3',
        correlation_id=str(uuid.uuid4()),
        trace_id=str(uuid.uuid4()),
        span_id=str(uuid.uuid4()),
        status=PipelineStatus.COMPLETED,
        artifacts=[
            CodeForgeArtifact(
                artifact_id=str(uuid.uuid4()),
                ticket_id=ticket_id,
                plan_id='plan-test-d3',
                intent_id='intent-test-d3',
                correlation_id=str(uuid.uuid4()),
                trace_id=str(uuid.uuid4()),
                span_id=str(uuid.uuid4()),
                artifact_type=ArtifactType.CONTAINER,
                language='python',
                confidence_score=0.95,
                generation_method=GenerationMethod.TEMPLATE,
                content_uri='ghcr.io/neural-hive/myapp-api:latest',
                content_hash='sha256:abc123',
                sbom_uri='s3://sboms/test.spdx.json',
                signature='test-signature',
                created_at=datetime.now()
            )
        ],
        pipeline_stages=[
            PipelineStage(
                stage_name='template_selection',
                status=StageStatus.COMPLETED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                duration_ms=100
            ),
            PipelineStage(
                stage_name='code_composition',
                status=StageStatus.COMPLETED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                duration_ms=500
            ),
            PipelineStage(
                stage_name='validation',
                status=StageStatus.COMPLETED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                duration_ms=5000
            ),
            PipelineStage(
                stage_name='testing',
                status=StageStatus.COMPLETED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                duration_ms=10000
            ),
            PipelineStage(
                stage_name='packaging',
                status=StageStatus.COMPLETED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                duration_ms=15000
            ),
            PipelineStage(
                stage_name='approval_gate',
                status=StageStatus.COMPLETED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                duration_ms=100
            )
        ],
        total_duration_ms=30700,
        approval_required=False,
        approval_reason=None,
        error_message=None,
        created_at=datetime.now(),
        completed_at=datetime.now(),
        metadata={}
    )


# ============================================================================
# Fixtures de Banco de dados para D3
# ============================================================================


@pytest.fixture
def mock_d3_mongodb_artifact():
    """Mock de artefato salvo no MongoDB para testes D3."""
    return {
        '_id': str(uuid.uuid4()),
        'artifact_id': str(uuid.uuid4()),
        'ticket_id': str(uuid.uuid4()),
        'artifact_type': 'CONTAINER',
        'content_uri': 'ghcr.io/neural-hive/myapp-api:latest',
        'content_hash': 'sha256:abc123',
        'sbom_uri': 's3://sboms/test.spdx.json',
        'signature': 'test-signature',
        'created_at': datetime.now().isoformat(),
        'metadata': {
            'image_size_bytes': '123456789',
            'digest': 'sha256:abc123'
        }
    }


@pytest.fixture
def mock_d3_postgres_pipeline():
    """Mock de pipeline salvo no PostgreSQL para testes D3."""
    return {
        'pipeline_id': str(uuid.uuid4()),
        'ticket_id': str(uuid.uuid4()),
        'plan_id': 'plan-test-d3',
        'intent_id': 'intent-test-d3',
        'status': 'COMPLETED',
        'total_duration_ms': 30700,
        'approval_required': False,
        'artifacts_count': 2,
        'created_at': datetime.now(),
        'completed_at': datetime.now()
    }
