"""
Testes de validacao de configuracoes de seguranca do Service Registry.
"""
import pytest
from pydantic import ValidationError
from src.config.settings import Settings


class TestRedisPasswordValidation:
    """Testes de validacao de REDIS_PASSWORD."""

    def test_redis_password_empty_in_development_allowed(self, monkeypatch):
        """REDIS_PASSWORD vazio e permitido em development."""
        monkeypatch.setenv('ENVIRONMENT', 'development')
        monkeypatch.setenv('REDIS_PASSWORD', '')

        settings = Settings()
        assert settings.REDIS_PASSWORD == ''
        assert settings.ENVIRONMENT == 'development'

    def test_redis_password_set_in_production_allowed(self, monkeypatch):
        """REDIS_PASSWORD configurado e permitido em production."""
        monkeypatch.setenv('ENVIRONMENT', 'production')
        monkeypatch.setenv('REDIS_PASSWORD', 'secure-redis-password')

        settings = Settings()
        assert settings.REDIS_PASSWORD == 'secure-redis-password'
        assert settings.ENVIRONMENT == 'production'

    def test_redis_password_empty_in_production_rejected(self, monkeypatch):
        """REDIS_PASSWORD vazio e rejeitado em production."""
        monkeypatch.setenv('ENVIRONMENT', 'production')
        monkeypatch.setenv('REDIS_PASSWORD', '')

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert 'REDIS_PASSWORD' in str(exc_info.value)
        assert 'production' in str(exc_info.value).lower()

    def test_redis_password_empty_in_prod_alias_rejected(self, monkeypatch):
        """REDIS_PASSWORD vazio e rejeitado em 'prod' (alias)."""
        monkeypatch.setenv('ENVIRONMENT', 'prod')
        monkeypatch.setenv('REDIS_PASSWORD', '')

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert 'REDIS_PASSWORD' in str(exc_info.value)

    def test_redis_password_empty_in_staging_allowed(self, monkeypatch):
        """REDIS_PASSWORD vazio e permitido em staging."""
        monkeypatch.setenv('ENVIRONMENT', 'staging')
        monkeypatch.setenv('REDIS_PASSWORD', '')

        settings = Settings()
        assert settings.REDIS_PASSWORD == ''
        assert settings.ENVIRONMENT == 'staging'

    def test_redis_password_not_set_in_development_uses_default(self, monkeypatch):
        """REDIS_PASSWORD nao definido em development usa default vazio."""
        monkeypatch.setenv('ENVIRONMENT', 'development')
        monkeypatch.delenv('REDIS_PASSWORD', raising=False)

        settings = Settings()
        assert settings.REDIS_PASSWORD == ''
        assert settings.ENVIRONMENT == 'development'


class TestEnvironmentSettings:
    """Testes de configuracoes de ambiente."""

    def test_default_environment_is_development(self, monkeypatch):
        """Ambiente padrao e development."""
        monkeypatch.delenv('ENVIRONMENT', raising=False)
        monkeypatch.setenv('REDIS_PASSWORD', '')

        settings = Settings()
        assert settings.ENVIRONMENT == 'development'

    def test_production_environment_with_secure_settings(self, monkeypatch):
        """Producao com configuracoes seguras deve funcionar."""
        monkeypatch.setenv('ENVIRONMENT', 'production')
        monkeypatch.setenv('REDIS_PASSWORD', 'secure-password')

        settings = Settings()
        assert settings.ENVIRONMENT == 'production'
        assert settings.REDIS_PASSWORD == 'secure-password'

    def test_case_sensitivity_preserved(self, monkeypatch):
        """Nomes de configuracao sao case sensitive."""
        monkeypatch.setenv('ENVIRONMENT', 'development')
        monkeypatch.setenv('REDIS_PASSWORD', 'test-password')
        monkeypatch.setenv('SERVICE_NAME', 'test-registry')

        settings = Settings()
        assert settings.SERVICE_NAME == 'test-registry'
        assert settings.REDIS_PASSWORD == 'test-password'
