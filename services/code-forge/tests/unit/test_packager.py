"""
Testes unitarios para Packager.

Cobertura:
- Empacotamento de artefatos
- Geracao de SBOM
- Assinatura via Sigstore
- Upload S3 e verificacao de integridade
- Registro no Artifact Registry
- Retry logic
"""

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPackagerSBOMGeneration:
    """Testes de geracao de SBOM."""

    @pytest.mark.asyncio
    async def test_package_generates_sbom(
        self,
        mock_sigstore_client,
        sample_pipeline_context_with_artifacts
    ):
        """Deve gerar SBOM para cada artefato."""
        from services.code_forge.src.services.packager import Packager

        packager = Packager(
            sigstore_client=mock_sigstore_client,
            s3_artifact_client=None,
            artifact_registry_client=None
        )

        await packager.package(sample_pipeline_context_with_artifacts)

        mock_sigstore_client.generate_sbom.assert_called_once()
        artifact = sample_pipeline_context_with_artifacts.generated_artifacts[0]
        assert artifact.sbom_uri is not None

    @pytest.mark.asyncio
    async def test_package_multiple_artifacts(
        self,
        mock_sigstore_client,
        sample_pipeline_context_with_artifacts
    ):
        """Deve processar multiplos artefatos."""
        from services.code_forge.src.services.packager import Packager
        from services.code_forge.src.models.artifact import (
            CodeForgeArtifact, ArtifactType, GenerationMethod
        )

        # Adicionar segundo artefato
        artifact2 = CodeForgeArtifact(
            artifact_id=str(uuid.uuid4()),
            ticket_id=sample_pipeline_context_with_artifacts.ticket.ticket_id,
            correlation_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            artifact_type=ArtifactType.DOCUMENTATION,
            language='markdown',
            template_id='docs-v1',
            confidence_score=0.9,
            generation_method=GenerationMethod.TEMPLATE,
            content_uri='mongodb://artifacts/test-456',
            content_hash='def456',
            created_at=datetime.now(),
            metadata={}
        )
        sample_pipeline_context_with_artifacts.add_artifact(artifact2)

        packager = Packager(
            sigstore_client=mock_sigstore_client,
            s3_artifact_client=None,
            artifact_registry_client=None
        )

        await packager.package(sample_pipeline_context_with_artifacts)

        assert mock_sigstore_client.generate_sbom.call_count == 2


class TestPackagerSignature:
    """Testes de assinatura de artefatos."""

    @pytest.mark.asyncio
    async def test_package_signs_artifact(
        self,
        mock_sigstore_client,
        sample_pipeline_context_with_artifacts
    ):
        """Deve assinar cada artefato."""
        from services.code_forge.src.services.packager import Packager

        packager = Packager(
            sigstore_client=mock_sigstore_client,
            s3_artifact_client=None,
            artifact_registry_client=None
        )

        await packager.package(sample_pipeline_context_with_artifacts)

        mock_sigstore_client.sign_artifact.assert_called_once()
        artifact = sample_pipeline_context_with_artifacts.generated_artifacts[0]
        assert artifact.signature is not None


class TestPackagerS3Integration:
    """Testes de integracao com S3."""

    @pytest.mark.asyncio
    async def test_package_verifies_s3_integrity(
        self,
        mock_sigstore_client,
        mock_s3_client,
        sample_pipeline_context_with_artifacts
    ):
        """Deve verificar integridade do SBOM no S3."""
        from services.code_forge.src.services.packager import Packager

        mock_sigstore_client.generate_sbom.return_value = 's3://code-forge/sboms/test.json'

        packager = Packager(
            sigstore_client=mock_sigstore_client,
            s3_artifact_client=mock_s3_client,
            artifact_registry_client=None
        )

        await packager.package(sample_pipeline_context_with_artifacts)

        mock_s3_client.verify_sbom_integrity.assert_called_once_with(
            's3://code-forge/sboms/test.json'
        )

    @pytest.mark.asyncio
    async def test_package_skips_s3_for_non_s3_uri(
        self,
        mock_sigstore_client,
        mock_s3_client,
        sample_pipeline_context_with_artifacts
    ):
        """Deve pular verificacao S3 para URIs nao-S3."""
        from services.code_forge.src.services.packager import Packager

        mock_sigstore_client.generate_sbom.return_value = 'file:///local/sbom.json'

        packager = Packager(
            sigstore_client=mock_sigstore_client,
            s3_artifact_client=mock_s3_client,
            artifact_registry_client=None
        )

        await packager.package(sample_pipeline_context_with_artifacts)

        mock_s3_client.verify_sbom_integrity.assert_not_called()


class TestPackagerIntegrityRetry:
    """Testes de retry de verificacao de integridade."""

    @pytest.mark.asyncio
    async def test_retry_on_integrity_failure(
        self,
        mock_sigstore_client,
        mock_s3_client,
        sample_pipeline_context_with_artifacts
    ):
        """Deve fazer retry quando integridade falha."""
        from services.code_forge.src.services.packager import Packager

        mock_sigstore_client.generate_sbom.return_value = 's3://code-forge/sboms/test.json'
        # Primeira verificacao falha, segunda sucede
        mock_s3_client.verify_sbom_integrity.side_effect = [False, True]

        packager = Packager(
            sigstore_client=mock_sigstore_client,
            s3_artifact_client=mock_s3_client,
            artifact_registry_client=None
        )

        await packager.package(sample_pipeline_context_with_artifacts)

        # Deve re-gerar SBOM apos falha
        assert mock_sigstore_client.generate_sbom.call_count == 2

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(
        self,
        mock_sigstore_client,
        mock_s3_client,
        sample_pipeline_context_with_artifacts
    ):
        """Deve parar apos max_retries."""
        from services.code_forge.src.services.packager import Packager

        mock_sigstore_client.generate_sbom.return_value = 's3://code-forge/sboms/test.json'
        mock_s3_client.verify_sbom_integrity.return_value = False  # Sempre falha

        packager = Packager(
            sigstore_client=mock_sigstore_client,
            s3_artifact_client=mock_s3_client,
            artifact_registry_client=None
        )

        await packager.package(sample_pipeline_context_with_artifacts)

        # 1 inicial + 1 retry = 2 calls
        assert mock_sigstore_client.generate_sbom.call_count == 2


class TestPackagerArtifactRegistry:
    """Testes de integracao com Artifact Registry."""

    @pytest.mark.asyncio
    async def test_registers_sbom_in_artifact_registry(
        self,
        mock_sigstore_client,
        mock_s3_client,
        mock_artifact_registry_client,
        sample_pipeline_context_with_artifacts
    ):
        """Deve registrar SBOM no Artifact Registry."""
        from services.code_forge.src.services.packager import Packager

        mock_sigstore_client.generate_sbom.return_value = 's3://code-forge/sboms/test.json'

        packager = Packager(
            sigstore_client=mock_sigstore_client,
            s3_artifact_client=mock_s3_client,
            artifact_registry_client=mock_artifact_registry_client
        )

        await packager.package(sample_pipeline_context_with_artifacts)

        mock_artifact_registry_client.register_sbom.assert_called_once()
        artifact = sample_pipeline_context_with_artifacts.generated_artifacts[0]
        assert artifact.registry_reference is not None

    @pytest.mark.asyncio
    async def test_skips_registry_for_non_s3_uri(
        self,
        mock_sigstore_client,
        mock_artifact_registry_client,
        sample_pipeline_context_with_artifacts
    ):
        """Deve pular registro para URIs nao-S3."""
        from services.code_forge.src.services.packager import Packager

        mock_sigstore_client.generate_sbom.return_value = 'file:///local/sbom.json'

        packager = Packager(
            sigstore_client=mock_sigstore_client,
            s3_artifact_client=None,
            artifact_registry_client=mock_artifact_registry_client
        )

        await packager.package(sample_pipeline_context_with_artifacts)

        mock_artifact_registry_client.register_sbom.assert_not_called()


class TestPackagerMetadata:
    """Testes de metadata passada para clientes."""

    @pytest.mark.asyncio
    async def test_passes_ticket_id_to_sbom(
        self,
        mock_sigstore_client,
        sample_pipeline_context_with_artifacts
    ):
        """Deve passar ticket_id para geracao de SBOM."""
        from services.code_forge.src.services.packager import Packager

        packager = Packager(
            sigstore_client=mock_sigstore_client,
            s3_artifact_client=None,
            artifact_registry_client=None
        )

        await packager.package(sample_pipeline_context_with_artifacts)

        call_kwargs = mock_sigstore_client.generate_sbom.call_args[1]
        assert 'ticket_id' in call_kwargs

    @pytest.mark.asyncio
    async def test_passes_artifact_id_to_sbom(
        self,
        mock_sigstore_client,
        sample_pipeline_context_with_artifacts
    ):
        """Deve passar artifact_id para geracao de SBOM."""
        from services.code_forge.src.services.packager import Packager

        packager = Packager(
            sigstore_client=mock_sigstore_client,
            s3_artifact_client=None,
            artifact_registry_client=None
        )

        await packager.package(sample_pipeline_context_with_artifacts)

        call_kwargs = mock_sigstore_client.generate_sbom.call_args[1]
        assert 'artifact_id' in call_kwargs
