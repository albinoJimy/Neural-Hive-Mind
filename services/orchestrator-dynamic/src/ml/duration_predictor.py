"""
Duration Predictor para estimativa de duração de tickets.

Usa RandomForestRegressor para predição de actual_duration_ms baseado
em features extraídas de tickets e estatísticas históricas.

Integra com ClickHouse para estatísticas históricas (mais rápido),
com fallback para MongoDB quando ClickHouse indisponível.
"""

from typing import Dict, Any, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .model_promotion import ModelPromotionManager
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

    Integra com ClickHouse para estatísticas históricas (10x mais rápido),
    com fallback para MongoDB quando ClickHouse indisponível.
    """

    def __init__(
        self,
        config,
        mongodb_client,
        model_registry,
        metrics,
        clickhouse_client=None
    ):
        """
        Inicializa DurationPredictor.

        Args:
            config: Configuração do orchestrator
            mongodb_client: Cliente MongoDB para queries históricas
            model_registry: ModelRegistry para load/save de modelos
            metrics: OrchestratorMetrics para observabilidade
            clickhouse_client: Cliente ClickHouse para estatísticas (opcional, preferido se disponível)
        """
        self.config = config
        self.mongodb_client = mongodb_client
        self.model_registry = model_registry
        self.metrics = metrics
        self.clickhouse_client = clickhouse_client
        self.logger = logger.bind(component="duration_predictor")

        # Flag para usar ClickHouse (configuração)
        self.use_clickhouse = getattr(config, 'ml_use_clickhouse_for_features', True)

        # Modelo em memória (carregado do registry)
        self.model: Optional[RandomForestRegressor] = None

        # Cache de estatísticas históricas
        self.historical_stats: Dict = {}
        self.stats_cache_timestamp: Optional[float] = None

        # Nome do modelo no registry
        self.model_name = 'ticket-duration-predictor'

        # Referência ao promotion manager (injetada externamente para shadow mode)
        self.promotion_manager: Optional['ModelPromotionManager'] = None

    async def initialize(self):
        """
        Inicializa predictor carregando modelo do registry.

        Tenta carregar modelo existente e verifica se está treinado.
        Se modelo não estiver treinado e houver dados suficientes, treina automaticamente.
        """
        try:
            # Carrega modelo existente (retorna None se não treinado)
            self.model = await self._load_model()

            # Carrega estatísticas históricas
            await self._refresh_historical_stats()

            # Verificar se modelo está treinado, treinar se necessário
            model_ready = await self._ensure_model_trained()

            if not model_ready:
                self.logger.warning(
                    "predictor_initialized_without_trained_model",
                    fallback="heuristic",
                    model_name=self.model_name
                )

            self.logger.info(
                "duration_predictor_initialized",
                model_loaded=self.model is not None,
                model_trained=model_ready,
                has_estimators=hasattr(self.model, 'estimators_') if self.model else False,
                stats_groups=len(self.historical_stats)
            )

        except Exception as e:
            self.logger.error("duration_predictor_init_failed", error=str(e))
            # Não inicializa modelo default - mantém None para usar heurística
            self.model = None

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

        Valida se modelo está treinado verificando existência de estimators_.
        Retorna None se modelo não estiver treinado (não retorna modelo inválido).

        Returns:
            Modelo treinado carregado ou None se não encontrado/não treinado
        """
        try:
            model = await self.model_registry.load_model(
                model_name=self.model_name,
                stage='Production'
            )

            if model:
                # Validar se modelo está treinado (tem estimators_)
                if not hasattr(model, 'estimators_'):
                    self.logger.warning(
                        "model_loaded_but_not_trained",
                        model_name=self.model_name,
                        reason="missing_estimators"
                    )
                    # Registrar status de modelo não treinado
                    self.metrics.record_ml_model_init_training_status(
                        model_name=self.model_name,
                        status='untrained'
                    )
                    return None

                self.logger.info(
                    "duration_model_loaded",
                    model_name=self.model_name,
                    n_estimators=len(model.estimators_)
                )
                # Registrar status de modelo treinado
                self.metrics.record_ml_model_init_training_status(
                    model_name=self.model_name,
                    status='trained'
                )
                return model
            else:
                self.logger.warning("duration_model_not_found", model_name=self.model_name)
                # Registrar status de modelo não treinado
                self.metrics.record_ml_model_init_training_status(
                    model_name=self.model_name,
                    status='untrained'
                )
                return None

        except Exception as e:
            self.logger.error("duration_model_load_failed", error=str(e))
            self.metrics.record_ml_error('model_load')
            return None

    async def _check_training_data_availability(self) -> tuple:
        """
        Verifica se há dados históricos suficientes para treinamento.

        Returns:
            Tuple (has_sufficient_data: bool, sample_count: int)
        """
        from datetime import datetime, timedelta

        try:
            cutoff_date = datetime.utcnow() - timedelta(
                days=self.config.ml_training_window_days
            )

            count = await self.mongodb_client.db['execution_tickets'].count_documents({
                'completed_at': {'$gte': cutoff_date},
                'actual_duration_ms': {'$exists': True, '$ne': None, '$gt': 0}
            })

            has_sufficient = count >= self.config.ml_min_training_samples

            self.logger.info(
                "training_data_availability_checked",
                sample_count=count,
                required=self.config.ml_min_training_samples,
                sufficient=has_sufficient
            )

            return has_sufficient, count

        except Exception as e:
            self.logger.error("data_availability_check_failed", error=str(e))
            return False, 0

    async def _ensure_model_trained(self) -> bool:
        """
        Garante que modelo está treinado, executando treinamento se necessário.

        Verifica:
        1. Se self.model existe e tem estimators_
        2. Se não, tenta treinar com dados históricos
        3. Se treinamento falhar (dados insuficientes), retorna False

        Returns:
            True se modelo treinado disponível, False caso contrário
        """
        try:
            # Verificar modelo atual
            if self.model and hasattr(self.model, 'estimators_'):
                self.logger.info(
                    "model_already_trained",
                    model_name=self.model_name,
                    n_estimators=len(self.model.estimators_)
                )
                return True

            # Verificar dados históricos suficientes
            has_sufficient, count = await self._check_training_data_availability()

            if not has_sufficient:
                self.logger.warning(
                    "insufficient_data_for_training",
                    sample_count=count,
                    required=self.config.ml_min_training_samples,
                    model_name=self.model_name
                )
                # Registrar status de falha
                self.metrics.record_ml_model_training_status(
                    model_name=self.model_name,
                    is_trained=False,
                    has_estimators=False
                )
                return False

            # Executar treinamento
            self.logger.info(
                "auto_training_triggered",
                model_name=self.model_name,
                sample_count=count
            )

            metrics = await self.train_model()

            if metrics.get('promoted'):
                self.logger.info(
                    "auto_training_succeeded",
                    model_name=self.model_name,
                    mae_percentage=metrics.get('mae_percentage')
                )
                return True
            else:
                self.logger.warning(
                    "auto_training_not_promoted",
                    model_name=self.model_name,
                    reason="quality_below_threshold"
                )
                return False

        except Exception as e:
            self.logger.error(
                "auto_training_failed",
                error=str(e),
                model_name=self.model_name
            )
            # Registrar status de falha
            self.metrics.record_ml_model_training_status(
                model_name=self.model_name,
                is_trained=False,
                has_estimators=False
            )
            return False

    async def _refresh_historical_stats(self):
        """
        Atualiza cache de estatísticas históricas.

        Prioriza ClickHouse se disponível e habilitado (10x mais rápido),
        com fallback para MongoDB.

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

            # Determina fonte de dados (ClickHouse preferido se disponível)
            clickhouse_client_to_use = None
            if self.use_clickhouse and self.clickhouse_client is not None:
                try:
                    # Verifica se ClickHouse está disponível
                    if await self.clickhouse_client.health_check():
                        clickhouse_client_to_use = self.clickhouse_client
                        self.logger.debug("using_clickhouse_for_stats")
                except Exception as e:
                    self.logger.warning(
                        "clickhouse_health_check_failed_using_mongodb",
                        error=str(e)
                    )

            # Computa novas estatísticas (com ClickHouse ou MongoDB)
            self.historical_stats = await compute_historical_stats(
                mongodb_client=self.mongodb_client,
                window_days=self.config.ml_training_window_days,
                clickhouse_client=clickhouse_client_to_use
            )

            self.stats_cache_timestamp = current_time

            self.logger.info(
                "historical_stats_refreshed",
                stats_groups=len(self.historical_stats),
                ttl_seconds=cache_ttl,
                source="clickhouse" if clickhouse_client_to_use else "mongodb"
            )

        except Exception as e:
            self.logger.error("stats_refresh_failed", error=str(e))
            # Mantém stats antigos em caso de erro

    async def predict_duration(self, ticket: Dict[str, Any]) -> Dict[str, float]:
        """
        Prediz duração do ticket com confidence score.

        Se shadow mode ativo, executa predição shadow em paralelo.

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

            # Verifica se shadow mode está ativo
            shadow_runner = None
            if self.promotion_manager:
                shadow_runner = self.promotion_manager.get_shadow_runner(self.model_name)

            # Se shadow mode ativo, usa shadow runner
            if shadow_runner:
                context = {
                    'ticket_id': ticket.get('ticket_id'),
                    'task_type': ticket.get('task_type'),
                    'risk_band': ticket.get('risk_band')
                }
                result = await shadow_runner.predict_with_shadow(
                    features=features_dict,
                    context=context
                )

                # Métricas
                duration_seconds = time.time() - start_time
                self.metrics.record_ml_prediction(
                    model_type='duration',
                    status='success',
                    duration=duration_seconds
                )

                return result

            # Predição normal (sem shadow mode)
            # Verifica se modelo está treinado (tem estimators_)
            if self.model and hasattr(self.model, 'estimators_') and hasattr(self.model, 'predict'):
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
                    confidence = 0.3  # Confidence reduzido para heurística
            else:
                # Modelo não treinado, usa heurística
                self.logger.debug(
                    "model_not_trained_using_heuristic",
                    ticket_id=ticket.get('ticket_id'),
                    reason="missing_estimators"
                )
                predicted_duration = self._heuristic_prediction(features_dict)
                confidence = 0.3  # Confidence baixo pois modelo não está treinado

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
        self.logger.debug(
            "using_heuristic_prediction",
            reason="model_not_trained",
            base_duration=features.get('avg_duration_by_task'),
            risk_weight=features.get('risk_weight')
        )

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

    async def train_model(self, training_window_days: Optional[int] = None) -> Dict[str, Any]:
        """
        Treina modelo com dados históricos.

        Prioriza ClickHouse para carregar dados de treino quando habilitado
        (query_ticket_metrics_for_training), com fallback para MongoDB.

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

            # Tenta carregar dados de treino via ClickHouse se habilitado
            tickets = []
            data_source = "mongodb"

            if self.use_clickhouse and self.clickhouse_client is not None:
                try:
                    if await self.clickhouse_client.health_check():
                        self.logger.info("loading_training_data_from_clickhouse", window_days=window_days)
                        clickhouse_data = await self.clickhouse_client.query_ticket_metrics_for_training(
                            window_days=window_days,
                            limit=100000
                        )
                        if clickhouse_data:
                            tickets = clickhouse_data
                            data_source = "clickhouse"
                            self.logger.info(
                                "training_data_loaded_from_clickhouse",
                                records=len(tickets)
                            )
                except Exception as e:
                    self.logger.warning(
                        "clickhouse_training_data_failed_using_mongodb",
                        error=str(e)
                    )

            # Fallback para MongoDB se ClickHouse falhou ou não está habilitado
            if not tickets:
                tickets = await self.mongodb_client.db['execution_tickets'].find({
                    'completed_at': {'$gte': cutoff_date},
                    'actual_duration_ms': {'$exists': True, '$ne': None, '$gt': 0}
                }).to_list(None)
                data_source = "mongodb"

            if len(tickets) < self.config.ml_min_training_samples:
                self.logger.warning(
                    "insufficient_training_data",
                    samples=len(tickets),
                    required=self.config.ml_min_training_samples
                )
                return {
                    'promoted': False,
                    'version': None,
                    'train_samples': len(tickets),
                    'test_samples': 0
                }

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

            run_id = await self.model_registry.save_model(
                model=model,
                model_name=self.model_name,
                metrics=metrics,
                params=params,
                tags=tags
            )

            # Atualiza modelo em memória se melhor que threshold
            promoted = False
            latest_version = await self._get_latest_version()
            metrics['version'] = latest_version

            if mae_pct < self.config.ml_duration_error_threshold * 100:
                self.model = model
                self.logger.info("model_updated_in_memory", mae_pct=mae_pct)
                promoted = True

                # Promove modelo se passar critérios
                if latest_version:
                    await self.model_registry.promote_model(
                        model_name=self.model_name,
                        version=latest_version,
                        stage='Production'
                    )

            metrics['promoted'] = promoted

            # Métricas
            training_duration = time.time() - start_time
            self.metrics.record_ml_training(
                model_type='duration',
                duration=training_duration,
                metrics=metrics
            )

            # Registrar métricas de qualidade
            self.metrics.record_ml_model_quality(
                model_name=self.model_name,
                mae=metrics.get('mae'),
                rmse=metrics.get('rmse'),
                r2=metrics.get('r2'),
                mae_percentage=metrics.get('mae_percentage')
            )

            # Registrar status de treinamento
            self.metrics.record_ml_model_training_status(
                model_name=self.model_name,
                is_trained=True,
                has_estimators=hasattr(model, 'estimators_')
            )

            self.logger.info(
                "duration_model_trained",
                metrics=metrics,
                run_id=run_id,
                duration_seconds=training_duration,
                data_source=data_source
            )

            return metrics

        except Exception as e:
            self.logger.error("training_failed", error=str(e))
            self.metrics.record_ml_error('training')
            # Registrar status de falha
            self.metrics.record_ml_model_training_status(
                model_name=self.model_name,
                is_trained=False,
                has_estimators=False
            )
            return {
                'promoted': False,
                'version': None,
                'train_samples': 0,
                'test_samples': 0
            }

    async def _get_latest_version(self) -> Optional[str]:
        """
        Obtém última versão do modelo no registry.

        Returns:
            String com número da versão ou None
        """
        try:
            metadata = await self.model_registry.get_model_metadata(self.model_name)
            return metadata.get('version')
        except:
            return None
