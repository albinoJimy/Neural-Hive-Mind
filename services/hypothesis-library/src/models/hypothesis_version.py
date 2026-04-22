"""Hypothesis versioning models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.models.hypothesis import Hypothesis, PyObjectId, utcnow


class HypothesisVersion(BaseModel):
    """Versão de uma hipótese."""

    id: PyObjectId | None = Field(None, alias="_id", description="MongoDB ObjectId")
    version_id: str = Field(..., description="Unique version identifier (hypothesis_id:version)")
    hypothesis_id: str = Field(..., description="ID da hipótese pai")
    version_number: int = Field(..., ge=1, description="Número da versão")

    # Snapshot completo da hipótese
    snapshot: dict[str, Any] = Field(..., description="Snapshot completo do estado da hipótese")

    # Metadados da versão
    created_at: datetime = Field(
        default_factory=utcnow, description="Timestamp da criação desta versão"
    )
    created_by: str = Field(..., description="Quem criou esta versão")
    change_reason: str = Field(default="", description="Razão da mudança")
    change_type: str = Field(
        default="update", description="Tipo: create, update, status_change, archive"
    )

    # Diff para versões anteriores
    changes: dict[str, Any] = Field(
        default_factory=dict, description="Campos alterados em relação à versão anterior"
    )
    parent_version: int | None = Field(
        None, description="Número da versão pai (None para primeira versão)"
    )

    model_config = ConfigDict(
        populate_by_name=True,
    )

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário."""
        data = self.model_dump(exclude={"id"})
        if self.id:
            data["_id"] = str(self.id)
        return data

    @classmethod
    def from_hypothesis(
        cls,
        hypothesis: Hypothesis,
        created_by: str,
        change_reason: str = "",
        change_type: str = "update",
        changes: dict[str, Any] | None = None,
        parent_version: int | None = None,
    ) -> HypothesisVersion:
        """
        Cria uma HypothesisVersion a partir de uma Hypothesis.

        Args:
            hypothesis: Hipótese a versionar
            created_by: Usuário que criou a versão
            change_reason: Razão da mudança
            change_type: Tipo de mudança
            changes: Dicionário de campos alterados
            parent_version: Versão pai

        Returns:
            Nova instância de HypothesisVersion
        """
        return cls(
            version_id=f"{hypothesis.hypothesis_id}:{hypothesis.current_version}",
            hypothesis_id=hypothesis.hypothesis_id,
            version_number=hypothesis.current_version,
            snapshot=hypothesis.to_dict(),
            created_by=created_by,
            change_reason=change_reason,
            change_type=change_type,
            changes=changes or {},
            parent_version=parent_version,
        )


class VersionDiff(BaseModel):
    """Representa as diferenças entre duas versões."""

    version_from: int = Field(..., description="Versão de origem")
    version_to: int = Field(..., description="Versão de destino")
    changed_fields: list[str] = Field(default_factory=list, description="Campos alterados")
    changes: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Detalhe das mudanças por campo"
    )

    @classmethod
    def compare(
        cls,
        from_snapshot: dict[str, Any],
        to_snapshot: dict[str, Any],
    ) -> VersionDiff:
        """
        Compara dois snapshots e retorna o diff.

        Args:
            from_snapshot: Snapshot da versão anterior
            to_snapshot: Snapshot da versão atual

        Returns:
            VersionDiff com as diferenças
        """
        changed_fields: list[str] = []
        changes: dict[str, dict[str, Any]] = {}

        # Campos relevantes para comparação
        comparable_fields = {
            "title",
            "description",
            "background",
            "expected_outcome",
            "metrics",
            "baseline_metrics",
            "target_metrics",
            "priority",
            "status",
            "tags",
            "reviewers",
        }

        for field in comparable_fields:
            from_value = from_snapshot.get(field)
            to_value = to_snapshot.get(field)

            if from_value != to_value:
                changed_fields.append(field)
                changes[field] = {
                    "from": from_value,
                    "to": to_value,
                }

        return cls(
            version_from=from_snapshot.get("current_version", 0),
            version_to=to_snapshot.get("current_version", 0),
            changed_fields=changed_fields,
            changes=changes,
        )
