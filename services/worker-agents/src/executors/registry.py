import structlog
from typing import Dict
from .base_executor import BaseTaskExecutor

logger = structlog.get_logger()


class ExecutorNotFoundError(Exception):
    pass


class TaskExecutorRegistry:
    '''Registry de executores de tarefas'''

    def __init__(self, config):
        self.config = config
        self.executors: Dict[str, BaseTaskExecutor] = {}
        self.logger = logger.bind(service='task_executor_registry')

    def register_executor(self, executor: BaseTaskExecutor):
        '''Registrar executor por task_type'''
        task_type = executor.get_task_type()
        self.executors[task_type] = executor

        self.logger.info(
            'executor_registered',
            task_type=task_type,
            executor_class=executor.__class__.__name__
        )

        # TODO: Incrementar métrica worker_agent_executors_registered_total{task_type=...}

    def get_executor(self, task_type: str) -> BaseTaskExecutor:
        '''Obter executor por task_type'''
        executor = self.executors.get(task_type)

        if not executor:
            raise ExecutorNotFoundError(f'No executor found for task_type: {task_type}')

        return executor

    def list_supported_task_types(self):
        '''Listar task_types suportados'''
        return list(self.executors.keys())

    def validate_configuration(self):
        '''Validar que todos os task_types configurados têm executores'''
        registered_types = set(self.executors.keys())
        configured_types = set(self.config.supported_task_types)

        missing_executors = configured_types - registered_types

        if missing_executors:
            self.logger.warning(
                'missing_executors',
                task_types=list(missing_executors)
            )

        self.logger.info(
            'registry_validated',
            registered_types=list(registered_types),
            configured_types=list(configured_types)
        )
