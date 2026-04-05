"""
Testes unitários para configuração de Rate Limiting por endpoint.

Valida a classe RateLimitConfig e a função get_rate_limit_config:
- RateLimitConfig dataclass (capacity, refill_rate, burst_multiplier)
- ENDPOINT_RATE_LIMITS dict com endpoints padrão
- Lookup de config por (method, path)
- Fallback para default config se endpoint não listado
"""

from src.config.rate_limit_config import (
    ENDPOINT_RATE_LIMITS,
    RateLimitConfig,
    get_rate_limit_config,
)


class TestRateLimitConfig:
    """Testes da dataclass RateLimitConfig."""

    def test_rate_limit_config_initialization(self):
        """Verifica que RateLimitConfig pode ser instanciada."""
        config = RateLimitConfig(
            capacity=100,
            refill_rate=10.0,
            burst_multiplier=2.0,
        )

        assert config.capacity == 100
        assert config.refill_rate == 10.0
        assert config.burst_multiplier == 2.0

    def test_rate_limit_config_default_burst_multiplier(self):
        """Verifica que burst_multiplier padrão é 2.0."""
        config = RateLimitConfig(
            capacity=50,
            refill_rate=5.0,
        )

        assert config.burst_multiplier == 2.0

    def test_get_effective_capacity_default_multiplier(self):
        """Verifica capacidade efetiva com multiplicador padrão."""
        config = RateLimitConfig(
            capacity=100,
            refill_rate=10.0,
            burst_multiplier=2.0,
        )

        assert config.get_effective_capacity() == 200

    def test_get_effective_capacity_custom_multiplier(self):
        """Verifica capacidade efetiva com multiplicador customizado."""
        config = RateLimitConfig(
            capacity=50,
            refill_rate=5.0,
            burst_multiplier=3.0,
        )

        assert config.get_effective_capacity() == 150

    def test_get_effective_capacity_no_burst(self):
        """Verifica capacidade efetiva sem burst (multiplier=1.0)."""
        config = RateLimitConfig(
            capacity=100,
            refill_rate=10.0,
            burst_multiplier=1.0,
        )

        assert config.get_effective_capacity() == 100

    def test_get_effective_capacity_returns_int(self):
        """Verifica que capacidade efetiva é sempre inteiro."""
        config = RateLimitConfig(
            capacity=101,
            refill_rate=10.0,
            burst_multiplier=2.5,
        )

        result = config.get_effective_capacity()
        assert isinstance(result, int)
        assert result == 252  # 101 * 2.5 = 252.5 -> 252


class TestEndpointRateLimits:
    """Testes do dict ENDPOINT_RATE_LIMITS."""

    def test_endpoint_rate_limits_is_dict(self):
        """Verifica que ENDPOINT_RATE_LIMITS é um dict."""
        assert isinstance(ENDPOINT_RATE_LIMITS, dict)

    def test_endpoint_rate_limits_not_empty(self):
        """Verifica que ENDPOINT_RATE_LIMITS contém endpoints padrão."""
        assert len(ENDPOINT_RATE_LIMITS) > 0

    def test_workflows_endpoint_configured(self):
        """Verifica que POST /api/v1/workflows está configurado."""
        key = "POST:/api/v1/workflows"
        assert key in ENDPOINT_RATE_LIMITS

        config = ENDPOINT_RATE_LIMITS[key]
        assert isinstance(config, RateLimitConfig)
        assert config.capacity == 50
        assert config.refill_rate == 5

    def test_predict_endpoint_configured(self):
        """Verifica que POST /api/v1/predict está configurado."""
        key = "POST:/api/v1/predict"
        assert key in ENDPOINT_RATE_LIMITS

        config = ENDPOINT_RATE_LIMITS[key]
        assert isinstance(config, RateLimitConfig)
        assert config.capacity == 10  # ML endpoint é custoso
        assert config.refill_rate == 1

    def test_health_endpoint_configured(self):
        """Verifica que GET /api/v1/health está configurado."""
        key = "GET:/api/v1/health"
        assert key in ENDPOINT_RATE_LIMITS

        config = ENDPOINT_RATE_LIMITS[key]
        assert isinstance(config, RateLimitConfig)
        assert config.capacity == 1000  # Health check é barato
        assert config.refill_rate == 100

    def test_all_configs_are_rate_limit_config_instances(self):
        """Verifica que todas as configs são instâncias de RateLimitConfig."""
        for key, config in ENDPOINT_RATE_LIMITS.items():
            assert isinstance(config, RateLimitConfig), f"{key} não é RateLimitConfig"

    def test_all_keys_follow_method_path_pattern(self):
        """Verifica que todas as chaves seguem padrão METHOD:path."""
        for key in ENDPOINT_RATE_LIMITS:
            assert ":" in key, f"{key} não contém ':')"
            parts = key.split(":", 1)
            assert len(parts) == 2, f"{key} não tem formato METHOD:path"
            method, path = parts
            assert method in [
                "GET",
                "POST",
                "PUT",
                "DELETE",
                "PATCH",
            ], f"{key} método inválido"
            assert path.startswith("/"), f"{key} path não começa com /"


class TestGetRateLimitConfig:
    """Testes da função get_rate_limit_config."""

    def setup_method(self):
        """Configura config padrão para testes."""
        self.default_config = RateLimitConfig(
            capacity=100,
            refill_rate=10.0,
            burst_multiplier=2.0,
        )

    def test_get_config_for_existing_endpoint(self):
        """Retorna config específica para endpoint configurado."""
        config = get_rate_limit_config(
            method="POST",
            path="/api/v1/workflows",
            default_config=self.default_config,
        )

        assert config.capacity == 50
        assert config.refill_rate == 5
        assert config is not self.default_config

    def test_get_config_for_predict_endpoint(self):
        """Retorna config específica para endpoint ML."""
        config = get_rate_limit_config(
            method="POST",
            path="/api/v1/predict",
            default_config=self.default_config,
        )

        assert config.capacity == 10
        assert config.refill_rate == 1

    def test_get_config_for_health_endpoint(self):
        """Retorna config específica para health check."""
        config = get_rate_limit_config(
            method="GET",
            path="/api/v1/health",
            default_config=self.default_config,
        )

        assert config.capacity == 1000
        assert config.refill_rate == 100

    def test_get_config_fallback_to_default_for_unknown_endpoint(self):
        """Retorna config padrão para endpoint não configurado."""
        config = get_rate_limit_config(
            method="POST",
            path="/api/v1/unknown",
            default_config=self.default_config,
        )

        assert config is self.default_config
        assert config.capacity == 100
        assert config.refill_rate == 10.0

    def test_get_config_case_sensitive_method(self):
        """Verifica que método é case-sensitive."""
        # POST em minúsculo não deve encontrar
        config = get_rate_limit_config(
            method="post",  # minúsculo
            path="/api/v1/workflows",
            default_config=self.default_config,
        )

        assert config is self.default_config

    def test_get_config_exact_path_match(self):
        """Verifica que match é exato (não é prefix)."""
        config = get_rate_limit_config(
            method="GET",
            path="/api/v1/health/extra",  # path diferente
            default_config=self.default_config,
        )

        assert config is self.default_config

    def test_get_config_different_method_same_path(self):
        """Verifica que métodos diferentes têm configs diferentes."""
        post_config = get_rate_limit_config(
            method="POST",
            path="/api/v1/workflows",
            default_config=self.default_config,
        )

        # GET para mesmo path não está configurado
        get_config = get_rate_limit_config(
            method="GET",
            path="/api/v1/workflows",
            default_config=self.default_config,
        )

        assert post_config.capacity == 50
        assert get_config is self.default_config


class TestRateLimitConfigValidation:
    """Testes de validação de valores em RateLimitConfig."""

    def test_capacity_must_be_positive(self):
        """Capacity deve ser positivo (não enforced por dataclass, mas documentado)."""
        # dataclasses não validam automaticamente, mas o valor deve ser usado corretamente
        config = RateLimitConfig(capacity=1, refill_rate=1.0)
        assert config.capacity == 1

    def test_refill_rate_must_be_positive(self):
        """Refill rate deve ser positivo (não enforced por dataclass, mas documentado)."""
        # dataclasses não validam automaticamente, mas o valor deve ser usado corretamente
        config = RateLimitConfig(capacity=100, refill_rate=0.1)
        assert config.refill_rate == 0.1

    def test_burst_multiplier_minimum_is_1(self):
        """Burst multiplier mínimo é 1.0 (sem burst adicional)."""
        config = RateLimitConfig(
            capacity=100,
            refill_rate=10.0,
            burst_multiplier=1.0,
        )

        assert config.get_effective_capacity() == 100

    def test_burst_multiplier_can_be_float(self):
        """Burst multiplier pode ser float."""
        config = RateLimitConfig(
            capacity=100,
            refill_rate=10.0,
            burst_multiplier=1.5,
        )

        assert config.get_effective_capacity() == 150
