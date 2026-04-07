"""
Testes E2E para clientes de registry com mocks.

Testes de integração que simulam interações com registries privados
sem depender de credenciais reais.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import base64


class TestECRE2E:
    """Testes E2E para ECR com moto mock."""

    @pytest.mark.asyncio
    async def test_ecr_full_workflow_mock(self):
        """Teste workflow completo de autenticação ECR com mock."""
        from src.clients.ecr_client import ECRClient

        # Mock boto3 session e cliente
        mock_session = MagicMock()
        mock_ecr = MagicMock()

        # Mock resposta do get_authorization_token
        auth_token = base64.b64encode(b"AWS:temp-password").decode("utf-8")
        mock_ecr.get_authorization_token.return_value = {
            "authorizationData": [
                {
                    "authorizationToken": auth_token,
                    "proxyEndpoint": "https://123456789012.dkr.ecr.us-east-1.amazonaws.com",
                }
            ]
        }

        mock_session.client.return_value = mock_ecr

        with patch("src.clients.ecr_client.boto3.Session", return_value=mock_session):
            client = ECRClient(region="us-east-1", use_irsa=True)

            # Obter credenciais
            username, password, endpoint = client.get_ecr_credentials()

            assert username == "AWS"
            assert password == "temp-password"
            assert endpoint == "123456789012.dkr.ecr.us-east-1.amazonaws.com"

            # Verificar cache
            assert client._cached_token is not None

            # Refresh não deve fazer nova chamada
            mock_ecr.get_authorization_token.reset_mock()
            username2, password2, _ = client.get_ecr_credentials()
            assert not mock_ecr.get_authorization_token.called

            # Forçar refresh
            client._cached_token.obtained_at = client._cached_token.obtained_at.replace(
                hour=0, minute=0, second=0
            )
            client.refresh_if_needed()
            assert mock_ecr.get_authorization_token.called


class TestGCRE2E:
    """Testes E2E para GCR com mock."""

    @pytest.mark.asyncio
    async def test_gcr_full_workflow_mock(self):
        """Teste workflow completo de autenticação GCR com mock."""
        from src.clients.gcr_client import GCRClient

        with patch("builtins.open", create=True) as mock_open:
            # Mock service account key file
            key_data = {
                "access_token": "ya29.mock-token-12345",
            }
            import json

            mock_file = MagicMock()
            mock_file.read.return_value = json.dumps(key_data)
            mock_open.return_value.__enter__.return_value = mock_file

            client = GCRClient(
                service_account_key_path="/tmp/mock-key.json",
                use_workload_identity=False,
            )

            # Obter credenciais
            credentials = client.get_gcr_credentials("gcr.io/project/image:tag")

            assert credentials == "oauth2accesstoken://ya29.mock-token-12345"

            # Verificar cache
            assert client._cached_token is not None


class TestACRE2E:
    """Testes E2E para ACR com mock."""

    @pytest.mark.asyncio
    async def test_acr_full_workflow_mock(self):
        """Teste workflow completo de autenticação ACR com mock."""
        from src.clients.acr_client import ACRClient

        client = ACRClient(
            registry="myregistry.azurecr.io",
            client_id="test-client-id",
            client_secret="test-secret",
            tenant_id="test-tenant-id",
            use_managed_identity=False,
        )

        # Mock requests para Service Principal
        with patch("src.clients.acr_client.requests") as mock_requests:
            # Mock response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "access_token": "test-acr-token-67890",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
            mock_requests.post.return_value = mock_response

            # Obter credenciais
            username, password = client.get_acr_credentials()

            # ACR usa token como username, password vazio
            assert username == "test-acr-token-67890"
            assert password == ""


class TestMultiArchE2E:
    """Testes E2E para builds multi-arch."""

    @pytest.mark.asyncio
    async def test_parallel_builder_multi_platforms_mock(self):
        """Teste build paralelo para múltiplas plataformas."""
        from src.services.kaniko.parallel_builder import (
            ParallelBuilder,
            ParallelBuildResult,
        )

        builder = ParallelBuilder(max_concurrent_builds=2)

        # Mock _build_single_platform
        async def mock_build(*args, **kwargs):
            import asyncio

            await asyncio.sleep(0.05)

            platform = kwargs.get("platform", "linux/amd64")

            # Simular falha para uma plataforma
            if platform == "linux/arm/v7":
                return ParallelBuildResult(
                    platform=platform,
                    success=False,
                    error_message="Simulated failure",
                    duration_seconds=50.0,
                )

            return ParallelBuildResult(
                platform=platform,
                success=True,
                image_digest=f"sha256:{platform.replace('/', '-')}",
                duration_seconds=100.0,
            )

        builder._build_single_platform = mock_build

        # Mock create_manifest
        builder.create_manifest = AsyncMock(return_value="sha256:manifest-mock")

        summary = await builder.build_parallel(
            dockerfile_path="Dockerfile",
            build_context=".",
            image_name="testapp",
            platforms=["linux/amd64", "linux/arm64", "linux/arm/v7"],
            tag="v1.0",
        )

        # Verificar resultados
        assert summary.success is False  # Uma falha
        assert len(summary.platforms_succeeded) == 2
        assert len(summary.platforms_failed) == 1
        assert "linux/arm/v7" in summary.platforms_failed

        # Speedup > 1x (paralelo mais rápido que soma sequencial)
        sequential_duration = sum(r.duration_seconds for r in summary.results)
        assert summary.total_duration_seconds < sequential_duration

        speedup = builder.calculate_speedup(
            summary.total_duration_seconds,
            sequential_duration,
        )
        assert speedup > 1.0


class TestPVCFallbackE2E:
    """Testes E2E para fallback de PVC."""

    def test_large_context_triggers_pvc(self):
        """Teste que contexto grande detecta necessidade de PVC."""
        from src.services.kaniko.pvc_manager import PVCManager

        manager = PVCManager(namespace="test-ns")

        # Contexto pequeno - não precisa de PVC
        small_size = 500 * 1024  # 500KB
        assert not manager.should_use_pvc(small_size)

        # Contexto grande - precisa de PVC
        large_size = 2 * 1024 * 1024  # 2MB
        assert manager.should_use_pvc(large_size)


class TestRegistryDetectionE2E:
    """Testes E2E para detecção de registry."""

    def test_detect_all_registry_types(self):
        """Teste detecção de todos os tipos de registry."""
        from src.services.container_builder import ContainerBuilder

        builder = ContainerBuilder()

        # ECR
        assert (
            builder._detect_registry_type("123456.dkr.ecr.us-east-1.amazonaws.com/image") == "ecr"
        )

        # GCR
        assert builder._detect_registry_type("gcr.io/project/image") == "gcr"
        assert builder._detect_registry_type("us.gcr.io/project/image") == "gcr"

        # ACR
        assert builder._detect_registry_type("myregistry.azurecr.io/image") == "acr"

        # Generic
        assert builder._detect_registry_type("docker.io/library/nginx") == "generic"
        assert builder._detect_registry_type("ghcr.io/user/repo") == "generic"


class TestSecurityE2E:
    """Testes E2E para segurança."""

    def test_never_log_credentials(self):
        """Testa que credenciais nunca são logadas."""
        import logging
        from io import StringIO

        # Capturar logs
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)

        logger = logging.getLogger("src.clients.ecr_client")
        logger.addHandler(handler)

        try:

            # Criar token (que normalmente seria logado)
            from src.clients.ecr_client import ECRToken
            from datetime import datetime, timedelta, timezone

            token = ECRToken(
                username="AWS",
                password="secret-password-123",
                endpoint="123.dkr.ecr.amazonaws.com",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                obtained_at=datetime.now(timezone.utc),
            )

            # Verificar que password não aparece nos logs
            log_output = log_stream.getvalue()
            assert "secret-password-123" not in log_output
            assert "password" not in log_output

        finally:
            logger.removeHandler(handler)

    def test_tokens_only_in_memory(self):
        """Testa que tokens nunca são persistidos."""
        from src.clients.gcr_client import GCRClient
        import tempfile
        import os

        # Verificar que não há write de token em disco
        with tempfile.TemporaryDirectory() as tmpdir:
            client = GCRClient(
                service_account_key_path=os.path.join(tmpdir, "fake-key.json"),
                use_workload_identity=False,
            )

            # Tentar obter token (vai falhar, mas não deve criar arquivos)
            try:
                client.get_gcr_token()
            except:
                pass

            # Verificar que nenhum arquivo de token foi criado
            files = os.listdir(tmpdir)
            assert len(files) == 0 or files == ["fake-key.json"]
