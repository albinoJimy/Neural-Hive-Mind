import httpx
import structlog
from typing import Dict, List, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()


class TicketNotFoundError(Exception):
    pass


class ExecutionTicketClient:
    '''Cliente HTTP para Execution Ticket Service'''

    def __init__(self, config, metrics=None):
        self.config = config
        self.metrics = metrics
        self.logger = logger.bind(service='execution_ticket_client')
        self.client = None
        self._token_cache: Dict[str, Dict[str, Any]] = {}

    async def initialize(self):
        '''Inicializar cliente HTTP'''
        try:
            self.client = httpx.AsyncClient(
                base_url=self.config.execution_ticket_service_url,
                timeout=self.config.ticket_api_timeout_seconds,
                headers={'User-Agent': f'worker-agents/{self.config.service_version}'}
            )
            self.logger.info(
                'execution_ticket_client_initialized',
                base_url=self.config.execution_ticket_service_url
            )
        except Exception as e:
            self.logger.error('execution_ticket_client_init_failed', error=str(e))
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def get_ticket(self, ticket_id: str) -> Dict[str, Any]:
        '''Obter ticket por ID'''
        status = 'error'
        try:
            response = await self.client.get(f'/api/v1/tickets/{ticket_id}')

            if response.status_code == 404:
                raise TicketNotFoundError(f'Ticket not found: {ticket_id}')

            response.raise_for_status()

            self.logger.debug('ticket_retrieved', ticket_id=ticket_id)
            if response.status_code == 200:
                status = 'success'

            return response.json()

        except TicketNotFoundError:
            raise
        except Exception as e:
            self.logger.error('get_ticket_failed', ticket_id=ticket_id, error=str(e))
            raise
        finally:
            if self.metrics:
                self.metrics.ticket_api_calls_total.labels(method='get_ticket', status=status).inc()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def update_ticket_status(
        self,
        ticket_id: str,
        status: str,
        error_message: Optional[str] = None,
        actual_duration_ms: Optional[int] = None
    ) -> Dict[str, Any]:
        '''Atualizar status do ticket'''
        api_status = 'error'
        try:
            payload = {
                'status': status,
                'error_message': error_message,
                'actual_duration_ms': actual_duration_ms
            }

            response = await self.client.patch(
                f'/api/v1/tickets/{ticket_id}/status',
                json=payload
            )
            response.raise_for_status()

            self.logger.info(
                'ticket_status_updated',
                ticket_id=ticket_id,
                status=status,
                error_message=error_message
            )

            if self.metrics:
                self.metrics.ticket_status_updates_total.labels(status=status).inc()

            api_status = 'success'
            return response.json()

        except Exception as e:
            self.logger.error(
                'update_ticket_status_failed',
                ticket_id=ticket_id,
                status=status,
                error=str(e)
            )
            raise
        finally:
            if self.metrics:
                self.metrics.ticket_api_calls_total.labels(method='update_ticket_status', status=api_status).inc()

    async def get_ticket_token(self, ticket_id: str) -> str:
        '''Obter token JWT para ticket'''
        try:
            # Verificar cache
            if ticket_id in self._token_cache:
                cached = self._token_cache[ticket_id]
                # TODO: Verificar expiração do token
                return cached['access_token']

            response = await self.client.get(f'/api/v1/tickets/{ticket_id}/token')
            response.raise_for_status()

            token_data = response.json()
            self._token_cache[ticket_id] = token_data

            self.logger.debug('ticket_token_obtained', ticket_id=ticket_id)
            if self.metrics:
                self.metrics.ticket_tokens_obtained_total.inc()

            return token_data['access_token']

        except Exception as e:
            self.logger.error('get_ticket_token_failed', ticket_id=ticket_id, error=str(e))
            raise

    async def list_tickets(
        self,
        plan_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        '''Listar tickets com filtros'''
        try:
            params = {}
            if plan_id:
                params['plan_id'] = plan_id
            if status:
                params['status'] = status

            response = await self.client.get('/api/v1/tickets', params=params)
            response.raise_for_status()

            self.logger.debug('tickets_listed', plan_id=plan_id, status=status)

            return response.json()

        except Exception as e:
            self.logger.error('list_tickets_failed', error=str(e))
            raise

    async def close(self):
        '''Fechar cliente HTTP'''
        if self.client:
            await self.client.aclose()
            self.logger.info('execution_ticket_client_closed')
