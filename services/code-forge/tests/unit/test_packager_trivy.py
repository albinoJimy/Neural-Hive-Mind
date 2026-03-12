"""
Testes unitários para integração Packager + Trivy.

Valida que o Packager executa scan de vulnerabilidades nos artefatos.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.services.packager import Packager
from src.models.artifact import (
    CodeForgeArtifact,
    ArtifactType,
    GenerationMethod,
    ValidationResult,
    ValidationStatus,
    ValidationType
)
from src.models.execution_ticket import (
    ExecutionTicket,
    TaskType,
    TicketStatus,
    Priority,
    RiskBand,
    SLA,
    QoS,
    SecurityLevel,
    DeliveryMode,
    Consistency,
    Durability
)


@pytest.fixture
def mock_trivy_client():
    """Mock do TrivyClient."""
    client = AsyncMock()
    client.scan_filesystem = AsyncMock()
    client.scan_container_image = AsyncMock()
    return client


@pytest.fixture
def mock_sigstore_client():
    """Mock do SigstoreClient."""
    client = AsyncMock()
    client.generate_sbom = AsyncMock(return_value='s3://bucket/sbom.json')
    client.sign_artifact = AsyncMock(return_value='signature123')
    return client


@pytest.fixture
def mock_s3_client():
    """Mock do S3ArtifactClient."""
    client = AsyncMock()
    client.verify_sbom_integrity = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_registry_client():
    """Mock do ArtifactRegistryClient."""
    client = AsyncMock()
    client.register_sbom = AsyncMock(return_value='registry-ref-123')
    return client


@pytest.fixture
def mock_postgres_client():
    """Mock do PostgresClient."""
    client = AsyncMock()
    client.save_artifact_metadata = AsyncMock()
    return client


@pytest.fixture
def sample_artifact():
    """Artefato de exemplo."""
    return CodeForgeArtifact(
        artifact_id='artifact-123',
        ticket_id='ticket-456',
        artifact_type=ArtifactType.CODE,
        language='python',
        confidence_score=0.95,
        generation_method=GenerationMethod.LLM,
        content_uri='/tmp/app',
        content_hash='sha256:abc123',
        created_at=datetime.now()
    )


@pytest.fixture
def sample_ticket():
    """Ticket de execução completo para testes."""
    now = datetime.now()
    return ExecutionTicket(
        ticket_id='ticket-456',
        task_type=TaskType.BUILD,
        status=TicketStatus.PENDING,
        priority=Priority.NORMAL,
        risk_band=RiskBand.LOW,
        sla=SLA(
            deadline=now,
            timeout_ms=300000,
            max_retries=3
        ),
        qos=QoS(
            delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            consistency=Consistency.EVENTUAL,
            durability=Durability.PERSISTENT
        ),
        security_level=SecurityLevel.INTERNAL,
        created_at=now
    )


@pytest.fixture
def packager_with_trivy(
    mock_trivy_client,
    mock_sigstore_client,
    mock_s3_client,
    mock_registry_client,
    mock_postgres_client
):
    """Packager com todos os clientes mockados."""
    return Packager(
        sigstore_client=mock_sigstore_client,
        s3_artifact_client=mock_s3_client,
        artifact_registry_client=mock_registry_client,
        postgres_client=mock_postgres_client,
        trivy_client=mock_trivy_client
    )


class TestPackagerTrivyIntegration:
    """Testes de integração Packager + Trivy."""

    @pytest.mark.asyncio
    async def test_package_with_trivy_scan_success(
        self,
        packager_with_trivy,
        sample_artifact,
        sample_ticket,
        mock_trivy_client,
        mock_sigstore_client
    ):
        """Teste empacotamento com scan Trivy bem-sucedido."""
        # Setup mock do scan
        scan_result = ValidationResult(
            validation_type=ValidationType.SECURITY_SCAN,
            tool_name='Trivy',
            tool_version='0.45.0',
            status=ValidationStatus.PASSED,
            score=1.0,
            issues_count=0,
            critical_issues=0,
            high_issues=0,
            medium_issues=0,
            low_issues=0,
            executed_at=datetime.now(),
            duration_ms=5000
        )
        mock_trivy_client.scan_filesystem.return_value = scan_result

        # Criar contexto
        from src.models.pipeline_context import PipelineContext

        context = PipelineContext(
            pipeline_id='pipeline-789',
            ticket=sample_ticket,
            trace_id='trace-123',
            span_id='span-456'
        )
        context.generated_artifacts = [sample_artifact]

        # Executar package
        await packager_with_trivy.package(context)

        # Asserts
        mock_trivy_client.scan_filesystem.assert_called_once()
        assert len(sample_artifact.validation_results) == 1
        assert sample_artifact.validation_results[0].status == ValidationStatus.PASSED

    @pytest.mark.asyncio
    async def test_package_without_trivy_client(
        self,
        sample_artifact,
        sample_ticket,
        mock_sigstore_client,
        mock_s3_client,
        mock_registry_client,
        mock_postgres_client
    ):
        """Teste empacotamento sem Trivy configurado."""
        packager = Packager(
            sigstore_client=mock_sigstore_client,
            s3_artifact_client=mock_s3_client,
            artifact_registry_client=mock_registry_client,
            postgres_client=mock_postgres_client,
            trivy_client=None  # Sem Trivy
        )

        from src.models.pipeline_context import PipelineContext

        context = PipelineContext(
            pipeline_id='pipeline-789',
            ticket=sample_ticket,
            trace_id='trace-123',
            span_id='span-456'
        )
        context.generated_artifacts = [sample_artifact]

        await packager.package(context)

        # Não deve ter resultados de validação
        assert len(sample_artifact.validation_results) == 0

    @pytest.mark.asyncio
    async def test_package_with_trivy_scan_finds_vulnerabilities(
        self,
        packager_with_trivy,
        sample_artifact,
        sample_ticket,
        mock_trivy_client,
        mock_sigstore_client
    ):
        """Teste scan que encontra vulnerabilidades."""
        # Scan com HIGH vulnerability
        scan_result = ValidationResult(
            validation_type=ValidationType.SECURITY_SCAN,
            tool_name='Trivy',
            tool_version='0.45.0',
            status=ValidationStatus.WARNING,
            score=0.6,
            issues_count=3,
            critical_issues=0,
            high_issues=2,
            medium_issues=1,
            low_issues=0,
            executed_at=datetime.now(),
            duration_ms=3000
        )
        mock_trivy_client.scan_filesystem.return_value = scan_result

        from src.models.pipeline_context import PipelineContext

        context = PipelineContext(
            pipeline_id='pipeline-789',
            ticket=sample_ticket,
            trace_id='trace-123',
            span_id='span-456'
        )
        context.generated_artifacts = [sample_artifact]

        await packager_with_trivy.package(context)

        assert len(sample_artifact.validation_results) == 1
        assert sample_artifact.validation_results[0].high_issues == 2

    @pytest.mark.asyncio
    async def test_package_with_container_type(
        self,
        packager_with_trivy,
        sample_ticket,
        mock_trivy_client,
        mock_sigstore_client
    ):
        """Teste scan de artefato tipo CONTAINER."""
        # Criar artifact de container
        container_artifact = CodeForgeArtifact(
            artifact_id='container-123',
            ticket_id='ticket-456',
            artifact_type=ArtifactType.CONTAINER,
            language='golang',
            confidence_score=0.9,
            generation_method=GenerationMethod.LLM,
            content_uri='file:///tmp/build/context',
            content_hash='sha256:def456',
            created_at=datetime.now()
        )

        scan_result = ValidationResult(
            validation_type=ValidationType.SECURITY_SCAN,
            tool_name='Trivy',
            tool_version='0.45.0',
            status=ValidationStatus.PASSED,
            score=1.0,
            issues_count=0,
            critical_issues=0,
            high_issues=0,
            medium_issues=0,
            low_issues=0,
            executed_at=datetime.now(),
            duration_ms=2000
        )
        mock_trivy_client.scan_filesystem.return_value = scan_result

        from src.models.pipeline_context import PipelineContext

        context = PipelineContext(
            pipeline_id='pipeline-789',
            ticket=sample_ticket,
            trace_id='trace-123',
            span_id='span-456'
        )
        context.generated_artifacts = [container_artifact]

        await packager_with_trivy.package(context)

        # Para container com file:// URI, deve usar filesystem scan
        mock_trivy_client.scan_filesystem.assert_called_once()

    @pytest.mark.asyncio
    async def test_package_scan_error_continues(
        self,
        packager_with_trivy,
        sample_artifact,
        sample_ticket,
        mock_trivy_client,
        mock_sigstore_client
    ):
        """Teste que erro no scan não interrompe o empacotamento."""
        # Scan lança exceção
        mock_trivy_client.scan_filesystem.side_effect = Exception('Scan failed')

        from src.models.pipeline_context import PipelineContext

        context = PipelineContext(
            pipeline_id='pipeline-789',
            ticket=sample_ticket,
            trace_id='trace-123',
            span_id='span-456'
        )
        context.generated_artifacts = [sample_artifact]

        # Não deve lançar exceção
        await packager_with_trivy.package(context)

        # Scan não deve ter sido adicionado
        assert len(sample_artifact.validation_results) == 0

        # Outras operações devem ter sido executadas
        mock_sigstore_client.generate_sbom.assert_called_once()
        mock_sigstore_client.sign_artifact.assert_called_once()


class TestPackagerWithoutTrivy:
    """Testes do Packager sem Trivy (backward compatibility)."""

    @pytest.mark.asyncio
    async def test_package_backward_compatibility(
        self,
        sample_artifact,
        sample_ticket,
        mock_sigstore_client,
        mock_s3_client,
        mock_registry_client,
        mock_postgres_client
    ):
        """Teste que Packager funciona sem Trivy (backward compat)."""
        packager = Packager(
            sigstore_client=mock_sigstore_client,
            s3_artifact_client=mock_s3_client,
            artifact_registry_client=mock_registry_client,
            postgres_client=mock_postgres_client
            # Sem trivy_client
        )

        from src.models.pipeline_context import PipelineContext

        context = PipelineContext(
            pipeline_id='pipeline-789',
            ticket=sample_ticket,
            trace_id='trace-123',
            span_id='span-456'
        )
        context.generated_artifacts = [sample_artifact]

        # Deve completar sem erros
        await packager.package(context)

        # Verificar que operações padrão foram executadas
        mock_sigstore_client.generate_sbom.assert_called_once()
        mock_sigstore_client.sign_artifact.assert_called_once()
        mock_postgres_client.save_artifact_metadata.assert_called_once()
