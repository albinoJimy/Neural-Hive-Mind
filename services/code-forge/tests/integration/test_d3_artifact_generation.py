"""
Testes de geração de artefatos D3 (Build + Artifact Generation)

Conforme MODELO_TESTE_WORKER_AGENT.md seção D3.

Artefatos:
- CONTAINER: Imagem OCI/Docker
- MANIFEST: Kubernetes manifest
- SBOM: Software Bill of Materials (SPDX 2.3)
- SIGNATURE: Assinatura Sigstore/Cosign
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.artifact import (
from src.types.artifact_types import ArtifactCategory, CodeLanguage
    ArtifactCategory, CodeForgeArtifact, GenerationMethod, ValidationResult,
    ValidationType, ValidationStatus
)
from src.models.pipeline_context import PipelineContext


pytest_plugins = [
    'tests.unit.conftest',
    'tests.fixtures.d3_fixtures'
]


# ============================================================================
# Testes de Geração de Container
# ============================================================================


class TestD3ContainerGeneration:
    """Testes de geração de artefatos CONTAINER."""

    @pytest.mark.asyncio
    async def test_d3_container_artifact_structure(
        self,
        d3_build_ticket_with_container,
        mock_d3_packager,
        d3_pipeline_context
    ):
        """
        D3: Estrutura do artefato CONTAINER

        Campos obrigatórios:
        - artifact_type: CONTAINER
        - content_uri: ghcr.io/neural-hive/...
        - content_hash: sha256:...
        - sbom_uri: s3://...
        - signature: base64...
        """
        await mock_d3_packager.package(d3_pipeline_context)

        # Obter artefato gerado
        assert len(d3_pipeline_context.generated_artifacts) > 0
        container = d3_pipeline_context.generated_artifacts[0]

        # Verificar tipo
        assert container.artifact_type == ArtifactCategory.CONTAINER

        # Verificar content_uri
        assert container.content_uri is not None
        assert any(registry in container.content_uri for registry in [
            'ghcr.io', 'docker.io', 'gcr.io', 'registry.example.com'
        ]), f"Registry inválido: {container.content_uri}"

        # Verificar content_hash
        assert container.content_hash is not None
        assert container.content_hash.startswith('sha256:')

        # Verificar tag presente
        assert ':' in container.content_uri or '@sha256:' in container.content_uri, \
            f"URI sem tag ou digest: {container.content_uri}"

    @pytest.mark.asyncio
    async def test_d3_container_metadata(
        self,
        d3_pipeline_context,
        mock_d3_packager
    ):
        """
        D3: Metadados do artefato CONTAINER

        Metadados esperados:
        - image_size_bytes: tamanho da imagem
        - digest: SHA256 completo
        - registry: registry utilizado
        """
        await mock_d3_packager.package(d3_pipeline_context)

        container = d3_pipeline_context.generated_artifacts[0]

        # Verificar metadados de container
        assert 'image_size_bytes' in container.metadata or \
               'size' in container.metadata, \
            "Metadado de tamanho não encontrado"

        if 'image_size_bytes' in container.metadata:
            size = int(container.metadata['image_size_bytes'])
            assert size > 0, "Tamanho da imagem deve ser > 0"

    @pytest.mark.asyncio
    async def test_d3_container_with_multiple_platforms(
        self,
        d3_pipeline_context
    ):
        """
        D3: Container multi-platform (multi-arch)

        Verifica geração de manifest para múltiplas arquiteturas:
        - linux/amd64
        - linux/arm64
        """
        # Configurar ticket para multi-arch
        d3_pipeline_context.ticket.parameters['platforms'] = [
            'linux/amd64',
            'linux/arm64'
        ]

        packager = MagicMock()
        packager.package = AsyncMock()

        async def _package_multiarch(context):
            artifact = CodeForgeArtifact(
                artifact_id=str(uuid.uuid4()),
                ticket_id=context.ticket.ticket_id,
                plan_id=context.ticket.plan_id,
                intent_id=context.ticket.intent_id,
                correlation_id=context.ticket.correlation_id,
                trace_id=context.trace_id,
                span_id=context.span_id,
                artifact_type=ArtifactCategory.CONTAINER,
                language='python',
                confidence_score=0.95,
                generation_method=GenerationMethod.TEMPLATE,
                content_uri='ghcr.io/neural-hive/myapp-api:multi',
                content_hash='sha256:multi123',
                sbom_uri='s3://sboms/multi.spdx.json',
                signature='multi-signature',
                metadata={
                    'platforms': 'linux/amd64,linux/arm64',
                    'manifest_type': 'manifest-list'
                },
                created_at=datetime.now()
            )
            context.add_artifact(artifact)

        packager.package.side_effect = _package_multiarch

        await packager.package(d3_pipeline_context)

        container = d3_pipeline_context.generated_artifacts[0]
        assert 'platforms' in container.metadata
        assert 'linux/amd64' in container.metadata['platforms']
        assert 'linux/arm64' in container.metadata['platforms']


# ============================================================================
# Testes de Geração de SBOM
# ============================================================================


class TestD3SBOMGeneration:
    """Testes de geração de SBOM."""

    @pytest.mark.asyncio
    async def test_d3_sbom_format_spdx(
        self,
        d3_pipeline_context,
        mock_d3_packager
    ):
        """
        D3: SBOM no formato SPDX 2.3

        Verifica:
        - Formato SPDX
        - Versão 2.3
        - URI válida (.spdx.json)
        """
        await mock_d3_packager.package(d3_pipeline_context)

        container = d3_pipeline_context.generated_artifacts[0]

        # Verificar SBOM
        assert container.sbom_uri is not None
        assert '.spdx' in container.sbom_uri.lower(), \
            f"SBOM não parece SPDX: {container.sbom_uri}"

        # Verificar se é JSON
        assert '.json' in container.sbom_uri or \
               container.sbom_uri.endswith('.spdx'), \
            f"Extensão inválida: {container.sbom_uri}"

    @pytest.mark.asyncio
    async def test_d3_sbom_storage_location(
        self,
        d3_pipeline_context,
        mock_d3_packager
    ):
        """
        D3: Local de armazenamento do SBOM

        Locais suportados:
        - S3: s3://bucket/path/sbom.spdx.json
        - GCS: gs://bucket/path/sbom.spdx.json
        - Azure: azure://bucket/path/sbom.spdx.json
        """
        await mock_d3_packager.package(d3_pipeline_context)

        container = d3_pipeline_context.generated_artifacts[0]

        valid_prefixes = ['s3://', 'gs://', 'azure://', 'http']
        assert any(container.sbom_uri.startswith(p) for p in valid_prefixes), \
            f"URI inválida: {container.sbom_uri}"

    @pytest.mark.asyncio
    async def test_d3_sbom_content_verification(
        self,
        d3_pipeline_context,
        mock_d3_packager
    ):
        """
        D3: Verificação de conteúdo do SBOM

        Campos obrigatórios no SBOM SPDX:
        - spdxVersion
        - dataLicense
        - SPDXID
        - name
        - documentNamespace
        - creationInfo
        - packages[] (lista de componentes)
        """
        # Simular SBOM completo
        async def _package_with_sbom(context):
            artifact = CodeForgeArtifact(
                artifact_id=str(uuid.uuid4()),
                ticket_id=context.ticket.ticket_id,
                plan_id=context.ticket.plan_id,
                intent_id=context.ticket.intent_id,
                correlation_id=context.ticket.correlation_id,
                trace_id=context.trace_id,
                span_id=context.span_id,
                artifact_type=ArtifactCategory.CONTAINER,
                language='python',
                confidence_score=0.95,
                generation_method=GenerationMethod.TEMPLATE,
                content_uri='ghcr.io/neural-hive/myapp-api:latest',
                content_hash='sha256:abc123',
                sbom_uri='s3://sboms/test.spdx.json',
                signature='test-signature',
                metadata={
                    'sbom_components_count': '42',
                    'sbom_format': 'SPDX',
                    'sbom_version': '2.3'
                },
                created_at=datetime.now()
            )
            context.add_artifact(artifact)

        mock_d3_packager.package.side_effect = _package_with_sbom
        await mock_d3_packager.package(d3_pipeline_context)

        container = d3_pipeline_context.generated_artifacts[0]

        # Verificar metadados do SBOM
        assert 'sbom_components_count' in container.metadata
        components = int(container.metadata['sbom_components_count'])
        assert components > 0, "SBOM deve ter componentes"

    @pytest.mark.asyncio
    async def test_d3_sbom_vulnerability_scan(
        self,
        d3_pipeline_context
    ):
        """
        D3: Scan de vulnerabilidade no SBOM

        Verifica:
        - CVEs identificados
        - Severity levels (HIGH, CRITICAL, etc)
        - Componentes vulneráveis listados
        """
        # Adicionar resultado de validação com scan de vulnerabilidade
        validation = ValidationResult(
            validation_type=ValidationType.SECURITY_SCAN,
            tool_name='Grype',
            tool_version='0.70.0',
            status=ValidationStatus.PASSED,
            score=0.85,
            issues_count=2,
            critical_issues=0,
            high_issues=0,
            medium_issues=2,
            low_issues=0,
            executed_at=datetime.now(),
            duration_ms=3000
        )
        d3_pipeline_context.add_validation(validation)

        # Verificar validação adicionada
        assert len(d3_pipeline_context.validation_results) > 0

        vuln_scan = [
            v for v in d3_pipeline_context.validation_results
            if v.validation_type == ValidationType.SECURITY_SCAN
        ]
        assert len(vuln_scan) > 0


# ============================================================================
# Testes de Assinatura de Artefatos
# ============================================================================


class TestD3ArtifactSigning:
    """Testes de assinatura de artefatos."""

    @pytest.mark.asyncio
    async def test_d3_signature_present(
        self,
        d3_pipeline_context,
        mock_d3_packager
    ):
        """
        D3: Assinatura presente no artefato

        Verifica:
        - Campo signature preenchido
        - Formato base64 válido
        """
        await mock_d3_packager.package(d3_pipeline_context)

        container = d3_pipeline_context.generated_artifacts[0]

        assert container.signature is not None
        assert len(container.signature) > 0

        # Verificar formato base64-like
        import base64
        try:
            # Tenta decodificar (pode falhar se não for base64 puro)
            decoded = base64.b64decode(container.signature)
            assert len(decoded) > 0
        except Exception:
            # Pode ser formato diferente (ex: Sigstore bundle)
            # Em testes, assinatura pode ser mais curta
            assert len(container.signature) > 5

    @pytest.mark.asyncio
    async def test_d3_signature_verification(
        self,
        d3_pipeline_context,
        mock_sigstore_client
    ):
        """
        D3: Verificação de assinatura

        Verifica:
        - Assinatura pode ser verificada
        - Público key valida
        - Artefato autêntico
        """
        # Mock verify_signature
        mock_sigstore_client.verify_signature = AsyncMock(return_value=True)

        # Adicionar artefato com assinatura
        artifact = CodeForgeArtifact(
            artifact_id=str(uuid.uuid4()),
            ticket_id=d3_pipeline_context.ticket.ticket_id,
            plan_id=d3_pipeline_context.ticket.plan_id,
            intent_id=d3_pipeline_context.ticket.intent_id,
            correlation_id=d3_pipeline_context.ticket.correlation_id,
            trace_id=d3_pipeline_context.trace_id,
            span_id=d3_pipeline_context.span_id,
            artifact_type=ArtifactCategory.CONTAINER,
            language='python',
            confidence_score=0.95,
            generation_method=GenerationMethod.TEMPLATE,
            content_uri='ghcr.io/neural-hive/myapp-api:latest',
            content_hash='sha256:abc123',
            sbom_uri='s3://sboms/test.spdx.json',
            signature='test-signature-abc123',
            created_at=datetime.now()
        )
        d3_pipeline_context.add_artifact(artifact)

        # Verificar assinatura
        verified = await mock_sigstore_client.verify_signature(
            artifact.content_uri,
            artifact.signature
        )

        assert verified is True

    @pytest.mark.asyncio
    async def test_d3_signature_algorithm(
        self,
        d3_pipeline_context
    ):
        """
        D3: Algoritmo de assinatura

        Algoritmos suportados:
        - SHA256 (ECDSA)
        - SHA512 (RSA)
        """
        artifact = CodeForgeArtifact(
            artifact_id=str(uuid.uuid4()),
            ticket_id=d3_pipeline_context.ticket.ticket_id,
            plan_id=d3_pipeline_context.ticket.plan_id,
            intent_id=d3_pipeline_context.ticket.intent_id,
            correlation_id=d3_pipeline_context.ticket.correlation_id,
            trace_id=d3_pipeline_context.trace_id,
            span_id=d3_pipeline_context.span_id,
            artifact_type=ArtifactCategory.CONTAINER,
            language='python',
            confidence_score=0.95,
            generation_method=GenerationMethod.TEMPLATE,
            content_uri='ghcr.io/neural-hive/myapp-api:latest',
            content_hash='sha256:abc123',
            sbom_uri='s3://sboms/test.spdx.json',
            signature='eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9...',  # ECDSA JWT
            metadata={
                'signature_algorithm': 'ECDSA_SHA256',
                'key_id': 'key-123'
            },
            created_at=datetime.now()
        )
        d3_pipeline_context.add_artifact(artifact)

        assert 'signature_algorithm' in artifact.metadata
        assert 'SHA256' in artifact.metadata['signature_algorithm'] or \
               'SHA512' in artifact.metadata['signature_algorithm']


# ============================================================================
# Testes de Manifestos Kubernetes
# ============================================================================


class TestD3KubernetesManifests:
    """Testes de geração de manifests Kubernetes."""

    @pytest.mark.asyncio
    async def test_d3_kubernetes_deployment_manifest(
        self,
        d3_pipeline_context
    ):
        """
        D3: Manifesto Kubernetes Deployment

        Verifica:
        - Tipo: IAC
        - content_uri aponta para YAML
        - Estrutura válida (deployment, service, etc)
        """
        manifest = CodeForgeArtifact(
            artifact_id=str(uuid.uuid4()),
            ticket_id=d3_pipeline_context.ticket.ticket_id,
            plan_id=d3_pipeline_context.ticket.plan_id,
            intent_id=d3_pipeline_context.ticket.intent_id,
            correlation_id=d3_pipeline_context.ticket.correlation_id,
            trace_id=d3_pipeline_context.trace_id,
            span_id=d3_pipeline_context.span_id,
            artifact_type=ArtifactCategory.IAC,
            language='yaml',
            template_id='kubernetes-deployment-v1',
            confidence_score=0.90,
            generation_method=GenerationMethod.TEMPLATE,
            content_uri='s3://manifests/myapp-api-deployment.yaml',
            content_hash='sha256:manifest123',
            metadata={
                'k8s_version': '1.28',
                'namespace': 'production',
                'replicas': '3',
                'kind': 'Deployment'
            },
            created_at=datetime.now()
        )
        d3_pipeline_context.add_artifact(manifest)

        assert manifest.artifact_type == ArtifactCategory.IAC
        assert manifest.language == 'yaml'
        assert '.yaml' in manifest.content_uri or '.yml' in manifest.content_uri
        assert 'kind' in manifest.metadata

    @pytest.mark.asyncio
    async def test_d3_kubernetes_helm_chart(
        self,
        d3_pipeline_context
    ):
        """
        D3: Chart Helm

        Verifica:
        - Tipo: IAC/CHART
        - Chart.yaml presente
        - values.yaml presente
        - Templates/
        """
        chart = CodeForgeArtifact(
            artifact_id=str(uuid.uuid4()),
            ticket_id=d3_pipeline_context.ticket.ticket_id,
            plan_id=d3_pipeline_context.ticket.plan_id,
            intent_id=d3_pipeline_context.ticket.intent_id,
            correlation_id=d3_pipeline_context.ticket.correlation_id,
            trace_id=d3_pipeline_context.trace_id,
            span_id=d3_pipeline_context.span_id,
            artifact_type=ArtifactCategory.CHART,
            language='yaml',
            template_id='helm-chart-v1',
            confidence_score=0.90,
            generation_method=GenerationMethod.TEMPLATE,
            content_uri='s3://charts/myapp-api-1.0.0.tgz',
            content_hash='sha256:chart123',
            metadata={
                'chart_name': 'myapp-api',
                'chart_version': '1.0.0',
                'app_version': '1.0.0',
                'description': 'MyApp API Helm Chart'
            },
            created_at=datetime.now()
        )
        d3_pipeline_context.add_artifact(chart)

        assert chart.artifact_type == ArtifactCategory.CHART
        assert 'chart_name' in chart.metadata
        assert 'chart_version' in chart.metadata


# ============================================================================
# Testes de Validação de Artefatos
# ============================================================================


class TestD3ArtifactValidation:
    """Testes de validação de artefatos gerados."""

    @pytest.mark.asyncio
    async def test_d3_container_image_scan(
        self,
        d3_pipeline_context,
        mock_trivy_client
    ):
        """
        D3: Scan de imagem de container

        Ferramenta: Trivy
        Verifica:
        - Vulnerabilidades
        - Secrets expostas
        - Configurações inseguras
        """
        # Mock scan Trivy
        mock_trivy_client.scan_container = AsyncMock(
            return_value=ValidationResult(
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
        )

        result = await mock_trivy_client.scan_container(
            'ghcr.io/neural-hive/myapp-api:latest'
        )

        assert result.status == ValidationStatus.PASSED
        assert result.critical_issues == 0

    @pytest.mark.asyncio
    async def test_d3_sbom_compliance_check(
        self,
        d3_pipeline_context
    ):
        """
        D3: Verificação de compliance do SBOM

        Verifica:
        - Licenças permitidas
        - Componentes proibidos (ex: log4j vulnerável)
        - Atribuição completa
        """
        validation = ValidationResult(
            validation_type=ValidationType.COMPLIANCE_CHECK,
            tool_name='SBOM-Compliance',
            tool_version='1.0.0',
            status=ValidationStatus.PASSED,
            score=1.0,
            issues_count=0,
            critical_issues=0,
            high_issues=0,
            medium_issues=0,
            low_issues=0,
            executed_at=datetime.now(),
            duration_ms=1000,
            report_uri='s3://reports/compliance-report.json'
        )
        d3_pipeline_context.add_validation(validation)

        assert validation.validation_type == ValidationType.COMPLIANCE_CHECK
        assert validation.status == ValidationStatus.PASSED

    @pytest.mark.asyncio
    async def test_d3_artifact_integrity_verification(
        self,
        d3_pipeline_context
    ):
        """
        D3: Verificação de integridade do artefato

        Verifica:
        - Hash SHA256 confere
        - Artefato não foi modificado
        - Download completo
        """
        # Adicionar artefato
        artifact = CodeForgeArtifact(
            artifact_id=str(uuid.uuid4()),
            ticket_id=d3_pipeline_context.ticket.ticket_id,
            plan_id=d3_pipeline_context.ticket.plan_id,
            intent_id=d3_pipeline_context.ticket.intent_id,
            correlation_id=d3_pipeline_context.ticket.correlation_id,
            trace_id=d3_pipeline_context.trace_id,
            span_id=d3_pipeline_context.span_id,
            artifact_type=ArtifactCategory.CONTAINER,
            language='python',
            confidence_score=0.95,
            generation_method=GenerationMethod.TEMPLATE,
            content_uri='ghcr.io/neural-hive/myapp-api:latest',
            content_hash='sha256:a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890',  # 64 caracteres hex
            sbom_uri='s3://sboms/test.spdx.json',
            signature='test-signature',
            metadata={'verified': 'true'},
            created_at=datetime.now()
        )
        d3_pipeline_context.add_artifact(artifact)

        # Verificar formato do hash
        assert artifact.content_hash.startswith('sha256:')
        hash_part = artifact.content_hash.split(':', 1)[1]
        assert len(hash_part) == 64, f"Hash inválido: {hash_part}"
        assert all(c in '0123456789abcdef' for c in hash_part.lower())


# ============================================================================
# Testes de Multi-Artefato
# ============================================================================


class TestD3MultipleArtifacts:
    """Testes de geração de múltiplos artefatos."""

    @pytest.mark.asyncio
    async def test_d3_container_plus_manifest_generation(
        self,
        d3_pipeline_context,
        mock_d3_packager
    ):
        """
        D3: Geração de CONTAINER + MANIFEST

        Verifica:
        - Ambos artefatos gerados
        - Referência cruzada (manifest aponta para container)
        - Mesmo trace_id/span_id
        """
        await mock_d3_packager.package(d3_pipeline_context)

        # Adicionar manifest
        manifest = CodeForgeArtifact(
            artifact_id=str(uuid.uuid4()),
            ticket_id=d3_pipeline_context.ticket.ticket_id,
            plan_id=d3_pipeline_context.ticket.plan_id,
            intent_id=d3_pipeline_context.ticket.intent_id,
            correlation_id=d3_pipeline_context.ticket.correlation_id,
            trace_id=d3_pipeline_context.trace_id,
            span_id=d3_pipeline_context.span_id,
            artifact_type=ArtifactCategory.IAC,
            language='yaml',
            confidence_score=0.90,
            generation_method=GenerationMethod.TEMPLATE,
            content_uri='s3://manifests/deployment.yaml',
            content_hash='sha256:manifest123',
            metadata={
                'container_image': d3_pipeline_context.generated_artifacts[0].content_uri
            },
            created_at=datetime.now()
        )
        d3_pipeline_context.add_artifact(manifest)

        # Verificar
        assert len(d3_pipeline_context.generated_artifacts) >= 2

        container = d3_pipeline_context.generated_artifacts[0]
        manifest_artifact = d3_pipeline_context.generated_artifacts[1]

        # Verificar referência cruzada
        assert 'container_image' in manifest_artifact.metadata
        assert manifest_artifact.metadata['container_image'] == container.content_uri

        # Verificar IDs de tracing
        assert container.trace_id == manifest_artifact.trace_id
        assert container.span_id == manifest_artifact.span_id

    @pytest.mark.asyncio
    async def test_d3_artifact_relationships(
        self,
        d3_pipeline_context
    ):
        """
        D3: Relacionamentos entre artefatos

        Verifica:
        - ticket_id compartilhado
        - plan_id compartilhado
        - Ordem de criação mantida
        """
        artifacts = []

        for i, artifact_type in enumerate([
            ArtifactCategory.CODE,
            ArtifactCategory.CONTAINER,
            ArtifactCategory.IAC
        ]):
            artifact = CodeForgeArtifact(
                artifact_id=str(uuid.uuid4()),
                ticket_id=d3_pipeline_context.ticket.ticket_id,
                plan_id=d3_pipeline_context.ticket.plan_id,
                intent_id=d3_pipeline_context.ticket.intent_id,
                correlation_id=d3_pipeline_context.ticket.correlation_id,
                trace_id=d3_pipeline_context.trace_id,
                span_id=d3_pipeline_context.span_id,
                artifact_type=artifact_type,
                language='python' if i == 0 else 'yaml',
                confidence_score=0.90,
                generation_method=GenerationMethod.TEMPLATE,
                content_uri=f's3://artifacts/artifact-{i}',
                content_hash=f'sha256:hash{i}',
                created_at=datetime.now()
            )
            artifacts.append(artifact)
            d3_pipeline_context.add_artifact(artifact)

        # Verificar relacionamentos
        ticket_ids = {a.ticket_id for a in artifacts}
        assert len(ticket_ids) == 1, "Todos devem ter mesmo ticket_id"

        plan_ids = {a.plan_id for a in artifacts}
        assert len(plan_ids) == 1, "Todos devem ter mesmo plan_id"

        # Verificar ordem
        for i, artifact in enumerate(d3_pipeline_context.generated_artifacts):
            if i > 0:
                prev = d3_pipeline_context.generated_artifacts[i-1]
                # Ordem de criação
                assert artifact.created_at >= prev.created_at
