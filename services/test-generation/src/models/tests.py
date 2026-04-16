"""Modelos de domínio para Test Generation."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TestType(str, Enum):
    """Tipo de teste."""

    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"
    PERFORMANCE = "performance"
    SECURITY = "security"


class TestFramework(str, Enum):
    """Framework de teste."""

    PYTEST = "pytest"
    JEST = "jest"
    JUNIT = "junit"
    GO_TEST = "go_test"
    ROBOT = "robot"


class TestCase(BaseModel):
    """Caso de teste gerado."""

    id: str = Field(..., description="ID único do caso de teste")
    name: str = Field(..., description="Nome do teste")
    description: str = Field(..., description="Descrição do que testa")
    test_type: TestType = Field(..., description="Tipo do teste")
    framework: TestFramework = Field(..., description="Framework usado")

    # Conteúdo gerado
    test_code: str = Field(..., description="Código do teste")
    file_path: str = Field(..., description="Caminho do arquivo")

    # Rastreabilidade
    requirement_id: Optional[str] = Field(None, description="ID do requisito origem")
    user_story_id: Optional[str] = Field(None, description="ID da user story origem")
    acceptance_criteria_id: Optional[str] = Field(None, description="ID do critério de aceitação")

    # Metadados
    language: str = Field(..., description="Linguagem do código testado")
    tags: List[str] = Field(default_factory=list, description="Tags para organização")
    priority: str = Field(default="medium", description="Prioridade: low/medium/high/critical")

    # Status
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed: bool = Field(default=False, description="Se foi revisado por humano")


class TestSuite(BaseModel):
    """Suíte de testes gerada."""

    id: str = Field(..., description="ID único da suíte")
    name: str = Field(..., description="Nome da suíte")
    description: str = Field(..., description="Descrição da suíte")

    # Testes incluídos
    test_cases: List[TestCase] = Field(default_factory=list)

    # Configuração
    framework: TestFramework = Field(..., description="Framework")
    language: str = Field(..., description="Linguagem principal")
    setup_code: Optional[str] = Field(None, description="Código de setup")
    teardown_code: Optional[str] = Field(None, description="Código de teardown")

    # Métricas
    total_tests: int = Field(default=0, description="Total de testes")
    estimated_duration_seconds: int = Field(
        default=60,
        description="Duração estimada"
    )

    # Rastreabilidade
    plan_id: Optional[str] = Field(None, description="ID do plano origem")
    requirements_ids: List[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)


class TestGenerationRequest(BaseModel):
    """Request para geração de testes."""

    source_type: str = Field(
        ...,
        description="Tipo da fonte: requirements, user_stories, acceptance_criteria, code"
    )
    source_data: Dict[str, Any] = Field(..., description="Dados da fonte")

    # Configuração
    test_types: List[TestType] = Field(
        default_factory=lambda: [TestType.UNIT, TestType.INTEGRATION],
        description="Tipos de teste a gerar"
    )
    framework: TestFramework = Field(
        default=TestFramework.PYTEST,
        description="Framework de teste"
    )
    language: str = Field(default="python", description="Linguagem do código")

    # Contexto adicional
    plan_id: Optional[str] = Field(None, description="ID do plano")
    code_snippets: Dict[str, str] = Field(
        default_factory=dict,
        description="Snippets de código para análise"
    )


class TestGenerationResult(BaseModel):
    """Resultado da geração de testes."""

    request_id: str
    test_suite: TestSuite
    total_tests_generated: int
    coverage_estimate: float

    # Informações de arquivos
    files_created: List[str] = Field(default_factory=list, description="Arquivos gerados")

    # Status
    generation_duration_ms: int
    status: str = Field(default="completed")

    created_at: datetime = Field(default_factory=datetime.utcnow)


class TestCoverage(BaseModel):
    """Cobertura de testes."""

    total_requirements: int = 0
    requirements_with_tests: int = 0
    total_user_stories: int = 0
    user_stories_with_tests: int = 0

    line_coverage: float = 0.0
    branch_coverage: float = 0.0

    def coverage_percentage(self) -> float:
        """Retorna cobertura percentual."""
        if self.total_requirements == 0:
            return 0.0
        return (self.requirements_with_tests / self.total_requirements) * 100
