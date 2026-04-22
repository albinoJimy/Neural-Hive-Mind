"""Tests para o serviço de geração de testes."""

from unittest.mock import AsyncMock

import pytest
from models.tests import TestFramework, TestType

from services.test_generator import TestGeneratorService


class TestTestGeneratorService:
    """Testes para TestGeneratorService."""

    @pytest.fixture()
    def service(self, mock_openai_client, mock_settings):
        """Fixture do serviço."""
        return TestGeneratorService(llm_client=mock_openai_client)

    @pytest.fixture()
    def sample_requirement(self):
        """Requisito de exemplo."""
        return {
            "id": "REQ-001",
            "title": "Autenticação de Usuário",
            "description": "O sistema deve permitir autenticação via email e senha",
            "acceptance_criteria": [
                "Usuário deve conseguir fazer login com credenciais válidas",
                "Usuário não deve conseguir fazer login com credenciais inválidas",
            ],
        }

    @pytest.fixture()
    def sample_user_story(self):
        """User Story de exemplo."""
        return {
            "id": "US-001",
            "title": "Como usuário, quero fazer login",
            "description": "Para acessar minhas informações pessoais",
            "acceptance_criteria": [
                {
                    "id": "AC-001",
                    "given": "que estou na página de login",
                    "when": "insiro email e senha válidos",
                    "then": "devo ser redirecionado para o dashboard",
                }
            ],
        }

    async def test_generate_tests_from_requirements(self, service, sample_requirement):
        """Testa geração de testes a partir de requisitos."""
        result = await service.generate_tests(
            requirements=[sample_requirement],
            framework=TestFramework.PYTEST,
            language="python",
        )

        assert len(result.test_cases) > 0
        assert result.test_cases[0].framework == TestFramework.PYTEST
        assert result.test_cases[0].language == "python"

    async def test_generate_tests_from_user_stories(self, service, sample_user_story):
        """Testa geração de testes a partir de user stories."""
        result = await service.generate_tests(
            user_stories=[sample_user_story],
            test_type=TestType.E2E,
            framework=TestFramework.ROBOT,
        )

        assert len(result.test_cases) > 0
        assert all(tc.test_type == TestType.E2E for tc in result.test_cases)

    async def test_generate_unit_tests(self, service):
        """Testa geração de testes unitários."""
        code = """
def calculate_sum(a: int, b: int) -> int:
    return a + b
"""

        result = await service.generate_tests_from_code(
            code=code,
            language="python",
            framework=TestFramework.PYTEST,
        )

        assert len(result.test_cases) > 0
        assert all(tc.test_type == TestType.UNIT for tc in result.test_cases)

    async def test_generate_integration_tests(self, service, sample_requirement):
        """Testa geração de testes de integração."""
        result = await service.generate_tests(
            requirements=[sample_requirement],
            test_type=TestType.INTEGRATION,
            framework=TestFramework.PYTEST,
        )

        assert all(tc.test_type == TestType.INTEGRATION for tc in result.test_cases)

    async def test_llm_call_error_handling(self, service, sample_requirement):
        """Testa tratamento de erros na chamada LLM."""
        service.llm_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))

        with pytest.raises(Exception):
            await service.generate_tests(
                requirements=[sample_requirement],
                framework=TestFramework.PYTEST,
            )

    async def test_test_case_includes_tracking(self, service, sample_requirement):
        """Testa que casos de teste incluem rastreabilidade."""
        result = await service.generate_tests(
            requirements=[sample_requirement],
            framework=TestFramework.PYTEST,
        )

        assert result.test_cases[0].requirement_id == "REQ-001"

    async def test_generate_multiple_test_cases(self, service, sample_requirement):
        """Testa geração de múltiplos casos de teste."""
        result = await service.generate_tests(
            requirements=[sample_requirement],
            framework=TestFramework.PYTEST,
            max_test_cases_per_requirement=3,
        )

        assert len(result.test_cases) <= 3
