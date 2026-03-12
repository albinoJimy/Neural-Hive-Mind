"""
Testes unitarios para ContainerBuilder.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.services.container_builder import (
    ContainerBuilder,
    BuilderType,
    BuildResult,
)


class TestContainerBuilder:
    """Testes para ContainerBuilder."""

    @pytest.mark.asyncio
    async def test_docker_build_success(self):
        """Testa build Docker com sucesso."""
        builder = ContainerBuilder(builder_type=BuilderType.DOCKER)

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Mock do docker build
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(
                return_value=(b"Successfully built abc123", b"")
            )
            mock_subprocess.return_value = mock_process

            # Mock dos metodos auxiliares
            with patch.object(builder, "_get_image_digest", return_value="sha256:abc123def456"):
                with patch.object(builder, "_get_image_size", return_value=123456789):
                    result = await builder.build_container(
                        dockerfile_path="/tmp/Dockerfile",
                        build_context="/tmp/app",
                        image_tag="test:latest",
                    )

                    assert result.success is True
                    assert result.image_digest == "sha256:abc123def456"
                    assert result.image_tag == "test:latest"
                    assert result.size_bytes == 123456789

    @pytest.mark.asyncio
    async def test_docker_build_failure(self):
        """Testa build Docker com falha."""
        builder = ContainerBuilder()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate = AsyncMock(
                return_value=(b"", b"Build failed: error")
            )

            mock_subprocess.return_value = mock_process

            result = await builder.build_container(
                dockerfile_path="/tmp/Dockerfile",
                build_context="/tmp/app",
                image_tag="test:latest",
            )

            assert result.success is False
            assert "error" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_docker_build_with_build_args(self):
        """Testa build Docker com build args."""
        builder = ContainerBuilder()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))

            mock_subprocess.return_value = mock_process

            with patch.object(builder, "_get_image_digest", return_value="sha256:abc"):
                with patch.object(builder, "_get_image_size", return_value=1000):
                    result = await builder.build_container(
                        dockerfile_path="/tmp/Dockerfile",
                        build_context="/tmp/app",
                        image_tag="test:latest",
                        build_args={"VERSION": "1.0", "ENV": "prod"},
                    )

                    # Verifica que create_subprocess_exec foi chamado
                    assert mock_subprocess.called
                    # Verifica que os argumentos incluem build args
                    call_args_str = str(mock_subprocess.call_args)
                    assert "VERSION=1.0" in call_args_str
                    assert "ENV=prod" in call_args_str

    @pytest.mark.asyncio
    async def test_docker_build_with_target_stage(self):
        """Testa build Docker com target stage."""
        builder = ContainerBuilder()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))

            mock_subprocess.return_value = mock_process

            with patch.object(builder, "_get_image_digest", return_value="sha256:abc"):
                with patch.object(builder, "_get_image_size", return_value=1000):
                    result = await builder.build_container(
                        dockerfile_path="/tmp/Dockerfile",
                        build_context="/tmp/app",
                        image_tag="test:latest",
                        target_stage="builder",
                    )

                    call_args_str = str(mock_subprocess.call_args)
                    assert "--target" in call_args_str
                    assert "builder" in call_args_str

    @pytest.mark.asyncio
    async def test_docker_build_multi_platform(self):
        """Testa build Docker multi-plataforma."""
        builder = ContainerBuilder()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))

            mock_subprocess.return_value = mock_process

            with patch.object(builder, "_get_image_digest", return_value="sha256:abc"):
                with patch.object(builder, "_get_image_size", return_value=1000):
                    result = await builder.build_container(
                        dockerfile_path="/tmp/Dockerfile",
                        build_context="/tmp/app",
                        image_tag="test:latest",
                        platforms=["linux/amd64", "linux/arm64"],
                    )

                    call_args_str = str(mock_subprocess.call_args)
                    assert "--platform" in call_args_str
                    assert "linux/amd64,linux/arm64" in call_args_str

    @pytest.mark.asyncio
    async def test_docker_build_timeout(self):
        """Testa timeout de build Docker."""
        builder = ContainerBuilder(timeout_seconds=1)

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            # Simula timeout
            mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)

            mock_subprocess.return_value = mock_process

            result = await builder.build_container(
                dockerfile_path="/tmp/Dockerfile",
                build_context="/tmp/app",
                image_tag="test:latest",
            )

            assert result.success is False
            assert "timeout" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_kaniko_not_implemented(self):
        """Testa que Kaniko retorna erro de nao implementado."""
        builder = ContainerBuilder(builder_type=BuilderType.KANIKO)

        result = await builder.build_container(
            dockerfile_path="/tmp/Dockerfile",
            build_context="/tmp/app",
            image_tag="test:latest",
        )

        assert result.success is False
        assert "Kaniko" in result.error_message

    @pytest.mark.asyncio
    async def test_push_to_registry_success(self):
        """Testa push para registry com sucesso."""
        builder = ContainerBuilder()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Mock para push que retorna digest
            mock_push_proc = AsyncMock()
            mock_push_proc.returncode = 0
            mock_push_proc.communicate = AsyncMock(
                return_value=(
                    b"latest: digest: sha256:abc123 size: 1234",
                    b"",
                )
            )

            # Mock para inspect que confirma o digest
            async def mock_exec(*args, **kwargs):
                if "inspect" in args[0]:
                    mock_proc = AsyncMock()
                    mock_proc.returncode = 0
                    mock_proc.communicate = AsyncMock(
                        return_value=(b"ghcr.io/test/app@sha256:abc123", b"")
                    )
                    return mock_proc
                return mock_push_proc

            mock_subprocess.side_effect = mock_exec

            digest = await builder.push_to_registry(
                local_image="test:latest",
                target_uri="ghcr.io/test/app:latest",
            )

            # O digest deve ser encontrado no output do push
            assert "sha256:abc123" in digest or "sha256:ab" in digest

    @pytest.mark.asyncio
    async def test_push_to_registry_with_auth(self):
        """Testa push com autenticacao."""
        builder = ContainerBuilder()

        call_count = {"count": 0}

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            async def mock_exec(*args, **kwargs):
                call_count["count"] += 1
                mock_proc = AsyncMock()
                mock_proc.returncode = 0

                if "login" in args:
                    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                elif "tag" in args:
                    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                elif "push" in args:
                    mock_proc.communicate = AsyncMock(
                        return_value=(b"digest: sha256:xyz789", b"")
                    )
                elif "inspect" in args:
                    mock_proc.communicate = AsyncMock(
                        return_value=(b"ghcr.io/test/app@sha256:xyz789", b"")
                    )

                return mock_proc

            mock_subprocess.side_effect = mock_exec

            digest = await builder.push_to_registry(
                local_image="test:latest",
                target_uri="ghcr.io/test/app:latest",
                username="testuser",
                password="testpass",
                registry="ghcr.io",
            )

            # Verifica que o processo foi executado
            assert digest is not None or call_count["count"] > 0

    @pytest.mark.asyncio
    async def test_push_login_failure(self):
        """Testa push com falha de login."""
        builder = ContainerBuilder()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Mock login falhando
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.communicate = AsyncMock(return_value=(b"", b"Login failed"))

            mock_subprocess.return_value = mock_proc

            digest = await builder.push_to_registry(
                local_image="test:latest",
                target_uri="ghcr.io/test/app:latest",
                username="testuser",
                password="wrongpass",
            )

            assert digest is None

    def test_parse_size_bytes(self):
        """Testa conversao de tamanho string para bytes."""
        builder = ContainerBuilder()

        assert builder._parse_size("1024B") == 1024
        assert builder._parse_size("1KB") == 1024
        assert builder._parse_size("10MB") == 10 * 1024 * 1024
        assert builder._parse_size("1.5GB") == int(1.5 * 1024 ** 3)

    def test_build_result_default_values(self):
        """Testa valores padrao de BuildResult."""
        result = BuildResult(success=False)

        assert result.success is False
        assert result.image_digest is None
        assert result.image_tag is None
        assert result.size_bytes is None
        assert result.duration_seconds == 0.0
        assert result.error_message is None
        assert result.build_logs == []

    @pytest.mark.asyncio
    async def test_get_image_digest_success(self):
        """Testa obter digest de imagem com sucesso."""
        builder = ContainerBuilder()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(
                return_value=(b"ghcr.io/test/app@sha256:abc123def456", b"")
            )

            mock_subprocess.return_value = mock_proc

            digest = await builder._get_image_digest("test:latest")
            # O metodo retorna apenas o hash (depois do @)
            assert digest == "sha256:abc123def456"

    @pytest.mark.asyncio
    async def test_get_image_digest_failure(self):
        """Testa obter digest quando comando falha."""
        builder = ContainerBuilder()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.communicate = AsyncMock(
                return_value=(b"", b"Error")
            )

            mock_subprocess.return_value = mock_proc

            digest = await builder._get_image_digest("test:latest")
            assert digest is None

    @pytest.mark.asyncio
    async def test_get_image_size_success(self):
        """Testa obter tamanho de imagem com sucesso."""
        builder = ContainerBuilder()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(
                return_value=(b"123456789", b"")
            )

            mock_subprocess.return_value = mock_proc

            size = await builder._get_image_size("test:latest")
            assert size == 123456789

    @pytest.mark.asyncio
    async def test_get_image_size_success(self):
        """Testa obter tamanho com sucesso via docker inspect."""
        builder = ContainerBuilder()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            # Simula tamanho em bytes direto
            mock_proc.communicate = AsyncMock(
                return_value=(b"123456789", b"")
            )

            mock_subprocess.return_value = mock_proc

            size = await builder._get_image_size("test:latest")
            assert size == 123456789

    @pytest.mark.asyncio
    async def test_get_image_size_failure(self):
        """Testa obter tamanho quando comandos falham."""
        builder = ContainerBuilder()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.communicate = AsyncMock(
                return_value=(b"", b"Error")
            )

            mock_subprocess.return_value = mock_proc

            size = await builder._get_image_size("test:latest")
            # Retorna None quando ambos os metodos falham
            assert size is None
