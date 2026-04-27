"""Classe base (ABC) para provedores LLM.

Define a interface que todos os provedores devem implementar,
garantindo consistência entre diferentes implementações.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from neural_hive_llm.models import LLMResponse, LLMStreamChunk


class BaseProvider(ABC):
    """Classe abstrata base para provedores LLM.

    Todos os provedores devem herdar desta classe e implementar
    os métodos abstratos definidos abaixo.
    """

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """Inicializa provedor LLM.

        Args:
            model: Nome do modelo
            api_key: Chave de API (para provedores externos)
            endpoint_url: URL do endpoint (para provedores locais)
            timeout: Timeout de requisição em segundos
        """
        self.model = model
        self.api_key = api_key
        self.endpoint_url = endpoint_url
        self.timeout = timeout

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs,
    ) -> LLMResponse:
        """Gera texto usando o provedor LLM.

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema (opcional)
            temperature: Temperatura de amostragem (0.0-1.0)
            max_tokens: Número máximo de tokens
            **kwargs: Parâmetros adicionais específicos do provedor

        Returns:
            LLMResponse com texto gerado e metadados
        """

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Gera texto com streaming.

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema (opcional)
            temperature: Temperatura de amostragem
            max_tokens: Número máximo de tokens
            **kwargs: Parâmetros adicionais

        Yields:
            LLMStreamChunk com texto parcial
        """

    @abstractmethod
    async def healthcheck(self) -> bool:
        """Verifica saúde da conexão com provedor.

        Returns:
            True se conexão está saudável, False caso contrário
        """

    async def start(self):
        """Inicializa conexão com provedor.

        Método opcional para setup lazy de recursos.
        """
        pass

    async def stop(self):
        """Fecha conexão e limpa recursos.

        Método opcional para cleanup.
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model})"


__all__ = ["BaseProvider"]
