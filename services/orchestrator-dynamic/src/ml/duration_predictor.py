"""
Duration Predictor para estimativa de duração de tickets.

Usa RandomForestRegressor para predição de actual_duration_ms baseado
em features extraídas de tickets e estatísticas históricas.
"""

from typing import Dict, Any, Optional, Tuple
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import structlog

from .feature_engineering import (
    extract_ticket_features,
    normalize_features,
    compute_historical_stats
)

logger = structlog.get_logger(__name__)


class DurationPredictor:
    """
    Preditor de duração de tickets usando Random Forest Regression.

    Features utilizadas (15+):
    - risk_weight, qos_scores, capabilities_count, task_type_encoded
    - parameters_size, estimated_duration_ms, sla_timeout_ms
    - avg_duration_by_task, avg_duration_by_risk, success_rate_by_task
    - std_duration_by_task, retry_count, hour_of_day

    Target: actual_duration_ms
    """

    def __init__(self, config, mongodb_client, model_registry, metrics):
        """
        Inicializa DurationPredictor.

        Args:
            config: Configuração do orchestrator
            mongodb_client: Cliente MongoDB para queries históricas
            model_registry: ModelRegistry para load/save de modelos
            metrics: OrchestratorMetrics para observabilidade
        """
        self.config = config
        self.mongodb_client = mongodb_client
        self.model_registry = model_registry
        self.metrics = metrics
        self.logger = logger.bind(component="duration_predictor")

        # Modelo em memória (carregado do registry)
        self.model: Optional[RandomForestRegressor] = None

        # Cache de estatísticas históricas
        self.historical_stats: Dict = {}
        self.stats_cache_timestamp: Optional[float] = None

        # Nome do modelo no registry
        self.model_name = 'ticket-duration-predictor'

    async def initialize(self):
        """
        Inicializa predictor carregando modelo do registry.
        """
        try:
            # Carrega modelo existente ou inicializa default
            self.model = await self._load_model()

            # Carrega estatísticas históricas
            await self._refresh_historical_stats()

            self.logger.info(
                "duration_predictor_initialized",
                model_loaded=self.model is not None,
                stats_groups=len(self.historical_stats)
            )

        except Exception as e:
            self.logger.error("duration_predictor_init_failed", error=str(e))
            # Inicializa modelo default
            self.model = self._create_default_model()

    def _create_default_model(self) -> RandomForestRegressor:
        """
        Cria modelo RandomForest default (não treinado).

        Returns:
            RandomForestRegressor com hiperparâmetros padrão
        """
        return RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1
        )

    async def _load_model(self) -> Optional[RandomForestRegressor]:
        """
        Carrega modelo do ModelRegistry.

        Returns:
            Modelo carregado ou None
        """
        try:
            model = self.model_registry.load_model(
                model_name=self.model_name,
                stage='Production'
            )

            if model:
                self.logger.info("duration_model_loaded", model_name=self.model_name)
                return model
            else:
                self.logger.warning("duration_model_not_found", model_name=self.model_name)
                return self._create_default_model()

        except Exception as e:
            self.logger.error("duration_model_load_failed", error=str(e))
            self.metrics.record_ml_error('model_load')
            return None

    async def _refresh_historical_stats(self):
        """
        Atualiza cache de estatísticas históricas.

        Cache tem TTL configurável (default 1h).
        """
        import time

        try:
            current_time = time.time()
            cache_ttl = self.config.ml_feature_cache_ttl_seconds

            # Verifica se cache ainda válido
            if (self.stats_cache_timestamp and
                current_time - self.stats_cache_timestamp < cache_ttl):
                return

            # Computa novas estatísticas
            self.historical_stats = await compute_historical_stats(
                mongodb_client=self.mongodb_client,
                window_days=self.config.ml_training_window_days
            )

            self.stats_cache_timestamp = current_time

            self.logger.info(
                "historical_stats_refreshed",
                stats_groups=len(self.historical_stats),
                ttl_seconds=cache_ttl
            )

        except Exception as e:
            self.logger.error("stats_refresh_failed", error=str(e))
            # Mantém stats antigos em caso de erro

    async def predict_duration(self, ticket: Dict[str, Any]) -> Dict[str, float]:
        """
        Prediz duração do ticket com confidence score.

        Args:
            ticket: Dict com dados do ticket

        Returns:
            Dict com duration_ms e confidence (0-1)
        """
        import time

        start_time = time.time()

        try:
            # Atualiza stats se necessário
            await self._refresh_historical_stats()

            # Extrai features
            features_dict = extract_ticket_features(
                ticket=ticket,
                historical_stats=self.historical_stats
            )

            # Normaliza features para array
            features = normalize_features(features_dict)

            # Prediz duração
            if self.model and hasattr(self.model, 'predict'):
                try:
                    predicted_duration = float(self.model.predict(features)[0])

                    # Garante valor positivo razoável
                    predicted_duration = max(predicted_duration, 1000.0)  # min 1s

                    # Calcula confidence
                    confidence = self._calculate_confidence(features_dict, predicted_duration)

                except Exception as e:
                    self.logger.warning("prediction_failed", error=str(e))
                    # Fallback para heurística
                    predicted_duration = self._heuristic_prediction(features_dict)
                    confidence = 0.5
            else:
                # Modelo não treinado, usa heurística
                predicted_duration = self._heuristic_prediction(features_dict)
                confidence = 0.5

            # Métricas
            duration_seconds = time.time() - start_time
            self.metrics.record_ml_prediction(
                model_type='duration',
                status='success',
                duration=duration_seconds
            )

            self.logger.debug(
                "duration_predicted",
                ticket_id=ticket.get('ticket_id'),
                predicted_ms=predicted_duration,
                confidence=confidence,
                latency_ms=duration_seconds * 1000
            )

            return {
                'duration_ms': predicted_duration,
                'confidence': confidence
            }

        except Exception as e:
            self.logger.error("predict_duration_failed", error=str(e), ticket_id=ticket.get('ticket_id'))
            self.metrics.record_ml_error('prediction')

            # Fallback para estimativa do ticket
            estimated = ticket.get('estimated_duration_ms', 60000.0)
            return {
                'duration_ms': float(estimated),
                'confidence': 0.3
            }

    def _heuristic_prediction(self, features: Dict[str, float]) -> float:
        """
        Predição heurística quando modelo não disponível.

        Usa avg_duration_by_task ajustado por risk_weight e capabilities.

        Args:
            features: Features extraídas do ticket

        Returns:
            Duração estimada em ms
        """
        base_duration = features.get('avg_duration_by_task', 60000.0)
        risk_weight = features.get('risk_weight', 0.5)
        capabilities_count = features.get('capabilities_count', 1.0)

        # Ajusta por risco e complexidade
        adjusted_duration = base_duration * (0.7 + risk_weight * 0.6)
        adjusted_duration *= (1.0 + capabilities_count * 0.1)

        return float(adjusted_duration)

    def _calculate_confidence(
        self,
        features: Dict[str, float],
        prediction: float
    ) -> float:
        """
        Calcula confidence score da predição.

        Baseado em:
        - Distância das features para dados de treino (simplificado)
        - Variância do modelo (se disponível)
        - Consistência com estatísticas históricas

        Args:
            features: Features do ticket
            prediction: Predição feita

        Returns:
            Confidence score (0-1)
        """
        try:
            # Base confidence: 0.7 para modelo treinado, 0.5 para heurística
            if self.model and hasattr(self.model, 'predict'):
                base_confidence = 0.7
            else:
                base_confidence = 0.5

            # Ajusta por consistência com histórico
            avg_duration = features.get('avg_duration_by_task', 60000.0)
            std_duration = features.get('std_duration_by_task', 15000.0)

            if std_duration > 0:
                # Z-score simplificado
                z_score = abs(prediction - avg_duration) / std_duration
                consistency_factor = max(0.0, 1.0 - z_score / 3.0)  # >3 std = 0 confidence
            else:
                consistency_factor = 0.8

            # Combina fatores
            confidence = base_confidence * consistency_factor

            # Limita entre 0.1 e 1.0
            return max(0.1, min(1.0, confidence))

        except Exception as e:
            self.logger.warning("confidence_calculation_failed", error=str(e))
            return 0.5

    async def train_model(self, training_window_days: Optional[int] = None) -> Dict[str, float]:
        """
        Treina modelo com dados históricos do MongoDB.

        Args:
            training_window_days: Janela de dados (default: config value)

        Returns:
            Dict com métricas de avaliação (MAE, RMSE, R2, MAE%)
        """
        import time
        from datetime import datetime, timedelta

        start_time = time.time()

        try:
            window_days = training_window_days or self.config.ml_training_window_days
            cutoff_date = datetime.utcnow() - timedelta(days=window_days)

            # Query tickets completados com actual_duration
            tickets = await self.mongodb_client.db['execution_tickets'].find({
                'completed_at': {'$gte': cutoff_date},
                'actual_duration_ms': {'$exists': True, '$ne': None},
                'status': 'COMPLETED'
            }).to_list(None)

            if len(tickets) < self.config.ml_min_training_samples:
                self.logger.warning(
                    "insufficient_training_data",
                    samples=len(tickets),
                    required=self.config.ml_min_training_samples
                )
                return {}

            # Atualiza stats antes de extrair features
            await self._refresh_historical_stats()

            # Extrai features e labels
            X_list = []
            y_list = []

            for ticket in tickets:
                try:
                    features_dict = extract_ticket_features(
                        ticket=ticket,
                        historical_stats=self.historical_stats
                    )
                    features = normalize_features(features_dict)

                    actual_duration = float(ticket['actual_duration_ms'])

                    X_list.append(features[0])
                    y_list.append(actual_duration)

                except Exception as e:
                    self.logger.warning("feature_extraction_failed", error=str(e))
                    continue

            X = np.array(X_list)
            y = np.array(y_list)

            # Split train/test
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )

            # Treina modelo
            model = self._create_default_model()
            model.fit(X_train, y_train)

            # Avalia modelo
            y_pred = model.predict(X_test)

            mae = mean_absolute_error(y_test, y_pred)
            rmse = np.sqrt(mean_squared_error(y_test, y_pred))
            r2 = r2_score(y_test, y_pred)

            # MAE como % da média
            mean_duration = np.mean(y_test)
            mae_pct = (mae / mean_duration * 100) if mean_duration > 0 else 100.0

            metrics = {
                'mae': float(mae),
                'rmse': float(rmse),
                'r2': float(r2),
                'mae_percentage': float(mae_pct),
                'train_samples': len(X_train),
                'test_samples': len(X_test)
            }

            # Salva modelo no registry
            params = {
                'n_estimators': 100,
                'max_depth': 10,
                'training_window_days': window_days,
                'feature_count': X.shape[1]
            }

            tags = {
                'model_type': 'duration_predictor',
                'timestamp': datetime.utcnow().isoformat()
            }

            run_id = self.model_registry.save_model(
                model=model,
                model_name=self.model_name,
                metrics=metrics,
                params=params,
                tags=tags
            )

            # Atualiza modelo em memória se melhor que threshold
            if mae_pct < self.config.ml_duration_error_threshold * 100:
                self.model = model
                self.logger.info("model_updated_in_memory", mae_pct=mae_pct)

                # Promove modelo se passar critérios
                latest_version = await self._get_latest_version()
                if latest_version:
                    self.model_registry.promote_model(
                        model_name=self.model_name,
                        version=latest_version,
                        stage='Production'
                    )

            # Métricas
            training_duration = time.time() - start_time
            self.metrics.record_ml_training(
                model_type='duration',
                duration=training_duration,
                metrics=metrics
            )

            self.logger.info(
                "duration_model_trained",
                metrics=metrics,
                run_id=run_id,
                duration_seconds=training_duration
            )

            return metrics

        except Exception as e:
            self.logger.error("training_failed", error=str(e))
            self.metrics.record_ml_error('training')
            return {}

    async def _get_latest_version(self) -> Optional[str]:
        """
        Obtém última versão do modelo no registry.

        Returns:
            String com número da versão ou None
        """
        try:
            metadata = self.model_registry.get_model_metadata(self.model_name)
            return metadata.get('version')
        except:
            return None
