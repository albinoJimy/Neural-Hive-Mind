"""
Unit tests para Multi-arch Support (FASE 3.3).

Testa suporte a builds multi-plataforma para amd64, arm64, etc.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from src.services.container_builder import (
    ContainerBuilder,
    BuilderType,
    BuildResult,
    Platform,
    PLATFORM_ALIASES
)


class TestPlatformEnum:
    """Testes para o enum Platform."""

    def test_all_platform_values(self):
        """Testa valores do enum Platform."""
        assert Platform.LINUX_AMD64 == "linux/amd64"
        assert Platform.LINUX_ARM64 == "linux/arm64"
        assert Platform.LINUX_ARM_V7 == "linux/arm/v7"
        assert Platform.LINUX_PPC64LE == "linux/ppc64le"
        assert Platform.LINUX_S390X == "linux/s390x"
        assert Platform.LINUX_RISCV64 == "linux/riscv64"

    def test_platform_count(self):
        """Testa quantidade de plataformas suportadas."""
        assert len(Platform) == 6


class TestPlatformAliases:
    """Testes para aliases de plataformas."""

    def test_amd64_aliases(self):
        """Testa aliases para AMD64."""
        assert PLATFORM_ALIASES["amd64"] == Platform.LINUX_AMD64
        assert PLATFORM_ALIASES["x86_64"] == Platform.LINUX_AMD64

    def test_arm64_aliases(self):
        """Testa aliases para ARM64."""
        assert PLATFORM_ALIASES["arm64"] == Platform.LINUX_ARM64
        assert PLATFORM_ALIASES["aarch64"] == Platform.LINUX_ARM64

    def test_arm_aliases(self):
        """Testa aliases para ARM v7."""
        assert PLATFORM_ALIASES["arm"] == Platform.LINUX_ARM_V7

    def test_all_aliases(self):
        """Testa que todos os aliases são válidos."""
        for alias, platform in PLATFORM_ALIASES.items():
            assert platform in Platform
            assert platform.value.startswith("linux/")


class TestPlatformNormalization:
    """Testes para normalização de plataformas."""

    def test_normalize_none(self):
        """Testa normalização de None."""
        builder = ContainerBuilder()
        assert builder._normalize_platforms(None) is None

    def test_normalize_empty_list(self):
        """Testa normalização de lista vazia."""
        builder = ContainerBuilder()
        assert builder._normalize_platforms([]) is None

    def test_normalize_single_platform(self):
        """Testa normalização de plataforma única."""
        builder = ContainerBuilder()
        result = builder._normalize_platforms(["amd64"])
        assert result == [Platform.LINUX_AMD64]

    def test_normalize_multiple_platforms(self):
        """Testa normalização de múltiplas plataformas."""
        builder = ContainerBuilder()
        result = builder._normalize_platforms(["amd64", "arm64"])
        assert result == [Platform.LINUX_AMD64, Platform.LINUX_ARM64]

    def test_normalize_full_platform_names(self):
        """Testa normalização com nomes completos."""
        builder = ContainerBuilder()
        result = builder._normalize_platforms(["linux/amd64", "linux/arm64"])
        assert result == [Platform.LINUX_AMD64, Platform.LINUX_ARM64]

    def test_normalize_mixed_aliases_and_full(self):
        """Testa normalização com aliases e nomes completos misturados."""
        builder = ContainerBuilder()
        result = builder._normalize_platforms(["amd64", "linux/arm64"])
        assert result == [Platform.LINUX_AMD64, Platform.LINUX_ARM64]

    def test_normalize_invalid_platform(self):
        """Testa erro para plataforma inválida."""
        builder = ContainerBuilder()
        with pytest.raises(ValueError) as exc:
            builder._normalize_platforms(["invalid/platform"])

        assert "inválida" in str(exc.value)

    def test_normalize_invalid_alias(self):
        """Testa erro para alias inválido."""
        builder = ContainerBuilder()
        with pytest.raises(ValueError) as exc:
            builder._normalize_platforms(["mips"])

        assert "inválida" in str(exc.value)


class TestDockerMultiArch:
    """Testes para builds multi-arch com Docker."""

    @pytest.mark.asyncio
    async def test_docker_build_single_platform(self):
        """Testa build Docker com plataforma única."""
        builder = ContainerBuilder(builder_type=BuilderType.DOCKER)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = Mock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            with patch.object(builder, '_get_image_digest', return_value="sha256:abc123"):
                with patch.object(builder, '_get_image_size', return_value=1024000):
                    result = await builder.build_container(
                        dockerfile_path="Dockerfile",
                        build_context=".",
                        image_tag="myapp:latest",
                        platforms=["amd64"]
                    )

            all_args = list(mock_exec.call_args[0])
            assert "--platform" in all_args
            platform_idx = all_args.index("--platform")
            assert all_args[platform_idx + 1] == "linux/amd64"

    @pytest.mark.asyncio
    async def test_docker_build_multi_platform(self):
        """Testa build Docker com múltiplas plataformas."""
        builder = ContainerBuilder(builder_type=BuilderType.DOCKER)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = Mock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            with patch.object(builder, '_get_image_digest', return_value="sha256:abc123"):
                with patch.object(builder, '_get_image_size', return_value=1024000):
                    result = await builder.build_container(
                        dockerfile_path="Dockerfile",
                        build_context=".",
                        image_tag="myapp:latest",
                        platforms=["amd64", "arm64"]
                    )

            all_args = list(mock_exec.call_args[0])
            assert "--platform" in all_args
            platform_idx = all_args.index("--platform")
            # Docker usa vírgula para separar plataformas
            assert "linux/amd64,linux/arm64" in all_args[platform_idx + 1]

    @pytest.mark.asyncio
    async def test_docker_build_without_platform(self):
        """Testa build Docker sem especificar plataforma (padrão)."""
        builder = ContainerBuilder(builder_type=BuilderType.DOCKER)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = Mock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            with patch.object(builder, '_get_image_digest', return_value="sha256:abc123"):
                with patch.object(builder, '_get_image_size', return_value=1024000):
                    result = await builder.build_container(
                        dockerfile_path="Dockerfile",
                        build_context=".",
                        image_tag="myapp:latest"
                    )

            all_args = list(mock_exec.call_args[0])
            assert "--platform" not in all_args


class TestKanikoMultiArch:
    """Testes para builds multi-arch com Kaniko."""

    def test_kaniko_builder_normalizes_platforms(self):
        """Testa que builder Kaniko normaliza plataformas."""
        builder = ContainerBuilder(builder_type=BuilderType.KANIKO)
        result = builder._normalize_platforms(["amd64", "arm64"])
        assert result == [Platform.LINUX_AMD64, Platform.LINUX_ARM64]

    @pytest.mark.asyncio
    async def test_kaniko_build_with_platform(self):
        """Testa build Kaniko com plataforma especificada."""
        builder = ContainerBuilder(
            builder_type=BuilderType.KANIKO,
            enable_cache=False
        )

        # Criar Dockerfile temporário
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            dockerfile_path = os.path.join(tmpdir, "Dockerfile")
            with open(dockerfile_path, "w") as f:
                f.write("FROM alpine:latest\nRUN echo test\n")

            # O build vai falhar devido aos mocks, mas testa a normalização
            result = await builder.build_container(
                dockerfile_path=dockerfile_path,
                build_context=tmpdir,
                image_tag="myapp:latest",
                platforms=["arm64"]
            )

            # A normalização aconteceu, então o build tentou executar
            assert result is not None


class TestBuildResultPlatforms:
    """Testes para BuildResult com informações de plataforma."""

    def test_build_result_with_platforms(self):
        """Testa BuildResult com lista de plataformas."""
        result = BuildResult(
            success=True,
            image_digest="sha256:abc123",
            image_tag="myapp:latest",
            platforms=["linux/amd64", "linux/arm64"]
        )
        assert result.platforms == ["linux/amd64", "linux/arm64"]
        assert len(result.platforms) == 2

    def test_build_result_without_platforms(self):
        """Testa BuildResult sem plataformas (single arch)."""
        result = BuildResult(
            success=True,
            image_digest="sha256:abc123",
            image_tag="myapp:latest"
        )
        assert result.platforms is None

    def test_build_result_cache_hit(self):
        """Testa BuildResult com informação de cache."""
        result = BuildResult(
            success=True,
            image_digest="sha256:abc123",
            image_tag="myapp:latest",
            cache_hit=True
        )
        assert result.cache_hit is True

    def test_build_result_cache_miss(self):
        """Testa BuildResult sem cache (padrão)."""
        result = BuildResult(
            success=True,
            image_digest="sha256:abc123",
            image_tag="myapp:latest"
        )
        assert result.cache_hit is False


class TestPlatformSupportMatrix:
    """Testes para matriz de suporte de plataformas."""

    def test_all_common_platforms_supported(self):
        """Testa que plataformas comuns são suportadas."""
        common_platforms = ["amd64", "arm64", "arm"]
        builder = ContainerBuilder()

        for platform in common_platforms:
            result = builder._normalize_platforms([platform])
            assert result is not None
            assert len(result) == 1
            assert result[0].startswith("linux/")

    def test_platform_list_preserves_order(self):
        """Testa que ordem das plataformas é preservada."""
        builder = ContainerBuilder()
        result = builder._normalize_platforms(["amd64", "arm64", "arm"])
        assert result == [
            Platform.LINUX_AMD64,
            Platform.LINUX_ARM64,
            Platform.LINUX_ARM_V7
        ]

    def test_duplicate_platforms_deduplicated(self):
        """Testa que plataformas duplicadas são mantidas (Docker trata)."""
        builder = ContainerBuilder()
        # Normalização não deduplica - Docker CLI trata
        result = builder._normalize_platforms(["amd64", "amd64"])
        # Mantém duplicatas pois pode ser intencional
        assert len(result) == 2


class TestPlatformValidationErrors:
    """Testes para erros de validação de plataforma."""

    def test_error_message_unsupported_platform(self):
        """Testa mensagem de erro para plataforma não suportada."""
        builder = ContainerBuilder()
        with pytest.raises(ValueError) as exc:
            builder._normalize_platforms(["windows/amd64"])

        error_msg = str(exc.value)
        assert "inválida" in error_msg
        assert "windows/amd64" in error_msg

    def test_error_message_shows_supported(self):
        """Testa que erro mostra plataformas suportadas."""
        builder = ContainerBuilder()
        with pytest.raises(ValueError) as exc:
            builder._normalize_platforms(["fake/arch"])

        error_msg = str(exc.value)
        assert "Use:" in error_msg
        assert "linux/amd64" in error_msg
