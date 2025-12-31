"""
Testes E2E para validar preservação de tipos de metadata no fluxo completo.

Testa o ciclo: Criação -> Serialização -> Deserialização -> API Response
garantindo que valores booleanos são preservados em todas as camadas.
"""

import pytest

from src.models.tool_descriptor import (
    AuthenticationMethod,
    IntegrationType,
    ToolCategory,
    ToolDescriptor,
)


class TestBootstrapMetadataTypesE2E:
    """Testes E2E do fluxo de bootstrap."""

    def test_tool_with_active_as_boolean(self):
        """Valida que ferramenta criada com active=True mantém tipo boolean."""
        tool = ToolDescriptor(
            tool_id="bootstrap-test-001",
            tool_name="Bootstrap Test Tool",
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
            metadata={"homepage": "https://test.dev", "license": "MIT"},
        )

        # Simula o que bootstrap faz (linha 40 de tool_catalog_bootstrap.py)
        if "active" not in tool.metadata:
            tool.metadata["active"] = True

        # Valida que active é boolean, não string
        assert tool.metadata["active"] is True
        assert isinstance(tool.metadata["active"], bool)
        assert not isinstance(tool.metadata["active"], str)

    def test_bootstrap_preserves_existing_metadata(self):
        """Valida que adicionar active preserva metadata existente."""
        tool = ToolDescriptor(
            tool_id="sonarqube-001",
            tool_name="SonarQube",
            category=ToolCategory.ANALYSIS,
            capabilities=["code_quality"],
            version="10.3.0",
            reputation_score=0.85,
            average_execution_time_ms=30000,
            cost_score=0.6,
            required_parameters={"project_key": "string"},
            output_format="json",
            integration_type=IntegrationType.REST_API,
            endpoint_url="http://sonarqube:9000/api",
            authentication_method=AuthenticationMethod.API_KEY,
            metadata={"homepage": "https://sonarqube.org", "license": "LGPL-3.0"},
        )

        # Adiciona active
        tool.metadata["active"] = True

        # Valida todos os campos preservados
        assert tool.metadata["homepage"] == "https://sonarqube.org"
        assert tool.metadata["license"] == "LGPL-3.0"
        assert tool.metadata["active"] is True

        # Valida tipos
        assert isinstance(tool.metadata["homepage"], str)
        assert isinstance(tool.metadata["license"], str)
        assert isinstance(tool.metadata["active"], bool)


class TestAPIResponseMetadataTypesE2E:
    """Testes E2E para responses da API."""

    def test_tool_serialization_for_api_response(self):
        """Valida que serialização para API preserva tipos."""
        tool = ToolDescriptor(
            tool_id="api-test-001",
            tool_name="API Test Tool",
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
                "homepage": "https://api-test.dev",
            },
        )

        # Simula serialização para JSON (como FastAPI faria)
        # Usa model_dump() que é o método Pydantic v2
        json_data = tool.model_dump(mode="json")

        # Valida que active é boolean no JSON
        assert json_data["metadata"]["active"] is True
        assert isinstance(json_data["metadata"]["active"], bool)

    def test_multiple_tools_api_response(self):
        """Valida response com múltiplas ferramentas."""
        tools = [
            ToolDescriptor(
                tool_id="multi-test-001",
                tool_name="Multi Tool 1",
                category=ToolCategory.ANALYSIS,
                capabilities=["analyze"],
                version="1.0.0",
                reputation_score=0.85,
                average_execution_time_ms=3000,
                cost_score=0.2,
                required_parameters={},
                output_format="json",
                integration_type=IntegrationType.CLI,
                authentication_method=AuthenticationMethod.NONE,
                metadata={"active": True},
            ),
            ToolDescriptor(
                tool_id="multi-test-002",
                tool_name="Multi Tool 2",
                category=ToolCategory.GENERATION,
                capabilities=["generate"],
                version="2.0.0",
                reputation_score=0.75,
                average_execution_time_ms=4000,
                cost_score=0.3,
                required_parameters={},
                output_format="text",
                integration_type=IntegrationType.REST_API,
                authentication_method=AuthenticationMethod.API_KEY,
                metadata={"active": False, "deprecated": True},
            ),
        ]

        # Serializa todas as ferramentas
        json_tools = [t.model_dump(mode="json") for t in tools]

        # Valida tipos em todas as ferramentas
        assert json_tools[0]["metadata"]["active"] is True
        assert json_tools[1]["metadata"]["active"] is False
        assert json_tools[1]["metadata"]["deprecated"] is True

        # Valida que são boolean, não string
        for json_tool in json_tools:
            assert isinstance(json_tool["metadata"]["active"], bool)


class TestDeactivateToolFlowE2E:
    """Testes E2E do fluxo de desativação."""

    def test_tool_deactivation_flow(self):
        """Simula fluxo completo de desativação de ferramenta."""
        # Estado inicial: ferramenta ativa
        initial_tool = ToolDescriptor(
            tool_id="deactivate-flow-001",
            tool_name="Deactivate Flow Test",
            category=ToolCategory.VALIDATION,
            capabilities=["validate"],
            version="1.0.0",
            reputation_score=0.7,
            average_execution_time_ms=2000,
            cost_score=0.2,
            required_parameters={},
            output_format="json",
            integration_type=IntegrationType.CLI,
            authentication_method=AuthenticationMethod.NONE,
            metadata={"active": True, "homepage": "https://test.dev"},
        )

        # Simula operação $set que tool_registry.deactivate_tool faz
        # MongoDB: db.tools.update_one({"tool_id": ...}, {"$set": {"metadata.active": False}})
        mongo_document = initial_tool.to_dict()
        mongo_document["metadata"]["active"] = False

        # Simula recuperação do MongoDB após update
        restored_tool = ToolDescriptor.from_avro(mongo_document)

        # Valida estado final
        assert restored_tool.metadata["active"] is False
        assert isinstance(restored_tool.metadata["active"], bool)
        assert restored_tool.metadata["homepage"] == "https://test.dev"

        # Valida serialização para API
        api_response = restored_tool.model_dump(mode="json")
        assert api_response["metadata"]["active"] is False
        assert isinstance(api_response["metadata"]["active"], bool)


class TestFullCycleE2E:
    """Testes do ciclo completo: criação -> persistência -> recuperação -> API."""

    def test_full_tool_lifecycle_preserves_metadata_types(self):
        """Testa ciclo completo de vida da ferramenta."""
        # 1. Criação da ferramenta (como no bootstrap)
        tool = ToolDescriptor(
            tool_id="lifecycle-001",
            tool_name="Lifecycle Test Tool",
            category=ToolCategory.INTEGRATION,
            capabilities=["integrate"],
            version="1.0.0",
            reputation_score=0.9,
            average_execution_time_ms=5000,
            cost_score=0.4,
            required_parameters={"api_key": "string"},
            output_format="json",
            integration_type=IntegrationType.REST_API,
            endpoint_url="https://api.lifecycle.dev",
            authentication_method=AuthenticationMethod.API_KEY,
            metadata={"homepage": "https://lifecycle.dev", "license": "MIT"},
        )

        # Bootstrap adiciona active=True
        tool.metadata["active"] = True

        # 2. Serialização para MongoDB
        mongo_doc = tool.to_dict()

        # Valida documento MongoDB
        assert mongo_doc["metadata"]["active"] is True
        assert isinstance(mongo_doc["metadata"]["active"], bool)

        # 3. Simula recuperação do MongoDB (from_avro)
        restored_tool = ToolDescriptor.from_avro(mongo_doc)

        # Valida objeto restaurado
        assert restored_tool.metadata["active"] is True
        assert isinstance(restored_tool.metadata["active"], bool)

        # 4. Serialização para API (JSON response)
        api_response = restored_tool.model_dump(mode="json")

        # Valida response JSON
        assert api_response["metadata"]["active"] is True
        assert isinstance(api_response["metadata"]["active"], bool)
        assert api_response["metadata"]["homepage"] == "https://lifecycle.dev"
        assert api_response["metadata"]["license"] == "MIT"

    def test_tool_update_metadata_preserves_types(self):
        """Testa atualização de metadata preserva tipos."""
        # Ferramenta original
        original = ToolDescriptor(
            tool_id="update-meta-001",
            tool_name="Update Meta Test",
            category=ToolCategory.AUTOMATION,
            capabilities=["automate"],
            version="1.0.0",
            reputation_score=0.8,
            average_execution_time_ms=3000,
            cost_score=0.3,
            required_parameters={},
            output_format="json",
            integration_type=IntegrationType.CLI,
            authentication_method=AuthenticationMethod.NONE,
            metadata={"active": True, "priority": 5},
        )

        # Simula atualização de metadata
        mongo_doc = original.to_dict()
        mongo_doc["metadata"]["experimental"] = True
        mongo_doc["metadata"]["priority"] = 10

        # Restaura
        updated = ToolDescriptor.from_avro(mongo_doc)

        # Valida todos os tipos
        assert updated.metadata["active"] is True
        assert updated.metadata["experimental"] is True
        assert updated.metadata["priority"] == 10

        assert isinstance(updated.metadata["active"], bool)
        assert isinstance(updated.metadata["experimental"], bool)
        assert isinstance(updated.metadata["priority"], int)


class TestEdgeCasesE2E:
    """Testes de casos extremos."""

    def test_empty_metadata_then_add_active(self):
        """Testa adicionar active a metadata vazia."""
        tool = ToolDescriptor(
            tool_id="empty-meta-001",
            tool_name="Empty Meta Test",
            category=ToolCategory.TRANSFORMATION,
            capabilities=["transform"],
            version="1.0.0",
            reputation_score=0.7,
            average_execution_time_ms=2000,
            cost_score=0.2,
            required_parameters={},
            output_format="text",
            integration_type=IntegrationType.CLI,
            authentication_method=AuthenticationMethod.NONE,
            metadata={},  # Metadata vazia
        )

        # Adiciona active (como bootstrap faz)
        tool.metadata["active"] = True

        # Serializa e deserializa
        mongo_doc = tool.to_dict()
        restored = ToolDescriptor.from_avro(mongo_doc)

        assert restored.metadata["active"] is True
        assert isinstance(restored.metadata["active"], bool)

    def test_metadata_with_none_values(self):
        """Testa metadata com valores None."""
        tool = ToolDescriptor(
            tool_id="none-meta-001",
            tool_name="None Meta Test",
            category=ToolCategory.VALIDATION,
            capabilities=["validate"],
            version="1.0.0",
            reputation_score=0.6,
            average_execution_time_ms=1000,
            cost_score=0.1,
            required_parameters={},
            output_format="json",
            integration_type=IntegrationType.CLI,
            authentication_method=AuthenticationMethod.NONE,
            metadata={
                "active": True,
                "optional_field": None,
                "license": "MIT",
            },
        )

        mongo_doc = tool.to_dict()
        restored = ToolDescriptor.from_avro(mongo_doc)

        assert restored.metadata["active"] is True
        assert restored.metadata["optional_field"] is None
        assert isinstance(restored.metadata["active"], bool)

    def test_metadata_with_nested_dict(self):
        """Testa metadata com dict aninhado (Dict[str, Any] suporta)."""
        tool = ToolDescriptor(
            tool_id="nested-meta-001",
            tool_name="Nested Meta Test",
            category=ToolCategory.ANALYSIS,
            capabilities=["analyze"],
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
                "config": {"enabled": True, "max_retries": 3},
            },
        )

        mongo_doc = tool.to_dict()
        restored = ToolDescriptor.from_avro(mongo_doc)

        assert restored.metadata["active"] is True
        assert restored.metadata["config"]["enabled"] is True
        assert restored.metadata["config"]["max_retries"] == 3
