"""
Modelo para ferramenta MCP validada.

Representa ferramenta com relatórios de validação de schema, segurança e conectividade.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.functional_serializers import field_serializer

from .tool_descriptor import ToolDescriptor


class ValidationStatus(str, Enum):
    """Status de validação."""

    PENDING = "pending"
    VALIDATING = "validating"
    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"
    ERROR = "error"


class SchemaValidationSummary(BaseModel):
    """Resumo de validação de schema."""

    input_valid: bool = Field(..., description="Se schema de entrada é válido")
    output_valid: bool = Field(default=True, description="Se schema de saída é válido")
    input_issues_count: int = Field(default=0, description="Número de issues no schema de entrada")
    output_issues_count: int = Field(default=0, description="Número de issues no schema de saída")
    input_recommendations: List[str] = Field(
        default_factory=list, description="Recomendações para input"
    )
    output_recommendations: List[str] = Field(
        default_factory=list, description="Recomendações para output"
    )


class SecurityValidationSummary(BaseModel):
    """Resumo de validação de segurança."""

    is_safe: bool = Field(..., description="Se ferramenta é considerada segura")
    risk_count: int = Field(default=0, description="Total de riscos encontrados")
    critical_risks: int = Field(default=0, description="Riscos críticos")
    high_risks: int = Field(default=0, description="Riscos altos")
    medium_risks: int = Field(default=0, description="Riscos médios")
    low_risks: int = Field(default=0, description="Riscos baixos")
    requires_approval: bool = Field(default=False, description="Se requer aprovação humana")
    allowed_contexts: List[str] = Field(
        default_factory=lambda: ["default"], description="Contextos onde pode ser usada"
    )
    risk_types: List[str] = Field(default_factory=list, description="Tipos de risco encontrados")


class ConnectivityStatus(str, Enum):
    """Status de conectividade."""

    UNKNOWN = "unknown"
    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"
    DEGRADED = "degraded"


class ConnectivityValidationSummary(BaseModel):
    """Resumo de validação de conectividade."""

    status: ConnectivityStatus = Field(..., description="Status de conectividade")
    endpoint_reachable: bool = Field(
        default=False, description="Se endpoint principal é alcançável"
    )
    response_time_ms: Optional[int] = Field(default=None, description="Tempo de resposta em ms")
    last_check: Optional[datetime] = Field(default=None, description="Data da última verificação")
    tests_passed: int = Field(default=0, description="Testes que passaram")
    tests_failed: int = Field(default=0, description="Testes que falharam")
    recommendations: List[str] = Field(default_factory=list, description="Recomendações")


class ValidatedTool(BaseModel):
    """
    Ferramenta MCP com validações.

    Estende ToolDescriptor com relatórios de validação.
    """

    # Campos base do ToolDescriptor
    tool_id: str
    tool_name: str
    category: str
    capabilities: List[str]
    version: str
    reputation_score: float
    average_execution_time_ms: int
    cost_score: float
    required_parameters: Dict[str, str] = Field(default_factory=dict)
    output_format: str
    integration_type: str
    endpoint_url: Optional[str] = None
    authentication_method: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    schema_version: int = 1

    # Campos de validação
    validation_status: ValidationStatus = Field(default=ValidationStatus.PENDING)
    validation_timestamp: Optional[datetime] = Field(default=None)

    # Validação de Schema
    schema_validation: Optional[SchemaValidationSummary] = Field(default=None)
    input_schema: Optional[Dict[str, Any]] = Field(default=None)
    output_schema: Optional[Dict[str, Any]] = Field(default=None)

    # Validação de Segurança
    security_validation: Optional[SecurityValidationSummary] = Field(default=None)

    # Validação de Conectividade
    connectivity_validation: Optional[ConnectivityValidationSummary] = Field(default=None)

    def is_fully_validated(self) -> bool:
        """Verifica se todas as validações foram realizadas."""
        return (
            self.schema_validation is not None
            and self.security_validation is not None
            and self.connectivity_validation is not None
        )

    def can_be_used_safely(self) -> bool:
        """
        Verifica se ferramenta pode ser usada com segurança.

        Requer:
        - Schema válido
        - Segurança aprovada
        - Conectividade OK (ou não aplicável)
        """
        if not self.is_fully_validated():
            return False

        if not (self.schema_validation.input_valid and self.schema_validation.output_valid):
            return False

        if not self.security_validation.is_safe:
            return False

        if self.connectivity_validation.status == ConnectivityStatus.UNREACHABLE:
            return False

        return True

    def requires_human_approval(self) -> bool:
        """Verifica se ferramenta requer aprovação humana."""
        return self.security_validation.requires_approval if self.security_validation else False

    def to_tool_descriptor(self) -> ToolDescriptor:
        """Converte para ToolDescriptor básico."""
        from .tool_descriptor import AuthenticationMethod, IntegrationType, ToolCategory

        return ToolDescriptor(
            tool_id=self.tool_id,
            tool_name=self.tool_name,
            category=ToolCategory(self.category),
            capabilities=self.capabilities,
            version=self.version,
            reputation_score=self.reputation_score,
            average_execution_time_ms=self.average_execution_time_ms,
            cost_score=self.cost_score,
            required_parameters=self.required_parameters,
            output_format=self.output_format,
            integration_type=IntegrationType(self.integration_type),
            endpoint_url=self.endpoint_url,
            authentication_method=AuthenticationMethod(self.authentication_method),
            metadata=self.metadata,
            created_at=self.created_at,
            updated_at=self.updated_at,
            trace_id=self.trace_id,
            span_id=self.span_id,
            schema_version=self.schema_version,
        )

    def get_validation_summary(self) -> Dict[str, Any]:
        """Retorna resumo das validações."""
        return {
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "validation_status": self.validation_status.value,
            "validation_timestamp": (
                self.validation_timestamp.isoformat() if self.validation_timestamp else None
            ),
            "fully_validated": self.is_fully_validated(),
            "can_be_used_safely": self.can_be_used_safely(),
            "requires_approval": self.requires_human_approval(),
            "schema_valid": (
                self.schema_validation.input_valid and self.schema_validation.output_valid
                if self.schema_validation
                else None
            ),
            "security_safe": self.security_validation.is_safe if self.security_validation else None,
            "connectivity_status": (
                self.connectivity_validation.status.value if self.connectivity_validation else None
            ),
        }

    model_config = ConfigDict(use_enum_values=False)

    @field_serializer(
        "created_at",
        "updated_at",
        "validation_timestamp",
        "last_check",
        when_used="json",
        check_fields=False,
    )
    def serialize_datetime(self, dt: datetime) -> str:
        """Serialize datetime to ISO format"""
        return dt.isoformat() if dt else None
