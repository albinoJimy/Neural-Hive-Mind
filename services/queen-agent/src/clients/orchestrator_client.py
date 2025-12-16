import structlog
from typing import Optional

from neural_hive_resilience.circuit_breaker import MonitoredCircuitBreaker, CircuitBreakerError
from ..config import Settings
from ..models import QoSAdjustment


logger = structlog.get_logger()


class OrchestratorClient:
    """Cliente gRPC para Orchestrator Dynamic (stub para MVP)"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.grpc_host = settings.ORCHESTRATOR_GRPC_HOST
        self.grpc_port = settings.ORCHESTRATOR_GRPC_PORT
        self.circuit_breaker_enabled: bool = getattr(settings, "CIRCUIT_BREAKER_ENABLED", False)
        self.orchestrator_breaker: Optional[MonitoredCircuitBreaker] = None

    async def initialize(self) -> None:
        """Inicializar cliente gRPC"""
        # TODO: Implementar criação de canal gRPC quando Orchestrator expor API de ajustes
        if self.circuit_breaker_enabled:
            self.orchestrator_breaker = MonitoredCircuitBreaker(
                service_name=self.settings.SERVICE_NAME,
                circuit_name="orchestrator_grpc",
                fail_max=self.settings.CIRCUIT_BREAKER_FAIL_MAX,
                timeout_duration=self.settings.CIRCUIT_BREAKER_TIMEOUT,
                recovery_timeout=self.settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
                expected_exception=Exception
            )
        logger.info("orchestrator_client_initialized", host=self.grpc_host, port=self.grpc_port)

    async def close(self) -> None:
        """Fechar canal gRPC"""
        logger.info("orchestrator_client_closed")

    async def adjust_qos(self, adjustment: QoSAdjustment) -> bool:
        """Enviar ajuste de QoS (stub)"""
        async def _adjust():
            logger.info(
                "qos_adjustment_requested",
                adjustment_id=adjustment.adjustment_id,
                adjustment_type=adjustment.adjustment_type.value,
                workflow_id=adjustment.target_workflow_id,
                reason=adjustment.reason
            )
            return True

        return await self._execute_with_breaker(self.orchestrator_breaker, _adjust)

    async def pause_workflow(self, workflow_id: str, reason: str) -> bool:
        """Pausar workflow (stub)"""
        async def _pause():
            logger.info("workflow_pause_requested", workflow_id=workflow_id, reason=reason)
            return True

        return await self._execute_with_breaker(self.orchestrator_breaker, _pause)

    async def resume_workflow(self, workflow_id: str) -> bool:
        """Retomar workflow (stub)"""
        async def _resume():
            logger.info("workflow_resume_requested", workflow_id=workflow_id)
            return True

        return await self._execute_with_breaker(self.orchestrator_breaker, _resume)

    async def trigger_replanning(self, plan_id: str, reason: str) -> bool:
        """Acionar replanejamento (stub)"""
        async def _replan():
            logger.info("replanning_triggered", plan_id=plan_id, reason=reason)
            return True

        return await self._execute_with_breaker(self.orchestrator_breaker, _replan)

    async def start_workflow(self, workflow_id: str, payload: Optional[dict] = None) -> bool:
        """Iniciar workflow no Orchestrator (stub protegido por circuit breaker)."""
        async def _start():
            logger.info(
                "orchestrator_workflow_start",
                workflow_id=workflow_id,
                payload=bool(payload)
            )
            return True

        try:
            return await self._execute_with_breaker(self.orchestrator_breaker, _start)
        except CircuitBreakerError:
            logger.warning(
                "orchestrator_circuit_open",
                operation="start_workflow",
                workflow_id=workflow_id
            )
            raise

    async def signal_workflow(self, workflow_id: str, signal_name: str, input_payload: Optional[dict] = None) -> bool:
        """Enviar sinal para workflow em execução (stub protegido por circuit breaker)."""
        async def _signal():
            logger.info(
                "orchestrator_workflow_signal",
                workflow_id=workflow_id,
                signal=signal_name,
                payload=bool(input_payload)
            )
            return True

        try:
            return await self._execute_with_breaker(self.orchestrator_breaker, _signal)
        except CircuitBreakerError:
            logger.warning(
                "orchestrator_circuit_open",
                operation="signal_workflow",
                workflow_id=workflow_id,
                signal=signal_name
            )
            raise

    async def _execute_with_breaker(self, breaker: Optional[MonitoredCircuitBreaker], func, *args, **kwargs):
        """Executa chamadas gRPC protegidas por circuit breaker quando habilitado."""
        if not self.circuit_breaker_enabled or breaker is None:
            return await func(*args, **kwargs)

        return await breaker.call_async(func, *args, **kwargs)
