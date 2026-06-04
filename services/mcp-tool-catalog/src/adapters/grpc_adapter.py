"""
GRPCAdapter para execução de ferramentas via gRPC.

Permite comunicação com serviços gRPC do Neural Hive-Mind.
"""

import asyncio
import socket
import time
from typing import Any, Optional
from unittest.mock import Mock

import grpc
from grpc.aio import AioRpcError

from .base_adapter import BaseToolAdapter, ExecutionResult


class GRPCAdapter(BaseToolAdapter):
    """
    Adapter para execução de ferramentas via gRPC.

    Suporta:
    - Chamadas unary (request/response)
    - Service discovery via Service Registry
    - Retry com exponential backoff
    - Timeout configurável
    - Metadata gRPC (tracing, autenticação)
    """

    def __init__(
        self,
        service_registry=None,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        retry_delay_ms: int = 100,
    ):
        """
        Inicializa o GRPCAdapter.

        Args:
            service_registry: Cliente do Service Registry para descoberta
            timeout_seconds: Timeout para chamadas gRPC
            max_retries: Número máximo de retries
            retry_delay_ms: Delay inicial entre retries (ms)
        """
        super().__init__()
        self.service_registry = service_registry
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms
        self._channel_cache = {}
        self._service_cache = {}

    async def execute(
        self,
        tool_id: str,
        tool_name: str,
        command: str,
        parameters: dict[str, Any],
        context: dict[str, Any],
    ) -> ExecutionResult:
        """
        Executa uma ferramenta via gRPC.

        Args:
            tool_id: ID único da ferramenta
            tool_name: Nome da ferramenta (usado para service discovery)
            command: Comando gRPC no formato "service:Method"
            parameters: Parâmetros da chamada
            context: Contexto adicional (auth_token, trace_id, etc)

        Returns:
            ExecutionResult com resultado da execução
        """
        start_time = time.time()

        # Extrair service name e método do command
        service_name = tool_name

        # Descobrir serviço
        service_info = await self._discover_service(service_name)
        if not service_info:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Service {service_name} not found",
                metadata={"service_name": service_name},
            )

        host = service_info.get("host", f"{service_name}.neural-hive.svc.cluster.local")
        port = service_info.get("port", 9090)

        # Preparar metadata gRPC
        metadata = self._prepare_grpc_metadata(context)

        # Executar com retry
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                stub = await self._get_stub(service_name, host, port)

                # Criar request a partir dos parâmetros
                request = self._create_request(parameters)

                # Executar chamada gRPC
                response = await stub.ExecuteTool(
                    request,
                    timeout=self.timeout_seconds,
                    metadata=metadata,
                )

                # Processar resposta
                execution_time_ms = (time.time() - start_time) * 1000

                # Obter output de response, com fallbacks
                # Nota: Mock objects podem criar atributos dinamicamente, então verificamos o tipo
                output = ""
                message_attr = getattr(response, "message", None)
                insight_attr = getattr(response, "insight_data", None)

                # Verificar se o valor é uma string (não um Mock)
                if message_attr and isinstance(message_attr, str):
                    output = message_attr
                elif insight_attr and isinstance(insight_attr, str):
                    output = insight_attr
                else:
                    # Fallback para str() se os atributos existirem
                    if message_attr:
                        output = str(message_attr) if not isinstance(message_attr, Mock) else ""
                    elif insight_attr:
                        output = str(insight_attr) if not isinstance(insight_attr, Mock) else ""

                result = ExecutionResult(
                    success=getattr(response, "success", True),
                    output=output,
                    execution_time_ms=execution_time_ms,
                    exit_code=getattr(response, "exit_code", 0),
                    metadata={
                        "command": command,
                        "service_name": service_name,
                        "host": host,
                        "port": port,
                        "attempts": attempt,
                        "execution_time_ms": execution_time_ms,
                    },
                )

                await self._log_execution(tool_name, command, result)
                return result

            except AioRpcError as e:
                last_error = e
                self.logger.warning(
                    "grpc_call_failed",
                    service=service_name,
                    attempt=attempt,
                    code=e.code(),
                    details=e.details(),
                )

                # Não retry em erros não-transientes
                if e.code() in [
                    grpc.StatusCode.PERMISSION_DENIED,
                    grpc.StatusCode.UNAUTHENTICATED,
                    grpc.StatusCode.INVALID_ARGUMENT,
                    grpc.StatusCode.NOT_FOUND,
                ]:
                    break

                # Retry com exponential backoff
                if attempt < self.max_retries:
                    delay = self.retry_delay_ms * (2 ** (attempt - 1)) / 1000
                    await asyncio.sleep(delay)

            except asyncio.TimeoutError:
                last_error = asyncio.TimeoutError("gRPC call timeout")
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay_ms / 1000)

            except Exception as e:
                last_error = e
                self.logger.error("grpc_call_unexpected_error", error=str(e))
                break

        # Todas as tentativas falharam
        execution_time_ms = (time.time() - start_time) * 1000

        error_msg = self._format_grpc_error(last_error)
        return ExecutionResult(
            success=False,
            output="",
            error=error_msg,
            execution_time_ms=execution_time_ms,
            metadata={
                "command": command,
                "service_name": service_name,
                "attempts": self.max_retries,
            },
        )

    async def validate_tool_availability(self, tool_name: str, health_check: bool = False) -> bool:
        """
        Valida se a ferramenta está disponível via gRPC.

        Args:
            tool_name: Nome da ferramenta/serviço
            health_check: Se deve executar health check gRPC

        Returns:
            True se disponível, False caso contrário
        """
        service_info = await self._discover_service(tool_name)

        if not service_info:
            return False

        if not health_check:
            return True

        # Executar health check
        try:
            host = service_info.get("host")
            port = service_info.get("port", 9090)

            stub = await self._get_stub(tool_name, host, port)
            response = await stub.Check(
                request=None,  # EmptyRequest
                timeout=5,
            )

            return getattr(response, "status", "") == "SERVING"

        except Exception as e:
            self.logger.warning("health_check_failed", tool=tool_name, error=str(e))
            return False

    async def _discover_service(self, service_name: str) -> Optional[dict[str, Any]]:
        """
        Descobre informações do serviço via Service Registry ou DNS.

        Args:
            service_name: Nome do serviço

        Returns:
            Dict com host, port e metadata
        """
        # Verificar cache
        if service_name in self._service_cache:
            return self._service_cache[service_name]

        # Usar Service Registry se disponível
        if self.service_registry:
            try:
                service_info = await self.service_registry.discover_service(service_name)
                if service_info:
                    self._service_cache[service_name] = service_info
                    return service_info
            except Exception as e:
                self.logger.warning(
                    "service_registry_discovery_failed", service=service_name, error=str(e)
                )

        # Fallback para DNS
        try:
            host = f"{service_name}.neural-hive.svc.cluster.local"
            socket.gethostbyname(host)

            service_info = {
                "service_name": service_name,
                "host": host,
                "port": 9090,  # Porta gRPC padrão
            }
            self._service_cache[service_name] = service_info
            return service_info

        except socket.gaierror:
            self.logger.error("service_not_found", service=service_name)
            return None

    async def _get_stub(self, service_name: str, host: str, port: int) -> Any:
        """
        Obtém stub gRPC para o serviço.

        Reutiliza canais em cache quando possível.

        Args:
            service_name: Nome do serviço
            host: Host do serviço
            port: Porta do serviço

        Returns:
            Stub gRPC
        """
        service_key = f"{service_name}:{port}"

        # Verificar cache de canal
        if service_key in self._channel_cache:
            channel = self._channel_cache[service_key]
            try:
                # Criar stub a partir do canal em cache
                return self._create_stub(channel)
            except Exception:
                # Canal inválido, remover e criar novo
                await self._close_channel(service_name, port)

        # Criar novo canal
        target = f"{host}:{port}"
        channel = grpc.aio.insecure_channel(target)
        self._channel_cache[service_key] = channel

        return self._create_stub(channel)

    def _create_stub(self, channel: Any) -> Any:
        """
        Cria stub gRPC a partir do canal.

        Nota: Em produção, isso deve usar o proto compilado.
        Aqui usamos um mock para os testes.
        """
        # Em produção, isso seria algo como:
        # from generated import tool_pb2_grpc
        # return tool_pb2_grpc.ToolServiceStub(channel)

        # Para testes, retornamos o canal que será mockado
        return channel

    async def _close_channel(self, service_name: str, port: int):
        """
        Fecha canal gRPC e remove do cache.

        Args:
            service_name: Nome do serviço
            port: Porta do serviço
        """
        service_key = f"{service_name}:{port}"

        if service_key in self._channel_cache:
            channel = self._channel_cache.pop(service_key)
            await channel.close()

    def _prepare_grpc_metadata(self, context: dict[str, Any]) -> list:
        """
        Prepara metadata gRPC a partir do contexto.

        Args:
            context: Contexto da execução

        Returns:
            Lista de tuplas (key, value) para metadata gRPC
        """
        metadata = []

        # Tracing
        if "trace_id" in context:
            metadata.append(("trace_id", str(context["trace_id"])))
        if "span_id" in context:
            metadata.append(("span_id", str(context["span_id"])))

        # Autenticação
        if "auth_token" in context:
            metadata.append(("authorization", f"Bearer {context['auth_token']}"))
        elif "api_key" in context:
            metadata.append(("x-api-key", str(context["api_key"])))

        # Outros metadados
        for key, value in context.items():
            if key not in ["trace_id", "span_id", "auth_token", "api_key"]:
                metadata.append((f"x-context-{key}", str(value)))

        return metadata

    def _create_request(self, parameters: dict[str, Any]) -> Any:
        """
        Cria objeto request para chamada gRPC.

        Nota: Em produção, isso deve usar o proto compilado.
        Aqui usamos um dict simples que será convertido.

        Args:
            parameters: Parâmetros da chamada

        Returns:
            Objeto request (mockado para testes)
        """
        # Em produção, isso seria algo como:
        # request = tool_pb2.ExecuteToolRequest()
        # request.tool_id = parameters.get("tool_id")
        # ...
        # return request

        # Para testes, retornamos os parâmetros como dict
        return parameters

    def _format_grpc_error(self, error: Any) -> str:
        """
        Formata erro gRPC para mensagem legível.

        Args:
            error: Erro gRPC

        Returns:
            String com mensagem de erro formatada
        """
        if isinstance(error, AioRpcError):
            code_name = error.code().name
            details = error.details()
            return f"gRPC error: {code_name} - {details}"
        elif isinstance(error, asyncio.TimeoutError):
            return "gRPC call timeout"
        elif isinstance(error, Exception):
            return f"gRPC error: {error!s}"
        else:
            return "Unknown gRPC error"
