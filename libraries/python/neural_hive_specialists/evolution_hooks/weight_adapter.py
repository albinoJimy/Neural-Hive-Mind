"""Weight adaptation based on historical patterns."""

import structlog

from .models import DEFAULT_WEIGHTS, Fingerprint, PatternRecord
from .pattern_matcher import PatternMatcher

logger = structlog.get_logger()


class WeightAdapter:
    """Adapta pesos baseado em histórico de padrões similares."""

    def __init__(self, mongo_client, min_similar_patterns: int = 5, max_adjustment: float = 0.05):
        """
        Inicializa adaptador.

        Args:
            mongo_client: Cliente MongoDB
            min_similar_patterns: Mínimo de padrões para adaptação
            max_adjustment: Ajuste máximo por peso (absoluto)
        """
        self.matcher = PatternMatcher(mongo_client)
        self.min_similar_patterns = min_similar_patterns
        self.max_adjustment = max_adjustment
        self.logger = logger
        # Expor registry para acesso nos testes
        self.registry = self.matcher.registry

    async def adapt_weights(self, fingerprint: Fingerprint) -> dict[str, float]:
        """
        Adapta pesos baseado em histórico.

        Args:
            fingerprint: Fingerprint do plano atual

        Returns:
            Dict com pesos adaptados (ou defaults se insuficiente histórico ou erro)
        """
        try:
            # Buscar padrões similares
            similar = await self.matcher.find_similar(fingerprint)
        except Exception as e:
            self.logger.warning("Failed to find similar patterns, using defaults", error=str(e))
            return DEFAULT_WEIGHTS.copy()

        if len(similar) < self.min_similar_patterns:
            self.logger.debug(
                "Insufficient similar patterns",
                found=len(similar),
                required=self.min_similar_patterns,
            )
            return DEFAULT_WEIGHTS.copy()

        # Calcular ajustes
        adjustments = self._calculate_weight_adjustments(similar)

        # Aplicar ajustes e normalizar
        adapted = self._apply_adjustments_and_normalize(DEFAULT_WEIGHTS, adjustments)

        self.logger.debug(
            "Adapted weights",
            fingerprint=fingerprint.complexity_signature,
            similar_count=len(similar),
            adapted=adapted,
        )

        return adapted

    def _calculate_weight_adjustments(self, similar: list[PatternRecord]) -> dict[str, float]:
        """
        Calcula ajustes baseado em histórico.

        Args:
            similar: Lista de padrões similares

        Returns:
            Dict com ajustes por peso
        """
        adjustments = {}
        weight_names = [
            "maintainability",
            "scalability",
            "extensibility",
            "modularity",
            "tech_debt_prevention",
        ]

        for weight_name in weight_names:
            # Contar sucessos quando peso foi alto vs baixo
            success_when_high = 0
            count_high = 0
            success_when_low = 0
            count_low = 0

            for pattern in similar:
                if not pattern.feedback:
                    continue

                weight_value = pattern.evaluation.weights_used.get(weight_name, 0.15)
                is_high = weight_value > 0.20

                outcome_is_success = pattern.feedback.outcome == "approve"

                if is_high:
                    count_high += 1
                    if outcome_is_success:
                        success_when_high += 1
                else:
                    count_low += 1
                    if outcome_is_success:
                        success_when_low += 1

            # Calcular taxa de sucesso
            rate_high = success_when_high / count_high if count_high > 0 else 0
            rate_low = success_when_low / count_low if count_low > 0 else 0

            # Calcular ajuste
            if rate_high > rate_low:
                # Aumentar peso
                diff = rate_high - rate_low
                adjustment = min(self.max_adjustment, diff / 20)  # Divide por 20 para suavizar
                adjustments[weight_name] = +adjustment
            elif rate_low > rate_high:
                # Diminuir peso
                diff = rate_low - rate_high
                adjustment = min(self.max_adjustment, diff / 20)
                adjustments[weight_name] = -adjustment
            else:
                adjustments[weight_name] = 0.0

        return adjustments

    def _apply_adjustments_and_normalize(
        self, base: dict[str, float], adjustments: dict[str, float]
    ) -> dict[str, float]:
        """
        Aplica ajustes aos pesos base e normaliza.

        Algoritmo:
        1. Aplicar ajustes brutos
        2. Clipar cada peso aos limites [default - max, default + max]
        3. Calcular soma atual
        4. Se soma != 1.0, redistribuir proporcionalmente
        5. Re-clipar e iterar se necessário
        """
        # Passo 1: Aplicar ajustes
        result = {}
        for name, value in base.items():
            adjustment = adjustments.get(name, 0.0)
            result[name] = max(0.0, value + adjustment)

        # Passo 2: Clipar aos limites
        for name, value in result.items():
            default = base.get(name, 0)
            min_val = max(0.0, default - self.max_adjustment)
            max_val = min(1.0, default + self.max_adjustment)
            result[name] = max(min_val, min(max_val, value))

        # Passo 3-5: Normalizar e iterar até convergência
        for iteration in range(10):
            total = sum(result.values())

            if abs(total - 1.0) < 0.0001:
                break  # Convergiu

            # Calcular quanto cada peso pode se mover
            deltas = {}
            for name, value in result.items():
                default = base.get(name, 0)
                min_val = max(0.0, default - self.max_adjustment)
                max_val = min(1.0, default + self.max_adjustment)
                deltas[name] = {"can_increase": max_val - value, "can_decrease": value - min_val}

            # Se total < 1, precisamos aumentar
            if total < 1.0:
                # Aumentar proporcionalmente aos que podem aumentar
                increase_available = sum(d["can_increase"] for d in deltas.values())
                if increase_available > 0.0001:
                    needed = 1.0 - total
                    for name in result:
                        ratio = deltas[name]["can_increase"] / increase_available
                        result[name] += ratio * needed
                else:
                    # Não é possível ajustar sem violar limites
                    break
            else:
                # Se total > 1, precisamos diminuir
                decrease_available = sum(d["can_decrease"] for d in deltas.values())
                if decrease_available > 0.0001:
                    excess = total - 1.0
                    for name in result:
                        ratio = deltas[name]["can_decrease"] / decrease_available
                        result[name] -= ratio * excess
                else:
                    # Não é possível ajustar sem violar limites
                    break

            # Clip novamente após ajuste
            for name, value in result.items():
                default = base.get(name, 0)
                min_val = max(0.0, default - self.max_adjustment)
                max_val = min(1.0, default + self.max_adjustment)
                result[name] = max(min_val, min(max_val, value))

        return result
