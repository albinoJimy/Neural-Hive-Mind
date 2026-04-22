"""
Testes unitários para ParallelBuilder.

Testes para construções multi-arch de containers em paralelo.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.services.kaniko.parallel_builder import (
    ParallelBuilder,
    ParallelBuildResult,
    ParallelBuildSummary,
    estimate_sequential_duration,
)


class TestParallelBuildResult:
    """Testes para ParallelBuildResult."""

    def test_successful_result(self):
        """Testa resultado de build bem-sucedido."""
        result = ParallelBuildResult(
            platform="linux/amd64",
            success=True,
            image_digest="sha256:abc123",
            image_tag="myimage:latest",
            duration_seconds=120.0,
        )

        assert result.platform == "linux/amd64"
        assert result.success is True
        assert result.image_digest == "sha256:abc123"
        assert result.duration_seconds == 120.0

    def test_failed_result(self):
        """Testa resultado de build falhado."""
        result = ParallelBuildResult(
            platform="linux/arm64",
            success=False,
            duration_seconds=90.0,
            error_message="Build failed: unknown instruction",
        )

        assert result.platform == "linux/arm64"
        assert result.success is False
        assert result.error_message == "Build failed: unknown instruction"


class TestParallelBuildSummary:
    """Testes para ParallelBuildSummary."""

    def test_all_succeeded(self):
        """Testa resumo onde todos os builds sucederam."""
        summary = ParallelBuildSummary(
            platforms_requested=["linux/amd64", "linux/arm64"],
            platforms_succeeded=["linux/amd64", "linux/arm64"],
            platforms_failed={},
            total_duration_seconds=150.0,
            manifest_digest="sha256:manifest123",
        )

        assert summary.success is True
        assert summary.success_rate == 1.0
        assert len(summary.platforms_failed) == 0

    def test_partial_failure(self):
        """Testa resumo com algumas falhas."""
        summary = ParallelBuildSummary(
            platforms_requested=["linux/amd64", "linux/arm64", "linux/arm/v7"],
            platforms_succeeded=["linux/amd64", "linux/arm64"],
            platforms_failed={"linux/arm/v7": "QEMU not available"},
            total_duration_seconds=200.0,
        )

        assert summary.success is False
        assert summary.success_rate == 2.0 / 3.0

    def test_all_failed(self):
        """Testa resumo onde todos os builds falharam."""
        summary = ParallelBuildSummary(
            platforms_requested=["linux/amd64", "linux/arm64"],
            platforms_succeeded=[],
            platforms_failed={
                "linux/amd64": "Network error",
                "linux/arm64": "Timeout",
            },
            total_duration_seconds=300.0,
        )

        assert summary.success is False
        assert summary.success_rate == 0.0


class TestParallelBuilderInitialization:
    """Testes para inicialização do ParallelBuilder."""

    def test_default_initialization(self):
        """Testa inicialização com valores padrão."""
        builder = ParallelBuilder()

        assert builder.max_concurrent_builds == 4
        assert builder.timeout_per_platform == 3600

    def test_custom_initialization(self):
        """Testa inicialização com valores customizados."""
        builder = ParallelBuilder(
            max_concurrent_builds=8,
            timeout_per_platform=7200,
        )

        assert builder.max_concurrent_builds == 8
        assert builder.timeout_per_platform == 7200


class TestBuildSinglePlatform:
    """Testes para _build_single_platform."""

    @pytest.mark.asyncio()
    async def test_build_success(self):
        """Testa build bem-sucedido para uma plataforma."""
        builder = ParallelBuilder()

        # Mock ContainerBuilder
        with patch("src.services.kaniko.parallel_builder.ContainerBuilder") as mock_builder_class:
            mock_builder = MagicMock()
            mock_builder_class.return_value = mock_builder

            # Mock build_container result
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.image_digest = "sha256:test123"
            mock_result.error_message = None
            mock_result.build_logs = ["Step 1/5: FROM alpine"]

            # Mock build_container as async
            async def mock_build(*args, **kwargs):
                return mock_result

            mock_builder.build_container = mock_build

            result = await builder._build_single_platform(
                dockerfile_path="Dockerfile",
                build_context=".",
                image_name="testimage",
                platform="linux/amd64",
                registry=None,
                tag="latest",
                build_args=None,
                cache=False,
                cache_repo=None,
                builder_type="docker",
                namespace="default",
            )

            assert result.success is True
            assert result.platform == "linux/amd64"
            assert result.image_digest == "sha256:test123"

    @pytest.mark.asyncio()
    async def test_build_failure(self):
        """Testa build falhado para uma plataforma."""
        builder = ParallelBuilder()

        with patch("src.services.kaniko.parallel_builder.ContainerBuilder") as mock_builder_class:
            mock_builder = MagicMock()
            mock_builder_class.return_value = mock_builder

            # Mock build_container result
            mock_result = MagicMock()
            mock_result.success = False
            mock_result.error_message = "Build failed"

            async def mock_build(*args, **kwargs):
                return mock_result

            mock_builder.build_container = mock_build

            result = await builder._build_single_platform(
                dockerfile_path="Dockerfile",
                build_context=".",
                image_name="testimage",
                platform="linux/amd64",
                registry=None,
                tag="latest",
                build_args=None,
                cache=False,
                cache_repo=None,
                builder_type="docker",
                namespace="default",
            )

            assert result.success is False
            assert result.error_message == "Build failed"


class TestRunWithConcurrencyLimit:
    """Testes para _run_with_concurrency_limit."""

    @pytest.mark.asyncio()
    async def test_concurrency_limit(self):
        """Testa que limite de concorrência é respeitado."""
        builder = ParallelBuilder(max_concurrent_builds=2)

        # Criar 4 tarefas que demoram um pouco
        executed_count = {"count": 0}
        max_concurrent = {"max": 0}

        async def mock_task():
            executed_count["count"] += 1
            current = executed_count["count"]
            max_concurrent["max"] = max(max_concurrent["max"], current)

            await asyncio.sleep(0.1)
            executed_count["count"] -= 1
            return ParallelBuildResult(
                platform=f"platform-{current}",
                success=True,
            )

        tasks = [mock_task() for _ in range(4)]

        results = await builder._run_with_concurrency_limit(tasks)

        assert len(results) == 4
        # Verificar que no máximo 2 rodaram simultaneamente
        assert max_concurrent["max"] <= 2


class TestCreateManifest:
    """Testes para create_manifest."""

    @pytest.mark.asyncio()
    async def test_create_manifest_docker_success(self):
        """Testa criação de manifest via Docker."""
        builder = ParallelBuilder()

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock manifest create
            mock_create_proc = MagicMock()
            mock_create_proc.returncode = 0
            mock_create_proc.communicate = AsyncMock(return_value=(b"", b""))

            # Mock manifest push
            mock_push_proc = MagicMock()
            mock_push_proc.returncode = 0
            mock_push_output = b"pushed manifest: sha256:abc123def456"
            mock_push_proc.communicate = AsyncMock(return_value=(mock_push_output, b""))

            mock_exec.side_effect = [mock_create_proc, mock_push_proc]

            digest = await builder._create_manifest_docker(
                image_name="testimage",
                platforms=["linux/amd64", "linux/arm64"],
                registry=None,
                tag="latest",
            )

            assert digest is not None

    @pytest.mark.asyncio()
    async def test_create_manifest_kaniko(self):
        """Testa criação de manifest via Kaniko (limitada)."""
        builder = ParallelBuilder()

        digest = await builder._create_manifest_kaniko(
            image_name="testimage",
            platforms=["linux/amd64", "linux/arm64"],
            registry=None,
            tag="latest",
        )

        # Kaniko manifest creation retorna None (não suportado nativamente)
        assert digest is None


class TestCalculateSpeedup:
    """Testes para calculate_speedup."""

    def test_speedup_calculation(self):
        """Testa cálculo de speedup."""
        builder = ParallelBuilder()

        # 2x speedup
        speedup = builder.calculate_speedup(
            parallel_duration=100.0,
            sequential_duration_estimate=200.0,
        )
        assert speedup == 2.0

        # 1.5x speedup
        speedup = builder.calculate_speedup(
            parallel_duration=150.0,
            sequential_duration_estimate=225.0,
        )
        assert speedup == 1.5

    def test_no_speedup(self):
        """Testa quando não há speedup."""
        builder = ParallelBuilder()

        speedup = builder.calculate_speedup(
            parallel_duration=200.0,
            sequential_duration_estimate=200.0,
        )
        assert speedup == 1.0

    def test_slowdown(self):
        """Testa quando paralelo é mais lento (overhead)."""
        builder = ParallelBuilder()

        speedup = builder.calculate_speedup(
            parallel_duration=200.0,
            sequential_duration_estimate=100.0,
        )
        assert speedup == 0.5


class TestEstimateSequentialDuration:
    """Testes para estimate_sequential_duration."""

    def test_single_result(self):
        """Testa estimativa com um único resultado."""
        results = [
            ParallelBuildResult(
                platform="linux/amd64",
                success=True,
                duration_seconds=120.0,
            )
        ]

        estimate = estimate_sequential_duration(results)
        assert estimate == 120.0

    def test_multiple_results(self):
        """Testa estimativa com múltiplos resultados."""
        results = [
            ParallelBuildResult(
                platform="linux/amd64",
                success=True,
                duration_seconds=120.0,
            ),
            ParallelBuildResult(
                platform="linux/arm64",
                success=True,
                duration_seconds=150.0,
            ),
            ParallelBuildResult(
                platform="linux/arm/v7",
                success=False,
                duration_seconds=90.0,
            ),
        ]

        estimate = estimate_sequential_duration(results)
        assert estimate == 360.0  # 120 + 150 + 90


class TestBuildParallelIntegration:
    """Testes de integração para build_parallel."""

    @pytest.mark.asyncio()
    async def test_build_parallel_all_success(self):
        """Testa build paralelo onde todas as plataformas sucedem."""
        builder = ParallelBuilder(max_concurrent_builds=2)

        # Mock _build_single_platform
        async def mock_build_platform(*args, **kwargs):
            platform = kwargs.get("platform") or args[4]
            await asyncio.sleep(0.05)  # Simular tempo de build
            return ParallelBuildResult(
                platform=platform,
                success=True,
                image_digest=f"sha256:{platform.replace('/', '-')}",
                duration_seconds=100.0,
            )

        builder._build_single_platform = mock_build_platform

        # Mock create_manifest
        builder.create_manifest = AsyncMock(return_value="sha256:manifest123")

        summary = await builder.build_parallel(
            dockerfile_path="Dockerfile",
            build_context=".",
            image_name="testimage",
            platforms=["linux/amd64", "linux/arm64", "linux/arm/v7"],
            tag="v1.0",
        )

        assert summary.success is True
        assert len(summary.platforms_succeeded) == 3
        assert len(summary.platforms_failed) == 0
        assert summary.manifest_digest == "sha256:manifest123"

    @pytest.mark.asyncio()
    async def test_build_parallel_partial_failure(self):
        """Testa build paralelo com algumas falhas."""
        builder = ParallelBuilder()

        call_count = {"count": 0}

        async def mock_build_platform(*args, **kwargs):
            call_count["count"] += 1
            platform = kwargs.get("platform", "linux/amd64")

            # Falhar para linux/arm/v7
            if "arm/v7" in platform:
                return ParallelBuildResult(
                    platform=platform,
                    success=False,
                    error_message="QEMU not available",
                    duration_seconds=50.0,
                )

            return ParallelBuildResult(
                platform=platform,
                success=True,
                image_digest=f"sha256:{platform.replace('/', '-')}",
                duration_seconds=100.0,
            )

        builder._build_single_platform = mock_build_platform
        builder.create_manifest = AsyncMock(return_value=None)

        summary = await builder.build_parallel(
            dockerfile_path="Dockerfile",
            build_context=".",
            image_name="testimage",
            platforms=["linux/amd64", "linux/arm64", "linux/arm/v7"],
            tag="v1.0",
        )

        assert summary.success is False
        assert len(summary.platforms_succeeded) == 2
        assert len(summary.platforms_failed) == 1
        assert "linux/arm/v7" in summary.platforms_failed
