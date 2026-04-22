"""Testes de integração MongoDB para Test Generation.

Autor: Neural Hive Mind
Criado: 2026-04-19 (FEAT-G-002)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.database.mongodb_client import MongoDBClient
from src.database.repositories import GenerationResultRepository, TestSuiteRepository
from src.models.tests import TestCase, TestFramework, TestSuite, TestType


@pytest.mark.asyncio()
class TestMongoDBClientClass:
    """Testes para MongoDBClient."""

    @pytest.mark.asyncio()
    async def test_mongodb_client_starts_successfully(self):
        """Testa que o cliente MongoDB inicia corretamente."""
        client = MongoDBClient()

        # Mock motor client
        with patch("src.database.mongodb_client.AsyncIOMotorClient") as mock_motor:
            mock_instance = MagicMock()
            mock_instance.admin.command = AsyncMock(return_value="ok")
            mock_motor.return_value = mock_instance

            await client.connect()

            mock_instance.admin.command.assert_called_once_with("ping")
            assert client._client is not None

    @pytest.mark.asyncio()
    async def test_ping_returns_true_when_connected(self):
        """Testa que ping retorna True quando conectado."""
        client = MongoDBClient()

        with patch("src.database.mongodb_client.AsyncIOMotorClient") as mock_motor:
            mock_instance = MagicMock()
            mock_instance.admin.command = AsyncMock(return_value="ok")
            mock_motor.return_value = mock_instance

            await client.connect()

            is_connected = await client.ping()
            assert is_connected is True

    @pytest.mark.asyncio()
    async def test_ping_returns_false_when_disconnected(self):
        """Testa que ping retorna False quando desconectado."""
        client = MongoDBClient()

        # Sem conectar
        is_connected = await client.ping()
        assert is_connected is False

    @pytest.mark.asyncio()
    async def test_ping_returns_false_on_exception(self):
        """Testa que ping retorna False quando há erro."""
        client = MongoDBClient()

        with patch("src.database.mongodb_client.AsyncIOMotorClient") as mock_motor:
            mock_instance = MagicMock()
            # Primeira chamada (connect) funciona, segunda (ping) falha
            mock_instance.admin.command = AsyncMock(
                side_effect=["ok", Exception("Connection error")]
            )
            mock_motor.return_value = mock_instance

            await client.connect()

            is_connected = await client.ping()
            assert is_connected is False

    @pytest.mark.asyncio()
    async def test_health_check_returns_status(self):
        """Testa que health check retorna status detalhado."""
        client = MongoDBClient()

        with patch("src.database.mongodb_client.AsyncIOMotorClient") as mock_motor:
            mock_instance = MagicMock()
            mock_instance.admin.command = AsyncMock(return_value="ok")

            # Mock database e coleções - cada coleção precisa do seu próprio mock
            mock_db = MagicMock()
            mock_test_suites = MagicMock()
            mock_test_cases = MagicMock()
            mock_gen_results = MagicMock()

            # count_documents é async
            mock_test_suites.count_documents = AsyncMock(return_value=5)
            mock_test_cases.count_documents = AsyncMock(return_value=10)
            mock_gen_results.count_documents = AsyncMock(return_value=3)

            # Configurar atributos do database diretamente
            mock_db.test_suites = mock_test_suites
            mock_db.test_cases = mock_test_cases
            mock_db.generation_results = mock_gen_results

            mock_instance.__getitem__ = MagicMock(return_value=mock_db)
            mock_motor.return_value = mock_instance

            await client.connect()

            health = await client.health_check()

            assert health["mongodb_connected"] is True
            assert "database" in health
            assert "test_suites_count" in health

    @pytest.mark.asyncio()
    async def test_insert_test_suite(self):
        """Testa inserção de test suite."""
        client = MongoDBClient()

        with patch("src.database.mongodb_client.AsyncIOMotorClient") as mock_motor:
            mock_instance = MagicMock()
            mock_instance.admin.command = AsyncMock(return_value="ok")

            # Mock database and collection
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="test-id"))
            mock_db.test_suites = mock_collection
            mock_instance.__getitem__ = MagicMock(return_value=mock_db)
            mock_motor.return_value = mock_instance

            await client.connect()

            suite_data = {
                "id": "TS-123",
                "name": "Test Suite",
                "description": "Description",
                "framework": "pytest",
                "language": "python",
                "total_tests": 5,
                "plan_id": "plan-1",
            }

            result_id = await client.insert_test_suite(suite_data)

            assert result_id == "test-id"
            mock_collection.insert_one.assert_called_once()

    @pytest.mark.asyncio()
    async def test_get_test_suite(self):
        """Testa busca de test suite por ID."""
        client = MongoDBClient()

        with patch("src.database.mongodb_client.AsyncIOMotorClient") as mock_motor:
            mock_instance = MagicMock()
            mock_instance.admin.command = AsyncMock(return_value="ok")

            mock_db = MagicMock()
            mock_collection = MagicMock()
            expected_suite = {"id": "TS-123", "name": "Test Suite"}
            mock_collection.find_one = AsyncMock(return_value=expected_suite)
            mock_db.test_suites = mock_collection
            mock_instance.__getitem__ = MagicMock(return_value=mock_db)
            mock_motor.return_value = mock_instance

            await client.connect()

            suite = await client.get_test_suite("TS-123")

            assert suite is not None
            assert suite["id"] == "TS-123"

    @pytest.mark.asyncio()
    async def test_delete_test_suite(self):
        """Testa deleção de test suite."""
        client = MongoDBClient()

        with patch("src.database.mongodb_client.AsyncIOMotorClient") as mock_motor:
            mock_instance = MagicMock()
            mock_instance.admin.command = AsyncMock(return_value="ok")

            mock_db = MagicMock()
            mock_test_cases = MagicMock()
            mock_test_suites = MagicMock()

            # delete_many e delete_one são async
            mock_test_cases.delete_many = AsyncMock(return_value=MagicMock(deleted_count=2))
            mock_test_suites.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))

            # Configurar atributos do database diretamente
            mock_db.test_cases = mock_test_cases
            mock_db.test_suites = mock_test_suites

            mock_instance.__getitem__ = MagicMock(return_value=mock_db)
            mock_motor.return_value = mock_instance

            await client.connect()

            result = await client.delete_test_suite("TS-123")

            assert result is True
            mock_test_cases.delete_many.assert_called_once_with({"test_suite_id": "TS-123"})
            mock_test_suites.delete_one.assert_called_once_with({"id": "TS-123"})


@pytest.mark.asyncio()
class TestTestSuiteRepository:
    """Testes para TestSuiteRepository."""

    @pytest.mark.asyncio()
    async def test_save_test_suite(self):
        """Testa salvamento de test suite com test cases."""
        mock_db = MagicMock()

        # Mock insert_test_suite
        mock_db.insert_test_suite = AsyncMock(return_value="suite-mongo-id")
        # Mock insert_test_cases
        mock_db.insert_test_cases = AsyncMock(return_value=["tc1", "tc2"])

        repo = TestSuiteRepository(mock_db)

        # Criar test suite
        test_suite = TestSuite(
            id="TS-123",
            name="Authentication Tests",
            description="Tests for authentication",
            test_cases=[
                TestCase(
                    id="TC-001",
                    name="Test Login",
                    description="Test login functionality",
                    test_type=TestType.UNIT,
                    framework=TestFramework.PYTEST,
                    test_code="def test_login(): pass",
                    file_path="tests/test_login.py",
                    language="python",
                    tags=["auth"],
                )
            ],
            framework=TestFramework.PYTEST,
            language="python",
            total_tests=1,
            plan_id="plan-1",
        )

        suite_id = await repo.save(test_suite)

        assert suite_id == "suite-mongo-id"
        mock_db.insert_test_suite.assert_called_once()
        mock_db.insert_test_cases.assert_called_once()

    @pytest.mark.asyncio()
    async def test_find_by_id(self):
        """Testa busca de test suite por ID."""
        mock_db = MagicMock()
        expected_suite = {"id": "TS-123", "name": "Test Suite"}
        mock_db.get_test_suite = AsyncMock(return_value=expected_suite)

        repo = TestSuiteRepository(mock_db)

        suite = await repo.find_by_id("TS-123")

        assert suite is not None
        assert suite["id"] == "TS-123"
        mock_db.get_test_suite.assert_called_once_with("TS-123")

    @pytest.mark.asyncio()
    async def test_find_by_plan_id(self):
        """Testa busca de test suites por plan ID."""
        mock_db = MagicMock()
        expected_suites = [
            {"id": "TS-123", "plan_id": "plan-1"},
            {"id": "TS-124", "plan_id": "plan-1"},
        ]
        mock_db.list_test_suites = AsyncMock(return_value=expected_suites)

        repo = TestSuiteRepository(mock_db)

        suites = await repo.find_by_plan_id("plan-1")

        assert len(suites) == 2
        mock_db.list_test_suites.assert_called_once_with(plan_id="plan-1")

    @pytest.mark.asyncio()
    async def test_update_coverage(self):
        """Testa atualização de cobertura."""
        mock_db = MagicMock()
        mock_db.update_test_suite = AsyncMock(return_value=True)

        repo = TestSuiteRepository(mock_db)

        result = await repo.update_coverage("TS-123", 0.85)

        assert result is True
        mock_db.update_test_suite.assert_called_once_with("TS-123", {"coverage": 0.85})

    @pytest.mark.asyncio()
    async def test_delete(self):
        """Testa deleção de test suite."""
        mock_db = MagicMock()
        mock_db.delete_test_suite = AsyncMock(return_value=True)

        repo = TestSuiteRepository(mock_db)

        result = await repo.delete("TS-123")

        assert result is True
        mock_db.delete_test_suite.assert_called_once_with("TS-123")


@pytest.mark.asyncio()
class TestGenerationResultRepo:
    """Testes para GenerationResultRepository."""

    @pytest.mark.asyncio()
    async def test_save_generation_result(self):
        """Testa salvamento de resultado de geração."""
        mock_db = MagicMock()
        mock_db.insert_generation_result = AsyncMock(return_value="result-id")

        repo = GenerationResultRepository(mock_db)

        # Criar resultado
        result = MagicMock()
        result.request_id = "REQ-123"
        result.test_suite.id = "TS-123"
        result.total_tests_generated = 5
        result.coverage_estimate = 0.8
        result.files_created = ["test1.py", "test2.py"]
        result.generation_duration_ms = 1500

        result_id = await repo.save(result)

        assert result_id == "result-id"
        mock_db.insert_generation_result.assert_called_once()

    @pytest.mark.asyncio()
    async def test_find_by_request_id(self):
        """Testa busca por request ID."""
        mock_db = MagicMock()
        expected_result = {"request_id": "REQ-123", "total_tests_generated": 5}
        mock_db.get_generation_result = AsyncMock(return_value=expected_result)

        repo = GenerationResultRepository(mock_db)

        result = await repo.find_by_request_id("REQ-123")

        assert result is not None
        assert result["request_id"] == "REQ-123"
        mock_db.get_generation_result.assert_called_once_with("REQ-123")

    @pytest.mark.asyncio()
    async def test_find_by_suite_id(self):
        """Testa busca por test suite ID."""
        mock_db = MagicMock()
        expected_results = [
            {"request_id": "REQ-123", "test_suite_id": "TS-123"},
            {"request_id": "REQ-124", "test_suite_id": "TS-123"},
        ]

        # Criar mock de cursor async
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=expected_results)

        # Mock generation_results collection
        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)
        mock_db.generation_results = MagicMock(return_value=mock_collection)

        repo = GenerationResultRepository(mock_db)

        results = await repo.find_by_suite_id("TS-123")

        assert len(results) == 2
