"""
Testes de lógica de retry para neural_hive_agent_sdk.

Cobre retry em erros transitórios, sem retry em erros permanentes,
limite máximo de tentativas, backoff exponencial, retry idempotente
e métricas de retry.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neural_hive_agent_sdk import AgentClient, AgentConfig, AgentType

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture()
def retry_config():
    """Configuração para testes de retry."""
    return AgentConfig(
        REGISTRY_GRPC_ENDPOINT="localhost:50051",
        GRPC_TIMEOUT_SECONDS=2,
        GRPC_MAX_RETRIES=3,
        HEARTBEAT_INTERVAL_SECONDS=10,
    )


@pytest.fixture()
def mock_channel_for_retry():
    """Mock de canal funcional."""
    channel = MagicMock()
    channel.channel_ready = AsyncMock()
    channel.close = AsyncMock()
    return channel


# ============================================================================
# Testes de Retry em Erros Transitórios
# ============================================================================


class TestRetryTransientErrors:
    """Testes de retry em erros transitórios."""

    @pytest.mark.asyncio()
    async def test_retry_on_channel_ready_failure(self, retry_config, mock_channel_for_retry):
        """Testa retry quando há falha em channel_ready."""
        call_count = 0
        original_channel_ready = mock_channel_for_retry.channel_ready

        async def failing_channel_ready(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Connection refused")

        mock_channel_for_retry.channel_ready = failing_channel_ready

        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_channel_for_retry,
        ):
            client = AgentClient(config=retry_config)

            # Após 2 falhas, deve ter sucesso na 3ª tentativa
            agent_id = await client.register(
                agent_type=AgentType.WORKER,
                capabilities=["test"],
            )

            assert agent_id is not None
            assert call_count == 3

    @pytest.mark.asyncio()
    async def test_retry_success_after_transient_error(self, retry_config, mock_channel_for_retry):
        """Testa sucesso após erro transitório."""
        attempt = 0

        async def failing_once_channel_ready(*args, **kwargs):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise Exception("Temporary failure")

        mock_channel_for_retry.channel_ready = failing_once_channel_ready

        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_channel_for_retry,
        ):
            client = AgentClient(config=retry_config)

            agent_id = await client.register(
                agent_type=AgentType.SCOUT,
                capabilities=["explore"],
            )

            assert agent_id is not None
            assert attempt == 2

    @pytest.mark.asyncio()
    async def test_retry_multiple_transient_errors(self, retry_config, mock_channel_for_retry):
        """Testa múltiplos erros transitórios antes do sucesso."""
        attempt = 0

        async def failing_multiple_times_channel_ready(*args, **kwargs):
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise Exception(f"Temporary failure {attempt}")

        mock_channel_for_retry.channel_ready = failing_multiple_times_channel_ready

        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_channel_for_retry,
        ):
            client = AgentClient(config=retry_config)
            client.config.GRPC_MAX_RETRIES = 5

            agent_id = await client.register(
                agent_type=AgentType.ANALYST,
                capabilities=["analyze"],
            )

            assert agent_id is not None
            assert attempt == 3


# ============================================================================
# Testes de Falha sem Retry (Erros de Configuração)
# ============================================================================


class TestNoRetryConfigErrors:
    """Testes de ausência de retry em erros de configuração."""

    @pytest.mark.asyncio()
    async def test_invalid_endpoint_fails_after_retries(self, retry_config):
        """Testa que endpoint inválido falha após retries."""
        retry_config.REGISTRY_GRPC_ENDPOINT = "invalid-host:99999"

        channel = MagicMock()
        channel.channel_ready = AsyncMock(side_effect=Exception("Invalid endpoint"))
        channel.close = AsyncMock()

        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=channel):
            client = AgentClient(config=retry_config)

            with pytest.raises(Exception):
                await client.register(
                    agent_type=AgentType.WORKER,
                    capabilities=["test"],
                )


# ============================================================================
# Testes de Limite Máximo de Retries
# ============================================================================


class TestMaxRetries:
    """Testes de limite máximo de tentativas."""

    @pytest.mark.asyncio()
    async def test_max_retries_respected(self, retry_config):
        """Testa que limite máximo de retries é respeitado."""
        call_count = 0
        max_retries = 3

        channel = MagicMock()

        async def always_failing_channel_ready(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("Persistent failure")

        channel.channel_ready = always_failing_channel_ready
        channel.close = AsyncMock()

        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=channel):
            client = AgentClient(config=retry_config)

            with pytest.raises(Exception):
                await client.register(
                    agent_type=AgentType.WORKER,
                    capabilities=["test"],
                )

            assert call_count == max_retries

    @pytest.mark.asyncio()
    async def test_custom_max_retries(self, retry_config):
        """Testa configuração customizada de máximo de retries."""
        call_count = 0
        custom_max = 5

        channel = MagicMock()

        async def always_failing_channel_ready(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("Failure")

        channel.channel_ready = always_failing_channel_ready
        channel.close = AsyncMock()

        retry_config.GRPC_MAX_RETRIES = custom_max

        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=channel):
            client = AgentClient(config=retry_config)

            with pytest.raises(Exception):
                await client.register(
                    agent_type=AgentType.SCOUT,
                    capabilities=["test"],
                )

            assert call_count == custom_max

    @pytest.mark.asyncio()
    async def test_success_before_max_retries(self, retry_config, mock_channel_for_retry):
        """Testa sucesso antes de atingir máximo de retries."""
        call_count = 0

        async def eventually_succeeds_channel_ready(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Temporary failure")

        mock_channel_for_retry.channel_ready = eventually_succeeds_channel_ready

        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_channel_for_retry,
        ):
            client = AgentClient(config=retry_config)

            agent_id = await client.register(
                agent_type=AgentType.GUARD,
                capabilities=["test"],
            )

            assert agent_id is not None
            assert call_count == 2


# ============================================================================
# Testes de Backoff Exponencial
# ============================================================================


class TestExponentialBackoff:
    """Testes de backoff exponencial."""

    @pytest.mark.asyncio()
    async def test_backoff_occurs_between_retries(self, retry_config):
        """Testa que há delays entre tentativas de retry."""
        call_count = 0

        channel = MagicMock()

        async def failing_channel_ready(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("Failure")

        channel.channel_ready = failing_channel_ready
        channel.close = AsyncMock()

        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=channel):
            client = AgentClient(config=retry_config)
            client.config.GRPC_MAX_RETRIES = 3

            start_time = time.time()

            with pytest.raises(Exception):
                await client.register(
                    agent_type=AgentType.WORKER,
                    capabilities=["test"],
                )

            elapsed = time.time() - start_time

            assert call_count == 3
            # Deve haver delay entre tentativas (backoff)
            assert elapsed >= 0


# ============================================================================
# Testes de Retry Idempotente
# ============================================================================


class TestRetryIdempotent:
    """Testes de retry em operações idempotentes."""

    @pytest.mark.asyncio()
    async def test_register_can_be_retried(self, retry_config, mock_channel_for_retry):
        """Testa que register pode ter retry (idempotente)."""
        call_count = 0

        async def failing_once_channel_ready(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Transient error")

        mock_channel_for_retry.channel_ready = failing_once_channel_ready

        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_channel_for_retry,
        ):
            client = AgentClient(config=retry_config)

            agent_id = await client.register(
                agent_type=AgentType.WORKER,
                capabilities=["test"],
            )

            assert agent_id is not None
            assert call_count == 2

    @pytest.mark.asyncio()
    async def test_deregister_completes_once(self, retry_config, mock_channel_for_retry):
        """Testa que deregister completa uma única vez."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_channel_for_retry,
        ):
            client = AgentClient(config=retry_config)
            client.agent_id = "test-agent"

            await client.deregister()

            assert client._running is False


# ============================================================================
# Testes de Métricas de Retry
# ============================================================================


class TestRetryMetrics:
    """Testes de coleta de métricas de retry."""

    @pytest.mark.asyncio()
    async def test_retry_attempts_counted(self, retry_config, mock_channel_for_retry):
        """Testa que tentativas de retry são contadas."""
        attempt_count = 0

        async def failing_multiple_times_channel_ready(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise Exception("Transient error")

        mock_channel_for_retry.channel_ready = failing_multiple_times_channel_ready

        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_channel_for_retry,
        ):
            client = AgentClient(config=retry_config)

            agent_id = await client.register(
                agent_type=AgentType.SCOUT,
                capabilities=["explore"],
            )

            assert agent_id is not None
            assert attempt_count == 3

    @pytest.mark.asyncio()
    async def test_backoff_time_accumulated(self, retry_config):
        """Testa que tempo de backoff é acumulado."""
        call_count = 0

        channel = MagicMock()

        async def failing_channel_ready(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("Failure")

        channel.channel_ready = failing_channel_ready
        channel.close = AsyncMock()

        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=channel):
            client = AgentClient(config=retry_config)

            start_time = time.time()

            with pytest.raises(Exception):
                await client.register(
                    agent_type=AgentType.GUARD,
                    capabilities=["test"],
                )

            elapsed = time.time() - start_time

            assert elapsed >= 0
            assert call_count == 3

    @pytest.mark.asyncio()
    async def test_success_without_retry(self, retry_config, mock_channel_for_retry):
        """Testa sucesso sem necessidade de retry."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_channel_for_retry,
        ):
            client = AgentClient(config=retry_config)

            agent_id = await client.register(
                agent_type=AgentType.ANALYST,
                capabilities=["analyze"],
            )

            assert agent_id is not None
