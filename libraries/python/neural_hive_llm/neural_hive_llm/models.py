"""Modelos Pydantic para clientes LLM.

Define modelos de dados para requisições e respostas LLM,
além de enums para provedores e tipos de operação.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class LLMProvider(str, Enum):
    """Provedores LLM suportados."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


class LLMOperationType(str, Enum):
    """Tipos de operação LLM."""

    GENERATE = "generate"
    STREAM = "stream"
    BATCH = "batch"


class LLMRequest(BaseModel):
    """Modelo de requisição para geração LLM.

    Attributes:
        prompt: Prompt principal para o modelo
        system_prompt: Prompt de sistema (opcional)
        temperature: Temperatura de amostragem (0.0-1.0)
        max_tokens: Número máximo de tokens na resposta
        top_p: Nucleus sampling parameter
        frequency_penalty: Penalidade por frequência
        presence_penalty: Penalidade por presença
        stop: Sequências de parada
        stream: Habilita streaming de resposta
    """

    prompt: str = Field(..., description="Prompt principal para geração")
    system_prompt: Optional[str] = Field(None, description="Prompt de sistema")
    temperature: float = Field(0.7, ge=0.0, le=1.0, description="Temperatura de amostragem")
    max_tokens: int = Field(1024, ge=1, description="Máximo de tokens na resposta")
    top_p: float = Field(1.0, ge=0.0, le=1.0, description="Nucleus sampling")
    frequency_penalty: float = Field(0.0, ge=-2.0, le=2.0, description="Penalidade de frequência")
    presence_penalty: float = Field(0.0, ge=-2.0, le=2.0, description="Penalidade de presença")
    stop: Optional[list[str]] = Field(None, description="Sequências de parada")
    stream: bool = Field(False, description="Habilitar streaming")


class LLMResponse(BaseModel):
    """Modelo de resposta de geração LLM.

    Attributes:
        text: Texto gerado pelo modelo
        prompt_tokens: Tokens utilizados no prompt
        completion_tokens: Tokens gerados na resposta
        total_tokens: Total de tokens utilizados
        estimated_cost_usd: Custo estimado em USD
        latency_ms: Latência da requisição em ms
        model: Modelo utilizado
        provider: Provedor utilizado
        finish_reason: Motivo de término (length, stop, etc)
        metadata: Metadados adicionais
    """

    text: str = Field(..., description="Texto gerado pelo modelo")
    prompt_tokens: int = Field(0, description="Tokens de entrada")
    completion_tokens: int = Field(0, description="Tokens de saída")
    total_tokens: int = Field(0, description="Total de tokens")
    estimated_cost_usd: float = Field(0.0, description="Custo estimado em USD")
    latency_ms: float = Field(0.0, description="Latência em milissegundos")
    model: str = Field(..., description="Modelo utilizado")
    provider: LLMProvider = Field(..., description="Provedor utilizado")
    finish_reason: Optional[str] = Field(None, description="Motivo de término")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")

    @classmethod
    def from_provider_response(
        cls,
        text: str,
        model: str,
        provider: LLMProvider,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: float = 0.0,
        finish_reason: str | None = None,
        cost_usd: float = 0.0,
        **metadata,
    ) -> "LLMResponse":
        """Cria resposta a partir de resposta do provedor.

        Args:
            text: Texto gerado
            model: Nome do modelo
            provider: Provedor LLM
            prompt_tokens: Tokens de entrada
            completion_tokens: Tokens de saída
            latency_ms: Latência em ms
            finish_reason: Motivo de término
            cost_usd: Custo em USD
            **metadata: Metadados adicionais

        Returns:
            Instância de LLMResponse
        """
        return cls(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            estimated_cost_usd=cost_usd,
            latency_ms=latency_ms,
            model=model,
            provider=provider,
            finish_reason=finish_reason,
            metadata=metadata,
        )


class LLMStreamChunk(BaseModel):
    """Chunk de resposta durante streaming.

    Attributes:
        text: Texto parcial do chunk
        delta: Texto delta (apenas o novo texto)
        is_final: Se é o último chunk
        finish_reason: Motivo de término (se is_final)
    """

    text: str = Field(..., description="Texto acumulado até agora")
    delta: str = Field(..., description="Novo texto neste chunk")
    is_final: bool = Field(False, description="Se é o chunk final")
    finish_reason: Optional[str] = Field(None, description="Motivo de término")


class LLMMessage(BaseModel):
    """Mensagem em formato de chat.

    Attributes:
        role: Papel da mensagem (system, user, assistant)
        content: Conteúdo da mensagem
    """

    role: str = Field(..., description="Papel: system, user, assistant")
    content: str = Field(..., description="Conteúdo da mensagem")


@dataclass
class LLMConfig:
    """Configuração para cliente LLM.

    Attributes:
        provider: Provedor LLM
        api_key: Chave de API (para provedores externos)
        model: Nome do modelo
        endpoint_url: URL do endpoint (para provedores locais)
        timeout: Timeout de requisição em segundos
        max_retries: Número máximo de retries
        enable_circuit_breaker: Habilitar circuit breaker
        enable_tracing: Habilitar tracing distribuído
    """

    provider: LLMProvider
    api_key: str | None = None
    model: str = "gpt-4"
    endpoint_url: str | None = None
    timeout: float = 60.0
    max_retries: int = 3
    enable_circuit_breaker: bool = True
    enable_tracing: bool = True


__all__ = [
    "LLMProvider",
    "LLMOperationType",
    "LLMRequest",
    "LLMResponse",
    "LLMStreamChunk",
    "LLMMessage",
    "LLMConfig",
]
