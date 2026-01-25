"""
Execution Ticket Service client com suporte a autenticação JWT-SVID via SPIFFE.
"""

import asyncio
import sys
from typing import Optional, Dict, List, Any, TYPE_CHECKING

import grpc
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
from opentelemetry import trace
from neural_hive_observability.grpc_instrumentation import instrument_grpc_channel
from neural_hive_observability.context import inject_context_to_metadata

from src.config.settings import OrchestratorSettings

if sys.version_info >= (3, 8):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict

if TYPE_CHECKING:
    from neural_hive_security import SPIFFEManager

# Import compiled proto stubs from neural_hive_integration
from neural_hive_integration.proto_stubs import ticket_service_pb2, ticket_service_pb2_grpc

logger = structlog.get_logger(__name__)

# Default timeout for gRPC channel initialization (seconds)
DEFAULT_CHANNEL_READY_TIMEOUT = 5


class ExecutionTicketDict(TypedDict, total=False):
    ticket_id: str
    plan_id: str
    intent_id: str
    task_id: str
    task_type: str
    description: str
    status: str
    priority: str
    created_at: int


class ExecutionTicketClient:
    """
    Cliente gRPC para o Execution Ticket Service com autenticação JWT-SVID opcional.

    O cliente é resiliente a falhas de conexão durante a inicialização,
    permitindo que o serviço inicie mesmo quando o Execution Ticket Service
    não está disponível. As operações falharão graciosamente se o cliente
    não estiver disponível.
    """

    def __init__(
        self,
        config: OrchestratorSettings,
        spiffe_manager: Optional['SPIFFEManager'] = None
    ):
        """
        Args:
            config: Configurações do orchestrator
            spiffe_manager: Gerenciador SPIFFE para JWT-SVID
        """
        self.config = config
        self.spiffe_manager = spiffe_manager
        self.logger = logger.bind(component='execution_ticket_client')
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None
        self.target = f"{getattr(config, 'execution_ticket_service_host', 'execution-ticket-service.neural-hive.svc.cluster.local')}:{getattr(config, 'execution_ticket_service_port', 50052)}"
        self.timeout_seconds = getattr(config, 'execution_ticket_timeout_seconds', 5)
        self.channel_ready_timeout = getattr(config, 'execution_ticket_channel_ready_timeout', DEFAULT_CHANNEL_READY_TIMEOUT)
        self._available = False

    @property
    def is_available(self) -> bool:
        """Retorna True se o cliente está disponível para operações."""
        return self._available and self.stub is not None

    async def initialize(self):
        """
        Inicializa canal gRPC e stub.

        Este método não bloqueia indefinidamente - usa timeout para verificar
        se o serviço está disponível. Se o serviço não estiver disponível,
        o cliente é marcado como indisponível mas não impede a inicialização
        do orchestrator.
        """
        try:
            self.logger.info('initializing_execution_ticket_client', target=self.target)
            self.channel = instrument_grpc_channel(
                grpc.aio.insecure_channel(self.target),
                service_name="orchestrator-dynamic",
                target_service="execution-ticket-service"
            )
            self.stub = ticket_service_pb2_grpc.TicketServiceStub(self.channel)

            # Aguarda o canal ficar pronto com timeout
            try:
                await asyncio.wait_for(
                    self.channel.channel_ready(),
                    timeout=self.channel_ready_timeout
                )
                self._available = True
                self.logger.info('execution_ticket_grpc_channel_ready', target=self.target)
            except asyncio.TimeoutError:
                self._available = False
                self.logger.warning(
                    'execution_ticket_client_channel_timeout',
                    target=self.target,
                    timeout=self.channel_ready_timeout,
                    message='Execution Ticket Service não disponível, operando em modo degradado'
                )
            except grpc.aio.AioRpcError as e:
                self._available = False
                self.logger.warning(
                    'execution_ticket_client_channel_error',
                    target=self.target,
                    error=str(e),
                    message='Falha ao conectar ao Execution Ticket Service, operando em modo degradado'
                )

        except Exception as e:
            self._available = False
            self.logger.error(
                'execution_ticket_client_init_failed',
                error=str(e),
                message='Falha na inicialização do cliente, operando em modo degradado'
            )

    async def _build_metadata(self) -> Optional[List[tuple]]:
        """
        Constrói metadata gRPC com JWT-SVID se SPIFFE estiver habilitado.
        """
        metadata = []
        if self.spiffe_manager and getattr(self.config, 'spiffe_enabled', False):
            audience = 'execution-ticket-service.neural-hive.local'
            try:
                jwt_svid = await self.spiffe_manager.fetch_jwt_svid(audience=audience)
                metadata.append(('authorization', f'Bearer {jwt_svid.token}'))
                self.logger.debug(
                    'jwt_svid_attached',
                    audience=audience,
                    spiffe_id=getattr(jwt_svid, 'spiffe_id', None)
                )
            except Exception as e:
                from neural_hive_security.spiffe_manager import SPIFFEFetchError

                fallback_allowed = getattr(self.config, 'spiffe_fallback_allowed', False)
                if isinstance(e, SPIFFEFetchError) and not fallback_allowed:
                    self.logger.error(
                        'jwt_auth_required_fallback_disabled',
                        error=str(e)
                    )
                    raise RuntimeError(f"JWT-SVID authentication required but SPIFFE unavailable: {e}")

                self.logger.warning(
                    'jwt_svid_fetch_failed_fallback_unauthenticated',
                    error=str(e)
                )

        metadata = inject_context_to_metadata(metadata or [])
        return metadata if metadata else None

    def _check_availability(self, operation: str) -> bool:
        """
        Verifica se o cliente está disponível para operações.

        Args:
            operation: Nome da operação sendo executada (para logging)

        Returns:
            True se disponível, False caso contrário
        """
        if not self.is_available:
            self.logger.warning(
                'execution_ticket_client_unavailable',
                operation=operation,
                message='Operação ignorada - cliente não disponível'
            )
            return False
        return True

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=0.5, max=2))
    async def get_ticket(self, ticket_id: str) -> Optional[ExecutionTicketDict]:
        """Busca ticket por ID."""
        if not self._check_availability('get_ticket'):
            return None

        request = ticket_service_pb2.GetTicketRequest(ticket_id=ticket_id)
        metadata = await self._build_metadata()

        response = await self.stub.GetTicket(request, metadata=metadata, timeout=self.timeout_seconds)
        if response.ticket:
            span = trace.get_current_span()
            span.set_attribute("rpc.service", "TicketService")
            span.set_attribute("rpc.method", "GetTicket")
            span.set_attribute("neural.hive.ticket.id", ticket_id)
            return self._convert_ticket(response.ticket)
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=0.5, max=2))
    async def list_tickets(
        self,
        plan_id: Optional[str] = None,
        status: Optional[str] = None,
        offset: int = 0,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Lista tickets com filtros opcionais."""
        if not self._check_availability('list_tickets'):
            return {'tickets': [], 'total': 0}

        request = ticket_service_pb2.ListTicketsRequest(
            plan_id=plan_id or '',
            status=status or '',
            offset=offset,
            limit=limit
        )
        metadata = await self._build_metadata()

        response = await self.stub.ListTickets(request, metadata=metadata, timeout=self.timeout_seconds)
        span = trace.get_current_span()
        span.set_attribute("rpc.service", "TicketService")
        span.set_attribute("rpc.method", "ListTickets")
        tickets = [self._convert_ticket(ticket_proto) for ticket_proto in response.tickets]
        return {'tickets': tickets, 'total': response.total}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=0.5, max=2))
    async def update_status(
        self,
        ticket_id: str,
        status: str,
        error_message: Optional[str] = None
    ) -> Optional[ExecutionTicketDict]:
        """Atualiza status do ticket."""
        if not self._check_availability('update_status'):
            return None

        request = ticket_service_pb2.UpdateTicketStatusRequest(
            ticket_id=ticket_id,
            status=status,
            error_message=error_message or ''
        )
        metadata = await self._build_metadata()

        response = await self.stub.UpdateTicketStatus(request, metadata=metadata, timeout=self.timeout_seconds)
        if response.ticket:
            span = trace.get_current_span()
            span.set_attribute("rpc.service", "TicketService")
            span.set_attribute("rpc.method", "UpdateTicketStatus")
            span.set_attribute("neural.hive.ticket.id", ticket_id)
            return self._convert_ticket(response.ticket)
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=0.5, max=2))
    async def generate_token(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Gera token JWT para ticket."""
        if not self._check_availability('generate_token'):
            return None

        request = ticket_service_pb2.GenerateTokenRequest(ticket_id=ticket_id)
        metadata = await self._build_metadata()

        response = await self.stub.GenerateToken(request, metadata=metadata, timeout=self.timeout_seconds)
        span = trace.get_current_span()
        span.set_attribute("rpc.service", "TicketService")
        span.set_attribute("rpc.method", "GenerateToken")
        span.set_attribute("neural.hive.ticket.id", ticket_id)
        return {'access_token': response.access_token, 'expires_at': response.expires_at}

    async def close(self):
        """Fecha canal gRPC."""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None

    def _convert_ticket(self, ticket_proto) -> ExecutionTicketDict:
        """Converte ExecutionTicketProto para dict."""
        return ExecutionTicketDict(
            ticket_id=ticket_proto.ticket_id,
            plan_id=ticket_proto.plan_id,
            intent_id=ticket_proto.intent_id,
            task_id=ticket_proto.task_id,
            task_type=ticket_proto.task_type,
            description=ticket_proto.description,
            status=ticket_proto.status,
            priority=ticket_proto.priority,
            created_at=ticket_proto.created_at
        )
