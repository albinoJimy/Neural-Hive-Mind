import structlog
import asyncio
from typing import Dict, List
from datetime import datetime

logger = structlog.get_logger()


class DependencyFailedError(Exception):
    pass


class DependencyTimeoutError(Exception):
    pass


class DependencyCoordinator:
    '''Coordenador de dependências entre tickets'''

    def __init__(self, config, ticket_client, metrics=None):
        self.config = config
        self.ticket_client = ticket_client
        self.metrics = metrics
        self.logger = logger.bind(service='dependency_coordinator')
        self._status_cache: Dict[str, Dict] = {}

    async def wait_for_dependencies(self, ticket: Dict) -> bool:
        '''Aguardar conclusão de dependências'''
        dependencies = ticket.get('dependencies', [])

        if not dependencies:
            self.logger.debug('no_dependencies', ticket_id=ticket.get('ticket_id'))
            return True

        ticket_id = ticket.get('ticket_id')
        self.logger.info(
            'waiting_for_dependencies',
            ticket_id=ticket_id,
            dependencies=dependencies
        )

        start_time = datetime.now()

        for attempt in range(self.config.dependency_check_max_attempts):
            all_completed = True
            failed_deps = []

            for dep_ticket_id in dependencies:
                try:
                    status = await self._check_dependency_status(dep_ticket_id)

                    if status == 'COMPLETED':
                        continue
                    elif status == 'FAILED':
                        failed_deps.append(dep_ticket_id)
                        all_completed = False
                        break
                    else:  # PENDING ou RUNNING
                        all_completed = False

                except Exception as e:
                    self.logger.warning(
                        'dependency_check_failed',
                        ticket_id=ticket_id,
                        dependency=dep_ticket_id,
                        error=str(e)
                    )
                    all_completed = False

            if failed_deps:
                self.logger.error(
                    'dependencies_failed',
                    ticket_id=ticket_id,
                    failed_dependencies=failed_deps
                )
                if self.metrics:
                    self.metrics.dependency_checks_total.labels(result='failed').inc()
                raise DependencyFailedError(f'Dependencies failed: {failed_deps}')

            if all_completed:
                duration = (datetime.now() - start_time).total_seconds()
                self.logger.info(
                    'dependencies_ready',
                    ticket_id=ticket_id,
                    dependencies=dependencies,
                    wait_duration_seconds=duration
                )
                if self.metrics:
                    self.metrics.dependency_checks_total.labels(result='success').inc()
                    self.metrics.dependency_wait_duration_seconds.observe(duration)
                return True

            # Aguardar antes da próxima verificação
            await asyncio.sleep(self.config.dependency_check_interval_seconds)

        # Timeout
        duration = (datetime.now() - start_time).total_seconds()
        self.logger.error(
            'dependency_timeout',
            ticket_id=ticket_id,
            dependencies=dependencies,
            wait_duration_seconds=duration
        )
        if self.metrics:
            self.metrics.dependency_checks_total.labels(result='timeout').inc()
        raise DependencyTimeoutError(f'Timeout waiting for dependencies: {dependencies}')

    async def _check_dependency_status(self, dependency_ticket_id: str) -> str:
        '''Verificar status de um ticket de dependência'''
        # Verificar cache (5s TTL)
        if dependency_ticket_id in self._status_cache:
            cached = self._status_cache[dependency_ticket_id]
            age = (datetime.now() - cached['timestamp']).total_seconds()
            if age < 5:
                return cached['status']

        # Consultar API
        ticket = await self.ticket_client.get_ticket(dependency_ticket_id)
        status = ticket.get('status')

        # Atualizar cache
        self._status_cache[dependency_ticket_id] = {
            'status': status,
            'timestamp': datetime.now()
        }

        return status
