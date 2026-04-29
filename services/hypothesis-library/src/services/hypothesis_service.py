"""Service para gerenciamento de hipóteses."""

from __future__ import annotations

import logging
from datetime import timezone
from typing import Any

from src.config.settings import get_settings
from src.models.hypothesis import (
    Hypothesis,
    HypothesisCreate,
    HypothesisFilter,
    HypothesisResults,
    HypothesisStatus,
    HypothesisUpdate,
)
from src.models.hypothesis_version import HypothesisVersion
from src.models.workflow import (
    HypothesisWorkflow,
    TransitionError,
    WorkflowTransition,
)
from src.repositories.hypothesis_repository import HypothesisRepository
from src.services.versioning_service import VersioningService

logger = logging.getLogger(__name__)
UTC = timezone.utc


class HypothesisService:
    """Service para gerenciar hipóteses com workflow e versionamento."""

    def __init__(
        self,
        hypothesis_repository: HypothesisRepository,
        versioning_service: VersioningService | None = None,
    ):
        """
        Inicializa service.

        Args:
            hypothesis_repository: Repository de hipóteses
            versioning_service: Service de versionamento (opcional)
        """
        self.repository = hypothesis_repository
        self.versioning = versioning_service
        self.settings = get_settings()

    async def create(self, create_data: HypothesisCreate, author: str) -> Hypothesis:
        """
        Cria nova hipótese.

        Args:
            create_data: Dados para criação
            author: Autor da hipótese

        Returns:
            Hipótese criada
        """
        data_dict = create_data.model_dump()
        data_dict["author"] = author

        hypothesis = Hypothesis(
            **data_dict,
            status=HypothesisStatus.DRAFT,
        )

        created = await self.repository.create(hypothesis)

        # Criar versão inicial se versionamento habilitado
        if self.versioning and self.settings.enable_versioning:
            await self.versioning.create_version(
                hypothesis=created,
                created_by=author,
                change_reason="Versão inicial",
                change_type="create",
            )

        logger.info(
            f"hypothesis_created: hypothesis_id={created.hypothesis_id}, title={created.title}, author={author}"
        )

        return created

    async def get_by_id(self, hypothesis_id: str) -> Hypothesis | None:
        """
        Busca hipótese por ID.

        Args:
            hypothesis_id: ID da hipótese

        Returns:
            Hipótese ou None
        """
        return await self.repository.get_by_id(hypothesis_id)

    async def list(self, filters: HypothesisFilter | None = None) -> dict[str, Any]:
        """
        Lista hipóteses com filtros.

        Args:
            filters: Filtros de busca

        Returns:
            Dict com resultados paginados
        """
        return await self.repository.list_by_filters(filters)

    async def update(
        self,
        hypothesis_id: str,
        update_data: HypothesisUpdate,
        updated_by: str,
        create_version: bool = True,
    ) -> Hypothesis | None:
        """
        Atualiza hipótese.

        Args:
            hypothesis_id: ID da hipótese
            update_data: Dados para atualização
            updated_by: Usuário que está atualizando
            create_version: Se deve criar nova versão

        Returns:
            Hipótese atualizada ou None
        """
        hypothesis = await self.get_by_id(hypothesis_id)
        if not hypothesis:
            return None

        # Buscar snapshot anterior para versionamento
        previous_snapshot = None
        if self.versioning and create_version:
            previous_snapshot = hypothesis.to_dict()

        # Aplicar atualizações
        updates = update_data.model_dump(exclude_unset=True)
        updated = await self.repository.update(hypothesis_id, updates)

        if not updated:
            return None

        # Criar nova versão se habilitado
        if self.versioning and create_version and self.settings.enable_versioning:
            # Atualizar número da versão
            updated.current_version += 1
            updated.versions.append(updated.current_version)
            await self.repository.update(
                hypothesis_id,
                {
                    "current_version": updated.current_version,
                    "versions": updated.versions,
                },
            )

            await self.versioning.create_version(
                hypothesis=updated,
                created_by=updated_by,
                change_reason=updates.get("change_reason", "Atualização"),
                change_type="update",
                previous_snapshot=previous_snapshot,
            )

        logger.info(f"hypothesis_updated: hypothesis_id={hypothesis_id}, updated_by={updated_by}")

        return updated

    async def propose(
        self,
        hypothesis_id: str,
        proposed_by: str,
        reason: str = "",
    ) -> tuple[Hypothesis | None, WorkflowTransition | None]:
        """
        Propõe hipótese para revisão.

        Args:
            hypothesis_id: ID da hipótese
            proposed_by: Usuário que está propondo
            reason: Razão da proposta

        Returns:
            Tupla (hipótese atualizada, transição) ou (None, None)
        """
        hypothesis = await self.get_by_id(hypothesis_id)
        if not hypothesis:
            return None, None

        # Validar transição
        try:
            HypothesisWorkflow.validate_transition(
                hypothesis.status,
                HypothesisStatus.PROPOSED,
                "author",
            )
        except TransitionError as e:
            logger.warning(
                f"invalid_transition: hypothesis_id={hypothesis_id}, from_status={hypothesis.status.value}, to_status={HypothesisStatus.PROPOSED.value}, error={e!s}"
            )
            raise

        # Criar versão antes de mudar status
        if self.versioning and self.settings.enable_versioning:
            previous_snapshot = hypothesis.to_dict()
            hypothesis.current_version += 1
            hypothesis.versions.append(hypothesis.current_version)
            await self.repository.update(
                hypothesis_id,
                {
                    "current_version": hypothesis.current_version,
                    "versions": hypothesis.versions,
                },
            )
            await self.versioning.create_version(
                hypothesis=hypothesis,
                created_by=proposed_by,
                change_reason=reason or "Proposta para revisão",
                change_type="status_change",
                previous_snapshot=previous_snapshot,
            )

        # Executar transição
        updated, transition = await self.repository.transition_status(
            hypothesis_id=hypothesis_id,
            new_status=HypothesisStatus.PROPOSED,
            transitioned_by=proposed_by,
            reason=reason,
        )

        logger.info(
            f"hypothesis_proposed: hypothesis_id={hypothesis_id}, proposed_by={proposed_by}"
        )

        return updated, transition

    async def approve(
        self,
        hypothesis_id: str,
        approved_by: str,
        reason: str = "",
    ) -> tuple[Hypothesis | None, WorkflowTransition | None]:
        """
        Aprova hipótese para teste.

        Args:
            hypothesis_id: ID da hipótese
            approved_by: Usuário que está aprovando
            reason: Razão da aprovação

        Returns:
            Tupla (hipótese atualizada, transição) ou (None, None)
        """
        hypothesis = await self.get_by_id(hypothesis_id)
        if not hypothesis:
            return None, None

        # Validar transição
        try:
            HypothesisWorkflow.validate_transition(
                hypothesis.status,
                HypothesisStatus.APPROVED,
                "reviewer",
            )
        except TransitionError as e:
            logger.warning(
                f"invalid_transition: hypothesis_id={hypothesis_id}, from_status={hypothesis.status.value}, to_status={HypothesisStatus.APPROVED.value}, error={e!s}"
            )
            raise

        # Criar versão antes de mudar status
        if self.versioning and self.settings.enable_versioning:
            previous_snapshot = hypothesis.to_dict()
            hypothesis.current_version += 1
            hypothesis.versions.append(hypothesis.current_version)
            await self.repository.update(
                hypothesis_id,
                {
                    "current_version": hypothesis.current_version,
                    "versions": hypothesis.versions,
                },
            )
            await self.versioning.create_version(
                hypothesis=hypothesis,
                created_by=approved_by,
                change_reason=reason or "Aprovada para teste",
                change_type="status_change",
                previous_snapshot=previous_snapshot,
            )

        # Executar transição
        updated, transition = await self.repository.transition_status(
            hypothesis_id=hypothesis_id,
            new_status=HypothesisStatus.APPROVED,
            transitioned_by=approved_by,
            reason=reason,
        )

        logger.info(
            f"hypothesis_approved: hypothesis_id={hypothesis_id}, approved_by={approved_by}"
        )

        return updated, transition

    async def reject(
        self,
        hypothesis_id: str,
        rejected_by: str,
        reason: str = "",
    ) -> tuple[Hypothesis | None, WorkflowTransition | None]:
        """
        Rejeita hipótese.

        Args:
            hypothesis_id: ID da hipótese
            rejected_by: Usuário que está rejeitando
            reason: Razão da rejeição

        Returns:
            Tupla (hipótese atualizada, transição) ou (None, None)
        """
        hypothesis = await self.get_by_id(hypothesis_id)
        if not hypothesis:
            return None, None

        # Validar transição
        role = "reviewer" if hypothesis.status == HypothesisStatus.PROPOSED else "system"
        try:
            HypothesisWorkflow.validate_transition(
                hypothesis.status,
                HypothesisStatus.REJECTED,
                role,
            )
        except TransitionError as e:
            logger.warning(
                f"invalid_transition: hypothesis_id={hypothesis_id}, from_status={hypothesis.status.value}, to_status={HypothesisStatus.REJECTED.value}, error={e!s}"
            )
            raise

        # Criar versão antes de mudar status
        if self.versioning and self.settings.enable_versioning:
            previous_snapshot = hypothesis.to_dict()
            hypothesis.current_version += 1
            hypothesis.versions.append(hypothesis.current_version)
            await self.repository.update(
                hypothesis_id,
                {
                    "current_version": hypothesis.current_version,
                    "versions": hypothesis.versions,
                },
            )
            await self.versioning.create_version(
                hypothesis=hypothesis,
                created_by=rejected_by,
                change_reason=reason or "Rejeitada",
                change_type="status_change",
                previous_snapshot=previous_snapshot,
            )

        # Executar transição
        updated, transition = await self.repository.transition_status(
            hypothesis_id=hypothesis_id,
            new_status=HypothesisStatus.REJECTED,
            transitioned_by=rejected_by,
            reason=reason,
        )

        logger.info(
            f"hypothesis_rejected: hypothesis_id={hypothesis_id}, rejected_by={rejected_by}, reason={reason}"
        )

        return updated, transition

    async def start_testing(
        self,
        hypothesis_id: str,
        experiment_id: str,
        started_by: str = "system",
    ) -> tuple[Hypothesis | None, WorkflowTransition | None]:
        """
        Inicia teste de hipótese.

        Args:
            hypothesis_id: ID da hipótese
            experiment_id: ID do experimento criado
            started_by: Usuário/sistema que iniciou

        Returns:
            Tupla (hipótese atualizada, transição) ou (None, None)
        """
        hypothesis = await self.get_by_id(hypothesis_id)
        if not hypothesis:
            return None, None

        # Validar transição
        try:
            HypothesisWorkflow.validate_transition(
                hypothesis.status,
                HypothesisStatus.IN_TESTING,
                "system_or_author",
            )
        except TransitionError as e:
            logger.warning(
                f"invalid_transition: hypothesis_id={hypothesis_id}, from_status={hypothesis.status.value}, to_status={HypothesisStatus.IN_TESTING.value}, error={e!s}"
            )
            raise

        # Associar experimento
        await self.repository.set_experiment_id(hypothesis_id, experiment_id)

        # Executar transição
        updated, transition = await self.repository.transition_status(
            hypothesis_id=hypothesis_id,
            new_status=HypothesisStatus.IN_TESTING,
            transitioned_by=started_by,
            reason=f"Experimento {experiment_id} iniciado",
        )

        logger.info(
            f"hypothesis_testing_started: hypothesis_id={hypothesis_id}, experiment_id={experiment_id}"
        )

        return updated, transition

    async def complete(
        self,
        hypothesis_id: str,
        results: HypothesisResults,
        completed_by: str = "system",
    ) -> tuple[Hypothesis | None, WorkflowTransition | None]:
        """
        Marca hipótese como completada (com resultados).

        Args:
            hypothesis_id: ID da hipótese
            results: Resultados do experimento
            completed_by: Usuário/sistema que completou

        Returns:
            Tupla (hipótese atualizada, transição) ou (None, None)
        """
        hypothesis = await self.get_by_id(hypothesis_id)
        if not hypothesis:
            return None, None

        # Salvar resultados
        await self.repository.set_results(hypothesis_id, results.model_dump())

        # Executar transição para COMPLETED
        updated, transition = await self.repository.transition_status(
            hypothesis_id=hypothesis_id,
            new_status=HypothesisStatus.COMPLETED,
            transitioned_by=completed_by,
            reason=f"Experimento completado: {results.outcome}",
        )

        logger.info(
            f"hypothesis_completed: hypothesis_id={hypothesis_id}, outcome={results.outcome}"
        )

        return updated, transition

    async def accept(
        self,
        hypothesis_id: str,
        accepted_by: str,
        reason: str = "",
    ) -> tuple[Hypothesis | None, WorkflowTransition | None]:
        """
        Aceita hipótese como validada.

        Args:
            hypothesis_id: ID da hipótese
            accepted_by: Usuário que aceitou
            reason: Razão da aceitação

        Returns:
            Tupla (hipótese atualizada, transição) ou (None, None)
        """
        hypothesis = await self.get_by_id(hypothesis_id)
        if not hypothesis:
            return None, None

        # Validar transição
        try:
            HypothesisWorkflow.validate_transition(
                hypothesis.status,
                HypothesisStatus.ACCEPTED,
                "reviewer",
            )
        except TransitionError as e:
            logger.warning(
                f"invalid_transition: hypothesis_id={hypothesis_id}, from_status={hypothesis.status.value}, to_status={HypothesisStatus.ACCEPTED.value}, error={e!s}"
            )
            raise

        # Executar transição
        updated, transition = await self.repository.transition_status(
            hypothesis_id=hypothesis_id,
            new_status=HypothesisStatus.ACCEPTED,
            transitioned_by=accepted_by,
            reason=reason or "Hipótese validada",
        )

        logger.info(
            f"hypothesis_accepted: hypothesis_id={hypothesis_id}, accepted_by={accepted_by}"
        )

        return updated, transition

    async def archive(
        self,
        hypothesis_id: str,
        archived_by: str,
        reason: str = "",
    ) -> tuple[Hypothesis | None, WorkflowTransition | None]:
        """
        Arquiva hipótese.

        Args:
            hypothesis_id: ID da hipótese
            archived_by: Usuário que está arquivando
            reason: Razão do arquivamento

        Returns:
            Tupla (hipótese atualizada, transição) ou (None, None)
        """
        hypothesis = await self.get_by_id(hypothesis_id)
        if not hypothesis:
            return None, None

        # Validar transição
        try:
            HypothesisWorkflow.validate_transition(
                hypothesis.status,
                HypothesisStatus.ARCHIVED,
                "author_or_reviewer",
            )
        except TransitionError as e:
            logger.warning(
                f"invalid_transition: hypothesis_id={hypothesis_id}, from_status={hypothesis.status.value}, to_status={HypothesisStatus.ARCHIVED.value}, error={e!s}"
            )
            raise

        # Executar transição
        updated, transition = await self.repository.transition_status(
            hypothesis_id=hypothesis_id,
            new_status=HypothesisStatus.ARCHIVED,
            transitioned_by=archived_by,
            reason=reason or "Arquivada",
        )

        logger.info(
            f"hypothesis_archived: hypothesis_id={hypothesis_id}, archived_by={archived_by}"
        )

        return updated, transition

    async def delete(self, hypothesis_id: str) -> bool:
        """
        Remove hipótese (soft delete via arquivo).

        Args:
            hypothesis_id: ID da hipótese

        Returns:
            True se removida
        """
        return await self.repository.delete(hypothesis_id)

    async def get_version_history(
        self,
        hypothesis_id: str,
    ) -> list[HypothesisVersion]:
        """
        Retorna histórico de versões.

        Args:
            hypothesis_id: ID da hipótese

        Returns:
            Lista de versões
        """
        if not self.versioning:
            return []

        return await self.versioning.get_version_history(hypothesis_id)

    async def compare_versions(
        self,
        hypothesis_id: str,
        from_version: int,
        to_version: int,
    ):
        """
        Compara duas versões.

        Args:
            hypothesis_id: ID da hipótese
            from_version: Versão de origem
            to_version: Versão de destino

        Returns:
            Diff entre versões ou None
        """
        if not self.versioning:
            return None

        return await self.versioning.compare_versions(
            hypothesis_id=hypothesis_id,
            from_version=from_version,
            to_version=to_version,
        )

    async def get_transition_history(
        self,
        hypothesis_id: str,
    ) -> list[WorkflowTransition]:
        """
        Retorna histórico de transições de estado.

        Args:
            hypothesis_id: ID da hipótese

        Returns:
            Lista de transições
        """
        return await self.repository.get_transition_history(hypothesis_id)

    async def get_allowed_transitions(
        self,
        hypothesis_id: str,
        role: str = "author",
    ) -> list[HypothesisStatus]:
        """
        Retorna transições permitidas para uma hipótese.

        Args:
            hypothesis_id: ID da hipótese
            role: Papel do usuário

        Returns:
            Lista de status permitidos
        """
        hypothesis = await self.get_by_id(hypothesis_id)
        if not hypothesis:
            return []

        return HypothesisWorkflow.get_allowed_transitions(
            hypothesis.status,
            role,
        )

    async def get_aggregations(self) -> dict[str, Any]:
        """
        Retorna agregações para dashboard.

        Returns:
            Dict com métricas
        """
        return await self.repository.get_aggregations()
