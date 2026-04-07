"""
Risk Thresholds

Configuração dinâmica de thresholds com ajuste automático baseado em histórico.
"""

import structlog
from typing import Dict, List, Optional
from datetime import datetime, timezone
from collections import deque
from statistics import mean, stdev

from .config import RiskScoringConfig
from neural_hive_domain import UnifiedDomain


logger = structlog.get_logger(__name__)


class ThresholdAdjustmentStrategy:
    """Estratégias de ajuste de threshold."""

    PERCENTILE = "percentile"  # Baseado em percentis do histórico
    STANDARD_DEVIATION = "std_dev"  # Baseado em desvio padrão
    EXPONENTIAL_MOVING_AVG = "ema"  # Média móvel exponencial
    MANUAL = "manual"  # Ajuste manual


class DynamicThresholds:
    """Gerencia thresholds dinâmicos de risco."""

    def __init__(
        self,
        base_config: RiskScoringConfig,
        adjustment_strategy: str = ThresholdAdjustmentStrategy.PERCENTILE,
        window_size: int = 100,
        min_samples_for_adjustment: int = 20,
        adjustment_factor: float = 0.1,
    ):
        """Inicializa gerenciador de thresholds dinâmicos.

        Args:
            base_config: Configuração base de thresholds
            adjustment_strategy: Estratégia de ajuste automático
            window_size: Tamanho da janela de histórico para cálculo
            min_samples_for_adjustment: Mínimo de amostras antes de ajustar
            adjustment_factor: Fator de ajuste (0.0 a 1.0)
        """
        self.base_config = base_config
        self.adjustment_strategy = adjustment_strategy
        self.window_size = window_size
        self.min_samples_for_adjustment = min_samples_for_adjustment
        self.adjustment_factor = adjustment_factor

        # Histórico de scores por domínio
        self._history: Dict[str, deque] = {
            domain.value: deque(maxlen=window_size) for domain in UnifiedDomain
        }

        # Thresholds atuais (inicializa com base_config)
        self._current_thresholds: Dict[str, Dict[str, float]] = {}
        for domain in UnifiedDomain:
            self._current_thresholds[domain.value] = base_config.get_thresholds(domain).copy()

        # Timestamp da última atualização
        self._last_adjustment: Dict[str, datetime] = {}

    def get_thresholds(self, domain: UnifiedDomain) -> Dict[str, float]:
        """Retorna thresholds atuais para domínio.

        Args:
            domain: Domínio de risco

        Returns:
            Dict com {'medium': X, 'high': Y, 'critical': Z}
        """
        return self._current_thresholds.get(domain.value, self.base_config.get_thresholds(domain))

    def record_score(
        self, domain: UnifiedDomain, score: float, timestamp: Optional[datetime] = None
    ):
        """Registra score para análise de threshold.

        Args:
            domain: Domínio do score
            score: Valor do score (0.0 a 1.0)
            timestamp: Timestamp do score (padrão: agora)
        """
        ts = timestamp or datetime.now(timezone.utc)
        self._history[domain.value].append((ts, score))

    def adjust_thresholds(
        self, domain: Optional[UnifiedDomain] = None, force: bool = False
    ) -> Dict[str, Dict[str, float]]:
        """Ajusta thresholds baseado em histórico.

        Args:
            domain: Domínio específico ou None para todos
            force: Força ajuste mesmo sem amostras suficientes

        Returns:
            Thresholds ajustados por domínio
        """
        domains = [domain] if domain else list(UnifiedDomain)

        adjusted = {}

        for d in domains:
            domain_value = d.value
            history = list(self._history[domain_value])

            if not force and len(history) < self.min_samples_for_adjustment:
                logger.debug(
                    "insufficient_samples_for_adjustment",
                    domain=domain_value,
                    samples=len(history),
                    required=self.min_samples_for_adjustment,
                )
                adjusted[domain_value] = self._current_thresholds[domain_value]
                continue

            # Extrair scores
            scores = [score for _, score in history]

            # Calcular novos thresholds baseado na estratégia
            if self.adjustment_strategy == ThresholdAdjustmentStrategy.PERCENTILE:
                new_thresholds = self._calculate_percentile_thresholds(scores, domain_value)
            elif self.adjustment_strategy == ThresholdAdjustmentStrategy.STANDARD_DEVIATION:
                new_thresholds = self._calculate_std_dev_thresholds(scores, domain_value)
            elif self.adjustment_strategy == ThresholdAdjustmentStrategy.EXPONENTIAL_MOVING_AVG:
                new_thresholds = self._calculate_ema_thresholds(scores, domain_value)
            else:
                new_thresholds = self.base_config.get_thresholds(d)

            # Aplicar ajuste parcial (não muda drasticamente)
            old_thresholds = self._current_thresholds[domain_value]
            blended_thresholds = self._blend_thresholds(old_thresholds, new_thresholds)

            self._current_thresholds[domain_value] = blended_thresholds
            self._last_adjustment[domain_value] = datetime.now(timezone.utc)

            adjusted[domain_value] = blended_thresholds

            logger.info(
                "thresholds_adjusted",
                domain=domain_value,
                strategy=self.adjustment_strategy,
                old_thresholds=old_thresholds,
                new_thresholds=blended_thresholds,
                samples=len(scores),
            )

        return adjusted

    def _calculate_percentile_thresholds(
        self, scores: List[float], domain: str
    ) -> Dict[str, float]:
        """Calcula thresholds baseado em percentis.

        Strategy:
        - medium: percentil 60
        - high: percentil 80
        - critical: percentil 95
        """
        if not scores:
            return self.base_config.get_thresholds(UnifiedDomain(domain))

        sorted_scores = sorted(scores)
        n = len(sorted_scores)

        def percentile(p: float) -> float:
            idx = min(int(n * p), n - 1)
            return sorted_scores[idx]

        return {"medium": percentile(0.60), "high": percentile(0.80), "critical": percentile(0.95)}

    def _calculate_std_dev_thresholds(self, scores: List[float], domain: str) -> Dict[str, float]:
        """Calcula thresholds baseado em desvio padrão.

        Strategy:
        - medium: mean + 0.5 * std
        - high: mean + 1.0 * std
        - critical: mean + 1.5 * std
        """
        if len(scores) < 2:
            return self.base_config.get_thresholds(UnifiedDomain(domain))

        avg = mean(scores)
        std = stdev(scores)

        return {
            "medium": min(1.0, avg + 0.5 * std),
            "high": min(1.0, avg + 1.0 * std),
            "critical": min(1.0, avg + 1.5 * std),
        }

    def _calculate_ema_thresholds(self, scores: List[float], domain: str) -> Dict[str, float]:
        """Calcula thresholds usando média móvel exponencial.

        Strategy: EMA com alpha=0.2, adiciona múltiplos de desvio.
        """
        if not scores:
            return self.base_config.get_thresholds(UnifiedDomain(domain))

        # Calcular EMA
        alpha = 0.2
        ema = scores[0]
        for score in scores[1:]:
            ema = alpha * score + (1 - alpha) * ema

        # Calcular desvio em relação à EMA
        deviations = [abs(s - ema) for s in scores]
        avg_deviation = mean(deviations)

        return {
            "medium": min(1.0, ema + 0.5 * avg_deviation),
            "high": min(1.0, ema + 1.0 * avg_deviation),
            "critical": min(1.0, ema + 1.5 * avg_deviation),
        }

    def _blend_thresholds(self, old: Dict[str, float], new: Dict[str, float]) -> Dict[str, float]:
        """Combina thresholds antigos e novos.

        Args:
            old: Thresholds atuais
            new: Novos thresholds calculados

        Returns:
            Thresholds ajustados parcialmente
        """
        blended = {}
        for key in ["medium", "high", "critical"]:
            old_val = old.get(key, 0.5)
            new_val = new.get(key, 0.5)
            # Ajuste parcial: move X% em direção ao novo valor
            blended[key] = old_val + (new_val - old_val) * self.adjustment_factor

        return blended

    def reset_to_base(self, domain: Optional[UnifiedDomain] = None):
        """Reseta thresholds para valores base."""
        domains = [domain] if domain else list(UnifiedDomain)

        for d in domains:
            self._current_thresholds[d.value] = self.base_config.get_thresholds(d).copy()
            logger.info("thresholds_reset_to_base", domain=d.value)

    def get_threshold_stats(self, domain: UnifiedDomain) -> Dict:
        """Retorna estatísticas sobre thresholds.

        Returns:
            Dict com current, base, last_adjustment, sample_count
        """
        return {
            "domain": domain.value,
            "current_thresholds": self._current_thresholds.get(domain.value, {}),
            "base_thresholds": self.base_config.get_thresholds(domain),
            "last_adjustment": self._last_adjustment.get(domain.value),
            "sample_count": len(self._history[domain.value]),
            "adjustment_strategy": self.adjustment_strategy,
        }

    def set_manual_threshold(
        self, domain: UnifiedDomain, level: str, value: float  # 'medium', 'high', 'critical'
    ):
        """Define manualmente um threshold específico.

        Args:
            domain: Domínio do threshold
            level: Nível do threshold
            value: Valor do threshold (0.0 a 1.0)
        """
        if domain.value not in self._current_thresholds:
            self._current_thresholds[domain.value] = self.base_config.get_thresholds(domain).copy()

        self._current_thresholds[domain.value][level] = value

        logger.info("manual_threshold_set", domain=domain.value, level=level, value=value)


class ThresholdViolation:
    """Representa uma violação de threshold."""

    def __init__(
        self,
        domain: UnifiedDomain,
        score: float,
        threshold_level: str,
        threshold_value: float,
        severity: str,
        timestamp: Optional[datetime] = None,
    ):
        self.domain = domain
        self.score = score
        self.threshold_level = threshold_level
        self.threshold_value = threshold_value
        self.severity = severity  # 'minor', 'major', 'critical'
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.delta = score - threshold_value

    def to_dict(self) -> Dict:
        """Converte para dicionário."""
        return {
            "domain": self.domain.value,
            "score": self.score,
            "threshold_level": self.threshold_level,
            "threshold_value": self.threshold_value,
            "severity": self.severity,
            "timestamp": self.timestamp.isoformat(),
            "delta": self.delta,
        }


class ThresholdMonitor:
    """Monitora violações de thresholds."""

    def __init__(self, dynamic_thresholds: DynamicThresholds):
        """Inicializa monitor.

        Args:
            dynamic_thresholds: Gerenciador de thresholds a monitorar
        """
        self.thresholds = dynamic_thresholds
        self._violations: List[ThresholdViolation] = []
        self._violation_counts: Dict[str, int] = {}

    def check_violation(self, domain: UnifiedDomain, score: float) -> Optional[ThresholdViolation]:
        """Verifica se score viola thresholds.

        Args:
            domain: Domínio do score
            score: Valor do score

        Returns:
            ThresholdViolation se violação detectada, None caso contrário
        """
        thresholds = self.thresholds.get_thresholds(domain)

        # Verificar do mais grave para o menos grave
        if score >= thresholds["critical"]:
            violation = ThresholdViolation(
                domain=domain,
                score=score,
                threshold_level="critical",
                threshold_value=thresholds["critical"],
                severity="critical",
            )
        elif score >= thresholds["high"]:
            violation = ThresholdViolation(
                domain=domain,
                score=score,
                threshold_level="high",
                threshold_value=thresholds["high"],
                severity="major",
            )
        elif score >= thresholds["medium"]:
            violation = ThresholdViolation(
                domain=domain,
                score=score,
                threshold_level="medium",
                threshold_value=thresholds["medium"],
                severity="minor",
            )
        else:
            return None

        self._violations.append(violation)
        key = f"{domain.value}_{violation.threshold_level}"
        self._violation_counts[key] = self._violation_counts.get(key, 0) + 1

        logger.warning(
            "threshold_violation_detected",
            domain=domain.value,
            score=score,
            threshold_level=violation.threshold_level,
            threshold_value=violation.threshold_value,
            delta=violation.delta,
        )

        return violation

    def get_violations(
        self,
        domain: Optional[UnifiedDomain] = None,
        since: Optional[datetime] = None,
        severity: Optional[str] = None,
    ) -> List[ThresholdViolation]:
        """Retorna violações filtradas.

        Args:
            domain: Filtrar por domínio
            since: Filtrar desde timestamp
            severity: Filtrar por severidade

        Returns:
            Lista de violações
        """
        violations = self._violations

        if domain:
            violations = [v for v in violations if v.domain == domain]

        if since:
            violations = [v for v in violations if v.timestamp >= since]

        if severity:
            violations = [v for v in violations if v.severity == severity]

        return violations

    def get_violation_stats(self) -> Dict:
        """Retorna estatísticas de violações."""
        return {
            "total_violations": len(self._violations),
            "counts_by_type": self._violation_counts.copy(),
            "last_violation": self._violations[-1].to_dict() if self._violations else None,
        }

    def clear_violations(self, before: Optional[datetime] = None):
        """Limpa violações antigas.

        Args:
            before: Limpar violações antes deste timestamp
        """
        if before:
            self._violations = [v for v in self._violations if v.timestamp >= before]
        else:
            self._violations = []

        # Recalcular contadores
        self._violation_counts = {}
        for v in self._violations:
            key = f"{v.domain.value}_{v.threshold_level}"
            self._violation_counts[key] = self._violation_counts.get(key, 0) + 1
