from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import structlog

logger = structlog.get_logger()


class ValidationError(Exception):
    pass


class BaseTaskExecutor(ABC):
    '''Classe base abstrata para executores de tarefas'''

    def __init__(self, config, vault_client=None, code_forge_client=None, metrics=None):
        self.config = config
        self.vault_client = vault_client
        self.code_forge_client = code_forge_client
        self.metrics = metrics
        self.logger = logger.bind(service=self.__class__.__name__)
        self.logger.info(
            'executor_initialized',
            vault_enabled=bool(self.vault_client),
            code_forge_enabled=bool(self.code_forge_client)
        )

    @abstractmethod
    async def execute(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        '''
        Executar tarefa específica

        Returns:
            {
                'success': bool,
                'output': Any,
                'metadata': Dict[str, Any],
                'logs': List[str]
            }
        '''
        pass

    @abstractmethod
    def get_task_type(self) -> str:
        '''Retornar task_type suportado'''
        pass

    def validate_ticket(self, ticket: Dict[str, Any]):
        '''Validar campos obrigatórios do ticket'''
        required_fields = ['ticket_id', 'task_id', 'task_type', 'parameters']
        missing_fields = [f for f in required_fields if f not in ticket]

        if missing_fields:
            raise ValidationError(f'Missing required fields: {missing_fields}')

        if ticket.get('task_type') != self.get_task_type():
            raise ValidationError(
                f"Task type mismatch: expected {self.get_task_type()}, got {ticket.get('task_type')}"
            )

    def log_execution(self, ticket_id: str, message: str, level: str = 'info', **kwargs):
        '''Logar com contexto de ticket'''
        log_func = getattr(self.logger, level)
        log_func(
            message,
            ticket_id=ticket_id,
            executor=self.__class__.__name__,
            **kwargs
        )

    async def get_secret(self, path: str) -> Dict[str, Any]:
        '''Buscar secret no Vault se disponível.'''
        if not self.vault_client:
            return {}

        try:
            client = getattr(self.vault_client, 'vault_client', None) or self.vault_client
            if hasattr(client, 'read_secret'):
                return await client.read_secret(path) or {}
            return {}
        except Exception as exc:
            self.logger.warning('vault_secret_fetch_failed', path=path, error=str(exc))
            if getattr(self.config, 'vault_fail_open', True):
                return {}
            raise

    async def submit_code_generation(
        self,
        ticket_id: str,
        template_id: str,
        parameters: Dict[str, Any]
    ) -> Optional[str]:
        '''Wrapper para submit_generation_request do Code Forge.'''
        if not self.code_forge_client:
            self.logger.warning('code_forge_client_unavailable', ticket_id=ticket_id)
            return None

        try:
            return await self.code_forge_client.submit_generation_request(ticket_id, template_id, parameters)
        except Exception as exc:
            self.logger.error('code_forge_submission_failed', ticket_id=ticket_id, error=str(exc))
            return None
