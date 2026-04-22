"""Router REST para Test Generation API."""

from typing import Optional

from fastapi import APIRouter, HTTPException, status
from structlog import get_logger

from src.models.tests import (
    TestCoverage,
    TestFramework,
    TestGenerationRequest,
    TestGenerationResult,
    TestSuite,
    TestType,
)
from src.services.test_generator import TestGenerator

logger = get_logger(__name__)

router = APIRouter(prefix="/tests", tags=["tests"])

# Singleton
_test_generator: Optional[TestGenerator] = None


def get_test_generator() -> TestGenerator:
    """Retorna instância singleton."""
    global _test_generator
    if _test_generator is None:
        _test_generator = TestGenerator()
    return _test_generator


@router.post(
    "/generate",
    response_model=TestGenerationResult,
    status_code=status.HTTP_201_CREATED,
    summary="Gerar testes automaticamente",
)
async def generate_tests(request: TestGenerationRequest) -> TestGenerationResult:
    """
    Gera testes automaticamente baseado em requisitos, user stories ou código.

    Suporta as seguintes fontes:
    - **requirements**: Gera testes unitários e de integração
    - **user_stories**: Gera cenários E2E baseados em user stories
    - **acceptance_criteria**: Gera testes Given-When-Then
    - **code**: Analisa código e gera testes

    Exemplo de payload para requirements:
    ```json
    {
        "source_type": "requirements",
        "source_data": {
            "requirements": [
                {
                    "id": "REQ-001",
                    "title": "User Authentication",
                    "description": "Sistema deve permitir login via email e senha"
                }
            ]
        },
        "test_types": ["unit", "integration"],
        "framework": "pytest",
        "language": "python"
    }
    ```
    """
    generator = get_test_generator()

    try:
        result = await generator.generate_tests(request)
        return result

    except Exception as e:
        logger.error("test_generation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha na geração de testes: {e!s}",
        )


@router.post(
    "/generate/from-requirements",
    response_model=TestGenerationResult,
    summary="Gerar testes a partir de requisitos",
)
async def generate_from_requirements(
    requirements: list[dict],
    test_types: list[str] = ["unit", "integration"],
    framework: str = "pytest",
    language: str = "python",
    plan_id: Optional[str] = None,
) -> TestGenerationResult:
    """
    Gera testes a partir de uma lista de requisitos.

    Args:
        requirements: Lista de requisitos com id, title, description
        test_types: Tipos de teste a gerar
        framework: Framework de teste
        language: Linguagem do código
        plan_id: ID do plano relacionado
    """
    from src.models.tests import TestFramework, TestType

    # Converter strings para enums
    test_type_enums = [TestType(t) for t in test_types]
    framework_enum = TestFramework(framework)

    request = TestGenerationRequest(
        source_type="requirements",
        source_data={"requirements": requirements},
        test_types=test_type_enums,
        framework=framework_enum,
        language=language,
        plan_id=plan_id,
    )

    return await generate_tests(request)


@router.post(
    "/generate/from-user-stories",
    response_model=TestGenerationResult,
    summary="Gerar testes E2E a partir de user stories",
)
async def generate_from_user_stories(
    user_stories: list[dict],
    framework: str = "pytest",
    language: str = "python",
    plan_id: Optional[str] = None,
) -> TestGenerationResult:
    """
    Gera testes E2E a partir de user stories.

    Cada user story deve ter:
    - role: Papel do usuário
    - action: Ação que realiza
    - benefit: Benefício esperado
    """
    request = TestGenerationRequest(
        source_type="user_stories",
        source_data={"user_stories": user_stories},
        test_types=[TestType.E2E],
        framework=TestFramework(framework),
        language=language,
        plan_id=plan_id,
    )

    return await generate_tests(request)


@router.get("/coverage", response_model=TestCoverage, summary="Obter cobertura de testes")
async def get_coverage(plan_id: Optional[str] = None) -> TestCoverage:
    """
    Retorna métricas de cobertura de testes.

    Args:
        plan_id: Filtrar por plano específico (opcional)
    """
    # TODO: Buscar dados reais do MongoDB
    return TestCoverage(
        total_requirements=0,
        requirements_with_tests=0,
        total_user_stories=0,
        user_stories_with_tests=0,
        line_coverage=0.0,
    )


@router.get("/suites", response_model=list[TestSuite], summary="Listar suítes de testes")
async def list_test_suites(
    plan_id: Optional[str] = None,
    limit: int = 50,
) -> list[TestSuite]:
    """
    Lista suítes de testes geradas.

    Args:
        plan_id: Filtrar por plano
        limit: Limite de resultados
    """
    # TODO: Buscar do MongoDB
    return []


@router.get("/health", summary="Health check")
async def health_check() -> dict:
    """Verifica saúde do serviço."""
    return {
        "status": "healthy",
        "service": "test-generation",
        "version": "0.1.0",
    }
