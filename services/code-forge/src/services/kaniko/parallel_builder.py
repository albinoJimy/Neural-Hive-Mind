"""
Builder paralelo para construções multi-arch de containers.

Permite construir imagens para múltiplas arquiteturas simultaneamente,
usando asyncio para executar builds em paralelo e criar um manifest
multi-arch no final.
"""

import asyncio
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class ParallelBuildResult:
    """Resultado de um build paralelo para uma plataforma específica."""

    platform: str
    success: bool
    image_digest: str | None = None
    image_tag: str | None = None
    duration_seconds: float = 0.0
    error_message: str | None = None
    build_logs: list[str] = field(default_factory=list)


@dataclass
class ParallelBuildSummary:
    """Resumo de um build paralelo multi-arch."""

    platforms_requested: list[str]
    platforms_succeeded: list[str]
    platforms_failed: dict[str, str]  # platform -> error message
    total_duration_seconds: float
    manifest_digest: str | None = None
    results: list[ParallelBuildResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Retorna True se todos os builds sucederam."""
        return len(self.platforms_failed) == 0 and len(self.platforms_succeeded) > 0

    @property
    def success_rate(self) -> float:
        """Retorna taxa de sucesso (0.0 a 1.0)."""
        total = len(self.platforms_requested)
        if total == 0:
            return 0.0
        return len(self.platforms_succeeded) / total


class ParallelBuilder:
    """
    Builder para construções multi-arch em paralelo.

    Executa builds para múltiplas plataformas simultaneamente
    e cria um manifest multi-arch no final.

    Exemplo:
        builder = ParallelBuilder()
        summary = await builder.build_parallel(
            dockerfile_path="Dockerfile",
            build_context=".",
            image_name="myapp",
            platforms=["linux/amd64", "linux/arm64"],
            registry="myregistry.com"
        )
    """

    def __init__(
        self,
        max_concurrent_builds: int = 4,
        timeout_per_platform: int = 3600,
    ):
        """
        Inicializa o ParallelBuilder.

        Args:
            max_concurrent_builds: Máximo de builds simultâneos
            timeout_per_platform: Timeout em segundos por plataforma
        """
        self.max_concurrent_builds = max_concurrent_builds
        self.timeout_per_platform = timeout_per_platform

    async def build_parallel(
        self,
        dockerfile_path: str,
        build_context: str,
        image_name: str,
        platforms: list[str],
        registry: str | None = None,
        tag: str = "latest",
        build_args: dict[str, str] | None = None,
        cache: bool = False,
        cache_repo: str | None = None,
        builder_type: str = "docker",  # "docker" ou "kaniko"
        namespace: str = "default",
    ) -> ParallelBuildSummary:
        """
        Executa builds em paralelo para múltiplas plataformas.

        Args:
            dockerfile_path: Caminho para o Dockerfile
            build_context: Diretório do contexto de build
            image_name: Nome base da imagem
            platforms: Lista de plataformas (ex: ["linux/amd64", "linux/arm64"])
            registry: Registry de destino (opcional)
            tag: Tag da imagem
            build_args: Argumentos de build
            cache: Habilitar cache
            cache_repo: Repositório de cache
            builder_type: Tipo de builder ("docker" ou "kaniko")
            namespace: Namespace Kubernetes (para Kaniko)

        Returns:
            ParallelBuildSummary com resultados de todos os builds
        """
        start_time = asyncio.get_event_loop().time()

        logger.info(
            "parallel_build_started",
            image_name=image_name,
            platforms=platforms,
            count=len(platforms),
        )

        # Criar tarefas de build para cada plataforma
        tasks = []
        for platform in platforms:
            task = self._build_single_platform(
                dockerfile_path=dockerfile_path,
                build_context=build_context,
                image_name=image_name,
                platform=platform,
                registry=registry,
                tag=tag,
                build_args=build_args,
                cache=cache,
                cache_repo=cache_repo,
                builder_type=builder_type,
                namespace=namespace,
            )
            tasks.append(task)

        # Executar builds em paralelo com limite de concorrência
        results = await self._run_with_concurrency_limit(tasks)

        # Analisar resultados
        succeeded = []
        failed = {}
        for result in results:
            if result.success:
                succeeded.append(result.platform)
            else:
                failed[result.platform] = result.error_message or "Unknown error"

        total_duration = (asyncio.get_event_loop().time() - start_time) / 1000.0

        # Criar manifest multi-arch se mais de uma plataforma sucedeu
        manifest_digest = None
        if len(succeeded) > 1:
            manifest_digest = await self.create_manifest(
                image_name=image_name,
                platforms=succeeded,
                registry=registry,
                tag=tag,
                builder_type=builder_type,
            )
        elif len(succeeded) == 1:
            # Se só uma plataforma, usar a digest dela
            for result in results:
                if result.success:
                    manifest_digest = result.image_digest

        summary = ParallelBuildSummary(
            platforms_requested=platforms,
            platforms_succeeded=succeeded,
            platforms_failed=failed,
            total_duration_seconds=total_duration,
            manifest_digest=manifest_digest,
            results=results,
        )

        logger.info(
            "parallel_build_completed",
            success=summary.success,
            succeeded=len(succeeded),
            failed=len(failed),
            duration_seconds=total_duration,
            manifest_digest=manifest_digest,
        )

        return summary

    async def _build_single_platform(
        self,
        dockerfile_path: str,
        build_context: str,
        image_name: str,
        platform: str,
        registry: str | None,
        tag: str,
        build_args: dict[str, str] | None,
        cache: bool,
        cache_repo: str | None,
        builder_type: str,
        namespace: str,
    ) -> ParallelBuildResult:
        """
        Executa build para uma única plataforma.

        Args:
            Todos os parâmetros de build_parallel

        Returns:
            ParallelBuildResult para a plataforma
        """
        start_time = asyncio.get_event_loop().time()

        logger.info("platform_build_started", platform=platform, image=image_name)

        try:
            # Importar ContainerBuilder dinamicamente para evitar import circular
            from ..container_builder import BuilderType, ContainerBuilder

            builder = ContainerBuilder(
                builder_type=BuilderType.KANIKO if builder_type == "kaniko" else BuilderType.DOCKER,
            )

            # Construir tag específica para a plataforma
            platform_suffix = platform.replace("/", "-")
            platform_tag = f"{tag}-{platform_suffix}"

            # Registry + imagem + tag
            full_image = f"{image_name}:{platform_tag}"
            if registry:
                full_image = f"{registry}/{image_name}:{platform_tag}"

            # Executar build
            build_result = await builder.build_container(
                dockerfile_path=dockerfile_path,
                build_context=build_context,
                image_tag=full_image,
                platforms=[platform],
                build_args=build_args,
                enable_cache=cache,
                cache_repo=cache_repo,
            )

            duration = (asyncio.get_event_loop().time() - start_time) / 1000.0

            if build_result.success:
                logger.info(
                    "platform_build_success",
                    platform=platform,
                    digest=build_result.image_digest,
                    duration_seconds=duration,
                )
                return ParallelBuildResult(
                    platform=platform,
                    success=True,
                    image_digest=build_result.image_digest,
                    image_tag=full_image,
                    duration_seconds=duration,
                    build_logs=build_result.build_logs,
                )
            logger.warning(
                "platform_build_failed",
                platform=platform,
                error=build_result.error_message,
            )
            return ParallelBuildResult(
                platform=platform,
                success=False,
                duration_seconds=duration,
                error_message=build_result.error_message,
                build_logs=build_result.build_logs,
            )

        except Exception as e:
            duration = (asyncio.get_event_loop().time() - start_time) / 1000.0
            logger.error(
                "platform_build_exception",
                platform=platform,
                error=str(e),
            )
            return ParallelBuildResult(
                platform=platform,
                success=False,
                duration_seconds=duration,
                error_message=str(e),
            )

    async def _run_with_concurrency_limit(
        self, tasks: list[asyncio.Task]
    ) -> list[ParallelBuildResult]:
        """
        Executa tarefas com limite de concorrência.

        Args:
            tasks: Lista de tarefas async

        Returns:
            Lista de resultados
        """
        semaphore = asyncio.Semaphore(self.max_concurrent_builds)

        async def bounded_task(task):
            async with semaphore:
                return await task

        results = await asyncio.gather(
            *[bounded_task(task) for task in tasks],
            return_exceptions=True,
        )

        # Converter exceções em resultados de falha
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(
                    ParallelBuildResult(
                        platform=f"platform-{i}",
                        success=False,
                        error_message=str(result),
                    )
                )
            else:
                processed_results.append(result)

        return processed_results

    async def create_manifest(
        self,
        image_name: str,
        platforms: list[str],
        registry: str | None,
        tag: str,
        builder_type: str,
    ) -> str | None:
        """
        Cria um manifest multi-arch para as plataformas especificadas.

        Args:
            image_name: Nome base da imagem
            platforms: Lista de plataformas que foram buildadas com sucesso
            registry: Registry de destino
            tag: Tag do manifest
            builder_type: Tipo de builder para criar manifest

        Returns:
            Digest do manifest ou None
        """
        logger.info(
            "manifest_creation_started",
            image=image_name,
            platforms=platforms,
        )

        try:
            if builder_type == "kaniko":
                # Kaniko: usar pod com manifest tool
                return await self._create_manifest_kaniko(
                    image_name=image_name,
                    platforms=platforms,
                    registry=registry,
                    tag=tag,
                )
            # Docker: usar docker manifest
            return await self._create_manifest_docker(
                image_name=image_name,
                platforms=platforms,
                registry=registry,
                tag=tag,
            )

        except Exception as e:
            logger.error("manifest_creation_failed", error=str(e))
            return None

    async def _create_manifest_docker(
        self,
        image_name: str,
        platforms: list[str],
        registry: str | None,
        tag: str,
    ) -> str | None:
        """Cria manifest usando Docker CLI."""
        manifest_name = f"{image_name}:{tag}"
        if registry:
            manifest_name = f"{registry}/{manifest_name}"

        # Criar manifest
        create_cmd = ["docker", "manifest", "create", manifest_name]

        for platform in platforms:
            platform_suffix = platform.replace("/", "-")
            platform_image = f"{image_name}:{tag}-{platform_suffix}"
            if registry:
                platform_image = f"{registry}/{platform_image}"
            create_cmd.append(platform_image)

        proc = await asyncio.create_subprocess_exec(
            *create_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        if proc.returncode != 0:
            logger.error("docker_manifest_create_failed")
            return None

        # Push manifest
        push_cmd = ["docker", "manifest", "push", manifest_name]
        proc = await asyncio.create_subprocess_exec(
            *push_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            output = stdout.decode() + stderr.decode()
            # Tentar extrair digest
            for line in output.splitlines():
                if "sha256:" in line:
                    parts = line.split("sha256:")
                    if len(parts) > 1:
                        digest = f"sha256:{parts[1][:64]}"
                        logger.info("docker_manifest_pushed", digest=digest)
                        return digest

        return None

    async def _create_manifest_kaniko(
        self,
        image_name: str,
        platforms: list[str],
        registry: str | None,
        tag: str,
    ) -> str | None:
        """
        Cria manifest usando Kaniko / manifest tool.

        Nota: Kaniko executor não cria manifests nativamente.
        Esta é uma implementação simplificada que retorna o digest da primeira imagem.
        Para produção, considere usar docker manifest ou uma ferramenta dedicada.
        """
        logger.warning(
            "kaniko_manifest_not_fully_supported",
            note="Using first platform digest as manifest digest",
        )

        # Retornar digest da primeira plataforma
        # Em produção, você pode usar:
        # - docker manifest (se docker disponível)
        # - manifest-tool (https://github.com/estesp/manifest-tool)
        # - buildx com docker-container driver
        return None

    def calculate_speedup(
        self,
        parallel_duration: float,
        sequential_duration_estimate: float,
    ) -> float:
        """
        Calcula o speedup do build paralelo.

        Args:
            parallel_duration: Duração do build paralelo
            sequential_duration_estimate: Estimativa de duração sequencial

        Returns:
            Speedup (1.0 = mesmo tempo, >1.0 = mais rápido)
        """
        if parallel_duration <= 0:
            return 0.0
        if sequential_duration_estimate <= 0:
            return 0.0

        return sequential_duration_estimate / parallel_duration


def estimate_sequential_duration(
    results: list[ParallelBuildResult],
) -> float:
    """
    Estima duração que o build sequencial levaria.

    Args:
        results: Lista de resultados do build paralelo

    Returns:
    Estimativa de duração em segundos (soma das durações individuais)
    """
    return sum(r.duration_seconds for r in results)
