"""
Modelos Pydantic para Feature Flags.

Define modelos para:
- FeatureFlag: Flag principal com metadata
- RolloutStrategy: Estratégia de rollout (immediate, gradual, canary, scheduled)
- Conditions: Condições de ativação (whitelist, percentage, attribute)
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings

from neural_hive_domain import StrEnum


class RolloutType(StrEnum):
    """Tipos de estratégia de rollout."""

    IMMEDIATE = "immediate"
    GRADUAL = "gradual"
    CANARY = "canary"
    SCHEDULED = "scheduled"


class ConditionType(StrEnum):
    """Tipos de condição."""

    WHITELIST = "whitelist"
    PERCENTAGE = "percentage"
    ATTRIBUTE = "attribute"


class OperatorType(StrEnum):
    """Operadores para condições de atributo."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"


class RolloutStrategy(BaseModel):
    """Estratégia de rollout para feature flag."""

    type: RolloutType = Field(
        default=RolloutType.IMMEDIATE, description="Tipo de rollout"
    )
    percentage: int = Field(
        default=100, ge=0, le=100, description="Percentagem de tráfego (0-100)"
    )
    whitelist: list[str] = Field(
        default_factory=list, description="Lista de valores para whitelist"
    )
    scheduled_start: datetime | None = Field(
        default=None, description="Início programado"
    )
    scheduled_end: datetime | None = Field(default=None, description="Fim programado")


class WhitelistCondition(BaseModel):
    """Condição baseada em whitelist de valores."""

    type: ConditionType = Field(
        default=ConditionType.WHITELIST, description="Tipo da condição"
    )
    values: list[str] = Field(..., description="Valores permitidos")
    attribute: str | None = Field(
        default=None, description="Atributo do contexto para avaliar"
    )

    def evaluate(self, value: str | None, context: dict[str, Any]) -> bool:
        """
        Avalia se value está na whitelist.

        Args:
            value: Valor direto a verificar
            context: Contexto com atributos

        Returns:
            True se valor está na whitelist ou se atributo do contexto está na whitelist
        """
        # Se attribute especificado, buscar do contexto
        if self.attribute:
            value = context.get(self.attribute)

        return value in self.values


class PercentageCondition(BaseModel):
    """Condição baseada em percentagem (hash determinístico)."""

    type: ConditionType = Field(
        default=ConditionType.PERCENTAGE, description="Tipo da condição"
    )
    percentage: int = Field(..., ge=0, le=100, description="Percentagem (0-100)")
    attribute: str | None = Field(
        default=None, description="Atributo do contexto para hash"
    )

    def evaluate(self, value: str | None, context: dict[str, Any]) -> bool:
        """
        Avalia baseado em hash determinístico.

        Usa SHA256 do valor para determinação consistente.

        Args:
            value: Valor para calcular hash
            context: Contexto com atributos

        Returns:
            True se hash cai na percentagem configurada
        """
        import hashlib

        # Se attribute especificado, buscar do contexto
        if self.attribute:
            value = context.get(self.attribute)

        if value is None:
            return False

        # Hash SHA256 determinístico
        hash_bytes = hashlib.sha256(str(value).encode()).digest()
        # Converter para inteiro 0-99
        bucket = int.from_bytes(hash_bytes[:2], "big") % 100

        return bucket < self.percentage


class AttributeCondition(BaseModel):
    """Condição baseada em atributo do contexto."""

    type: ConditionType = Field(
        default=ConditionType.ATTRIBUTE, description="Tipo da condição"
    )
    attribute: str = Field(..., description="Nome do atributo no contexto")
    operator: OperatorType = Field(..., description="Operador de comparação")
    value: Any = Field(..., description="Valor de comparação")

    def evaluate(self, _value: str | None, context: dict[str, Any]) -> bool:
        """
        Avalia condição do atributo.

        Args:
            _value: Ignorado (usa attribute do contexto)
            context: Contexto com atributos

        Returns:
            True se condição é satisfeita
        """
        actual_value = context.get(self.attribute)

        # Atributo não presente
        if actual_value is None:
            return False

        match self.operator:
            case OperatorType.EQUALS:
                return actual_value == self.value

            case OperatorType.NOT_EQUALS:
                return actual_value != self.value

            case OperatorType.IN:
                return (
                    actual_value in self.value
                    if isinstance(self.value, list)
                    else False
                )

            case OperatorType.NOT_IN:
                return (
                    actual_value not in self.value
                    if isinstance(self.value, list)
                    else True
                )

            case OperatorType.GREATER_THAN:
                try:
                    return actual_value > self.value
                except TypeError:
                    return False

            case OperatorType.LESS_THAN:
                try:
                    return actual_value < self.value
                except TypeError:
                    return False

            case OperatorType.GREATER_THAN_OR_EQUAL:
                try:
                    return actual_value >= self.value
                except TypeError:
                    return False

            case OperatorType.LESS_THAN_OR_EQUAL:
                try:
                    return actual_value <= self.value
                except TypeError:
                    return False

            case _:
                return False


# Union type para condições
Condition = WhitelistCondition | PercentageCondition | AttributeCondition


class FeatureFlag(BaseModel):
    """
    Feature Flag com estratégia de rollout e condições.

    Permite ativação/desativação dinâmica de features sem deploy.
    """

    name: str = Field(..., description="Nome único da flag (snake_case)")
    description: str = Field(..., description="Descrição da funcionalidade")
    enabled: bool = Field(default=False, description="Flag está habilitada?")
    rollout_strategy: RolloutStrategy = Field(
        default_factory=RolloutStrategy, description="Estratégia de rollout"
    )
    conditions: list[Condition] = Field(
        default_factory=list, description="Condições adicionais (AND logic)"
    )
    owner: str | None = Field(default=None, description="Time/dono responsável")
    tags: list[str] = Field(default_factory=list, description="Tags para organização")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadados adicionais"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Data de criação"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Última atualização"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Valida formato do nome (snake_case)."""
        if not v.replace("_", "").isalnum():
            raise ValueError(
                "name deve estar em snake_case (apenas letras, números e underscore)"
            )
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Valida e normaliza tags."""
        return [tag.lower().strip() for tag in v if tag.strip()]

    def enable(self) -> None:
        """Habilita a flag e atualiza timestamp."""
        self.enabled = True
        self.updated_at = datetime.utcnow()

    def disable(self) -> None:
        """Desabilita a flag e atualiza timestamp."""
        self.enabled = False
        self.updated_at = datetime.utcnow()

    def is_enabled_for(self, context: dict[str, Any]) -> bool:
        """
        Avalia se flag está habilitada para o contexto fornecido.

        Args:
            context: Contexto de avaliação (tenant_id, user_id, namespace, etc.)

        Returns:
            True se flag está habilitada e todas condições são satisfeitas
        """
        # Flag desabilitada nunca retorna True
        if not self.enabled:
            return False

        # Sem condições significa que está habilitada para todos
        if not self.conditions:
            return True

        # Avaliar estratégia de rollout gradual se aplicável
        if self.rollout_strategy.type == RolloutType.GRADUAL:
            percentage_condition = PercentageCondition(
                percentage=self.rollout_strategy.percentage,
                attribute="tenant_id",  # Default para gradual
            )
            if not percentage_condition.evaluate(None, context):
                return False

        # Avaliar todas as condições (AND logic)
        for condition in self.conditions:
            if not condition.evaluate(None, context):
                return False

        return True

    def to_dict(self) -> dict[str, Any]:
        """
        Converte para dicionário (para MongoDB/Redis).

        Returns:
            Dicionário com timestamps como strings ISO
        """
        data = self.model_dump()

        # Converter datetime para ISO string
        if isinstance(data.get("created_at"), datetime):
            data["created_at"] = data["created_at"].isoformat()
        if isinstance(data.get("updated_at"), datetime):
            data["updated_at"] = data["updated_at"].isoformat()

        # Converter enums para strings
        if self.rollout_strategy:
            data["rollout_strategy"]["type"] = self.rollout_strategy.type.value

        # Serializar condições
        data["conditions"] = [c.model_dump() for c in self.conditions]

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeatureFlag":
        """
        Cria instância a partir de dicionário (do MongoDB/Redis).

        Args:
            data: Dicionário com dados da flag

        Returns:
            Instância de FeatureFlag
        """
        # Copiar para não modificar original
        data = data.copy()

        # Parse datetime
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        # Deserializar rollout_strategy type
        if "rollout_strategy" in data and isinstance(data["rollout_strategy"], dict):
            if "type" in data["rollout_strategy"] and isinstance(
                data["rollout_strategy"]["type"], str
            ):
                data["rollout_strategy"]["type"] = RolloutType(
                    data["rollout_strategy"]["type"]
                )

        # Deserializar condições
        if "conditions" in data and isinstance(data["conditions"], list):
            deserialized_conditions = []
            for cond in data["conditions"]:
                if not isinstance(cond, dict):
                    continue

                cond_type = cond.get("type")
                match cond_type:
                    case "whitelist":
                        deserialized_conditions.append(WhitelistCondition(**cond))
                    case "percentage":
                        deserialized_conditions.append(PercentageCondition(**cond))
                    case "attribute":
                        deserialized_conditions.append(AttributeCondition(**cond))
                    case _:
                        # Tentar desserializar genérico
                        deserialized_conditions.append(cond)

            data["conditions"] = deserialized_conditions

        return cls(**data)

    def calculate_hash(self) -> str:
        """
        Calcula hash SHA-256 para integridade.

        Returns:
            Hash hexadecimal da configuração da flag
        """
        import hashlib
        import json

        data = self.to_dict()
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()
