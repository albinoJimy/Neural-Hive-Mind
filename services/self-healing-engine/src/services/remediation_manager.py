import asyncio
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

import structlog
from opentelemetry.trace import Status, StatusCode
from prometheus_client import Counter, Histogram

from neural_hive_observability import get_tracer
from src.models.remediation_models import RemediationRequest

logger = structlog.get_logger()
tracer = get_tracer()

# Métricas Prometheus globais para RemediationManager
_mttr_seconds_total = Histogram(
    "self_healing_mttr_seconds_total",
    "MTTR (Mean Time To Remediate) total em segundos",
    ["incident_type", "service_name", "remediation_type"],
    buckets=[60, 300, 900, 1800, 3600, 7200],
)

_remediations_total = Counter(
    "self_healing_remediations_total",
    "Total de remediações executadas",
    ["remediation_type", "status", "playbook_name"],
)

_remediation_duration_seconds = Histogram(
    "self_healing_remediation_duration_seconds",
    "Duração das remediações",
    ["remediation_type", "playbook_name", "status"],
    buckets=[10, 30, 60, 120, 300, 600],
)


class RemediationStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"


@dataclass
class RemediationState:
    remediation_id: str
    incident_id: str
    playbook_name: str
    status: RemediationStatus = RemediationStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    progress: float = 0.0
    actions_completed: int = 0
    total_actions: int = 0
    result: Optional[dict] = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class RemediationManager:
    """Gerencia estado de remediações em execução."""

    def __init__(self, redis_client=None, default_timeout_seconds: int = 300):
        self.redis_client = redis_client
        self.default_timeout_seconds = default_timeout_seconds
        self.active_remediations: dict[str, RemediationState] = {}

        # Métricas Prometheus para RemediationManager (globais)
        self._mttr_seconds_total = _mttr_seconds_total
        self._remediations_total = _remediations_total
        self._remediation_duration_seconds = _remediation_duration_seconds

    def start_remediation(
        self, request: RemediationRequest, total_actions: int = 0
    ) -> RemediationState:
        """Cria um RemediationState inicial e registra em memória/Redis."""
        remediation_id = request.remediation_id or str(uuid4())
        remediation_type = request.parameters.get("incident_type", "unknown")
        playbook_name = request.playbook_name

        self._remediations_total.labels(
            remediation_type=remediation_type, status="pending", playbook_name=playbook_name
        ).inc()

        state = RemediationState(
            remediation_id=remediation_id,
            incident_id=request.incident_id,
            playbook_name=playbook_name,
            status=RemediationStatus.PENDING,
            total_actions=total_actions,
            metadata={"execution_mode": request.execution_mode, "parameters": request.parameters},
        )

        self.active_remediations[remediation_id] = state
        asyncio.create_task(self._persist_state(state))

        logger.info(
            "remediation_manager.state_created",
            remediation_id=remediation_id,
            playbook=request.playbook_name,
            total_actions=total_actions,
        )

        return state

    async def execute_remediation(
        self,
        state: RemediationState,
        executor,
        request: RemediationRequest,
        on_completed: Optional[Callable[[RemediationState], None]] = None,
    ):
        """Executa playbook e atualiza progresso/estado."""
        remediation_start_time = time.time()
        remediation_type = request.parameters.get("incident_type", "unknown")
        playbook_name = request.playbook_name
        service_name = request.parameters.get("service_name", "unknown")

        with tracer.start_as_current_span("remediation_manager.execute_remediation") as span:
            span.set_attribute("remediation_id", state.remediation_id)
            span.set_attribute("remediation_type", remediation_type)
            span.set_attribute("playbook_name", playbook_name)
            span.set_attribute("service_name", service_name)

            self._remediations_total.labels(
                remediation_type=remediation_type, status="started", playbook_name=playbook_name
            ).inc()

            state.status = RemediationStatus.RUNNING
            state.started_at = datetime.now(UTC).isoformat()
            await self._persist_state(state)

            async def on_action_completed(action_result: dict):
                state.actions_completed += 1
                if state.total_actions > 0:
                    state.progress = min(1.0, state.actions_completed / state.total_actions)
                await self._persist_state(state)

            async def on_playbook_completed(result: dict):
                total_duration = time.time() - remediation_start_time

                state.result = result
                final_status = (
                    RemediationStatus.COMPLETED
                    if result.get("success")
                    else RemediationStatus.FAILED
                )
                state.status = final_status
                state.error = result.get("error")
                state.completed_at = datetime.now(UTC).isoformat()

                # Registrar métricas de conclusão
                self._remediation_duration_seconds.labels(
                    remediation_type=remediation_type,
                    playbook_name=playbook_name,
                    status=final_status.value.lower(),
                ).observe(total_duration)

                self._remediations_total.labels(
                    remediation_type=remediation_type,
                    status=final_status.value.lower(),
                    playbook_name=playbook_name,
                ).inc()

                # MTTR: tempo total desde detecção até conclusão
                incident_type = request.parameters.get("incident_type", "unknown")
                self._mttr_seconds_total.labels(
                    incident_type=incident_type,
                    service_name=service_name,
                    remediation_type=remediation_type,
                ).observe(total_duration)

                span.set_status(
                    Status(StatusCode.OK)
                    if final_status == RemediationStatus.COMPLETED
                    else Status(StatusCode.ERROR)
                )
                span.set_attribute("final_status", final_status.value)
                span.set_attribute("duration_seconds", str(total_duration))

                await self._persist_state(state)
                if on_completed:
                    on_completed(state)

            try:
                await executor.execute_playbook(
                    request.playbook_name,
                    request.parameters,
                    on_action_completed=on_action_completed,
                    on_playbook_completed=on_playbook_completed,
                    timeout_seconds=self.default_timeout_seconds,
                )
            except asyncio.TimeoutError:
                total_duration = time.time() - remediation_start_time
                state.status = RemediationStatus.TIMEOUT
                state.error = "Playbook timeout"
                state.completed_at = datetime.now(UTC).isoformat()

                # Registrar métricas de timeout
                self._remediation_duration_seconds.labels(
                    remediation_type=remediation_type,
                    playbook_name=playbook_name,
                    status="timeout",
                ).observe(total_duration)

                self._remediations_total.labels(
                    remediation_type=remediation_type,
                    status="timeout",
                    playbook_name=playbook_name,
                ).inc()

                await self._persist_state(state)
                logger.warning(
                    "remediation_manager.playbook_timeout",
                    remediation_id=state.remediation_id,
                    playbook=state.playbook_name,
                )
            except asyncio.CancelledError:
                total_duration = time.time() - remediation_start_time
                state.status = RemediationStatus.CANCELLED
                state.error = "Cancelled"
                state.completed_at = datetime.now(UTC).isoformat()

                # Registrar métricas de cancelamento
                self._remediation_duration_seconds.labels(
                    remediation_type=remediation_type,
                    playbook_name=playbook_name,
                    status="cancelled",
                ).observe(total_duration)

                self._remediations_total.labels(
                    remediation_type=remediation_type,
                    status="cancelled",
                    playbook_name=playbook_name,
                ).inc()

                await self._persist_state(state)
                logger.info(
                    "remediation_manager.playbook_cancelled", remediation_id=state.remediation_id
                )
            except Exception as exc:  # - fail-open
                total_duration = time.time() - remediation_start_time
                state.status = RemediationStatus.FAILED
                state.error = str(exc)
                state.completed_at = datetime.now(UTC).isoformat()

                # Registrar métricas de falha
                self._remediation_duration_seconds.labels(
                    remediation_type=remediation_type,
                    playbook_name=playbook_name,
                    status="failed",
                ).observe(total_duration)

                self._remediations_total.labels(
                    remediation_type=remediation_type,
                    status="failed",
                    playbook_name=playbook_name,
                ).inc()

                await self._persist_state(state)
                logger.error(
                    "remediation_manager.playbook_failed",
                    remediation_id=state.remediation_id,
                    error=str(exc),
                )

    def update_status(self, remediation_id: str, **kwargs) -> Optional[RemediationState]:
        """Atualiza atributos do estado e persiste (fail-open)."""
        state = self.active_remediations.get(remediation_id)
        if not state:
            return None

        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)

        asyncio.create_task(self._persist_state(state))
        return state

    def get_status(self, remediation_id: str) -> Optional[RemediationState]:
        """Retorna estado atual (None se inexistente)."""
        return self.active_remediations.get(remediation_id)

    def cancel_remediation(self, remediation_id: str) -> Optional[RemediationState]:
        """Marca remediação como cancelada (não interrompe execução em andamento)."""
        state = self.active_remediations.get(remediation_id)
        if not state:
            return None

        state.status = RemediationStatus.CANCELLED
        state.completed_at = datetime.now(UTC).isoformat()
        asyncio.create_task(self._persist_state(state))

        logger.info("remediation_manager.remediation_cancelled", remediation_id=remediation_id)
        return state

    async def _persist_state(self, state: RemediationState):
        """Persiste estado no Redis se disponível (fail-open)."""
        if not self.redis_client:
            return

        try:
            await self.redis_client.set(
                f"remediation:{state.remediation_id}", state.to_dict(), ex=3600
            )
        except Exception as exc:
            logger.warning(
                "remediation_manager.redis_persist_failed",
                remediation_id=state.remediation_id,
                error=str(exc),
            )
