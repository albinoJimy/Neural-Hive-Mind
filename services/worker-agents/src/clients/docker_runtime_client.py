"""
Cliente Docker Runtime para execução de comandos em containers Docker.

Este cliente implementa execução isolada de comandos via Docker API,
seguindo o padrão estabelecido pelos outros clientes do worker-agents.
"""

import asyncio
import structlog
from typing import Dict, Any, Optional, List
from tenacity import retry, stop_after_attempt, wait_exponential
from opentelemetry import trace
from pydantic import BaseModel, Field
from enum import Enum


logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


class DockerRuntimeError(Exception):
    """Erro de execução no Docker Runtime."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class DockerTimeoutError(Exception):
    """Timeout aguardando execução no Docker."""
    pass


class CommandNotAllowedError(Exception):
    """Comando não permitido para execução."""
    pass


class DockerNetworkMode(str, Enum):
    """Modos de rede disponíveis para containers."""
    BRIDGE = 'bridge'
    HOST = 'host'
    NONE = 'none'
    CONTAINER = 'container'


class ResourceLimits(BaseModel):
    """Limites de recursos para container Docker."""
    cpu_limit: float = Field(default=1.0, description='Limite de CPU em cores')
    memory_limit: str = Field(default='512m', description='Limite de memória (ex: 512m, 1g)')
    cpu_shares: Optional[int] = Field(default=None, description='CPU shares (peso relativo)')
    memory_swap: Optional[str] = Field(default=None, description='Limite de swap (ex: 1g, -1 para ilimitado)')


class VolumeMount(BaseModel):
    """Montagem de volume no container."""
    host_path: str
    container_path: str
    read_only: bool = True


class DockerExecutionRequest(BaseModel):
    """Request para execução de comando em container Docker."""
    image: str = Field(..., description='Imagem Docker a usar')
    command: List[str] = Field(..., description='Comando a executar')
    args: Optional[List[str]] = Field(default=None, description='Argumentos adicionais')
    env_vars: Optional[Dict[str, str]] = Field(default=None, description='Variáveis de ambiente')
    working_dir: Optional[str] = Field(default=None, description='Diretório de trabalho')
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)
    timeout_seconds: int = Field(default=600, description='Timeout em segundos')
    network_mode: DockerNetworkMode = Field(default=DockerNetworkMode.BRIDGE)
    volumes: Optional[List[VolumeMount]] = Field(default=None, description='Volumes a montar')
    user: Optional[str] = Field(default=None, description='Usuário para execução (ex: 1000:1000)')
    entrypoint: Optional[List[str]] = Field(default=None, description='Entrypoint customizado')


class ResourceUsage(BaseModel):
    """Uso de recursos pelo container."""
    cpu_usage_percent: float = 0.0
    memory_usage_bytes: int = 0
    memory_limit_bytes: int = 0
    network_rx_bytes: int = 0
    network_tx_bytes: int = 0


class DockerExecutionResult(BaseModel):
    """Resultado da execução em container Docker."""
    container_id: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    resource_usage: Optional[ResourceUsage] = None
    image_pulled: bool = False


class DockerRuntimeClient:
    """Cliente para execução de comandos em containers Docker."""

    def __init__(
        self,
        base_url: str = 'unix:///var/run/docker.sock',
        timeout: int = 600,
        verify_ssl: bool = True,
        default_cpu_limit: float = 1.0,
        default_memory_limit: str = '512m',
        cleanup_containers: bool = True,
    ):
        """
        Inicializa cliente Docker Runtime.

        Args:
            base_url: URL do Docker daemon (unix socket ou tcp)
            timeout: Timeout padrão para operações em segundos
            verify_ssl: Verificar certificado SSL (para tcp)
            default_cpu_limit: Limite de CPU padrão em cores
            default_memory_limit: Limite de memória padrão
            cleanup_containers: Remover containers após execução
        """
        self.base_url = base_url
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.default_cpu_limit = default_cpu_limit
        self.default_memory_limit = default_memory_limit
        self.cleanup_containers = cleanup_containers
        self._docker = None
        self._initialized = False
        self.logger = logger.bind(service='docker_runtime_client')

    async def initialize(self) -> None:
        """Inicializa conexão com Docker daemon."""
        try:
            import aiodocker
            self._docker = aiodocker.Docker(url=self.base_url)
            # Testar conexão
            await self._docker.version()
            self._initialized = True
            self.logger.info('docker_runtime_client_initialized', base_url=self.base_url)
        except ImportError:
            self.logger.error('aiodocker_not_installed')
            raise DockerRuntimeError('aiodocker não está instalado')
        except Exception as e:
            self.logger.error('docker_runtime_init_failed', error=str(e))
            raise DockerRuntimeError(f'Falha ao conectar ao Docker: {e}')

    async def close(self) -> None:
        """Fecha conexão com Docker daemon."""
        if self._docker:
            await self._docker.close()
            self._initialized = False
            self.logger.info('docker_runtime_client_closed')

    def _parse_memory_limit(self, memory_str: str) -> int:
        """Converte string de memória para bytes."""
        memory_str = memory_str.lower().strip()
        multipliers = {
            'b': 1,
            'k': 1024,
            'kb': 1024,
            'm': 1024 * 1024,
            'mb': 1024 * 1024,
            'g': 1024 * 1024 * 1024,
            'gb': 1024 * 1024 * 1024,
        }
        for suffix, multiplier in multipliers.items():
            if memory_str.endswith(suffix):
                return int(float(memory_str[:-len(suffix)]) * multiplier)
        return int(memory_str)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _pull_image(self, image: str) -> bool:
        """
        Pull de imagem Docker se necessário.

        Args:
            image: Nome da imagem

        Returns:
            True se imagem foi pulled, False se já existia
        """
        with tracer.start_as_current_span('docker.pull_image') as span:
            span.set_attribute('docker.image', image)

            try:
                # Verificar se imagem já existe
                try:
                    await self._docker.images.inspect(image)
                    self.logger.debug('docker_image_exists', image=image)
                    return False
                except Exception:
                    pass

                # Pull da imagem
                self.logger.info('docker_pulling_image', image=image)
                await self._docker.images.pull(image)
                self.logger.info('docker_image_pulled', image=image)
                return True

            except Exception as e:
                self.logger.error('docker_pull_failed', image=image, error=str(e))
                raise DockerRuntimeError(f'Falha ao pull de imagem {image}: {e}')

    async def execute_command(
        self,
        request: DockerExecutionRequest,
        metrics=None
    ) -> DockerExecutionResult:
        """
        Executa comando em container Docker.

        Args:
            request: Parâmetros da execução
            metrics: Objeto de métricas Prometheus (opcional)

        Returns:
            DockerExecutionResult com resultado da execução

        Raises:
            DockerRuntimeError: Erro na execução
            DockerTimeoutError: Timeout aguardando execução
        """
        if not self._initialized:
            await self.initialize()

        with tracer.start_as_current_span('docker.execute_command') as span:
            span.set_attribute('docker.image', request.image)
            span.set_attribute('docker.command', ' '.join(request.command))
            span.set_attribute('docker.timeout', request.timeout_seconds)

            container = None
            start_time = asyncio.get_event_loop().time()
            image_pulled = False

            try:
                # Pull imagem se necessário
                image_pulled = await self._pull_image(request.image)

                # Construir comando completo
                cmd = request.command.copy()
                if request.args:
                    cmd.extend(request.args)

                # Configurar recursos
                memory_bytes = self._parse_memory_limit(request.resource_limits.memory_limit)
                cpu_period = 100000
                cpu_quota = int(request.resource_limits.cpu_limit * cpu_period)

                # Configurar container
                config = {
                    'Image': request.image,
                    'Cmd': cmd,
                    'AttachStdout': True,
                    'AttachStderr': True,
                    'Tty': False,
                    'HostConfig': {
                        'Memory': memory_bytes,
                        'CpuPeriod': cpu_period,
                        'CpuQuota': cpu_quota,
                        'NetworkMode': request.network_mode.value,
                        'AutoRemove': False,  # Removeremos manualmente após coletar logs
                    }
                }

                if request.env_vars:
                    config['Env'] = [f'{k}={v}' for k, v in request.env_vars.items()]

                if request.working_dir:
                    config['WorkingDir'] = request.working_dir

                if request.user:
                    config['User'] = request.user

                if request.entrypoint:
                    config['Entrypoint'] = request.entrypoint

                if request.volumes:
                    binds = []
                    for vol in request.volumes:
                        mode = 'ro' if vol.read_only else 'rw'
                        binds.append(f'{vol.host_path}:{vol.container_path}:{mode}')
                    config['HostConfig']['Binds'] = binds

                if request.resource_limits.memory_swap:
                    swap_bytes = self._parse_memory_limit(request.resource_limits.memory_swap)
                    config['HostConfig']['MemorySwap'] = swap_bytes

                if request.resource_limits.cpu_shares:
                    config['HostConfig']['CpuShares'] = request.resource_limits.cpu_shares

                self.logger.info(
                    'docker_creating_container',
                    image=request.image,
                    command=cmd,
                    memory_limit=request.resource_limits.memory_limit,
                    cpu_limit=request.resource_limits.cpu_limit
                )

                # Criar container
                container = await self._docker.containers.create(config)
                container_id = container.id[:12]
                span.set_attribute('docker.container_id', container_id)

                self.logger.info('docker_container_created', container_id=container_id)

                # Iniciar container
                await container.start()
                self.logger.info('docker_container_started', container_id=container_id)

                # Aguardar conclusão com timeout
                try:
                    wait_result = await asyncio.wait_for(
                        container.wait(),
                        timeout=request.timeout_seconds
                    )
                    exit_code = wait_result.get('StatusCode', -1)
                except asyncio.TimeoutError:
                    self.logger.warning(
                        'docker_execution_timeout',
                        container_id=container_id,
                        timeout=request.timeout_seconds
                    )
                    # Tentar parar container
                    try:
                        await container.stop()
                    except Exception:
                        pass
                    raise DockerTimeoutError(
                        f'Timeout após {request.timeout_seconds}s aguardando container {container_id}'
                    )

                # Coletar logs
                stdout_logs = await container.log(stdout=True, stderr=False)
                stderr_logs = await container.log(stdout=False, stderr=True)

                stdout = ''.join(stdout_logs) if stdout_logs else ''
                stderr = ''.join(stderr_logs) if stderr_logs else ''

                # Calcular duração
                duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)

                # Coletar stats de recursos (se disponível)
                resource_usage = None
                try:
                    stats = await container.stats(stream=False)
                    if stats:
                        cpu_stats = stats.get('cpu_stats', {})
                        memory_stats = stats.get('memory_stats', {})
                        network_stats = stats.get('networks', {}).get('eth0', {})

                        resource_usage = ResourceUsage(
                            cpu_usage_percent=0.0,  # Simplificado
                            memory_usage_bytes=memory_stats.get('usage', 0),
                            memory_limit_bytes=memory_stats.get('limit', 0),
                            network_rx_bytes=network_stats.get('rx_bytes', 0),
                            network_tx_bytes=network_stats.get('tx_bytes', 0)
                        )
                except Exception:
                    pass  # Stats não são críticos

                self.logger.info(
                    'docker_execution_completed',
                    container_id=container_id,
                    exit_code=exit_code,
                    duration_ms=duration_ms
                )

                # Registrar métricas
                if metrics:
                    status = 'success' if exit_code == 0 else 'failed'
                    if hasattr(metrics, 'docker_executions_total'):
                        metrics.docker_executions_total.labels(status=status).inc()
                    if hasattr(metrics, 'docker_execution_duration_seconds'):
                        metrics.docker_execution_duration_seconds.labels(
                            stage='total'
                        ).observe(duration_ms / 1000)

                return DockerExecutionResult(
                    container_id=container_id,
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    duration_ms=duration_ms,
                    resource_usage=resource_usage,
                    image_pulled=image_pulled
                )

            except DockerTimeoutError:
                if metrics and hasattr(metrics, 'docker_executions_total'):
                    metrics.docker_executions_total.labels(status='timeout').inc()
                raise

            except Exception as e:
                self.logger.error(
                    'docker_execution_failed',
                    image=request.image,
                    error=str(e)
                )
                if metrics and hasattr(metrics, 'docker_executions_total'):
                    metrics.docker_executions_total.labels(status='failed').inc()
                raise DockerRuntimeError(f'Erro na execução Docker: {e}')

            finally:
                # Cleanup container
                if container and self.cleanup_containers:
                    try:
                        await container.delete(force=True)
                        self.logger.debug('docker_container_cleaned', container_id=container.id[:12])
                    except Exception as e:
                        self.logger.warning(
                            'docker_cleanup_failed',
                            container_id=container.id[:12] if container else 'unknown',
                            error=str(e)
                        )

    async def health_check(self) -> bool:
        """Verifica se Docker daemon está acessível."""
        try:
            if not self._docker:
                return False
            await self._docker.version()
            return True
        except Exception:
            return False
