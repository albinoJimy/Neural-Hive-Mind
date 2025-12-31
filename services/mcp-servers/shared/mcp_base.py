"""
Classe base para todos os MCP Servers do Neural Hive-Mind.

Fornece funcionalidades comuns como observability, health checks,
CORS e graceful shutdown.
"""

import asyncio
import signal
from abc import ABC, abstractmethod
from typing import Any, Optional

import structlog
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

logger = structlog.get_logger(__name__)


# Métricas Prometheus
MCP_REQUESTS_TOTAL = Counter(
    "mcp_server_requests_total",
    "Total de requisições MCP recebidas",
    ["method", "status"]
)

MCP_REQUEST_DURATION = Histogram(
    "mcp_server_request_duration_seconds",
    "Duração das requisições MCP em segundos",
    ["method"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

MCP_TOOL_EXECUTIONS = Counter(
    "mcp_tool_executions_total",
    "Total de execuções de ferramentas MCP",
    ["tool_name", "status"]
)

MCP_TOOL_DURATION = Histogram(
    "mcp_tool_execution_duration_seconds",
    "Duração da execução de ferramentas MCP em segundos",
    ["tool_name"],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)


class BaseMCPServer(ABC):
    """
    Classe base abstrata para MCP Servers.

    Fornece:
    - Setup de observability (Prometheus metrics + structured logging)
    - Health checks (/health e /ready)
    - Configuração CORS
    - Graceful shutdown
    """

    def __init__(
        self,
        name: str,
        version: str,
        allowed_origins: Optional[list[str]] = None
    ):
        self.name = name
        self.version = version
        self.allowed_origins = allowed_origins or ["*"]
        self._shutdown_event = asyncio.Event()
        self._is_ready = False

        # Configurar logging estruturado
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

    def setup_health_checks(self, app: FastAPI) -> None:
        """Adiciona endpoints de health check à aplicação FastAPI."""

        @app.get("/health")
        async def health_check() -> dict[str, Any]:
            """Verifica se o servidor está funcionando."""
            return {
                "status": "healthy",
                "service": self.name,
                "version": self.version
            }

        @app.get("/ready")
        async def readiness_check() -> Response:
            """Verifica se o servidor está pronto para receber tráfego."""
            if self._is_ready:
                return Response(
                    content='{"status": "ready"}',
                    media_type="application/json",
                    status_code=200
                )
            return Response(
                content='{"status": "not_ready"}',
                media_type="application/json",
                status_code=503
            )

        @app.get("/metrics")
        async def metrics() -> Response:
            """Expõe métricas Prometheus."""
            return Response(
                content=generate_latest(),
                media_type=CONTENT_TYPE_LATEST
            )

    def setup_cors(self, app: FastAPI) -> None:
        """Configura CORS para aceitar requisições do MCP Tool Catalog."""
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def setup_graceful_shutdown(self) -> None:
        """Configura handlers para SIGTERM e SIGINT."""
        loop = asyncio.get_event_loop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(self._handle_shutdown(s))
            )

    async def _handle_shutdown(self, sig: signal.Signals) -> None:
        """Handler para shutdown graceful."""
        logger.info(
            "shutdown_signal_received",
            signal=sig.name,
            service=self.name
        )
        self._is_ready = False
        self._shutdown_event.set()

    def set_ready(self, ready: bool = True) -> None:
        """Define o estado de readiness do servidor."""
        self._is_ready = ready
        logger.info(
            "readiness_state_changed",
            ready=ready,
            service=self.name
        )

    @property
    def is_shutting_down(self) -> bool:
        """Retorna True se o servidor está em processo de shutdown."""
        return self._shutdown_event.is_set()

    async def wait_for_shutdown(self) -> None:
        """Aguarda o sinal de shutdown."""
        await self._shutdown_event.wait()

    @abstractmethod
    async def initialize(self) -> None:
        """Inicializa recursos do servidor. Deve ser implementado pelas subclasses."""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Libera recursos do servidor. Deve ser implementado pelas subclasses."""
        pass


def record_request(method: str, status: str) -> None:
    """Registra uma requisição MCP nas métricas."""
    MCP_REQUESTS_TOTAL.labels(method=method, status=status).inc()


def record_request_duration(method: str, duration: float) -> None:
    """Registra a duração de uma requisição MCP."""
    MCP_REQUEST_DURATION.labels(method=method).observe(duration)


def record_tool_execution(tool_name: str, status: str) -> None:
    """Registra uma execução de ferramenta nas métricas."""
    MCP_TOOL_EXECUTIONS.labels(tool_name=tool_name, status=status).inc()


def record_tool_duration(tool_name: str, duration: float) -> None:
    """Registra a duração de execução de uma ferramenta."""
    MCP_TOOL_DURATION.labels(tool_name=tool_name).observe(duration)
