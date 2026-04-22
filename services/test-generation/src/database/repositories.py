"""Repositórios MongoDB para Test Generation.

Autor: Neural Hive Mind
Criado: 2026-04-19 (FEAT-G-002)

Repositórios para persistência e recuperação de
test suites, test cases e resultados de geração.
"""

from typing import Any, Optional

import structlog

from src.database.mongodb_client import MongoDBClient
from src.models.tests import TestGenerationResult, TestSuite

logger = structlog.get_logger(__name__)


class TestSuiteRepository:
    """Repositório para TestSuites."""

    def __init__(self, db_client: MongoDBClient):
        """Inicializa o repositório.

        Args:
            db_client: Cliente MongoDB
        """
        self._db = db_client
        self._logger = logger

    async def save(self, test_suite: TestSuite) -> str:
        """Salva uma test suite completa.

        Args:
            test_suite: TestSuite para salvar

        Returns:
            ID do documento inserido
        """
        # Converter para dict
        suite_data = {
            "id": test_suite.id,
            "name": test_suite.name,
            "description": test_suite.description,
            "framework": test_suite.framework.value,
            "language": test_suite.language,
            "total_tests": test_suite.total_tests,
            "plan_id": test_suite.plan_id,
            "tags": list(test_suite.tags) if test_suite.tags else [],
        }

        # Salvar suite
        suite_id = await self._db.insert_test_suite(suite_data)
        self._logger.info(
            "test_suite_saved",
            test_suite_id=test_suite.id,
            mongo_id=suite_id,
        )

        # Salvar test cases
        if test_suite.test_cases:
            test_cases_data = []
            for tc in test_suite.test_cases:
                tc_dict = {
                    "id": tc.id,
                    "test_suite_id": test_suite.id,
                    "name": tc.name,
                    "description": tc.description,
                    "test_type": tc.test_type.value,
                    "framework": tc.framework.value,
                    "test_code": tc.test_code,
                    "file_path": tc.file_path,
                    "language": tc.language,
                    "requirement_id": tc.requirement_id,
                    "user_story_id": tc.user_story_id,
                    "acceptance_criteria_id": tc.acceptance_criteria_id,
                    "tags": list(tc.tags) if tc.tags else [],
                }
                test_cases_data.append(tc_dict)

            await self._db.insert_test_cases(test_cases_data)
            self._logger.info(
                "test_cases_saved",
                test_suite_id=test_suite.id,
                count=len(test_cases_data),
            )

        return suite_id

    async def find_by_id(self, suite_id: str) -> Optional[dict[str, Any]]:
        """Busca uma test suite por ID.

        Args:
            suite_id: ID da test suite

        Returns:
            Dados da test suite ou None
        """
        return await self._db.get_test_suite(suite_id)

    async def find_by_plan_id(self, plan_id: str) -> list[dict[str, Any]]:
        """Busca test suites por plan ID.

        Args:
            plan_id: ID do plano

        Returns:
            Lista de test suites
        """
        return await self._db.list_test_suites(plan_id=plan_id)

    async def update_coverage(self, suite_id: str, coverage: float) -> bool:
        """Atualiza cobertura de uma test suite.

        Args:
            suite_id: ID da test suite
            coverage: Cobertura calculada

        Returns:
            True se atualizou, False caso contrário
        """
        return await self._db.update_test_suite(suite_id, {"coverage": coverage})

    async def delete(self, suite_id: str) -> bool:
        """Deleta uma test suite e seus test cases.

        Args:
            suite_id: ID da test suite

        Returns:
            True se deletou, False caso contrário
        """
        return await self._db.delete_test_suite(suite_id)


class GenerationResultRepository:
    """Repositório para resultados de geração."""

    def __init__(self, db_client: MongoDBClient):
        """Inicializa o repositório.

        Args:
            db_client: Cliente MongoDB
        """
        self._db = db_client
        self._logger = logger

    async def save(self, result: TestGenerationResult) -> str:
        """Salva resultado de geração.

        Args:
            result: Resultado da geração

        Returns:
            ID do documento inserido
        """
        result_data = {
            "request_id": result.request_id,
            "test_suite_id": result.test_suite.id,
            "total_tests_generated": result.total_tests_generated,
            "coverage_estimate": result.coverage_estimate,
            "files_created": result.files_created,
            "generation_duration_ms": result.generation_duration_ms,
        }

        result_id = await self._db.insert_generation_result(result_data)
        self._logger.info(
            "generation_result_saved",
            request_id=result.request_id,
            test_suite_id=result.test_suite.id,
            mongo_id=result_id,
        )

        return result_id

    async def find_by_request_id(self, request_id: str) -> Optional[dict[str, Any]]:
        """Busca resultado por request ID.

        Args:
            request_id: ID do request

        Returns:
            Dados do resultado ou None
        """
        return await self._db.get_generation_result(request_id)

    async def find_by_suite_id(self, suite_id: str) -> list[dict[str, Any]]:
        """Busca resultados por test suite ID.

        Args:
            suite_id: ID da test suite

        Returns:
            Lista de resultados
        """
        cursor = self._db.generation_results().find({"test_suite_id": suite_id})
        return await cursor.to_list(length=None)
