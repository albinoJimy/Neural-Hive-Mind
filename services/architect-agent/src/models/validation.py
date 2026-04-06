from neural_hive_domain import UTC
"""Modelos de dados para validação de código e arquitetura."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field



class Severity(str, Enum):
    """Nível de severidade de uma violação."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ViolationType(str, Enum):
    """Tipos de violações de princípios SOLID e design."""

    SRP = "srp"  # Single Responsibility Principle
    OCP = "ocp"  # Open/Closed Principle
    LSP = "lsp"  # Liskov Substitution Principle
    ISP = "isp"  # Interface Segregation Principle
    DIP = "dip"  # Dependency Inversion Principle
    COUPLING = "coupling"  # Alto acoplamento
    COHESION = "cohesion"  # Baixa coesão
    COMPLEXITY = "complexity"  # Complexidade ciclomática alta
    DUPLICATION = "duplication"  # Código duplicado


class Trend(str, Enum):
    """Tendência de evolução da saúde do código."""

    UP = "up"  # Saúde melhorando
    DOWN = "down"  # Saúde piorando
    STABLE = "stable"  # Saúde estável


class Violation(BaseModel):
    """Violação detectada na validação de código."""

    model_config = ConfigDict(extra="forbid")

    type: ViolationType = Field(..., description="Tipo da violação")
    severity: Severity = Field(..., description="Nível de severidade")
    location: str = Field(..., description="Localização no código (ex: file.py:linha)")
    description: str = Field(..., description="Descrição da violação")
    suggestion: Optional[str] = Field(None, description="Sugestão de correção")


class Suggestion(BaseModel):
    """Sugestão de melhoria para o código."""

    model_config = ConfigDict(extra="forbid")

    priority: int = Field(..., ge=1, le=5, description="Prioridade 1-5 (1 mais alta)")
    description: str = Field(..., description="Descrição da sugestão")
    effort: Literal["XS", "S", "M", "L", "XL"] = Field(
        default="M",
        description="Esforço estimado: XS, S, M, L, XL",
    )
    affected_files: List[str] = Field(
        default_factory=list, description="Arquivos afetados pela mudança"
    )


class ValidationReport(BaseModel):
    """Relatório de validação de código e arquitetura.

    Contém o resultado da análise de saúde do código, incluindo
    violações detectadas e sugestões de melhoria.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "report_id": "val-789",
                "repo_url": "github.com/org/repo",
                "branch": "main",
                "commit_sha": "abc123",
                "health_score": 72,
                "trend": "up",
                "violations": [
                    {
                        "type": "srp",
                        "severity": "high",
                        "location": "UserService.py:145",
                        "description": "Classe com 15 responsabilidades",
                        "suggestion": "Separar responsabilidades em classes menores",
                    }
                ],
                "suggestions": [
                    {
                        "priority": 1,
                        "description": "Separar responsabilidades",
                        "effort": "L",
                        "affected_files": ["UserService.py"],
                    }
                ],
                "metrics": {
                    "complexity": 45,
                    "duplication": 12,
                    "test_coverage": 68,
                },
            }
        },
    )

    report_id: str = Field(..., description="ID único do relatório")
    repo_url: str = Field(..., description="URL do repositório")
    branch: str = Field(default="main", description="Branch analisada")
    commit_sha: Optional[str] = Field(None, description="SHA do commit analisado")
    health_score: int = Field(..., ge=0, le=100, description="Score de saúde 0-100")
    trend: Trend = Field(default=Trend.STABLE, description="Tendência de evolução")
    violations: List[Violation] = Field(
        default_factory=list, description="Lista de violações detectadas"
    )
    suggestions: List[Suggestion] = Field(
        default_factory=list, description="Lista de sugestões de melhoria"
    )
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Métricas adicionais")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Data de criação")
