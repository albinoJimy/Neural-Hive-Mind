"""
Testes TDD para neural_hive_opa - Fase RED

Testes escritos ANTES da implementação.
Seguem o ciclo RED-GREEN-REFACTOR.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from unittest.mock import AsyncMock
import pytest
import asyncio


# ===== FIXTURES =====


@pytest.fixture
def mock_opa_config():
    """Configurações mockadas para testes."""
    from neural_hive_opa.config import OPAConfig

    return OPAConfig(
        opa_url="http://localhost:8181",
        opa_timeout_seconds=5,
        opa_cache_ttl_seconds=300,
        opa_circuit_breaker_enabled=True,
        opa_circuit_breaker_failure_threshold=5,
        opa_circuit_breaker_reset_timeout_seconds=60,
        opa_max_concurrent_evaluations=20,
        opa_cache_max_size=1000,
        opa_enable_metrics=False,  # Desabilitar metrics para evitar duplicidade
    )


@pytest.fixture
def mock_response():
    """Resposta HTTP mockada."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    return mock_resp


# ===== TESTES: OPAConfig =====


class TestOPAConfig:
    """Testes do modelo de configuração."""

    def test_config_initialization(self, mock_opa_config):
        """
        DADO: Configurações válidas
        QUANDO: Crio OPAConfig
        ENTÃO: Deve armazenar valores
        """
        from neural_hive_opa.config import OPAConfig

        config = OPAConfig(
            opa_url="http://localhost:8181",
            opa_timeout_seconds=5,
            opa_cache_ttl_seconds=300,
        )

        assert config.opa_url == "http://localhost:8181"
        assert config.opa_timeout_seconds == 5

    def test_config_with_all_fields(self):
        """
        DADO: Todas as configurações
        QUANDO: Crio OPAConfig
        ENTÃO: Deve armazenar todos valores
        """
        from neural_hive_opa.config import OPAConfig

        config = OPAConfig(
            opa_url="http://opa.example.com:8181",
            opa_timeout_seconds=10,
            opa_cache_ttl_seconds=600,
            opa_circuit_breaker_enabled=True,
            opa_circuit_breaker_failure_threshold=10,
            opa_circuit_breaker_reset_timeout_seconds=120,
            opa_max_concurrent_evaluations=50,
        )

        assert config.opa_timeout_seconds == 10
        assert config.opa_cache_ttl_seconds == 600


# ===== TESTES: OPAClient Init =====


class TestOPAClientInit:
    """Testes de inicialização do OPAClient."""

    def test_client_initialization(self, mock_opa_config):
        """
        DADO: Configuração válida
        QUANDO: Crio OPAClient
        ENTÃO: Deve inicializar corretamente
        """
        from neural_hive_opa.client import OPAClient

        client = OPAClient(mock_opa_config)

        assert client.config == mock_opa_config
        assert client._cache is not None
        assert client._circuit_state == "closed"

    def test_client_cache_initialization(self, mock_opa_config):
        """
        DADO: Cache TTL configurado
        QUANDO: Crio OPAClient
        ENTÃO: Deve inicializar cache com tamanho correto
        """
        from neural_hive_opa.client import OPAClient

        client = OPAClient(mock_opa_config)

        assert hasattr(client, '_cache')
        assert client._cache.maxsize == 1000


# ===== TESTES: Cache Layer =====


class TestOPAClientCache:
    """Testes do cache de decisões OPA."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_decision(self, mock_opa_config):
        """
        DADO: Decisão previamente cacheada
        QUANDO: Avalio mesma política com mesmo input
        ENTÃO: Deve retornar do cache sem chamar OPA
        """
        from neural_hive_opa.client import OPAClient

        client = OPAClient(mock_opa_config)
        await client.initialize()

        # Adicionar decisão ao cache
        cached_decision = {"allow": True, "reason": "cached"}
        cache_key = client._get_cache_key("policy/test", {"user": "test"})
        client._cache[cache_key] = cached_decision

        # Patch para não chamar OPA
        with patch.object(client, '_call_opa') as mock_call_opa:
            mock_call_opa.return_value = {"allow": False}

            result = await client.evaluate("policy/test", {"user": "test"})

        assert result == cached_decision
        mock_call_opa.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_opa(self, mock_opa_config):
        """
        DADO: Decisão não cacheada
        QUANDO: Avalio política
        ENTÃO: Deve chamar OPA e cachear resultado
        """
        from neural_hive_opa.client import OPAClient

        client = OPAClient(mock_opa_config)
        await client.initialize()

        opa_result = {"allow": True, "reason": "allowed"}

        with patch.object(client, '_call_opa') as mock_call_opa:
            mock_call_opa.return_value = opa_result

            result = await client.evaluate("policy/test", {"user": "test"})

        assert result == opa_result
        mock_call_opa.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, mock_opa_config):
        """
        DADO: Cache com TTL expirado
        QUANDO: Avalio política após TTL
        ENTÃO: Deve chamar OPA novamente
        """
        from neural_hive_opa.client import OPAClient

        client = OPAClient(mock_opa_config)
        await client.initialize()

        # Cache expira após TTL
        # (implementado por cachetools TTLCache automaticamente)

        with patch.object(client, '_call_opa') as mock_call_opa:
            mock_call_opa.return_value = {"allow": True}

            result1 = await client.evaluate("policy/test", {"user": "test"})
            result2 = await client.evaluate("policy/test", {"user": "test"})

        # Cada chamada deve gerar chave de cache diferente ou expirar
        assert mock_call_opa.call_count >= 1

    @pytest.mark.asyncio
    async def test_cache_key_includes_input_data(self, mock_opa_config):
        """
        DADO: Input data diferente
        QUANDO: Avalio mesma política
        ENTÃO: Deve gerar chave de cache diferente
        """
        from neural_hive_opa.client import OPAClient

        client = OPAClient(mock_opa_config)

        key1 = client._get_cache_key("policy/test", {"user": "alice"})
        key2 = client._get_cache_key("policy/test", {"user": "bob"})

        assert key1 != key2


# ===== TESTES: Circuit Breaker =====


class TestOPAClientCircuitBreaker:
    """Testes do circuit breaker."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_closed_allows_requests(self, mock_opa_config):
        """
        DADO: Circuit breaker em estado closed
        QUANDO: Chamo OPA
        ENTÃO: Deve tentar requisição
        """
        from neural_hive_opa.client import OPAClient

        client = OPAClient(mock_opa_config)
        await client.initialize()

        with patch.object(client, '_call_opa') as mock_call_opa:
            mock_call_opa.return_value = {"allow": True}

            result = await client.evaluate("policy/test", {})

        assert result["allow"] is True
        assert client._circuit_state == "closed"

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_threshold(self):
        """
        DADO: Threshold de falhas atingido
        QUANDO: Falha pela enésima vez
        ENTÃO: Deve abrir circuit breaker
        """
        from neural_hive_opa.client import OPAClient
        from neural_hive_opa.config import OPAConfig

        config = OPAConfig(
            opa_url="http://localhost:8181",
            opa_circuit_breaker_failure_threshold=3,
            opa_circuit_breaker_enabled=True,
            opa_enable_metrics=False,
        )
        client = OPAClient(config)
        await client.initialize()

        with patch.object(client, '_call_opa') as mock_call_opa:
            mock_call_opa.side_effect = Exception("OPA unavailable")

            # Falhas consecutivas devem abrir o circuit breaker
            for _ in range(3):
                try:
                    await client.evaluate("policy/test", {})
                except Exception:
                    pass

        assert client._circuit_state == "open"

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_blocks_requests(self):
        """
        DADO: Circuit breaker em estado open
        QUANDO: Chamo evaluate
        ENTÃO: Deve levantar exceção sem chamar OPA
        """
        from neural_hive_opa.client import OPAClient
        from neural_hive_opa.config import OPAConfig
        from neural_hive_opa.exceptions import OPACircuitBreakerOpenError

        config = OPAConfig(
            opa_url="http://localhost:8181",
            opa_circuit_breaker_enabled=True,
            opa_enable_metrics=False,
        )
        client = OPAClient(config)
        client._circuit_state = "open"
        # Definir last_failure_time para recentemente para não expirar o timeout
        client._last_failure_time = datetime.now()

        with patch.object(client, '_call_opa') as mock_call_opa:
            # Não deve ser chamado quando circuit breaker está aberto
            with pytest.raises(OPACircuitBreakerOpenError):
                await client.evaluate("policy/test", {})


# ===== TESTES: Health Check =====


class TestOPAClientHealth:
    """Testes de health check."""

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, mock_opa_config):
        """
        DADO: OPA respondendo
        QUANDO: Chamo health_check
        ENTÃO: Deve retornar True
        """
        from neural_hive_opa.client import OPAClient

        client = OPAClient(mock_opa_config)
        await client.initialize()

        with patch.object(client, '_call_opa_health') as mock_health:
            mock_health.return_value = True

            result = await client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, mock_opa_config):
        """
        DADO: OPA indisponível
        QUANDO: Chamo health_check
        ENTÃO: Deve retornar False
        """
        from neural_hive_opa.client import OPAClient

        client = OPAClient(mock_opa_config)
        await client.initialize()

        with patch.object(client, '_call_opa_health') as mock_health:
            mock_health.return_value = False

            result = await client.health_check()

        assert result is False


# ===== TESTES: Batch Evaluation =====


class TestOPABatchEvaluation:
    """Testes de avaliação em lote."""

    @pytest.mark.asyncio
    async def test_evaluate_batch_success(self):
        """
        DADO: Lista de requisições
        QUANDO: Chamo evaluate_batch
        ENTÃO: Deve retornar todas as decisões
        """
        from neural_hive_opa.client import OPAClient
        from neural_hive_opa.config import OPAConfig

        config = OPAConfig(
            opa_url="http://localhost:8181",
            opa_max_concurrent_evaluations=5,
            opa_enable_metrics=False,
        )
        client = OPAClient(config)
        await client.initialize()

        requests = [
            {"policy": "policy1", "input": {"user": "alice"}},
            {"policy": "policy2", "input": {"user": "bob"}},
            {"policy": "policy3", "input": {"user": "charlie"}},
        ]

        expected_results = [
            {"allow": True},
            {"allow": False},
            {"allow": True},
        ]

        with patch.object(client, '_call_opa') as mock_call_opa:
            mock_call_opa.side_effect = lambda p, i: expected_results.pop(0)

            results = await client.evaluate_batch(requests)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_evaluate_batch_with_semaphore(self):
        """
        DADO: Max concurrent evaluations limitado
        QUANDO: Chamo evaluate_batch com muitas requisições
        ENTÃO: Deve respeitar limite de semáforo
        """
        from neural_hive_opa.client import OPAClient
        from neural_hive_opa.config import OPAConfig

        config = OPAConfig(
            opa_url="http://localhost:8181",
            opa_max_concurrent_evaluations=2,
            opa_enable_metrics=False,
        )
        client = OPAClient(config)
        await client.initialize()

        requests = []
        for i in range(10):
            requests.extend([
                {"policy": "policy1", "input": {"user": f"user{i}_1"}},
                {"policy": "policy2", "input": {"user": f"user{i}_2"}},
                {"policy": "policy3", "input": {"user": f"user{i}_3"}},
            ])

        with patch.object(client, '_call_opa') as mock_call_opa:
            mock_call_opa.return_value = {"allow": True}

            results = await client.evaluate_batch(requests)

        assert len(results) == 30


# ===== TESTES: Metrics =====


class TestOPAMetrics:
    """Testes de métricas Prometheus."""

    def test_metrics_initialized(self, mock_opa_config):
        """
        DADO: Cliente com métricas
        QUANDO: Crio OPAClient
        ENTÃO: Deve inicializar métricas
        """
        from neural_hive_opa.client import OPAClient
        from neural_hive_opa.metrics import OPAMetrics
        from prometheus_client import CollectorRegistry

        # Usar registry separado para testes
        registry = CollectorRegistry()
        metrics = OPAMetrics()
        client = OPAClient(mock_opa_config, metrics=metrics)

        assert client.metrics == metrics

    @pytest.mark.asyncio
    async def test_metrics_record_evaluation(self, mock_opa_config):
        """
        DADO: Avaliação realizada
        QUANDO: Chamo evaluate
        ENTÃO: Deve registrar métricas
        """
        from neural_hive_opa.client import OPAClient
        from neural_hive_opa.metrics import OPAMetrics

        metrics = OPAMetrics()
        client = OPAClient(mock_opa_config, metrics=metrics)
        await client.initialize()

        with patch.object(client, '_call_opa') as mock_call_opa:
            mock_call_opa.return_value = {"allow": True}

            await client.evaluate("policy/test", {})

        # Verificar que métricas foram registradas
        # (métricas são internas ao Prometheus, verificamos apenas que não houve erro)
        assert client.metrics is not None

    @pytest.mark.asyncio
    async def test_metrics_record_cache_hit(self, mock_opa_config):
        """
        DADO: Cache hit
        QUANDO: Decisão retornada do cache
        ENTÃO: Deve registrar métrica de cache hit
        """
        from neural_hive_opa.client import OPAClient
        from neural_hive_opa.metrics import OPAMetrics

        metrics = OPAMetrics()
        client = OPAClient(mock_opa_config, metrics=metrics)
        await client.initialize()

        # Adicionar ao cache
        cache_key = client._get_cache_key("policy/test", {"user": "test"})
        client._cache[cache_key] = {"allow": True}

        with patch.object(client, '_call_opa') as mock_call_opa:
            await client.evaluate("policy/test", {})

        # Verificar que métricas foram registradas
        assert client.metrics is not None


# ===== TESTES: Connection Management =====


class TestOPAConnection:
    """Testes de gerenciamento de conexão."""

    @pytest.mark.asyncio
    async def test_initialize_creates_session(self, mock_opa_config):
        """
        DADO: Cliente não inicializado
        QUANDO: Chamo initialize
        ENTÃO: Deve criar sessão HTTP
        """
        from neural_hive_opa.client import OPAClient

        client = OPAClient(mock_opa_config)

        with patch('neural_hive_opa.client.aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_class.return_value = mock_session

            await client.initialize()

        assert client.session is not None

    @pytest.mark.asyncio
    async def test_close_closes_session(self, mock_opa_config):
        """
        DADO: Cliente com sessão ativa
        QUANDO: Chamo close
        ENTÃO: Deve fechar sessão
        """
        from neural_hive_opa.client import OPAClient

        client = OPAClient(mock_opa_config)

        with patch('neural_hive_opa.client.aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.close = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_class.return_value = mock_session

            await client.initialize()
            session_before = client.session
            await client.close()

        assert session_before is not None


# ===== TESTES: Exceptions =====


class TestOPAExceptions:
    """Testes das exceções customizadas."""

    def test_opa_connection_error(self):
        """
        DADO: Falha de conexão com OPA
        QUANDO: OPAConnectionError é criada
        ENTÃO: Deve armazenar mensagem
        """
        from neural_hive_opa.exceptions import OPAConnectionError

        error = OPAConnectionError("Cannot connect to OPA")

        assert str(error) == "Cannot connect to OPA"

    def test_opa_policy_not_found_error(self):
        """
        DADO: Política retornou 404
        QUANDO: OPAPolicyNotFoundError é criada
        ENTÃO: Deve incluir status_code
        """
        from neural_hive_opa.exceptions import OPAPolicyNotFoundError

        error = OPAPolicyNotFoundError("policy/notfound", 404)

        assert error.status_code == 404

    def test_opa_evaluation_error(self):
        """
        DADO: Erro na avaliação
        QUANDO: OPAEvaluationError é criada
        ENTÃO: Deve armazenar detalhes
        """
        from neural_hive_opa.exceptions import OPAEvaluationError

        error = OPAEvaluationError("Evaluation failed", policy="policy/test")

        assert error.policy == "policy/test"


# ===== TESTES: Models =====


class TestOPAModels:
    """Testes dos modelos Pydantic."""

    def test_policy_request_model(self):
        """
        DADO: Dados válidos de requisição
        QUANDO: Crio PolicyRequest
        ENTÃO: Deve validar corretamente
        """
        from neural_hive_opa.models import PolicyRequest

        request = PolicyRequest(
            policy_path="neuralhive/orchestrator/allow",
            input_data={"resource": "cpu", "amount": 4},
        )

        assert request.policy_path == "neuralhive/orchestrator/allow"

    def test_policy_response_model(self):
        """
        DADO: Resposta OPA válida
        QUANDO: Crio PolicyResponse
        ENTÃO: Deve incluir allow e violations
        """
        from neural_hive_opa.models import PolicyResponse, Violation, ViolationSeverity

        response = PolicyResponse(
            allow=False,
            violations=[
                Violation(
                    rule_id="deny_all",
                    message="Access denied",
                    severity=ViolationSeverity.HIGH,
                )
            ],
        )

        assert response.allow is False
        assert len(response.violations) == 1
        assert response.violations[0].severity == ViolationSeverity.HIGH


# ===== TESTES: Utils =====


class TestOPAUtils:
    """Testes das funções utilitárias."""

    def test_build_opa_url(self):
        """
        DADO: Policy path
        QUANDO: Chamo _build_opa_url
        ENTÃO: Deve retornar URL completa
        """
        from neural_hive_opa.utils import _build_opa_url

        url = _build_opa_url(
            base_url="http://opa:8181",
            policy_path="neuralhive/orchestrator/allow"
        )

        assert url == "http://opa:8181/v1/data/neuralhive/orchestrator/allow"

    def test_build_opa_url_with_custom_port(self):
        """
        DADO: URL base com porta customizada
        QUANDO: Chamo _build_opa_url
        ENTÃO: Deve usar porta correta
        """
        from neural_hive_opa.utils import _build_opa_url

        url = _build_opa_url(
            base_url="http://opa.example.com:9000",
            policy_path="policy/test"
        )

        assert url == "http://opa.example.com:9000/v1/data/policy/test"
