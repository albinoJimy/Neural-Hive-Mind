"""
Testes unitários para schemas Avro do ML Inference API.
"""
import json
import uuid
from datetime import datetime

import pytest

from src.models.schemas import (
    PredictRequest,
    PredictResponse,
    PredictOptions,
    BatchPredictRequest,
    BatchOptions,
    DecisionType,
)
from src.schemas.avro_schemas import (
    INFERENCE_REQUEST_AVRO_SCHEMA,
    INFERENCE_RESPONSE_AVRO_SCHEMA,
    BATCH_INFERENCE_REQUEST_AVRO_SCHEMA,
    BATCH_INFERENCE_RESPONSE_AVRO_SCHEMA,
    AvroSchemaRegistry,
    pydantic_to_avro,
    avro_to_pydantic,
    pydantic_response_to_avro,
    avro_to_pydantic_response,
    batch_pydantic_to_avro,
    batch_avro_to_pydantic_response,
    create_inference_request,
    create_inference_response,
    _datetime_to_millis,
    _millis_to_datetime,
)


class TestAvroSchemaDefinitions:
    """Testes para definições de schemas Avro."""

    def test_inference_request_schema_valid(self):
        """Verifica que schema de request é válido."""
        assert INFERENCE_REQUEST_AVRO_SCHEMA["type"] == "record"
        assert INFERENCE_REQUEST_AVRO_SCHEMA["name"] == "InferenceRequest"
        assert INFERENCE_REQUEST_AVRO_SCHEMA["namespace"] == "io.neuralhive.inference"
        assert "fields" in INFERENCE_REQUEST_AVRO_SCHEMA

        # Verificar campos obrigatórios
        field_names = [f["name"] for f in INFERENCE_REQUEST_AVRO_SCHEMA["fields"]]
        assert "request_id" in field_names
        assert "intent_text" in field_names
        assert "specialist_confidence" in field_names
        assert "options" in field_names

    def test_inference_response_schema_valid(self):
        """Verifica que schema de response é válido."""
        assert INFERENCE_RESPONSE_AVRO_SCHEMA["type"] == "record"
        assert INFERENCE_RESPONSE_AVRO_SCHEMA["name"] == "InferenceResponse"

        # Verificar campos obrigatórios
        field_names = [f["name"] for f in INFERENCE_RESPONSE_AVRO_SCHEMA["fields"]]
        assert "request_id" in field_names
        assert "decision" in field_names
        assert "confidence" in field_names
        assert "model_version" in field_names
        assert "inference_time_ms" in field_names

    def test_decision_enum_symbols(self):
        """Verifica enum de decisão tem valores corretos."""
        decision_field = next(
            f for f in INFERENCE_RESPONSE_AVRO_SCHEMA["fields"] if f["name"] == "decision"
        )
        enum_type = decision_field["type"]
        assert set(enum_type["symbols"]) == {"approve", "reject", "review_required"}

    def test_batch_request_schema_valid(self):
        """Verifica que schema de batch request é válido."""
        assert BATCH_INFERENCE_REQUEST_AVRO_SCHEMA["type"] == "record"
        assert BATCH_INFERENCE_REQUEST_AVRO_SCHEMA["name"] == "BatchInferenceRequest"

        field_names = [f["name"] for f in BATCH_INFERENCE_REQUEST_AVRO_SCHEMA["fields"]]
        assert "batch_id" in field_names
        assert "requests" in field_names
        assert "options" in field_names

    def test_batch_response_schema_valid(self):
        """Verifica que schema de batch response é válido."""
        assert BATCH_INFERENCE_RESPONSE_AVRO_SCHEMA["type"] == "record"
        assert BATCH_INFERENCE_RESPONSE_AVRO_SCHEMA["name"] == "BatchInferenceResponse"

        field_names = [f["name"] for f in BATCH_INFERENCE_RESPONSE_AVRO_SCHEMA["fields"]]
        assert "batch_id" in field_names
        assert "results" in field_names
        assert "total_processed" in field_names
        assert "successful" in field_names
        assert "failed" in field_names


class TestDatetimeConversion:
    """Testes para conversão datetime <-> millis."""

    def test_datetime_to_millis_none(self):
        """Testa conversão de None."""
        assert _datetime_to_millis(None) is None

    def test_datetime_to_millis_valid(self):
        """Testa conversão de datetime válido."""
        dt = datetime(2026, 4, 4, 12, 0, 0)
        millis = _datetime_to_millis(dt)
        assert millis is not None
        assert isinstance(millis, int)
        assert millis > 0

    def test_millis_to_datetime_none(self):
        """Testa conversão de None."""
        assert _millis_to_datetime(None) is None

    def test_millis_to_datetime_valid(self):
        """Testa conversão de millis válido."""
        millis = 1743782400000  # 2026-04-04 12:00:00 UTC aprox
        dt = _millis_to_datetime(millis)
        assert dt is not None
        assert isinstance(dt, datetime)


class TestPydanticToAvroConversion:
    """Testes para conversão Pydantic -> Avro."""

    def test_predict_request_to_avro_minimal(self):
        """Testa conversão de request mínimo."""
        request = PredictRequest(
            intent_text="Create new user",
            specialist_confidence=0.8,
        )

        avro_dict = pydantic_to_avro(request)

        assert avro_dict["intent_text"] == "Create new user"
        assert avro_dict["specialist_confidence"] == 0.8
        assert avro_dict["specialist_type"] is None
        assert "request_id" in avro_dict
        assert isinstance(avro_dict["request_id"], str)

    def test_predict_request_to_avro_with_options(self):
        """Testa conversão de request com opções."""
        request = PredictRequest(
            intent_text="Delete user",
            specialist_confidence=0.6,
            specialist_type="security",
            options=PredictOptions(
                return_probabilities=True,
                return_features=True,
                threshold=0.7,
            ),
        )

        avro_dict = pydantic_to_avro(request)

        assert avro_dict["specialist_type"] == "security"
        assert avro_dict["options"]["include_probabilities"] is True
        assert avro_dict["options"]["include_features"] is True
        assert avro_dict["options"]["threshold"] == 0.7

    def test_predict_request_to_avro_custom_id(self):
        """Testa conversão com request_id customizado."""
        request = PredictRequest(intent_text="Test")
        custom_id = "custom-request-123"

        avro_dict = pydantic_to_avro(request, request_id=custom_id)

        assert avro_dict["request_id"] == custom_id

    def test_predict_response_to_avro(self):
        """Testa conversão de response para Avro."""
        response = PredictResponse(
            decision=DecisionType.APPROVE,
            confidence=0.95,
            probabilities={"approve": 0.95, "reject": 0.05},
            model_version="v7",
            inference_time_ms=42.5,
        )

        avro_dict = pydantic_response_to_avro(response, "req-123")

        assert avro_dict["request_id"] == "req-123"
        assert avro_dict["decision"] == "approve"
        assert avro_dict["confidence"] == 0.95
        assert avro_dict["probabilities"]["approve"] == 0.95
        assert avro_dict["model_version"] == "v7"
        assert avro_dict["inference_time_ms"] == 42.5
        assert avro_dict["error"] is None

    def test_batch_request_to_avro(self):
        """Testa conversão de batch request para Avro."""
        batch_request = BatchPredictRequest(
            requests=[
                PredictRequest(intent_text="Request 1", specialist_confidence=0.7),
                PredictRequest(intent_text="Request 2", specialist_confidence=0.8),
            ],
            options=BatchOptions(parallel=True, max_workers=4),
        )

        avro_dict = batch_pydantic_to_avro(batch_request, batch_id="batch-456")

        assert avro_dict["batch_id"] == "batch-456"
        assert len(avro_dict["requests"]) == 2
        assert avro_dict["options"]["parallel"] is True
        assert avro_dict["options"]["max_workers"] == 4


class TestAvroToPydanticConversion:
    """Testes para conversão Avro -> Pydantic."""

    def test_avro_to_predict_request_minimal(self):
        """Testa conversão de Avro mínimo para Pydantic."""
        avro_dict = {
            "request_id": "req-123",
            "intent_text": "Test intent",
            "specialist_confidence": 0.75,
            "specialist_type": None,
            "model_version": "latest",
            "options": None,
        }

        request = avro_to_pydantic(avro_dict)

        assert request.intent_text == "Test intent"
        assert request.specialist_confidence == 0.75
        assert request.specialist_type is None
        assert request.options is None

    def test_avro_to_predict_request_with_options(self):
        """Testa conversão com opções."""
        avro_dict = {
            "request_id": "req-123",
            "intent_text": "Test",
            "specialist_confidence": 0.7,
            "specialist_type": "business",
            "model_version": "v7",
            "options": {
                "explain": False,
                "include_probabilities": True,
                "include_features": True,
                "threshold": 0.8,
            },
        }

        request = avro_to_pydantic(avro_dict)

        assert request.specialist_type == "business"
        assert request.options.return_probabilities is True
        assert request.options.return_features is True
        assert request.options.threshold == 0.8

    def test_avro_to_predict_response(self):
        """Testa conversão de response Avro para Pydantic."""
        avro_dict = {
            "request_id": "req-123",
            "decision": "reject",
            "confidence": 0.3,
            "probabilities": {"approve": 0.3, "reject": 0.7},
            "features": None,
            "model_version": "v7",
            "inference_time_ms": 25.0,
            "timestamp": None,
            "error": None,
        }

        response = avro_to_pydantic_response(avro_dict)

        assert response.decision == DecisionType.REJECT
        assert response.confidence == 0.3
        assert response.probabilities["reject"] == 0.7
        assert response.model_version == "v7"
        assert response.inference_time_ms == 25.0

    def test_avro_to_batch_response(self):
        """Testa conversão de batch response Avro para Pydantic."""
        avro_dict = {
            "batch_id": "batch-789",
            "results": [
                {
                    "request_id": "req-1",
                    "decision": "approve",
                    "confidence": 0.9,
                    "probabilities": None,
                    "features": None,
                    "model_version": "v7",
                    "inference_time_ms": 20.0,
                    "timestamp": None,
                    "error": None,
                },
                {
                    "request_id": "req-2",
                    "decision": "reject",
                    "confidence": 0.4,
                    "probabilities": None,
                    "features": None,
                    "model_version": "v7",
                    "inference_time_ms": 15.0,
                    "timestamp": None,
                    "error": None,
                },
            ],
            "total_processed": 2,
            "successful": 2,
            "failed": 0,
            "aggregate_stats": {"avg_confidence": 0.65},
            "total_inference_time_ms": 35.0,
            "timestamp": None,
        }

        response = batch_avro_to_pydantic_response(avro_dict)

        assert len(response.results) == 2
        assert response.total_processed == 2
        assert response.successful == 2
        assert response.failed == 0
        assert response.aggregate_stats["avg_confidence"] == 0.65
        assert response.total_inference_time_ms == 35.0


class TestAvroSchemaRegistry:
    """Testes para AvroSchemaRegistry."""

    def test_registry_initialization(self):
        """Testa inicialização do registry."""
        registry = AvroSchemaRegistry()

        assert "inference_request" in registry.schemas
        assert "inference_response" in registry.schemas
        assert "batch_request" in registry.schemas
        assert "batch_response" in registry.schemas

    def test_get_schema(self):
        """Testa obter schema por nome."""
        registry = AvroSchemaRegistry()

        schema = registry.get_schema("inference_request")
        assert schema["name"] == "InferenceRequest"

    def test_get_schema_invalid_name(self):
        """Testa obter schema com nome inválido."""
        registry = AvroSchemaRegistry()

        with pytest.raises(ValueError, match="not found"):
            registry.get_schema("invalid_schema")

    def test_json_fallback_serialize(self):
        """Testa fallback JSON quando Avro não disponível."""
        registry = AvroSchemaRegistry()

        data = {"test": "value", "number": 123}

        # Deve funcionar mesmo se Avro não disponível
        serialized = registry.serialize(data, "inference_request")

        assert isinstance(serialized, bytes)
        # Se Avro não disponível, retorna JSON
        decoded = json.loads(serialized.decode("utf-8"))
        assert decoded["test"] == "value"

    def test_json_fallback_deserialize(self):
        """Testa desserialização JSON."""
        registry = AvroSchemaRegistry()

        data = {"test": "value"}
        serialized = json.dumps(data).encode("utf-8")

        deserialized = registry.deserialize(serialized, "inference_request")

        assert deserialized["test"] == "value"


class TestHelperFunctions:
    """Testes para funções helper."""

    def test_create_inference_request(self):
        """Testa criação de request Avro."""
        request = create_inference_request(
            intent_text="Test intent",
            specialist_confidence=0.85,
            specialist_type="technical",
            include_probabilities=True,
        )

        assert request["intent_text"] == "Test intent"
        assert request["specialist_confidence"] == 0.85
        assert request["specialist_type"] == "technical"
        assert request["options"]["include_probabilities"] is True
        assert "request_id" in request

    def test_create_inference_request_with_custom_id(self):
        """Testa criação com ID customizado."""
        custom_id = "my-custom-id"
        request = create_inference_request(
            intent_text="Test",
            request_id=custom_id,
        )

        assert request["request_id"] == custom_id

    def test_create_inference_response(self):
        """Testa criação de response Avro."""
        response = create_inference_response(
            request_id="req-123",
            decision="approve",
            confidence=0.92,
            model_version="v8",
            inference_time_ms=30.5,
            probabilities={"approve": 0.92, "reject": 0.08},
        )

        assert response["request_id"] == "req-123"
        assert response["decision"] == "approve"
        assert response["confidence"] == 0.92
        assert response["model_version"] == "v8"
        assert response["inference_time_ms"] == 30.5
        assert response["error"] is None

    def test_create_inference_response_with_error(self):
        """Testa criação de response com erro."""
        response = create_inference_response(
            request_id="req-123",
            decision="review_required",
            confidence=0.5,
            model_version="v8",
            inference_time_ms=0.0,
            error="Model not loaded",
        )

        assert response["error"] == "Model not loaded"

    def test_get_schema_registry_singleton(self):
        """Testa singleton do registry."""
        from src.schemas.avro_schemas import get_schema_registry

        registry1 = get_schema_registry()
        registry2 = get_schema_registry()

        assert registry1 is registry2


class TestRoundTripConversion:
    """Testes de conversão ida e volta."""

    def test_predict_request_round_trip(self):
        """Testa conversão Pydantic -> Avro -> Pydantic."""
        original = PredictRequest(
            intent_text="Complex intent with many details",
            specialist_confidence=0.77,
            specialist_type="architecture",
            options=PredictOptions(
                return_probabilities=True,
                return_features=False,
                threshold=0.8,
            ),
        )

        # Pydantic -> Avro
        avro_dict = pydantic_to_avro(original)

        # Avro -> Pydantic
        restored = avro_to_pydantic(avro_dict)

        assert restored.intent_text == original.intent_text
        assert restored.specialist_confidence == original.specialist_confidence
        assert restored.specialist_type == original.specialist_type
        assert restored.options.return_probabilities == original.options.return_probabilities
        assert restored.options.return_features == original.options.return_features
        assert restored.options.threshold == original.options.threshold

    def test_predict_response_round_trip(self):
        """Testa conversão response ida e volta."""
        original = PredictResponse(
            decision=DecisionType.APPROVE,
            confidence=0.88,
            probabilities={"approve": 0.88, "reject": 0.12},
            model_version="v7.1",
            inference_time_ms=45.2,
        )

        # Pydantic -> Avro
        avro_dict = pydantic_response_to_avro(original, "req-xyz")

        # Avro -> Pydantic
        restored = avro_to_pydantic_response(avro_dict)

        assert restored.decision == original.decision
        assert restored.confidence == original.confidence
        assert restored.probabilities["approve"] == original.probabilities["approve"]
        assert restored.model_version == original.model_version
        assert restored.inference_time_ms == original.inference_time_ms
