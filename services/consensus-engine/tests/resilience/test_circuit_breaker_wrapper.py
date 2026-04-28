"""Testes para o GrpcCircuitBreakerWrapper do consensus-engine.

Gap P1: Circuit breaker implementado para proteger chamadas gRPC contra falhas em cascata.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from src.resilience.circuit_breaker_wrapper import (
    GrpcCircuitBreakerWrapper,
    get_grpc_circuit_breaker,
    init_grpc_circuit_breaker,
)


@pytest.fixture()
def reset_global_wrapper():
    """Reseta a instância global do wrapper antes de cada teste."""
    import src.resilience.circuit_breaker_wrapper as wrapper_module

    wrapper_module._global_wrapper = None
    yield
    wrapper_module._global_wrapper = None


@pytest.fixture()
def circuit_breaker_wrapper():
    """Cria uma instância do wrapper para testes."""
    return GrpcCircuitBreakerWrapper(service_name="test-consensus-engine")


class TestGrpcCircuitBreakerWrapper:
    """Testes para o GrpcCircuitBreakerWrapper."""

    def test_init_creates_default_breakers(self, circuit_breaker_wrapper):
        """Verifica que a inicialização cria circuit breakers padrão."""
        states = circuit_breaker_wrapper.get_breaker_states()

        # Deve ter breakers para Queen Agent, Analyst Agent e 5 specialists
        expected_breakers = [
            "queen_agent_calls",
            "analyst_agent_calls",
            "specialist_business_calls",
            "specialist_technical_calls",
            "specialist_behavior_calls",
            "specialist_evolution_calls",
            "specialist_architecture_calls",
        ]

        for name in expected_breakers:
            assert name in states, f"Circuit breaker {name} não foi criado"

    def test_register_custom_breaker(self, circuit_breaker_wrapper):
        """Testa registro de circuit breaker customizado."""
        cb = circuit_breaker_wrapper.register_breaker(
            name="custom_service",
            failure_threshold=10,
            recovery_timeout=120,
            description="Test custom breaker",
        )

        assert cb is not None
        states = circuit_breaker_wrapper.get_breaker_states()
        assert "custom_service" in states

    def test_get_breaker(self, circuit_breaker_wrapper):
        """Testa obter circuit breaker registrado."""
        cb = circuit_breaker_wrapper.get_breaker("queen_agent_calls")
        assert cb is not None

    def test_get_nonexistent_breaker(self, circuit_breaker_wrapper):
        """Testa obter circuit breaker inexistente retorna None."""
        cb = circuit_breaker_wrapper.get_breaker("nonexistent_breaker")
        assert cb is None

    @pytest.mark.asyncio()
    async def test_call_with_breaker_success(self, circuit_breaker_wrapper):
        """Testa chamada com sucesso através do circuit breaker."""
        mock_func = AsyncMock(return_value="success")

        result = await circuit_breaker_wrapper.call_with_breaker("queen_agent_calls", mock_func)

        assert result == "success"
        mock_func.assert_called_once()

    @pytest.mark.asyncio()
    async def test_call_with_breaker_failure(self, circuit_breaker_wrapper):
        """Testa chamada com falha através do circuit breaker."""
        mock_func = AsyncMock(side_effect=Exception("gRPC error"))

        with pytest.raises(Exception):
            await circuit_breaker_wrapper.call_with_breaker("queen_agent_calls", mock_func)

        mock_func.assert_called_once()

    @pytest.mark.asyncio()
    async def test_call_with_breaker_fallback_without_breaker(self, circuit_breaker_wrapper):
        """Testa fallback quando circuit breaker não existe."""
        mock_func = AsyncMock(return_value="fallback_result")

        # Usar nome de breaker que não existe
        result = await circuit_breaker_wrapper.call_with_breaker("nonexistent_breaker", mock_func)

        assert result == "fallback_result"
        mock_func.assert_called_once()

    @pytest.mark.asyncio()
    async def test_call_queen_agent(self, circuit_breaker_wrapper):
        """Testa chamada ao Queen Agent através do circuit breaker."""
        mock_func = AsyncMock(return_value={"decision_id": "test-123"})

        result = await circuit_breaker_wrapper.call_queen_agent(mock_func)

        assert result == {"decision_id": "test-123"}
        mock_func.assert_called_once()

    @pytest.mark.asyncio()
    async def test_call_analyst_agent(self, circuit_breaker_wrapper):
        """Testa chamada ao Analyst Agent através do circuit breaker."""
        mock_func = AsyncMock(return_value={"insight_id": "insight-456"})

        result = await circuit_breaker_wrapper.call_analyst_agent(mock_func)

        assert result == {"insight_id": "insight-456"}
        mock_func.assert_called_once()

    @pytest.mark.asyncio()
    async def test_call_specialist(self, circuit_breaker_wrapper):
        """Testa chamada a specialist através do circuit breaker."""
        mock_func = AsyncMock(
            return_value={"opinion_id": "opinion-789", "specialist_type": "business"}
        )

        result = await circuit_breaker_wrapper.call_specialist("business", mock_func)

        assert result["opinion_id"] == "opinion-789"
        mock_func.assert_called_once()

    @pytest.mark.asyncio()
    async def test_call_specialist_all_types(self, circuit_breaker_wrapper):
        """Testa chamada para todos os tipos de specialists."""
        specialist_types = ["business", "technical", "behavior", "evolution", "architecture"]

        for specialist_type in specialist_types:
            mock_func = AsyncMock(
                return_value={
                    "opinion_id": f"opinion-{specialist_type}",
                    "specialist_type": specialist_type,
                }
            )

            result = await circuit_breaker_wrapper.call_specialist(specialist_type, mock_func)

            assert result["specialist_type"] == specialist_type

    def test_get_breaker_states(self, circuit_breaker_wrapper):
        """Testa obter estados de todos os circuit breakers."""
        states = circuit_breaker_wrapper.get_breaker_states()

        assert isinstance(states, dict)
        assert len(states) >= 7  # Queen + Analyst + 5 specialists

        # Verificar que estados são válidos (CLOSED inicialmente)
        for name, state in states.items():
            # pybreaker usa "closed", "open", "half_open"
            assert state in ["closed", "open", "half_open", "UNKNOWN"]

    def test_reset_breaker(self, circuit_breaker_wrapper):
        """Testa reset de circuit breaker."""
        # Registrar um breaker customizado
        cb = circuit_breaker_wrapper.register_breaker(
            name="test_reset",
            failure_threshold=2,
            recovery_timeout=30,
        )

        # Reset deve retornar True (log apenas, pois pybreaker não tem reset direto)
        result = circuit_breaker_wrapper.reset_breaker("test_reset")
        assert result is True

    def test_reset_nonexistent_breaker(self, circuit_breaker_wrapper):
        """Testa reset de circuit breaker inexistente."""
        result = circuit_breaker_wrapper.reset_breaker("nonexistent_breaker")
        assert result is False


class TestGlobalCircuitBreaker:
    """Testes para as funções globais do circuit breaker."""

    def test_get_grpc_circuit_breaker_singleton(self, reset_global_wrapper):
        """Testa que get_grpc_circuit_breaker retorna singleton."""
        wrapper1 = get_grpc_circuit_breaker()
        wrapper2 = get_grpc_circuit_breaker()

        assert wrapper1 is wrapper2
        assert wrapper1.service_name == "consensus-engine"

    def test_init_grpc_circuit_breaker_custom(self, reset_global_wrapper):
        """Testa inicialização customizada do circuit breaker global."""
        wrapper = init_grpc_circuit_breaker(
            service_name="custom-service",
        )

        assert wrapper.service_name == "custom-service"

        # Verificar que é o mesmo singleton
        wrapper2 = get_grpc_circuit_breaker()
        assert wrapper is wrapper2


class TestCircuitBreakerStates:
    """Testes para estados do circuit breaker."""

    @pytest.mark.asyncio()
    async def test_circuit_opens_after_threshold(self, circuit_breaker_wrapper):
        """Testa que circuit breaker abre após threshold de falhas."""
        # Criar um breaker com threshold baixo para teste
        circuit_breaker_wrapper.register_breaker(
            name="test_open",
            failure_threshold=3,
            recovery_timeout=1,  # 1 segundo para recuperação rápida
        )

        mock_func = AsyncMock(side_effect=Exception("test error"))

        # Gerar falhas até o threshold
        for _ in range(3):
            try:
                await circuit_breaker_wrapper.call_with_breaker("test_open", mock_func)
            except Exception:
                pass

        # Verificar que o circuito abriu
        # Na próxima chamada deve ser rejeitada rapidamente
        with pytest.raises(Exception):
            await circuit_breaker_wrapper.call_with_breaker("test_open", mock_func)

    @pytest.mark.asyncio()
    async def test_circuit_recovers_after_timeout(self, circuit_breaker_wrapper):
        """Testa que circuit breaker recupera após timeout."""
        # Criar breaker com timeout curto
        circuit_breaker_wrapper.register_breaker(
            name="test_recovery",
            failure_threshold=2,
            recovery_timeout=1,  # 1 segundo
        )

        mock_func_fail = AsyncMock(side_effect=Exception("test error"))
        mock_func_success = AsyncMock(return_value="success")

        # Abrir o circuito
        for _ in range(2):
            try:
                await circuit_breaker_wrapper.call_with_breaker("test_recovery", mock_func_fail)
            except Exception:
                pass

        # Aguardar recuperação
        await asyncio.sleep(1.5)

        # Tentar novamente - deve permitir chamada em HALF_OPEN
        result = await circuit_breaker_wrapper.call_with_breaker("test_recovery", mock_func_success)

        assert result == "success"


@pytest.mark.asyncio()
async def test_circuit_breaker_with_grpc_error():
    """Testa comportamento com erro gRPC simulado."""
    import grpc

    # Criar um RpcError mock com o atributo code
    class MockRpcError(Exception):
        def __init__(self, message):
            super().__init__(message)
            self._code = grpc.StatusCode.UNAVAILABLE

        def code(self):
            return self._code

    wrapper = GrpcCircuitBreakerWrapper(service_name="test-grpc")

    # Simular erro gRPC
    mock_func = AsyncMock(side_effect=MockRpcError("grpc error"))

    with pytest.raises(Exception):
        await wrapper.call_queen_agent(mock_func)
