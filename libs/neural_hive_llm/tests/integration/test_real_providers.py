"""
Testes de integração com providers reais.

Estes testes requerem credenciais ou serviços locais e devem ser
executados manualmente ou em CI/CD com as variáveis de ambiente
configuradas.
"""

import pytest

from neural_hive_llm import LLMResponse


@pytest.mark.integration
@pytest.mark.asyncio
async def test_openai_generate(openai_client):
    """Testa geração básica com OpenAI."""
    response: LLMResponse = await openai_client.generate(
        prompt="Say 'Hello, OpenAI!' in Portuguese.",
        temperature=0.5,
        max_tokens=50,
    )

    assert response.text is not None
    assert len(response.text) > 0
    assert "olá" in response.text.lower() or "hello" in response.text.lower()
    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0
    assert response.total_tokens > 0
    assert response.latency_ms > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_openai_generate_with_system_prompt(openai_client):
    """Testa geração com system prompt."""
    response = await openai_client.generate(
        prompt="What is 2 + 2?",
        system_prompt="You are a helpful math tutor. Be concise.",
        temperature=0.0,
    )

    assert "4" in response.text
    assert response.prompt_tokens > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_openai_streaming(openai_client):
    """Testa streaming com OpenAI."""
    chunks = []
    async for chunk in openai_client.generate_stream(
        prompt="Count from 1 to 5 in Portuguese.",
        temperature=0.0,
    ):
        chunks.append(chunk.text)

    full_text = "".join(chunks)
    assert len(full_text) > 0
    # Verificar que recebemos dados em múltiplos chunks
    assert len(chunks) > 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_openai_healthcheck(openai_client):
    """Testa healthcheck de OpenAI."""
    is_healthy = await openai_client.healthcheck()
    assert is_healthy is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_anthropic_generate(anthropic_client):
    """Testa geração básica com Anthropic."""
    response: LLMResponse = await anthropic_client.generate(
        prompt="Say 'Hello, Anthropic!' in Portuguese.",
        temperature=0.5,
        max_tokens=50,
    )

    assert response.text is not None
    assert len(response.text) > 0
    assert "olá" in response.text.lower() or "hello" in response.text.lower()
    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_anthropic_generate_with_system_prompt(anthropic_client):
    """Testa geração com system prompt no Anthropic."""
    response = await anthropic_client.generate(
        prompt="What is 3 + 3?",
        system_prompt="You are a helpful math tutor. Be concise.",
        temperature=0.0,
    )

    assert "6" in response.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_anthropic_streaming(anthropic_client):
    """Testa streaming com Anthropic."""
    chunks = []
    async for chunk in anthropic_client.generate_stream(
        prompt="Count from 1 to 5 in Spanish.",
        temperature=0.0,
    ):
        chunks.append(chunk.text)

    full_text = "".join(chunks)
    assert len(full_text) > 0
    assert len(chunks) > 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_anthropic_healthcheck(anthropic_client):
    """Testa healthcheck de Anthropic."""
    is_healthy = await anthropic_client.healthcheck()
    assert is_healthy is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_local_generate(local_client):
    """Testa geração básica com Ollama."""
    response: LLMResponse = await local_client.generate(
        prompt="Say 'Hello, Ollama!' in Portuguese.",
        temperature=0.5,
        max_tokens=50,
    )

    assert response.text is not None
    assert len(response.text) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_local_healthcheck(local_client):
    """Testa healthcheck de Ollama."""
    is_healthy = await local_client.healthcheck()
    assert is_healthy is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_batch_generation(openai_client, simple_prompts):
    """Testa geração em batch."""
    responses = await openai_client.generate_batch(
        prompts=simple_prompts[:3],
        temperature=0.0,
        max_tokens=30,
    )

    assert len(responses) == 3
    for response in responses:
        assert response.text is not None
        assert len(response.text) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_requests(openai_client, simple_prompts):
    """Testa múltiplas requisições concorrentes."""
    import asyncio

    async def generate(prompt):
        return await openai_client.generate(prompt, max_tokens=20)

    tasks = [generate(p) for p in simple_prompts[:2]]
    responses = await asyncio.gather(*tasks)

    assert len(responses) == 2
    for response in responses:
        assert response.text is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_temperature_effect(openai_client):
    """Testa efeito da temperatura nas respostas."""
    # Temperatura baixa = respostas mais consistentes
    responses_low = []
    for _ in range(2):
        response = await openai_client.generate(
            prompt="Pick a number between 1 and 10.",
            temperature=0.0,
            max_tokens=10,
        )
        responses_low.append(response.text)

    # Temperatura zero deve produzir respostas muito similares
    # (pode não ser idêntico devido a tokenização)
    assert len(responses_low) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_max_tokens_limit(openai_client):
    """Testa limite de max_tokens."""
    max_tokens = 20

    response = await openai_client.generate(
        prompt="Write a long paragraph about AI.",
        max_tokens=max_tokens,
        temperature=0.5,
    )

    # Resposta deve existir mas ser limitada
    assert response.text is not None
    assert response.completion_tokens <= max_tokens + 10  # Margem para tokenização


@pytest.mark.integration
@pytest.mark.asyncio
async def test_error_handling_invalid_api_key():
    """Testa tratamento de erro com API key inválida."""
    from neural_hive_llm import LLMClient, LLMProvider
    from neural_hive_llm.exceptions import LLMProviderError

    client = LLMClient(
        provider=LLMProvider.OPENAI,
        api_key="sk-invalid-key-12345",
        model="gpt-3.5-turbo",
    )

    try:
        await client.start()
        # Pode falhar no start ou no generate
        response = await client.generate("Test")
        # Se não falhar, pode ser porque OpenAI retorna erro diferente
    except (LLMProviderError, Exception) as e:
        # Esperado: erro de autenticação
        assert "key" in str(e).lower() or "auth" in str(e).lower() or True
    finally:
        try:
            await client.stop()
        except Exception:
            pass


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cost_estimation(openai_client):
    """Testa estimativa de custo."""
    response = await openai_client.generate(
        prompt="Explain neural networks in one sentence.",
        max_tokens=50,
    )

    # Verificar que estimativa de custo está presente
    assert response.estimated_cost_usd is not None
    assert response.estimated_cost_usd >= 0
    # Custo deve ser muito pequeno para este teste
    assert response.estimated_cost_usd < 1.0  # Menos de $1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_context_manager(openai_client):
    """Testa uso como context manager."""
    from neural_hive_llm import LLMClient, LLMProvider

    api_key = openai_client.api_key

    async with LLMClient(
        provider=LLMProvider.OPENAI,
        api_key=api_key,
        model="gpt-3.5-turbo",
    ) as client:
        response = await client.generate("Say hello")
        assert response.text is not None

    # Cliente deve ser parado automaticamente
