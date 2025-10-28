from typing import Optional, Dict, Any
import httpx
import structlog

from ..models.execution_ticket import ExecutionTicket, TicketStatus

logger = structlog.get_logger()


class ExecutionTicketClient:
    """Cliente HTTP para Execution Ticket Service"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.client: Optional[httpx.AsyncClient] = None

    async def start(self):
        """Inicia o cliente HTTP"""
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=100)
        )
        logger.info('execution_ticket_client_started', base_url=self.base_url)

    async def stop(self):
        """Para o cliente HTTP"""
        if self.client:
            await self.client.aclose()
            logger.info('execution_ticket_client_stopped')

    async def get_ticket(self, ticket_id: str) -> Optional[ExecutionTicket]:
        """
        Busca ticket por ID

        Args:
            ticket_id: ID do ticket

        Returns:
            ExecutionTicket ou None se não encontrado
        """
        if not self.client:
            raise RuntimeError('Cliente não foi iniciado')

        try:
            response = await self.client.get(f'/api/v1/tickets/{ticket_id}')
            response.raise_for_status()

            data = response.json()
            return ExecutionTicket(**data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning('ticket_not_found', ticket_id=ticket_id)
                return None
            logger.error('get_ticket_failed', ticket_id=ticket_id, status=e.response.status_code)
            raise
        except Exception as e:
            logger.error('get_ticket_error', ticket_id=ticket_id, error=str(e))
            raise

    async def update_status(
        self,
        ticket_id: str,
        status: TicketStatus,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Atualiza status do ticket

        Args:
            ticket_id: ID do ticket
            status: Novo status
            metadata: Metadados adicionais
        """
        if not self.client:
            raise RuntimeError('Cliente não foi iniciado')

        try:
            payload = {
                'status': status.value,
                'metadata': metadata or {}
            }

            response = await self.client.patch(
                f'/api/v1/tickets/{ticket_id}/status',
                json=payload
            )
            response.raise_for_status()

            logger.info(
                'ticket_status_updated',
                ticket_id=ticket_id,
                status=status
            )

        except Exception as e:
            logger.error(
                'update_ticket_status_failed',
                ticket_id=ticket_id,
                status=status,
                error=str(e)
            )
            raise

    async def get_dependencies(self, ticket_id: str) -> list[ExecutionTicket]:
        """
        Busca tickets de dependências

        Args:
            ticket_id: ID do ticket

        Returns:
            Lista de tickets de dependências
        """
        if not self.client:
            raise RuntimeError('Cliente não foi iniciado')

        try:
            response = await self.client.get(f'/api/v1/tickets/{ticket_id}/dependencies')
            response.raise_for_status()

            data = response.json()
            return [ExecutionTicket(**t) for t in data]

        except Exception as e:
            logger.error('get_dependencies_failed', ticket_id=ticket_id, error=str(e))
            raise

    async def create_compensation_ticket(self, ticket_id: str, reason: str) -> str:
        """
        Cria ticket de compensação em caso de falha

        Args:
            ticket_id: ID do ticket original
            reason: Motivo da compensação

        Returns:
            ID do ticket de compensação criado
        """
        if not self.client:
            raise RuntimeError('Cliente não foi iniciado')

        try:
            payload = {
                'original_ticket_id': ticket_id,
                'reason': reason
            }

            response = await self.client.post(
                '/api/v1/tickets/compensation',
                json=payload
            )
            response.raise_for_status()

            data = response.json()
            compensation_ticket_id = data['ticket_id']

            logger.info(
                'compensation_ticket_created',
                original_ticket_id=ticket_id,
                compensation_ticket_id=compensation_ticket_id
            )

            return compensation_ticket_id

        except Exception as e:
            logger.error(
                'create_compensation_ticket_failed',
                ticket_id=ticket_id,
                error=str(e)
            )
            raise
