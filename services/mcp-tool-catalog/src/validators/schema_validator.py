"""
Validador de JSON Schema para ferramentas MCP.

Valida schemas de entrada/saída conforme especificação JSON Schema Draft 7.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

import structlog
from jsonschema import (
    Draft7Validator,
    FormatChecker,
    ValidationError,
    validate as jsonschema_validate,
)
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class ValidationSeverity(str, Enum):
    """Níveis de severidade de validação."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class SchemaValidationIssue(BaseModel):
    """Issue encontrado durante validação de schema."""

    type: str = Field(..., description="Tipo do issue")
    severity: ValidationSeverity = Field(..., description="Nível de severidade")
    message: str = Field(..., description="Mensagem descritiva")
    path: str = Field(default="", description="Caminho JSON Pointer ao issue")
    suggestion: Optional[str] = Field(default=None, description="Sugestão de correção")


class SchemaValidationResult(BaseModel):
    """Resultado da validação de schema."""

    is_valid: bool = Field(..., description="Se o schema é válido")
    schema_type: str = Field(..., description="Tipo de schema validado (input/output)")
    issues: List[SchemaValidationIssue] = Field(default_factory=list, description="Lista de issues")
    validation_errors: List[Dict[str, Any]] = Field(
        default_factory=list, description="Erros JSON Schema"
    )
    recommendations: List[str] = Field(
        default_factory=list, description="Recomendações de melhoria"
    )


class SchemaValidator:
    """
    Validador de JSON Schema para ferramentas MCP.

    Utiliza jsonschema library para validar conforme Draft 7.
    """

    # Tipos primitivos suportados pelo JSON Schema
    PRIMITIVE_TYPES = {"string", "number", "integer", "boolean", "null"}

    # Formatos string comuns
    STRING_FORMATS = {
        "email",
        "uri",
        "date",
        "date-time",
        "time",
        "uuid",
        "hostname",
        "ipv4",
        "ipv6",
        "regex",
    }

    def __init__(self, strict_mode: bool = False):
        """
        Inicializa validador de schema.

        Args:
            strict_mode: Se True, rejeita schemas com warnings
        """
        self.strict_mode = strict_mode
        self.format_checker = FormatChecker()

    def validate_input_schema(
        self, schema: Dict[str, Any], tool_name: str
    ) -> SchemaValidationResult:
        """
        Valida schema de entrada de ferramenta MCP.

        Args:
            schema: Schema JSON a validar
            tool_name: Nome da ferramenta (para logging)

        Returns:
            Resultado da validação
        """
        return self._validate_schema(schema, tool_name, "input")

    def validate_output_schema(
        self, schema: Dict[str, Any], tool_name: str
    ) -> SchemaValidationResult:
        """
        Valida schema de saída de ferramenta MCP.

        Args:
            schema: Schema JSON a validar
            tool_name: Nome da ferramenta (para logging)

        Returns:
            Resultado da validação
        """
        return self._validate_schema(schema, tool_name, "output")

    def validate_schema_draft7(self, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Valida se o schema está conforme JSON Schema Draft 7.

        Args:
            schema: Schema a validar

        Returns:
            Lista de erros de validação
        """
        errors = []

        try:
            # Tenta criar validator para detectar erros estruturais
            Draft7Validator.check_schema(schema)
        except Exception as e:
            errors.append({"type": "schema_structure_error", "message": str(e), "path": "$"})

        return errors

    def validate_sample_data(
        self, schema: Dict[str, Any], sample: Dict[str, Any]
    ) -> SchemaValidationResult:
        """
        Valida dados de exemplo contra schema.

        Args:
            schema: Schema JSON
            sample: Dados de exemplo

        Returns:
            Resultado da validação
        """
        result = SchemaValidationResult(
            is_valid=True, schema_type="sample_validation", issues=[], validation_errors=[]
        )

        try:
            jsonschema_validate(instance=sample, schema=schema, format_checker=self.format_checker)
            logger.info("sample_data_valid", schema_keys=list(schema.keys()))
        except ValidationError as e:
            result.is_valid = False
            result.validation_errors.append(
                {
                    "path": "->".join(str(p) for p in e.path),
                    "message": e.message,
                    "failed_value": e.instance,
                }
            )
            result.issues.append(
                SchemaValidationIssue(
                    type="validation_error",
                    severity=ValidationSeverity.ERROR,
                    message=f"Sample data inválido: {e.message}",
                    path="->".join(str(p) for p in e.path),
                )
            )

        return result

    def _validate_schema(
        self, schema: Dict[str, Any], tool_name: str, schema_type: str
    ) -> SchemaValidationResult:
        """
        Valida schema genérico.

        Args:
            schema: Schema JSON
            tool_name: Nome da ferramenta
            schema_type: Tipo de schema (input/output)

        Returns:
            Resultado da validação
        """
        result = SchemaValidationResult(
            is_valid=True,
            schema_type=schema_type,
            issues=[],
            validation_errors=[],
            recommendations=[],
        )

        # 1. Validar estrutura conforme Draft 7
        draft_errors = self.validate_schema_draft7(schema)
        if draft_errors:
            result.is_valid = False
            result.validation_errors.extend(draft_errors)
            for error in draft_errors:
                result.issues.append(
                    SchemaValidationIssue(
                        type="draft7_violation",
                        severity=ValidationSeverity.ERROR,
                        message=error["message"],
                        path=error.get("path", "$"),
                    )
                )

        # 2. Validar campos obrigatórios
        if not schema:
            result.is_valid = False
            result.issues.append(
                SchemaValidationIssue(
                    type="empty_schema",
                    severity=ValidationSeverity.ERROR,
                    message="Schema está vazio",
                    path="$",
                )
            )
            return result

        # 3. Validar tipo
        if "type" not in schema:
            result.issues.append(
                SchemaValidationIssue(
                    type="missing_type",
                    severity=ValidationSeverity.WARNING,
                    message="Schema não define 'type'. Recomendado especificar tipo primitivo ou 'object'",
                    path="$",
                    suggestion="Adicione 'type': 'object' para objetos complexos",
                )
            )
        elif schema["type"] == "object":
            # Validar properties se for objeto
            if "properties" not in schema:
                result.issues.append(
                    SchemaValidationIssue(
                        type="missing_properties",
                        severity=ValidationSeverity.WARNING,
                        message="Objeto sem 'properties'. Recomendado definir estrutura",
                        path="$",
                        suggestion="Adicione 'properties': {} mesmo que vazio",
                    )
                )

        # 4. Validar descrições
        self._validate_descriptions(schema, result)

        # 5. Validar formatos
        self._validate_formats(schema, result)

        # 6. Validar required fields
        self._validate_required_fields(schema, result)

        # 7. Validar enums
        self._validate_enums(schema, result)

        # 8. Checar modo estrito
        if self.strict_mode:
            errors = [i for i in result.issues if i.severity == ValidationSeverity.WARNING]
            if errors:
                result.is_valid = False

        logger.info(
            "schema_validation_completed",
            tool_name=tool_name,
            schema_type=schema_type,
            is_valid=result.is_valid,
            issues_count=len(result.issues),
        )

        return result

    def _validate_descriptions(
        self, schema: Dict[str, Any], result: SchemaValidationResult, path: str = "$"
    ):
        """Valida presença de descrições em campos."""
        if isinstance(schema, dict):
            # Schema sem descrição
            if "description" not in schema and "type" in schema:
                result.issues.append(
                    SchemaValidationIssue(
                        type="missing_description",
                        severity=ValidationSeverity.INFO,
                        message="Campo sem 'description'",
                        path=path,
                    )
                )

            # Recursão para properties
            if "properties" in schema and isinstance(schema["properties"], dict):
                for prop_name, prop_schema in schema["properties"].items():
                    if "description" not in prop_schema:
                        result.issues.append(
                            SchemaValidationIssue(
                                type="missing_description",
                                severity=ValidationSeverity.INFO,
                                message=f"Property '{prop_name}' sem descrição",
                                path=f"{path}.properties.{prop_name}",
                            )
                        )
                    self._validate_descriptions(
                        prop_schema, result, f"{path}.properties.{prop_name}"
                    )

            # Recursão para items (arrays)
            if "items" in schema and isinstance(schema["items"], dict):
                self._validate_descriptions(schema["items"], result, f"{path}.items")

    def _validate_formats(
        self, schema: Dict[str, Any], result: SchemaValidationResult, path: str = "$"
    ):
        """Valida formatos de string."""
        if isinstance(schema, dict):
            if schema.get("type") == "string":
                fmt = schema.get("format")
                if fmt and fmt not in self.STRING_FORMATS:
                    result.issues.append(
                        SchemaValidationIssue(
                            type="unknown_format",
                            severity=ValidationSeverity.WARNING,
                            message=f"Formato '{fmt}' não é padrão JSON Schema",
                            path=path,
                            suggestion=f"Usar um dos: {', '.join(sorted(self.STRING_FORMATS))}",
                        )
                    )

            # Recursão
            if "properties" in schema:
                for prop_name, prop_schema in schema["properties"].items():
                    self._validate_formats(prop_schema, result, f"{path}.properties.{prop_name}")

            if "items" in schema:
                self._validate_formats(schema["items"], result, f"{path}.items")

    def _validate_required_fields(
        self, schema: Dict[str, Any], result: SchemaValidationResult, path: str = "$"
    ):
        """Valida lista de required."""
        if isinstance(schema, dict):
            required = schema.get("required", [])
            properties = schema.get("properties", {})

            if not isinstance(required, list):
                result.issues.append(
                    SchemaValidationIssue(
                        type="invalid_required",
                        severity=ValidationSeverity.ERROR,
                        message="'required' deve ser uma lista",
                        path=path,
                    )
                )
            else:
                # Checar se required existem em properties
                for req_field in required:
                    if req_field not in properties:
                        result.issues.append(
                            SchemaValidationIssue(
                                type="required_not_in_properties",
                                severity=ValidationSeverity.WARNING,
                                message=f"Campo '{req_field}' em 'required' não existe em 'properties'",
                                path=path,
                                suggestion=f"Adicionar '{req_field}' às properties ou remover de 'required'",
                            )
                        )

    def _validate_enums(
        self, schema: Dict[str, Any], result: SchemaValidationResult, path: str = "$"
    ):
        """Valida definições de enum."""
        if isinstance(schema, dict):
            if "enum" in schema:
                enum_values = schema["enum"]
                if not isinstance(enum_values, list) or len(enum_values) == 0:
                    result.issues.append(
                        SchemaValidationIssue(
                            type="invalid_enum",
                            severity=ValidationSeverity.ERROR,
                            message="'enum' deve ser uma lista não vazia",
                            path=path,
                        )
                    )
                elif len(enum_values) == 1:
                    result.issues.append(
                        SchemaValidationIssue(
                            type="single_value_enum",
                            severity=ValidationSeverity.INFO,
                            message="Enum com único valor - considere usar const",
                            path=path,
                        )
                    )

            # Recursão
            if "properties" in schema:
                for prop_name, prop_schema in schema["properties"].items():
                    self._validate_enums(prop_schema, result, f"{path}.properties.{prop_name}")

            if "items" in schema:
                self._validate_enums(schema["items"], result, f"{path}.items")


def validate_tool_descriptor(
    tool_name: str,
    input_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    strict_mode: bool = False,
) -> Dict[str, Any]:
    """
    Valida descritor completo de ferramenta.

    Args:
        tool_name: Nome da ferramenta
        input_schema: Schema de entrada
        output_schema: Schema de saída
        strict_mode: Modo estrito de validação

    Returns:
        Dicionário com resultados consolidados
    """
    validator = SchemaValidator(strict_mode=strict_mode)

    results = {
        "tool_name": tool_name,
        "input_schema": None,
        "output_schema": None,
        "overall_valid": True,
    }

    if input_schema:
        input_result = validator.validate_input_schema(input_schema, tool_name)
        results["input_schema"] = input_result.model_dump()
        if not input_result.is_valid:
            results["overall_valid"] = False

    if output_schema:
        output_result = validator.validate_output_schema(output_schema, tool_name)
        results["output_schema"] = output_result.model_dump()
        if not output_result.is_valid:
            results["overall_valid"] = False

    return results
