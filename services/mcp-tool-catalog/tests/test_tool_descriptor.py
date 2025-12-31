"""
Unit tests for ToolDescriptor model with Dict[str, Any] metadata validation.

Validates that metadata field correctly accepts various value types (bool, int, str)
as required for MongoDB/BSON compatibility with Pydantic v2.
"""

import pytest
from datetime import datetime

from src.models.tool_descriptor import (
    AuthenticationMethod,
    IntegrationType,
    ToolCategory,
    ToolDescriptor,
)


class TestToolDescriptorMetadataTypes:
    """Test ToolDescriptor metadata field with different value types."""

    def _create_base_tool(self, metadata: dict) -> ToolDescriptor:
        """Create a ToolDescriptor with given metadata for testing."""
        return ToolDescriptor(
            tool_id="test-tool-001",
            tool_name="Test Tool",
            category=ToolCategory.ANALYSIS,
            capabilities=["test_capability"],
            version="1.0.0",
            reputation_score=0.8,
            average_execution_time_ms=5000,
            cost_score=0.3,
            required_parameters={"param1": "string"},
            output_format="json",
            integration_type=IntegrationType.CLI,
            authentication_method=AuthenticationMethod.NONE,
            metadata=metadata,
        )

    def test_metadata_with_boolean_values(self):
        """Test that metadata accepts boolean values (required for MongoDB BSON)."""
        metadata = {
            "active": True,
            "deprecated": False,
            "license": "MIT",
        }

        tool = self._create_base_tool(metadata)

        # Validate types are preserved
        assert tool.metadata["active"] is True
        assert tool.metadata["deprecated"] is False
        assert tool.metadata["license"] == "MIT"

        # Validate type is boolean, not string
        assert isinstance(tool.metadata["active"], bool)
        assert isinstance(tool.metadata["deprecated"], bool)
        assert not isinstance(tool.metadata["active"], str)

    def test_metadata_with_numeric_values(self):
        """Test that metadata accepts numeric values."""
        metadata = {
            "active": True,
            "priority": 5,
            "weight": 0.75,
            "retry_count": 3,
        }

        tool = self._create_base_tool(metadata)

        assert tool.metadata["priority"] == 5
        assert tool.metadata["weight"] == 0.75
        assert tool.metadata["retry_count"] == 3

        assert isinstance(tool.metadata["priority"], int)
        assert isinstance(tool.metadata["weight"], float)

    def test_metadata_with_mixed_types(self):
        """Test metadata with mixed value types (typical MongoDB document)."""
        metadata = {
            "active": True,
            "homepage": "https://example.com",
            "license": "Apache-2.0",
            "priority": 10,
            "experimental": False,
            "score": 0.95,
        }

        tool = self._create_base_tool(metadata)

        # All types preserved
        assert tool.metadata["active"] is True
        assert tool.metadata["homepage"] == "https://example.com"
        assert tool.metadata["license"] == "Apache-2.0"
        assert tool.metadata["priority"] == 10
        assert tool.metadata["experimental"] is False
        assert tool.metadata["score"] == 0.95

    def test_metadata_empty_dict(self):
        """Test that empty metadata dict is valid."""
        tool = self._create_base_tool({})

        assert tool.metadata == {}
        assert isinstance(tool.metadata, dict)

    def test_metadata_default_factory(self):
        """Test that metadata defaults to empty dict when not provided."""
        tool = ToolDescriptor(
            tool_id="test-tool-002",
            tool_name="Test Tool 2",
            category=ToolCategory.GENERATION,
            capabilities=["gen"],
            version="1.0.0",
            reputation_score=0.5,
            average_execution_time_ms=1000,
            cost_score=0.1,
            output_format="json",
            integration_type=IntegrationType.REST_API,
            authentication_method=AuthenticationMethod.API_KEY,
        )

        assert tool.metadata == {}


class TestToolDescriptorSerialization:
    """Test ToolDescriptor serialization with metadata containing various types."""

    def _create_tool_with_metadata(self) -> ToolDescriptor:
        """Create a ToolDescriptor with mixed metadata types."""
        return ToolDescriptor(
            tool_id="serialize-test-001",
            tool_name="Serialize Test Tool",
            category=ToolCategory.VALIDATION,
            capabilities=["validate"],
            version="2.0.0",
            reputation_score=0.9,
            average_execution_time_ms=10000,
            cost_score=0.2,
            required_parameters={},
            output_format="xml",
            integration_type=IntegrationType.LIBRARY,
            authentication_method=AuthenticationMethod.MTLS,
            metadata={
                "active": True,
                "homepage": "https://test.dev",
                "license": "MIT",
                "priority": 5,
            },
        )

    def test_to_dict_preserves_metadata_types(self):
        """Test that to_dict() preserves metadata value types."""
        tool = self._create_tool_with_metadata()
        data = tool.to_dict()

        # Metadata should be preserved with original types
        assert data["metadata"]["active"] is True
        assert data["metadata"]["homepage"] == "https://test.dev"
        assert data["metadata"]["priority"] == 5

        # Verify boolean type, not string
        assert isinstance(data["metadata"]["active"], bool)
        assert not isinstance(data["metadata"]["active"], str)

    def test_model_dump_preserves_metadata_types(self):
        """Test that Pydantic model_dump() preserves metadata types."""
        tool = self._create_tool_with_metadata()
        data = tool.model_dump()

        assert data["metadata"]["active"] is True
        assert isinstance(data["metadata"]["active"], bool)

    def test_to_dict_with_boolean_false(self):
        """Test serialization with boolean False value."""
        tool = ToolDescriptor(
            tool_id="bool-false-test",
            tool_name="Bool False Test",
            category=ToolCategory.AUTOMATION,
            capabilities=["auto"],
            version="1.0.0",
            reputation_score=0.7,
            average_execution_time_ms=2000,
            cost_score=0.4,
            output_format="json",
            integration_type=IntegrationType.CLI,
            authentication_method=AuthenticationMethod.NONE,
            metadata={"active": False, "enabled": False},
        )

        data = tool.to_dict()

        # False should be preserved as boolean False, not string "false"
        assert data["metadata"]["active"] is False
        assert data["metadata"]["enabled"] is False
        assert isinstance(data["metadata"]["active"], bool)


class TestToolDescriptorFromAvro:
    """Test ToolDescriptor.from_avro() with metadata containing various types."""

    def test_from_avro_with_boolean_metadata(self):
        """Test from_avro() correctly deserializes boolean metadata values."""
        # Simulate data as it would come from MongoDB/Avro
        avro_data = {
            "tool_id": "avro-test-001",
            "tool_name": "Avro Test Tool",
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
            "metadata": {
                "active": True,  # Boolean from MongoDB BSON
                "homepage": "https://avro-test.dev",
                "license": "MIT",
            },
            "created_at": 1703980800000,  # Epoch ms
            "updated_at": 1703980800000,
            "schema_version": 1,
        }

        tool = ToolDescriptor.from_avro(avro_data)

        # Validate metadata types preserved
        assert tool.metadata["active"] is True
        assert isinstance(tool.metadata["active"], bool)
        assert tool.metadata["homepage"] == "https://avro-test.dev"

    def test_from_avro_with_mixed_metadata_types(self):
        """Test from_avro() with mixed metadata types (typical MongoDB scenario)."""
        avro_data = {
            "tool_id": "avro-mixed-001",
            "tool_name": "Avro Mixed Test",
            "category": "GENERATION",
            "capabilities": ["generate"],
            "version": "2.0.0",
            "reputation_score": 0.9,
            "average_execution_time_ms": 3000,
            "cost_score": 0.5,
            "required_parameters": {"input": "string"},
            "output_format": "text",
            "integration_type": "REST_API",
            "endpoint_url": "https://api.test.com",
            "authentication_method": "API_KEY",
            "metadata": {
                "active": True,
                "deprecated": False,
                "priority": 10,
                "score": 0.95,
                "homepage": "https://mixed-test.dev",
            },
            "created_at": 1703980800000,
            "updated_at": 1703980800000,
            "schema_version": 1,
        }

        tool = ToolDescriptor.from_avro(avro_data)

        # All types should be preserved
        assert tool.metadata["active"] is True
        assert tool.metadata["deprecated"] is False
        assert tool.metadata["priority"] == 10
        assert tool.metadata["score"] == 0.95
        assert tool.metadata["homepage"] == "https://mixed-test.dev"

        # Verify actual types
        assert isinstance(tool.metadata["active"], bool)
        assert isinstance(tool.metadata["deprecated"], bool)
        assert isinstance(tool.metadata["priority"], int)
        assert isinstance(tool.metadata["score"], float)
        assert isinstance(tool.metadata["homepage"], str)

    def test_from_avro_with_false_active_metadata(self):
        """Test from_avro() correctly handles active=False (deactivated tool)."""
        avro_data = {
            "tool_id": "deactivated-001",
            "tool_name": "Deactivated Tool",
            "category": "VALIDATION",
            "capabilities": ["validate"],
            "version": "1.0.0",
            "reputation_score": 0.6,
            "average_execution_time_ms": 2000,
            "cost_score": 0.2,
            "required_parameters": {},
            "output_format": "json",
            "integration_type": "CLI",
            "authentication_method": "NONE",
            "metadata": {
                "active": False,  # Deactivated tool
                "deactivated_reason": "deprecated",
            },
            "created_at": 1703980800000,
            "updated_at": 1703980800000,
            "schema_version": 1,
        }

        tool = ToolDescriptor.from_avro(avro_data)

        # False should be preserved as boolean
        assert tool.metadata["active"] is False
        assert isinstance(tool.metadata["active"], bool)
        assert tool.metadata["deactivated_reason"] == "deprecated"


class TestToolDescriptorRoundTrip:
    """Test round-trip serialization/deserialization preserves metadata types."""

    def test_round_trip_preserves_boolean_metadata(self):
        """Test that to_dict() -> from_avro() preserves boolean metadata."""
        original = ToolDescriptor(
            tool_id="roundtrip-001",
            tool_name="Round Trip Test",
            category=ToolCategory.TRANSFORMATION,
            capabilities=["transform"],
            version="1.0.0",
            reputation_score=0.8,
            average_execution_time_ms=4000,
            cost_score=0.35,
            required_parameters={},
            output_format="json",
            integration_type=IntegrationType.CLI,
            authentication_method=AuthenticationMethod.NONE,
            metadata={
                "active": True,
                "experimental": False,
                "version_major": 1,
                "homepage": "https://roundtrip.dev",
            },
        )

        # Serialize
        data = original.to_dict()

        # Verify serialized data has correct types
        assert data["metadata"]["active"] is True
        assert data["metadata"]["experimental"] is False
        assert isinstance(data["metadata"]["active"], bool)

        # Deserialize
        restored = ToolDescriptor.from_avro(data)

        # Verify restored metadata has correct types
        assert restored.metadata["active"] is True
        assert restored.metadata["experimental"] is False
        assert restored.metadata["version_major"] == 1
        assert restored.metadata["homepage"] == "https://roundtrip.dev"

        # Verify types are preserved after round-trip
        assert isinstance(restored.metadata["active"], bool)
        assert isinstance(restored.metadata["experimental"], bool)
        assert isinstance(restored.metadata["version_major"], int)


class TestMongoDBDeserialization:
    """Test deserialization from MongoDB documents with boolean metadata."""

    def test_from_avro_preserves_metadata_boolean_from_mongodb_document(self):
        """
        Test that from_avro() correctly deserializes metadata with boolean
        fields from a MongoDB document.

        This test emulates a MongoDB document with:
        - created_at and updated_at in milliseconds (epoch format)
        - metadata containing a boolean field active: True

        Asserts that metadata["active"] remains a boolean and not a string.
        """
        mongodb_document = {
            "tool_id": "mongo-bool-test-001",
            "tool_name": "MongoDB Boolean Test Tool",
            "category": "ANALYSIS",
            "capabilities": ["analyze", "report"],
            "version": "1.0.0",
            "reputation_score": 0.85,
            "average_execution_time_ms": 5000,
            "cost_score": 0.3,
            "required_parameters": {"input_file": "string"},
            "output_format": "json",
            "integration_type": "CLI",
            "authentication_method": "NONE",
            "metadata": {
                "active": True,
                "homepage": "https://example.com",
                "license": "MIT",
            },
            "created_at": 1703980800000,  # Epoch milliseconds
            "updated_at": 1704067200000,  # Epoch milliseconds
            "schema_version": 1,
        }

        tool = ToolDescriptor.from_avro(mongodb_document)

        # Assert metadata["active"] is a boolean True, not a string
        assert tool.metadata["active"] is True
        assert isinstance(tool.metadata["active"], bool)
        assert not isinstance(tool.metadata["active"], str)


class TestToolDescriptorBootstrapScenario:
    """Test scenarios matching the bootstrap service behavior."""

    def test_bootstrap_adds_active_true_as_boolean(self):
        """Test that adding active=True to metadata stores it as boolean."""
        # Simulate bootstrap behavior: create tool, then add active flag
        tool = ToolDescriptor(
            tool_id="bootstrap-test-001",
            tool_name="Bootstrap Test Tool",
            category=ToolCategory.INTEGRATION,
            capabilities=["integrate"],
            version="1.0.0",
            reputation_score=0.75,
            average_execution_time_ms=3000,
            cost_score=0.4,
            required_parameters={},
            output_format="json",
            integration_type=IntegrationType.REST_API,
            endpoint_url="https://api.test.com",
            authentication_method=AuthenticationMethod.API_KEY,
            metadata={"homepage": "https://bootstrap.dev", "license": "MIT"},
        )

        # Simulate bootstrap adding active flag (as done in tool_catalog_bootstrap.py:40)
        if "active" not in tool.metadata:
            tool.metadata["active"] = True

        # Verify active is boolean True, not string "True"
        assert tool.metadata["active"] is True
        assert isinstance(tool.metadata["active"], bool)
        assert not isinstance(tool.metadata["active"], str)

        # Verify serialization preserves the type
        data = tool.to_dict()
        assert data["metadata"]["active"] is True
        assert isinstance(data["metadata"]["active"], bool)
