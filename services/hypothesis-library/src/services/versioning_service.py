"""Service para versionamento de hipóteses."""

from __future__ import annotations

import logging
from typing import Any

from src.models.hypothesis import Hypothesis
from src.models.hypothesis_version import HypothesisVersion, VersionDiff
from src.repositories.version_repository import HypothesisVersionRepository

logger = logging.getLogger(__name__)


class VersioningService:
    """Service para gerenciar versionamento de hipóteses."""

    def __init__(self, version_repository: HypothesisVersionRepository):
        """
        Inicializa service.

        Args:
            version_repository: Repository de versões
        """
        self.version_repository = version_repository

    async def create_version(
        self,
        hypothesis: Hypothesis,
        created_by: str,
        change_reason: str = "",
        change_type: str = "update",
        previous_snapshot: dict[str, Any] | None = None,
    ) -> HypothesisVersion:
        """
        Cria nova versão de uma hipótese.

        Args:
            hypothesis: Hipótese atual
            created_by: Usuário que criou a versão
            change_reason: Razão da mudança
            change_type: Tipo de mudança
            previous_snapshot: Snapshot anterior para diff

        Returns:
            Nova versão criada
        """
        # Calcular mudanças se temos snapshot anterior
        changes: dict[str, Any] = {}
        if previous_snapshot:
            changes = self._calculate_changes(
                previous_snapshot,
                hypothesis.to_dict()
            )

        # Determinar versão pai
        parent_version = None
        if hypothesis.current_version > 1:
            parent_version = hypothesis.current_version - 1

        version = HypothesisVersion.from_hypothesis(
            hypothesis=hypothesis,
            created_by=created_by,
            change_reason=change_reason,
            change_type=change_type,
            changes=changes,
            parent_version=parent_version,
        )

        saved_version = await self.version_repository.save(version)

        # Cleanup de versões antigas se necessário
        await self.version_repository.cleanup_old_versions(
            hypothesis.hypothesis_id
        )

        logger.info(
            "version_created",
            version_id=saved_version.version_id,
            hypothesis_id=hypothesis.hypothesis_id,
            version_number=version.version_number,
        )

        return saved_version

    async def get_version_history(
        self,
        hypothesis_id: str,
        limit: int = 50,
    ) -> list[HypothesisVersion]:
        """
        Retorna histórico de versões.

        Args:
            hypothesis_id: ID da hipótese
            limit: Limite de versões

        Returns:
            Lista de versões
        """
        return await self.version_repository.list_versions(
            hypothesis_id=hypothesis_id,
            limit=limit,
        )

    async def get_version(
        self,
        hypothesis_id: str,
        version_number: int,
    ) -> HypothesisVersion | None:
        """
        Retorna versão específica.

        Args:
            hypothesis_id: ID da hipótese
            version_number: Número da versão

        Returns:
            Versão ou None
        """
        return await self.version_repository.get_version(
            hypothesis_id=hypothesis_id,
            version_number=version_number,
        )

    async def compare_versions(
        self,
        hypothesis_id: str,
        from_version: int,
        to_version: int,
    ) -> VersionDiff | None:
        """
        Compara duas versões.

        Args:
            hypothesis_id: ID da hipótese
            from_version: Versão de origem
            to_version: Versão de destino

        Returns:
            Diff entre versões ou None
        """
        return await self.version_repository.compare_versions(
            hypothesis_id=hypothesis_id,
            from_version=from_version,
            to_version=to_version,
        )

    async def revert_to_version(
        self,
        hypothesis_id: str,
        version_number: int,
        reverted_by: str,
    ) -> Hypothesis | None:
        """
        Reverte hipótese para versão anterior.

        Nota: Este método retorna o snapshot da versão.
        A aplicação da reversão deve ser feita pelo HypothesisService.

        Args:
            hypothesis_id: ID da hipótese
            version_number: Versão para reverter
            reverted_by: Usuário que fez a reversão

        Returns:
            Hipótese restaurada ou None
        """
        version = await self.get_version(hypothesis_id, version_number)
        if not version:
            return None

        # Retornar hipótese do snapshot
        restored_hypothesis = Hypothesis(**version.snapshot)

        # Atualizar metadados da reversão
        restored_hypothesis.hypothesis_id = hypothesis_id  # Manter ID
        restored_hypothesis.current_version += 1  # Nova versão

        logger.info(
            "hypothesis_reverted",
            hypothesis_id=hypothesis_id,
            to_version=version_number,
            reverted_by=reverted_by,
        )

        return restored_hypothesis

    def _calculate_changes(
        self,
        from_snapshot: dict[str, Any],
        to_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Calcula mudanças entre snapshots."""
        changes = {}

        # Campos relevantes para diff
        comparable_fields = {
            "title",
            "description",
            "background",
            "expected_outcome",
            "metrics",
            "baseline_metrics",
            "target_metrics",
            "priority",
            "tags",
            "reviewers",
        }

        for field in comparable_fields:
            from_value = from_snapshot.get(field)
            to_value = to_snapshot.get(field)

            if from_value != to_value:
                changes[field] = {
                    "from": from_value,
                    "to": to_value,
                }

        return changes
