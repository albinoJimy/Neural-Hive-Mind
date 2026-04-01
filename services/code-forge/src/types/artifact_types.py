"""
Tipos centralizados para artefatos do CodeForge.

Este módulo unifica as definições de tipos e linguagens que antes
estavam espalhadas em múltiplos arquivos, eliminando duplicação
e inconsistências.

Novos nomes:
- ArtifactCategory: categorias de alto nível (CODE, IAC, TEST, etc)
- ArtifactSubtype: subtipos específicos (MICROSERVICE, LAMBDA_FUNCTION, etc)
- CodeLanguage: linguagens unificadas (python, javascript, typescript, etc)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ArtifactCategory(str, Enum):
    """Categorias de alto nível para CodeForgeArtifact.

    Usado em models/artifact.py para classificar artefatos principais.
    """

    CODE = "CODE"
    IAC = "IAC"
    TEST = "TEST"
    POLICY = "POLICY"
    DOCUMENTATION = "DOCUMENTATION"
    CONTAINER = "CONTAINER"
    CHART = "CHART"
    FUNCTION = "FUNCTION"


class ArtifactSubtype(str, Enum):
    """Subtipos específicos para geração de código e Dockerfiles.

    Usado em services/dockerfile_generator.py e services/pipeline_engine.py
    para distinguir entre diferentes tipos de artefatos de código.
    """

    MICROSERVICE = "microservice"
    LAMBDA_FUNCTION = "lambda_function"
    CLI_TOOL = "cli_tool"
    LIBRARY = "library"
    SCRIPT = "script"


class CodeLanguage(str, Enum):
    """Linguagens de programação suportadas.

    Valores em lowercase para consistência com parâmetros do Kafka.
    """

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    JAVA = "java"
    RUST = "rust"
    CSHARP = "csharp"
    BASH = "bash"
    HCL = "hcl"
    YAML = "yaml"
    REGO = "rego"
    NODEJS = "nodejs"  # Alias para javascript
    GOLANG = "golang"  # Alias para go


__all__ = [
    "ArtifactCategory",
    "ArtifactSubtype",
    "CodeLanguage",
    "ValidationType",
    "ValidationStatus",
    "ValidationResult",
]


# ===== COMPATIBILIDADE (Aliases para código legado) =====
# Manter compatibilidade com código existente que usa os nomes antigos
ArtifactType = ArtifactCategory  # legacy alias
TemplateLanguage = CodeLanguage  # legacy alias
SupportedLanguage = CodeLanguage  # legacy alias


# ===== VALIDATION TYPES =====
# Tipos para resultados de validação de segurança e qualidade


class ValidationType(str, Enum):
    """Tipos de validação suportados."""

    SAST = "SAST"
    SCA = "SCA"
    LICENSE_CHECK = "LICENSE_CHECK"
    CONTAINER_SCAN = "CONTAINER_SCAN"
    IAC_SCAN = "IAC_SCAN"
    DEPENDENCY_CHECK = "DEPENDENCY_CHECK"


class ValidationStatus(str, Enum):
    """Status de validação."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    PENDING = "PENDING"


@dataclass
class ValidationResult:
    """Resultado de uma validação."""

    validation_type: ValidationType
    tool_name: str
    tool_version: str
    status: ValidationStatus
    score: float
    issues_count: int
    critical_issues: int
    high_issues: int
    medium_issues: int
    low_issues: int
    executed_at: Optional[str] = None
    duration_ms: int = 0
    report_uri: Optional[str] = None
