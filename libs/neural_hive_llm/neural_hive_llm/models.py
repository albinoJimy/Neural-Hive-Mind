"""
Modelos Pydantic para neural_hive_llm.

Define os modelos de dados usados em toda a biblioteca, incluindo:
- Enums para providers e modelos
- Modelos de request/response
- Modelo para streaming chunks
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class LLMProvider(str, Enum):
    """Provider de LLM suportado."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"  # Ollama ou outro endpoint local


class LLMModel(str, Enum):
    """Modelos pré-configurados por provider."""

    # OpenAI
    GPT4 = "gpt-4"
    GPT4_TURBO = "gpt-4-turbo-preview"
    GPT35_TURBO = "gpt-3.5-turbo"

    # Anthropic
    CLAUDE_3_OPUS = "claude-3-opus-20240229"
    CLAUDE_3_SONNET = "claude-3-sonnet-20240229"
    CLAUDE_3_HAIKU = "claude-3-haiku-20240307"

    # Local/Ollama (exemplos)
    LLAMA2 = "llama2"
    MISTRAL = "mistral"
    NEURAL_CHAT = "neural-chat"


class LLMRequest(BaseModel):
    """Modelo para requisição de geração."""

    prompt: str = Field(..., description="Prompt principal do usuário")
    system_prompt: Optional[str] = Field(
        default=None, description="Prompt de sistema (contexto/role)"
    )
    temperature: float = Field(
        default=0.7, ge=0.0, le=2.0, description="Temperatura de amostragem (0-2)"
    )
    max_tokens: Optional[int] = Field(
        default=None, ge=1, description="Máximo de tokens a gerar"
    )
    top_p: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Nucleus sampling parameter"
    )
    frequency_penalty: float = Field(
        default=0.0, ge=-2.0, le=2.0, description="Penalidade de frequência"
    )
    presence_penalty: float = Field(
        default=0.0, ge=-2.0, le=2.0, description="Penalidade de presença"
    )
    stop_sequences: Optional[list[str]] = Field(
        default=None, description="Sequências que param a geração"
    )
    metadata: Optional[dict] = Field(
        default=None, description="Metadados adicionais para tracing/logging"
    )

    @field_validator("prompt")
    @classmethod
    def validate_prompt_not_empty(cls, v: str) -> str:
        """Valida que o prompt não está vazio."""
        if not v or not v.strip():
            raise ValueError("prompt não pode estar vazio")
        return v.strip()


class LLMResponse(BaseModel):
    """Modelo para resposta de geração."""

    text: str = Field(..., description="Texto gerado pelo LLM")
    prompt_tokens: int = Field(..., ge=0, description="Tokens do prompt")
    completion_tokens: int = Field(..., ge=0, description="Tokens da resposta")
    total_tokens: int = Field(..., ge=0, description="Total de tokens")
    model: str = Field(..., description="Modelo utilizado")
    provider: LLMProvider = Field(..., description="Provider utilizado")
    finish_reason: Optional[str] = Field(
        default=None, description="Motivo de término (stop, length, etc)"
    )
    estimated_cost_usd: float = Field(
        default=0.0, ge=0, description="Custo estimado em USD"
    )
    latency_ms: float = Field(..., ge=0, description="Latência em milissegundos")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp da resposta"
    )
    raw_response: Optional[dict] = Field(
        default=None, description="Resposta bruta do provider (para debug)"
    )
    metadata: Optional[dict] = Field(
        default=None, description="Metadados adicionais"
    )

    @property
    def tokens_per_second(self) -> float:
        """Calcula tokens gerados por segundo."""
        if self.latency_ms > 0:
            return (self.completion_tokens / self.latency_ms) * 1000
        return 0.0


class LLMStreamChunk(BaseModel):
    """Modelo para chunk de streaming."""

    delta: str = Field(..., description="Texto incremental do chunk")
    finish_reason: Optional[str] = Field(
        default=None, description="Motivo de término (None enquanto streaming)"
    )
    is_complete: bool = Field(
        default=False, description="True se este é o último chunk"
    )
    prompt_tokens: Optional[int] = Field(
        default=None, description="Tokens do prompt (disponível no primeiro chunk)"
    )


class TokenUsage(BaseModel):
    """Modelo para uso de tokens."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Calcula total de tokens."""
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        """Soma dois usos de tokens."""
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
        )

    def __repr__(self) -> str:
        """Representação string."""
        return f"TokenUsage(prompt={self.prompt_tokens}, completion={self.completion_tokens}, total={self.total_tokens})"
