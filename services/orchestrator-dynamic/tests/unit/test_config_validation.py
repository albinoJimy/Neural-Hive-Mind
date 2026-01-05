"""
Testes de validacao de configuracoes de seguranca.

Valida que configuracoes inseguras sao rejeitadas em ambiente production.
"""
import pytest
from pydantic import ValidationError
from src.config.settings import OrchestratorSettings


class TestVaultFailOpenValidation:
    """Testes de validacao de vault_fail_open."""

    def test_vault_fail_open_true_in_development_allowed(self, monkeypatch):
        """vault_fail_open=true e permitido em development."""
        monkeypatch.setenv('ENVIRONMENT', 'development')
        monkeypatch.setenv('VAULT_FAIL_OPEN', 'true')
        monkeypatch.setenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        monkeypatch.setenv('POSTGRES_HOST', 'localhost')
        monkeypatch.setenv('POSTGRES_USER', 'test')
        monkeypatch.setenv('POSTGRES_PASSWORD', 'test')
        monkeypatch.setenv('MONGODB_URI', 'mongodb://localhost:27017')
        monkeypatch.setenv('REDIS_CLUSTER_NODES', 'localhost:6379')

        settings = OrchestratorSettings()
        assert settings.vault_fail_open is True
        assert settings.environment == 'development'

    def test_vault_fail_open_false_in_production_allowed(self, monkeypatch):
        """vault_fail_open=false e permitido em production."""
        monkeypatch.setenv('ENVIRONMENT', 'production')
        monkeypatch.setenv('VAULT_FAIL_OPEN', 'false')
        monkeypatch.setenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        monkeypatch.setenv('POSTGRES_HOST', 'localhost')
        monkeypatch.setenv('POSTGRES_USER', 'test')
        monkeypatch.setenv('POSTGRES_PASSWORD', 'test')
        monkeypatch.setenv('MONGODB_URI', 'mongodb://localhost:27017')
        monkeypatch.setenv('REDIS_CLUSTER_NODES', 'localhost:6379')
        monkeypatch.setenv('REDIS_PASSWORD', 'secure-password')

        settings = OrchestratorSettings()
        assert settings.vault_fail_open is False
        assert settings.environment == 'production'

    def test_vault_fail_open_true_in_production_rejected(self, monkeypatch):
        """vault_fail_open=true e rejeitado em production."""
        monkeypatch.setenv('ENVIRONMENT', 'production')
        monkeypatch.setenv('VAULT_FAIL_OPEN', 'true')
        monkeypatch.setenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        monkeypatch.setenv('POSTGRES_HOST', 'localhost')
        monkeypatch.setenv('POSTGRES_USER', 'test')
        monkeypatch.setenv('POSTGRES_PASSWORD', 'test')
        monkeypatch.setenv('MONGODB_URI', 'mongodb://localhost:27017')
        monkeypatch.setenv('REDIS_CLUSTER_NODES', 'localhost:6379')
        monkeypatch.setenv('REDIS_PASSWORD', 'secure-password')

        with pytest.raises(ValidationError) as exc_info:
            OrchestratorSettings()

        assert 'vault_fail_open' in str(exc_info.value)
        assert 'production' in str(exc_info.value).lower()

    def test_vault_fail_open_true_in_prod_alias_rejected(self, monkeypatch):
        """vault_fail_open=true e rejeitado em 'prod' (alias)."""
        monkeypatch.setenv('ENVIRONMENT', 'prod')
        monkeypatch.setenv('VAULT_FAIL_OPEN', 'true')
        monkeypatch.setenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        monkeypatch.setenv('POSTGRES_HOST', 'localhost')
        monkeypatch.setenv('POSTGRES_USER', 'test')
        monkeypatch.setenv('POSTGRES_PASSWORD', 'test')
        monkeypatch.setenv('MONGODB_URI', 'mongodb://localhost:27017')
        monkeypatch.setenv('REDIS_CLUSTER_NODES', 'localhost:6379')
        monkeypatch.setenv('REDIS_PASSWORD', 'secure-password')

        with pytest.raises(ValidationError) as exc_info:
            OrchestratorSettings()

        assert 'vault_fail_open' in str(exc_info.value)

    def test_vault_fail_open_true_in_staging_allowed(self, monkeypatch):
        """vault_fail_open=true e permitido em staging."""
        monkeypatch.setenv('ENVIRONMENT', 'staging')
        monkeypatch.setenv('VAULT_FAIL_OPEN', 'true')
        monkeypatch.setenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        monkeypatch.setenv('POSTGRES_HOST', 'localhost')
        monkeypatch.setenv('POSTGRES_USER', 'test')
        monkeypatch.setenv('POSTGRES_PASSWORD', 'test')
        monkeypatch.setenv('MONGODB_URI', 'mongodb://localhost:27017')
        monkeypatch.setenv('REDIS_CLUSTER_NODES', 'localhost:6379')

        settings = OrchestratorSettings()
        assert settings.vault_fail_open is True
        assert settings.environment == 'staging'


class TestRedisPasswordValidation:
    """Testes de validacao de redis_password."""

    def test_redis_password_empty_in_development_allowed(self, monkeypatch):
        """redis_password vazio e permitido em development."""
        monkeypatch.setenv('ENVIRONMENT', 'development')
        monkeypatch.setenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        monkeypatch.setenv('POSTGRES_HOST', 'localhost')
        monkeypatch.setenv('POSTGRES_USER', 'test')
        monkeypatch.setenv('POSTGRES_PASSWORD', 'test')
        monkeypatch.setenv('MONGODB_URI', 'mongodb://localhost:27017')
        monkeypatch.setenv('REDIS_CLUSTER_NODES', 'localhost:6379')
        monkeypatch.setenv('REDIS_PASSWORD', '')

        settings = OrchestratorSettings()
        assert settings.redis_password in [None, '']
        assert settings.environment == 'development'

    def test_redis_password_set_in_production_allowed(self, monkeypatch):
        """redis_password configurado e permitido em production."""
        monkeypatch.setenv('ENVIRONMENT', 'production')
        monkeypatch.setenv('VAULT_FAIL_OPEN', 'false')
        monkeypatch.setenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        monkeypatch.setenv('POSTGRES_HOST', 'localhost')
        monkeypatch.setenv('POSTGRES_USER', 'test')
        monkeypatch.setenv('POSTGRES_PASSWORD', 'test')
        monkeypatch.setenv('MONGODB_URI', 'mongodb://localhost:27017')
        monkeypatch.setenv('REDIS_CLUSTER_NODES', 'localhost:6379')
        monkeypatch.setenv('REDIS_PASSWORD', 'secure-redis-password')

        settings = OrchestratorSettings()
        assert settings.redis_password == 'secure-redis-password'
        assert settings.environment == 'production'

    def test_redis_password_empty_in_production_rejected(self, monkeypatch):
        """redis_password vazio e rejeitado em production."""
        monkeypatch.setenv('ENVIRONMENT', 'production')
        monkeypatch.setenv('VAULT_FAIL_OPEN', 'false')
        monkeypatch.setenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        monkeypatch.setenv('POSTGRES_HOST', 'localhost')
        monkeypatch.setenv('POSTGRES_USER', 'test')
        monkeypatch.setenv('POSTGRES_PASSWORD', 'test')
        monkeypatch.setenv('MONGODB_URI', 'mongodb://localhost:27017')
        monkeypatch.setenv('REDIS_CLUSTER_NODES', 'localhost:6379')
        monkeypatch.setenv('REDIS_PASSWORD', '')

        with pytest.raises(ValidationError) as exc_info:
            OrchestratorSettings()

        assert 'redis_password' in str(exc_info.value)
        assert 'production' in str(exc_info.value).lower()

    def test_redis_password_none_in_production_rejected(self, monkeypatch):
        """redis_password None e rejeitado em production."""
        monkeypatch.setenv('ENVIRONMENT', 'production')
        monkeypatch.setenv('VAULT_FAIL_OPEN', 'false')
        monkeypatch.setenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        monkeypatch.setenv('POSTGRES_HOST', 'localhost')
        monkeypatch.setenv('POSTGRES_USER', 'test')
        monkeypatch.setenv('POSTGRES_PASSWORD', 'test')
        monkeypatch.setenv('MONGODB_URI', 'mongodb://localhost:27017')
        monkeypatch.setenv('REDIS_CLUSTER_NODES', 'localhost:6379')
        # Nao definir REDIS_PASSWORD (sera None)
        monkeypatch.delenv('REDIS_PASSWORD', raising=False)

        with pytest.raises(ValidationError) as exc_info:
            OrchestratorSettings()

        assert 'redis_password' in str(exc_info.value)

    def test_redis_password_empty_in_staging_allowed(self, monkeypatch):
        """redis_password vazio e permitido em staging."""
        monkeypatch.setenv('ENVIRONMENT', 'staging')
        monkeypatch.setenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        monkeypatch.setenv('POSTGRES_HOST', 'localhost')
        monkeypatch.setenv('POSTGRES_USER', 'test')
        monkeypatch.setenv('POSTGRES_PASSWORD', 'test')
        monkeypatch.setenv('MONGODB_URI', 'mongodb://localhost:27017')
        monkeypatch.setenv('REDIS_CLUSTER_NODES', 'localhost:6379')
        monkeypatch.setenv('REDIS_PASSWORD', '')

        settings = OrchestratorSettings()
        assert settings.redis_password in [None, '']
        assert settings.environment == 'staging'


class TestCombinedValidations:
    """Testes de validacoes combinadas."""

    def test_production_with_all_secure_settings(self, monkeypatch):
        """Producao com todas as configuracoes seguras deve funcionar."""
        monkeypatch.setenv('ENVIRONMENT', 'production')
        monkeypatch.setenv('VAULT_FAIL_OPEN', 'false')
        monkeypatch.setenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        monkeypatch.setenv('POSTGRES_HOST', 'localhost')
        monkeypatch.setenv('POSTGRES_USER', 'test')
        monkeypatch.setenv('POSTGRES_PASSWORD', 'test')
        monkeypatch.setenv('MONGODB_URI', 'mongodb://localhost:27017')
        monkeypatch.setenv('REDIS_CLUSTER_NODES', 'localhost:6379')
        monkeypatch.setenv('REDIS_PASSWORD', 'secure-password')

        settings = OrchestratorSettings()
        assert settings.environment == 'production'
        assert settings.vault_fail_open is False
        assert settings.redis_password == 'secure-password'

    def test_development_with_insecure_settings(self, monkeypatch):
        """Development com configuracoes inseguras deve funcionar."""
        monkeypatch.setenv('ENVIRONMENT', 'development')
        monkeypatch.setenv('VAULT_FAIL_OPEN', 'true')
        monkeypatch.setenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        monkeypatch.setenv('POSTGRES_HOST', 'localhost')
        monkeypatch.setenv('POSTGRES_USER', 'test')
        monkeypatch.setenv('POSTGRES_PASSWORD', 'test')
        monkeypatch.setenv('MONGODB_URI', 'mongodb://localhost:27017')
        monkeypatch.setenv('REDIS_CLUSTER_NODES', 'localhost:6379')
        monkeypatch.setenv('REDIS_PASSWORD', '')

        settings = OrchestratorSettings()
        assert settings.environment == 'development'
        assert settings.vault_fail_open is True
        assert settings.redis_password in [None, '']
