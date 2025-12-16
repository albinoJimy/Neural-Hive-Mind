import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Callable
from uuid import uuid4

import structlog

from src.models.remediation_models import RemediationRequest

logger = structlog.get_logger()


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
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


class RemediationManager:
    """Gerencia estado de remediações em execução."""

    def __init__(self, redis_client=None, default_timeout_seconds: int = 300):
        self.redis_client = redis_client
        self.default_timeout_seconds = default_timeout_seconds
        self.active_remediations: Dict[str, RemediationState] = {}

    def start_remediation(
        self,
        request: RemediationRequest,
        total_actions: int = 0
    ) -> RemediationState:
        """Cria um RemediationState inicial e registra em memória/Redis."""
        remediation_id = request.remediation_id or str(uuid4())

        state = RemediationState(
            remediation_id=remediation_id,
            incident_id=request.incident_id,
            playbook_name=request.playbook_name,
            status=RemediationStatus.PENDING,
            total_actions=total_actions,
            metadata={
                "execution_mode": request.execution_mode,
                "parameters": request.parameters
            }
        )

        self.active_remediations[remediation_id] = state
        asyncio.create_task(self._persist_state(state))

        logger.info(
            "remediation_manager.state_created",
            remediation_id=remediation_id,
            playbook=request.playbook_name,
            total_actions=total_actions
        )

        return state

    async def execute_remediation(
        self,
        state: RemediationState,
        executor,
        request: RemediationRequest,
        on_completed: Optional[Callable[[RemediationState], None]] = None
    ):
        """Executa playbook e atualiza progresso/estado."""
        state.status = RemediationStatus.RUNNING
        state.started_at = datetime.utcnow().isoformat()
        await self._persist_state(state)

        async def on_action_completed(action_result: dict):
            state.actions_completed += 1
            if state.total_actions > 0:
                state.progress = min(1.0, state.actions_completed / state.total_actions)
            await self._persist_state(state)

        async def on_playbook_completed(result: dict):
            state.result = result
            state.status = RemediationStatus.COMPLETED if result.get("success") else RemediationStatus.FAILED
            state.error = result.get("error")
            state.completed_at = datetime.utcnow().isoformat()
            await self._persist_state(state)
            if on_completed:
                on_completed(state)

        try:
            await executor.execute_playbook(
                request.playbook_name,
                request.parameters,
                on_action_completed=on_action_completed,
                on_playbook_completed=on_playbook_completed,
                timeout_seconds=self.default_timeout_seconds
            )
        except asyncio.TimeoutError:
            state.status = RemediationStatus.TIMEOUT
            state.error = "Playbook timeout"
            state.completed_at = datetime.utcnow().isoformat()
            await self._persist_state(state)
            logger.warning(
                "remediation_manager.playbook_timeout",
                remediation_id=state.remediation_id,
                playbook=state.playbook_name
            )
        except asyncio.CancelledError:
            state.status = RemediationStatus.CANCELLED
            state.error = "Cancelled"
            state.completed_at = datetime.utcnow().isoformat()
            await self._persist_state(state)
            logger.info(
                "remediation_manager.playbook_cancelled",
                remediation_id=state.remediation_id
            )
        except Exception as exc:  # noqa: BLE001 - fail-open
            state.status = RemediationStatus.FAILED
            state.error = str(exc)
            state.completed_at = datetime.utcnow().isoformat()
            await self._persist_state(state)
            logger.error(
                "remediation_manager.playbook_failed",
                remediation_id=state.remediation_id,
                error=str(exc)
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
        state.completed_at = datetime.utcnow().isoformat()
        asyncio.create_task(self._persist_state(state))

        logger.info("remediation_manager.remediation_cancelled", remediation_id=remediation_id)
        return state

    async def _persist_state(self, state: RemediationState):
        """Persiste estado no Redis se disponível (fail-open)."""
        if not self.redis_client:
            return

        try:
            await self.redis_client.set(
                f"remediation:{state.remediation_id}",
                state.to_dict(),
                ex=3600
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "remediation_manager.redis_persist_failed",
                remediation_id=state.remediation_id,
                error=str(exc)
            )
