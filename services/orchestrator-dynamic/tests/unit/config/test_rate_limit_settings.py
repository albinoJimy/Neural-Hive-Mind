"""
Testes de configuração de Rate Limiting via Token Bucket.

Valida campos de configuração para rate limiting com token bucket:
- enable_rate_limiting
- rate_limit_default_capacity
- rate_limit_default_refill_rate
- rate_limit_burst_multiplier
- rate_limit_tier_limits
- rate_limit_redis_key_prefix
"""
import pytest
from pydantic import ValidationError
from src.config.settings import OrchestratorSettings


class TestRateLimitingDefaultValues:
    """Testes de valores padrão das configurações de rate limiting."""

    def setup_method(self):
        """Configurar variáveis de ambiente mínimas."""
        self.env_vars = {
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
            "POSTGRES_HOST": "localhost",
            "POSTGRES_USER": "test",
            "POSTGRES_PASSWORD": "test",
            "MONGODB_URI": "mongodb://localhost:27017",
            "REDIS_CLUSTER_NODES": "localhost:6379",
        }

    def test_default_rate_limiting_disabled(self, monkeypatch):
        """Rate limiting vem desabilitado por padrão."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)

        settings = OrchestratorSettings()
        assert settings.enable_rate_limiting is False

    def test_default_capacity_value(self, monkeypatch):
        """Capacidade padrão do token bucket é 100."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)

        settings = OrchestratorSettings()
        assert settings.rate_limit_default_capacity == 100

    def test_default_refill_rate_value(self, monkeypatch):
        """Taxa de refill padrão é 10.0 tokens/segundo."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)

        settings = OrchestratorSettings()
        assert settings.rate_limit_default_refill_rate == 10.0

    def test_default_burst_multiplier_value(self, monkeypatch):
        """Multiplicador de burst padrão é 2.0."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)

        settings = OrchestratorSettings()
        assert settings.rate_limit_burst_multiplier == 2.0

    def test_default_tier_limits(self, monkeypatch):
        """Limites por tier padrão contêm premium, standard e basic."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)

        settings = OrchestratorSettings()
        assert "premium" in settings.rate_limit_tier_limits
        assert "standard" in settings.rate_limit_tier_limits
        assert "basic" in settings.rate_limit_tier_limits

        # Validar estrutura do tier premium
        premium = settings.rate_limit_tier_limits["premium"]
        assert "capacity" in premium
        assert "refill_rate" in premium
        assert premium["capacity"] == 1000
        assert premium["refill_rate"] == 50

    def test_default_redis_key_prefix(self, monkeypatch):
        """Prefixo padrão para chaves Redis é 'rate_limit'."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)

        settings = OrchestratorSettings()
        assert settings.rate_limit_redis_key_prefix == "rate_limit"


class TestBurstMultiplierValidation:
    """Testes de validação do burst_multiplier."""

    def setup_method(self):
        """Configurar variáveis de ambiente mínimas."""
        self.env_vars = {
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
            "POSTGRES_HOST": "localhost",
            "POSTGRES_USER": "test",
            "POSTGRES_PASSWORD": "test",
            "MONGODB_URI": "mongodb://localhost:27017",
            "REDIS_CLUSTER_NODES": "localhost:6379",
        }

    def test_burst_multiplier_minimum_allowed(self, monkeypatch):
        """burst_multiplier=1.0 é permitido (mínimo)."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("RATE_LIMIT_BURST_MULTIPLIER", "1.0")

        settings = OrchestratorSettings()
        assert settings.rate_limit_burst_multiplier == 1.0

    def test_burst_multiplier_maximum_allowed(self, monkeypatch):
        """burst_multiplier=5.0 é permitido (máximo)."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("RATE_LIMIT_BURST_MULTIPLIER", "5.0")

        settings = OrchestratorSettings()
        assert settings.rate_limit_burst_multiplier == 5.0

    def test_burst_multiplier_below_minimum_rejected(self, monkeypatch):
        """burst_multiplier < 1.0 é rejeitado."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("RATE_LIMIT_BURST_MULTIPLIER", "0.9")

        with pytest.raises(ValidationError) as exc_info:
            OrchestratorSettings()

        assert "burst_multiplier" in str(exc_info.value).lower()

    def test_burst_multiplier_above_maximum_rejected(self, monkeypatch):
        """burst_multiplier > 5.0 é rejeitado."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("RATE_LIMIT_BURST_MULTIPLIER", "5.1")

        with pytest.raises(ValidationError) as exc_info:
            OrchestratorSettings()

        assert "burst_multiplier" in str(exc_info.value).lower()

    def test_burst_multiplier_negative_rejected(self, monkeypatch):
        """burst_multiplier negativo é rejeitado."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("RATE_LIMIT_BURST_MULTIPLIER", "-1.0")

        with pytest.raises(ValidationError) as exc_info:
            OrchestratorSettings()

        assert "burst_multiplier" in str(exc_info.value).lower()


class TestCapacityValidation:
    """Testes de validação da capacidade do token bucket."""

    def setup_method(self):
        """Configurar variáveis de ambiente mínimas."""
        self.env_vars = {
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
            "POSTGRES_HOST": "localhost",
            "POSTGRES_USER": "test",
            "POSTGRES_PASSWORD": "test",
            "MONGODB_URI": "mongodb://localhost:27017",
            "REDIS_CLUSTER_NODES": "localhost:6379",
        }

    def test_capacity_minimum_allowed(self, monkeypatch):
        """capacity=1 é permitido (mínimo)."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("RATE_LIMIT_DEFAULT_CAPACITY", "1")

        settings = OrchestratorSettings()
        assert settings.rate_limit_default_capacity == 1

    def test_capacity_zero_rejected(self, monkeypatch):
        """capacity=0 é rejeitado."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("RATE_LIMIT_DEFAULT_CAPACITY", "0")

        with pytest.raises(ValidationError) as exc_info:
            OrchestratorSettings()

        assert "capacity" in str(exc_info.value).lower()

    def test_capacity_negative_rejected(self, monkeypatch):
        """capacity negativo é rejeitado."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("RATE_LIMIT_DEFAULT_CAPACITY", "-10")

        with pytest.raises(ValidationError) as exc_info:
            OrchestratorSettings()

        assert "capacity" in str(exc_info.value).lower()


class TestRefillRateValidation:
    """Testes de validação da taxa de refill."""

    def setup_method(self):
        """Configurar variáveis de ambiente mínimas."""
        self.env_vars = {
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
            "POSTGRES_HOST": "localhost",
            "POSTGRES_USER": "test",
            "POSTGRES_PASSWORD": "test",
            "MONGODB_URI": "mongodb://localhost:27017",
            "REDIS_CLUSTER_NODES": "localhost:6379",
        }

    def test_refill_rate_positive_allowed(self, monkeypatch):
        """refill_rate > 0 é permitido."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("RATE_LIMIT_DEFAULT_REFILL_RATE", "5.5")

        settings = OrchestratorSettings()
        assert settings.rate_limit_default_refill_rate == 5.5

    def test_refill_rate_zero_rejected(self, monkeypatch):
        """refill_rate=0 é rejeitado."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("RATE_LIMIT_DEFAULT_REFILL_RATE", "0")

        with pytest.raises(ValidationError) as exc_info:
            OrchestratorSettings()

        assert "refill_rate" in str(exc_info.value).lower()

    def test_refill_rate_negative_rejected(self, monkeypatch):
        """refill_rate negativo é rejeitado."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("RATE_LIMIT_DEFAULT_REFILL_RATE", "-1.0")

        with pytest.raises(ValidationError) as exc_info:
            OrchestratorSettings()

        assert "refill_rate" in str(exc_info.value).lower()


class TestTierLimitsValidation:
    """Testes de validação dos limites por tier."""

    def setup_method(self):
        """Configurar variáveis de ambiente mínimas."""
        self.env_vars = {
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
            "POSTGRES_HOST": "localhost",
            "POSTGRES_USER": "test",
            "POSTGRES_PASSWORD": "test",
            "MONGODB_URI": "mongodb://localhost:27017",
            "REDIS_CLUSTER_NODES": "localhost:6379",
        }

    def test_tier_limits_valid_structure(self, monkeypatch):
        """Estrutura válida de tier_limits é aceita."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)

        settings = OrchestratorSettings()
        tier_limits = settings.rate_limit_tier_limits

        # Validar que cada tier tem os campos obrigatórios
        for tier_name, tier_config in tier_limits.items():
            assert "capacity" in tier_config
            assert "refill_rate" in tier_config
            assert isinstance(tier_config["capacity"], (int, float))
            assert isinstance(tier_config["refill_rate"], (int, float))
            assert tier_config["capacity"] > 0
            assert tier_config["refill_rate"] > 0

    def test_tier_limits_custom_via_env(self, monkeypatch):
        """Custom tier_limits via variável de ambiente (JSON)."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)

        custom_tiers = json.dumps(
            {
                "enterprise": {"capacity": 5000, "refill_rate": 200},
                "startup": {"capacity": 25, "refill_rate": 2},
            }
        )
        monkeypatch.setenv("RATE_LIMIT_TIER_LIMITS", custom_tiers)

        settings = OrchestratorSettings()
        assert "enterprise" in settings.rate_limit_tier_limits
        assert "startup" in settings.rate_limit_tier_limits
        assert settings.rate_limit_tier_limits["enterprise"]["capacity"] == 5000

    def test_tier_limits_missing_capacity_rejected(self, monkeypatch):
        """Tier sem campo 'capacity' é rejeitado."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)

        invalid_tiers = json.dumps(
            {"invalid_tier": {"refill_rate": 10}}  # falta capacity
        )
        monkeypatch.setenv("RATE_LIMIT_TIER_LIMITS", invalid_tiers)

        with pytest.raises(ValidationError) as exc_info:
            OrchestratorSettings()

        assert (
            "tier" in str(exc_info.value).lower()
            or "capacity" in str(exc_info.value).lower()
        )

    def test_tier_limits_missing_refill_rate_rejected(self, monkeypatch):
        """Tier sem campo 'refill_rate' é rejeitado."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)

        invalid_tiers = json.dumps(
            {"invalid_tier": {"capacity": 100}}  # falta refill_rate
        )
        monkeypatch.setenv("RATE_LIMIT_TIER_LIMITS", invalid_tiers)

        with pytest.raises(ValidationError) as exc_info:
            OrchestratorSettings()

        assert (
            "tier" in str(exc_info.value).lower()
            or "refill_rate" in str(exc_info.value).lower()
        )

    def test_tier_limits_negative_capacity_rejected(self, monkeypatch):
        """Tier com capacity negativo é rejeitado."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)

        invalid_tiers = json.dumps(
            {"invalid_tier": {"capacity": -10, "refill_rate": 5}}
        )
        monkeypatch.setenv("RATE_LIMIT_TIER_LIMITS", invalid_tiers)

        with pytest.raises(ValidationError) as exc_info:
            OrchestratorSettings()

        assert "capacity" in str(exc_info.value).lower()

    def test_tier_limits_zero_refill_rate_rejected(self, monkeypatch):
        """Tier com refill_rate=0 é rejeitado."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)

        invalid_tiers = json.dumps(
            {"invalid_tier": {"capacity": 100, "refill_rate": 0}}
        )
        monkeypatch.setenv("RATE_LIMIT_TIER_LIMITS", invalid_tiers)

        with pytest.raises(ValidationError) as exc_info:
            OrchestratorSettings()

        assert "refill_rate" in str(exc_info.value).lower()


class TestEnableRateLimiting:
    """Testes de habilitação de rate limiting."""

    def setup_method(self):
        """Configurar variáveis de ambiente mínimas."""
        self.env_vars = {
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
            "POSTGRES_HOST": "localhost",
            "POSTGRES_USER": "test",
            "POSTGRES_PASSWORD": "test",
            "MONGODB_URI": "mongodb://localhost:27017",
            "REDIS_CLUSTER_NODES": "localhost:6379",
        }

    def test_enable_rate_limiting_true(self, monkeypatch):
        """Habilitar rate limiting via variável de ambiente."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("ENABLE_RATE_LIMITING", "true")

        settings = OrchestratorSettings()
        assert settings.enable_rate_limiting is True

    def test_enable_rate_limiting_false(self, monkeypatch):
        """Desabilitar rate limiting via variável de ambiente."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("ENABLE_RATE_LIMITING", "false")

        settings = OrchestratorSettings()
        assert settings.enable_rate_limiting is False

    def test_enable_rate_limiting_with_integer_1(self, monkeypatch):
        """Valor inteiro 1 é interpretado como True."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("ENABLE_RATE_LIMITING", "1")

        settings = OrchestratorSettings()
        assert settings.enable_rate_limiting is True

    def test_enable_rate_limiting_with_integer_0(self, monkeypatch):
        """Valor inteiro 0 é interpretado como False."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("ENABLE_RATE_LIMITING", "0")

        settings = OrchestratorSettings()
        assert settings.enable_rate_limiting is False


class TestRedisKeyPrefix:
    """Testes de configuração do prefixo de chaves Redis."""

    def setup_method(self):
        """Configurar variáveis de ambiente mínimas."""
        self.env_vars = {
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
            "POSTGRES_HOST": "localhost",
            "POSTGRES_USER": "test",
            "POSTGRES_PASSWORD": "test",
            "MONGODB_URI": "mongodb://localhost:27017",
            "REDIS_CLUSTER_NODES": "localhost:6379",
        }

    def test_custom_redis_key_prefix(self, monkeypatch):
        """Prefixo customizado para chaves Redis."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("RATE_LIMIT_REDIS_KEY_PREFIX", "custom_prefix")

        settings = OrchestratorSettings()
        assert settings.rate_limit_redis_key_prefix == "custom_prefix"

    def test_redis_key_prefix_with_colon(self, monkeypatch):
        """Prefixo com dois pontos é preservado."""
        for k, v in self.env_vars.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("RATE_LIMIT_REDIS_KEY_PREFIX", "rate_limit:")

        settings = OrchestratorSettings()
        assert settings.rate_limit_redis_key_prefix == "rate_limit:"


# Import json para testes de tier_limits via JSON
import json
