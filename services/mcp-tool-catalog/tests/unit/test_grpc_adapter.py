"""
Testes unitarios para GRPCAdapter.

Cobertura:
- Execucao de chamadas gRPC (unary)
- Discovery de servicos via Service Registry
- Reconexao e retry com exponential backoff
- Tratamento de erros gRPC
- Validacao de disponibilidade
- Timeout em chamadas de longa duracao
- Metadata gRPC (autenticacao, tracing)
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime

import pytest
import grpc
from grpc.aio import AioRpcError
from grpc import Status

from src.adapters.base_adapter import ExecutionResult


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_service_registry():
    """Mock do Service Registry client."""
    registry = AsyncMock()
    registry.discover_service = AsyncMock(return_value={
        "service_name": "analyst_agents",
        "host": "analyst_agents.neural-hive.svc.cluster.local",
        "port": 9090,
        "metadata": {"version": "1.0.0"}
    })
    registry.send_heartbeat = AsyncMock()
    return registry


@pytest.fixture
def mock_grpc_channel():
    """Mock do gRPC channel."""
    channel = AsyncMock()
    return channel


@pytest.fixture
def mock_grpc_stub():
    """Mock do gRPC stub."""
    stub = AsyncMock()
    return stub


# ============================================================================
# Testes de Inicializacao
# ============================================================================

class TestGRPCAdapterInitialization:
    """Testes de inicializacao do GRPCAdapter."""

    def test_adapter_initialization_with_service_registry(self, mock_service_registry):
        """Testa inicializacao com Service Registry."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(
            service_registry=mock_service_registry,
            timeout_seconds=30,
            max_retries=3
        )

        assert adapter.service_registry == mock_service_registry
        assert adapter.timeout_seconds == 30
        assert adapter.max_retries == 3
        assert adapter._channel_cache == {}

    def test_adapter_initialization_without_service_registry(self):
        """Testa inicializacao sem Service Registry (direct connection)."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(
            service_registry=None,
            timeout_seconds=60,
            max_retries=5
        )

        assert adapter.service_registry is None
        assert adapter.timeout_seconds == 60
        assert adapter.max_retries == 5


# ============================================================================
# Testes de Execucao gRPC
# ============================================================================

class TestGRPCAdapterExecution:
    """Testes de execucao de chamadas gRPC."""

    @pytest.mark.asyncio
    async def test_execute_unary_call_success(self, mock_service_registry):
        """Testa chamada gRPC unary bem-sucedida."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        # Mock response
        mock_response = Mock()
        mock_response.success = True
        mock_response.insight_data = '{"key": "value"}'
        mock_response.exit_code = 0

        with patch.object(adapter, '_get_stub', new_callable=AsyncMock) as mock_get_stub:
            mock_stub = AsyncMock()
            mock_stub.ExecuteTool = AsyncMock(return_value=mock_response)
            mock_get_stub.return_value = mock_stub

            result = await adapter.execute(
                tool_id="analyst-agent-001",
                tool_name="analyst_agents",
                command="analyst_agents:GetInsight",
                parameters={"insight_id": "123"},
                context={"trace_id": "trace-123"}
            )

            assert result.success is True
            assert result.exit_code == 0
            assert '{"key": "value"}' in result.output
            assert result.metadata.get("command") == "analyst_agents:GetInsight"

    @pytest.mark.asyncio
    async def test_execute_with_service_discovery(self, mock_service_registry):
        """Testa execucao com discovery via Service Registry."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        mock_response = Mock()
        mock_response.success = True
        mock_response.message = "Analysis complete"

        with patch.object(adapter, '_get_stub', new_callable=AsyncMock) as mock_get_stub:
            mock_stub = AsyncMock()
            mock_stub.ExecuteTool = AsyncMock(return_value=mock_response)
            mock_get_stub.return_value = mock_stub

            result = await adapter.execute(
                tool_id="analyst-agent-001",
                tool_name="analyst_agents",
                command="analyst_agents:GetInsight",
                parameters={"insight_id": "456"},
                context={}
            )

            # Verifica que o service registry foi consultado
            mock_service_registry.discover_service.assert_called_once_with("analyst_agents")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_with_grpc_error(self, mock_service_registry):
        """Testa tratamento de erro gRPC."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        with patch.object(adapter, '_get_stub', new_callable=AsyncMock) as mock_get_stub:
            mock_stub = AsyncMock()
            # Simular erro gRPC
            mock_stub.ExecuteTool = AsyncMock(
                side_effect=AioRpcError(
                    grpc.StatusCode.UNAVAILABLE,
                    "Service temporarily unavailable",
                    (),
                )
            )
            mock_get_stub.return_value = mock_stub

            result = await adapter.execute(
                tool_id="analyst-agent-001",
                tool_name="analyst_agents",
                command="analyst_agents:GetInsight",
                parameters={},
                context={}
            )

            assert result.success is False
            assert "UNAVAILABLE" in result.error or "unavailable" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_with_timeout(self, mock_service_registry):
        """Testa timeout em chamada gRPC."""
        from src.adapters.grpc_adapter import GRPCAdapter
        import asyncio

        adapter = GRPCAdapter(
            service_registry=mock_service_registry,
            timeout_seconds=1
        )

        with patch.object(adapter, '_get_stub', new_callable=AsyncMock) as mock_get_stub:
            mock_stub = AsyncMock()
            # Simular timeout
            mock_stub.ExecuteTool = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_get_stub.return_value = mock_stub

            result = await adapter.execute(
                tool_id="analyst-agent-001",
                tool_name="analyst_agents",
                command="analyst_agents:GetInsight",
                parameters={},
                context={}
            )

            assert result.success is False
            assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_with_retry_on_transient_error(self, mock_service_registry):
        """Testa retry em erros transientes."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(
            service_registry=mock_service_registry,
            max_retries=3
        )

        mock_response = Mock()
        mock_response.success = True
        mock_response.message = "Success after retry"

        call_count = 0

        async def side_effect_retry(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise AioRpcError(grpc.StatusCode.UNAVAILABLE, "Temporary failure", ())
            return mock_response

        with patch.object(adapter, '_get_stub', new_callable=AsyncMock) as mock_get_stub:
            mock_stub = AsyncMock()
            mock_stub.ExecuteTool = AsyncMock(side_effect=side_effect_retry)
            mock_get_stub.return_value = mock_stub

            result = await adapter.execute(
                tool_id="analyst-agent-001",
                tool_name="analyst_agents",
                command="analyst_agents:GetInsight",
                parameters={},
                context={}
            )

            assert result.success is True
            assert call_count == 2  # Falhou uma vez, depois sucedeu
            assert result.metadata.get("attempts") == 2

    @pytest.mark.asyncio
    async def test_execute_exhausts_retries(self, mock_service_registry):
        """Testa que exaustao de retries retorna falha."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(
            service_registry=mock_service_registry,
            max_retries=2
        )

        with patch.object(adapter, '_get_stub', new_callable=AsyncMock) as mock_get_stub:
            mock_stub = AsyncMock()
            mock_stub.ExecuteTool = AsyncMock(
                side_effect=AioRpcError(grpc.StatusCode.UNAVAILABLE, "Persistent failure", ())
            )
            mock_get_stub.return_value = mock_stub

            result = await adapter.execute(
                tool_id="analyst-agent-001",
                tool_name="analyst_agents",
                command="analyst_agents:GetInsight",
                parameters={},
                context={}
            )

            assert result.success is False
            assert result.metadata.get("attempts") == 2


# ============================================================================
# Testes de Service Discovery
# ============================================================================

class TestServiceDiscovery:
    """Testes de descoberta de servicos."""

    @pytest.mark.asyncio
    async def test_discover_service_via_registry(self, mock_service_registry):
        """Testa descoberta de servico via Service Registry."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        service_info = await adapter._discover_service("analyst_agents")

        assert service_info["service_name"] == "analyst_agents"
        assert "analyst_agents" in service_info["host"]
        assert service_info["port"] == 9090
        mock_service_registry.discover_service.assert_called_once_with("analyst_agents")

    @pytest.mark.asyncio
    async def test_discover_service_with_cache(self, mock_service_registry):
        """Testa cache de descoberta de servico."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        # Primeira chamada - usa registry
        await adapter._discover_service("analyst_agents")
        # Segunda chamada - usa cache
        await adapter._discover_service("analyst_agents")

        # Registry deve ser chamado apenas uma vez
        mock_service_registry.discover_service.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_service_without_registry(self):
        """Testa descoberta sem registry (usa DNS)."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=None)

        # Mock DNS resolution
        with patch("socket.gethostbyname") as mock_gethostbyname:
            mock_gethostbyname.return_value = "10.0.0.1"

            service_info = await adapter._discover_service("analyst_agents")

            # Deve retornar configuracao padrao baseada em DNS
            assert service_info is not None
            assert "analyst_agents" in service_info.get("host", "")


# ============================================================================
# Testes de Channel Management
# ============================================================================

class TestChannelManagement:
    """Testes de gerenciamento de canais gRPC."""

    @pytest.mark.asyncio
    async def test_get_stub_creates_new_channel(self, mock_service_registry):
        """Testa que um novo canal e criado quando necessario."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        mock_response = Mock()
        mock_response.success = True

        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel_instance = AsyncMock()
            mock_channel.return_value = mock_channel_instance

            stub = await adapter._get_stub("analyst_agents", "analyst_agents.neural-hive.svc.cluster.local", 9090)

            assert stub is not None
            mock_channel.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_stub_reuses_cached_channel(self, mock_service_registry):
        """Testa que canal em cache e reutilizado."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        service_key = "analyst_agents:9090"

        # Simular canal em cache
        mock_cached_channel = AsyncMock()
        adapter._channel_cache[service_key] = mock_cached_channel

        with patch("grpc.aio.insecure_channel") as mock_channel:
            # Nao deve criar novo canal
            stub = await adapter._get_stub("analyst_agents", "analyst-agents", 9090)

            mock_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_channel(self, mock_service_registry):
        """Testa fechamento de canal."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        service_key = "analyst_agents:9090"
        mock_channel = AsyncMock()
        adapter._channel_cache[service_key] = mock_channel

        await adapter._close_channel("analyst_agents", 9090)

        assert service_key not in adapter._channel_cache
        mock_channel.close.assert_called_once()


# ============================================================================
# Testes de Validacao de Disponibilidade
# ============================================================================

class TestAvailabilityValidation:
    """Testes de validacao de disponibilidade de ferramentas."""

    @pytest.mark.asyncio
    async def test_validate_tool_availability_success(self, mock_service_registry):
        """Testa validacao de ferramenta disponivel."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        is_available = await adapter.validate_tool_availability("analyst_agents")

        assert is_available is True

    @pytest.mark.asyncio
    async def test_validate_tool_availability_service_not_found(self, mock_service_registry):
        """Testa validacao quando servico nao e encontrado."""
        from src.adapters.grpc_adapter import GRPCAdapter

        mock_service_registry.discover_service = AsyncMock(return_value=None)

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        is_available = await adapter.validate_tool_availability("nonexistent_service")

        assert is_available is False

    @pytest.mark.asyncio
    async def test_validate_tool_availability_with_health_check(self, mock_service_registry):
        """Testa validacao com health check gRPC."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        mock_health_response = Mock()
        mock_health_response.status = "SERVING"

        with patch.object(adapter, '_get_stub', new_callable=AsyncMock) as mock_get_stub:
            mock_stub = AsyncMock()
            mock_stub.Check = AsyncMock(return_value=mock_health_response)
            mock_get_stub.return_value = mock_stub

            is_available = await adapter.validate_tool_availability("analyst_agents", health_check=True)

            assert is_available is True


# ============================================================================
# Testes de Metadata e Tracing
# ============================================================================

class TestMetadataAndTracing:
    """Testes de metadata gRPC e distributed tracing."""

    @pytest.mark.asyncio
    async def test_execute_with_trace_id(self, mock_service_registry):
        """Testa que trace_id e propagado."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        mock_response = Mock()
        mock_response.success = True

        metadata_sent = []

        async def capture_metadata(*args, **kwargs):
            metadata = kwargs.get("metadata", [])
            metadata_sent.extend(metadata)
            return mock_response

        with patch.object(adapter, '_get_stub', new_callable=AsyncMock) as mock_get_stub:
            mock_stub = AsyncMock()
            mock_stub.ExecuteTool = AsyncMock(side_effect=capture_metadata)
            mock_get_stub.return_value = mock_stub

            await adapter.execute(
                tool_id="analyst-agent-001",
                tool_name="analyst_agents",
                command="analyst_agents:GetInsight",
                parameters={},
                context={"trace_id": "trace-123", "span_id": "span-456"}
            )

            # Verificar que metadata foi enviada
            trace_ids = [v for k, v in metadata_sent if k == "trace_id"]
            assert any("trace-123" in str(v) for v in trace_ids)

    @pytest.mark.asyncio
    async def test_execute_with_authentication_metadata(self, mock_service_registry):
        """Testa que metadata de autenticacao e enviada."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        mock_response = Mock()
        mock_response.success = True

        metadata_sent = []

        async def capture_metadata(*args, **kwargs):
            metadata = kwargs.get("metadata", [])
            metadata_sent.extend(metadata)
            return mock_response

        with patch.object(adapter, '_get_stub', new_callable=AsyncMock) as mock_get_stub:
            mock_stub = AsyncMock()
            mock_stub.ExecuteTool = AsyncMock(side_effect=capture_metadata)
            mock_get_stub.return_value = mock_stub

            await adapter.execute(
                tool_id="analyst-agent-001",
                tool_name="analyst_agents",
                command="analyst_agents:GetInsight",
                parameters={},
                context={"auth_token": "jwt-token-123"}
            )

            # Verificar que auth token foi enviado
            auth_tokens = [v for k, v in metadata_sent if k == "authorization"]
            assert len(auth_tokens) > 0


# ============================================================================
# Testes de Tratamento de Erros
# ============================================================================

class TestErrorHandling:
    """Testes de tratamento de erros especificos."""

    @pytest.mark.asyncio
    async def test_handles_deadline_exceeded(self, mock_service_registry):
        """Testa tratamento de deadline exceeded."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        with patch.object(adapter, '_get_stub', new_callable=AsyncMock) as mock_get_stub:
            mock_stub = AsyncMock()
            mock_stub.ExecuteTool = AsyncMock(
                side_effect=AioRpcError(
                    grpc.StatusCode.DEADLINE_EXCEEDED,
                    "Deadline exceeded",
                    (),
                )
            )
            mock_get_stub.return_value = mock_stub

            result = await adapter.execute(
                tool_id="analyst-agent-001",
                tool_name="analyst_agents",
                command="analyst_agents:GetInsight",
                parameters={},
                context={}
            )

            assert result.success is False
            assert "deadline" in result.error.lower()

    @pytest.mark.asyncio
    async def test_handles_permission_denied(self, mock_service_registry):
        """Testa tratamento de permission denied."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        with patch.object(adapter, '_get_stub', new_callable=AsyncMock) as mock_get_stub:
            mock_stub = AsyncMock()
            mock_stub.ExecuteTool = AsyncMock(
                side_effect=AioRpcError(
                    grpc.StatusCode.PERMISSION_DENIED,
                    "Permission denied",
                    (),
                )
            )
            mock_get_stub.return_value = mock_stub

            result = await adapter.execute(
                tool_id="analyst-agent-001",
                tool_name="analyst_agents",
                command="analyst_agents:GetInsight",
                parameters={},
                context={}
            )

            assert result.success is False
            assert "permission" in result.error.lower() or "denied" in result.error.lower()

    @pytest.mark.asyncio
    async def test_handles_unauthenticated(self, mock_service_registry):
        """Testa tratamento de unauthenticated."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        with patch.object(adapter, '_get_stub', new_callable=AsyncMock) as mock_get_stub:
            mock_stub = AsyncMock()
            mock_stub.ExecuteTool = AsyncMock(
                side_effect=AioRpcError(
                    grpc.StatusCode.UNAUTHENTICATED,
                    "Authentication required",
                    (),
                )
            )
            mock_get_stub.return_value = mock_stub

            result = await adapter.execute(
                tool_id="analyst-agent-001",
                tool_name="analyst_agents",
                command="analyst_agents:GetInsight",
                parameters={},
                context={}
            )

            assert result.success is False
            assert "authenticat" in result.error.lower()


# ============================================================================
# Testes de Performance
# ============================================================================

class TestPerformanceMetrics:
    """Testes de metricas de performance."""

    @pytest.mark.asyncio
    async def test_execution_time_is_recorded(self, mock_service_registry):
        """Testa que tempo de execucao e registrado."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        mock_response = Mock()
        mock_response.success = True
        mock_response.message = "Done"

        with patch.object(adapter, '_get_stub', new_callable=AsyncMock) as mock_get_stub:
            mock_stub = AsyncMock()
            mock_stub.ExecuteTool = AsyncMock(return_value=mock_response)
            mock_get_stub.return_value = mock_stub

            result = await adapter.execute(
                tool_id="analyst-agent-001",
                tool_name="analyst_agents",
                command="analyst_agents:GetInsight",
                parameters={},
                context={}
            )

            assert result.execution_time_ms >= 0
            assert "execution_time_ms" in str(result.metadata)

    @pytest.mark.asyncio
    async def test_metadata_contains_performance_info(self, mock_service_registry):
        """Testa que metadata contem informacoes de performance."""
        from src.adapters.grpc_adapter import GRPCAdapter

        adapter = GRPCAdapter(service_registry=mock_service_registry)

        mock_response = Mock()
        mock_response.success = True
        mock_response.message = "Done"

        with patch.object(adapter, '_get_stub', new_callable=AsyncMock) as mock_get_stub:
            mock_stub = AsyncMock()
            mock_stub.ExecuteTool = AsyncMock(return_value=mock_response)
            mock_get_stub.return_value = mock_stub

            result = await adapter.execute(
                tool_id="analyst-agent-001",
                tool_name="analyst_agents",
                command="analyst_agents:GetInsight",
                parameters={},
                context={}
            )

            assert "command" in result.metadata
            assert "service_name" in result.metadata
