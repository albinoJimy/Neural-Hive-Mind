"""
Serviço para teste de conectividade de ferramentas MCP.

Verifica se ferramentas estão acessíveis e funcionais.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class HealthStatus(str, Enum):
    """Status de saúde de conectividade."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class TestType(str, Enum):
    """Tipos de teste disponíveis."""

    TCP = "tcp"
    HTTP = "http"
    GRPC = "grpc"
    MCP_STDIO = "mcp_stdio"
    MCP_SSE = "mcp_sse"
    REDIS = "redis"
    MONGODB = "mongodb"
    KAFKA = "kafka"


@dataclass
class ConnectivityResult:
    """Resultado de teste de conectividade."""

    test_type: TestType
    target: str
    is_reachable: bool
    response_time_ms: Optional[int] = None
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class ConnectivityReport(BaseModel):
    """Relatório consolidado de conectividade."""

    tool_id: str = Field(..., description="ID da ferramenta")
    tool_name: str = Field(..., description="Nome da ferramenta")
    overall_status: HealthStatus = Field(..., description="Status consolidado")
    tests_performed: int = Field(..., description="Número de testes realizados")
    tests_passed: int = Field(..., description="Número de testes passados")
    tests_failed: int = Field(..., description="Número de testes falhados")
    results: list[dict[str, Any]] = Field(default_factory=list, description="Resultados detalhados")
    average_response_time_ms: Optional[float] = Field(
        default=None, description="Tempo médio de resposta"
    )
    recommendations: list[str] = Field(default_factory=list, description="Recomendações")
    last_check: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConnectivityTester:
    """
    Testador de conectividade para ferramentas MCP.

    Suporta testes de:
    - TCP socket connection
    - HTTP/HTTPS endpoints
    - gRPC services
    - MCP stdio servers
    - MCP SSE connections
    - Infrastructure (Redis, MongoDB, Kafka)
    """

    def __init__(self, timeout_seconds: float = 5.0, max_concurrent_tests: int = 10):
        """
        Inicializa testador de conectividade.

        Args:
            timeout_seconds: Timeout para cada teste
            max_concurrent_tests: Número máximo de testes paralelos
        """
        self.timeout = timeout_seconds
        self.max_concurrent_tests = max_concurrent_tests

    async def test_tool_connectivity(
        self,
        tool_id: str,
        tool_name: str,
        endpoint_url: Optional[str] = None,
        integration_type: Optional[str] = None,
        additional_endpoints: Optional[list[str]] = None,
    ) -> ConnectivityReport:
        """
        Testa conectividade completa de uma ferramenta.

        Args:
            tool_id: ID da ferramenta
            tool_name: Nome da ferramenta
            endpoint_url: URL principal (se aplicável)
            integration_type: Tipo de integração
            additional_endpoints: Endpoints adicionais para testar

        Returns:
            Relatório de conectividade
        """
        results: list[ConnectivityResult] = []
        recommendations: list[str] = []

        # Sempre testar endpoint principal se fornecido
        if endpoint_url:
            result = await self._test_endpoint(endpoint_url, integration_type)
            results.append(result)

        # Testar endpoints adicionais
        if additional_endpoints:
            for ep in additional_endpoints:
                result = await self._test_endpoint(ep, integration_type)
                results.append(result)

        # Consolidar resultado
        passed = sum(1 for r in results if r.is_reachable)
        failed = len(results) - passed

        # Determinar status geral
        if failed == 0:
            overall_status = HealthStatus.HEALTHY
        elif passed == 0:
            overall_status = HealthStatus.UNHEALTHY
        else:
            overall_status = HealthStatus.DEGRADED

        # Calcular tempo médio de resposta
        response_times = [r.response_time_ms for r in results if r.response_time_ms is not None]
        avg_response = sum(response_times) / len(response_times) if response_times else None

        # Gerar recomendações
        if overall_status == HealthStatus.UNHEALTHY:
            recommendations.append(
                "Ferramenta não está acessível. Verificar se serviço está rodando."
            )
        elif overall_status == HealthStatus.DEGRADED:
            recommendations.append("Alguns endpoints não estão acessíveis. Verificar configuração.")
        if avg_response and avg_response > 1000:
            recommendations.append(
                f"Tempo de resposta alto ({avg_response:.0f}ms). Considerar otimização."
            )

        return ConnectivityReport(
            tool_id=tool_id,
            tool_name=tool_name,
            overall_status=overall_status,
            tests_performed=len(results),
            tests_passed=passed,
            tests_failed=failed,
            results=[self._result_to_dict(r) for r in results],
            average_response_time_ms=avg_response,
            recommendations=recommendations,
        )

    async def _test_endpoint(
        self, endpoint: str, integration_type: Optional[str] = None
    ) -> ConnectivityResult:
        """Testa um endpoint específico."""
        # Determinar tipo de teste baseado na URL
        if endpoint.startswith(("http://", "https://")):
            return await self._test_http(endpoint)
        elif endpoint.startswith(("redis://", "rediss://")):
            return await self._test_redis(endpoint)
        elif endpoint.startswith(("mongodb://", "mongodb+srv://")):
            return await self._test_mongodb(endpoint)
        elif endpoint.startswith(("kafka://", "kafka+ssl://")):
            return await self._test_kafka(endpoint)
        elif ":" in endpoint:  # host:port format
            host, port = endpoint.rsplit(":", 1)
            return await self._test_tcp(host, int(port))
        else:
            return ConnectivityResult(
                test_type=TestType.HTTP,
                target=endpoint,
                is_reachable=False,
                error_message=f"Tipo de endpoint não suportado: {endpoint}",
            )

    async def _test_http(self, url: str) -> ConnectivityResult:
        """Testa conectividade HTTP/HTTPS."""
        import aiohttp

        start_time = asyncio.get_event_loop().time()

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as session:
                async with session.get(url, allow_redirects=True) as response:
                    elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
                    is_reachable = response.status < 500

                    return ConnectivityResult(
                        test_type=TestType.HTTP,
                        target=url,
                        is_reachable=is_reachable,
                        response_time_ms=int(elapsed),
                        status_code=response.status,
                        details={
                            "status": response.status,
                            "reason": response.reason,
                            "headers": dict(response.headers),
                        },
                    )
        except asyncio.TimeoutError:
            return ConnectivityResult(
                test_type=TestType.HTTP,
                target=url,
                is_reachable=False,
                error_message=f"Timeout após {self.timeout}s",
            )
        except Exception as e:
            return ConnectivityResult(
                test_type=TestType.HTTP, target=url, is_reachable=False, error_message=str(e)
            )

    async def _test_tcp(self, host: str, port: int) -> ConnectivityResult:
        """Testa conectividade TCP básica."""
        start_time = asyncio.get_event_loop().time()

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=self.timeout
            )
            elapsed = (asyncio.get_event_loop().time() - start_time) * 1000

            writer.close()
            await writer.wait_closed()

            return ConnectivityResult(
                test_type=TestType.TCP,
                target=f"{host}:{port}",
                is_reachable=True,
                response_time_ms=int(elapsed),
                details={"host": host, "port": port},
            )
        except asyncio.TimeoutError:
            return ConnectivityResult(
                test_type=TestType.TCP,
                target=f"{host}:{port}",
                is_reachable=False,
                error_message=f"Timeout após {self.timeout}s",
                details={"host": host, "port": port},
            )
        except Exception as e:
            return ConnectivityResult(
                test_type=TestType.TCP,
                target=f"{host}:{port}",
                is_reachable=False,
                error_message=str(e),
                details={"host": host, "port": port},
            )

    async def _test_redis(self, url: str) -> ConnectivityResult:
        """Testa conectividade Redis."""
        try:
            import aioredis
        except ImportError:
            return ConnectivityResult(
                test_type=TestType.REDIS,
                target=url,
                is_reachable=False,
                error_message="aioredis não instalado",
            )

        start_time = asyncio.get_event_loop().time()

        try:
            client = await aioredis.from_url(url, socket_timeout=self.timeout)
            await client.ping()
            elapsed = (asyncio.get_event_loop().time() - start_time) * 1000

            await client.close()

            return ConnectivityResult(
                test_type=TestType.REDIS,
                target=url,
                is_reachable=True,
                response_time_ms=int(elapsed),
                details={"url": url},
            )
        except Exception as e:
            return ConnectivityResult(
                test_type=TestType.REDIS, target=url, is_reachable=False, error_message=str(e)
            )

    async def _test_mongodb(self, url: str) -> ConnectivityResult:
        """Testa conectividade MongoDB."""
        try:
            import motor.motor_asyncio
        except ImportError:
            return ConnectivityResult(
                test_type=TestType.MONGODB,
                target=url,
                is_reachable=False,
                error_message="motor não instalado",
            )

        start_time = asyncio.get_event_loop().time()

        try:
            client = motor.motor_asyncio.AsyncIOMotorClient(
                url, serverSelectionTimeoutMS=int(self.timeout * 1000)
            )
            await client.admin.command("ping")
            elapsed = (asyncio.get_event_loop().time() - start_time) * 1000

            client.close()

            return ConnectivityResult(
                test_type=TestType.MONGODB,
                target=url,
                is_reachable=True,
                response_time_ms=int(elapsed),
                details={"url": url},
            )
        except Exception as e:
            return ConnectivityResult(
                test_type=TestType.MONGODB, target=url, is_reachable=False, error_message=str(e)
            )

    async def _test_kafka(self, url: str) -> ConnectivityResult:
        """Testa conectividade Kafka."""
        try:
            import aiokafka
        except ImportError:
            return ConnectivityResult(
                test_type=TestType.KAFKA,
                target=url,
                is_reachable=False,
                error_message="aiokafka não instalado",
            )

        start_time = asyncio.get_event_loop().time()

        try:
            # Extrair host e port da URL kafka://host:port
            target = url.replace("kafka://", "").replace("kafka+ssl://", "")

            producer = aiokafka.AIOKafkaProducer(
                bootstrap_servers=target, request_timeout_ms=int(self.timeout * 1000)
            )
            await producer.start()
            elapsed = (asyncio.get_event_loop().time() - start_time) * 1000

            await producer.stop()

            return ConnectivityResult(
                test_type=TestType.KAFKA,
                target=url,
                is_reachable=True,
                response_time_ms=int(elapsed),
                details={"bootstrap_servers": target},
            )
        except Exception as e:
            return ConnectivityResult(
                test_type=TestType.KAFKA, target=url, is_reachable=False, error_message=str(e)
            )

    async def test_batch(self, tools: list[dict[str, Any]]) -> list[ConnectivityReport]:
        """
        Testa conectividade de múltiplas ferramentas em paralelo.

        Args:
            tools: Lista de dicionários com tool_id, tool_name, endpoint_url

        Returns:
            Lista de relatórios
        """
        semaphore = asyncio.Semaphore(self.max_concurrent_tests)

        async def test_with_semaphore(tool: dict[str, Any]) -> ConnectivityReport:
            async with semaphore:
                return await self.test_tool_connectivity(
                    tool_id=tool.get("tool_id", ""),
                    tool_name=tool.get("tool_name", ""),
                    endpoint_url=tool.get("endpoint_url"),
                    integration_type=tool.get("integration_type"),
                    additional_endpoints=tool.get("additional_endpoints"),
                )

        tasks = [test_with_semaphore(tool) for tool in tools]
        return await asyncio.gather(*tasks)

    def _result_to_dict(self, result: ConnectivityResult) -> dict[str, Any]:
        """Converte ConnectivityResult para dicionário."""
        return {
            "test_type": result.test_type.value,
            "target": result.target,
            "is_reachable": result.is_reachable,
            "response_time_ms": result.response_time_ms,
            "status_code": result.status_code,
            "error_message": result.error_message,
            "details": result.details,
            "timestamp": result.timestamp.isoformat(),
        }

    async def check_infrastructure_connectivity(
        self,
        redis_url: Optional[str] = None,
        mongodb_url: Optional[str] = None,
        kafka_url: Optional[str] = None,
    ) -> dict[str, ConnectivityResult]:
        """
        Testa conectividade de infraestrutura.

        Args:
            redis_url: URL do Redis
            mongodb_url: URL do MongoDB
            kafka_url: URL do Kafka

        Returns:
            Dicionário com resultados por serviço
        """
        results = {}

        if redis_url:
            results["redis"] = await self._test_redis(redis_url)

        if mongodb_url:
            results["mongodb"] = await self._test_mongodb(mongodb_url)

        if kafka_url:
            results["kafka"] = await self._test_kafka(kafka_url)

        return results


async def check_tool_health(
    tool_id: str, tool_name: str, endpoint_url: Optional[str] = None
) -> dict[str, Any]:
    """
    Função auxiliar para verificar saúde de ferramenta.

    Args:
        tool_id: ID da ferramenta
        tool_name: Nome da ferramenta
        endpoint_url: URL para testar

    Returns:
        Dicionário com status de saúde
    """
    tester = ConnectivityTester()
    report = await tester.test_tool_connectivity(
        tool_id=tool_id, tool_name=tool_name, endpoint_url=endpoint_url
    )

    return {
        "tool_id": report.tool_id,
        "tool_name": report.tool_name,
        "is_healthy": report.overall_status == HealthStatus.HEALTHY,
        "status": report.overall_status.value,
        "last_check": report.last_check.isoformat(),
        "details": report.model_dump(),
    }
