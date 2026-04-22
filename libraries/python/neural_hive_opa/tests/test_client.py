"""
Testes do cliente OPA.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from neural_hive_opa.client import (
    CircuitBreaker,
    OPAClient,
    OPAClientConfig,
    OPARequestOptions,
    OPAResult,
)


@pytest.fixture
def opa_client():
    """Fixture que cria um cliente OPA para testes."""
    return OPAClient(
        opa_url="http://opa-test:8181",
        policy_path="test/policy",
    )


@pytest.mark.asyncio
class TestOPAClient:
    """Testes do cliente OPA."""

    async def test_initialization(self, opa_client):
        """Cliente deve ser inicializado corretamente."""
        assert opa_client.opa_url == "http://opa-test:8181"
        assert opa_client.policy_path == "test/policy"
        assert opa_client.config.fail_open is False

    async def test_check_allow_decision(self, opa_client):
        """Deve retornar decisão allow quando OPA permite."""
        # Mock resposta OPA
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"allow": True, "reason": "authorized"}}
        mock_response.raise_for_status = MagicMock()

        with patch.object(opa_client._client, "post", AsyncMock(return_value=mock_response)):
            result = await opa_client.check(
                input_data={"user": {"id": "123"}, "request": {"method": "GET", "path": "/api"}}
            )

            assert result.allow is True
            assert result.cached is False

    async def test_check_deny_decision(self, opa_client):
        """Deve retornar decisão deny quando OPA nega."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"allow": False, "reason": "unauthorized"}}
        mock_response.raise_for_status = MagicMock()

        with patch.object(opa_client._client, "post", AsyncMock(return_value=mock_response)):
            result = await opa_client.check(
                input_data={"user": {"id": "123"}, "request": {"method": "GET", "path": "/api"}}
            )

            assert result.allow is False
            assert result.reason == "unauthorized"

    async def test_check_with_cache(self, opa_client):
        """Deve usar cache quando disponível."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"allow": True}}
        mock_response.raise_for_status = MagicMock()

        with patch.object(opa_client._client, "post", AsyncMock(return_value=mock_response)):
            input_data = {"user": {"id": "123"}}

            # Primeira chamada - cache miss
            result1 = await opa_client.check(input_data)
            assert result1.cached is False

            # Segunda chamada - cache hit
            result2 = await opa_client.check(input_data)
            assert result2.cached is True

    async def test_check_fail_open(self, opa_client):
        """Deve permitir acesso quando fail_open=True e OPA erro."""
        # Criar cliente com fail_open
        config = OPAClientConfig(
            opa_url="http://opa:8181",
            fail_open=True,
        )
        client = OPAClient(opa_url="http://opa:8181", config=config)

        # Usar HTTPStatusError que não está no retry_if_exception_type
        with patch.object(
            client._client,
            "post",
            AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Server error", request=MagicMock(), response=MagicMock()
                )
            ),
        ):
            result = await client.check(
                input_data={"user": {"id": "123"}},
                options=OPARequestOptions(fail_open=True),
            )

            assert result.allow is True
            assert result.reason == "fail_open"

    async def test_check_fail_closed(self, opa_client):
        """Deve lançar exceção quando fail_closed e OPA erro."""
        # Criar cliente com fail_closed
        config = OPAClientConfig(
            opa_url="http://opa:8181",
            fail_open=False,
        )
        client = OPAClient(opa_url="http://opa:8181", config=config)

        # Usar HTTPStatusError que não está no retry_if_exception_type
        with patch.object(
            client._client,
            "post",
            AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Server error", request=MagicMock(), response=MagicMock()
                )
            ),
        ):
            with pytest.raises(httpx.HTTPStatusError):
                await client.check(
                    input_data={"user": {"id": "123"}},
                    options=OPARequestOptions(fail_open=False),
                )

    async def test_cache_key_generation(self, opa_client):
        """Deve gerar mesma chave para inputs iguais."""
        input_data = {"user": {"id": "123"}, "request": {"path": "/api"}}

        key1 = opa_client._generate_cache_key("test/policy", input_data)
        key2 = opa_client._generate_cache_key("test/policy", input_data)

        assert key1 == key2

    async def test_cache_different_keys_different_inputs(self, opa_client):
        """Deve gerar chaves diferentes para inputs diferentes."""
        input1 = {"user": {"id": "123"}, "request": {"path": "/api"}}
        input2 = {"user": {"id": "456"}, "request": {"path": "/api"}}

        key1 = opa_client._generate_cache_key("test/policy", input1)
        key2 = opa_client._generate_cache_key("test/policy", input2)

        assert key1 != key2

    async def test_get_cache_stats(self, opa_client):
        """Deve retornar estatísticas do cache."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"allow": True}}
        mock_response.raise_for_status = MagicMock()

        with patch.object(opa_client._client, "post", AsyncMock(return_value=mock_response)):
            await opa_client.check({"user": {"id": "123"}})

            stats = opa_client.get_cache_stats()
            assert stats["total_entries"] == 1

    async def test_clear_cache(self, opa_client):
        """Deve limpar o cache."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"allow": True}}
        mock_response.raise_for_status = MagicMock()

        with patch.object(opa_client._client, "post", AsyncMock(return_value=mock_response)):
            await opa_client.check({"user": {"id": "123"}})

            opa_client.clear_cache()
            stats = opa_client.get_cache_stats()
            assert stats["total_entries"] == 0

    async def test_close(self, opa_client):
        """Deve fechar o cliente HTTP."""
        await opa_client.close()
        assert opa_client._client.is_closed


@pytest.mark.asyncio
class TestCircuitBreaker:
    """Testes do Circuit Breaker."""

    async def test_initial_state_closed(self):
        """Circuit breaker deve começar fechado."""
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=60)
        assert cb.get_state() == "CLOSED"
        assert cb.allow_request() is True

    async def test_opens_after_threshold(self):
        """Circuit breaker deve abrir após threshold de falhas."""
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=60)

        # Registrar falhas até threshold
        for _ in range(3):
            assert cb.allow_request() is True
            cb.record_failure()

        # Agora deve estar aberto
        assert cb.get_state() == "OPEN"
        assert cb.allow_request() is False

    async def test_half_open_after_timeout(self):
        """Circuit breaker deve ir para HALF_OPEN após timeout."""
        import time

        cb = CircuitBreaker(failure_threshold=2, reset_timeout=1)

        # Abrir circuit breaker
        cb.record_failure()
        cb.record_failure()
        assert cb.get_state() == "OPEN"

        # Esperar timeout
        time.sleep(1.1)

        # Próxima requisição deve transicionar para HALF_OPEN
        assert cb.allow_request() is True
        assert cb.get_state() == "HALF_OPEN"

    async def test_closes_after_success_in_half_open(self):
        """Circuit breaker deve fechar após sucesso em HALF_OPEN."""
        cb = CircuitBreaker(failure_threshold=10, reset_timeout=60)

        # Não abrir o circuit breaker - diretamente para HALF_OPEN
        cb._state = "HALF_OPEN"
        cb.failure_count = 0

        # Registrar sucesso - deve fechar
        cb.record_success()

        # Deve fechar
        assert cb.get_state() == "CLOSED"
        assert cb.failure_count == 0

    async def test_resets_failure_count_on_success(self):
        """Contador de falhas deve resetar em sucesso."""
        cb = CircuitBreaker(failure_threshold=5, reset_timeout=60)

        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2

        cb.record_success()
        assert cb.failure_count == 0


@pytest.mark.asyncio
class TestOPAResult:
    """Testes do OPAResult."""

    async def test_to_dict(self):
        """Deve converter para dicionário corretamente."""
        result = OPAResult(allow=True, reason="authorized", cached=False)
        expected = {
            "allow": True,
            "reason": "authorized",
            "cached": False,
            "metadata": {},
        }
        assert result.to_dict() == expected

    async def test_to_dict_with_metadata(self):
        """Deve incluir metadados na conversão."""
        result = OPAResult(
            allow=True,
            reason="authorized",
            cached=True,
            metadata={"policy_version": "v1"},
        )
        data = result.to_dict()
        assert data["metadata"]["policy_version"] == "v1"
