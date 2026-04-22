"""
Risk Ensemble

Combinação de múltiplos modelos de avaliação de risco para decisão robusta.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from statistics import mean, median, stdev
from typing import Any, Optional

import structlog

from neural_hive_domain import UnifiedDomain

from .config import RiskBand, RiskScoringConfig
from .models import RiskAssessment

logger = structlog.get_logger(__name__)


class EnsembleMethod(str, Enum):
    """Métodos de ensemble."""

    MAJORITY_VOTE = "majority_vote"  # Votação por majority
    WEIGHTED_AVERAGE = "weighted_average"  # Média ponderada
    STACKING = "stacking"  # Stacking com meta-modelo
    BORDA_COUNT = "borda_count"  # Contagem Borda
    BUCKET_VOTE = "bucket_vote"  # Votação por buckets
    CONFIDENCE_WEIGHTED = "confidence_weighted"  # Ponderado por confiança


class RiskModel:
    """Representa um modelo de risco no ensemble."""

    def __init__(
        self,
        name: str,
        assessor: Callable,
        weight: float = 1.0,
        domains: Optional[list[UnifiedDomain]] = None,
        metadata: Optional[dict] = None,
    ):
        """Inicializa modelo.

        Args:
            name: Nome do modelo
            assessor: Função que retorna RiskAssessment
            weight: Peso no ensemble (0.0 a 1.0)
            domains: Domínios suportados
            metadata: Metadados do modelo
        """
        self.name = name
        self.assessor = assessor
        self.weight = weight
        self.domains = domains or list(UnifiedDomain)
        self.metadata = metadata or {}

        # Estatísticas de performance
        self._accuracy_history: list[float] = []
        self._call_count = 0

    def assess(self, entity: dict[str, Any], domain: UnifiedDomain) -> Optional[RiskAssessment]:
        """Executa avaliação.

        Args:
            entity: Entidade a avaliar
            domain: Domínio de avaliação

        Returns:
            RiskAssessment ou None se domínio não suportado
        """
        if domain not in self.domains:
            return None

        try:
            result = self.assessor(entity, domain)
            self._call_count += 1
            return result
        except Exception as e:
            logger.error(
                "model_assessment_failed", model=self.name, domain=domain.value, error=str(e)
            )
            return None

    def record_accuracy(self, accuracy: float):
        """Registra acurácia do modelo."""
        self._accuracy_history.append(accuracy)
        # Manter apenas últimas 100 medições
        if len(self._accuracy_history) > 100:
            self._accuracy_history = self._accuracy_history[-100:]

    def get_accuracy(self) -> Optional[float]:
        """Retorna acurácia média do modelo."""
        if not self._accuracy_history:
            return None
        return mean(self._accuracy_history)


@dataclass
class EnsembleResult:
    """Resultado do ensemble."""

    entity_id: str
    domain: UnifiedDomain
    final_score: float
    final_band: RiskBand
    method: EnsembleMethod
    model_count: int
    model_votes: dict[str, tuple[float, RiskBand]]  # model -> (score, band)
    confidence: float  # 0.0 a 1.0, quão confidente o ensemble está
    consensus_level: float  # 0.0 a 1.0, quão de acordo estão os modelos
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "entity_id": self.entity_id,
            "domain": self.domain.value,
            "final_score": self.final_score,
            "final_band": self.final_band.value,
            "method": self.method.value,
            "model_count": self.model_count,
            "model_votes": {
                name: {"score": score, "band": band.value}
                for name, (score, band) in self.model_votes.items()
            },
            "confidence": self.confidence,
            "consensus_level": self.consensus_level,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class RiskEnsemble:
    """Combina múltiplos modelos para decisão robusta."""

    def __init__(
        self,
        method: EnsembleMethod = EnsembleMethod.WEIGHTED_AVERAGE,
        config: Optional[RiskScoringConfig] = None,
        min_models: int = 2,
        fallback_to_default: bool = True,
    ):
        """Inicializa ensemble.

        Args:
            method: Método de combinação
            config: Configuração base de thresholds
            min_models: Mínimo de modelos para decisão
            fallback_to_default: Usa padrão se modelos insuficientes
        """
        self.method = method
        self.config = config
        self.min_models = min_models
        self.fallback_to_default = fallback_to_default

        self._models: list[RiskModel] = []

    def add_model(self, model: RiskModel):
        """Adiciona modelo ao ensemble.

        Args:
            model: Modelo a adicionar
        """
        self._models.append(model)
        logger.info("model_added_to_ensemble", model_name=model.name, total=len(self._models))

    def remove_model(self, model_name: str):
        """Remove modelo do ensemble.

        Args:
            model_name: Nome do modelo a remover
        """
        self._models = [m for m in self._models if m.name != model_name]
        logger.info("model_removed_from_ensemble", model_name=model_name)

    def assess(
        self, entity: dict[str, Any], domain: UnifiedDomain, entity_id: str
    ) -> EnsembleResult:
        """Avalia usando ensemble de modelos.

        Args:
            entity: Entidade a avaliar
            domain: Domínio de avaliação
            entity_id: ID da entidade

        Returns:
            EnsembleResult com decisão combinada
        """
        # Coletar avaliações de todos os modelos
        model_votes: dict[str, tuple[float, RiskBand]] = {}

        for model in self._models:
            assessment = model.assess(entity, domain)
            if assessment:
                model_votes[model.name] = (assessment.score, assessment.band)

        # Verificar se temos modelos suficientes
        if len(model_votes) < self.min_models:
            if self.fallback_to_default:
                logger.warning(
                    "insufficient_models_falling_back",
                    available=len(model_votes),
                    required=self.min_models,
                )
                return self._fallback_result(entity_id, domain, model_votes)
            else:
                raise ValueError(f"Modelos insuficientes: {len(model_votes)} < {self.min_models}")

        # Aplicar método de ensemble
        if self.method == EnsembleMethod.MAJORITY_VOTE:
            final_score, final_band = self._majority_vote(model_votes)
        elif self.method == EnsembleMethod.WEIGHTED_AVERAGE:
            final_score, final_band = self._weighted_average(model_votes)
        elif self.method == EnsembleMethod.STACKING:
            final_score, final_band = self._stacking(model_votes, entity, domain)
        elif self.method == EnsembleMethod.BORDA_COUNT:
            final_score, final_band = self._borda_count(model_votes)
        elif self.method == EnsembleMethod.BUCKET_VOTE:
            final_score, final_band = self._bucket_vote(model_votes)
        elif self.method == EnsembleMethod.CONFIDENCE_WEIGHTED:
            final_score, final_band = self._confidence_weighted(model_votes)
        else:
            final_score, final_band = self._weighted_average(model_votes)

        # Calcular confiança e consenso
        confidence = self._calculate_confidence(model_votes, final_score)
        consensus = self._calculate_consensus(model_votes)

        result = EnsembleResult(
            entity_id=entity_id,
            domain=domain,
            final_score=final_score,
            final_band=final_band,
            method=self.method,
            model_count=len(model_votes),
            model_votes=model_votes,
            confidence=confidence,
            consensus_level=consensus,
        )

        logger.info(
            "ensemble_assessment_completed",
            entity_id=entity_id,
            domain=domain.value,
            final_score=final_score,
            final_band=final_band.value,
            model_count=len(model_votes),
            consensus=consensus,
        )

        return result

    def _majority_vote(
        self, model_votes: dict[str, tuple[float, RiskBand]]
    ) -> tuple[float, RiskBand]:
        """Votação por maioria (band)."""
        # Contar votos por band
        band_counts: dict[RiskBand, int] = {}
        for score, band in model_votes.values():
            band_counts[band] = band_counts.get(band, 0) + 1

        # Encontrar banda com mais votos
        winning_band = max(band_counts.items(), key=lambda x: x[1])[0]

        # Média dos scores dos modelos que votaram na banda vencedora
        winning_scores = [score for score, band in model_votes.values() if band == winning_band]
        final_score = mean(winning_scores) if winning_scores else 0.5

        return final_score, winning_band

    def _weighted_average(
        self, model_votes: dict[str, tuple[float, RiskBand]]
    ) -> tuple[float, RiskBand]:
        """Média ponderada dos scores."""
        # Buscar pesos dos modelos
        models_dict = {m.name: m for m in self._models}

        weighted_sum = 0.0
        total_weight = 0.0

        for model_name, (score, band) in model_votes.items():
            model = models_dict.get(model_name)
            if model:
                weight = model.weight
                weighted_sum += score * weight
                total_weight += weight

        final_score = weighted_sum / total_weight if total_weight > 0 else 0.5

        # Classificar band
        if self.config:
            thresholds = self.config.get_thresholds(list(model_votes.values())[0][1])
            if final_score >= thresholds["critical"]:
                final_band = RiskBand.CRITICAL
            elif final_score >= thresholds["high"]:
                final_band = RiskBand.HIGH
            elif final_score >= thresholds["medium"]:
                final_band = RiskBand.MEDIUM
            else:
                final_band = RiskBand.LOW
        else:
            # Thresholds padrão
            if final_score >= 0.85:
                final_band = RiskBand.CRITICAL
            elif final_score >= 0.65:
                final_band = RiskBand.HIGH
            elif final_score >= 0.40:
                final_band = RiskBand.MEDIUM
            else:
                final_band = RiskBand.LOW

        return final_score, final_band

    def _stacking(
        self,
        model_votes: dict[str, tuple[float, RiskBand]],
        entity: dict[str, Any],
        domain: UnifiedDomain,
    ) -> tuple[float, RiskBand]:
        """Stacking: usa meta-modelo simples para combinar."""
        # Meta-modelo simples: média ponderada por acurácia histórica
        models_dict = {m.name: m for m in self._models}

        weighted_sum = 0.0
        total_weight = 0.0

        for model_name, (score, band) in model_votes.items():
            model = models_dict.get(model_name)
            if model:
                # Peso = peso base * acurácia (se disponível)
                accuracy = model.get_accuracy()
                weight = model.weight * (accuracy or 0.8)
                weighted_sum += score * weight
                total_weight += weight

        final_score = weighted_sum / total_weight if total_weight > 0 else 0.5

        # Classificar band
        if self.config:
            thresholds = self.config.get_thresholds(domain)
            if final_score >= thresholds["critical"]:
                final_band = RiskBand.CRITICAL
            elif final_score >= thresholds["high"]:
                final_band = RiskBand.HIGH
            elif final_score >= thresholds["medium"]:
                final_band = RiskBand.MEDIUM
            else:
                final_band = RiskBand.LOW
        else:
            if final_score >= 0.85:
                final_band = RiskBand.CRITICAL
            elif final_score >= 0.65:
                final_band = RiskBand.HIGH
            elif final_score >= 0.40:
                final_band = RiskBand.MEDIUM
            else:
                final_band = RiskBand.LOW

        return final_score, final_band

    def _borda_count(
        self, model_votes: dict[str, tuple[float, RiskBand]]
    ) -> tuple[float, RiskBand]:
        """Contagem Borda: cada modelo dá pontos para cada band."""
        # Ordem de bands (do menor para o maior risco)
        band_order = [RiskBand.LOW, RiskBand.MEDIUM, RiskBand.HIGH, RiskBand.CRITICAL]

        # Pontos por posição
        points: dict[RiskBand, int] = {band: 0 for band in band_order}

        for score, band in model_votes.values():
            # Dar pontos baseado na posição
            for i, b in enumerate(band_order):
                if b == band:
                    # Mais pontos para bands mais "altas" na ordem
                    points[b] += i

        # Band com mais pontos
        winning_band = max(points.items(), key=lambda x: x[1])[0]

        # Média dos scores
        final_score = mean(score for score, _ in model_votes.values())

        return final_score, winning_band

    def _bucket_vote(
        self, model_votes: dict[str, tuple[float, RiskBand]]
    ) -> tuple[float, RiskBand]:
        """Votação por buckets de score."""
        # Criar buckets de score
        buckets = {
            RiskBand.LOW: (0.0, 0.4),
            RiskBand.MEDIUM: (0.4, 0.65),
            RiskBand.HIGH: (0.65, 0.85),
            RiskBand.CRITICAL: (0.85, 1.0),
        }

        # Contar votos em buckets
        bucket_counts: dict[RiskBand, int] = {band: 0 for band in buckets.keys()}

        for score, _ in model_votes.values():
            for band, (low, high) in buckets.items():
                if low <= score < high:
                    bucket_counts[band] += 1
                    break
            else:
                # Score no limite superior
                bucket_counts[RiskBand.CRITICAL] += 1

        # Bucket com mais votos
        winning_band = max(bucket_counts.items(), key=lambda x: x[1])[0]

        # Média dos scores
        final_score = mean(score for score, _ in model_votes.values())

        return final_score, winning_band

    def _confidence_weighted(
        self, model_votes: dict[str, tuple[float, RiskBand]]
    ) -> tuple[float, RiskBand]:
        """Ponderação por confiança (baseado em variância)."""
        # Usar mediana como baseline
        scores = [score for score, _ in model_votes.values()]
        median_score = median(scores)

        # Calcular confiança de cada modelo (inverso da distância da mediana)
        models_dict = {m.name: m for m in self._models}

        weighted_sum = 0.0
        total_weight = 0.0

        for model_name, (score, band) in model_votes.items():
            model = models_dict.get(model_name)
            if model:
                # Confiança = peso / (1 + distância da mediana)
                distance = abs(score - median_score)
                confidence = 1.0 / (1.0 + distance)
                weight = model.weight * confidence
                weighted_sum += score * weight
                total_weight += weight

        final_score = weighted_sum / total_weight if total_weight > 0 else median_score

        # Classificar band
        if self.config:
            thresholds = self.config.get_thresholds(list(model_votes.values())[0][1])
            if final_score >= thresholds["critical"]:
                final_band = RiskBand.CRITICAL
            elif final_score >= thresholds["high"]:
                final_band = RiskBand.HIGH
            elif final_score >= thresholds["medium"]:
                final_band = RiskBand.MEDIUM
            else:
                final_band = RiskBand.LOW
        else:
            if final_score >= 0.85:
                final_band = RiskBand.CRITICAL
            elif final_score >= 0.65:
                final_band = RiskBand.HIGH
            elif final_score >= 0.40:
                final_band = RiskBand.MEDIUM
            else:
                final_band = RiskBand.LOW

        return final_score, final_band

    def _calculate_confidence(
        self, model_votes: dict[str, tuple[float, RiskBand]], final_score: float
    ) -> float:
        """Calcula confiança do ensemble (inverso da variância)."""
        scores = [score for score, _ in model_votes.values()]

        if len(scores) < 2:
            return 1.0

        # Desvio padrão
        std = stdev(scores)

        # Confiança = 1 - (desvio padrão normalizado)
        # Std máximo teórico é 0.5 (range 0-1)
        confidence = max(0.0, 1.0 - (std / 0.5))

        return confidence

    def _calculate_consensus(self, model_votes: dict[str, tuple[float, RiskBand]]) -> float:
        """Calcula nível de consenso entre modelos.

        Returns:
            0.0 (discordância total) a 1.0 (consenso total)
        """
        if not model_votes:
            return 0.0

        # Consenso de band: todos na mesma band = 1.0
        bands = [band for _, band in model_votes.values()]
        unique_bands = set(bands)

        if len(unique_bands) == 1:
            return 1.0

        # Penalizar por bands diferentes
        band_penalty = len(unique_bands) / 4.0  # Máximo 4 bands

        # Consenso de score: desvio padrão
        scores = [score for score, _ in model_votes.values()]
        if len(scores) >= 2:
            std = stdev(scores)
            score_consensus = max(0.0, 1.0 - (std / 0.5))
        else:
            score_consensus = 1.0

        # Combinar
        consensus = (score_consensus + (1.0 - band_penalty)) / 2.0

        return max(0.0, min(1.0, consensus))

    def _fallback_result(
        self, entity_id: str, domain: UnifiedDomain, model_votes: dict[str, tuple[float, RiskBand]]
    ) -> EnsembleResult:
        """Resultado de fallback quando modelos insuficientes."""
        if model_votes:
            # Usar primeiro disponível
            score, band = list(model_votes.values())[0]
            final_score = score
            final_band = band
        else:
            # Default médio
            final_score = 0.5
            final_band = RiskBand.MEDIUM

        return EnsembleResult(
            entity_id=entity_id,
            domain=domain,
            final_score=final_score,
            final_band=final_band,
            method=self.method,
            model_count=len(model_votes),
            model_votes=model_votes,
            confidence=0.0,
            consensus_level=0.0,
            metadata={"fallback": True},
        )

    def get_model_stats(self) -> list[dict]:
        """Retorna estatísticas de todos os modelos."""
        stats = []

        for model in self._models:
            stats.append(
                {
                    "name": model.name,
                    "weight": model.weight,
                    "domains": [d.value for d in model.domains],
                    "call_count": model._call_count,
                    "accuracy": model.get_accuracy(),
                    "metadata": model.metadata,
                }
            )

        return stats

    def reweight_by_accuracy(self):
        """Reajusta pesos baseado na acurácia histórica."""
        total_accuracy = 0.0

        # Somar acurácias
        for model in self._models:
            accuracy = model.get_accuracy()
            if accuracy is not None:
                total_accuracy += accuracy

        # Reajustar pesos
        if total_accuracy > 0:
            for model in self._models:
                accuracy = model.get_accuracy()
                if accuracy is not None:
                    model.weight = accuracy / total_accuracy

            logger.info("model_weights_recalculated", total_accuracy=total_accuracy)
