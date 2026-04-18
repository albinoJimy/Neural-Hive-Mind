"""
Workflow Condicional para arquitetura com branching.

Implementa lógica de if/else para workflows que requerem
decisões baseadas em condições (ex: escolher DB baseado em volume).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ConditionOperator(str, Enum):
    """Operadores de condição."""

    EQUALS = "eq"
    NOT_EQUALS = "ne"
    GREATER_THAN = "gt"
    GREATER_EQUAL = "gte"
    LESS_THAN = "lt"
    LESS_EQUAL = "lte"
    IN = "in"
    NOT_IN = "nin"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"


@dataclass
class Condition:
    """Condição para avaliação."""

    field: str
    operator: ConditionOperator
    value: Any
    description: str = ""


@dataclass
class ConditionalBranch:
    """Branch condicional com suas atividades."""

    name: str
    condition: Condition | None = None  # None = else/default
    activities: list[dict[str, Any]] = field(default_factory=list)
    description: str = ""

    def matches(self, context: dict[str, Any]) -> bool:
        """Verifica se a condição é verdadeira dado o contexto."""
        if self.condition is None:
            return True  # Branch default/else

        field_value = context.get(self.condition.field)

        match self.condition.operator:
            case ConditionOperator.EQUALS:
                return field_value == self.condition.value
            case ConditionOperator.NOT_EQUALS:
                return field_value != self.condition.value
            case ConditionOperator.GREATER_THAN:
                return field_value is not None and field_value > self.condition.value
            case ConditionOperator.GREATER_EQUAL:
                return field_value is not None and field_value >= self.condition.value
            case ConditionOperator.LESS_THAN:
                return field_value is not None and field_value < self.condition.value
            case ConditionOperator.LESS_EQUAL:
                return field_value is not None and field_value <= self.condition.value
            case ConditionOperator.IN:
                return field_value in self.condition.value
            case ConditionOperator.NOT_IN:
                return field_value not in self.condition.value
            case ConditionOperator.CONTAINS:
                return isinstance(field_value, (list, str)) and self.condition.value in field_value
            case ConditionOperator.STARTS_WITH:
                return isinstance(field_value, str) and field_value.startswith(self.condition.value)
            case ConditionOperator.ENDS_WITH:
                return isinstance(field_value, str) and field_value.endswith(self.condition.value)
            case _:
                return False


class ConditionalWorkflow(BaseModel):
    """Workflow com lógica condicional.

    Exemplo de uso:
        Seleção de banco de dados baseado em volume:
        - volume < 100GB: PostgreSQL
        - 100GB <= volume < 1TB: MongoDB
        - volume >= 1TB: Cassandra
    """

    model_config = {"extra": "forbid"}

    workflow_id: str = Field(..., description="ID único do workflow")
    name: str = Field(..., description="Nome do workflow")
    description: str = Field(default="", description="Descrição do propósito")
    branches: list[ConditionalBranch] = Field(
        ..., description="Lista de branches (último deve ser default/else)"
    )
    input_context: dict[str, Any] = Field(default_factory=dict, description="Contexto de entrada")

    def evaluate(self, context: dict[str, Any] | None = None) -> str | None:
        """Avalia condições e retorna o nome do branch selecionado.

        Args:
            context: Contexto para avaliação (usa input_context se None)

        Returns:
            Nome do branch que corresponde à condição, ou None
        """
        eval_context = context or self.input_context

        for branch in self.branches:
            if branch.matches(eval_context):
                return branch.name

        return None

    def get_selected_branch(
        self, context: dict[str, Any] | None = None
    ) -> ConditionalBranch | None:
        """Retorna o branch selecionado baseado no contexto.

        Args:
            context: Contexto para avaliação

        Returns:
            ConditionalBranch selecionado ou None
        """
        branch_name = self.evaluate(context)
        for branch in self.branches:
            if branch.name == branch_name:
                return branch
        return None

    def get_activities(self, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Retorna atividades do branch selecionado.

        Args:
            context: Contexto para avaliação

        Returns:
            Lista de atividades a executar
        """
        branch = self.get_selected_branch(context)
        return branch.activities if branch else []

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário serializável."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "branches": [
                {
                    "name": b.name,
                    "condition": (
                        {
                            "field": b.condition.field,
                            "operator": b.condition.operator.value,
                            "value": b.condition.value,
                            "description": b.condition.description,
                        }
                        if b.condition
                        else None
                    ),
                    "activities": b.activities,
                    "description": b.description,
                }
                for b in self.branches
            ],
            "input_context": self.input_context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConditionalWorkflow":
        """Cria ConditionalWorkflow a partir de dicionário."""
        branches = []
        for b_data in data.get("branches", []):
            cond_data = b_data.get("condition")
            condition = (
                Condition(
                    field=cond_data["field"],
                    operator=ConditionOperator(cond_data["operator"]),
                    value=cond_data["value"],
                    description=cond_data.get("description", ""),
                )
                if cond_data
                else None
            )
            branches.append(
                ConditionalBranch(
                    name=b_data["name"],
                    condition=condition,
                    activities=b_data.get("activities", []),
                    description=b_data.get("description", ""),
                )
            )

        return cls(
            workflow_id=data["workflow_id"],
            name=data["name"],
            description=data.get("description", ""),
            branches=branches,
            input_context=data.get("input_context", {}),
        )


# Exemplos de workflows condicionais predefinidos


def create_database_selection_workflow() -> ConditionalWorkflow:
    """Cria workflow para seleção de banco baseado em volume."""
    return ConditionalWorkflow(
        workflow_id="wf-db-selection",
        name="database_selection",
        description="Seleciona banco de dados baseado em volume de dados",
        branches=[
            ConditionalBranch(
                name="postgresql_branch",
                condition=Condition(
                    field="data_volume_gb",
                    operator=ConditionOperator.LESS_THAN,
                    value=100,
                    description="Volume pequeno (< 100GB)",
                ),
                activities=[
                    {
                        "type": "add_component",
                        "component": {
                            "name": "database",
                            "stack": "postgresql",
                            "config": {"ha": False, "replicas": 1},
                        },
                    }
                ],
                description="PostgreSQL para volumes pequenos",
            ),
            ConditionalBranch(
                name="mongodb_branch",
                condition=Condition(
                    field="data_volume_gb",
                    operator=ConditionOperator.LESS_THAN,
                    value=1024,
                    description="Volume médio (100GB - 1TB)",
                ),
                activities=[
                    {
                        "type": "add_component",
                        "component": {
                            "name": "database",
                            "stack": "mongodb",
                            "config": {"ha": True, "replicas": 3},
                        },
                    }
                ],
                description="MongoDB para volumes médios",
            ),
            ConditionalBranch(
                name="cassandra_branch",
                condition=None,  # Default
                activities=[
                    {
                        "type": "add_component",
                        "component": {
                            "name": "database",
                            "stack": "cassandra",
                            "config": {"ha": True, "replicas": 5},
                        },
                    }
                ],
                description="Cassandra para grandes volumes (>= 1TB)",
            ),
        ],
    )


def create_cache_strategy_workflow() -> ConditionalWorkflow:
    """Cria workflow para seleção de estratégia de cache."""
    return ConditionalWorkflow(
        workflow_id="wf-cache-strategy",
        name="cache_strategy",
        description="Define estratégia de caching baseado em padrão de acesso",
        branches=[
            ConditionalBranch(
                name="redis_branch",
                condition=Condition(
                    field="access_pattern",
                    operator=ConditionOperator.EQUALS,
                    value="read_heavy",
                    description="Leituras intensivas",
                ),
                activities=[
                    {
                        "type": "add_component",
                        "component": {
                            "name": "cache",
                            "stack": "redis",
                            "config": {
                                "mode": "cluster",
                                "eviction_policy": "allkeys-lru",
                            },
                        },
                    }
                ],
            ),
            ConditionalBranch(
                name="memcached_branch",
                condition=Condition(
                    field="access_pattern",
                    operator=ConditionOperator.EQUALS,
                    value="simple",
                    description="Acesso simples",
                ),
                activities=[
                    {
                        "type": "add_component",
                        "component": {
                            "name": "cache",
                            "stack": "memcached",
                            "config": {"threads": 4},
                        },
                    }
                ],
            ),
            ConditionalBranch(
                name="no_cache_branch",
                condition=None,
                activities=[],
                description="Sem cache para outros padrões",
            ),
        ],
    )
