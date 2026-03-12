"""
Executor de builds de container usando Docker ou Kaniko.

Suporta:
- Docker CLI para builds locais
- Build com argumentos customizados
- Multi-arch builds
- Push para registries com autenticação
"""

import asyncio
import subprocess
import json
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum
import structlog


logger = structlog.get_logger()


class BuilderType(str, Enum):
    """Tipos de builder suportados."""
    DOCKER = "docker"
    KANIKO = "kaniko"


@dataclass
class BuildResult:
    """Resultado de uma operacao de build."""
    success: bool
    image_digest: Optional[str] = None
    image_tag: Optional[str] = None
    size_bytes: Optional[int] = None
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
    build_logs: List[str] = field(default_factory=list)


class ContainerBuilder:
    """
    Executa builds de container usando Docker ou Kaniko.

    Features:
    - Docker CLI para builds locais
    - Suporte a build args
    - Multi-stage builds
    - Multi-arch builds
    - Push para registries
    - BuildKit cache distribuído
    """

    def __init__(
        self,
        builder_type: BuilderType = BuilderType.DOCKER,
        timeout_seconds: int = 3600,
        enable_cache: bool = False,
        cache_repo: Optional[str] = None,
    ):
        """
        Inicializa o ContainerBuilder.

        Args:
            builder_type: Tipo de builder (DOCKER ou KANIKO)
            timeout_seconds: Timeout para builds em segundos
            enable_cache: Habilita cache distribuído
            cache_repo: Repositório de cache (ex: ghcr.io/user/cache)
        """
        self.builder_type = builder_type
        self.timeout_seconds = timeout_seconds
        self.enable_cache = enable_cache
        self.cache_repo = cache_repo

    async def build_container(
        self,
        dockerfile_path: str,
        build_context: str,
        image_tag: str,
        build_args: Optional[dict] = None,
        target_stage: Optional[str] = None,
        platforms: Optional[List[str]] = None,
        enable_cache: Optional[bool] = None,
        cache_repo: Optional[str] = None,
    ) -> BuildResult:
        """
        Executa o build de uma imagem de container.

        Args:
            dockerfile_path: Caminho para o Dockerfile
            build_context: Diretorio de contexto do build
            image_tag: Tag para a imagem resultante
            build_args: Argumentos de build (--build-arg)
            target_stage: Stage alvo em multi-stage build
            platforms: Lista de plataformas para multi-arch (ex: ["linux/amd64", "linux/arm64"])
            enable_cache: Sobrescreve cache do builder (opcional)
            cache_repo: Sobrescreve cache_repo do builder (opcional)

        Returns:
            BuildResult com digest e metadados
        """
        # Usar parâmetros fornecidos ou defaults do builder
        use_cache = enable_cache if enable_cache is not None else self.enable_cache
        use_cache_repo = cache_repo if cache_repo is not None else self.cache_repo

        if self.builder_type == BuilderType.DOCKER:
            return await self._build_with_docker(
                dockerfile_path, build_context, image_tag,
                build_args, target_stage, platforms,
                use_cache, use_cache_repo,
            )
        else:
            return await self._build_with_kaniko(
                dockerfile_path, build_context, image_tag,
                build_args, target_stage, platforms,
                use_cache, use_cache_repo,
            )

    async def _build_with_docker(
        self,
        dockerfile_path: str,
        build_context: str,
        image_tag: str,
        build_args: Optional[dict] = None,
        target_stage: Optional[str] = None,
        platforms: Optional[List[str]] = None,
        enable_cache: bool = False,
        cache_repo: Optional[str] = None,
    ) -> BuildResult:
        """Executa build usando docker build CLI."""
        cmd = ["docker", "build"]

        # Adicionar flags de cache se habilitado
        if enable_cache:
            cmd.append("--cache-from")
            if cache_repo:
                cmd.append(f"type=registry,ref={cache_repo}")
            else:
                cmd.append("type=local")

            if cache_repo:
                cmd.append("--cache-to")
                cmd.append(f"type=registry,ref={cache_repo},mode=max")

        if platforms:
            cmd.extend(["--platform", ",".join(platforms)])

        cmd.extend(["-f", dockerfile_path])
        cmd.extend(["-t", image_tag])

        if build_args:
            for key, value in build_args.items():
                cmd.extend(["--build-arg", f"{key}={value}"])

        if target_stage:
            cmd.extend(["--target", target_stage])

        cmd.append(build_context)

        logger.info(
            "docker_build_started",
            image_tag=image_tag,
            dockerfile=dockerfile_path,
            context=build_context,
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds,
            )

            logs = (stdout.decode() + stderr.decode()).splitlines()

            if process.returncode == 0:
                # Obter digest via docker inspect
                digest = await self._get_image_digest(image_tag)
                size = await self._get_image_size(image_tag)

                logger.info(
                    "docker_build_success",
                    image_tag=image_tag,
                    digest=digest,
                    size_bytes=size,
                )

                return BuildResult(
                    success=True,
                    image_digest=digest,
                    image_tag=image_tag,
                    size_bytes=size,
                    build_logs=logs,
                )
            else:
                error_msg = stderr.decode()
                logger.error(
                    "docker_build_failed",
                    image_tag=image_tag,
                    error=error_msg,
                )

                return BuildResult(
                    success=False,
                    error_message=error_msg,
                    build_logs=logs,
                )

        except asyncio.TimeoutError:
            error_msg = f"Build timeout após {self.timeout_seconds}s"
            logger.error("docker_build_timeout", image_tag=image_tag)
            return BuildResult(
                success=False,
                error_message=error_msg,
            )
        except Exception as e:
            logger.error("docker_build_exception", image_tag=image_tag, error=str(e))
            return BuildResult(
                success=False,
                error_message=str(e),
            )

    async def _get_image_digest(self, image_tag: str) -> Optional[str]:
        """
        Obtém o digest SHA256 da imagem usando docker inspect.

        Tenta obter via RepoDigests primeiro, e fallback para ID.
        """
        try:
            # Primeiro tenta RepoDigests (para imagens com tag)
            cmd = [
                "docker",
                "inspect",
                "--format={{index .RepoDigests 0}}",
                image_tag,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, _ = await proc.communicate()

            if proc.returncode == 0:
                result = stdout.decode().strip()
                if "@" in result:
                    return result.split("@")[1]
        except Exception as e:
            logger.debug("docker_inspect_repodigests_failed", image=image_tag, error=str(e))

        # Fallback: tentar obter o ID da imagem
        try:
            cmd = [
                "docker",
                "inspect",
                "--format={{.Id}}",
                image_tag,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, _ = await proc.communicate()

            if proc.returncode == 0:
                result = stdout.decode().strip()
                # ID vem no formato "sha256:abc123"
                if result.startswith("sha256:"):
                    return result.replace("sha256:", "sha256:")
        except Exception as e:
            logger.warning("docker_inspect_id_failed", image=image_tag, error=str(e))

        return None

    async def _get_image_size(self, image_tag: str) -> Optional[int]:
        """Obtém o tamanho da imagem em bytes."""
        try:
            # Tentar obter via docker inspect (tamanho virtual)
            cmd = [
                "docker",
                "inspect",
                "--format={{.Size}}",
                image_tag,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, _ = await proc.communicate()

            if proc.returncode == 0:
                size_str = stdout.decode().strip()
                if size_str and size_str != "<nil>":
                    return int(size_str)
        except Exception:
            pass

        # Fallback: usar docker images
        try:
            cmd = ["docker", "images", image_tag, "--format", "{{.Size}}"]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, _ = await proc.communicate()

            if proc.returncode == 0:
                size_str = stdout.decode().strip()
                # Converter KB/MB/GB para bytes
                if size_str:
                    return self._parse_size(size_str)
        except Exception:
            pass

        return None

    def _parse_size(self, size_str: str) -> int:
        """Converte string de tamanho (10MB, 1.2GB) para bytes."""
        size_str = size_str.strip().upper()
        multipliers = {
            "B": 1,
            "KB": 1024,
            "MB": 1024 ** 2,
            "GB": 1024 ** 3,
        }

        for suffix, mult in multipliers.items():
            if size_str.endswith(suffix):
                num_str = size_str[: -len(suffix)]
                try:
                    return int(float(num_str) * mult)
                except ValueError:
                    pass

        return 0

    async def _build_with_kaniko(
        self,
        dockerfile_path: str,
        build_context: str,
        image_tag: str,
        build_args: Optional[dict] = None,
        target_stage: Optional[str] = None,
        platforms: Optional[List[str]] = None,
        enable_cache: bool = False,
        cache_repo: Optional[str] = None,
    ) -> BuildResult:
        """
        Executa build usando Kaniko no Kubernetes.

        Kaniko executa builds sem Docker daemon, ideal para Kubernetes.

        Args:
            dockerfile_path: Caminho para o Dockerfile
            build_context: Diretorio de contexto do build
            image_tag: Tag para a imagem resultante
            build_args: Argumentos de build (--build-arg)
            target_stage: Stage alvo em multi-stage build
            platforms: Lista de plataformas para multi-arch
            enable_cache: Habilita cache distribuído
            cache_repo: Repositório de cache (ex: ghcr.io/user/cache)

        Returns:
            BuildResult com digest e metadados
        """
        from kubernetes import client, config
        import tempfile
        import tarfile
        import base64
        import yaml

        logger.info(
            "kaniko_build_started",
            image_tag=image_tag,
            dockerfile=dockerfile_path,
            context=build_context,
        )

        try:
            # Carregar config do Kubernetes
            try:
                config.load_kube_config()
            except Exception:
                config.load_incluster_config()

            k8s = client.CoreV1Api()
            namespace = "docker-build"

            # Criar contexto empacotado (tar.gz)
            context_tar = tempfile.NamedTemporaryFile(
                suffix=".tar.gz",
                delete=False
            )

            with tarfile.open(context_tar.name, "w:gz") as tar:
                tar.add(build_context, arcname=".")

            # Ler Dockerfile
            with open(dockerfile_path, "r") as f:
                dockerfile_content = f.read()

            # Converter build_args para formato Kaniko
            kaniko_args = [
                "--dockerfile=Dockerfile",
                f"--context=tar://build-context.tar.gz",
                f"--destination={image_tag}",
                "--snapshotMode=redo",
                "--use-new-run",
            ]

            # Adicionar cache se habilitado
            if enable_cache:
                kaniko_args.append("--cache=true")
                if cache_repo:
                    kaniko_args.append(f"--cache-repo={cache_repo}")
                else:
                    # Usar o próprio image_tag como cache repo se não especificado
                    # Extrair registry e repositório da tag
                    tag_parts = image_tag.split("/")
                    if len(tag_parts) > 1:
                        # Usar o registry/repo sem a tag
                        cache_location = ":".join(image_tag.split(":")[:-1]) if ":" in image_tag else image_tag
                        kaniko_args.append(f"--cache-repo={cache_location}-cache")

            if build_args:
                for key, value in build_args.items():
                    kaniko_args.append(f"--build-arg={key}={value}")

            if target_stage:
                kaniko_args.append(f"--target={target_stage}")

            if platforms:
                kaniko_args.append(f"--platform={','.join(platforms)}")

            # Criar nome único para o pod
            import uuid
            pod_name = f"kaniko-{uuid.uuid4().hex[:8]}"

            # Ler o tar.gz e codificar em base64 para configmap
            with open(context_tar.name, "rb") as f:
                context_data = base64.b64encode(f.read()).decode()

            # Criar ConfigMap com o contexto
            configmap_name = f"kaniko-context-{uuid.uuid4().hex[:8]}"
            configmap = {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {
                    "name": configmap_name,
                    "namespace": namespace,
                },
                "data": {
                    "build-context.tar.gz": context_data,
                }
            }

            try:
                k8s.create_namespaced_config_map(
                    namespace=namespace,
                    body=configmap
                )
            except Exception as e:
                logger.warning("configmap_create_failed", error=str(e))

            # Manifesto do Pod Kaniko
            pod_manifest = {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "name": pod_name,
                    "namespace": namespace,
                    "labels": {
                        "app": "kaniko",
                        "build": image_tag.replace(":", "-").replace("/", "-")
                    }
                },
                "spec": {
                    "restartPolicy": "Never",
                    "containers": [{
                        "name": "kaniko",
                        "image": "gcr.io/kaniko-project/executor:latest",
                        "args": kaniko_args,
                        "volumeMounts": [{
                            "name": "kaniko-context",
                            "mountPath": "/workspace",
                        }],
                    }],
                    "volumes": [{
                        "name": "kaniko-context",
                        "configMap": {
                            "name": configmap_name
                        }
                    }],
                    "tolerations": [{
                        "key": "key",
                        "operator": "Exists",
                        "effect": "NoSchedule"
                    }]
                }
            }

            # Criar e executar o pod
            pod = k8s.create_namespaced_pod(
                namespace=namespace,
                body=pod_manifest
            )

            logger.info("kaniko_pod_created", pod_name=pod_name)

            # Aguardar conclusão do build
            start_time = asyncio.get_event_loop().time()

            while True:
                pod_status = k8s.read_namespaced_pod(
                    name=pod_name,
                    namespace=namespace
                )

                phase = pod_status.status.phase

                if phase == "Succeeded":
                    duration = int((asyncio.get_event_loop().time() - start_time) * 1000)

                    # Obter logs para extrair digest
                    logs = k8s.read_namespaced_pod_log(
                        name=pod_name,
                        namespace=namespace
                    )

                    # Parse digest dos logs
                    digest = self._parse_kaniko_digest(logs)

                    logger.info(
                        "kaniko_build_success",
                        pod_name=pod_name,
                        digest=digest,
                        duration_ms=duration,
                    )

                    # Cleanup
                    k8s.delete_namespaced_pod(
                        name=pod_name,
                        namespace=namespace
                    )
                    try:
                        k8s.delete_namespaced_config_map(
                            name=configmap_name,
                            namespace=namespace
                        )
                    except Exception:
                        pass

                    return BuildResult(
                        success=True,
                        image_digest=digest,
                        image_tag=image_tag,
                        duration_seconds=duration / 1000.0,
                    )

                elif phase == "Failed":
                    # Obter logs de erro
                    try:
                        logs = k8s.read_namespaced_pod_log(
                            name=pod_name,
                            namespace=namespace
                        )
                        error_msg = logs[-500:] if len(logs) > 500 else logs
                    except Exception:
                        error_msg = "Kaniko pod failed"

                    logger.error(
                        "kaniko_build_failed",
                        pod_name=pod_name,
                        error=error_msg,
                    )

                    # Cleanup
                    try:
                        k8s.delete_namespaced_pod(
                            name=pod_name,
                            namespace=namespace
                        )
                        k8s.delete_namespaced_config_map(
                            name=configmap_name,
                            namespace=namespace
                        )
                    except Exception:
                        pass

                    return BuildResult(
                        success=False,
                        error_message=f"Kaniko build failed: {error_msg}",
                    )

                # Timeout check
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > self.timeout_seconds:
                    logger.error("kaniko_build_timeout", pod_name=pod_name)
                    k8s.delete_namespaced_pod(
                        name=pod_name,
                        namespace=namespace
                    )
                    return BuildResult(
                        success=False,
                        error_message=f"Kaniko build timeout após {elapsed}s",
                    )

                await asyncio.sleep(5)

        except ImportError as e:
            logger.error("kubernetes_not_installed", error=str(e))
            return BuildResult(
                success=False,
                error_message="Kubernetes Python client não instalado. Instale: pip install kubernetes",
            )
        except Exception as e:
            logger.error("kaniko_build_exception", error=str(e))
            return BuildResult(
                success=False,
                error_message=f"Kaniko exception: {str(e)}",
            )

    def _parse_kaniko_digest(self, logs: str) -> Optional[str]:
        """
        Extrai o digest SHA256 dos logs do Kaniko.

        Formato esperado nos logs:
        Built image with digest sha256:abc123...
        """
        for line in logs.splitlines():
            if "digest sha256:" in line.lower():
                parts = line.split("sha256:")
                if len(parts) > 1:
                    digest_hash = parts[1].split()[0][:64]
                    return f"sha256:{digest_hash}"
        return None

    async def push_to_registry(
        self,
        local_image: str,
        target_uri: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        registry: Optional[str] = None,
    ) -> Optional[str]:
        """
        Faz push de uma imagem para um container registry.

        Args:
            local_image: Tag local da imagem
            target_uri: URI completa da imagem no registry (ex: ghcr.io/user/repo:tag)
            username: Usuario para autenticacao
            password: Password/token para autenticacao
            registry: URL do registry (se necessario)

        Returns:
            Digest SHA256 da imagem no registry ou None em caso de falha
        """
        logger.info(
            "push_started",
            local_image=local_image,
            target_uri=target_uri,
        )

        # Login se credenciais fornecidas
        if username and password:
            login_cmd = ["docker", "login"]
            if registry:
                login_cmd.append(registry)

            login_cmd.extend(["-u", username, "--password-stdin"])

            try:
                proc = await asyncio.create_subprocess_exec(
                    *login_cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate(input=password.encode())

                if proc.returncode != 0:
                    logger.error("docker_login_failed")
                    return None
            except Exception as e:
                logger.error("docker_login_exception", error=str(e))
                return None

        # Tag para target URI se diferente
        if local_image != target_uri:
            tag_cmd = ["docker", "tag", local_image, target_uri]
            try:
                proc = await asyncio.create_subprocess_exec(*tag_cmd)
                await proc.communicate()

                if proc.returncode != 0:
                    logger.error("docker_tag_failed")
                    return None
            except Exception as e:
                logger.error("docker_tag_exception", error=str(e))
                return None

        # Push
        push_cmd = ["docker", "push", target_uri]

        try:
            proc = await asyncio.create_subprocess_exec(
                *push_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=1800,  # 30 minutos
            )

            if proc.returncode == 0:
                # Extrair digest do output
                output = stdout.decode() + stderr.decode()
                for line in output.splitlines():
                    if "sha256:" in line and "digest" in line.lower():
                        parts = line.split("sha256:")
                        if len(parts) > 1:
                            digest = f"sha256:{parts[1][:64]}"
                            logger.info("push_success", digest=digest)
                            return digest

                # Tentar obter via inspect
                digest = await self._get_image_digest(target_uri)
                if digest:
                    logger.info("push_success", digest=digest)
                    return digest

        except asyncio.TimeoutError:
            logger.error("push_timeout")
        except Exception as e:
            logger.error("push_exception", error=str(e))

        return None
