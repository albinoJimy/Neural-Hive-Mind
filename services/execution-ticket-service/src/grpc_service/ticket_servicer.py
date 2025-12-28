"""
Implementação do gRPC Servicer para Ticket Service.

Este módulo implementa os métodos RPC definidos no ticket_service.proto,
expondo operações de consulta, listagem, atualização de status e geração
de tokens JWT para execution tickets.

Arquivos gerados pelo protoc:
    - ticket_service_pb2.py: mensagens Protocol Buffers
    - ticket_service_pb2_grpc.py: stubs e servicer base do gRPC
    - ticket_service_pb2.pyi: type hints

Comando para gerar arquivos:
    python -m grpc_tools.protoc -I./protos \
        --python_out=./src/grpc_service \
        --grpc_python_out=./src/grpc_service \
        --pyi_out=./src/grpc_service \
        ./protos/ticket_service.proto

Conversões:
    - _pydantic_to_proto: converte ExecutionTicket (Pydantic) para ExecutionTicketProto
      Importante: created_at é int64 em milissegundos, não string ISO
"""
import logging
from typing import Optional

import grpc
from . import ticket_service_pb2
from . import ticket_service_pb2_grpc

from neural_hive_observability import get_tracer
from neural_hive_observability.context import set_baggage
from neural_hive_observability.grpc_instrumentation import extract_grpc_context

from ..database import get_postgres_client
from ..models import ExecutionTicket, TicketStatus
from ..models.jwt_token import generate_token
from ..config import get_settings

logger = logging.getLogger(__name__)
tracer = get_tracer()


class TicketServiceServicer(ticket_service_pb2_grpc.TicketServiceServicer):
    """Implementação dos RPCs do Ticket Service."""

    async def GetTicket(self, request, context):
        """
        Busca ticket por ID.

        Args:
            request: GetTicketRequest
            context: gRPC context

        Returns:
            GetTicketResponse
        """
        ticket_id = request.ticket_id

        try:
            metadata_dict = dict(context.invocation_metadata())
            extract_grpc_context(metadata_dict)
            if hasattr(request, "plan_id") and request.plan_id:
                set_baggage("plan_id", request.plan_id)
            if ticket_id:
                set_baggage("ticket_id", ticket_id)

            postgres_client = await get_postgres_client()
            ticket_orm = await postgres_client.get_ticket_by_id(ticket_id)

            if not ticket_orm:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f'Ticket {ticket_id} not found')
                return ticket_service_pb2.GetTicketResponse()

            # Converter ORM → Pydantic → Proto
            ticket_pydantic = ticket_orm.to_pydantic()
            ticket_proto = self._pydantic_to_proto(ticket_pydantic)

            return ticket_service_pb2.GetTicketResponse(ticket=ticket_proto)

        except Exception as e:
            logger.error(f"GetTicket error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ticket_service_pb2.GetTicketResponse()

    async def ListTickets(self, request, context):
        """
        Lista tickets com filtros.

        Args:
            request: ListTicketsRequest
            context: gRPC context

        Returns:
            ListTicketsResponse
        """
        try:
            metadata_dict = dict(context.invocation_metadata())
            extract_grpc_context(metadata_dict)
            if hasattr(request, "plan_id") and request.plan_id:
                set_baggage("plan_id", request.plan_id)

            postgres_client = await get_postgres_client()

            filters = {}
            if request.plan_id:
                filters['plan_id'] = request.plan_id
            if request.status:
                filters['status'] = request.status

            offset = request.offset if request.offset > 0 else 0
            limit = min(request.limit if request.limit > 0 else 100, 1000)

            tickets_orm = await postgres_client.list_tickets(filters, offset, limit)
            total = await postgres_client.count_tickets(filters)

            # Converter para proto
            tickets_proto = [
                self._pydantic_to_proto(t.to_pydantic())
                for t in tickets_orm
            ]

            return ticket_service_pb2.ListTicketsResponse(
                tickets=tickets_proto,
                total=total
            )

        except Exception as e:
            logger.error(f"ListTickets error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ticket_service_pb2.ListTicketsResponse()

    async def UpdateTicketStatus(self, request, context):
        """
        Atualiza status do ticket.

        Args:
            request: UpdateTicketStatusRequest
            context: gRPC context

        Returns:
            UpdateTicketStatusResponse
        """
        ticket_id = request.ticket_id
        new_status = TicketStatus(request.status)
        error_message = request.error_message if request.error_message else None

        try:
            metadata_dict = dict(context.invocation_metadata())
            extract_grpc_context(metadata_dict)
            if hasattr(request, "plan_id") and request.plan_id:
                set_baggage("plan_id", request.plan_id)
            if ticket_id:
                set_baggage("ticket_id", ticket_id)

            postgres_client = await get_postgres_client()

            # Verificar se ticket existe
            ticket_orm = await postgres_client.get_ticket_by_id(ticket_id)
            if not ticket_orm:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f'Ticket {ticket_id} not found')
                return ticket_service_pb2.UpdateTicketStatusResponse()

            # Atualizar status
            updated_orm = await postgres_client.update_ticket_status(
                ticket_id,
                new_status,
                error_message
            )

            if not updated_orm:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details('Failed to update ticket')
                return ticket_service_pb2.UpdateTicketStatusResponse()

            # Converter para proto
            ticket_proto = self._pydantic_to_proto(updated_orm.to_pydantic())

            return ticket_service_pb2.UpdateTicketStatusResponse(ticket=ticket_proto)

        except Exception as e:
            logger.error(f"UpdateTicketStatus error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ticket_service_pb2.UpdateTicketStatusResponse()

    async def GenerateToken(self, request, context):
        """
        Gera token JWT para ticket.

        Args:
            request: GenerateTokenRequest
            context: gRPC context

        Returns:
            GenerateTokenResponse
        """
        ticket_id = request.ticket_id

        try:
            metadata_dict = dict(context.invocation_metadata())
            extract_grpc_context(metadata_dict)
            if hasattr(request, "plan_id") and request.plan_id:
                set_baggage("plan_id", request.plan_id)
            if ticket_id:
                set_baggage("ticket_id", ticket_id)

            settings = get_settings()
            postgres_client = await get_postgres_client()

            # Buscar ticket
            ticket_orm = await postgres_client.get_ticket_by_id(ticket_id)
            if not ticket_orm:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f'Ticket {ticket_id} not found')
                return ticket_service_pb2.GenerateTokenResponse()

            ticket = ticket_orm.to_pydantic()

            # Validar status
            if ticket.status not in [TicketStatus.PENDING, TicketStatus.RUNNING]:
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details(f'Cannot generate token for ticket with status {ticket.status.value}')
                return ticket_service_pb2.GenerateTokenResponse()

            # Gerar token
            with tracer.start_as_current_span("generate_jwt_token") as span:
                span.set_attribute("neural.hive.ticket.id", ticket_id)
                token = generate_token(
                    ticket,
                    settings.jwt_secret_key,
                    settings.jwt_algorithm,
                    settings.jwt_token_expiration_seconds
                )
                span.set_attribute("neural.hive.ticket.status", ticket.status.value)

            return ticket_service_pb2.GenerateTokenResponse(
                access_token=token.access_token,
                expires_at=token.expires_at
            )

        except Exception as e:
            logger.error(f"GenerateToken error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ticket_service_pb2.GenerateTokenResponse()

    def _pydantic_to_proto(self, ticket: ExecutionTicket):
        """
        Converte ExecutionTicket Pydantic para Proto.

        Args:
            ticket: ExecutionTicket Pydantic

        Returns:
            ExecutionTicketProto
        """
        return ticket_service_pb2.ExecutionTicketProto(
            ticket_id=ticket.ticket_id,
            plan_id=ticket.plan_id,
            intent_id=ticket.intent_id,
            task_id=ticket.task_id,
            task_type=ticket.task_type.value,
            description=ticket.description,
            status=ticket.status.value,
            priority=ticket.priority.value,
            created_at=ticket.created_at if ticket.created_at else 0
        )
