"""
Modelos Pydantic para OPA Client.

Request/Response models para integração OPA.
"""
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ViolationSeverity(str, Enum):
    """Severidade de violação."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Violation(BaseModel):
    """Representa uma violação de política."""

    rule_id: str = Field(..., description="ID da regra violada")
    message: str = Field(..., description="Mensagem descritiva")
    severity: ViolationSeverity = Field(default=ViolationSeverity.MEDIUM)
    details: dict[str, Any] | None = Field(default=None, description="Detalhes adicionais")


class PolicyRequest(BaseModel):
    """Request para avaliação de política."""

    model_config = ConfigDict(populate_by_name=True)

    policy_path: str = Field(..., alias="policy", description="Caminho da política OPA")
    input_data: dict[str, Any] = Field(default_factory=dict, description="Dados de entrada")


class PolicyResponse(BaseModel):
    """Resposta de avaliação de política."""

    allow: bool = Field(..., description="Resultado da avaliação")
    decision_id: str | None = Field(default=None, description="ID único da decisão")
    violations: list[Violation] = Field(default_factory=list, description="Lista de violações")
    raw_response: dict[str, Any] | None = Field(default=None, description="Resposta bruta OPA")
    policy_path: str | None = Field(default=None, description="Caminho da política avaliada")


class OPABatchRequest(BaseModel):
    """Request para avaliação em lote."""

    requests: list[dict[str, Any]] = Field(..., description="Lista de requisições")


class OPABatchResponse(BaseModel):
    """Resposta de avaliação em lote."""

    results: list[PolicyResponse] = Field(..., description="Lista de resultados")
    total_count: int = Field(..., description="Total de requisições")
    success_count: int = Field(..., description="Total de sucessos")
    failure_count: int = Field(..., description="Total de falhas")
