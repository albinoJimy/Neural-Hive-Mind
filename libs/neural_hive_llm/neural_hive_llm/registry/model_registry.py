"""
Model Registry - Catálogo central de modelos LLM.

Registra modelos com metadata sobre capacidades, custos e benchmarks.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """Tipos de tarefas suportadas."""

    TEXT_GENERATION = "text_generation"
    CODE_GENERATION = "code_generation"
    ANALYSIS = "analysis"
    SUMMARIZATION = "summarization"
    RAG = "rag"
    TRANSLATION = "translation"
    CHAT = "chat"
    TOOL_USE = "tool_use"
    EMBEDDING = "embedding"


class Priority(str, Enum):
    """Prioridade de seleção."""

    PERFORMANCE = "performance"
    COST = "cost"
    BALANCED = "balanced"
    QUALITY = "quality"


class ModelCapabilities(BaseModel):
    """Capacidades do modelo."""

    max_context_tokens: int = Field(..., description="Máximo de tokens de contexto")
    supports_streaming: bool = Field(default=True)
    supports_function_calling: bool = Field(default=False)
    supports_vision: bool = Field(default=False)
    supports_embedding: bool = Field(default=False)
    supports_system_messages: bool = Field(default=True)
    output_modalities: list[str] = Field(default_factory=lambda: ["text"])
    input_modalities: list[str] = Field(default_factory=lambda: ["text"])
    benchmark_quality_score: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Score de qualidade (0-1)"
    )


class ModelPricing(BaseModel):
    """Estrutura de preços do modelo."""

    input_price_per_1k_usd: float = Field(..., ge=0, description="Preço input por 1k tokens")
    output_price_per_1k_usd: float = Field(..., ge=0, description="Preço output por 1k tokens")
    currency: str = Field(default="USD")


class ModelPerformance(BaseModel):
    """Métricas de performance do modelo."""

    avg_latency_ms: float = Field(default=0.0, ge=0, description="Latência média")
    p50_latency_ms: float = Field(default=0.0, ge=0)
    p95_latency_ms: float = Field(default=0.0, ge=0)
    p99_latency_ms: float = Field(default=0.0, ge=0)
    avg_tokens_per_second: float = Field(default=0.0, ge=0)
    success_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    total_requests: int = Field(default=0, ge=0)


class ModelMetadata(BaseModel):
    """Metadados do modelo no registry."""

    model_id: str = Field(..., description="ID único do modelo")
    provider: str = Field(..., description="Provider (openai, anthropic, local)")
    display_name: str = Field(..., description="Nome para exibição")
    api_name: str = Field(..., description="Nome usado na API")
    capabilities: ModelCapabilities = Field(..., description="Capacidades do modelo")
    pricing: ModelPricing = Field(..., description="Preços")
    supported_tasks: list[TaskType] = Field(..., description="Tarefas suportadas")
    is_available: bool = Field(default=True, description="Se o modelo está disponível")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class ModelRegistry:
    """
    Registry central de modelos LLM.

    Armazena metadata de todos os modelos disponíveis e fornece
    métodos para filtrar e selecionar modelos baseado em critérios.
    """

    def __init__(self) -> None:
        """Inicializa o registry."""
        self._models: dict[str, ModelMetadata] = {}
        self._provider_index: dict[str, list[str]] = {}
        self._task_index: dict[TaskType, list[str]] = {}
        self._initialize_default_models()

    def _initialize_default_models(self) -> None:
        """Inicializa modelos padrão."""

        from neural_hive_llm.models import LLMProvider

        # OpenAI Models
        self.register_model(
            ModelMetadata(
                model_id="openai-gpt-4-turbo",
                provider=LLMProvider.OPENAI.value,
                display_name="GPT-4 Turbo",
                api_name="gpt-4-turbo-preview",
                capabilities=ModelCapabilities(
                    max_context_tokens=128000,
                    supports_streaming=True,
                    supports_function_calling=True,
                    supports_vision=True,
                    benchmark_quality_score=0.95,
                ),
                pricing=ModelPricing(input_price_per_1k_usd=0.01, output_price_per_1k_usd=0.03),
                supported_tasks=[
                    TaskType.TEXT_GENERATION,
                    TaskType.CODE_GENERATION,
                    TaskType.ANALYSIS,
                    TaskType.RAG,
                    TaskType.CHAT,
                    TaskType.TOOL_USE,
                ],
            )
        )

        self.register_model(
            ModelMetadata(
                model_id="openai-gpt-3.5-turbo",
                provider=LLMProvider.OPENAI.value,
                display_name="GPT-3.5 Turbo",
                api_name="gpt-3.5-turbo",
                capabilities=ModelCapabilities(
                    max_context_tokens=16385,
                    supports_streaming=True,
                    supports_function_calling=True,
                    benchmark_quality_score=0.85,
                ),
                pricing=ModelPricing(input_price_per_1k_usd=0.0005, output_price_per_1k_usd=0.0015),
                supported_tasks=[
                    TaskType.TEXT_GENERATION,
                    TaskType.CODE_GENERATION,
                    TaskType.CHAT,
                    TaskType.TOOL_USE,
                ],
            )
        )

        # Anthropic Models
        self.register_model(
            ModelMetadata(
                model_id="anthropic-claude-3-opus",
                provider=LLMProvider.ANTHROPIC.value,
                display_name="Claude 3 Opus",
                api_name="claude-3-opus-20240229",
                capabilities=ModelCapabilities(
                    max_context_tokens=200000,
                    supports_streaming=True,
                    supports_function_calling=True,
                    supports_vision=True,
                    benchmark_quality_score=0.98,
                ),
                pricing=ModelPricing(input_price_per_1k_usd=0.015, output_price_per_1k_usd=0.075),
                supported_tasks=[
                    TaskType.TEXT_GENERATION,
                    TaskType.CODE_GENERATION,
                    TaskType.ANALYSIS,
                    TaskType.SUMMARIZATION,
                    TaskType.RAG,
                    TaskType.CHAT,
                    TaskType.TOOL_USE,
                ],
            )
        )

        self.register_model(
            ModelMetadata(
                model_id="anthropic-claude-3-sonnet",
                provider=LLMProvider.ANTHROPIC.value,
                display_name="Claude 3 Sonnet",
                api_name="claude-3-sonnet-20240229",
                capabilities=ModelCapabilities(
                    max_context_tokens=200000,
                    supports_streaming=True,
                    supports_function_calling=True,
                    supports_vision=True,
                    benchmark_quality_score=0.92,
                ),
                pricing=ModelPricing(input_price_per_1k_usd=0.003, output_price_per_1k_usd=0.015),
                supported_tasks=[
                    TaskType.TEXT_GENERATION,
                    TaskType.CODE_GENERATION,
                    TaskType.ANALYSIS,
                    TaskType.SUMMARIZATION,
                    TaskType.RAG,
                    TaskType.CHAT,
                    TaskType.TOOL_USE,
                ],
            )
        )

        self.register_model(
            ModelMetadata(
                model_id="anthropic-claude-3-haiku",
                provider=LLMProvider.ANTHROPIC.value,
                display_name="Claude 3 Haiku",
                api_name="claude-3-haiku-20240307",
                capabilities=ModelCapabilities(
                    max_context_tokens=200000,
                    supports_streaming=True,
                    supports_function_calling=True,
                    supports_vision=True,
                    benchmark_quality_score=0.82,
                ),
                pricing=ModelPricing(
                    input_price_per_1k_usd=0.00025, output_price_per_1k_usd=0.00125
                ),
                supported_tasks=[
                    TaskType.TEXT_GENERATION,
                    TaskType.CHAT,
                    TaskType.TRANSLATION,
                ],
            )
        )

        # Local Models
        self.register_model(
            ModelMetadata(
                model_id="local-llama2",
                provider=LLMProvider.LOCAL.value,
                display_name="Llama 2",
                api_name="llama2",
                capabilities=ModelCapabilities(
                    max_context_tokens=4096,
                    supports_streaming=True,
                    supports_function_calling=False,
                    benchmark_quality_score=0.72,
                ),
                pricing=ModelPricing(input_price_per_1k_usd=0.0, output_price_per_1k_usd=0.0),
                supported_tasks=[
                    TaskType.TEXT_GENERATION,
                    TaskType.CHAT,
                ],
            )
        )

        self.register_model(
            ModelMetadata(
                model_id="local-mistral",
                provider=LLMProvider.LOCAL.value,
                display_name="Mistral",
                api_name="mistral",
                capabilities=ModelCapabilities(
                    max_context_tokens=8192,
                    supports_streaming=True,
                    supports_function_calling=False,
                    benchmark_quality_score=0.78,
                ),
                pricing=ModelPricing(input_price_per_1k_usd=0.0, output_price_per_1k_usd=0.0),
                supported_tasks=[
                    TaskType.TEXT_GENERATION,
                    TaskType.CODE_GENERATION,
                    TaskType.CHAT,
                ],
            )
        )

    def register_model(self, model: ModelMetadata) -> None:
        """
        Registra um novo modelo.

        Args:
            model: Metadados do modelo
        """
        self._models[model.model_id] = model
        model.last_updated = datetime.utcnow()

        # Atualiza índice de provider
        if model.provider not in self._provider_index:
            self._provider_index[model.provider] = []
        if model.model_id not in self._provider_index[model.provider]:
            self._provider_index[model.provider].append(model.model_id)

        # Atualiza índice de tasks
        for task in model.supported_tasks:
            if task not in self._task_index:
                self._task_index[task] = []
            if model.model_id not in self._task_index[task]:
                self._task_index[task].append(model.model_id)

    def get_model(self, model_id: str) -> Optional[ModelMetadata]:
        """
        Retorna metadados de um modelo.

        Args:
            model_id: ID do modelo

        Returns:
            ModelMetadata ou None se não encontrado
        """
        return self._models.get(model_id)

    def list_models(
        self,
        provider: Optional[str] = None,
        task: Optional[TaskType] = None,
        available_only: bool = True,
    ) -> list[ModelMetadata]:
        """
        Lista modelos baseado em filtros.

        Args:
            provider: Filtra por provider
            task: Filtra por tipo de tarefa
            available_only: Retorna apenas modelos disponíveis

        Returns:
            Lista de metadados de modelos
        """
        models = list(self._models.values())

        if provider:
            models = [m for m in models if m.provider == provider]

        if task:
            models = [m for m in models if task in m.supported_tasks]

        if available_only:
            models = [m for m in models if m.is_available]

        return models

    def update_model_availability(self, model_id: str, is_available: bool) -> None:
        """
        Atualiza disponibilidade de um modelo.

        Args:
            model_id: ID do modelo
            is_available: Nova disponibilidade
        """
        if model_id in self._models:
            self._models[model_id].is_available = is_available
            self._models[model_id].last_updated = datetime.utcnow()

    def get_models_for_task(
        self, task: TaskType, available_only: bool = True
    ) -> list[ModelMetadata]:
        """
        Retorna modelos que suportam uma tarefa específica.

        Args:
            task: Tipo de tarefa
            available_only: Apenas modelos disponíveis

        Returns:
            Lista de metadados de modelos
        """
        model_ids = self._task_index.get(task, [])
        models = [self._models[mid] for mid in model_ids if mid in self._models]

        if available_only:
            models = [m for m in models if m.is_available]

        return models


# Singleton global
_registry: Optional[ModelRegistry] = None


def get_registry() -> ModelRegistry:
    """
    Retorna o registry global (singleton).

    Returns:
        ModelRegistry: Instância global do registry
    """
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry


def reset_registry() -> None:
    """Reseta o registry (útil para testes)."""
    global _registry
    _registry = None
