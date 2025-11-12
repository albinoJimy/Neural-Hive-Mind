"""
Testes unitários para validação de timestamp em EvaluatePlanResponse.

Valida o caminho crítico de criação de timestamp no servidor gRPC, garantindo
que as validações implementadas na v1.0.7 permaneçam funcionais.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone
import json
from google.protobuf.timestamp_pb2 import Timestamp

from neural_hive_specialists.grpc_server import SpecialistServicer
from neural_hive_specialists.proto_gen import specialist_pb2


@pytest.fixture
def servicer(mock_specialist):
    """Cria fixture servicer para testes do servidor gRPC."""
    return SpecialistServicer(mock_specialist)


@pytest.mark.unit
class TestBuildEvaluatePlanResponseTimestamp:
    """Testes para validação de timestamp em EvaluatePlanResponse."""

    def test_timestamp_created_successfully(self, servicer):
        """
        Valida que _build_evaluate_plan_response cria timestamp válido.

        Verifica:
        - timestamp.seconds > 0
        - 0 <= timestamp.nanos < 1_000_000_000
        - timestamp.ToDatetime() retorna datetime válido
        """
        # Arrange
        result = {
            "opinion_id": "test-opinion-123",
            "specialist_type": "business",
            "specialist_version": "1.0.9",
            "opinion": {
                "confidence_score": 0.85,
                "risk_score": 0.2,
                "recommendation": "approve",
                "reasoning_summary": "Test reasoning",
                "reasoning_factors": [],
                "explainability_token": "test-token",
                "mitigations": [],
                "metadata": {}
            }
        }
        processing_time_ms = 150

        # Act
        response = servicer._build_evaluate_plan_response(result, processing_time_ms)

        # Assert
        assert response is not None, "Response não deve ser None"
        assert hasattr(response, 'evaluated_at'), "Response deve ter campo evaluated_at"

        timestamp = response.evaluated_at
        assert isinstance(timestamp, Timestamp), "evaluated_at deve ser Timestamp"
        assert timestamp.seconds > 0, "Timestamp seconds deve ser positivo"
        assert 0 <= timestamp.nanos < 1_000_000_000, "Timestamp nanos deve estar no range [0, 1e9)"

        # Verificar conversão para datetime
        dt = timestamp.ToDatetime()
        assert isinstance(dt, datetime), "Conversão ToDatetime deve retornar datetime"
        assert dt.tzinfo is not None, "Datetime deve ter timezone"

    def test_timestamp_validation_catches_invalid_seconds(self, servicer, monkeypatch):
        """
        Simula falha na criação de timestamp com seconds <= 0.

        Verifica que ValueError é lançado com mensagem apropriada.
        """
        # Arrange
        result = {
            "opinion_id": "test-opinion-123",
            "specialist_type": "business",
            "specialist_version": "1.0.9",
            "opinion": {
                "confidence_score": 0.85,
                "risk_score": 0.2,
                "recommendation": "approve",
                "reasoning_summary": "Test reasoning",
                "reasoning_factors": [],
                "explainability_token": "test-token",
                "mitigations": [],
                "metadata": {}
            }
        }
        processing_time_ms = 150

        # Monkeypatch Timestamp.FromDatetime para criar timestamp inválido
        def mock_from_datetime(self, dt):
            self.seconds = -1  # Seconds inválido
            self.nanos = 0

        monkeypatch.setattr(Timestamp, 'FromDatetime', mock_from_datetime)

        # Act & Assert
        with pytest.raises(ValueError, match=r"Invalid timestamp seconds"):
            servicer._build_evaluate_plan_response(result, processing_time_ms)

    def test_timestamp_validation_catches_invalid_nanos(self, servicer, monkeypatch):
        """
        Simula falha com nanos < 0 ou nanos >= 1_000_000_000.

        Verifica que ValueError é lançado.
        """
        # Arrange
        result = {
            "opinion_id": "test-opinion-123",
            "specialist_type": "business",
            "specialist_version": "1.0.9",
            "opinion": {
                "confidence_score": 0.85,
                "risk_score": 0.2,
                "recommendation": "approve",
                "reasoning_summary": "Test reasoning",
                "reasoning_factors": [],
                "explainability_token": "test-token",
                "mitigations": [],
                "metadata": {}
            }
        }
        processing_time_ms = 150

        # Monkeypatch Timestamp.FromDatetime para criar timestamp com nanos inválidos
        def mock_from_datetime_invalid_nanos(self, dt):
            self.seconds = 1705320645
            self.nanos = 1_000_000_000  # Nanos >= 1e9 é inválido

        monkeypatch.setattr(Timestamp, 'FromDatetime', mock_from_datetime_invalid_nanos)

        # Act & Assert
        with pytest.raises(ValueError, match=r"Invalid timestamp nanos"):
            servicer._build_evaluate_plan_response(result, processing_time_ms)

    def test_timestamp_from_datetime_conversion(self, servicer):
        """
        Verifica que conversão datetime -> Timestamp preserva precisão.

        Cria datetime específico e valida que seconds e nanos correspondem.
        """
        # Arrange
        test_dt = datetime(2025, 1, 15, 10, 30, 45, 123456, tzinfo=timezone.utc)

        # Act
        timestamp = Timestamp()
        timestamp.FromDatetime(test_dt)

        # Assert
        assert timestamp.seconds > 0, "Seconds deve ser positivo"
        assert 0 <= timestamp.nanos < 1_000_000_000, "Nanos deve estar no range válido"

        # Verificar conversão reversa
        converted_dt = timestamp.ToDatetime()
        # Precisão de microsegundos pode ter pequenas diferenças
        time_diff = abs((converted_dt - test_dt).total_seconds())
        assert time_diff < 0.001, "Conversão deve preservar precisão dentro de 1ms"

    def test_evaluate_plan_includes_valid_timestamp(self, servicer, mock_specialist):
        """
        Testa fluxo completo de EvaluatePlan.

        Verifica que response contém evaluated_at válido no formato correto.
        """
        # Arrange
        cognitive_plan = {
            "plan_id": "plan-123",
            "intent_id": "intent-456",
            "tasks": []
        }

        request = specialist_pb2.EvaluatePlanRequest(
            plan_id="plan-123",
            intent_id="intent-456",
            correlation_id="corr-789",
            trace_id="trace-123",
            span_id="span-456",
            cognitive_plan=json.dumps(cognitive_plan).encode('utf-8')
        )
        context = MagicMock()
        context.invocation_metadata = MagicMock(return_value=[])

        # Configurar mock do specialist
        mock_specialist.evaluate_plan.return_value = {
            "opinion_id": "op-123",
            "specialist_type": "test",
            "specialist_version": "1.0.0",
            "opinion": {
                "confidence_score": 0.95,
                "risk_score": 0.1,
                "recommendation": "approve",
                "reasoning_summary": "Test reasoning",
                "reasoning_factors": [],
                "explainability_token": "token-123",
                "mitigations": [],
                "metadata": {}
            }
        }

        # Act
        response = servicer.EvaluatePlan(request, context)

        # Assert
        assert response is not None, "Response não deve ser None"
        assert hasattr(response, 'evaluated_at'), "Response deve ter campo evaluated_at"

        # Validar timestamp
        timestamp = response.evaluated_at
        assert isinstance(timestamp, Timestamp), "evaluated_at deve ser Timestamp"
        assert timestamp.seconds > 0, "Timestamp seconds deve ser positivo"
        assert 0 <= timestamp.nanos < 1_000_000_000, "Timestamp nanos deve estar no range válido"

        # Verificar que pode ser convertido para datetime
        dt = timestamp.ToDatetime()
        assert isinstance(dt, datetime), "Timestamp deve ser conversível para datetime"
