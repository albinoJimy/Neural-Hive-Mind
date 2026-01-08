"""
Model Ensemble para Online Learning.

Combina modelos batch e online usando diferentes estratégias de agregação
para produzir predições finais com maior robustez.
"""

import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple, Callable
import structlog
import numpy as np
from functools import lru_cache
from prometheus_client import Counter, Histogram, Gauge

from .config import OnlineLearningConfig
from .incremental_learner import IncrementalLearner

logger = structlog.get_logger(__name__)

# Métricas Prometheus
ensemble_predictions_total = Counter(
    'neural_hive_ensemble_predictions_total',
    'Total de predições do ensemble',
    ['specialist_type', 'strategy']
)
ensemble_prediction_duration = Histogram(
    'neural_hive_ensemble_prediction_duration_seconds',
    'Duração de predições do ensemble',
    ['specialist_type']
)
ensemble_batch_contribution = Gauge(
    'neural_hive_ensemble_batch_contribution',
    'Contribuição do modelo batch',
    ['specialist_type']
)
ensemble_online_contribution = Gauge(
    'neural_hive_ensemble_online_contribution',
    'Contribuição do modelo online',
    ['specialist_type']
)
ensemble_fallback_total = Counter(
    'neural_hive_ensemble_fallback_total',
    'Total de fallbacks para batch model',
    ['specialist_type', 'reason']
)


class ModelEnsemble:
    """
    Combina modelos batch e online em um ensemble.

    Estratégias suportadas:
    - weighted_average: Média ponderada das probabilidades
    - stacking: Meta-modelo que aprende a combinar
    - dynamic_routing: Roteamento baseado em confiança

    Features:
    - Pesos adaptativos baseados em performance recente
    - Fallback automático para batch se online degradar
    - Cache de predições para reduzir latência
    """

    STRATEGIES = ['weighted_average', 'stacking', 'dynamic_routing']

    def __init__(
        self,
        config: OnlineLearningConfig,
        specialist_type: str,
        batch_model: Any,
        online_learner: Optional[IncrementalLearner] = None,
        meta_model: Optional[Any] = None
    ):
        """
        Inicializa ModelEnsemble.

        Args:
            config: Configuração de online learning
            specialist_type: Tipo do especialista
            batch_model: Modelo batch (baseline)
            online_learner: Learner incremental (opcional)
            meta_model: Meta-modelo para stacking (opcional)
        """
        self.config = config
        self.specialist_type = specialist_type
        self.batch_model = batch_model
        self.online_learner = online_learner
        self.meta_model = meta_model

        # Pesos do ensemble
        self._batch_weight = config.batch_model_weight
        self._online_weight = config.online_model_weight

        # Histórico de performance para pesos dinâmicos
        self._batch_performance_history: List[Dict[str, Any]] = []
        self._online_performance_history: List[Dict[str, Any]] = []

        # Cache de predições
        self._prediction_cache: Dict[str, Tuple[np.ndarray, datetime]] = {}
        self._cache_ttl_seconds = 300  # 5 minutos

        # Estatísticas
        self._prediction_count = 0
        self._fallback_count = 0

        logger.info(
            "model_ensemble_initialized",
            specialist_type=specialist_type,
            strategy=config.ensemble_strategy,
            batch_weight=self._batch_weight,
            online_weight=self._online_weight
        )

    def _get_cache_key(self, X: np.ndarray) -> str:
        """Gera chave de cache para features."""
        return str(hash(X.tobytes()))

    def _check_cache(self, cache_key: str) -> Optional[np.ndarray]:
        """Verifica cache e retorna predição se válida."""
        if cache_key not in self._prediction_cache:
            return None

        cached_pred, cached_time = self._prediction_cache[cache_key]
        if datetime.utcnow() - cached_time > timedelta(seconds=self._cache_ttl_seconds):
            del self._prediction_cache[cache_key]
            return None

        return cached_pred

    def _update_cache(self, cache_key: str, prediction: np.ndarray):
        """Atualiza cache de predições."""
        self._prediction_cache[cache_key] = (prediction, datetime.utcnow())

        # Limpar cache se muito grande
        if len(self._prediction_cache) > 10000:
            # Remover entradas mais antigas
            sorted_keys = sorted(
                self._prediction_cache.keys(),
                key=lambda k: self._prediction_cache[k][1]
            )
            for key in sorted_keys[:5000]:
                del self._prediction_cache[key]

    def _predict_batch(self, X: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Executa predição com modelo batch.

        Returns:
            Tuple (probabilidades, latência_ms)
        """
        start = time.perf_counter()
        probas = self.batch_model.predict_proba(X)
        latency_ms = (time.perf_counter() - start) * 1000
        return probas, latency_ms

    def _predict_online(self, X: np.ndarray) -> Tuple[Optional[np.ndarray], float]:
        """
        Executa predição com modelo online.

        Returns:
            Tuple (probabilidades ou None se falhar, latência_ms)
        """
        if self.online_learner is None or not self.online_learner.is_fitted:
            return None, 0.0

        start = time.perf_counter()
        try:
            probas = self.online_learner.predict_proba(X)
            latency_ms = (time.perf_counter() - start) * 1000
            return probas, latency_ms
        except Exception as e:
            logger.warning(
                "online_prediction_failed",
                specialist_type=self.specialist_type,
                error=str(e)
            )
            return None, 0.0

    def _weighted_average(
        self,
        batch_probas: np.ndarray,
        online_probas: Optional[np.ndarray]
    ) -> np.ndarray:
        """
        Combina predições via média ponderada.

        Args:
            batch_probas: Probabilidades do modelo batch
            online_probas: Probabilidades do modelo online (pode ser None)

        Returns:
            Probabilidades combinadas
        """
        if online_probas is None:
            return batch_probas

        combined = (
            self._batch_weight * batch_probas +
            self._online_weight * online_probas
        )

        # Normalizar para garantir distribuição válida
        combined = combined / combined.sum(axis=1, keepdims=True)
        return combined

    def _dynamic_routing(
        self,
        X: np.ndarray,
        batch_probas: np.ndarray,
        online_probas: Optional[np.ndarray]
    ) -> np.ndarray:
        """
        Roteamento dinâmico baseado em confiança.

        Para cada amostra, escolhe modelo com maior confiança
        (max probabilidade) ponderada pelo peso do modelo.

        Args:
            X: Features de entrada
            batch_probas: Probabilidades do batch
            online_probas: Probabilidades do online (pode ser None)

        Returns:
            Probabilidades combinadas
        """
        if online_probas is None:
            return batch_probas

        # Calcular confiança de cada modelo
        batch_confidence = np.max(batch_probas, axis=1) * self._batch_weight
        online_confidence = np.max(online_probas, axis=1) * self._online_weight

        # Criar máscara de roteamento
        use_online = online_confidence > batch_confidence

        # Combinar predições
        combined = np.where(
            use_online[:, np.newaxis],
            online_probas,
            batch_probas
        )

        return combined

    def _stacking(
        self,
        X: np.ndarray,
        batch_probas: np.ndarray,
        online_probas: Optional[np.ndarray]
    ) -> np.ndarray:
        """
        Combina predições via meta-modelo (stacking).

        Args:
            X: Features originais
            batch_probas: Probabilidades do batch
            online_probas: Probabilidades do online (pode ser None)

        Returns:
            Probabilidades do meta-modelo
        """
        if self.meta_model is None:
            logger.warning(
                "stacking_no_meta_model",
                specialist_type=self.specialist_type
            )
            return self._weighted_average(batch_probas, online_probas)

        if online_probas is None:
            online_probas = np.zeros_like(batch_probas)

        # Criar features para meta-modelo
        # Concatena probabilidades de ambos modelos
        meta_features = np.concatenate([batch_probas, online_probas], axis=1)

        try:
            return self.meta_model.predict_proba(meta_features)
        except Exception as e:
            logger.error(
                "stacking_meta_model_failed",
                specialist_type=self.specialist_type,
                error=str(e)
            )
            return self._weighted_average(batch_probas, online_probas)

    def predict_proba(
        self,
        X: np.ndarray,
        use_cache: bool = True
    ) -> np.ndarray:
        """
        Executa predição do ensemble.

        Args:
            X: Features de entrada
            use_cache: Se deve usar cache

        Returns:
            Probabilidades combinadas
        """
        start_time = time.perf_counter()
        X = np.asarray(X)

        # Verificar cache
        if use_cache:
            cache_key = self._get_cache_key(X)
            cached = self._check_cache(cache_key)
            if cached is not None:
                return cached

        # Predição batch (sempre disponível)
        batch_probas, batch_latency = self._predict_batch(X)

        # Predição online (pode falhar)
        online_probas, online_latency = self._predict_online(X)

        # Verificar se deve usar fallback
        use_fallback = False
        if online_probas is None:
            use_fallback = True
            fallback_reason = 'online_unavailable'
        elif self.config.fallback_to_batch_on_online_failure:
            # Verificar qualidade do online
            online_confidence = np.mean(np.max(online_probas, axis=1))
            batch_confidence = np.mean(np.max(batch_probas, axis=1))

            if online_confidence < batch_confidence * 0.5:
                use_fallback = True
                fallback_reason = 'low_confidence'

        # Combinar predições
        if use_fallback:
            combined = batch_probas
            self._fallback_count += 1
            ensemble_fallback_total.labels(
                specialist_type=self.specialist_type,
                reason=fallback_reason
            ).inc()
        else:
            strategy = self.config.ensemble_strategy

            if strategy == 'weighted_average':
                combined = self._weighted_average(batch_probas, online_probas)
            elif strategy == 'dynamic_routing':
                combined = self._dynamic_routing(X, batch_probas, online_probas)
            elif strategy == 'stacking':
                combined = self._stacking(X, batch_probas, online_probas)
            else:
                combined = self._weighted_average(batch_probas, online_probas)

        # Atualizar cache
        if use_cache:
            self._update_cache(cache_key, combined)

        # Emitir métricas
        duration = time.perf_counter() - start_time
        self._prediction_count += 1

        ensemble_predictions_total.labels(
            specialist_type=self.specialist_type,
            strategy=self.config.ensemble_strategy
        ).inc()
        ensemble_prediction_duration.labels(
            specialist_type=self.specialist_type
        ).observe(duration)

        return combined

    def predict(self, X: np.ndarray, use_cache: bool = True) -> np.ndarray:
        """
        Executa predição de classes.

        Args:
            X: Features de entrada
            use_cache: Se deve usar cache

        Returns:
            Classes preditas
        """
        probas = self.predict_proba(X, use_cache=use_cache)
        return np.argmax(probas, axis=1)

    def update_weights(
        self,
        batch_accuracy: float,
        online_accuracy: float,
        smoothing_factor: float = 0.1
    ):
        """
        Atualiza pesos do ensemble baseado em performance.

        Usa exponential moving average para suavização.

        Args:
            batch_accuracy: Accuracy recente do batch
            online_accuracy: Accuracy recente do online
            smoothing_factor: Fator de suavização (0-1)
        """
        total_accuracy = batch_accuracy + online_accuracy
        if total_accuracy == 0:
            return

        # Calcular novos pesos proporcionais à accuracy
        new_batch_weight = batch_accuracy / total_accuracy
        new_online_weight = online_accuracy / total_accuracy

        # Aplicar suavização
        self._batch_weight = (
            (1 - smoothing_factor) * self._batch_weight +
            smoothing_factor * new_batch_weight
        )
        self._online_weight = (
            (1 - smoothing_factor) * self._online_weight +
            smoothing_factor * new_online_weight
        )

        # Garantir que somam 1
        total = self._batch_weight + self._online_weight
        self._batch_weight /= total
        self._online_weight /= total

        # Emitir métricas
        ensemble_batch_contribution.labels(
            specialist_type=self.specialist_type
        ).set(self._batch_weight)
        ensemble_online_contribution.labels(
            specialist_type=self.specialist_type
        ).set(self._online_weight)

        logger.info(
            "ensemble_weights_updated",
            specialist_type=self.specialist_type,
            batch_weight=self._batch_weight,
            online_weight=self._online_weight,
            batch_accuracy=batch_accuracy,
            online_accuracy=online_accuracy
        )

    def record_performance(
        self,
        model_type: str,
        accuracy: float,
        latency_ms: float,
        timestamp: Optional[datetime] = None
    ):
        """
        Registra performance de um modelo para cálculo de pesos dinâmicos.

        Args:
            model_type: 'batch' ou 'online'
            accuracy: Accuracy observada
            latency_ms: Latência observada
            timestamp: Timestamp (usa atual se não fornecido)
        """
        record = {
            'accuracy': accuracy,
            'latency_ms': latency_ms,
            'timestamp': timestamp or datetime.utcnow()
        }

        if model_type == 'batch':
            self._batch_performance_history.append(record)
            if len(self._batch_performance_history) > 1000:
                self._batch_performance_history = self._batch_performance_history[-1000:]
        else:
            self._online_performance_history.append(record)
            if len(self._online_performance_history) > 1000:
                self._online_performance_history = self._online_performance_history[-1000:]

    def get_dynamic_weights(self, window_hours: int = 1) -> Tuple[float, float]:
        """
        Calcula pesos dinâmicos baseado em performance recente.

        Args:
            window_hours: Janela de tempo em horas

        Returns:
            Tuple (batch_weight, online_weight)
        """
        cutoff = datetime.utcnow() - timedelta(hours=window_hours)

        # Filtrar por janela de tempo
        recent_batch = [
            r for r in self._batch_performance_history
            if r['timestamp'] > cutoff
        ]
        recent_online = [
            r for r in self._online_performance_history
            if r['timestamp'] > cutoff
        ]

        if not recent_batch or not recent_online:
            return self._batch_weight, self._online_weight

        # Calcular accuracy média
        batch_acc = np.mean([r['accuracy'] for r in recent_batch])
        online_acc = np.mean([r['accuracy'] for r in recent_online])

        # Calcular pesos proporcionais
        total = batch_acc + online_acc
        if total == 0:
            return 0.5, 0.5

        return batch_acc / total, online_acc / total

    def get_contribution_metrics(self) -> Dict[str, Any]:
        """
        Retorna métricas de contribuição de cada modelo.

        Returns:
            Dict com métricas de contribuição
        """
        return {
            'batch_weight': self._batch_weight,
            'online_weight': self._online_weight,
            'total_predictions': self._prediction_count,
            'fallback_count': self._fallback_count,
            'fallback_rate': (
                self._fallback_count / self._prediction_count
                if self._prediction_count > 0 else 0.0
            ),
            'strategy': self.config.ensemble_strategy,
            'online_available': (
                self.online_learner is not None and
                self.online_learner.is_fitted
            ),
            'cache_size': len(self._prediction_cache)
        }

    def set_online_learner(self, learner: IncrementalLearner):
        """Define o learner online."""
        self.online_learner = learner
        logger.info(
            "online_learner_set",
            specialist_type=self.specialist_type,
            learner_version=learner.model_version
        )

    def clear_cache(self):
        """Limpa cache de predições."""
        self._prediction_cache.clear()
        logger.info(
            "prediction_cache_cleared",
            specialist_type=self.specialist_type
        )
