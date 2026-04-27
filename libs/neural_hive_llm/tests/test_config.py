"""
Testes unitários para configuração (LLMSettings).
"""

import pytest
from pydantic import ValidationError

from neural_hive_llm.config import (
    LLMSettings,
    get_llm_settings,
    reset_llm_settings,
)
from neural_hive_llm.models import LLMProvider


class TestLLMSettings:
    """Testes para LLMSettings."""

    def test_default_values(self) -> None:
        """Testa valores padrão."""
        settings = LLMSettings()
        assert settings.provider == LLMProvider.LOCAL
        assert settings.model == "llama2"
        assert settings.max_retries == 3
        assert settings.timeout_seconds == 60.0
        assert settings.temperature == 0.7

    def test_from_env_variables(self, monkeypatch) -> None:
        """Testa carregamento de variáveis de ambiente."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_API_KEY", "sk-test-key")
        monkeypatch.setenv("LLM_MODEL", "gpt-4")
        monkeypatch.setenv("LLM_MAX_RETRIES", "5")

        settings = LLMSettings()
        assert settings.provider == LLMProvider.OPENAI
        assert settings.api_key == "sk-test-key"
        assert settings.model == "gpt-4"
        assert settings.max_retries == 5

    def test_validation_openai_requires_api_key(self, monkeypatch) -> None:
        """Testa que OpenAI requer API key."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        with pytest.raises(ValidationError) as exc_info:
            LLMSettings()

        assert "api_key" in str(exc_info.value).lower()

    def test_validation_anthropic_requires_api_key(self, monkeypatch) -> None:
        """Testa que Anthropic requer API key."""
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        with pytest.raises(ValidationError) as exc_info:
            LLMSettings()

        assert "api_key" in str(exc_info.value).lower()

    def test_validation_max_retries_range(self) -> None:
        """Testa validação de range de max_retries."""
        with pytest.raises(ValidationError):
            LLMSettings(max_retries=11) > 10

        with pytest.raises(ValidationError):
            LLMSettings(max_retries=-1) < 0

    def test_validation_temperature_range(self) -> None:
        """Testa validação de range de temperatura."""
        with pytest.raises(ValidationError):
            LLMSettings(temperature=2.5) > 2.0

        with pytest.raises(ValidationError):
            LLMSettings(temperature=-0.1) < 0


class TestGetLLMSettings:
    """Testes para função get_llm_settings."""

    def test_singleton_behavior(self, monkeypatch) -> None:
        """Testa comportamento de singleton."""
        reset_llm_settings()

        monkeypatch.setenv("LLM_MODEL", "model1")
        settings1 = get_llm_settings()

        monkeypatch.setenv("LLM_MODEL", "model2")
        settings2 = get_llm_settings()

        # Singleton retorna mesma instância
        assert settings1 is settings2

    def test_override_kwargs(self, monkeypatch) -> None:
        """Testa override com kwargs."""
        reset_llm_settings()

        monkeypatch.setenv("LLM_MODEL", "env-model")
        settings = get_llm_settings(model="override-model")

        assert settings.model == "override-model"

    def test_reset_singleton(self, monkeypatch) -> None:
        """Testa reset do singleton."""
        reset_llm_settings()

        monkeypatch.setenv("LLM_MODEL", "model1")
        settings1 = get_llm_settings()

        reset_llm_settings()

        monkeypatch.setenv("LLM_MODEL", "model2")
        settings2 = get_llm_settings()

        # Após reset, valores podem mudar
        assert settings1.model == "model1"
        assert settings2.model == "model2"
