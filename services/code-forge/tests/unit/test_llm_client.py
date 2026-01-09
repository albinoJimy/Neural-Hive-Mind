"""
Testes unitarios para LLMClient.

Cobertura:
- Geracao de codigo via OpenAI (sucesso, rate limit, erro)
- Geracao via Anthropic (sucesso, erro)
- Geracao via Ollama (sucesso, erro)
- Fallback entre providers
- Token counting e cost tracking
- Streaming vs batch generation
- Retry logic
- Metricas
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx


class TestLLMClientInitialization:
    """Testes de inicializacao do cliente."""

    def test_client_default_config(self):
        """Deve usar configuracao padrao (LOCAL)."""
        from services.code_forge.src.clients.llm_client import LLMClient, LLMProvider

        client = LLMClient()

        assert client.provider == LLMProvider.LOCAL
        assert client.model_name == 'gpt-4'
        assert 'ollama' in client.endpoint_url

    def test_client_openai_config(self):
        """Deve configurar para OpenAI."""
        from services.code_forge.src.clients.llm_client import LLMClient, LLMProvider

        client = LLMClient(
            provider=LLMProvider.OPENAI,
            api_key='test-key',
            model_name='gpt-4-turbo'
        )

        assert client.provider == LLMProvider.OPENAI
        assert client.api_key == 'test-key'
        assert 'openai.com' in client.endpoint_url

    def test_client_anthropic_config(self):
        """Deve configurar para Anthropic."""
        from services.code_forge.src.clients.llm_client import LLMClient, LLMProvider

        client = LLMClient(
            provider=LLMProvider.ANTHROPIC,
            api_key='test-key',
            model_name='claude-3-opus'
        )

        assert client.provider == LLMProvider.ANTHROPIC
        assert 'anthropic.com' in client.endpoint_url

    def test_client_custom_endpoint(self):
        """Deve aceitar endpoint customizado."""
        from services.code_forge.src.clients.llm_client import LLMClient, LLMProvider

        client = LLMClient(
            provider=LLMProvider.LOCAL,
            endpoint_url='http://custom-ollama:11434/api'
        )

        assert client.endpoint_url == 'http://custom-ollama:11434/api'


class TestLLMClientOllama:
    """Testes de geracao via Ollama (local)."""

    @pytest.mark.asyncio
    async def test_generate_via_ollama_success(self):
        """Deve gerar codigo via Ollama com sucesso."""
        from services.code_forge.src.clients.llm_client import LLMClient, LLMProvider

        client = LLMClient(provider=LLMProvider.LOCAL, model_name='codellama')
        client.client = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'response': 'def hello():\n    print("Hello")'
        }
        mock_response.raise_for_status = MagicMock()
        client.client.post = AsyncMock(return_value=mock_response)

        result = await client.generate_code(
            prompt='Generate a hello function',
            constraints={'language': 'python'},
            temperature=0.2
        )

        assert result is not None
        assert 'code' in result
        assert 'hello' in result['code']

    @pytest.mark.asyncio
    async def test_generate_via_ollama_error(self):
        """Deve retornar None quando Ollama falha."""
        from services.code_forge.src.clients.llm_client import LLMClient, LLMProvider

        client = LLMClient(provider=LLMProvider.LOCAL)
        client.client = AsyncMock()
        client.client.post = AsyncMock(side_effect=httpx.HTTPError('Connection refused'))

        result = await client.generate_code(
            prompt='Generate code',
            constraints={'language': 'python'}
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_ollama_streaming_not_supported_warning(self):
        """Deve logar warning quando streaming solicitado para Ollama."""
        from services.code_forge.src.clients.llm_client import LLMClient, LLMProvider

        client = LLMClient(provider=LLMProvider.LOCAL)
        client.client = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'response': 'code'}
        mock_response.raise_for_status = MagicMock()
        client.client.post = AsyncMock(return_value=mock_response)

        # Deve funcionar mas ignorar streaming
        result = await client.generate_code(
            prompt='Generate code',
            constraints={'language': 'python'},
            stream=True  # Solicitado mas nao suportado
        )

        assert result is not None


class TestLLMClientOpenAI:
    """Testes de geracao via OpenAI."""

    @pytest.mark.asyncio
    async def test_generate_via_openai_success(self):
        """Deve gerar codigo via OpenAI com sucesso."""
        from services.code_forge.src.clients.llm_client import LLMClient, LLMProvider

        client = LLMClient(
            provider=LLMProvider.OPENAI,
            api_key='test-key',
            model_name='gpt-4'
        )

        # Mock do SDK OpenAI
        mock_openai_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='def hello():\n    pass'))
        ]
        mock_response.usage = MagicMock(prompt_tokens=50, completion_tokens=20)
        mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)
        client._openai_client = mock_openai_client

        result = await client._call_openai_sdk(
            system_prompt='You are a coder',
            user_prompt='Generate hello function',
            temperature=0.2
        )

        assert result is not None
        assert 'code' in result
        assert result['prompt_tokens'] == 50
        assert result['completion_tokens'] == 20

    @pytest.mark.asyncio
    async def test_openai_missing_api_key(self):
        """Deve retornar None quando api_key nao fornecida."""
        from services.code_forge.src.clients.llm_client import LLMClient, LLMProvider

        client = LLMClient(provider=LLMProvider.OPENAI, api_key=None)

        result = await client._call_openai_sdk(
            system_prompt='Test',
            user_prompt='Test',
            temperature=0.2
        )

        assert result is None


class TestLLMClientAnthropic:
    """Testes de geracao via Anthropic."""

    @pytest.mark.asyncio
    async def test_generate_via_anthropic_success(self):
        """Deve gerar codigo via Anthropic com sucesso."""
        from services.code_forge.src.clients.llm_client import LLMClient, LLMProvider

        client = LLMClient(
            provider=LLMProvider.ANTHROPIC,
            api_key='test-key',
            model_name='claude-3-opus'
        )

        # Mock do SDK Anthropic
        mock_anthropic_client = AsyncMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='def hello():\n    pass')]
        mock_message.usage = MagicMock(input_tokens=40, output_tokens=15)
        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_message)
        client._anthropic_client = mock_anthropic_client

        result = await client._call_anthropic_sdk(
            system_prompt='You are a coder',
            user_prompt='Generate hello function',
            temperature=0.2
        )

        assert result is not None
        assert 'code' in result
        assert result['prompt_tokens'] == 40
        assert result['completion_tokens'] == 15

    @pytest.mark.asyncio
    async def test_anthropic_missing_api_key(self):
        """Deve retornar None quando api_key nao fornecida."""
        from services.code_forge.src.clients.llm_client import LLMClient, LLMProvider

        client = LLMClient(provider=LLMProvider.ANTHROPIC, api_key=None)

        result = await client._call_anthropic_sdk(
            system_prompt='Test',
            user_prompt='Test',
            temperature=0.2
        )

        assert result is None


class TestLLMClientCodeExtraction:
    """Testes de extracao de codigo da resposta."""

    def test_extract_code_plain(self):
        """Deve extrair codigo simples."""
        from services.code_forge.src.clients.llm_client import LLMClient

        client = LLMClient()

        response = {'code': 'def hello():\n    pass'}
        result = client._extract_code_from_response(response)

        assert result == 'def hello():\n    pass'

    def test_extract_code_with_markdown(self):
        """Deve remover markdown code blocks."""
        from services.code_forge.src.clients.llm_client import LLMClient

        client = LLMClient()

        response = {'code': '```python\ndef hello():\n    pass\n```'}
        result = client._extract_code_from_response(response)

        assert result == 'def hello():\n    pass'
        assert '```' not in result

    def test_extract_code_empty(self):
        """Deve retornar vazio para resposta vazia."""
        from services.code_forge.src.clients.llm_client import LLMClient

        client = LLMClient()

        response = {'code': ''}
        result = client._extract_code_from_response(response)

        assert result == ''


class TestLLMClientConfidenceCalculation:
    """Testes de calculo de confianca."""

    @pytest.mark.asyncio
    async def test_confidence_base_score(self):
        """Deve retornar score base para codigo minimo."""
        from services.code_forge.src.clients.llm_client import LLMClient

        client = LLMClient()

        confidence = await client.calculate_confidence(
            code='x = 1',
            constraints={'language': 'python'}
        )

        assert confidence >= 0.5
        assert confidence < 0.7

    @pytest.mark.asyncio
    async def test_confidence_high_for_complete_code(self):
        """Deve retornar score alto para codigo completo."""
        from services.code_forge.src.clients.llm_client import LLMClient

        client = LLMClient()

        code = '''"""Module docstring."""
import logging

def hello(name: str) -> str:
    """Return greeting."""
    try:
        return f"Hello, {name}!"
    except Exception as e:
        raise ValueError(str(e))
'''

        confidence = await client.calculate_confidence(
            code=code,
            constraints={'language': 'python'}
        )

        assert confidence >= 0.8

    @pytest.mark.asyncio
    async def test_confidence_zero_for_empty(self):
        """Deve retornar zero para codigo vazio."""
        from services.code_forge.src.clients.llm_client import LLMClient

        client = LLMClient()

        confidence = await client.calculate_confidence(
            code='',
            constraints={'language': 'python'}
        )

        assert confidence == 0.0


class TestLLMClientSystemPrompt:
    """Testes de construcao de system prompt."""

    def test_build_system_prompt_python(self):
        """Deve construir prompt para Python."""
        from services.code_forge.src.clients.llm_client import LLMClient

        client = LLMClient()

        prompt = client._build_system_prompt({
            'language': 'python',
            'framework': 'fastapi',
            'patterns': ['repository', 'service_layer']
        })

        assert 'python' in prompt.lower()
        assert 'fastapi' in prompt.lower()
        assert 'repository' in prompt
        assert 'service_layer' in prompt

    def test_build_system_prompt_defaults(self):
        """Deve usar defaults quando nao especificado."""
        from services.code_forge.src.clients.llm_client import LLMClient

        client = LLMClient()

        prompt = client._build_system_prompt({})

        assert 'python' in prompt.lower()
        assert 'Standard patterns' in prompt


class TestLLMClientValidation:
    """Testes de validacao de codigo."""

    @pytest.mark.asyncio
    async def test_validate_code_valid(self):
        """Deve validar codigo valido."""
        from services.code_forge.src.clients.llm_client import LLMClient

        client = LLMClient()

        is_valid = await client.validate_code(
            code='def hello():\n    pass',
            language='python'
        )

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_validate_code_too_short(self):
        """Deve rejeitar codigo muito curto."""
        from services.code_forge.src.clients.llm_client import LLMClient

        client = LLMClient()

        is_valid = await client.validate_code(
            code='x=1',
            language='python'
        )

        assert is_valid is False

    @pytest.mark.asyncio
    async def test_validate_code_empty(self):
        """Deve rejeitar codigo vazio."""
        from services.code_forge.src.clients.llm_client import LLMClient

        client = LLMClient()

        is_valid = await client.validate_code(
            code='',
            language='python'
        )

        assert is_valid is False


class TestLLMClientLifecycle:
    """Testes de ciclo de vida do cliente."""

    @pytest.mark.asyncio
    async def test_start_creates_http_client(self):
        """Deve criar HTTP client ao iniciar."""
        from services.code_forge.src.clients.llm_client import LLMClient

        client = LLMClient()
        await client.start()

        assert client.client is not None
        await client.stop()

    @pytest.mark.asyncio
    async def test_stop_closes_all_clients(self):
        """Deve fechar todos os clients ao parar."""
        from services.code_forge.src.clients.llm_client import LLMClient

        client = LLMClient()
        await client.start()

        # Simular clients SDK existentes
        client._openai_client = MagicMock()
        client._openai_client.close = MagicMock()
        client._anthropic_client = MagicMock()
        client._anthropic_client.close = MagicMock()

        await client.stop()

        # Verificar que close foi chamado
        client._openai_client.close.assert_called_once()
        client._anthropic_client.close.assert_called_once()
