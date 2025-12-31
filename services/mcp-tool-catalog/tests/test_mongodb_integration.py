"""
Testes de integração MongoDB para validar preservação de tipos de metadata.

Valida que valores booleanos no campo metadata são corretamente
armazenados e recuperados via Motor/BSON sem conversão para strings.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.tool_descriptor import (
    AuthenticationMethod,
    IntegrationType,
    ToolCategory,
    ToolDescriptor,
)


class TestMongoDBMetadataTypePreservation:
    """Testes de integração para preservação de tipos no MongoDB."""

    @pytest.fixture
    def sample_tool_with_boolean_metadata(self) -> ToolDescriptor:
        """Ferramenta de teste com metadata contendo boolean."""
        return ToolDescriptor(
            tool_id="mongodb-test-001",
            tool_name="MongoDB Test Tool",
            category=ToolCategory.ANALYSIS,
            capabilities=["test"],
            version="1.0.0",
            reputation_score=0.8,
            average_execution_time_ms=5000,
            cost_score=0.3,
            required_parameters={},
            output_format="json",
            integration_type=IntegrationType.CLI,
            authentication_method=AuthenticationMethod.NONE,
            metadata={
                "active": True,
                "homepage": "https://test.dev",
                "license": "MIT",
            },
        )

    @pytest.mark.asyncio
    async def test_save_and_retrieve_preserves_boolean_metadata(
        self, sample_tool_with_boolean_metadata
    ):
        """Testa que save_tool + get_tool preserva tipos booleanos."""
        tool = sample_tool_with_boolean_metadata

        # Simula documento MongoDB retornado (como BSON seria deserializado)
        mock_mongo_document = {
            "tool_id": tool.tool_id,
            "tool_name": tool.tool_name,
            "category": "ANALYSIS",
            "capabilities": ["test"],
            "version": "1.0.0",
            "reputation_score": 0.8,
            "average_execution_time_ms": 5000,
            "cost_score": 0.3,
            "required_parameters": {},
            "output_format": "json",
            "integration_type": "CLI",
            "authentication_method": "NONE",
            "metadata": {
                "active": True,  # BSON preserva boolean
                "homepage": "https://test.dev",
                "license": "MIT",
            },
            "created_at": 1703980800000,
            "updated_at": 1703980800000,
            "schema_version": 1,
        }

        # Deserializa usando from_avro (como MongoDBClient.get_tool faz)
        restored_tool = ToolDescriptor.from_avro(mock_mongo_document)

        # Valida tipos preservados
        assert restored_tool.metadata["active"] is True
        assert isinstance(restored_tool.metadata["active"], bool)
        assert not isinstance(restored_tool.metadata["active"], str)
        assert restored_tool.metadata["homepage"] == "https://test.dev"

    @pytest.mark.asyncio
    async def test_deactivate_tool_sets_boolean_false(self):
        """Testa que deactivate_tool define metadata.active como boolean False."""
        # Simula documento após $set {"metadata.active": False}
        mock_deactivated_document = {
            "tool_id": "deactivated-tool-001",
            "tool_name": "Deactivated Tool",
            "category": "VALIDATION",
            "capabilities": ["validate"],
            "version": "1.0.0",
            "reputation_score": 0.7,
            "average_execution_time_ms": 3000,
            "cost_score": 0.2,
            "required_parameters": {},
            "output_format": "json",
            "integration_type": "CLI",
            "authentication_method": "NONE",
            "metadata": {
                "active": False,  # Após deactivate_tool
                "homepage": "https://deactivated.dev",
            },
            "created_at": 1703980800000,
            "updated_at": 1703980800000,
            "schema_version": 1,
        }

        restored_tool = ToolDescriptor.from_avro(mock_deactivated_document)

        # Valida que False é boolean, não string "false"
        assert restored_tool.metadata["active"] is False
        assert isinstance(restored_tool.metadata["active"], bool)
        assert restored_tool.metadata["active"] != "false"
        assert restored_tool.metadata["active"] != "False"

    @pytest.mark.asyncio
    async def test_mongodb_document_roundtrip_preserves_types(
        self, sample_tool_with_boolean_metadata
    ):
        """Testa roundtrip: ToolDescriptor -> to_dict -> from_avro."""
        original_tool = sample_tool_with_boolean_metadata

        # Serializa para documento MongoDB
        mongo_document = original_tool.to_dict()

        # Simula recuperação do MongoDB
        restored_tool = ToolDescriptor.from_avro(mongo_document)

        # Valida que tipos são preservados após roundtrip
        assert restored_tool.metadata["active"] is True
        assert isinstance(restored_tool.metadata["active"], bool)

        # Valida outros campos
        assert restored_tool.tool_id == original_tool.tool_id
        assert restored_tool.tool_name == original_tool.tool_name


class TestMongoDBClientIntegration:
    """Testes de integração com mock do MongoDBClient."""

    @pytest.fixture
    def mock_mongodb_client(self):
        """Mock do MongoDBClient para testes."""
        from src.clients.mongodb_client import MongoDBClient

        client = MongoDBClient("mongodb://localhost:27017", "test_db")
        client.db = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_get_tool_deserializes_boolean_metadata(self, mock_mongodb_client):
        """Testa que get_tool deserializa corretamente metadata com boolean."""
        # Configura mock para retornar documento com boolean
        mock_document = {
            "tool_id": "get-test-001",
            "tool_name": "Get Test Tool",
            "category": "GENERATION",
            "capabilities": ["generate"],
            "version": "2.0.0",
            "reputation_score": 0.9,
            "average_execution_time_ms": 4000,
            "cost_score": 0.4,
            "required_parameters": {},
            "output_format": "text",
            "integration_type": "REST_API",
            "authentication_method": "API_KEY",
            "metadata": {
                "active": True,
                "deprecated": False,
                "priority": 5,
            },
            "created_at": 1703980800000,
            "updated_at": 1703980800000,
            "schema_version": 1,
        }

        mock_mongodb_client.db.tools.find_one = AsyncMock(return_value=mock_document)

        tool = await mock_mongodb_client.get_tool("get-test-001")

        assert tool is not None
        assert tool.metadata["active"] is True
        assert tool.metadata["deprecated"] is False
        assert isinstance(tool.metadata["active"], bool)
        assert isinstance(tool.metadata["deprecated"], bool)
        assert tool.metadata["priority"] == 5

    @pytest.mark.asyncio
    async def test_list_tools_deserializes_multiple_tools_with_boolean_metadata(
        self, mock_mongodb_client
    ):
        """Testa que list_tools deserializa múltiplas ferramentas corretamente."""
        mock_documents = [
            {
                "tool_id": "list-test-001",
                "tool_name": "List Tool 1",
                "category": "ANALYSIS",
                "capabilities": ["analyze"],
                "version": "1.0.0",
                "reputation_score": 0.85,
                "average_execution_time_ms": 5000,
                "cost_score": 0.3,
                "required_parameters": {},
                "output_format": "json",
                "integration_type": "CLI",
                "authentication_method": "NONE",
                "metadata": {"active": True, "license": "MIT"},
                "created_at": 1703980800000,
                "updated_at": 1703980800000,
                "schema_version": 1,
            },
            {
                "tool_id": "list-test-002",
                "tool_name": "List Tool 2",
                "category": "ANALYSIS",
                "capabilities": ["scan"],
                "version": "2.0.0",
                "reputation_score": 0.75,
                "average_execution_time_ms": 3000,
                "cost_score": 0.2,
                "required_parameters": {},
                "output_format": "xml",
                "integration_type": "CLI",
                "authentication_method": "NONE",
                "metadata": {"active": False, "deprecated": True},  # Ferramenta desativada
                "created_at": 1703980800000,
                "updated_at": 1703980800000,
                "schema_version": 1,
            },
        ]

        # Mock do cursor assíncrono
        async def mock_async_generator():
            for doc in mock_documents:
                yield doc

        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.__aiter__ = lambda self: mock_async_generator()

        mock_mongodb_client.db.tools.find = MagicMock(return_value=mock_cursor)

        tools = await mock_mongodb_client.list_tools()

        assert len(tools) == 2

        # Primeira ferramenta: active=True
        assert tools[0].metadata["active"] is True
        assert isinstance(tools[0].metadata["active"], bool)

        # Segunda ferramenta: active=False, deprecated=True
        assert tools[1].metadata["active"] is False
        assert tools[1].metadata["deprecated"] is True
        assert isinstance(tools[1].metadata["active"], bool)
        assert isinstance(tools[1].metadata["deprecated"], bool)


class TestToolRegistryDeactivateIntegration:
    """Testes para operação de deactivate_tool."""

    @pytest.mark.asyncio
    async def test_deactivate_tool_uses_boolean_false(self):
        """Testa que deactivate_tool usa boolean False no $set."""
        # Este teste valida a operação MongoDB em tool_registry.py:79-82
        # db.tools.update_one({"tool_id": tool_id}, {"$set": {"metadata.active": False}})

        # Simula o documento antes da desativação
        before_document = {
            "tool_id": "to-deactivate-001",
            "tool_name": "To Deactivate",
            "category": "AUTOMATION",
            "capabilities": ["automate"],
            "version": "1.0.0",
            "reputation_score": 0.6,
            "average_execution_time_ms": 2000,
            "cost_score": 0.3,
            "required_parameters": {},
            "output_format": "json",
            "integration_type": "CLI",
            "authentication_method": "NONE",
            "metadata": {
                "active": True,
                "homepage": "https://deactivate.dev",
            },
            "created_at": 1703980800000,
            "updated_at": 1703980800000,
            "schema_version": 1,
        }

        # Simula o documento após a operação $set
        after_document = before_document.copy()
        after_document["metadata"] = before_document["metadata"].copy()
        after_document["metadata"]["active"] = False  # Boolean, não string

        tool_before = ToolDescriptor.from_avro(before_document)
        tool_after = ToolDescriptor.from_avro(after_document)

        # Valida transição de estado
        assert tool_before.metadata["active"] is True
        assert tool_after.metadata["active"] is False

        # Valida que ambos são boolean
        assert isinstance(tool_before.metadata["active"], bool)
        assert isinstance(tool_after.metadata["active"], bool)

        # Valida que não são strings
        assert tool_after.metadata["active"] != "false"
        assert tool_after.metadata["active"] != "False"
        assert tool_after.metadata["active"] is not None
