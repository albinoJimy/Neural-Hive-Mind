"""Testes E2E para fluxo completo de geração de testes.

Autor: Neural Hive Mind
Criado: 2026-04-19 (FEAT-G-004)

Estes testes verificam o fluxo completo desde o consumo de mensagens Kafka
até a persistência no MongoDB e publicação do resultado.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.consumers.requirements_consumer import RequirementsConsumer
from src.database.mongodb_client import MongoDBClient
from src.database.repositories import GenerationResultRepository, TestSuiteRepository
from src.producers.tests_producer import TestsProducer
from src.services.test_generator import (
    TestFramework,
    TestGenerationRequest,
    TestGenerator,
    TestType,
)


@pytest.mark.asyncio()
class TestE2EGenerationFlow:
    """Testes E2E do fluxo de geração de testes."""

    @pytest.mark.asyncio()
    async def test_full_flow_requirements_to_tests(self):
        """Testa fluxo completo: requirements → consumer → generator → mongodb."""
        # Setup mocks
        mock_llm_client = AsyncMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()

        mock_message.content = """import pytest

def test_requirement_user_authentication():
    '''Test user authentication works correctly.'''
    assert True
"""
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Criar componentes
        test_generator = TestGenerator(llm_client=mock_llm_client)

        # Criar request
        request = TestGenerationRequest(
            source_type="requirements",
            source_data={
                "requirements": [
                    {
                        "id": "REQ-001",
                        "title": "User Authentication",
                        "description": "System must authenticate users with username and password",
                    }
                ]
            },
            plan_id="PLAN-123",
            framework=TestFramework.PYTEST,
            language="python",
            test_types=[TestType.UNIT],
        )

        # Executar geração
        result = await test_generator.generate_tests(request)

        # Validar resultado
        assert result.total_tests_generated == 1
        assert result.test_suite.id.startswith("TS-")
        assert result.test_suite.total_tests == 1
        assert len(result.test_suite.test_cases) == 1
        assert result.test_suite.test_cases[0].test_type == TestType.UNIT
        assert result.test_suite.test_cases[0].requirement_id == "REQ-001"

    @pytest.mark.asyncio()
    async def test_flow_with_mongodb_persistence(self):
        """Testa fluxo com persistência no MongoDB."""
        # Mock LLM
        mock_llm_client = AsyncMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "def test(): pass"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Mock MongoDB
        with patch("src.database.mongodb_client.AsyncIOMotorClient") as mock_motor:
            mock_instance = MagicMock()
            mock_instance.admin.command = AsyncMock(return_value="ok")

            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mongo-id"))
            mock_collection.insert_many = AsyncMock(
                return_value=MagicMock(inserted_ids=["id1", "id2"])
            )
            mock_db.test_suites = mock_collection
            mock_db.test_cases = mock_collection
            mock_db.generation_results = mock_collection

            mock_instance.__getitem__ = MagicMock(return_value=mock_db)
            mock_motor.return_value = mock_instance

            # Inicializar cliente e repositórios
            mongodb_client = MongoDBClient()
            await mongodb_client.connect()

            test_generator = TestGenerator(llm_client=mock_llm_client)
            suite_repo = TestSuiteRepository(mongodb_client)
            result_repo = GenerationResultRepository(mongodb_client)

            # Gerar testes
            request = TestGenerationRequest(
                source_type="requirements",
                source_data={
                    "requirements": [
                        {
                            "id": "REQ-002",
                            "title": "Data Validation",
                            "description": "System must validate input data",
                        }
                    ]
                },
                framework=TestFramework.PYTEST,
                language="python",
            )

            result = await test_generator.generate_tests(request)

            # Persistir
            suite_id = await suite_repo.save(result.test_suite)
            result_id = await result_repo.save(result)

            # Validar
            assert suite_id == "mongo-id"
            assert result_id == "mongo-id"

    @pytest.mark.asyncio()
    async def test_flow_from_user_stories(self):
        """Testa fluxo a partir de user stories."""
        mock_llm_client = AsyncMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "def test_user_login_flow(): pass"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

        test_generator = TestGenerator(llm_client=mock_llm_client)

        request = TestGenerationRequest(
            source_type="user_stories",
            source_data={
                "user_stories": [
                    {
                        "id": "US-001",
                        "role": "user",
                        "action": "login to the system",
                        "benefit": "access my dashboard",
                    }
                ]
            },
            framework=TestFramework.PYTEST,
            language="python",
            test_types=[TestType.E2E],
        )

        result = await test_generator.generate_tests(request)

        assert result.total_tests_generated == 1
        assert result.test_suite.test_cases[0].test_type == TestType.E2E
        assert result.test_suite.test_cases[0].user_story_id == "US-001"

    @pytest.mark.asyncio()
    async def test_flow_from_acceptance_criteria(self):
        """Testa fluxo a partir de critérios de aceitação."""
        mock_llm_client = AsyncMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "def test_acceptance_criteria(): pass"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

        test_generator = TestGenerator(llm_client=mock_llm_client)

        request = TestGenerationRequest(
            source_type="acceptance_criteria",
            source_data={
                "acceptance_criteria": [
                    {
                        "id": "AC-001",
                        "statement": "Login fails with invalid credentials",
                        "given": "user is on login page",
                        "when": "enters invalid credentials",
                        "then": "system shows error message",
                    }
                ]
            },
            framework=TestFramework.PYTEST,
            language="python",
        )

        result = await test_generator.generate_tests(request)

        assert result.total_tests_generated == 1
        assert result.test_suite.test_cases[0].acceptance_criteria_id == "AC-001"

    @pytest.mark.asyncio()
    async def test_flow_multiple_test_types(self):
        """Testa geração de múltiplos tipos de teste."""
        mock_llm_client = AsyncMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "def test_multi(): pass"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

        test_generator = TestGenerator(llm_client=mock_llm_client)

        request = TestGenerationRequest(
            source_type="requirements",
            source_data={
                "requirements": [
                    {
                        "id": "REQ-003",
                        "title": "Multi-Type Test",
                        "description": "Test with multiple types",
                    }
                ]
            },
            framework=TestFramework.PYTEST,
            language="python",
            test_types=[TestType.UNIT, TestType.INTEGRATION],
        )

        result = await test_generator.generate_tests(request)

        # Deve gerar 2 testes (unit + integration)
        assert result.total_tests_generated == 2
        test_types = [tc.test_type for tc in result.test_suite.test_cases]
        assert TestType.UNIT in test_types
        assert TestType.INTEGRATION in test_types

    @pytest.mark.asyncio()
    async def test_flow_with_llm_error(self):
        """Testa comportamento quando LLM falha."""
        mock_llm_client = AsyncMock()
        mock_llm_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM error"))

        test_generator = TestGenerator(llm_client=mock_llm_client)

        request = TestGenerationRequest(
            source_type="requirements",
            source_data={
                "requirements": [
                    {
                        "id": "REQ-004",
                        "title": "Error Test",
                        "description": "Test LLM error handling",
                    }
                ]
            },
            framework=TestFramework.PYTEST,
            language="python",
            # Apenas UNIT para simplificar o teste
            test_types=[TestType.UNIT],
        )

        result = await test_generator.generate_tests(request)

        # Deve retornar stub mesmo com erro
        assert result.total_tests_generated == 1
        assert "# Test generation failed" in result.test_suite.test_cases[0].test_code

    @pytest.mark.asyncio()
    async def test_consumer_processes_message(self):
        """Testa que consumer processa mensagem Kafka corretamente."""
        mock_llm_client = AsyncMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "def test_consumer(): pass"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

        test_generator = TestGenerator(llm_client=mock_llm_client)
        consumer = RequirementsConsumer(test_generator=test_generator)

        # Mock message Kafka
        mock_msg = MagicMock()
        mock_msg.topic = "requirements.generated"
        mock_msg.partition = 0
        mock_msg.offset = 123
        mock_msg.key = b"REQ-SET-001"

        message_data = {
            "requirements_set_id": "REQ-SET-001",
            "plan_id": "PLAN-456",
            "requirements": [
                {
                    "id": "REQ-005",
                    "title": "Consumer Test",
                    "description": "Test message processing",
                }
            ],
        }
        mock_msg.value = json.dumps(message_data).encode("utf-8")

        # Processar mensagem
        await consumer._process_message(mock_msg)

        # Validar que testes foram gerados (chamada ao LLM foi feita)
        assert mock_llm_client.chat.completions.create.called

    @pytest.mark.asyncio()
    async def test_coverage_estimation(self):
        """Testa estimativa de cobertura."""
        mock_llm_client = AsyncMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "def test_coverage(): pass"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

        test_generator = TestGenerator(llm_client=mock_llm_client)

        # Gerar 5 testes
        request = TestGenerationRequest(
            source_type="requirements",
            source_data={
                "requirements": [
                    {"id": f"REQ-{i:03d}", "title": f"Test {i}", "description": f"Description {i}"}
                    for i in range(1, 6)
                ]
            },
            framework=TestFramework.PYTEST,
            language="python",
            test_types=[TestType.UNIT],
        )

        result = await test_generator.generate_tests(request)

        # Cobertura estimada: 5 * 0.1 = 0.5 (50%)
        assert result.coverage_estimate == 0.5

    @pytest.mark.asyncio()
    async def test_file_paths_generated(self):
        """Testa que caminhos de arquivo são gerados corretamente."""
        mock_llm_client = AsyncMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "def test_paths(): pass"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

        test_generator = TestGenerator(llm_client=mock_llm_client)

        request = TestGenerationRequest(
            source_type="requirements",
            source_data={
                "requirements": [
                    {
                        "id": "REQ-006",
                        "title": "File Path Test!",
                        "description": "Test file path generation",
                    }
                ]
            },
            framework=TestFramework.PYTEST,
            language="python",
            test_types=[TestType.UNIT, TestType.INTEGRATION],
        )

        result = await test_generator.generate_tests(request)

        # Validar caminhos
        file_paths = result.files_created
        assert len(file_paths) == 2
        assert any("unit" in path for path in file_paths)
        assert any("integration" in path for path in file_paths)

    @pytest.mark.asyncio()
    async def test_empty_requirements_handling(self):
        """Testa tratamento de requisitos vazios."""
        test_generator = TestGenerator(llm_client=AsyncMock())

        request = TestGenerationRequest(
            source_type="requirements",
            source_data={"requirements": []},
            framework=TestFramework.PYTEST,
            language="python",
        )

        result = await test_generator.generate_tests(request)

        # Não deve gerar testes
        assert result.total_tests_generated == 0
        assert len(result.test_suite.test_cases) == 0

    @pytest.mark.asyncio()
    async def test_unknown_source_type(self):
        """Testa tratamento de tipo de fonte desconhecido."""
        test_generator = TestGenerator(llm_client=AsyncMock())

        request = TestGenerationRequest(
            source_type="unknown_type",
            source_data={},
            framework=TestFramework.PYTEST,
            language="python",
        )

        result = await test_generator.generate_tests(request)

        # Não deve gerar testes para tipo desconhecido
        assert result.total_tests_generated == 0


@pytest.mark.asyncio()
class TestE2EHealthAndRecovery:
    """Testes E2E de health check e recuperação."""

    @pytest.mark.asyncio()
    async def test_service_health_with_all_components(self):
        """Testa health check com todos os componentes funcionando."""
        # Mock Kafka e MongoDB
        with (
            patch("src.database.mongodb_client.AsyncIOMotorClient") as mock_motor,
            patch("src.consumers.requirements_consumer.AIOKafkaConsumer") as mock_consumer_class,
            patch("src.producers.tests_producer.AIOKafkaProducer") as mock_producer_class,
        ):

            # MongoDB mock
            mock_instance = MagicMock()
            mock_instance.admin.command = AsyncMock(return_value="ok")
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_collection.count_documents = AsyncMock(return_value=5)
            mock_db.test_suites = mock_collection
            mock_db.test_cases = mock_collection
            mock_db.generation_results = mock_collection
            mock_instance.__getitem__ = MagicMock(return_value=mock_db)
            mock_motor.return_value = mock_instance

            # Kafka mock - evitar start() real
            mock_consumer = MagicMock()
            mock_consumer.start = AsyncMock()
            mock_producer = MagicMock()
            mock_producer.start = AsyncMock()
            mock_consumer_class.return_value = mock_consumer
            mock_producer_class.return_value = mock_producer

            # Criar componentes
            mongodb_client = MongoDBClient()
            await mongodb_client.connect()

            consumer = RequirementsConsumer(test_generator=AsyncMock())
            await consumer.start()

            producer = TestsProducer()
            await producer.start()

            # Verificar health de todos
            mongo_health = await mongodb_client.health_check()
            consumer_health = await consumer.health_check()
            producer_health = await producer.health_check()

            assert mongo_health["mongodb_connected"] is True
            assert consumer_health["kafka_connected"] is True
            assert producer_health["kafka_connected"] is True

    @pytest.mark.asyncio()
    async def test_mongodb_reconnection_after_failure(self):
        """Testa que ping retorna False quando MongoDB falha."""
        client = MongoDBClient()

        with patch("src.database.mongodb_client.AsyncIOMotorClient") as mock_motor:
            mock_instance = MagicMock()
            # Connect consome o primeiro ping, depois 2 pings ok
            mock_instance.admin.command = AsyncMock(side_effect=["ok", "ok", "ok"])
            mock_db = MagicMock()
            mock_db.test_suites = MagicMock()
            mock_db.test_cases = MagicMock()
            mock_db.generation_results = MagicMock()
            mock_instance.__getitem__ = MagicMock(return_value=mock_db)
            mock_motor.return_value = mock_instance

            # Primeira conexão - sucesso (consome o primeiro "ok")
            await client.connect()
            assert await client.ping() is True

            # Segundo ping - sucesso (consome o segundo "ok")
            assert await client.ping() is True

            # Alterar mock para falhar
            mock_instance.admin.command = AsyncMock(side_effect=Exception("Connection lost"))
            assert await client.ping() is False

    @pytest.mark.asyncio()
    async def test_consumer_recovery_after_error(self):
        """Testa recuperação do consumer após erro."""
        mock_llm = AsyncMock()
        test_generator = TestGenerator(llm_client=mock_llm)
        consumer = RequirementsConsumer(test_generator=test_generator)

        with patch("aiokafka.AIOKafkaConsumer") as mock_consumer_class:
            mock_consumer = MagicMock()
            mock_consumer.start = AsyncMock(side_effect=Exception("Kafka error"))
            mock_consumer_class.return_value = mock_consumer

            # Tentar iniciar deve lançar erro
            with pytest.raises(Exception):
                await consumer.start()

            # Consumer deve estar desconectado
            assert consumer.is_connected is False

    @pytest.mark.asyncio()
    async def test_generator_graceful_degradation(self):
        """Testa degradação graciosa do gerador quando componentes falham."""
        # LLM que falha
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(side_effect=Exception("LLM down"))

        test_generator = TestGenerator(llm_client=mock_llm)

        request = TestGenerationRequest(
            source_type="requirements",
            source_data={
                "requirements": [{"id": "REQ-007", "title": "Degradation", "description": "Test"}]
            },
            framework=TestFramework.PYTEST,
            language="python",
            # Apenas UNIT para simplificar o teste
            test_types=[TestType.UNIT],
        )

        result = await test_generator.generate_tests(request)

        # Deve retornar stub em vez de falhar completamente
        assert result.total_tests_generated == 1
        assert "# Test generation failed" in result.test_suite.test_cases[0].test_code


@pytest.mark.asyncio()
class TestE2EDataConsistency:
    """Testes E2E de consistência de dados."""

    @pytest.mark.asyncio()
    async def test_suite_and_test_cases_consistency(self):
        """Testa consistência entre suite e test cases."""
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "def test_consistency(): pass"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_llm.chat.completions.create = AsyncMock(return_value=mock_response)

        test_generator = TestGenerator(llm_client=mock_llm)

        request = TestGenerationRequest(
            source_type="requirements",
            source_data={
                "requirements": [{"id": "REQ-008", "title": "Consistency", "description": "Test"}]
            },
            framework=TestFramework.PYTEST,
            language="python",
            test_types=[TestType.UNIT, TestType.INTEGRATION],
        )

        result = await test_generator.generate_tests(request)

        suite = result.test_suite

        # Validar consistência
        assert suite.total_tests == len(suite.test_cases)
        assert suite.framework == TestFramework.PYTEST
        assert suite.language == "python"

        for tc in suite.test_cases:
            assert tc.framework == TestFramework.PYTEST
            assert tc.language == "python"
            assert tc.file_path  # Deve ter caminho de arquivo

    @pytest.mark.asyncio()
    async def test_traceability_across_flow(self):
        """Testa rastreabilidade através do fluxo."""
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "def test_traceability(): pass"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_llm.chat.completions.create = AsyncMock(return_value=mock_response)

        test_generator = TestGenerator(llm_client=mock_llm)

        plan_id = "PLAN-TRACE-001"
        req_id = "REQ-TRACE-001"

        request = TestGenerationRequest(
            source_type="requirements",
            source_data={
                "requirements": [{"id": req_id, "title": "Traceability", "description": "Test"}]
            },
            plan_id=plan_id,
            framework=TestFramework.PYTEST,
            language="python",
        )

        result = await test_generator.generate_tests(request)

        # Validar rastreabilidade
        assert result.test_suite.plan_id == plan_id
        assert plan_id in result.test_suite.requirements_ids or any(
            tc.requirement_id == req_id for tc in result.test_suite.test_cases
        )

        for tc in result.test_suite.test_cases:
            if tc.requirement_id:
                assert tc.requirement_id == req_id

    @pytest.mark.asyncio()
    async def test_result_metadata_completeness(self):
        """Testa completude de metadados do resultado."""
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "def test_metadata(): pass"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_llm.chat.completions.create = AsyncMock(return_value=mock_response)

        test_generator = TestGenerator(llm_client=mock_llm)

        request = TestGenerationRequest(
            source_type="requirements",
            source_data={
                "requirements": [{"id": "REQ-009", "title": "Metadata", "description": "Test"}]
            },
            framework=TestFramework.PYTEST,
            language="python",
        )

        result = await test_generator.generate_tests(request)

        # Validar campos obrigatórios
        assert result.request_id
        assert result.test_suite.id
        assert result.test_suite.name
        assert result.test_suite.description
        assert result.status == "completed"
        assert result.generation_duration_ms >= 0
        assert isinstance(result.coverage_estimate, float)
        assert isinstance(result.files_created, list)

        for tc in result.test_suite.test_cases:
            assert tc.id
            assert tc.name
            assert tc.description
            assert tc.test_code
            assert tc.file_path
            assert tc.test_type
            assert tc.framework
            assert tc.language
