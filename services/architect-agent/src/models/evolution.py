"""Modelos de dados para rastreamento de evolução de arquitetura."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class DriftType(str, Enum):
    """Tipos de divergência entre arquitetura planejada e implementada."""

    ARCHITECTURE = "architecture"  # Tipo de arquitetura divergiu
    COMPONENTS = "components"  # Componentes divergiram
    PATTERNS = "patterns"  # Padrões não aplicados
    STACK = "stack"  # Stack tecnológica divergiu


class DriftDetection(BaseModel):
    """Divergência detectada entre plano e implementação."""

    model_config = ConfigDict(extra="forbid")

    drift_type: DriftType = Field(..., description="Tipo de divergência")
    description: str = Field(..., description="Descrição da divergência")
    expected: str = Field(..., description="Valor esperado")
    actual: str = Field(..., description="Valor encontrado")
    severity: str = Field(
        default="medium", description="Severidade: low, medium, high, critical"
    )


class EvolutionHistory(BaseModel):
    """Histórico de evolução de um plano de arquitetura.

    Registra mudanças ao longo do tempo e divergências detectadas.
    """

    model_config = ConfigDict(extra="forbid")

    history_id: str = Field(..., description="ID único do histórico")
    plan_id: str = Field(..., description="ID do plano de arquitetura")
    version: int = Field(..., ge=1, description="Versão do plano")
    changes: List[str] = Field(
        default_factory=list, description="Lista de mudanças aplicadas"
    )
    drifts: List[DriftDetection] = Field(
        default_factory=list, description="Lista de divergências detectadas"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Data de criação"
    )
    created_by: str = Field(
        default="architect-agent",
        description="Autor da mudança (architect-agent ou user)",
    )


class ArchitectureDiff(BaseModel):
    """Diferença entre duas versões de um plano de arquitetura.

    Representa as mudanças entre versões consecutivas.
    """

    model_config = ConfigDict(extra="forbid")

    plan_id_old: str = Field(..., description="ID do plano antigo")
    plan_id_new: str = Field(..., description="ID do plano novo")
    additions: List[str] = Field(
        default_factory=list, description="Elementos adicionados"
    )
    removals: List[str] = Field(
        default_factory=list, description="Elementos removidos"
    )
    modifications: List[str] = Field(
        default_factory=list, description="Elementos modificados"
    )
    requires_migration: bool = Field(
        default=False, description="Se requer migração de dados/infra"
    )
