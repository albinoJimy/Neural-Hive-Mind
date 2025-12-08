"""LLM client for code generation (OpenAI, Anthropic, local models)."""
import json
from enum import Enum
import inspect
from typing import AsyncGenerator, Dict, List, Optional

import httpx
import structlog
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

logger = structlog.get_logger()


def _is_transient_error(exc: Exception) -> bool:
    """Define quais exceções são consideradas transitórias para retry."""
    transient_names = {"RateLimitError"}
    if isinstance(exc, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError)):
        return True
    if exc.__class__.__name__ in transient_names:
        return True
    return False


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


class LLMClient:
    """Client for LLM-based code generation."""

    def __init__(
        self,
        provider: LLMProvider = LLMProvider.LOCAL,
        api_key: Optional[str] = None,
        model_name: str = "gpt-4",
        endpoint_url: Optional[str] = None,
    ):
        """Initialize LLM client."""
        self.provider = provider
        self.api_key = api_key
        self.model_name = model_name
        self.endpoint_url = endpoint_url or self._get_default_endpoint(provider)
        self.client: Optional[httpx.AsyncClient] = None

    def _get_default_endpoint(self, provider: LLMProvider) -> str:
        """Get default endpoint for provider."""
        if provider == LLMProvider.OPENAI:
            return "https://api.openai.com/v1"
        elif provider == LLMProvider.ANTHROPIC:
            return "https://api.anthropic.com/v1"
        else:  # LOCAL
            return "http://ollama:11434/api"

    async def start(self):
        """Initialize HTTP client."""
        headers = {}
        if self.api_key and self.provider != LLMProvider.LOCAL:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = httpx.AsyncClient(base_url=self.endpoint_url, headers=headers, timeout=60.0)
        logger.info("llm_client_initialized", provider=self.provider, model=self.model_name)

    async def stop(self):
        """Close HTTP client."""
        if self.client:
            await self.client.aclose()

        # Cleanup OpenAI client
        if hasattr(self, "_openai_client"):
            close_fn = getattr(self._openai_client, "close", None)
            if callable(close_fn):
                maybe_coro = close_fn()
                if inspect.isawaitable(maybe_coro):
                    await maybe_coro

        # Cleanup Anthropic client
        if hasattr(self, "_anthropic_client"):
            close_fn = getattr(self._anthropic_client, "close", None)
            if callable(close_fn):
                maybe_coro = close_fn()
                if inspect.isawaitable(maybe_coro):
                    await maybe_coro

        logger.info("llm_client_stopped", provider=self.provider)

    async def generate_code(
        self, prompt: str, constraints: Dict, temperature: float = 0.2, stream: bool = False
    ) -> Optional[Dict]:
        """Generate code using LLM.

        Args:
            prompt: Prompt for code generation
            constraints: Dict with language, framework, patterns, max_lines
            temperature: Sampling temperature (0.0-1.0)
            stream: Enable streaming responses when supported

        Returns:
            Dict with 'code', 'confidence_score', 'explanation'
        """
        try:
            # Build system prompt
            system_prompt = self._build_system_prompt(constraints)

            # Call LLM based on provider
            if self.provider == LLMProvider.LOCAL:
                if stream:
                    logger.warning("streaming_not_supported_local_provider")
                response = await self._call_ollama(system_prompt, prompt, temperature)
            elif self.provider == LLMProvider.OPENAI:
                response = await self._call_openai_sdk(
                    system_prompt, prompt, temperature, stream=stream
                )
            elif self.provider == LLMProvider.ANTHROPIC:
                response = await self._call_anthropic_sdk(
                    system_prompt, prompt, temperature, stream=stream
                )
            else:
                logger.error("unsupported_llm_provider", provider=self.provider)
                return None

            if not response:
                return None

            # Parse and validate response
            code = self._extract_code_from_response(response)

            # Calcular confiança usando método público
            confidence = await self.calculate_confidence(code, constraints)

            logger.info(
                "llm_code_generated",
                provider=self.provider,
                confidence=confidence,
                code_length=len(code),
            )

            return {
                "code": code,
                "confidence_score": confidence,
                "explanation": response.get("explanation", ""),
                "prompt_tokens": response.get("prompt_tokens", 0),
                "completion_tokens": response.get("completion_tokens", 0),
            }

        except Exception as e:
            logger.error("llm_generation_failed", error=str(e))
            return None

    def _build_system_prompt(self, constraints: Dict) -> str:
        """Build system prompt with constraints."""
        language = constraints.get("language", "python")
        framework = constraints.get("framework", "")
        patterns = constraints.get("patterns", [])

        prompt = f"""You are an expert software engineer specializing in {language}.
Generate production-ready, well-structured code following best practices.

Constraints:
- Language: {language}
- Framework: {framework if framework else 'None'}
- Patterns: {', '.join(patterns) if patterns else 'Standard patterns'}
- Include docstrings and type hints
- Handle errors appropriately
- Follow PEP-8 (Python) or equivalent style guides

Return ONLY valid code without markdown formatting or explanations unless requested."""

        return prompt

    async def _call_ollama(self, system_prompt: str, user_prompt: str, temperature: float) -> Optional[Dict]:
        """Call Ollama local LLM."""
        try:
            payload = {
                "model": self.model_name,
                "prompt": f"{system_prompt}\n\n{user_prompt}",
                "stream": False,
                "options": {"temperature": temperature},
            }

            response = await self.client.post("/generate", json=payload)
            response.raise_for_status()

            result = response.json()
            return {
                "code": result.get("response", ""),
                "prompt_tokens": 0,  # Ollama doesn't return token counts
                "completion_tokens": 0,
            }

        except httpx.HTTPError as e:
            logger.error("ollama_call_failed", error=str(e))
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_transient_error),
    )
    async def _call_openai_sdk(
        self, system_prompt: str, user_prompt: str, temperature: float, stream: bool = False
    ) -> Optional[Dict]:
        """Call OpenAI API using official SDK with retry logic."""
        try:
            # Lazy import para evitar erro se SDK não instalado
            from openai import APIError, AsyncOpenAI, RateLimitError

            if not self.api_key:
                logger.error("openai_api_key_missing")
                return None

            # Criar cliente (reutilizar se já existe)
            if not hasattr(self, "_openai_client"):
                self._openai_client = AsyncOpenAI(api_key=self.api_key)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            if stream:
                # Streaming mode
                response_text = ""
                stream_iterator = await self._openai_client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                    stream=True,
                )
                async for chunk in stream_iterator:
                    if chunk.choices[0].delta.content:
                        response_text += chunk.choices[0].delta.content

                return {
                    "code": response_text,
                    "prompt_tokens": 0,  # Não disponível em streaming
                    "completion_tokens": 0,
                }
            else:
                # Non-streaming mode
                response = await self._openai_client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                )

                return {
                    "code": response.choices[0].message.content,
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                }

        except RateLimitError as e:
            logger.warning("openai_rate_limit", error=str(e))
            raise  # Retry via tenacity
        except APIError as e:
            logger.error("openai_api_error", error=str(e))
            return None
        except ImportError:
            logger.error("openai_sdk_not_installed", message="Install with: pip install openai")
            return None
        except Exception as e:
            logger.error("openai_call_failed", error=str(e))
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_transient_error),
    )
    async def _call_anthropic_sdk(
        self, system_prompt: str, user_prompt: str, temperature: float, stream: bool = False
    ) -> Optional[Dict]:
        """Call Anthropic API using official SDK with retry logic."""
        try:
            # Lazy import
            from anthropic import APIError, AsyncAnthropic, RateLimitError

            if not self.api_key:
                logger.error("anthropic_api_key_missing")
                return None

            # Criar cliente (reutilizar se já existe)
            if not hasattr(self, "_anthropic_client"):
                self._anthropic_client = AsyncAnthropic(api_key=self.api_key)

            # Anthropic usa system prompt como parâmetro separado
            if stream:
                # Streaming mode
                response_text = ""
                async with self._anthropic_client.messages.stream(
                    model=self.model_name,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=temperature,
                ) as stream_iterator:
                    async for text in stream_iterator.text_stream:
                        response_text += text

                return {
                    "code": response_text,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                }
            else:
                # Non-streaming mode
                message = await self._anthropic_client.messages.create(
                    model=self.model_name,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=temperature,
                )

                return {
                    "code": message.content[0].text,
                    "prompt_tokens": message.usage.input_tokens,
                    "completion_tokens": message.usage.output_tokens,
                }

        except RateLimitError as e:
            logger.warning("anthropic_rate_limit", error=str(e))
            raise  # Retry via tenacity
        except APIError as e:
            logger.error("anthropic_api_error", error=str(e))
            return None
        except ImportError:
            logger.error(
                "anthropic_sdk_not_installed", message="Install with: pip install anthropic"
            )
            return None
        except Exception as e:
            logger.error("anthropic_call_failed", error=str(e))
            return None

    def _extract_code_from_response(self, response: Dict) -> str:
        """Extract code from LLM response."""
        code = response.get("code", "")

        # Remove markdown code blocks if present
        if "```" in code:
            # Extract content between first ``` and last ```
            parts = code.split("```")
            if len(parts) >= 3:
                code = parts[1]
                # Remove language identifier (e.g., "python\n")
                if "\n" in code:
                    code = code.split("\n", 1)[1]

        return code.strip()

    def _calculate_confidence(self, code: str, constraints: Dict) -> float:
        """Calculate confidence score based on validations."""
        if not code:
            return 0.0

        confidence = 0.5  # Base confidence

        # Check if code is non-trivial
        if len(code) > 100:
            confidence += 0.1

        # Check for docstrings/comments
        if '"""' in code or "#" in code:
            confidence += 0.1

        # Check for type hints (Python)
        if constraints.get("language") == "python" and "->" in code:
            confidence += 0.1

        # Check for error handling
        if "try" in code or "except" in code or "raise" in code:
            confidence += 0.1

        # Check for imports/dependencies
        if "import" in code or "from" in code:
            confidence += 0.1

        return min(confidence, 1.0)

    async def validate_code(self, code: str, language: str) -> bool:
        """Validate code syntax (simplified)."""
        # Full implementation would use language-specific parsers
        # For Python: compile(code, '<string>', 'exec')
        return bool(code and len(code) > 10)

    async def calculate_confidence(self, code: str, constraints: Dict) -> float:
        """
        Calcula confiança final do código gerado.

        API pública recomendada para calcular confiança baseado em heurísticas
        internas e constraints fornecidas.

        Args:
            code: Código gerado
            constraints: Dict com language, framework, patterns, max_lines

        Returns:
            Score de confiança (0.0-1.0)
        """
        return self._calculate_confidence(code, constraints)
