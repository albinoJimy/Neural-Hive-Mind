from abc import ABC, abstractmethod
from typing import Dict, Any
import structlog

logger = structlog.get_logger()


class ValidationError(Exception):
    pass


class BaseTaskExecutor(ABC):
    '''Classe base abstrata para executores de tarefas'''

    def __init__(self, config):
        self.config = config
        self.logger = logger.bind(service=self.__class__.__name__)

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
