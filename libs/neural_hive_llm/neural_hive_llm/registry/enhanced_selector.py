"""
Enhanced Intelligent Selector with Additional Criteria.

Selector expandido que considera qualidade específica por domínio,
confiabilidade, compliance, feedback do utilizador e factores dinâmicos.
"""

from neural_hive_llm.registry.enhanced_selection import (
    DataResidencyRequirement,
    EnhancedSelectionContext,
    ExtendedSelectionCriteria,
    ExtendedSelectionWeights,
    PriorityLevel,
)
from neural_hive_llm.registry.extended_metrics import (
    ComplianceInfo,
    ExtendedModelMetadata,
    ModelQualityScores,
    ReliabilityMetrics,
    UserFeedbackMetrics,
)
from neural_hive_llm.registry.intelligent_selector import (
    IntelligentSelector,
    SelectionResult,
)
from neural_hive_llm.registry.model_registry import (
    ModelMetadata,
)
from neural_hive_llm.registry.model_registry import (
    get_registry as get_base_registry,
)


class EnhancedIntelligentSelector(IntelligentSelector):
    """
    Selector inteligente expandido com critérios adicionais.

    Considera além de performance e custo:
    - Qualidade específica por domínio
    - Confiabilidade (uptime, success rate)
    - Compliance e segurança
    - Feedback do utilizador
    - Factores dinâmicos (carga, hora do dia)
    - Prioridade da requisição
    """

    @staticmethod
    def _normalize_enum_value(value) -> str:
        """Normaliza valor de enum para string.

        Usado para lidar com campos do contexto que podem ser
        Enums ou strings devido ao use_enum_values do Pydantic.
        """
        if hasattr(value, "value"):
            return value.value
        return value

    def __init__(
        self,
        registry=None,
        tracker=None,
        min_requests_for_stats: int = 10,
    ) -> None:
        """Inicializa o selector expandido."""
        super().__init__(registry, tracker, min_requests_for_stats)
        self._base_registry = get_base_registry()
        self._base_models_map: dict[str, ModelMetadata] = {}

    async def select_model(
        self,
        context: EnhancedSelectionContext,
        criteria: ExtendedSelectionCriteria = ExtendedSelectionCriteria.OPTIMAL_COMPOSITE,
        weights: ExtendedSelectionWeights | None = None,
        excluded_models: set[str] | None = None,
    ) -> SelectionResult | None:
        """
        Selecciona o melhor modelo usando critérios expandidos.

        Args:
            context: Contexto de seleção expandido
            criteria: Critério de seleção
            weights: Pesos customizados (apenas se criteria=CUSTOM)
            excluded_models: Modelos a excluir

        Returns:
            SelectionResult ou None
        """
        # Obtém modelos base elegíveis
        base_models = self._base_registry.get_models_for_task(
            context.task_type, available_only=True
        )

        if excluded_models:
            base_models = [m for m in base_models if m.model_id not in excluded_models]

        # Aplica filtros de preferências do utilizador
        if context.exclude_providers:
            base_models = [m for m in base_models if m.provider not in context.exclude_providers]

        if context.provider_preference:
            # Dá preferência ao provider, mas mantém opções
            preferred = [m for m in base_models if m.provider == context.provider_preference]
            if preferred:
                base_models = preferred + [m for m in base_models if m not in preferred]

        # Mapeia para metadados extendidos (simulados por enquanto)
        extended_models = self._create_extended_metadata(base_models)

        # Filtra por critérios extendidos
        filtered_models = self._filter_by_extended_criteria(extended_models, context)

        if not filtered_models:
            return None

        # Aplica critério de seleção
        if criteria == ExtendedSelectionCriteria.FASTEST:
            return await self._select_fastest(filtered_models, context)
        elif criteria == ExtendedSelectionCriteria.CHEAPEST:
            return self._select_cheapest(filtered_models, context)
        elif criteria == ExtendedSelectionCriteria.HIGHEST_QUALITY:
            return self._select_highest_quality(filtered_models, context)
        elif criteria == ExtendedSelectionCriteria.HIGHEST_DOMAIN_QUALITY:
            return self._select_highest_domain_quality(filtered_models, context)
        elif criteria == ExtendedSelectionCriteria.MOST_RELIABLE:
            return self._select_most_reliable(filtered_models, context)
        elif criteria == ExtendedSelectionCriteria.BEST_USER_SATISFACTION:
            return self._select_best_user_satisfaction(filtered_models, context)
        elif criteria == ExtendedSelectionCriteria.BEST_COMPLIANCE:
            return self._select_best_compliance(filtered_models, context)
        elif criteria == ExtendedSelectionCriteria.PRIORITY_AWARE:
            return await self._select_priority_aware(filtered_models, context)
        elif criteria == ExtendedSelectionCriteria.CUSTOM:
            if not weights:
                weights = ExtendedSelectionWeights()
            return await self._select_custom(filtered_models, weights, context)
        else:
            return await self._select_optimal_composite(filtered_models, context)

    def _create_extended_metadata(
        self, base_models: list[ModelMetadata]
    ) -> list[ExtendedModelMetadata]:
        """
        Cria metadados extendidos a partir de modelos base.

        Em produção, isto buscaria dados reais de um banco de dados
        ou serviço de metadados.
        """
        extended = []
        self._base_models_map.clear()  # Limpa mapeamento anterior
        for base_model in base_models:
            # Armazena mapeamento para recuperar provider/api_name depois
            self._base_models_map[base_model.model_id] = base_model
            # Simula métricas de qualidade específicas por domínio
            quality_scores = ModelQualityScores(
                coding_score=0.9 if "gpt" in base_model.api_name else 0.75,
                analysis_score=base_model.capabilities.benchmark_quality_score,
                reasoning_score=base_model.capabilities.benchmark_quality_score,
                chat_score=base_model.capabilities.benchmark_quality_score,
            )

            # Simula métricas de confiabilidade
            reliability = ReliabilityMetrics(
                success_rate=0.98,
                uptime_percentage=99.9,
                geographic_regions=["us", "eu"] if "openai" in base_model.provider else ["global"],
            )

            # Simula informações de compliance
            compliance = ComplianceInfo(
                data_residency="us" if "openai" in base_model.provider else "eu",
                compliance_standards=(
                    ["soc2", "gdpr"] if base_model.provider in ["openai", "anthropic"] else []
                ),
                enterprise_tier=True if "gpt-4" in base_model.api_name else False,
            )

            # Simula feedback do utilizador
            user_feedback = UserFeedbackMetrics(
                avg_rating=4.5 if "gpt-4" in base_model.api_name else 4.0,
                total_feedback_count=1000,
                helpful_percentage=85.0,
                task_completion_rate=0.92,
            )

            extended_model = ExtendedModelMetadata(
                model_id=base_model.model_id,
                quality_scores=quality_scores,
                reliability=reliability,
                compliance=compliance,
                user_feedback=user_feedback,
                dynamic_factors=None,
            )

            extended.append(extended_model)

        return extended

    def _filter_by_extended_criteria(
        self,
        models: list[ExtendedModelMetadata],
        context: EnhancedSelectionContext,
    ) -> list[ExtendedModelMetadata]:
        """Filtra modelos por critérios extendidos."""
        filtered = []

        for model in models:
            # Filtro de uptime mínimo
            if model.reliability.uptime_percentage < context.min_uptime_percentage:
                continue

            # Filtro de success rate mínimo
            if model.reliability.success_rate < context.min_success_rate:
                continue

            # Filtro de compliance
            if context.compliance_requirements:
                model_compliance = set(model.compliance.compliance_standards)
                required = {self._normalize_enum_value(c) for c in context.compliance_requirements}
                if not required.issubset(model_compliance):
                    continue

            # Filtro de residência de dados
            if context.data_residency:
                residency_value = self._normalize_enum_value(context.data_residency)
                if residency_value != DataResidencyRequirement.NONE.value:
                    if model.compliance.data_residency != residency_value:
                        continue

            # Filtro de enterprise tier
            if context.require_enterprise_tier and not model.compliance.enterprise_tier:
                continue

            # Filtro de rating do utilizador
            if (
                context.require_positive_user_feedback
                and model.user_feedback
                and context.min_user_rating
            ):
                if model.user_feedback.avg_rating < context.min_user_rating:
                    continue

            # Filtro de alta disponibilidade para requisições críticas
            if (
                context.require_high_availability
                and self._normalize_enum_value(context.priority) == PriorityLevel.CRITICAL.value
            ):
                if model.reliability.uptime_percentage < 99.9:
                    continue

            filtered.append(model)

        return filtered

    def _create_selection_result(
        self,
        model_id: str,
        score: float,
        reason: str,
    ) -> SelectionResult:
        """Cria SelectionResult com provider e api_name do modelo base."""
        base_model = self._base_models_map.get(model_id)
        if not base_model:
            return SelectionResult(
                model_id=model_id,
                provider="unknown",
                api_name="unknown",
                score=score,
                selection_reason=reason,
            )
        return SelectionResult(
            model_id=model_id,
            provider=base_model.provider,
            api_name=base_model.api_name,
            score=score,
            selection_reason=reason,
        )

    async def _select_fastest(
        self,
        models: list[ExtendedModelMetadata],
        context: EnhancedSelectionContext,
    ) -> SelectionResult:
        """Selecciona modelo mais rápido baseado em métricas de confiabilidade."""
        candidates = []
        for model in models:
            # Usa success_rate como proxy de velocidade (maior sucesso = mais rápido)
            lat_score = model.reliability.success_rate
            candidates.append((model, lat_score))

        best_model = max(candidates, key=lambda x: x[1])[0]
        score = candidates[[m[0] for m in candidates].index(best_model)][1]

        return self._create_selection_result(
            best_model.model_id,
            score,
            "Menor latência média",
        )

    def _select_cheapest(
        self,
        models: list[ExtendedModelMetadata],
        context: EnhancedSelectionContext,
    ) -> SelectionResult:
        """Selecciona modelo com melhor qualidade (proxy para menor custo na ausência de dados)."""
        # Como ExtendedModelMetadata não tem dados de custo,
        # usamos qualidade como proxy inverso de custo
        candidates = []
        for model in models:
            # Menor qualidade = mais barato (geralmente)
            cost_score = 1.0 / (model.quality_scores.average_score + 0.01)
            candidates.append((model, cost_score))

        best_model = max(candidates, key=lambda x: x[1])[0]
        score = candidates[[m[0] for m in candidates].index(best_model)][1]

        return self._create_selection_result(
            best_model.model_id,
            score,
            "Menor custo estimado",
        )

    def _select_highest_quality(
        self,
        models: list[ExtendedModelMetadata],
        context: EnhancedSelectionContext,
    ) -> SelectionResult:
        """Selecciona modelo com maior qualidade."""
        candidates = []
        for model in models:
            quality = model.composite_quality_score
            # Penaliza se success rate baixo
            success_rate = model.reliability.success_rate
            adjusted_quality = quality * (success_rate**2)
            candidates.append((model, adjusted_quality))

        best_model = max(candidates, key=lambda x: x[1])[0]
        score = candidates[[m[0] for m in candidates].index(best_model)][1]

        return self._create_selection_result(
            best_model.model_id,
            score,
            "Maior qualidade ajustada por sucesso",
        )

    async def _select_balanced(
        self,
        models: list[ExtendedModelMetadata],
        context: EnhancedSelectionContext,
    ) -> SelectionResult:
        """Selecciona modelo balanceado."""
        candidates = []

        for model in models:
            perf_score = model.reliability.success_rate
            quality_score = model.composite_quality_score
            # Custo como inverso da qualidade
            cost_score = 1.0 / (model.quality_scores.average_score + 0.01)

            # Normaliza localmente
            candidates.append((model, perf_score, cost_score, quality_score))

        if candidates:
            max_perf = max(c[1] for c in candidates)
            max_cost = max(c[2] for c in candidates)
            max_quality = max(c[3] for c in candidates)

            normalized = []
            for model, perf, cost, qual in candidates:
                norm_perf = perf / max_perf if max_perf > 0 else 0
                norm_cost = cost / max_cost if max_cost > 0 else 0
                norm_qual = qual / max_quality if max_quality > 0 else 0

                combined = 0.35 * norm_perf + 0.35 * norm_cost + 0.30 * norm_qual
                normalized.append((model, combined))

            best_model = max(normalized, key=lambda x: x[1])[0]
            score = normalized[[m[0] for m in normalized].index(best_model)][1]

            return self._create_selection_result(
                best_model.model_id,
                score,
                "Melhor balance performance/custo/qualidade",
            )

        # Fallback
        return self._create_selection_result(
            models[0].model_id,
            0.5,
            "Seleção padrão",
        )

    def _select_highest_domain_quality(
        self,
        models: list[ExtendedModelMetadata],
        context: EnhancedSelectionContext,
    ) -> SelectionResult:
        """Selecciona modelo com maior qualidade no domínio específico."""
        if not context.domain or not context.require_domain_expertise:
            return self._select_highest_quality(models, context)

        candidates = []
        for model in models:
            domain_score = model.quality_scores.get_score_for_domain(context.domain)
            score = domain_score if domain_score else model.quality_scores.average_score
            candidates.append((model, score))

        best_model = max(candidates, key=lambda x: x[1])[0]
        score = candidates[[m[0] for m in candidates].index(best_model)][1]

        domain_value = self._normalize_enum_value(context.domain)
        return self._create_selection_result(
            best_model.model_id,
            score,
            f"Maior qualidade no domínio {domain_value}",
        )

    def _select_most_reliable(
        self,
        models: list[ExtendedModelMetadata],
        context: EnhancedSelectionContext,
    ) -> SelectionResult:
        """Selecciona modelo mais confiável."""
        candidates = []
        for model in models:
            reliability_score = model.operational_health_score
            candidates.append((model, reliability_score))

        best_model = max(candidates, key=lambda x: x[1])[0]
        score = candidates[[m[0] for m in candidates].index(best_model)][1]

        return self._create_selection_result(
            best_model.model_id,
            score,
            "Maior confiabilidade operacional",
        )

    def _select_best_user_satisfaction(
        self,
        models: list[ExtendedModelMetadata],
        context: EnhancedSelectionContext,
    ) -> SelectionResult:
        """Selecciona modelo com melhor satisfação do utilizador."""
        candidates = []
        for model in models:
            satisfaction = (
                model.user_feedback.user_satisfaction_score if model.user_feedback else 0.0
            )
            candidates.append((model, satisfaction))

        best_model = max(candidates, key=lambda x: x[1])[0]
        score = candidates[[m[0] for m in candidates].index(best_model)][1]

        return self._create_selection_result(
            best_model.model_id,
            score,
            "Melhor satisfação do utilizador",
        )

    def _select_best_compliance(
        self,
        models: list[ExtendedModelMetadata],
        context: EnhancedSelectionContext,
    ) -> SelectionResult:
        """Selecciona modelo com melhor compliance."""
        candidates = []
        for model in models:
            compliance_score = len(model.compliance.compliance_standards) * 0.5
            if model.compliance.enterprise_tier:
                compliance_score += 0.3
            if model.compliance.encryption_at_rest and model.compliance.encryption_in_transit:
                compliance_score += 0.2
            candidates.append((model, min(compliance_score, 1.0)))

        best_model = max(candidates, key=lambda x: x[1])[0]
        score = candidates[[m[0] for m in candidates].index(best_model)][1]

        return self._create_selection_result(
            best_model.model_id,
            score,
            "Melhor compliance e segurança",
        )

    async def _select_priority_aware(
        self,
        models: list[ExtendedModelMetadata],
        context: EnhancedSelectionContext,
    ) -> SelectionResult:
        """Selecciona modelo baseado na prioridade da requisição."""
        priority_value = self._normalize_enum_value(context.priority)
        if priority_value == PriorityLevel.CRITICAL.value:
            return self._select_most_reliable(models, context)
        elif priority_value == PriorityLevel.HIGH.value:
            return self._select_highest_domain_quality(models, context)
        elif priority_value == PriorityLevel.MEDIUM.value:
            return await self._select_balanced(models, context)
        else:
            return self._select_cheapest(models, context)

    async def _select_custom(
        self,
        models: list[ExtendedModelMetadata],
        weights: ExtendedSelectionWeights,
        context: EnhancedSelectionContext,
    ) -> SelectionResult:
        """Selecciona modelo com pesos customizados extendidos."""
        weights.validate()

        candidates = []

        for model in models:
            # Calcula scores parciais
            performance_score = model.reliability.success_rate
            cost_score = 1.0 / (model.quality_scores.average_score + 0.01)
            quality_score = model.composite_quality_score
            domain_score = (
                model.quality_scores.get_score_for_domain(context.domain)
                if context.domain
                else model.quality_scores.average_score
            )
            reliability_score = model.operational_health_score
            user_feedback_score = (
                model.user_feedback.user_satisfaction_score if model.user_feedback else 0.0
            )
            compliance_score = len(model.compliance.compliance_standards) * 0.1

            # Combina com pesos customizados
            combined_score = (
                weights.performance_weight * performance_score
                + weights.cost_weight * cost_score
                + weights.quality_weight * quality_score
                + weights.domain_quality_weight * domain_score
                + weights.reliability_weight * reliability_score
                + weights.user_feedback_weight * user_feedback_score
                + weights.compliance_weight * compliance_score
            )

            candidates.append((model, combined_score))

        best_model = max(candidates, key=lambda x: x[1])[0]
        score = candidates[[m[0] for m in candidates].index(best_model)][1]

        return self._create_selection_result(
            best_model.model_id,
            score,
            "Pesos customizados extendidos",
        )

    async def _select_optimal_composite(
        self,
        models: list[ExtendedModelMetadata],
        context: EnhancedSelectionContext,
    ) -> SelectionResult:
        """Selecciona modelo óptimo usando todos os critérios."""
        candidates = []

        for model in models:
            # Scores parciais
            reliability_score = model.operational_health_score
            quality_score = model.composite_quality_score

            # Domain expertise se aplicável
            domain_score = (
                model.quality_scores.get_score_for_domain(context.domain)
                if context.domain and context.require_domain_expertise
                else model.quality_scores.average_score
            )

            # User satisfaction
            user_feedback_score = (
                model.user_feedback.user_satisfaction_score if model.user_feedback else 0.0
            )

            # Compliance boost
            compliance_boost = len(model.compliance.compliance_standards) * 0.05

            # Combina com pesos óptimos
            combined_score = (
                0.30 * reliability_score
                + 0.30 * quality_score
                + 0.20 * domain_score
                + 0.15 * user_feedback_score
                + compliance_boost
            )

            # Prioridade boost
            priority_value = self._normalize_enum_value(context.priority)
            if priority_value == PriorityLevel.CRITICAL.value:
                combined_score *= 1.1

            candidates.append((model, combined_score))

        best_model = max(candidates, key=lambda x: x[1])[0]
        score = candidates[[m[0] for m in candidates].index(best_model)][1]

        return self._create_selection_result(
            best_model.model_id,
            score,
            "Seleção óptima composta (todos os critérios)",
        )


def get_enhanced_selector() -> EnhancedIntelligentSelector:
    """Retorna o selector expandido global (singleton)."""
    return EnhancedIntelligentSelector()
