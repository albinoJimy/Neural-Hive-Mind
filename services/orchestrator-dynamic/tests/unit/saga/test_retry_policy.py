"""
Testes unitarios para SagaRetryConfig e RetryPolicy.

Testa configuracao de retry, calculo de backoff exponencial,
jitter para evitar thundering herd e logica de retry.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from typing import Set

import sys

# Mock dos modulos problematicos antes de importar
sys.modules["neural_hive_resilience"] = MagicMock()

from src.saga.retry_config import SagaRetryConfig, NON_RETRYABLE_ERRORS
from src.saga.retry_policy import RetryPolicy, RetryError, NoRetryPolicy, create_retry_policy


class TestSagaRetryConfigDefaults:
    """Testes para valores default de SagaRetryConfig."""

    def test_retry_config_defaults(self):
        """Deve criar config com valores default corretos."""
        config = SagaRetryConfig()

        assert config.max_attempts == 3
        assert config.initial_delay_ms == 1000
        assert config.max_delay_ms == 30000
        assert config.multiplier == 2.0
        assert config.jitter is True
        assert config.jitter_factor == 0.1
        assert config.non_retryable_errors == NON_RETRYABLE_ERRORS

    def test_retry_config_custom_values(self):
        """Deve aceitar valores customizados."""
        config = SagaRetryConfig(
            max_attempts=5,
            initial_delay_ms=500,
            max_delay_ms=60000,
            multiplier=3.0,
            jitter=False,
            jitter_factor=0.2,
        )

        assert config.max_attempts == 5
        assert config.initial_delay_ms == 500
        assert config.max_delay_ms == 60000
        assert config.multiplier == 3.0
        assert config.jitter is False
        assert config.jitter_factor == 0.2

    def test_retry_config_validation_max_attempts(self):
        """Deve validar max_attempts (1-10)."""
        # Valores validos
        SagaRetryConfig(max_attempts=1)
        SagaRetryConfig(max_attempts=10)

        # Valores invalidos
        with pytest.raises(ValueError):
            SagaRetryConfig(max_attempts=0)

        with pytest.raises(ValueError):
            SagaRetryConfig(max_attempts=11)

    def test_retry_config_validation_delay_bounds(self):
        """Deve validar limites de delay."""
        # Valido
        SagaRetryConfig(initial_delay_ms=100, max_delay_ms=1000)

        # Invalido: initial_delay_ms < 100
        with pytest.raises(ValueError):
            SagaRetryConfig(initial_delay_ms=50)

        # Invalido: max_delay_ms < initial_delay_ms
        with pytest.raises(ValueError):
            SagaRetryConfig(initial_delay_ms=5000, max_delay_ms=1000)

    def test_retry_config_validation_multiplier(self):
        """Deve validar multiplier (1.0 - 10.0)."""
        # Validos
        SagaRetryConfig(multiplier=1.0)
        SagaRetryConfig(multiplier=10.0)

        # Invalidos
        with pytest.raises(ValueError):
            SagaRetryConfig(multiplier=0.5)

        with pytest.raises(ValueError):
            SagaRetryConfig(multiplier=15.0)


class TestRetryConfigGetDelay:
    """Testes para metodo get_delay (backoff exponencial)."""

    def test_get_delay_first_attempt(self):
        """Primeira tentativa deve retornar initial_delay."""
        config = SagaRetryConfig(initial_delay_ms=1000, jitter=False)
        assert config.get_delay(1) == 1000

    def test_get_delay_exponential_backoff(self):
        """Deve calcular backoff exponencial corretamente."""
        config = SagaRetryConfig(
            initial_delay_ms=1000,
            multiplier=2.0,
            jitter=False,  # Desabilitar jitter para teste deterministico
        )

        assert config.get_delay(1) == 1000  # 1000 * 2^0
        assert config.get_delay(2) == 2000  # 1000 * 2^1
        assert config.get_delay(3) == 4000  # 1000 * 2^2
        assert config.get_delay(4) == 8000  # 1000 * 2^3
        assert config.get_delay(5) == 16000  # 1000 * 2^4

    def test_get_delay_with_max_cap(self):
        """Deve aplicar cap max_delay_ms."""
        config = SagaRetryConfig(
            initial_delay_ms=1000, max_delay_ms=5000, multiplier=2.0, jitter=False
        )

        assert config.get_delay(1) == 1000
        assert config.get_delay(2) == 2000
        assert config.get_delay(3) == 4000
        assert config.get_delay(4) == 5000  # Cap aplicado (seria 8000)
        assert config.get_delay(5) == 5000  # Cap mantido
        assert config.get_delay(10) == 5000  # Cap mantido

    def test_get_delay_invalid_attempt(self):
        """Tentativa < 1 deve retornar 0."""
        config = SagaRetryConfig()
        assert config.get_delay(0) == 0
        assert config.get_delay(-1) == 0

    def test_get_delay_custom_multiplier(self):
        """Deve respeitar multiplier customizado."""
        config = SagaRetryConfig(initial_delay_ms=1000, multiplier=3.0, jitter=False)

        assert config.get_delay(1) == 1000  # 1000 * 3^0
        assert config.get_delay(2) == 3000  # 1000 * 3^1
        assert config.get_delay(3) == 9000  # 1000 * 3^2


class TestRetryConfigJitter:
    """Testes para aplicacao de jitter."""

    @pytest.mark.flaky(reruns=5)
    def test_retry_config_jitter_applied(self):
        """Jitter deve variar o delay."""
        config = SagaRetryConfig(initial_delay_ms=1000, jitter=True, jitter_factor=0.1)

        delays = [config.get_delay(1) for _ in range(10)]

        # Com jitter, delays devem variar
        # Base = 1000, jitter_range = 100, range = [900, 1100]
        min_delay = min(delays)
        max_delay = max(delays)

        # Deve haver variacao (pode ocasionalmente falhar por aleatoriedade)
        assert max_delay - min_delay > 0 or len(set(delays)) > 1

        # Todos devem estar dentro do range esperado
        for delay in delays:
            assert 900 <= delay <= 1100

    def test_retry_config_no_jitter(self):
        """Sem jitter, delay deve ser deterministico."""
        config = SagaRetryConfig(initial_delay_ms=1000, jitter=False)

        delays = [config.get_delay(1) for _ in range(10)]

        # Todos devem ser iguais
        assert all(d == 1000 for d in delays)

    def test_retry_config_jitter_factor_zero(self):
        """Jitter_factor=0 deve ser equivalente a jitter=False."""
        config = SagaRetryConfig(initial_delay_ms=1000, jitter=True, jitter_factor=0.0)

        delays = [config.get_delay(1) for _ in range(10)]
        assert all(d == 1000 for d in delays)


class TestRetryConfigShouldRetry:
    """Testes para metodo should_retry."""

    def test_should_retry_within_max_attempts(self):
        """Deve retentar se dentro do limite de tentativas."""
        config = SagaRetryConfig(max_attempts=3)

        assert config.should_retry(attempt=1, error="temporary_failure") is True
        assert config.should_retry(attempt=2, error="temporary_failure") is True
        assert config.should_retry(attempt=3, error="temporary_failure") is True

    def test_should_retry_exceeds_max_attempts(self):
        """Nao deve retentar se excedeu max_attempts."""
        config = SagaRetryConfig(max_attempts=3)

        assert config.should_retry(attempt=4, error="temporary_failure") is False
        assert config.should_retry(attempt=5, error="temporary_failure") is False

    def test_should_retry_non_retryable_errors(self):
        """Nao deve retentar erros non-retryable."""
        config = SagaRetryConfig(max_attempts=5)

        # Erros non-retryable
        assert config.should_retry(attempt=1, error="validation_error") is False
        assert config.should_retry(attempt=1, error="schema_error") is False
        assert config.should_retry(attempt=1, error="permission_denied") is False
        assert config.should_retry(attempt=1, error="not_found") is False
        assert config.should_retry(attempt=1, error="authentication_error") is False

    def test_should_retry_case_insensitive(self):
        """Verificacao de erro deve ser case-insensitive."""
        config = SagaRetryConfig()

        assert config.should_retry(attempt=1, error="Validation_Error") is False
        assert config.should_retry(attempt=1, error="VALIDATION_ERROR") is False
        assert config.should_retry(attempt=1, error="permission_denied") is False

    def test_should_retry_partial_match(self):
        """Deve detectar erro mesmo que parte da mensagem."""
        config = SagaRetryConfig()

        # Mensagem contendo 'validation_error'
        assert (
            config.should_retry(attempt=1, error="Failed due to validation_error in field X")
            is False
        )

    def test_should_retry_no_error(self):
        """Sem erro fornecido, deve verificar apenas max_attempts."""
        config = SagaRetryConfig(max_attempts=3)

        assert config.should_retry(attempt=1) is True
        assert config.should_retry(attempt=3) is True
        assert config.should_retry(attempt=4) is False

    def test_should_retry_custom_non_retryable(self):
        """Deve respeitar conjunto customizado de erros non-retryable."""
        config = SagaRetryConfig(non_retryable_errors={"custom_error", "another_error"})

        assert config.should_retry(attempt=1, error="temporary_failure") is True
        assert config.should_retry(attempt=1, error="custom_error") is False
        assert config.should_retry(attempt=1, error="another_error") is False


class TestRetryConfigTotalTimeout:
    """Testes para calculo de timeout total."""

    def test_get_total_timeout_ms_default(self):
        """Deve calcular timeout total com config default."""
        config = SagaRetryConfig(
            initial_delay_ms=1000, multiplier=2.0, max_attempts=3, jitter=False
        )

        # 1000 + 2000 + 4000 = 7000
        assert config.get_total_timeout_ms() == 7000

    def test_get_total_timeout_ms_with_cap(self):
        """Deve considerar cap no calculo."""
        config = SagaRetryConfig(
            initial_delay_ms=1000, max_delay_ms=3000, multiplier=2.0, max_attempts=5, jitter=False
        )

        # 1000 + 2000 + 3000 + 3000 + 3000 = 12000
        assert config.get_total_timeout_ms() == 12000

    def test_get_total_timeout_ms_single_attempt(self):
        """Deve funcionar com tentativa unica."""
        config = SagaRetryConfig(initial_delay_ms=500, max_attempts=1, jitter=False)

        assert config.get_total_timeout_ms() == 500


class TestRetryConfigWithOverrides:
    """Testes para metodo with_overrides."""

    def test_with_overrides_single_param(self):
        """Deve criar nova config com parametro sobrescrito."""
        base = SagaRetryConfig(max_attempts=3)
        override = base.with_overrides(max_attempts=5)

        assert base.max_attempts == 3  # Original inalterado
        assert override.max_attempts == 5

        # Outros parametros mantidos
        assert override.initial_delay_ms == base.initial_delay_ms
        assert override.multiplier == base.multiplier

    def test_with_overrides_multiple_params(self):
        """Deve sobrescrever multiplos parametros."""
        base = SagaRetryConfig()
        override = base.with_overrides(max_attempts=5, initial_delay_ms=500, multiplier=3.0)

        assert override.max_attempts == 5
        assert override.initial_delay_ms == 500
        assert override.multiplier == 3.0
        # Nao sobrescrito
        assert override.jitter == base.jitter

    def test_with_overrides_none_ignores(self):
        """Parametros None devem ser ignorados."""
        base = SagaRetryConfig(max_attempts=3)
        override = base.with_overrides(max_attempts=5, initial_delay_ms=None)

        assert override.max_attempts == 5
        assert override.initial_delay_ms == base.initial_delay_ms


class TestRetryPolicy:
    """Testes para RetryPolicy."""

    @pytest.fixture
    def mock_func(self):
        """Funcao mock assincrona."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_retry_policy_success_on_first_attempt(self, mock_func):
        """Deve executar com sucesso na primeira tentativa."""
        policy = RetryPolicy()
        mock_func.return_value = "success"

        result = await policy.execute(mock_func, operation_name="test_op")

        assert result == "success"
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_policy_retries_then_succeeds(self, mock_func):
        """Deve retentar e eventualmente ter sucesso."""
        config = SagaRetryConfig(max_attempts=3, initial_delay_ms=100)
        policy = RetryPolicy(config=config)

        # Falhar 2 vezes, sucessar na 3a
        mock_func.side_effect = [Exception("fail 1"), Exception("fail 2"), "success"]

        result = await policy.execute(mock_func, operation_name="test_op")

        assert result == "success"
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_policy_fails_after_max_attempts(self, mock_func):
        """Deve falhar apos exceder max_attempts."""
        config = SagaRetryConfig(max_attempts=3, initial_delay_ms=100)
        policy = RetryPolicy(config=config)

        mock_func.side_effect = Exception("always fails")

        with pytest.raises(RetryError) as exc_info:
            await policy.execute(mock_func, operation_name="test_op")

        assert exc_info.value.total_attempts == 3
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_policy_non_retryable_fails_immediately(self, mock_func):
        """Erros non-retryable devem falhar imediatamente."""
        policy = RetryPolicy()

        mock_func.side_effect = ValueError("validation_error: field required")

        with pytest.raises(RetryError) as exc_info:
            await policy.execute(mock_func, operation_name="test_op")

        assert exc_info.value.attempt == 1
        assert mock_func.call_count == 1  # So tentou uma vez

    @pytest.mark.asyncio
    async def test_retry_policy_passes_arguments(self, mock_func):
        """Deve passar argumentos corretamente para funcao."""
        policy = RetryPolicy()
        mock_func.return_value = "result"

        result = await policy.execute(
            mock_func, "arg1", "arg2", operation_name="test_op", kwarg1="kwvalue1"
        )

        assert result == "result"
        mock_func.assert_called_once_with("arg1", "arg2", kwarg1="kwvalue1")

    @pytest.mark.asyncio
    async def test_retry_policy_preserves_exception(self, mock_func):
        """Deve preservar excecao original em RetryError."""
        policy = RetryPolicy()
        original_error = ValueError("specific error")
        mock_func.side_effect = original_error

        with pytest.raises(RetryError) as exc_info:
            await policy.execute(mock_func)

        assert exc_info.value.last_error == original_error
        assert isinstance(exc_info.value.last_error, ValueError)


class TestRetryPolicyGetRetryCount:
    """Testes para get_retry_count."""

    def test_get_retry_count_immediate(self):
        """Tempo zero deve retornar 1."""
        policy = RetryPolicy()
        now = datetime.now(timezone.utc)

        assert policy.get_retry_count(now) == 1

    def test_get_retry_count_after_first_delay(self):
        """Apos primeiro delay deve estar na tentativa 2."""
        config = SagaRetryConfig(initial_delay_ms=1000, jitter=False)
        policy = RetryPolicy(config=config)

        started = datetime.now(timezone.utc) - timedelta(milliseconds=1500)

        # 1500ms > 1000ms (primeiro delay), logo na tentativa 2
        assert policy.get_retry_count(started) == 2

    def test_get_retry_count_multiple_attempts(self):
        """Deve estimar tentativa correta apos varios delays."""
        config = SagaRetryConfig(
            initial_delay_ms=1000, multiplier=2.0, max_attempts=5, jitter=False
        )
        policy = RetryPolicy(config=config)

        # Apos 3000ms: 1000 + 2000, iniciando tentativa 3
        started = datetime.now(timezone.utc) - timedelta(milliseconds=3000)
        assert policy.get_retry_count(started) == 3

        # Apos 7000ms: 1000 + 2000 + 4000, iniciando tentativa 4
        started = datetime.now(timezone.utc) - timedelta(milliseconds=7000)
        assert policy.get_retry_count(started) == 4


class TestRetryPolicyDecorator:
    """Testes para decorator de RetryPolicy."""

    @pytest.mark.asyncio
    async def test_decorator_basic_usage(self):
        """Decorator deve aplicar retry automaticamente."""
        config = SagaRetryConfig(max_attempts=3, initial_delay_ms=100)
        policy = RetryPolicy(config=config)

        call_count = 0

        @policy.decorator(operation_name="decorated_func")
        async def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("not yet")
            return "success"

        result = await failing_func()

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_decorator_default_operation_name(self):
        """Sem operation_name, deve usar nome da funcao."""
        policy = RetryPolicy()

        @policy.decorator()
        async def my_function():
            return "result"

        result = await my_function()

        assert result == "result"
        # Logger teria registrado com operation_name='my_function'


class TestNoRetryPolicy:
    """Testes para NoRetryPolicy."""

    @pytest.mark.asyncio
    async def test_no_retry_executes_once(self):
        """Deve executar apenas uma vez, mesmo com falha."""
        policy = NoRetryPolicy()
        mock_func = AsyncMock(side_effect=Exception("fail"))

        with pytest.raises(Exception):
            await policy.execute(mock_func, operation_name="test")

        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_success(self):
        """Deve funcionar normalmente em caso de sucesso."""
        policy = NoRetryPolicy()
        mock_func = AsyncMock(return_value="result")

        result = await policy.execute(mock_func)

        assert result == "result"
        assert mock_func.call_count == 1


class TestCreateRetryPolicy:
    """Testes para factory function create_retry_policy."""

    def test_create_retry_policy_default(self):
        """Deve criar politica com valores default."""
        policy = create_retry_policy()

        assert isinstance(policy, RetryPolicy)
        assert policy.config.max_attempts == 3
        assert policy.config.initial_delay_ms == 1000

    def test_create_retry_policy_custom(self):
        """Deve criar politica com valores customizados."""
        policy = create_retry_policy(
            max_attempts=5, initial_delay_ms=500, max_delay_ms=60000, multiplier=3.0, jitter=False
        )

        assert policy.config.max_attempts == 5
        assert policy.config.initial_delay_ms == 500
        assert policy.config.max_delay_ms == 60000
        assert policy.config.multiplier == 3.0
        assert policy.config.jitter is False


class TestRetryError:
    """Testes para RetryError."""

    def test_retry_error_attributes(self):
        """Deve armazenar atributos corretamente."""
        original_error = ValueError("test error")
        error = RetryError(
            message="Operation failed", last_error=original_error, attempt=3, total_attempts=5
        )

        assert str(error) == "Operation failed"
        assert error.last_error == original_error
        assert error.attempt == 3
        assert error.total_attempts == 5

    def test_retry_error_chaining(self):
        """Deve encadear excecao original."""
        original_error = ValueError("test error")

        try:
            raise RetryError("Wrapper error", last_error=original_error) from original_error
        except RetryError as e:
            assert e.__cause__ == original_error
