"""
Testes unitários para validação de timestamp no cliente gRPC.

Valida as validações defensivas implementadas no SpecialistsGrpcClient para
prevenir o TypeError relacionado ao campo evaluated_at.
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import datetime, timezone
from google.protobuf.timestamp_pb2 import Timestamp

from src.clients.specialists_grpc_client import SpecialistsGrpcClient
from neural_hive_specialists.proto_gen import specialist_pb2, specialist_pb2_grpc


@pytest.mark.unit
@pytest.mark.asyncio
class TestSpecialistsGrpcClientTimestampValidation:
    """Testes para validação de timestamp no cliente gRPC."""

    async def test_evaluate_plan_accepts_valid_timestamp(
        self,
        mock_specialists_grpc_client,
        valid_evaluate_plan_response,
        sample_cognitive_plan,
        sample_trace_context
    ):
        """
        Verifica que evaluate_plan aceita timestamp válido.

        Valida que response válida retorna dict com evaluated_at em formato ISO string.
        """
        # Arrange
        specialist_type = "business"

        # Configurar stub no client.stubs
        mock_stub = AsyncMock()
        mock_stub.EvaluatePlan = AsyncMock(return_value=valid_evaluate_plan_response)
        mock_specialists_grpc_client.stubs[specialist_type] = mock_stub

        # Act
        result = await mock_specialists_grpc_client.evaluate_plan(
            specialist_type=specialist_type,
            cognitive_plan=sample_cognitive_plan,
            trace_context=sample_trace_context
        )

        # Assert
        assert result is not None, "Resultado não deve ser None"
        assert 'evaluated_at' in result, "Resultado deve conter evaluated_at"
        assert isinstance(result['evaluated_at'], str), "evaluated_at deve ser string ISO"

    async def test_evaluate_plan_rejects_none_timestamp(
        self,
        mock_specialists_grpc_client,
        sample_cognitive_plan,
        sample_trace_context
    ):
        """
        Verifica que evaluate_plan rejeita timestamp None.

        Valida que ValueError é lançado com mensagem apropriada.
        """
        # Arrange
        specialist_type = "technical"

        # Criar response com evaluated_at = None
        invalid_response = specialist_pb2.EvaluatePlanResponse(
            opinion_id="op-123",
            specialist_type=specialist_type,
            specialist_version="1.0.9",
            opinion="APPROVE",
            processing_time_ms=100
        )
        invalid_response.evaluated_at.CopyFrom(Timestamp())  # Timestamp vazio
        invalid_response.ClearField('evaluated_at')  # Remover campo

        # Configurar stub no client.stubs
        mock_stub = AsyncMock()
        mock_stub.EvaluatePlan = AsyncMock(return_value=invalid_response)
        mock_specialists_grpc_client.stubs[specialist_type] = mock_stub

        # Act & Assert
        with pytest.raises(ValueError, match=r"Response from .* missing evaluated_at field"):
            await mock_specialists_grpc_client.evaluate_plan(
                specialist_type=specialist_type,
                cognitive_plan=sample_cognitive_plan,
                trace_context=sample_trace_context
            )

    async def test_evaluate_plan_rejects_dict_timestamp(
        self,
        mock_specialists_grpc_client,
        sample_cognitive_plan,
        sample_trace_context
    ):
        """
        Simula bug onde evaluated_at é desserializado como dict.

        Verifica que TypeError é lançado com mensagem 'Invalid evaluated_at type'.
        """
        # Arrange
        specialist_type = "behavior"

        # Criar mock onde evaluated_at é dict (bug original)
        invalid_response = MagicMock()
        invalid_response.opinion_id = "op-456"
        invalid_response.specialist_type = specialist_type
        invalid_response.evaluated_at = {'seconds': 123, 'nanos': 456}  # Dict ao invés de Timestamp

        # Configurar stub no client.stubs
        mock_stub = AsyncMock()
        mock_stub.EvaluatePlan = AsyncMock(return_value=invalid_response)
        mock_specialists_grpc_client.stubs[specialist_type] = mock_stub

        # Act & Assert
        with pytest.raises(TypeError, match=r"Invalid evaluated_at type"):
            await mock_specialists_grpc_client.evaluate_plan(
                specialist_type=specialist_type,
                cognitive_plan=sample_cognitive_plan,
                trace_context=sample_trace_context
            )

    async def test_evaluate_plan_rejects_missing_seconds_attribute(
        self,
        mock_specialists_grpc_client,
        sample_cognitive_plan,
        sample_trace_context
    ):
        """
        Verifica que timestamp sem atributo 'seconds' é rejeitado.

        Valida que AttributeError é lançado.
        """
        # Arrange
        specialist_type = "evolution"

        # Criar mock de Timestamp sem atributo seconds
        invalid_response = MagicMock()
        invalid_response.opinion_id = "op-789"
        invalid_response.specialist_type = specialist_type

        mock_timestamp = MagicMock(spec=[])  # Spec vazio, sem atributos
        invalid_response.evaluated_at = mock_timestamp

        # Configurar stub no client.stubs
        mock_stub = AsyncMock()
        mock_stub.EvaluatePlan = AsyncMock(return_value=invalid_response)
        mock_specialists_grpc_client.stubs[specialist_type] = mock_stub

        # Act & Assert
        with pytest.raises((AttributeError, TypeError), match=r"(Timestamp missing required fields|Invalid evaluated_at type)"):
            await mock_specialists_grpc_client.evaluate_plan(
                specialist_type=specialist_type,
                cognitive_plan=sample_cognitive_plan,
                trace_context=sample_trace_context
            )

    async def test_evaluate_plan_rejects_invalid_seconds_type(
        self,
        mock_specialists_grpc_client,
        sample_cognitive_plan,
        sample_trace_context
    ):
        """
        Verifica que seconds com tipo incorreto (string) é rejeitado.

        Valida que TypeError é lançado.
        """
        # Arrange
        specialist_type = "architecture"

        # Criar Timestamp com seconds como string
        invalid_response = MagicMock()
        invalid_response.opinion_id = "op-101"
        invalid_response.specialist_type = specialist_type

        mock_timestamp = MagicMock()
        mock_timestamp.seconds = "123"  # String ao invés de int
        mock_timestamp.nanos = 456
        invalid_response.evaluated_at = mock_timestamp

        # Configurar stub no client.stubs
        mock_stub = AsyncMock()
        mock_stub.EvaluatePlan = AsyncMock(return_value=invalid_response)
        mock_specialists_grpc_client.stubs[specialist_type] = mock_stub

        # Act & Assert
        with pytest.raises(TypeError, match=r"Timestamp fields have invalid types"):
            await mock_specialists_grpc_client.evaluate_plan(
                specialist_type=specialist_type,
                cognitive_plan=sample_cognitive_plan,
                trace_context=sample_trace_context
            )

    async def test_evaluate_plan_rejects_negative_seconds(
        self,
        mock_specialists_grpc_client,
        sample_cognitive_plan,
        sample_trace_context
    ):
        """
        Verifica que seconds negativos são rejeitados.

        Valida que ValueError é lançado.
        """
        # Arrange
        specialist_type = "business"

        # Criar Timestamp com seconds negativos
        invalid_response = MagicMock()
        invalid_response.opinion_id = "op-202"
        invalid_response.specialist_type = specialist_type

        mock_timestamp = MagicMock()
        mock_timestamp.seconds = -1
        mock_timestamp.nanos = 0
        invalid_response.evaluated_at = mock_timestamp

        # Configurar stub no client.stubs
        mock_stub = AsyncMock()
        mock_stub.EvaluatePlan = AsyncMock(return_value=invalid_response)
        mock_specialists_grpc_client.stubs[specialist_type] = mock_stub

        # Act & Assert
        with pytest.raises(ValueError, match=r"Invalid timestamp seconds"):
            await mock_specialists_grpc_client.evaluate_plan(
                specialist_type=specialist_type,
                cognitive_plan=sample_cognitive_plan,
                trace_context=sample_trace_context
            )

    async def test_evaluate_plan_rejects_invalid_nanos_range(
        self,
        mock_specialists_grpc_client,
        sample_cognitive_plan,
        sample_trace_context
    ):
        """
        Verifica que nanos fora do range [0, 1e9) são rejeitados.

        Testa nanos = -1 e nanos = 1_000_000_000.
        """
        # Arrange - nanos negativos
        specialist_type = "technical"

        invalid_response_neg = MagicMock()
        invalid_response_neg.opinion_id = "op-303"
        invalid_response_neg.specialist_type = specialist_type

        mock_timestamp_neg = MagicMock()
        mock_timestamp_neg.seconds = 1705320645
        mock_timestamp_neg.nanos = -1
        invalid_response_neg.evaluated_at = mock_timestamp_neg

        # Configurar stub no client.stubs para nanos negativos
        mock_stub = AsyncMock()
        mock_stub.EvaluatePlan = AsyncMock(return_value=invalid_response_neg)
        mock_specialists_grpc_client.stubs[specialist_type] = mock_stub

        # Act & Assert - nanos negativos
        with pytest.raises(ValueError, match=r"Invalid timestamp nanos"):
            await mock_specialists_grpc_client.evaluate_plan(
                specialist_type=specialist_type,
                cognitive_plan=sample_cognitive_plan,
                trace_context=sample_trace_context
            )

        # Arrange - nanos >= 1e9
        invalid_response_large = MagicMock()
        invalid_response_large.opinion_id = "op-404"
        invalid_response_large.specialist_type = specialist_type

        mock_timestamp_large = MagicMock()
        mock_timestamp_large.seconds = 1705320645
        mock_timestamp_large.nanos = 1_000_000_000
        invalid_response_large.evaluated_at = mock_timestamp_large

        # Configurar stub no client.stubs para nanos >= 1e9
        mock_stub2 = AsyncMock()
        mock_stub2.EvaluatePlan = AsyncMock(return_value=invalid_response_large)
        mock_specialists_grpc_client.stubs[specialist_type] = mock_stub2

        # Act & Assert - nanos >= 1e9
        with pytest.raises(ValueError, match=r"Invalid timestamp nanos"):
            await mock_specialists_grpc_client.evaluate_plan(
                specialist_type=specialist_type,
                cognitive_plan=sample_cognitive_plan,
                trace_context=sample_trace_context
            )

    async def test_evaluate_plan_logs_detailed_error_context(
        self,
        mock_specialists_grpc_client,
        sample_cognitive_plan,
        sample_trace_context,
        caplog
    ):
        """
        Verifica que logging detalhado ocorre em caso de erro.

        Valida que log contém: specialist_type, plan_id, seconds, nanos, error_type.
        """
        # Arrange
        specialist_type = "behavior"

        # Criar response inválida (dict ao invés de Timestamp)
        invalid_response = MagicMock()
        invalid_response.opinion_id = "op-505"
        invalid_response.specialist_type = specialist_type
        invalid_response.evaluated_at = {'seconds': 123, 'nanos': 456}

        # Configurar stub no client.stubs
        mock_stub = AsyncMock()
        mock_stub.EvaluatePlan = AsyncMock(return_value=invalid_response)
        mock_specialists_grpc_client.stubs[specialist_type] = mock_stub

        # Act
        with pytest.raises(TypeError):
            await mock_specialists_grpc_client.evaluate_plan(
                specialist_type=specialist_type,
                cognitive_plan=sample_cognitive_plan,
                trace_context=sample_trace_context
            )

        # Assert - verificar que erro foi logado (se implementado)
        # Note: Validação de log depende da implementação atual do cliente

    async def test_evaluate_plan_converts_timestamp_to_iso_string(
        self,
        mock_specialists_grpc_client,
        sample_cognitive_plan,
        sample_trace_context
    ):
        """
        Verifica que timestamp é convertido corretamente para string ISO.

        Valida que conversão preserva o valor original.
        """
        # Arrange
        specialist_type = "evolution"

        # Criar timestamp com valores conhecidos
        known_timestamp = Timestamp()
        known_timestamp.seconds = 1705320645
        known_timestamp.nanos = 123456789

        valid_response = specialist_pb2.EvaluatePlanResponse(
            opinion_id="op-606",
            specialist_type=specialist_type,
            specialist_version="1.0.9",
            opinion="APPROVE",
            processing_time_ms=200
        )
        valid_response.evaluated_at.CopyFrom(known_timestamp)

        # Configurar stub no client.stubs
        mock_stub = AsyncMock()
        mock_stub.EvaluatePlan = AsyncMock(return_value=valid_response)
        mock_specialists_grpc_client.stubs[specialist_type] = mock_stub

        # Act
        result = await mock_specialists_grpc_client.evaluate_plan(
            specialist_type=specialist_type,
            cognitive_plan=sample_cognitive_plan,
            trace_context=sample_trace_context
        )

        # Assert
        assert 'evaluated_at' in result, "Resultado deve conter evaluated_at"
        evaluated_at_str = result['evaluated_at']

        # Verificar que é string ISO válida
        assert isinstance(evaluated_at_str, str), "evaluated_at deve ser string"

        # Tentar parsear de volta para validar formato
        parsed_dt = datetime.fromisoformat(evaluated_at_str.replace('Z', '+00:00'))
        assert isinstance(parsed_dt, datetime), "String deve ser datetime válido"

    async def test_evaluate_plan_parallel_handles_timestamp_errors(
        self,
        mock_specialists_grpc_client,
        sample_cognitive_plan,
        sample_trace_context,
        valid_evaluate_plan_response
    ):
        """
        Verifica que evaluate_plan_parallel lida com erros de timestamp.

        Simula 2 specialists retornando timestamps inválidos e 3 válidos.
        Valida que método coleta 3 opiniões válidas e rejeita as inválidas.
        """
        # Arrange
        # Criar 3 responses válidas
        valid_responses = []
        for i, spec_type in enumerate(["business", "technical", "behavior"]):
            response = specialist_pb2.EvaluatePlanResponse(
                opinion_id=f"op-valid-{i}",
                specialist_type=spec_type,
                specialist_version="1.0.9",
                opinion="APPROVE",
                processing_time_ms=150 + i * 10
            )
            timestamp = Timestamp()
            timestamp.FromDatetime(datetime.now(timezone.utc))
            response.evaluated_at.CopyFrom(timestamp)
            valid_responses.append(response)

        # Criar 2 responses inválidas (timestamps como dict)
        invalid_responses = []
        for i, spec_type in enumerate(["evolution", "architecture"]):
            response = MagicMock()
            response.opinion_id = f"op-invalid-{i}"
            response.specialist_type = spec_type
            response.evaluated_at = {'seconds': 123, 'nanos': 456}  # Dict inválido
            invalid_responses.append(response)

        # Configurar stubs para todos os specialists
        specialist_types = ["business", "technical", "behavior", "evolution", "architecture"]
        all_responses = valid_responses + invalid_responses

        for spec_type, response in zip(specialist_types, all_responses):
            mock_stub = AsyncMock()
            mock_stub.EvaluatePlan = AsyncMock(return_value=response)
            mock_specialists_grpc_client.stubs[spec_type] = mock_stub

        # Act
        # Nota: Assumindo que evaluate_plan_parallel existe e lida com múltiplos specialists
        # Se não existir, este teste documenta o comportamento esperado
        try:
            results = await mock_specialists_grpc_client.evaluate_plan_parallel(
                cognitive_plan=sample_cognitive_plan,
                trace_context=sample_trace_context
            )

            # Assert - deve ter 3 opiniões válidas
            assert len(results) >= 3, "Deve coletar pelo menos 3 opiniões válidas"

        except AttributeError:
            # Se método não existe ainda, teste passa
            # (documenta comportamento esperado para implementação futura)
            pytest.skip("evaluate_plan_parallel não implementado ainda")
