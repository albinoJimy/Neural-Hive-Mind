"""Serviço de geração de testes automatizados."""

import uuid
from typing import Any, Optional

import structlog
from src.clients.llm_client_wrapper import LLMClient
from src.config.settings import Settings, get_settings
from src.models.tests import (
    TestCase,
    TestFramework,
    TestGenerationRequest,
    TestGenerationResult,
    TestSuite,
    TestType,
)

logger = structlog.get_logger(__name__)


class TestGenerator:
    """Serviço para geração de testes automatizados."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
    ):
        """Inicializa o serviço."""
        settings = get_settings()
        self._llm_client = llm_client or LLMClient(api_key=settings.openai_api_key)
        self._llm_model = settings.llm_model
        self._llm_temperature = settings.llm_temperature
        self._logger = logger

    async def generate_tests(self, request: TestGenerationRequest) -> TestGenerationResult:
        """
        Gera testes baseado em requisitos/user stories.

        Args:
            request: Request de geração com dados da fonte

        Returns:
            Resultado da geração com suíte de testes
        """
        start_time = structlog.get_logger().bind(request_id=request.source_type)

        self._logger.info(
            "generating_tests",
            source_type=request.source_type,
            test_types=[t.value for t in request.test_types],
        )

        test_cases = []

        # Gerar testes baseado no tipo da fonte
        if request.source_type == "requirements":
            test_cases = await self._generate_from_requirements(
                request.source_data,
                request.framework,
                request.language,
                request.test_types,
            )
        elif request.source_type == "user_stories":
            test_cases = await self._generate_from_user_stories(
                request.source_data,
                request.framework,
                request.language,
                request.test_types,
            )
        elif request.source_type == "acceptance_criteria":
            test_cases = await self._generate_from_acceptance_criteria(
                request.source_data,
                request.framework,
                request.language,
            )
        elif request.source_type == "code":
            test_cases = await self._generate_from_code(
                request.source_data,
                request.code_snippets,
                request.framework,
                request.language,
            )
        else:
            self._logger.warning("unknown_source_type", source_type=request.source_type)
            test_cases = []

        # Criar suíte de testes
        test_suite = TestSuite(
            id=f"TS-{uuid.uuid4().hex[:8]}",
            name=f"Test Suite for {request.source_type}",
            description=f"Generated tests from {request.source_type}",
            test_cases=test_cases,
            framework=request.framework,
            language=request.language,
            total_tests=len(test_cases),
            plan_id=request.plan_id,
        )

        # Estimar cobertura
        coverage_estimate = self._estimate_coverage(test_suite, request)

        result = TestGenerationResult(
            request_id=str(uuid.uuid4()),
            test_suite=test_suite,
            total_tests_generated=len(test_cases),
            coverage_estimate=coverage_estimate,
            files_created=[tc.file_path for tc in test_cases],
            generation_duration_ms=0,  # TODO: Calcular duração real
        )

        self._logger.info(
            "tests_generated",
            total=len(test_cases),
            coverage_estimate=coverage_estimate,
        )

        return result

    async def _generate_from_requirements(
        self,
        requirements: dict[str, Any],
        framework: TestFramework,
        language: str,
        test_types: list[TestType],
    ) -> list[TestCase]:
        """Gera testes a partir de requisitos."""
        test_cases = []
        req_list = requirements.get("requirements", [])

        for req in req_list[: self._get_settings().max_test_cases_per_requirement]:
            req_id = req.get("id", f"REQ-{uuid.uuid4().hex[:4]}")
            req_title = req.get("title", "Requisito sem título")
            req_desc = req.get("description", "")

            # Gerar teste unitário
            if TestType.UNIT in test_types:
                unit_test = await self._generate_unit_test(
                    req_id, req_title, req_desc, framework, language
                )
                test_cases.append(unit_test)

            # Gerar teste de integração
            if TestType.INTEGRATION in test_types:
                int_test = await self._generate_integration_test(
                    req_id, req_title, req_desc, framework, language
                )
                test_cases.append(int_test)

        return test_cases

    async def _generate_from_user_stories(
        self,
        user_stories: dict[str, Any],
        framework: TestFramework,
        language: str,
        test_types: list[TestType],
    ) -> list[TestCase]:
        """Gera testes a partir de user stories."""
        test_cases = []
        stories = user_stories.get("user_stories", [])

        for story in stories[:5]:  # Limitar a 5 stories
            story_id = story.get("id", f"US-{uuid.uuid4().hex[:4]}")
            role = story.get("role", "user")
            action = story.get("action", "ação")
            benefit = story.get("benefit", "benefício")

            # Gerar cenário de teste Given-When-Then
            scenario = self._story_to_scenario(role, action, benefit)

            if TestType.E2E in test_types:
                e2e_test = await self._generate_e2e_test(story_id, scenario, framework, language)
                test_cases.append(e2e_test)

        return test_cases

    async def _generate_from_acceptance_criteria(
        self,
        criteria: dict[str, Any],
        framework: TestFramework,
        language: str,
    ) -> list[TestCase]:
        """Gera testes a partir de critérios de aceitação."""
        test_cases = []
        ac_list = criteria.get("acceptance_criteria", [])

        for ac in ac_list[:10]:
            ac_id = ac.get("id", f"AC-{uuid.uuid4().hex[:4]}")
            statement = ac.get("statement", "")
            given = ac.get("given", "")
            when = ac.get("when", "")
            then = ac.get("then", "")

            # Gerar teste Given-When-Then
            test_code = await self._generate_gwt_test(ac_id, given, when, then, framework, language)

            test_cases.append(test_code)

        return test_cases

    async def _generate_from_code(
        self,
        code_data: dict[str, Any],
        code_snippets: dict[str, str],
        framework: TestFramework,
        language: str,
    ) -> list[TestCase]:
        """Gera testes a partir de código existente."""
        # TODO: Implementar análise de código e geração de testes
        return []

    async def _generate_unit_test(
        self,
        req_id: str,
        title: str,
        description: str,
        framework: TestFramework,
        language: str,
    ) -> TestCase:
        """Gera teste unitário."""
        prompt = self._build_unit_test_prompt(req_id, title, description, language)

        test_code = await self._call_llm(prompt)

        return TestCase(
            id=f"TC-{uuid.uuid4().hex[:8]}",
            name=f"Test: {title}",
            description=description,
            test_type=TestType.UNIT,
            framework=framework,
            test_code=test_code,
            file_path=f"tests/unit/test_{self._sanitize(title)}.py",
            requirement_id=req_id,
            language=language,
            tags=["unit", title.split()[0].lower()],
        )

    async def _generate_integration_test(
        self,
        req_id: str,
        title: str,
        description: str,
        framework: TestFramework,
        language: str,
    ) -> TestCase:
        """Gera teste de integração."""
        prompt = self._build_integration_test_prompt(req_id, title, description, language)

        test_code = await self._call_llm(prompt)

        return TestCase(
            id=f"TC-{uuid.uuid4().hex[:8]}",
            name=f"Integration: {title}",
            description=description,
            test_type=TestType.INTEGRATION,
            framework=framework,
            test_code=test_code,
            file_path=f"tests/integration/test_{self._sanitize(title)}_integration.py",
            requirement_id=req_id,
            language=language,
            tags=["integration"],
        )

    async def _generate_e2e_test(
        self,
        story_id: str,
        scenario: dict[str, str],
        framework: TestFramework,
        language: str,
    ) -> TestCase:
        """Gera teste E2E."""
        prompt = self._build_e2e_test_prompt(story_id, scenario, language)

        test_code = await self._call_llm(prompt)

        return TestCase(
            id=f"TC-{uuid.uuid4().hex[:8]}",
            name=f"E2E: {scenario.get('scenario', 'Test')}",
            description=scenario.get("description", ""),
            test_type=TestType.E2E,
            framework=framework,
            test_code=test_code,
            file_path=f"tests/e2e/test_{story_id}_e2e.py",
            user_story_id=story_id,
            language=language,
            tags=["e2e"],
        )

    async def _generate_gwt_test(
        self,
        ac_id: str,
        given: str,
        when: str,
        then: str,
        framework: TestFramework,
        language: str,
    ) -> TestCase:
        """Gera teste Given-When-Then."""
        prompt = f"""
Generate a test for the following acceptance criterion:

Given: {given}
When: {when}
Then: {then}

Language: {language}
Framework: {framework.value}

The test should follow the Given-When-Then pattern and include assertions.
"""

        test_code = await self._call_llm(prompt)

        return TestCase(
            id=f"TC-{uuid.uuid4().hex[:8]}",
            name=f"Acceptance: {ac_id}",
            description=f"{given} -> {when} -> {then}",
            test_type=TestType.UNIT,
            framework=framework,
            test_code=test_code,
            file_path=f"tests/acceptance/test_{ac_id}.py",
            acceptance_criteria_id=ac_id,
            language=language,
            tags=["acceptance"],
        )

    def _build_unit_test_prompt(
        self, req_id: str, title: str, description: str, language: str
    ) -> str:
        """Constrói prompt para geração de teste unitário."""
        return f"""
Generate a unit test for the following requirement:

Requirement ID: {req_id}
Title: {title}
Description: {description}

Language: {language}

The test should:
1. Test the core functionality described in the requirement
2. Include proper setup and teardown
3. Have clear assertions
4. Follow pytest conventions

Return only the test code without explanation.
"""

    def _build_integration_test_prompt(
        self, req_id: str, title: str, description: str, language: str
    ) -> str:
        """Constrói prompt para geração de teste de integração."""
        return f"""
Generate an integration test for the following requirement:

Requirement ID: {req_id}
Title: {title}
Description: {description}

Language: {language}

The integration test should:
1. Test interactions between components
2. Use mocks for external dependencies
3. Verify end-to-end behavior within the module boundary
4. Follow pytest conventions

Return only the test code without explanation.
"""

    def _build_e2e_test_prompt(self, story_id: str, scenario: dict[str, str], language: str) -> str:
        """Constrói prompt para geração de teste E2E."""
        return f"""
Generate an end-to-end test for the following user story scenario:

Story ID: {story_id}
Scenario: {scenario.get('scenario', 'Unknown')}
Role: {scenario.get('role', 'User')}
Action: {scenario.get('action', 'Action')}
Expected Result: {scenario.get('result', 'Result')}

Language: {language}

The E2E test should:
1. Simulate a real user scenario
2. Test through the UI or API layer
3. Include setup and cleanup
4. Follow pytest conventions

Return only the test code without explanation.
"""

    def _story_to_scenario(self, role: str, action: str, benefit: str) -> dict[str, str]:
        """Converte user story em cenário de teste."""
        return {
            "scenario": f"{role} wants to {action}",
            "role": role,
            "action": action,
            "result": benefit,
        }

    async def _call_llm(self, prompt: str) -> str:
        """Chama LLM para gerar código."""
        try:
            response = await self._llm_client.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert software testing engineer. Generate clean, well-structured test code following best practices.",
                    },
                    {"role": "user", "content": prompt},
                ],
                model=self._llm_model,
                temperature=self._llm_temperature,
                max_tokens=2000,
            )

            return response.choices[0].message["content"]

        except Exception as e:
            self._logger.error("llm_call_failed", error=str(e))
            # Retornar stub
            return "# Test generation failed\n# TODO: Manual implementation required"

    def _estimate_coverage(self, test_suite: TestSuite, request: TestGenerationRequest) -> float:
        """Estima cobertura de testes."""
        if test_suite.total_tests == 0:
            return 0.0

        # Estimativa simples: cada teste cobre ~10% do código
        # (simplificado - cálculo real seria mais complexo)
        estimated = min(test_suite.total_tests * 0.1, 1.0)
        return estimated

    def _sanitize(self, text: str) -> str:
        """Sanitiza texto para nome de arquivo."""
        import re

        # Remove caracteres especiais, substitui por underscore
        return re.sub(r"[^a-zA-Z0-9_]", "_", text.lower())[:50]

    def _get_settings(self) -> Settings:
        """Retorna configurações."""
        return get_settings()
