"""
Cliente gRPC para Execution Ticket Service.

Este módulo fornece um cliente assíncrono para comunicação
com o Execution Ticket Service via gRPC.
"""

import asyncio
from typing import Any, Optional

import grpc
import structlog

from execution_mcp_server.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class ExecutionTicketClient:
    """
    Cliente gRPC para Execution Ticket Service.
    
    Fornece métodos para:
    - Criar tickets
    - Consultar tickets
    - Atualizar status
    - Gerar tokens JWT
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        timeout_seconds: int = 30
    ):
        """
        Inicializa cliente gRPC.
        
        Args:
            host: Host do Execution Ticket Service
            port: Porta do Execution Ticket Service
            timeout_seconds: Timeout padrão para chamadas RPC
        """
        self._host = host or settings.execution_ticket_host
        self._port = port or settings.execution_ticket_port
        self._timeout = timeout_seconds
        self._channel: Optional[grpc.aio.Channel] = None
        self._stub: Optional[Any] = None
        self._connected = False

    async def connect(self) -> None:
        """Estabelece conexão com o servidor gRPC."""
        if self._connected:
            return

        target = f"{self._host}:{self._port}"
        logger.info("connecting_to_execution_ticket_service", target=target)

        try:
            self._channel = grpc.aio.insecure_channel(target)
            await self._channel.channel_ready()
            self._connected = True
            logger.info("execution_ticket_service_connected", target=target)

        except Exception as e:
            logger.error("execution_ticket_service_connection_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Fecha conexão com o servidor gRPC."""
        if self._channel:
            await self._channel.close()
            self._connected = False
            logger.info("execution_ticket_service_disconnected")

    async def _ensure_connected(self) -> None:
        """Garante que está conectado."""
        if not self._connected:
            await self.connect()

    async def create_ticket(
        self,
        plan_id: str,
        task_id: str,
        task_type: str,
        description: str,
        priority: str = "NORMAL",
        intent_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        dependencies: Optional[list[str]] = None,
        parameters: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """
        Cria novo execution ticket via gRPC.
        
        Args:
            plan_id: ID do plano cognitivo
            task_id: ID da tarefa
            task_type: Tipo da tarefa
            description: Descrição da tarefa
            priority: Prioridade (LOW, NORMAL, HIGH, CRITICAL)
            intent_id: ID da intenção
            decision_id: ID da decisão
            dependencies: Lista de ticket_ids dependentes
            parameters: Parâmetros da tarefa
            
        Returns:
            Dicionário com ticket criado
        """
        await self._ensure_connected()
        
        # Import dinâmico para evitar dependências em ambiente de testes
        try:
            from neural_hive_domain.proto_gen import ticket_service_pb2, ticket_service_pb2_grpc
            
            if not self._stub:
                self._stub = ticket_service_pb2_grpc.TicketServiceStub(self._channel)
            
            request = ticket_service_pb2.CreateTicketRequest(
                plan_id=plan_id,
                intent_id=intent_id or "",
                task_id=task_id,
                task_type=task_type,
                description=description,
                priority=priority
            )
            
            response = await asyncio.wait_for(
                self._stub.CreateTicket(request, timeout=self._timeout),
                timeout=self._timeout
            )
            
            return {
                "ticket_id": response.ticket.ticket_id,
                "status": response.ticket.status,
                "created_at": response.ticket.created_at
            }
            
        except ImportError:
            logger.warning("grpc_proto_not_available", message="Using mock response")
            # Retornar mock quando protobuf não está disponível
            import uuid
            return {
                "ticket_id": f"ticket-{uuid.uuid4().hex[:12]}",
                "status": "PENDING",
                "created_at": 0
            }

    async def get_ticket(self, ticket_id: str) -> Optional[dict[str, Any]]:
        """
        Busca ticket por ID via gRPC.
        
        Args:
            ticket_id: ID do ticket
            
        Returns:
            Dicionário com ticket ou None se não encontrado
        """
        await self._ensure_connected()
        
        try:
            from neural_hive_domain.proto_gen import ticket_service_pb2, ticket_service_pb2_grpc
            
            if not self._stub:
                self._stub = ticket_service_pb2_grpc.TicketServiceStub(self._channel)
            
            request = ticket_service_pb2.GetTicketRequest(ticket_id=ticket_id)
            response = await asyncio.wait_for(
                self._stub.GetTicket(request, timeout=self._timeout),
                timeout=self._timeout
            )
            
            return {
                "ticket_id": response.ticket.ticket_id,
                "plan_id": response.ticket.plan_id,
                "task_type": response.ticket.task_type,
                "status": response.ticket.status,
                "priority": response.ticket.priority,
                "created_at": response.ticket.created_at
            }
            
        except ImportError:
            logger.warning("grpc_proto_not_available")
            return None
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise

    async def update_status(
        self,
        ticket_id: str,
        status: str,
        error_message: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Atualiza status do ticket via gRPC.
        
        Args:
            ticket_id: ID do ticket
            status: Novo status
            error_message: Mensagem de erro (opcional)
            
        Returns:
            Dicionário com ticket atualizado
        """
        await self._ensure_connected()
        
        try:
            from neural_hive_domain.proto_gen import ticket_service_pb2, ticket_service_pb2_grpc
            
            if not self._stub:
                self._stub = ticket_service_pb2_grpc.TicketServiceStub(self._channel)
            
            request = ticket_service_pb2.UpdateTicketStatusRequest(
                ticket_id=ticket_id,
                status=status,
                error_message=error_message or ""
            )
            
            response = await asyncio.wait_for(
                self._stub.UpdateTicketStatus(request, timeout=self._timeout),
                timeout=self._timeout
            )
            
            return {
                "ticket_id": response.ticket.ticket_id,
                "status": response.ticket.status
            }
            
        except ImportError:
            logger.warning("grpc_proto_not_available")
            return {"ticket_id": ticket_id, "status": status}
        except grpc.aio.AioRpcError as e:
            logger.error("update_status_failed", code=e.code(), details=e.details())
            raise

    async def generate_token(self, ticket_id: str) -> Optional[dict[str, Any]]:
        """
        Gera token JWT para ticket via gRPC.
        
        Args:
            ticket_id: ID do ticket
            
        Returns:
            Dicionário com token ou None se falhar
        """
        await self._ensure_connected()
        
        try:
            from neural_hive_domain.proto_gen import ticket_service_pb2, ticket_service_pb2_grpc
            
            if not self._stub:
                self._stub = ticket_service_pb2_grpc.TicketServiceStub(self._channel)
            
            request = ticket_service_pb2.GenerateTokenRequest(ticket_id=ticket_id)
            response = await asyncio.wait_for(
                self._stub.GenerateToken(request, timeout=self._timeout),
                timeout=self._timeout
            )
            
            return {
                "access_token": response.access_token,
                "expires_at": response.expires_at,
                "ticket_id": ticket_id
            }
            
        except ImportError:
            logger.warning("grpc_proto_not_available")
            return None
        except grpc.aio.AioRpcError as e:
            logger.error("generate_token_failed", code=e.code(), details=e.details())
            return None


# Singleton instance
_client_instance: Optional[ExecutionTicketClient] = None


async def get_grpc_client() -> ExecutionTicketClient:
    """Retorna instância singleton do cliente gRPC."""
    global _client_instance
    if _client_instance is None:
        _client_instance = ExecutionTicketClient()
    return _client_instance
