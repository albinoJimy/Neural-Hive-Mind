"""Modelos de dados para arquitetura de software."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# Importar modelos relacionados para forward references
from src.models.bounded_context import BoundedContext
from src.models.tech_stack import TechChoice
from src.models.diagrams import Diagram


class ArchitectureType(str, Enum):
    """Tipo de arquitetura de software."""

    MICROSERVICES = "microservices"
    MONOLITH = "monolith"
    SERVERLESS = "serverless"
    HYBRID = "hybrid"


class Component(BaseModel):
    """Componente de uma arquitetura.

    Representa um serviço ou módulo com suas configurações de deploy.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Nome do componente")
    stack: str = Field(..., description="Stack tecnológica (ex: python/fastapi)")
    replicas: int = Field(default=1, ge=1, description="Número de réplicas")
    ha: bool = Field(default=False, description="High availability")
    resources: Dict[str, Any] = Field(default_factory=dict, description="CPU/memory limits")


class Pattern(str, Enum):
    """Padrões de design e arquiteturais."""

    REPOSITORY = "repository"
    CQRS = "cqrs"
    EVENT_SOURCING = "event_sourcing"
    SAGA = "saga"
    CIRCUIT_BREAKER = "circuit_breaker"
    API_GATEWAY = "api_gateway"
    MESSAGE_BROKER = "message_broker"


class ArchitecturePlan(BaseModel):
    """Plano de arquitetura gerado pelo Architect Agent.

    Contém a definição completa da arquitetura proposta para um sistema.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "plan_id": "arch-123",
                "cognitive_plan_id": "cp-456",
                "architecture_type": "microservices",
                "components": [
                    {
                        "name": "user-api",
                        "stack": "python/fastapi",
                        "replicas": 3,
                        "ha": True,
                    }
                ],
                "patterns": ["repository", "cqrs"],
                "rationale": "Microservices para escala independente",
                "requirements": {"scalability": "high", "availability": "99.9%"},
            }
        },
    )

    plan_id: str = Field(..., description="ID único do plano")
    cognitive_plan_id: Optional[str] = Field(None, description="ID do CognitivePlan de origem")
    architecture_type: ArchitectureType = Field(..., description="Tipo de arquitetura proposta")
    components: List[Component] = Field(..., description="Lista de componentes da arquitetura")
    patterns: List[Pattern] = Field(..., description="Padrões arquiteturais aplicados")
    rationale: str = Field(..., description="Justificativa das decisões")
    requirements: Dict[str, Any] = Field(
        default_factory=dict, description="Requisitos não-funcionais"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Data de criação")
    updated_at: Optional[datetime] = Field(None, description="Data da última atualização")

    # Campos estendidos do Fluxo G (opcionais para compatibilidade)
    bounded_contexts: Optional[List[BoundedContext]] = Field(
        None, description="Bounded contexts identificados (DDD)"
    )
    tech_stack: Optional[List[TechChoice]] = Field(
        None, description="Stack tecnológico recomendado"
    )
    diagrams: Optional[List[Diagram]] = Field(
        None, description="Diagramas de arquitetura gerados"
    )
