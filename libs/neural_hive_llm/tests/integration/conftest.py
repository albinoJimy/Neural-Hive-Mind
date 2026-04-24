"""
Configuração para testes de integração neural_hive_llm.

Testes de integração requerem credenciais reais ou serviços locais.
São marcados com @pytest.mark.integration e executados apenas em CI/CD
com credenciais configuradas.
"""

import os
import pytest

from neural_hive_llm import LLMClient, LLMProvider


def pytest_configure(config):
    """Registra marcadores customizados."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration (require API keys or local services)"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (should be skipped in CI)"
    )


@pytest.fixture
def integration_skip():
    """Skip test se não houver credenciais configuradas."""
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
    has_ollama = os.getenv("OLLAMA_HOST", "localhost:11434")

    if not any([has_openai, has_anthropic, has_ollama]):
        pytest.skip("Integration test requires at least one provider configured")


@pytest.fixture
async def openai_client():
    """Cliente OpenAI para testes de integração."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    client = LLMClient(
        provider=LLMProvider.OPENAI,
        api_key=api_key,
        model="gpt-3.5-turbo",  # Usar modelo mais barato para testes
    )
    await client.start()
    yield client
    await client.stop()


@pytest.fixture
async def anthropic_client():
    """Cliente Anthropic para testes de integração."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    client = LLMClient(
        provider=LLMProvider.ANTHROPIC,
        api_key=api_key,
        model="claude-3-haiku-20240307",  # Usar modelo mais barato
    )
    await client.start()
    yield client
    await client.stop()


@pytest.fixture
async def local_client():
    """Cliente Local (Ollama) para testes de integração."""
    base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    # Verificar se Ollama está disponível
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            response = await http.get(f"{base_url}/api/tags")
            response.raise_for_status()
    except Exception:
        pytest.skip("Ollama not available at {base_url}")

    client = LLMClient(
        provider=LLMProvider.LOCAL,
        base_url=base_url,
        model="llama2",  # Modelo comum
    )
    await client.start()
    yield client
    await client.stop()


@pytest.fixture
def simple_prompts():
    """Prompts simples para testes."""
    return [
        "What is 2 + 2?",
        "Explain microservices in one sentence.",
        "What is Python?",
    ]
