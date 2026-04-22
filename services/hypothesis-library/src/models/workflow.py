"""Hypothesis workflow and state machine."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.models.hypothesis import HypothesisStatus, utcnow


class TransitionError(Exception):
    """Erro em transição de estado inválida."""

    def __init__(
        self, from_status: HypothesisStatus, to_status: HypothesisStatus, reason: str = ""
    ):
        self.from_status = from_status
        self.to_status = to_status
        self.reason = reason
        message = f"Invalid transition: {from_status.value} -> {to_status.value}"
        if reason:
            message += f": {reason}"
        super().__init__(message)


class WorkflowTransition(BaseModel):
    """Registro de uma transição de estado."""

    from_status: HypothesisStatus = Field(..., description="Estado anterior")
    to_status: HypothesisStatus = Field(..., description="Novo estado")
    transitioned_at: datetime = Field(default_factory=utcnow, description="Timestamp da transição")
    transitioned_by: str = Field(..., description="Quem fez a transição")
    reason: str = Field(default="", description="Razão da transição")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")


class HypothesisWorkflow:
    """
    Máquina de estados para workflow de hipóteses.

    Transições válidas:
    - DRAFT -> PROPOSED (author)
    - DRAFT -> ARCHIVED (author)
    - PROPOSED -> APPROVED (reviewer)
    - PROPOSED -> REJECTED (reviewer)
    - PROPOSED -> DRAFT (author/reviewer - request changes)
    - APPROVED -> IN_TESTING (system/experimenter)
    - IN_TESTING -> COMPLETED (system - experiment done)
    - IN_TESTING -> REJECTED (system - experiment failed)
    - COMPLETED -> ACCEPTED (reviewer - validated)
    - COMPLETED -> REJECTED (reviewer - refuted)
    - ACCEPTED -> ARCHIVED (system - auto-archive after N days)
    - REJECTED -> ARCHIVED (author/reviewer)
    - ARCHIVED -> (terminal, no transitions out)
    """

    # Transições válidas: from_status -> set(of valid to_statuses)
    VALID_TRANSITIONS: dict[HypothesisStatus, set[HypothesisStatus]] = {
        HypothesisStatus.DRAFT: {
            HypothesisStatus.PROPOSED,
            HypothesisStatus.ARCHIVED,
        },
        HypothesisStatus.PROPOSED: {
            HypothesisStatus.APPROVED,
            HypothesisStatus.REJECTED,
            HypothesisStatus.DRAFT,
        },
        HypothesisStatus.APPROVED: {
            HypothesisStatus.IN_TESTING,
            HypothesisStatus.REJECTED,  # Cancelado antes do teste
        },
        HypothesisStatus.IN_TESTING: {
            HypothesisStatus.COMPLETED,
            HypothesisStatus.REJECTED,
        },
        HypothesisStatus.COMPLETED: {
            HypothesisStatus.ACCEPTED,
            HypothesisStatus.REJECTED,
        },
        HypothesisStatus.ACCEPTED: {
            HypothesisStatus.ARCHIVED,
        },
        HypothesisStatus.REJECTED: {
            HypothesisStatus.ARCHIVED,
            HypothesisStatus.DRAFT,  # Permitir re-proposta
        },
        HypothesisStatus.ARCHIVED: set(),  # Terminal state
    }

    # Quem pode fazer cada transição
    ROLE_REQUIREMENTS: dict[tuple[HypothesisStatus, HypothesisStatus], str] = {
        (HypothesisStatus.DRAFT, HypothesisStatus.PROPOSED): "author",
        (HypothesisStatus.DRAFT, HypothesisStatus.ARCHIVED): "author",
        (HypothesisStatus.PROPOSED, HypothesisStatus.APPROVED): "reviewer",
        (HypothesisStatus.PROPOSED, HypothesisStatus.REJECTED): "reviewer",
        (HypothesisStatus.PROPOSED, HypothesisStatus.DRAFT): "author_or_reviewer",
        (HypothesisStatus.APPROVED, HypothesisStatus.IN_TESTING): "system_or_author",
        (HypothesisStatus.APPROVED, HypothesisStatus.REJECTED): "reviewer",
        (HypothesisStatus.IN_TESTING, HypothesisStatus.COMPLETED): "system",
        (HypothesisStatus.IN_TESTING, HypothesisStatus.REJECTED): "system",
        (HypothesisStatus.COMPLETED, HypothesisStatus.ACCEPTED): "reviewer",
        (HypothesisStatus.COMPLETED, HypothesisStatus.REJECTED): "reviewer",
        (HypothesisStatus.ACCEPTED, HypothesisStatus.ARCHIVED): "system",
        (HypothesisStatus.REJECTED, HypothesisStatus.ARCHIVED): "author_or_reviewer",
        (HypothesisStatus.REJECTED, HypothesisStatus.DRAFT): "author",
    }

    @classmethod
    def validate_transition(
        cls,
        from_status: HypothesisStatus,
        to_status: HypothesisStatus,
        role: str = "author",
    ) -> None:
        """
        Valida se uma transição é permitida.

        Args:
            from_status: Status atual
            to_status: Status desejado
            role: Papel do usuário (author, reviewer, system)

        Raises:
            TransitionError: Se a transição não é válida
        """
        # Mesmo status - no-op
        if from_status == to_status:
            raise TransitionError(from_status, to_status, "Already in this state")

        # Verificar se transição existe
        valid_targets = cls.VALID_TRANSITIONS.get(from_status, set())
        if to_status not in valid_targets:
            raise TransitionError(
                from_status,
                to_status,
                f"Valid transitions from {from_status.value}: {[s.value for s in valid_targets]}",
            )

        # Verificar permissão
        required_role = cls.ROLE_REQUIREMENTS.get((from_status, to_status))
        if required_role and not cls._has_role_permission(role, required_role):
            raise TransitionError(
                from_status, to_status, f"Requires role '{required_role}', got '{role}'"
            )

    @classmethod
    def _has_role_permission(cls, user_role: str, required_role: str) -> bool:
        """Verifica se o usuário tem a permissão necessária."""
        if required_role == "system":
            return user_role == "system"

        if "or" in required_role:
            return any(r in user_role for r in required_role.split("_or_"))

        return user_role == required_role or user_role == "admin"

    @classmethod
    def get_allowed_transitions(
        cls,
        from_status: HypothesisStatus,
        role: str = "author",
    ) -> list[HypothesisStatus]:
        """
        Retorna transições permitidas para um status e papel.

        Args:
            from_status: Status atual
            role: Papel do usuário

        Returns:
            Lista de status permitidos
        """
        all_allowed = cls.VALID_TRANSITIONS.get(from_status, set())
        allowed = []

        for target in all_allowed:
            try:
                cls.validate_transition(from_status, target, role)
                allowed.append(target)
            except TransitionError:
                pass

        return allowed

    @classmethod
    def can_propose(cls, status: HypothesisStatus) -> bool:
        """Verifica se pode propor para revisão."""
        return status == HypothesisStatus.DRAFT

    @classmethod
    def can_approve(cls, status: HypothesisStatus) -> bool:
        """Verifica se pode aprovar."""
        return status == HypothesisStatus.PROPOSED

    @classmethod
    def can_start_test(cls, status: HypothesisStatus) -> bool:
        """Verifica se pode iniciar teste."""
        return status == HypothesisStatus.APPROVED

    @classmethod
    def can_complete(cls, status: HypothesisStatus) -> bool:
        """Verifica se pode completar (marcar como aceita/rejeitada)."""
        return status == HypothesisStatus.COMPLETED

    @classmethod
    def can_archive(cls, status: HypothesisStatus) -> bool:
        """Verifica se pode arquivar."""
        return status in {
            HypothesisStatus.ACCEPTED,
            HypothesisStatus.REJECTED,
            HypothesisStatus.DRAFT,
        }

    @classmethod
    def is_terminal(cls, status: HypothesisStatus) -> bool:
        """Verifica se é estado terminal."""
        return status == HypothesisStatus.ARCHIVED

    @classmethod
    def get_next_suggested(cls, status: HypothesisStatus) -> HypothesisStatus | None:
        """
        Sugere o próximo estado no workflow normal.

        Args:
            status: Status atual

        Returns:
            Próximo status sugerido ou None
        """
        flow_suggestions = {
            HypothesisStatus.DRAFT: HypothesisStatus.PROPOSED,
            HypothesisStatus.PROPOSED: HypothesisStatus.APPROVED,
            HypothesisStatus.APPROVED: HypothesisStatus.IN_TESTING,
            HypothesisStatus.IN_TESTING: HypothesisStatus.COMPLETED,
            HypothesisStatus.COMPLETED: HypothesisStatus.ACCEPTED,
            HypothesisStatus.ACCEPTED: HypothesisStatus.ARCHIVED,
            HypothesisStatus.REJECTED: HypothesisStatus.ARCHIVED,
        }
        return flow_suggestions.get(status)
