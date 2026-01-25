"""
Wrapper para Temporal Client com Circuit Breaker.
"""
import asyncio
from typing import Optional, Any
from temporalio.client import Client, WorkflowHandle
import structlog

from neural_hive_resilience.circuit_breaker import MonitoredCircuitBreaker, CircuitBreakerError

logger = structlog.get_logger(__name__)


class TemporalClientWrapper:
    """
    Wrapper para Temporal Client com circuit breaker para resiliência.

    Protege operações críticas:
    - start_workflow()
    - get_workflow_handle()
    - query_workflow() via handle
    """

    def __init__(
        self,
        client: Client,
        service_name: str,
        circuit_breaker_enabled: bool = True,
        fail_max: int = 5,
        timeout_duration: int = 60,
        recovery_timeout: int = 30
    ):
        """
        Inicializa wrapper com circuit breaker.

        Args:
            client: Cliente Temporal original
            service_name: Nome do serviço para métricas
            circuit_breaker_enabled: Se circuit breaker está habilitado
            fail_max: Número de falhas para abrir circuito
            timeout_duration: Timeout em segundos
            recovery_timeout: Tempo de recuperação em segundos
        """
        self.client = client
        self.service_name = service_name
        self.circuit_breaker_enabled = circuit_breaker_enabled
        self.breaker: Optional[MonitoredCircuitBreaker] = None

        if circuit_breaker_enabled:
            self.breaker = MonitoredCircuitBreaker(
                service_name=service_name,
                circuit_name='temporal_client',
                fail_max=fail_max,
                timeout_duration=timeout_duration,
                recovery_timeout=recovery_timeout
            )
            logger.info(
                'Temporal client circuit breaker habilitado',
                fail_max=fail_max,
                timeout=timeout_duration,
                recovery_timeout=recovery_timeout
            )

    async def start_workflow(
        self,
        workflow: str,
        arg: Any,
        *,
        id: str,
        task_queue: str,
        **kwargs
    ) -> WorkflowHandle:
        """
        Inicia workflow protegido por circuit breaker.

        Args:
            workflow: Nome do workflow
            arg: Argumento do workflow
            id: ID do workflow
            task_queue: Task queue
            **kwargs: Argumentos adicionais

        Returns:
            Handle do workflow iniciado

        Raises:
            CircuitBreakerError: Se circuit breaker estiver aberto
        """
        if not self.circuit_breaker_enabled or self.breaker is None:
            return await self.client.start_workflow(
                workflow,
                arg,
                id=id,
                task_queue=task_queue,
                **kwargs
            )

        try:
            return await self.breaker.call_async(
                self.client.start_workflow,
                workflow,
                arg,
                id=id,
                task_queue=task_queue,
                **kwargs
            )
        except CircuitBreakerError:
            logger.error(
                'temporal_client_circuit_breaker_open',
                workflow_id=id,
                workflow=workflow
            )
            raise

    async def get_workflow_handle(
        self,
        workflow_id: str,
        *,
        run_id: Optional[str] = None,
        **kwargs
    ) -> WorkflowHandle:
        """
        Obtém handle de workflow protegido por circuit breaker.

        Args:
            workflow_id: ID do workflow
            run_id: Run ID (opcional)
            **kwargs: Argumentos adicionais

        Returns:
            Handle do workflow

        Raises:
            CircuitBreakerError: Se circuit breaker estiver aberto
        """
        if not self.circuit_breaker_enabled or self.breaker is None:
            return self.client.get_workflow_handle(
                workflow_id,
                run_id=run_id,
                **kwargs
            )

        try:
            # get_workflow_handle é síncrono, envolver em executor
            loop = asyncio.get_event_loop()

            async def _get_handle():
                return await loop.run_in_executor(
                    None,
                    lambda: self.client.get_workflow_handle(
                        workflow_id,
                        run_id=run_id,
                        **kwargs
                    )
                )

            return await self.breaker.call_async(_get_handle)
        except CircuitBreakerError:
            logger.error(
                'temporal_client_circuit_breaker_open',
                workflow_id=workflow_id,
                operation='get_workflow_handle'
            )
            raise

    async def query_workflow(
        self,
        workflow_id: str,
        query: str,
        *args,
        **kwargs
    ) -> Any:
        """
        Executa query em workflow protegido por circuit breaker.

        Args:
            workflow_id: ID do workflow
            query: Nome da query
            *args, **kwargs: Argumentos da query

        Returns:
            Resultado da query

        Raises:
            CircuitBreakerError: Se circuit breaker estiver aberto
        """
        handle = await self.get_workflow_handle(workflow_id)

        if not self.circuit_breaker_enabled or self.breaker is None:
            return await handle.query(query, *args, **kwargs)

        try:
            return await self.breaker.call_async(
                handle.query,
                query,
                *args,
                **kwargs
            )
        except CircuitBreakerError:
            logger.error(
                'temporal_client_circuit_breaker_open',
                workflow_id=workflow_id,
                query=query
            )
            raise

    def __getattr__(self, name):
        """
        Delega atributos não implementados para o client original.

        Permite acesso a métodos não críticos sem circuit breaker.
        """
        return getattr(self.client, name)
