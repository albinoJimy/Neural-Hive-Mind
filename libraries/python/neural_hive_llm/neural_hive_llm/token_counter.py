"""Contador de tokens e calculadora de custos para provedores LLM.

Implementa contagem de tokens e cálculo de custos para diferentes modelos
de OpenAI e Anthropic, com métricas Prometheus integradas.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional

import structlog
from prometheus_client import Counter

logger = structlog.get_logger()


class ModelProvider(str, Enum):
    """Provedores de modelos suportados."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


@dataclass(frozen=True)
class ModelPricing:
    """Preços por token para um modelo.

    Attributes:
        input_price: Preço por 1M tokens de entrada (USD)
        output_price: Preço por 1M tokens de saída (USD)
    """

    input_price: float
    output_price: float


# Tabela de preços (atualizada em 2025-01)
# Preços em USD por 1M tokens
MODEL_PRICING: Final[dict[str, tuple[ModelProvider, ModelPricing]]] = {
    # OpenAI Models
    "gpt-4o": (ModelProvider.OPENAI, ModelPricing(2.50, 10.00)),
    "gpt-4o-mini": (ModelProvider.OPENAI, ModelPricing(0.15, 0.60)),
    "gpt-4-turbo": (ModelProvider.OPENAI, ModelPricing(10.00, 30.00)),
    "gpt-4": (ModelProvider.OPENAI, ModelPricing(30.00, 60.00)),
    "gpt-3.5-turbo": (ModelProvider.OPENAI, ModelPricing(0.50, 1.50)),
    "o1-preview": (ModelProvider.OPENAI, ModelPricing(15.00, 60.00)),
    "o1-mini": (ModelProvider.OPENAI, ModelPricing(3.00, 12.00)),
    # Anthropic Models
    "claude-3-5-sonnet-20241022": (ModelProvider.ANTHROPIC, ModelPricing(3.00, 15.00)),
    "claude-3-5-sonnet-20240620": (ModelProvider.ANTHROPIC, ModelPricing(3.00, 15.00)),
    "claude-3-5-haiku-20241022": (ModelProvider.ANTHROPIC, ModelPricing(0.80, 4.00)),
    "claude-3-opus-20240229": (ModelProvider.ANTHROPIC, ModelPricing(15.00, 75.00)),
    "claude-3-sonnet-20240229": (ModelProvider.ANTHROPIC, ModelPricing(3.00, 15.00)),
    "claude-3-haiku-20240307": (ModelProvider.ANTHROPIC, ModelPricing(0.25, 1.25)),
}


# Métricas Prometheus - usar registry dedicado para evitar conflitos
from prometheus_client import CollectorRegistry

_llm_registry = CollectorRegistry()

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total de tokens consumidos por LLM",
    ["service", "provider", "model", "token_type"],  # token_type: input, output
    registry=_llm_registry,
)

llm_cost_usd_total = Counter(
    "llm_cost_usd_total",
    "Custo total acumulado em USD",
    ["service", "provider", "model"],
    registry=_llm_registry,
)

llm_requests_total = Counter(
    "llm_requests_total",
    "Total de requisições LLM",
    ["service", "provider", "model", "status"],
    registry=_llm_registry,
)


class TokenCounter:
    """Contador de tokens e calculadora de custos.

    Rastreia o uso de tokens e custos para diferentes modelos LLM,
    publicando métricas Prometheus.

    Attributes:
        service_name: Nome do serviço para labels de métricas
    """

    def __init__(self, service_name: str = "neural_hive_llm"):
        """Inicializa contador de tokens.

        Args:
            service_name: Nome do serviço para métricas
        """
        self.service_name = service_name
        self.logger = structlog.get_logger().bind(service=service_name)

    def get_pricing(self, model: str) -> Optional[ModelPricing]:
        """Retorna precificação para um modelo.

        Args:
            model: Nome do modelo (ex: 'gpt-4o', 'claude-3-5-sonnet-20241022')

        Returns:
            ModelPricing se encontrado, None caso contrário
        """
        if model in MODEL_PRICING:
            return MODEL_PRICING[model][1]

        # Tentar match parcial para OpenAI
        if model.startswith("gpt-"):
            # Assumir preços do gpt-4o para modelos desconhecidos
            self.logger.warning("unknown_gpt_model_using_default_pricing", model=model)
            return MODEL_PRICING["gpt-4o"][1]

        # Tentar match parcial para Anthropic
        if "claude" in model:
            # Assumir preços do sonnet para modelos desconhecidos
            self.logger.warning("unknown_claude_model_using_default_pricing", model=model)
            return MODEL_PRICING["claude-3-5-sonnet-20241022"][1]

        self.logger.warning("unknown_model_no_pricing", model=model)
        return None

    def calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> tuple[float, Optional[ModelProvider]]:
        """Calcula custo em USD para uma requisição.

        Args:
            model: Nome do modelo
            input_tokens: Número de tokens de entrada
            output_tokens: Número de tokens de saída

        Returns:
            Tupla (custo_usd, provider) ou (0.0, None) se modelo desconhecido
        """
        pricing = self.get_pricing(model)
        if not pricing:
            return 0.0, None

        provider = None
        for m, (p, pr) in MODEL_PRICING.items():
            if m == model:
                provider = p
                break

        # Preços são por 1M tokens
        input_cost = (input_tokens / 1_000_000) * pricing.input_price
        output_cost = (output_tokens / 1_000_000) * pricing.output_price
        total_cost = input_cost + output_cost

        return total_cost, provider

    def record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        status: str = "success",
    ) -> dict[str, float]:
        """Registra uso de tokens e custos, atualizando métricas.

        Args:
            model: Nome do modelo
            input_tokens: Tokens de entrada
            output_tokens: Tokens de saída
            status: Status da requisição (success, error, timeout)

        Returns:
            Dict com total_tokens, total_cost_usd, provider
        """
        total_tokens = input_tokens + output_tokens
        cost_usd, provider = self.calculate_cost(model, input_tokens, output_tokens)

        # Publicar métricas de tokens
        if provider:
            llm_tokens_total.labels(
                service=self.service_name,
                provider=provider.value,
                model=model,
                token_type="input",
            ).inc(input_tokens)

            llm_tokens_total.labels(
                service=self.service_name,
                provider=provider.value,
                model=model,
                token_type="output",
            ).inc(output_tokens)

            # Publicar métrica de custo
            llm_cost_usd_total.labels(
                service=self.service_name,
                provider=provider.value,
                model=model,
            ).inc(cost_usd)

        # Publicar métrica de requisições
        llm_requests_total.labels(
            service=self.service_name,
            provider=provider.value if provider else "unknown",
            model=model,
            status=status,
        ).inc()

        self.logger.debug(
            "llm_usage_recorded",
            model=model,
            provider=provider.value if provider else "unknown",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=round(cost_usd, 6),
        )

        return {
            "total_tokens": total_tokens,
            "total_cost_usd": round(cost_usd, 6),
            "provider": provider.value if provider else "unknown",
        }

    def estimate_tokens(self, text: str, model: str) -> int:
        """Estima número de tokens para um texto.

        Esta é uma estimativa grosseira baseada em caracteres.
        Para contagem exata, use o tokenizer do SDK do provedor.

        Args:
            text: Texto para estimar
            model: Nome do modelo

        Returns:
            Estativa de número de tokens
        """
        # Estimativa conservadora: ~4 caracteres por token
        return len(text) // 4


# Instância global
_global_counter: Optional[TokenCounter] = None


def get_token_counter(service_name: str = "neural_hive_llm") -> TokenCounter:
    """Retorna instância global de TokenCounter.

    Args:
        service_name: Nome do serviço (usado apenas na primeira chamada)

    Returns:
        Instância de TokenCounter
    """
    global _global_counter
    if _global_counter is None:
        _global_counter = TokenCounter(service_name=service_name)
    return _global_counter


def reset_global_counter():
    """Reseta instância global de contador (útil para testes)."""
    global _global_counter
    _global_counter = None


__all__ = [
    "ModelProvider",
    "ModelPricing",
    "MODEL_PRICING",
    "TokenCounter",
    "get_token_counter",
    "reset_global_counter",
    "llm_tokens_total",
    "llm_cost_usd_total",
    "llm_requests_total",
]
