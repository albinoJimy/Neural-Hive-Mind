"""
Risk History

Histórico de scores para análise de tendências e padrões temporais.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Optional

import structlog

from neural_hive_domain import UnifiedDomain

from .config import RiskBand
from .models import RiskAssessment, RiskMatrix

logger = structlog.get_logger(__name__)


class TrendDirection(str, Enum):
    """Direção da tendência de risco."""

    IMPROVING = "improving"  # Risco diminuindo
    STABLE = "stable"  # Risco estável
    WORSENING = "worsening"  # Risco aumentando
    UNKNOWN = "unknown"


@dataclass
class RiskSnapshot:
    """Snapshot de risco em um ponto no tempo."""

    timestamp: datetime
    score: float
    band: RiskBand
    domain: UnifiedDomain
    entity_id: str
    factors: dict[str, float] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "score": self.score,
            "band": self.band.value,
            "domain": self.domain.value,
            "entity_id": self.entity_id,
            "factors": self.factors,
            "metadata": self.metadata,
        }


@dataclass
class TrendAnalysis:
    """Resultado da análise de tendência."""

    direction: TrendDirection
    strength: float  # 0.0 a 1.0, confiança na tendência
    start_score: float
    end_score: float
    delta: float
    delta_percentage: float
    period_hours: float
    volatility: float  # Desvio padrão normalizado
    sample_count: int


@dataclass
class AnomalyDetection:
    """Resultado da detecção de anomalia."""

    is_anomaly: bool
    score: float
    expected_range: tuple[float, float]
    deviation_std: float
    severity: str  # 'low', 'medium', 'high'
    timestamp: datetime


class RiskHistory:
    """Gerencia histórico de avaliações de risco."""

    def __init__(self, max_snapshots_per_entity: int = 1000, retention_days: int = 90):
        """Inicializa gerenciador de histórico.

        Args:
            max_snapshots_per_entity: Máximo de snapshots por entidade
            retention_days: Dias de retenção do histórico
        """
        self.max_snapshots = max_snapshots_per_entity
        self.retention_days = retention_days

        # Histórico: entity_id -> lista de snapshots ordenada por timestamp
        self._history: dict[str, list[RiskSnapshot]] = defaultdict(list)

        # Índices para consultas rápidas
        self._by_domain: dict[UnifiedDomain, list[str]] = defaultdict(list)
        self._by_time: dict[tuple[datetime, str], RiskSnapshot] = {}

    def record_assessment(
        self, assessment: RiskAssessment, entity_id: str, metadata: Optional[dict] = None
    ) -> RiskSnapshot:
        """Registra avaliação no histórico.

        Args:
            assessment: Avaliação de risco
            entity_id: ID da entidade
            metadata: Metadados adicionais

        Returns:
            RiskSnapshot criado
        """
        snapshot = RiskSnapshot(
            timestamp=assessment.assessed_at or datetime.now(UTC),
            score=assessment.score,
            band=assessment.band,
            domain=assessment.domain,
            entity_id=entity_id,
            factors=assessment.factors.copy(),
            metadata=metadata or {},
        )

        # Adicionar ao histórico
        snapshots = self._history[entity_id]
        snapshots.append(snapshot)

        # Manter ordenado por timestamp
        snapshots.sort(key=lambda s: s.timestamp)

        # Limitar tamanho
        if len(snapshots) > self.max_snapshots:
            snapshots = snapshots[-self.max_snapshots :]
            self._history[entity_id] = snapshots

        # Atualizar índices
        self._by_domain[assessment.domain].append(entity_id)
        self._by_time[(snapshot.timestamp, entity_id)] = snapshot

        # Limpar histórico antigo
        self._cleanup_old_snapshots(entity_id)

        logger.debug(
            "risk_assessment_recorded",
            entity_id=entity_id,
            domain=assessment.domain.value,
            score=assessment.score,
        )

        return snapshot

    def record_matrix(
        self, matrix: RiskMatrix, metadata: Optional[dict] = None
    ) -> list[RiskSnapshot]:
        """Registra matriz de risco (múltiplos domínios).

        Args:
            matrix: Matriz de risco
            metadata: Metadados adicionais

        Returns:
            Lista de snapshots criados
        """
        snapshots = []

        for domain, assessment in matrix.assessments.items():
            snapshot = self.record_assessment(
                assessment=assessment, entity_id=matrix.entity_id, metadata=metadata
            )
            snapshots.append(snapshot)

        return snapshots

    def get_history(
        self,
        entity_id: str,
        domain: Optional[UnifiedDomain] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[RiskSnapshot]:
        """Retorna histórico filtrado.

        Args:
            entity_id: ID da entidade
            domain: Filtrar por domínio
            start: Timestamp inicial
            end: Timestamp final
            limit: Limite de resultados

        Returns:
            Lista de snapshots
        """
        snapshots = self._history.get(entity_id, [])

        if domain:
            snapshots = [s for s in snapshots if s.domain == domain]

        if start:
            snapshots = [s for s in snapshots if s.timestamp >= start]

        if end:
            snapshots = [s for s in snapshots if s.timestamp <= end]

        if limit:
            snapshots = snapshots[-limit:]

        return snapshots

    def get_latest(
        self, entity_id: str, domain: Optional[UnifiedDomain] = None
    ) -> Optional[RiskSnapshot]:
        """Retorna snapshot mais recente.

        Args:
            entity_id: ID da entidade
            domain: Filtrar por domínio

        Returns:
            Snapshot mais recente ou None
        """
        snapshots = self.get_history(entity_id, domain, limit=1)
        return snapshots[0] if snapshots else None

    def analyze_trend(
        self,
        entity_id: str,
        domain: Optional[UnifiedDomain] = None,
        window_hours: float = 24.0,
        min_samples: int = 3,
    ) -> Optional[TrendAnalysis]:
        """Analisa tendência de risco.

        Args:
            entity_id: ID da entidade
            domain: Filtrar por domínio
            window_hours: Janela de tempo em horas
            min_samples: Mínimo de amostras necessárias

        Returns:
            TrendAnalysis ou None se dados insuficientes
        """
        # Buscar snapshots na janela
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(hours=window_hours)

        snapshots = self.get_history(
            entity_id=entity_id, domain=domain, start=start_time, end=end_time
        )

        if len(snapshots) < min_samples:
            logger.debug(
                "insufficient_samples_for_trend",
                entity_id=entity_id,
                samples=len(snapshots),
                required=min_samples,
            )
            return None

        # Extrair scores e timestamps
        scores = [s.score for s in snapshots]
        timestamps = [s.timestamp for s in snapshots]

        start_score = scores[0]
        end_score = scores[-1]
        delta = end_score - start_score
        delta_percentage = (delta / start_score * 100) if start_score > 0 else 0

        # Calcular direção usando regressão linear simples
        direction = self._calculate_trend_direction(scores, timestamps)

        # Calcular força da tendência (correlação)
        strength = self._calculate_trend_strength(scores, timestamps)

        # Calcular volatilidade (desvio padrão normalizado)
        volatility = self._calculate_volatility(scores)

        # Período em horas
        period_hours = (timestamps[-1] - timestamps[0]).total_seconds() / 3600

        return TrendAnalysis(
            direction=direction,
            strength=strength,
            start_score=start_score,
            end_score=end_score,
            delta=delta,
            delta_percentage=delta_percentage,
            period_hours=period_hours,
            volatility=volatility,
            sample_count=len(scores),
        )

    def _calculate_trend_direction(
        self, scores: list[float], timestamps: list[datetime]
    ) -> TrendDirection:
        """Calcula direção da tendência."""
        if len(scores) < 2:
            return TrendDirection.UNKNOWN

        # Regressão linear simples
        n = len(scores)
        x = [(ts - timestamps[0]).total_seconds() for ts in timestamps]
        y = scores

        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)

        # Slope (coeficiente angular)
        if sum_x2 == 0:
            return TrendDirection.UNKNOWN

        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)

        # Classificar direção
        if abs(slope) < 1e-6:
            return TrendDirection.STABLE
        elif slope > 0:
            return TrendDirection.WORSENING  # Risco aumentando
        else:
            return TrendDirection.IMPROVING  # Risco diminuindo

    def _calculate_trend_strength(self, scores: list[float], timestamps: list[datetime]) -> float:
        """Calcula força da tendência (correlação de Pearson).

        Returns:
            0.0 (sem correlação) a 1.0 (correlação perfeita)
        """
        if len(scores) < 3:
            return 0.0

        n = len(scores)
        x = [(ts - timestamps[0]).total_seconds() for ts in timestamps]
        y = scores

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        # Covariância e desvios
        covariance = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        var_x = sum((xi - mean_x) ** 2 for xi in x)
        var_y = sum((yi - mean_y) ** 2 for yi in y)

        if var_x == 0 or var_y == 0:
            return 0.0

        # Correlação de Pearson
        correlation = covariance / (var_x * var_y) ** 0.5

        return abs(correlation)

    def _calculate_volatility(self, scores: list[float]) -> float:
        """Calcula volatilidade normalizada.

        Returns:
            0.0 (estável) a 1.0 (muito volátil)
        """
        if len(scores) < 2:
            return 0.0

        mean_score = sum(scores) / len(scores)
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
        std_dev = variance**0.5

        # Normalizar por range (scores são 0-1)
        return min(1.0, std_dev)

    def detect_anomaly(
        self,
        entity_id: str,
        domain: Optional[UnifiedDomain] = None,
        std_threshold: float = 2.5,
        lookback_hours: float = 168.0,  # 7 dias
    ) -> Optional[AnomalyDetection]:
        """Detecta anomalia no score mais recente.

        Args:
            entity_id: ID da entidade
            domain: Filtrar por domínio
            std_threshold: Limite em desvios padrão
            lookback_hours: Horas para lookback histórico

        Returns:
            AnomalyDetection ou None se não for anomalia
        """
        # Buscar histórico
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(hours=lookback_hours)

        snapshots = self.get_history(
            entity_id=entity_id, domain=domain, start=start_time, end=end_time
        )

        if len(snapshots) < 3:
            return None

        # Separar histórico e atual
        historical = snapshots[:-1]
        current = snapshots[-1]

        # Calcular estatísticas do histórico
        scores = [s.score for s in historical]
        mean_score = sum(scores) / len(scores)

        # Desvio padrão
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
        std_dev = variance**0.5

        # Range esperado
        expected_min = max(0.0, mean_score - std_threshold * std_dev)
        expected_max = min(1.0, mean_score + std_threshold * std_dev)

        # Verificar se é anomalia
        is_anomaly = current.score < expected_min or current.score > expected_max
        deviation_std = (current.score - mean_score) / std_dev if std_dev > 0 else 0

        # Severidade baseada em desvios
        if abs(deviation_std) >= 4:
            severity = "high"
        elif abs(deviation_std) >= 2.5:
            severity = "medium"
        else:
            severity = "low"

        if is_anomaly:
            logger.warning(
                "risk_anomaly_detected",
                entity_id=entity_id,
                current_score=current.score,
                expected_range=(expected_min, expected_max),
                deviation_std=deviation_std,
                severity=severity,
            )

        return AnomalyDetection(
            is_anomaly=is_anomaly,
            score=current.score,
            expected_range=(expected_min, expected_max),
            deviation_std=deviation_std,
            severity=severity,
            timestamp=current.timestamp,
        )

    def get_percentile(
        self, entity_id: str, domain: Optional[UnifiedDomain] = None, score: Optional[float] = None
    ) -> float:
        """Retorna percentil de um score em relação ao histórico.

        Args:
            entity_id: ID da entidade
            domain: Filtrar por domínio
            score: Score a avaliar (padrão: mais recente)

        Returns:
            Percentil (0.0 a 1.0)
        """
        snapshots = self.get_history(entity_id, domain)

        if not snapshots:
            return 0.5

        if score is None:
            latest = snapshots[-1]
            score = latest.score

        scores = [s.score for s in snapshots]
        scores_sorted = sorted(scores)

        # Encontrar posição
        position = sum(1 for s in scores_sorted if s <= score)
        percentile = position / len(scores_sorted)

        return percentile

    def get_statistics(
        self,
        entity_id: str,
        domain: Optional[UnifiedDomain] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> dict:
        """Retorna estatísticas do histórico.

        Args:
            entity_id: ID da entidade
            domain: Filtrar por domínio
            start: Timestamp inicial
            end: Timestamp final

        Returns:
            Dict com estatísticas
        """
        snapshots = self.get_history(entity_id, domain, start, end)

        if not snapshots:
            return {"count": 0, "mean": None, "min": None, "max": None, "std_dev": None}

        scores = [s.score for s in snapshots]

        mean_score = sum(scores) / len(scores)
        min_score = min(scores)
        max_score = max(scores)

        # Desvio padrão
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
        std_dev = variance**0.5

        return {
            "count": len(scores),
            "mean": mean_score,
            "min": min_score,
            "max": max_score,
            "std_dev": std_dev,
            "first_timestamp": snapshots[0].timestamp.isoformat(),
            "last_timestamp": snapshots[-1].timestamp.isoformat(),
        }

    def _cleanup_old_snapshots(self, entity_id: str):
        """Remove snapshots antigos além da retenção."""
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        snapshots = self._history.get(entity_id, [])

        # Manter apenas snapshots recentes
        self._history[entity_id] = [s for s in snapshots if s.timestamp >= cutoff]

    def cleanup_all(self):
        """Limpa snapshots antigos de todas as entidades."""
        for entity_id in list(self._history.keys()):
            self._cleanup_old_snapshots(entity_id)

        logger.info("risk_history_cleanup_completed")

    def get_entity_ids(self, domain: Optional[UnifiedDomain] = None) -> list[str]:
        """Retorna IDs de entidades com histórico.

        Args:
            domain: Filtrar por domínio

        Returns:
            Lista de entity_ids
        """
        if domain:
            return list(set(self._by_domain.get(domain, [])))
        else:
            return list(self._history.keys())
