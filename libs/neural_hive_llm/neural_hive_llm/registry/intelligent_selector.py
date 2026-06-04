"""
Intelligent Selector - Motor de decisão para seleção de LLM.

Algoritmo que selecciona o melhor provider/modelo baseado em:
- Performance histórica (latência, sucesso rate)
- Custo (input/output por token)
- Qualidade do modelo (benchmarks)
- Prioridade configurável (performance vs cost)
- Capacidades necessárias (contexto, tools, etc)
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from neural_hive_llm.registry.model_registry import (
    ModelMetadata,
    ModelRegistry,
    TaskType,
    get_registry,
)
from neural_hive_llm.registry.performance_tracker import (
    PerformanceTracker,
    get_tracker,
)


class SelectionCriteria(str, Enum):
    """Critérios de seleção."""

    FASTEST = "fastest"
    CHEAPEST = "cheapest"
    BALANCED = "balanced"
    HIGHEST_QUALITY = "highest_quality"
    CUSTOM = "custom"


@dataclass
class SelectionWeights:
    """Pesos para algoritmo de seleção customizado."""

    performance_weight: float = 0.4
    cost_weight: float = 0.4
    quality_weight: float = 0.2

    def validate(self) -> None:
        """Valida que soma dos pesos é 1.0."""
        total = self.performance_weight + self.cost_weight + self.quality_weight
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Soma dos pesos deve ser 1.0, atual: {total}")


@dataclass
class SelectionContext:
    """Contexto para seleção de modelo."""

    task_type: TaskType
    expected_input_tokens: int
    expected_output_tokens: int
    requires_streaming: bool = False
    requires_function_calling: bool = False
    requires_vision: bool = False
    max_latency_ms: Optional[float] = None
    max_cost_usd: Optional[float] = None
    min_quality_score: Optional[float] = None


@dataclass
class SelectionResult:
    """Resultado da seleção."""

    model_id: str
    provider: str
    api_name: str
    score: float
    selection_reason: str
    performance_metrics: Optional[dict] = None
    estimated_cost_usd: Optional[float] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            from datetime import timezone

            self.timestamp = datetime.now(timezone.utc)


class IntelligentSelector:
    """
    Selector inteligente de modelos LLM.

    Utiliza registry e tracker para seleccionar o modelo óptimo
    baseado em múltiplos factores e prioridades configuráveis.
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        tracker: Optional[PerformanceTracker] = None,
        min_requests_for_stats: int = 10,
    ) -> None:
        """
        Inicializa o selector.

        Args:
            registry: Registry de modelos (usa global se None)
            tracker: Tracker de performance (usa global se None)
            min_requests_for_stats: Mínimo de requisições para usar stats
        """
        self._registry = registry or get_registry()
        self._tracker = tracker or get_tracker()
        self._min_requests_for_stats = min_requests_for_stats

    async def select_model(
        self,
        context: SelectionContext,
        criteria: SelectionCriteria = SelectionCriteria.BALANCED,
        weights: Optional[SelectionWeights] = None,
        excluded_models: Optional[set[str]] = None,
    ) -> Optional[SelectionResult]:
        """
        Selecciona o melhor modelo para o contexto dado.

        Args:
            context: Contexto da requisição
            criteria: Critério de seleção
            weights: Pesos customizados (apenas se criteria=CUSTOM)
            excluded_models: Modelos a excluir da seleção

        Returns:
            SelectionResult ou None se nenhum modelo encontrado
        """
        # Obtém modelos elegíveis
        models = self._registry.get_models_for_task(context.task_type, available_only=True)

        if excluded_models:
            models = [m for m in models if m.model_id not in excluded_models]

        # Filtra por capacidades requeridas
        models = self._filter_by_capabilities(models, context)

        if not models:
            return None

        # Filtra por constraints (latência, custo, qualidade)
        models = await self._filter_by_constraints(models, context)

        if not models:
            return None

        # Obtém métricas de performance
        metrics = {}
        for model in models:
            metrics[model.model_id] = await self._tracker.get_metrics(model.model_id)

        # Aplica critério de seleção
        if criteria == SelectionCriteria.FASTEST:
            return self._select_fastest(models, metrics, context)
        elif criteria == SelectionCriteria.CHEAPEST:
            return self._select_cheapest(models, context)
        elif criteria == SelectionCriteria.HIGHEST_QUALITY:
            return self._select_highest_quality(models, metrics, context)
        elif criteria == SelectionCriteria.CUSTOM:
            if not weights:
                weights = SelectionWeights()
            return await self._select_custom(models, metrics, weights, context)
        else:
            return await self._select_balanced(models, metrics, context)

    def _filter_by_capabilities(
        self,
        models: list[ModelMetadata],
        context: SelectionContext,
    ) -> list[ModelMetadata]:
        """Filtra modelos por capacidades requeridas."""
        filtered = []

        for model in models:
            caps = model.capabilities

            # Verifica streaming
            if context.requires_streaming and not caps.supports_streaming:
                continue

            # Verifica function calling
            if context.requires_function_calling and not caps.supports_function_calling:
                continue

            # Verifica visão
            if context.requires_vision and not caps.supports_vision:
                continue

            # Verifica tamanho de contexto
            total_tokens = context.expected_input_tokens + context.expected_output_tokens
            if total_tokens > caps.max_context_tokens:
                continue

            filtered.append(model)

        return filtered

    async def _filter_by_constraints(
        self,
        models: list[ModelMetadata],
        context: SelectionContext,
    ) -> list[ModelMetadata]:
        """Filtra modelos por constraints de latência, custo e qualidade."""
        filtered = []

        for model in models:
            metrics = await self._tracker.get_metrics(model.model_id)

            # Verifica latência máxima
            if context.max_latency_ms:
                avg_latency = metrics.get("avg_latency_ms", 0)
                if avg_latency > context.max_latency_ms:
                    continue

            # Verifica custo máximo
            if context.max_cost_usd:
                estimated_cost = self._estimate_cost(
                    model,
                    context.expected_input_tokens,
                    context.expected_output_tokens,
                )
                if estimated_cost > context.max_cost_usd:
                    continue

            # Verifica qualidade mínima
            if context.min_quality_score:
                quality = model.capabilities.benchmark_quality_score or 0
                if quality < context.min_quality_score:
                    continue

            filtered.append(model)

        return filtered

    def _select_fastest(
        self,
        models: list[ModelMetadata],
        metrics: dict,
        context: SelectionContext,
    ) -> SelectionResult:
        """Selecciona modelo mais rápido."""
        candidates = []

        for model in models:
            model_metrics = metrics[model.model_id]
            request_count = model_metrics.get("request_count", 0)

            # Usa latência do registry se não tem stats suficientes
            if request_count < self._min_requests_for_stats:
                lat_score = 1.0 / (model.capabilities.benchmark_quality_score or 0.5)
            else:
                latency = model_metrics.get("avg_latency_ms", 1)
                lat_score = 1000.0 / max(latency, 1.0)  # Evita divisão por zero

            candidates.append((model, lat_score))

        best_model = max(candidates, key=lambda x: x[1])[0]

        return SelectionResult(
            model_id=best_model.model_id,
            provider=best_model.provider,
            api_name=best_model.api_name,
            score=candidates[[m[0] for m in candidates].index(best_model)][1],
            selection_reason="Menor latência média",
            performance_metrics=metrics[best_model.model_id],
        )

    def _select_cheapest(
        self,
        models: list[ModelMetadata],
        context: SelectionContext,
    ) -> SelectionResult:
        """Selecciona modelo mais barato."""
        candidates = []

        for model in models:
            cost = self._estimate_cost(
                model,
                context.expected_input_tokens,
                context.expected_output_tokens,
            )
            # Score inverso do custo (menor custo = maior score)
            score = 1.0 / (cost + 0.0001)
            candidates.append((model, score))

        best_model = max(candidates, key=lambda x: x[1])[0]

        estimated_cost = self._estimate_cost(
            best_model,
            context.expected_input_tokens,
            context.expected_output_tokens,
        )

        return SelectionResult(
            model_id=best_model.model_id,
            provider=best_model.provider,
            api_name=best_model.api_name,
            score=candidates[[m[0] for m in candidates].index(best_model)][1],
            selection_reason="Menor custo estimado",
            estimated_cost_usd=estimated_cost,
        )

    def _select_highest_quality(
        self,
        models: list[ModelMetadata],
        metrics: dict,
        context: SelectionContext,
    ) -> SelectionResult:
        """Selecciona modelo com maior qualidade."""
        candidates = []

        for model in models:
            model_metrics = metrics[model.model_id]

            # Qualidade do registry
            quality = model.capabilities.benchmark_quality_score or 0.5

            # Penaliza se success rate baixo
            success_rate = model_metrics.get("success_rate", 1.0)
            adjusted_quality = quality * (success_rate**2)

            candidates.append((model, adjusted_quality))

        best_model = max(candidates, key=lambda x: x[1])[0]

        return SelectionResult(
            model_id=best_model.model_id,
            provider=best_model.provider,
            api_name=best_model.api_name,
            score=candidates[[m[0] for m in candidates].index(best_model)][1],
            selection_reason="Maior qualidade ajustada por sucesso",
            performance_metrics=metrics[best_model.model_id],
        )

    async def _select_balanced(
        self,
        models: list[ModelMetadata],
        metrics: dict,
        context: SelectionContext,
    ) -> SelectionResult:
        """Selecciona modelo balanceado (performance, custo, qualidade)."""
        candidates = []

        # Primeiro coleta todos os scores
        all_perf_scores = []
        all_cost_scores = []
        all_quality_scores = []

        for model in models:
            model_metrics = metrics[model.model_id]
            request_count = model_metrics.get("request_count", 0)

            if request_count < self._min_requests_for_stats:
                # Usa registry defaults
                perf_score = model.capabilities.benchmark_quality_score or 0.5
                cost = self._estimate_cost(
                    model,
                    context.expected_input_tokens,
                    context.expected_output_tokens,
                )
                cost_score = 1.0 / (cost + 0.0001) if cost > 0 else 1.0
                quality_score = model.capabilities.benchmark_quality_score or 0.5
            else:
                # Usa stats reais
                latency = model_metrics.get("avg_latency_ms", 1000)
                perf_score = 1000.0 / latency if latency > 0 else 0
                cost_per_k = model_metrics.get("avg_cost_per_1k_tokens", 0.001)
                cost_score = 1.0 / (cost_per_k + 0.0001) if cost_per_k > 0 else 1.0
                success_rate = model_metrics.get("success_rate", 1.0)
                quality_score = model.capabilities.benchmark_quality_score or 0.5
                quality_score *= success_rate

            all_perf_scores.append(perf_score)
            all_cost_scores.append(cost_score)
            all_quality_scores.append(quality_score)
            candidates.append((model, perf_score, cost_score, quality_score))

        # Normaliza scores
        max_perf = max(all_perf_scores) if all_perf_scores else 1.0
        max_cost = max(all_cost_scores) if all_cost_scores else 1.0
        max_quality = max(all_quality_scores) if all_quality_scores else 1.0

        normalized_candidates = []
        for model, perf_score, cost_score, quality_score in candidates:
            normalized_perf = perf_score / max_perf if max_perf > 0 else 0
            normalized_cost = cost_score / max_cost if max_cost > 0 else 0
            normalized_quality = quality_score / max_quality if max_quality > 0 else 0

            # Combina com pesos balanceados
            combined_score = (
                0.35 * normalized_perf + 0.35 * normalized_cost + 0.30 * normalized_quality
            )

            normalized_candidates.append((model, combined_score))

        best_model = max(normalized_candidates, key=lambda x: x[1])[0]

        return SelectionResult(
            model_id=best_model.model_id,
            provider=best_model.provider,
            api_name=best_model.api_name,
            score=normalized_candidates[[m[0] for m in normalized_candidates].index(best_model)][1],
            selection_reason="Melhor balance performance/custo/qualidade",
            performance_metrics=metrics[best_model.model_id],
            estimated_cost_usd=self._estimate_cost(
                best_model,
                context.expected_input_tokens,
                context.expected_output_tokens,
            ),
        )

    async def _select_custom(
        self,
        models: list[ModelMetadata],
        metrics: dict,
        weights: SelectionWeights,
        context: SelectionContext,
    ) -> SelectionResult:
        """Selecciona modelo com pesos customizados."""
        weights.validate()

        # Primeiro coleta todos os scores para normalização
        all_perf_scores = []
        all_cost_scores = []
        all_quality_scores = []

        raw_candidates = []

        for model in models:
            model_metrics = metrics[model.model_id]

            if model_metrics.get("request_count", 0) < self._min_requests_for_stats:
                perf_score = model.capabilities.benchmark_quality_score or 0.5
                cost = self._estimate_cost(
                    model,
                    context.expected_input_tokens,
                    context.expected_output_tokens,
                )
                cost_score = 1.0 / (cost + 0.0001) if cost > 0 else 1.0
                quality_score = model.capabilities.benchmark_quality_score or 0.5
            else:
                latency = model_metrics.get("avg_latency_ms", 1000)
                perf_score = 1000.0 / latency if latency > 0 else 0
                cost_per_k = model_metrics.get("avg_cost_per_1k_tokens", 0.001)
                cost_score = 1.0 / (cost_per_k + 0.0001) if cost_per_k > 0 else 1.0
                success_rate = model_metrics.get("success_rate", 1.0)
                quality_score = model.capabilities.benchmark_quality_score or 0.5
                quality_score *= success_rate

            all_perf_scores.append(perf_score)
            all_cost_scores.append(cost_score)
            all_quality_scores.append(quality_score)
            raw_candidates.append((model, perf_score, cost_score, quality_score))

        # Normaliza scores
        max_perf = max(all_perf_scores) if all_perf_scores else 1.0
        max_cost = max(all_cost_scores) if all_cost_scores else 1.0
        max_quality = max(all_quality_scores) if all_quality_scores else 1.0

        candidates = []
        for model, perf_score, cost_score, quality_score in raw_candidates:
            normalized_perf = perf_score / max_perf if max_perf > 0 else 0
            normalized_cost = cost_score / max_cost if max_cost > 0 else 0
            normalized_quality = quality_score / max_quality if max_quality > 0 else 0

            # Combina com pesos customizados
            combined_score = (
                weights.performance_weight * normalized_perf
                + weights.cost_weight * normalized_cost
                + weights.quality_weight * normalized_quality
            )

            candidates.append((model, combined_score))

        best_model = max(candidates, key=lambda x: x[1])[0]

        return SelectionResult(
            model_id=best_model.model_id,
            provider=best_model.provider,
            api_name=best_model.api_name,
            score=candidates[[m[0] for m in candidates].index(best_model)][1],
            selection_reason=f"Pesos customizados (P:{weights.performance_weight:.2f} C:{weights.cost_weight:.2f} Q:{weights.quality_weight:.2f})",
            performance_metrics=metrics[best_model.model_id],
            estimated_cost_usd=self._estimate_cost(
                best_model,
                context.expected_input_tokens,
                context.expected_output_tokens,
            ),
        )

    def _calc_perf_score(
        self,
        model: ModelMetadata,
        metrics: dict,
        min_requests: int,
    ) -> float:
        """Calcula score de performance."""
        if metrics.get("request_count", 0) < min_requests:
            return model.capabilities.benchmark_quality_score or 0.5

        latency = metrics.get("avg_latency_ms", 1000)
        return 1000.0 / latency if latency > 0 else 0

    def _calc_cost_score(
        self,
        model: ModelMetadata,
        metrics: dict,
        min_requests: int,
        context: SelectionContext,
    ) -> float:
        """Calcula score de custo."""
        if metrics.get("request_count", 0) >= min_requests:
            cost = metrics.get("avg_cost_per_1k_tokens", 0.001)
        else:
            cost = self._estimate_cost(
                model,
                context.expected_input_tokens,
                context.expected_output_tokens,
            )

        return 1.0 / (cost + 0.0001) if cost > 0 else 1.0

    def _calc_quality_score(
        self,
        model: ModelMetadata,
        metrics: dict,
        min_requests: int,
    ) -> float:
        """Calcula score de qualidade."""
        quality = model.capabilities.benchmark_quality_score or 0.5

        if metrics.get("request_count", 0) >= min_requests:
            success_rate = metrics.get("success_rate", 1.0)
            quality *= success_rate

        return quality

    def _estimate_cost(
        self,
        model: ModelMetadata,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Estima custo em USD para uma requisição."""
        input_cost = (input_tokens / 1000) * model.pricing.input_price_per_1k_usd
        output_cost = (output_tokens / 1000) * model.pricing.output_price_per_1k_usd
        return input_cost + output_cost


def get_selector() -> IntelligentSelector:
    """
    Retorna o selector global (singleton).

    Returns:
        IntelligentSelector: Instância global do selector
    """
    return IntelligentSelector()


def reset_selector() -> None:
    """Reseta o selector (útil para testes)."""
    pass
