"""
Cliente de Online Learning para Specialists.

Fornece interface simplificada para specialists consumirem
funcionalidades de online learning.
"""

import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import structlog
import numpy as np
import pybreaker
from functools import lru_cache

logger = structlog.get_logger(__name__)


class OnlineLearningClientError(Exception):
    """Exceção base para erros do cliente de online learning."""
    pass


class OnlineLearningClient:
    """
    Cliente para integração de specialists com online learning.

    Funcionalidades:
    - Carregar modelo online com cache local
    - Predição com ensemble (batch + online)
    - Reportar predições para monitoramento
    - Circuit breaker para fallback

    Uso:
        client = OnlineLearningClient(config, specialist_type)
        prediction = client.predict_with_ensemble(features, batch_model)
    """

    def __init__(
        self,
        specialist_type: str,
        online_learning_enabled: bool = True,
        cache_ttl_seconds: int = 300,
        mongodb_uri: Optional[str] = None,
        checkpoint_path: Optional[str] = None
    ):
        """
        Inicializa OnlineLearningClient.

        Args:
            specialist_type: Tipo do especialista
            online_learning_enabled: Se online learning está habilitado
            cache_ttl_seconds: TTL do cache local de modelos
            mongodb_uri: URI do MongoDB (opcional)
            checkpoint_path: Path para checkpoints (opcional)
        """
        self.specialist_type = specialist_type
        self.online_learning_enabled = online_learning_enabled
        self.cache_ttl_seconds = cache_ttl_seconds
        self.mongodb_uri = mongodb_uri or os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
        self.checkpoint_path = checkpoint_path or os.getenv(
            'ONLINE_CHECKPOINT_PATH',
            '/data/online_learning/checkpoints'
        )

        # Cache local de modelo
        self._cached_model = None
        self._cache_timestamp: Optional[datetime] = None

        # Circuit breaker
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=3,
            reset_timeout=60,
            name=f"online_learning_{specialist_type}"
        )

        # Estatísticas
        self._prediction_count = 0
        self._fallback_count = 0
        self._ensemble_count = 0

        logger.info(
            "online_learning_client_initialized",
            specialist_type=specialist_type,
            enabled=online_learning_enabled,
            cache_ttl=cache_ttl_seconds
        )

    def _is_cache_valid(self) -> bool:
        """Verifica se cache local é válido."""
        if self._cached_model is None or self._cache_timestamp is None:
            return False

        cache_age = datetime.utcnow() - self._cache_timestamp
        return cache_age < timedelta(seconds=self.cache_ttl_seconds)

    def _load_online_model(self) -> Optional[Any]:
        """
        Carrega modelo online do checkpoint mais recente.

        Returns:
            Modelo carregado ou None se não disponível
        """
        if not self.online_learning_enabled:
            return None

        try:
            # Buscar checkpoint mais recente
            import glob
            pattern = os.path.join(
                self.checkpoint_path,
                f"{self.specialist_type}_*.pkl"
            )
            checkpoints = sorted(glob.glob(pattern), reverse=True)

            if not checkpoints:
                logger.debug(
                    "no_checkpoint_found",
                    specialist_type=self.specialist_type,
                    pattern=pattern
                )
                return None

            # Carregar checkpoint mais recente
            import joblib
            checkpoint = joblib.load(checkpoints[0])

            logger.info(
                "online_model_loaded",
                specialist_type=self.specialist_type,
                checkpoint=checkpoints[0],
                version=checkpoint.get('model_version')
            )

            return checkpoint

        except Exception as e:
            logger.warning(
                "failed_to_load_online_model",
                specialist_type=self.specialist_type,
                error=str(e)
            )
            return None

    def get_online_model(self, force_reload: bool = False) -> Optional[Any]:
        """
        Obtém modelo online com cache.

        Args:
            force_reload: Forçar recarga do modelo

        Returns:
            Modelo online ou None se não disponível
        """
        if not self.online_learning_enabled:
            return None

        # Verificar cache
        if not force_reload and self._is_cache_valid():
            return self._cached_model

        # Carregar modelo com circuit breaker
        try:
            model = self._breaker.call(self._load_online_model)

            if model is not None:
                self._cached_model = model
                self._cache_timestamp = datetime.utcnow()

            return model

        except pybreaker.CircuitBreakerError:
            logger.warning(
                "circuit_breaker_open",
                specialist_type=self.specialist_type
            )
            return self._cached_model  # Retornar cache stale se disponível

    def predict_with_ensemble(
        self,
        features: np.ndarray,
        batch_model: Any,
        batch_weight: float = 0.7,
        online_weight: float = 0.3
    ) -> Dict[str, Any]:
        """
        Executa predição combinando batch e online models.

        Args:
            features: Features para predição
            batch_model: Modelo batch (baseline)
            batch_weight: Peso do modelo batch
            online_weight: Peso do modelo online

        Returns:
            Dict com predição e metadados:
            - probabilities: Probabilidades combinadas
            - prediction: Classe predita
            - model_used: 'ensemble', 'batch', ou 'online'
            - confidence: Confiança da predição
        """
        self._prediction_count += 1
        features = np.asarray(features)

        # Garantir formato 2D
        if features.ndim == 1:
            features = features.reshape(1, -1)

        # Predição batch (sempre disponível)
        batch_start = time.perf_counter()
        try:
            batch_probas = batch_model.predict_proba(features)
            batch_latency = (time.perf_counter() - batch_start) * 1000
        except Exception as e:
            logger.error(
                "batch_prediction_failed",
                specialist_type=self.specialist_type,
                error=str(e)
            )
            raise OnlineLearningClientError(f"Predição batch falhou: {str(e)}") from e

        # Tentar predição online
        online_probas = None
        online_latency = 0.0

        if self.online_learning_enabled:
            online_model = self.get_online_model()

            if online_model is not None:
                try:
                    online_start = time.perf_counter()

                    # Normalizar features usando scaler do modelo online
                    scaler = online_model.get('scaler')
                    model = online_model.get('model')

                    if scaler is not None and model is not None:
                        features_scaled = scaler.transform(features)
                        online_probas = model.predict_proba(features_scaled)
                        online_latency = (time.perf_counter() - online_start) * 1000

                except Exception as e:
                    logger.warning(
                        "online_prediction_failed",
                        specialist_type=self.specialist_type,
                        error=str(e)
                    )

        # Combinar predições
        if online_probas is not None:
            # Ensemble
            combined_probas = (
                batch_weight * batch_probas +
                online_weight * online_probas
            )
            combined_probas = combined_probas / combined_probas.sum(axis=1, keepdims=True)
            model_used = 'ensemble'
            self._ensemble_count += 1
        else:
            # Fallback para batch
            combined_probas = batch_probas
            model_used = 'batch'
            self._fallback_count += 1

        # Extrair predição e confiança
        prediction = np.argmax(combined_probas, axis=1)
        confidence = np.max(combined_probas, axis=1)

        result = {
            'probabilities': combined_probas.tolist(),
            'prediction': prediction.tolist(),
            'confidence': confidence.tolist(),
            'model_used': model_used,
            'batch_latency_ms': batch_latency,
            'online_latency_ms': online_latency,
            'total_latency_ms': batch_latency + online_latency
        }

        logger.debug(
            "ensemble_prediction_completed",
            specialist_type=self.specialist_type,
            model_used=model_used,
            confidence=float(np.mean(confidence)),
            total_latency_ms=result['total_latency_ms']
        )

        return result

    def report_prediction(
        self,
        plan_id: str,
        features: np.ndarray,
        prediction: str,
        confidence: float,
        model_used: str
    ):
        """
        Reporta predição para monitoramento e futuro treinamento.

        Args:
            plan_id: ID do plano avaliado
            features: Features utilizadas
            prediction: Predição realizada
            confidence: Confiança da predição
            model_used: Modelo utilizado
        """
        try:
            from pymongo import MongoClient

            client = MongoClient(self.mongodb_uri)
            db = client['neural_hive']
            collection = db['online_predictions']

            doc = {
                'plan_id': plan_id,
                'specialist_type': self.specialist_type,
                'prediction': prediction,
                'confidence': confidence,
                'model_used': model_used,
                'timestamp': datetime.utcnow(),
                'online_learning_enabled': self.online_learning_enabled
            }

            collection.insert_one(doc)
            client.close()

        except Exception as e:
            logger.warning(
                "failed_to_report_prediction",
                specialist_type=self.specialist_type,
                error=str(e)
            )

    def get_statistics(self) -> Dict[str, Any]:
        """
        Retorna estatísticas de uso.

        Returns:
            Dict com estatísticas
        """
        return {
            'specialist_type': self.specialist_type,
            'online_learning_enabled': self.online_learning_enabled,
            'total_predictions': self._prediction_count,
            'ensemble_predictions': self._ensemble_count,
            'fallback_predictions': self._fallback_count,
            'ensemble_rate': (
                self._ensemble_count / self._prediction_count
                if self._prediction_count > 0 else 0.0
            ),
            'cache_valid': self._is_cache_valid(),
            'circuit_breaker_state': self._breaker.current_state
        }

    def invalidate_cache(self):
        """Invalida cache local de modelo."""
        self._cached_model = None
        self._cache_timestamp = None
        logger.info(
            "online_model_cache_invalidated",
            specialist_type=self.specialist_type
        )

    def is_online_model_available(self) -> bool:
        """Verifica se modelo online está disponível."""
        if not self.online_learning_enabled:
            return False

        model = self.get_online_model()
        return model is not None

    def get_online_model_version(self) -> Optional[str]:
        """Retorna versão do modelo online carregado."""
        model = self.get_online_model()
        if model is None:
            return None
        return model.get('model_version')
