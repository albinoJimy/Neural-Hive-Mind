"""Testes unitários para LLMSettings."""


import pytest
from pydantic import ValidationError

from neural_hive_llm import LLMProvider
from neural_hive_llm.settings import LLMSettings, get_llm_settings, reset_llm_settings


class TestLLMSettings:
    """Testes para LLMSettings."""

    def test_default_values(self):
        """Testa valores padrão das configurações."""
        settings = LLMSettings()
        assert settings.provider == LLMProvider.LOCAL
        assert settings.model == "gpt-4"
        assert settings.timeout == 60.0
        assert settings.max_retries == 3
        assert settings.enable_circuit_breaker is True

    def test_custom_values(self):
        """Testa configuração customizada."""
        settings = LLMSettings(
            provider=LLMProvider.OPENAI,
            api_key="sk-test",
            model="gpt-4o",
            timeout=120.0,
        )
        assert settings.provider == LLMProvider.OPENAI
        assert settings.api_key == "sk-test"
        assert settings.model == "gpt-4o"
        assert settings.timeout == 120.0

    def test_api_key_validation_for_openai(self):
        """Testa validação de api_key para OpenAI."""
        with pytest.raises(ValidationError, match="api_key"):
            LLMSettings(provider=LLMProvider.OPENAI, api_key=None)

    def test_api_key_validation_for_anthropic(self):
        """Testa validação de api_key para Anthropic."""
        with pytest.raises(ValidationError, match="api_key"):
            LLMSettings(provider=LLMProvider.ANTHROPIC, api_key=None)

    def test_no_api_key_required_for_local(self):
        """Testa que provedor local não requer api_key."""
        settings = LLMSettings(provider=LLMProvider.LOCAL, api_key=None)
        assert settings.provider == LLMProvider.LOCAL
        assert settings.api_key is None

    def test_endpoint_url_default_for_local(self):
        """Testa URL padrão para provedor local."""
        settings = LLMSettings(provider=LLMProvider.LOCAL, endpoint_url=None)
        assert settings.endpoint_url is not None
        assert "11434" in settings.endpoint_url

    def test_timeout_validation(self):
        """Testa validação de timeout."""
        with pytest.raises(ValidationError):
            LLMSettings(timeout=0.5)  # Abaixo de 1.0

    def test_max_retries_validation(self):
        """Testa validação de max_retries."""
        with pytest.raises(ValidationError):
            LLMSettings(max_retries=15)  # Acima de 10

    def test_get_model_pricing_key(self):
        """Testa mapeamento de modelo para chave de preço."""
        settings = LLMSettings(model="gpt-4")
        key = settings.get_model_pricing_key()
        assert key == "gpt-4"

    def test_get_user_agent(self):
        """Testa geração de User-Agent."""
        settings = LLMSettings(service_name="my_service")
        ua = settings.get_user_agent()
        assert "my_service" in ua
        assert "1.0" in ua

    def test_env_variable_loading(self, monkeypatch):
        """Testa carregamento de variáveis de ambiente."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_API_KEY", "sk-env-test")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o")
        monkeypatch.setenv("LLM_MAX_RETRIES", "5")

        settings = LLMSettings()
        assert settings.provider == LLMProvider.OPENAI
        assert settings.api_key == "sk-env-test"
        assert settings.model == "gpt-4o"
        assert settings.max_retries == 5

        # Cleanup
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("LLM_MAX_RETRIES", raising=False)


class TestGetLLMSettings:
    """Testes para função get_llm_settings."""

    def setup_method(self):
        """Reseta estado global antes de cada teste."""
        reset_llm_settings()

    def test_returns_settings_instance(self):
        """Testa que retorna instância de LLMSettings."""
        settings = get_llm_settings()
        assert isinstance(settings, LLMSettings)

    def test_singleton_pattern(self):
        """Testa padrão singleton."""
        settings1 = get_llm_settings()
        settings2 = get_llm_settings()
        assert settings1 is settings2

    def test_with_overrides(self):
        """Testa overrides de configuração."""
        base_settings = get_llm_settings()
        base_model = base_settings.model

        # Criar nova instância com override
        overridden = get_llm_settings(model="gpt-4o-mini")

        # Base não deve ser alterada
        assert base_settings.model == base_model
        # Override deve ter novo valor
        assert overridden.model == "gpt-4o-mini"
        # Mas devem ser instâncias diferentes
        assert overridden is not base_settings

    def test_fallback_without_api_key(self, monkeypatch):
        """Testa fallback quando api_key não configurada."""
        # Remover variável de ambiente se existir
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        reset_llm_settings()
        settings = get_llm_settings()
        # Deve usar provedor local por padrão
        assert settings.provider == LLMProvider.LOCAL


class TestResetLLMSettings:
    """Testes para função reset_llm_settings."""

    def test_reset_clears_singleton(self):
        """Testa que reset limpa o singleton."""
        settings1 = get_llm_settings()
        reset_llm_settings()
        settings2 = get_llm_settings()
        # Não deve ser a mesma instância após reset
        assert settings1 is not settings2
