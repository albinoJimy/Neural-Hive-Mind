"""
Anomaly Detector para detecção de anomalias em tickets.

Usa Isolation Forest para detectar tickets com características anômalas
que podem indicar problemas de configuração ou comportamento inesperado.
"""

from typing import Dict, Any, Optional, List
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.metrics import precision_score, recall_score, f1_score, make_scorer
import structlog
from neural_hive_observability import get_tracer
from opentelemetry import trace

from .feature_engineering import (
    extract_ticket_features,
    normalize_features,
    compute_historical_stats
)
from .anomaly_training_utils import (
    prepare_anomaly_training_data,
    compute_anomaly_features_from_ticket,
    validate_anomaly_training_data
)

logger = structlog.get_logger(__name__)


class AnomalyDetector:
    """
    Detector de anomalias usando Isolation Forest.

    Detecta tickets com características atípicas:
    - Resource mismatch: capabilities vs risk_band inconsistente
    - QoS inconsistency: QoS incompatível com task_type
    - Duration outlier: duração muito diferente do histórico
    - Capability anomaly: número anormal de capabilities
    """

    ANOMALY_TYPES = [
        'resource_mismatch',
        'qos_inconsistency',
        'duration_outlier',
        'capability_anomaly'
    ]

    def __init__(self, config, mongodb_client, model_registry, metrics):
        """
        Inicializa AnomalyDetector.

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
        self.logger = logger.bind(component="anomaly_detector")
        self.tracer = get_tracer()

        # Modelo em memória
        self.model: Optional[IsolationForest] = None

        # Cache de estatísticas históricas
        self.historical_stats: Dict = {}
        self.stats_cache_timestamp: Optional[float] = None

        # Nome do modelo no registry
        self.model_name = 'ticket-anomaly-detector'

        # Contamination esperada (% de anomalias)
        self.contamination = config.ml_anomaly_contamination

        # Referência ao promotion manager (injetada externamente para shadow mode)
        self.promotion_manager = None

    async def initialize(self):
        """
        Inicializa detector carregando modelo do registry.
        """
        try:
            # Carrega modelo existente ou inicializa default
            self.model = await self._load_model()

            # Carrega estatísticas históricas
            await self._refresh_historical_stats()

            self.logger.info(
                "anomaly_detector_initialized",
                model_loaded=self.model is not None,
                contamination=self.contamination
            )

        except Exception as e:
            self.logger.error("anomaly_detector_init_failed", error=str(e))
            # Inicializa modelo default
            self.model = self._create_default_model()

    def _create_default_model(self) -> IsolationForest:
        """
        Cria modelo IsolationForest default (não treinado).

        Returns:
            IsolationForest com hiperparâmetros padrão
        """
        return IsolationForest(
            contamination=self.contamination,
            n_estimators=100,
            max_samples='auto',
            random_state=42,
            n_jobs=-1
        )

    async def _load_model(self) -> Optional[IsolationForest]:
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
                    "anomaly_model_loaded",
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
                self.logger.warning("anomaly_model_not_found", model_name=self.model_name)
                # Registrar status de modelo não treinado
                self.metrics.record_ml_model_init_training_status(
                    model_name=self.model_name,
                    status='untrained'
                )
                return None

        except Exception as e:
            self.logger.error("anomaly_model_load_failed", error=str(e))
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
                'completed_at': {'$gte': cutoff_date}
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
                    precision=metrics.get('precision')
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

            self.logger.debug("historical_stats_refreshed")

        except Exception as e:
            self.logger.error("stats_refresh_failed", error=str(e))

    async def detect_anomaly(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detecta se ticket é anômalo.

        Se shadow mode ativo, executa detecção shadow em paralelo.

        Args:
            ticket: Dict com dados do ticket

        Returns:
            Dict com:
            - is_anomaly: bool
            - anomaly_score: float (-1 a 1, quanto menor mais anômalo)
            - anomaly_type: str ou None
            - explanation: str com explicação
        """
        import time

        start_time = time.time()

        with self.tracer.start_as_current_span(
            "anomaly.detect",
            attributes={
                "neural.hive.ticket.id": ticket.get('ticket_id'),
                "neural.hive.ml.model_name": self.model_name
            }
        ) as span:
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
                        model_type='anomaly',
                        status='success',
                        duration=duration_seconds
                    )

                    # Mapear resultado do shadow runner para formato esperado
                    is_anomaly = result.get('is_anomaly', False)
                    if is_anomaly:
                        self.metrics.record_ml_anomaly('shadow_detected')

                    span.set_attribute("neural.hive.ml.is_anomaly", is_anomaly)
                    span.set_attribute("neural.hive.ml.shadow_mode", True)

                    return {
                        'is_anomaly': is_anomaly,
                        'anomaly_score': result.get('anomaly_score', 0.0),
                        'anomaly_type': result.get('anomaly_type'),
                        'explanation': result.get('explanation', 'Shadow mode prediction')
                    }

                # Detecta anomalia (modo normal)
                is_anomaly = False
                anomaly_score = 0.0
                anomaly_type = None
                explanation = "Ticket dentro do padrão esperado"

                if self.model and hasattr(self.model, 'predict'):
                    try:
                        # Predição: -1 = anomalia, 1 = normal
                        prediction = self.model.predict(features)[0]
                        is_anomaly = (prediction == -1)

                        # Score: valores negativos = anomalia
                        anomaly_score = float(self.model.score_samples(features)[0])

                        # Identifica tipo e explica anomalia
                        if is_anomaly:
                            anomaly_type, explanation = self._explain_anomaly(
                                features_dict,
                                ticket
                            )

                    except Exception as e:
                        self.logger.warning("anomaly_detection_failed", error=str(e))
                        # Fallback para regras heurísticas
                        is_anomaly, anomaly_type, explanation = self._heuristic_detection(
                            features_dict,
                            ticket
                        )
                        anomaly_score = -0.5 if is_anomaly else 0.5
                else:
                    # Modelo não treinado, usa heurísticas
                    is_anomaly, anomaly_type, explanation = self._heuristic_detection(
                        features_dict,
                        ticket
                    )
                    anomaly_score = -0.5 if is_anomaly else 0.5

                # Métricas
                if is_anomaly:
                    self.metrics.record_ml_anomaly(anomaly_type or 'unknown')

                duration_seconds = time.time() - start_time
                self.metrics.record_ml_prediction(
                    model_type='anomaly',
                    status='success',
                    duration=duration_seconds
                )

                self.logger.debug(
                    "anomaly_detected" if is_anomaly else "ticket_normal",
                    ticket_id=ticket.get('ticket_id'),
                    is_anomaly=is_anomaly,
                    anomaly_type=anomaly_type,
                    score=anomaly_score
                )
                span.set_attribute("neural.hive.ml.is_anomaly", is_anomaly)
                span.set_attribute("neural.hive.ml.anomaly_score", anomaly_score)
                if anomaly_type:
                    span.set_attribute("neural.hive.ml.anomaly_type", anomaly_type)

                return {
                    'is_anomaly': is_anomaly,
                    'anomaly_score': anomaly_score,
                    'anomaly_type': anomaly_type,
                    'explanation': explanation
                }

            except Exception as e:
                self.logger.error("detect_anomaly_failed", error=str(e), ticket_id=ticket.get('ticket_id'))
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                self.metrics.record_ml_error('prediction')

                return {
                    'is_anomaly': False,
                    'anomaly_score': 0.0,
                    'anomaly_type': None,
                    'explanation': 'Detecção de anomalia falhou'
                }

    def _explain_anomaly(
        self,
        features: Dict[str, float],
        ticket: Dict[str, Any]
    ) -> tuple[str, str]:
        """
        Identifica tipo de anomalia e gera explicação.

        Args:
            features: Features extraídas
            ticket: Ticket original

        Returns:
            Tupla (anomaly_type, explanation)
        """
        try:
            # Resource mismatch: baixo risk_band mas muitas capabilities
            risk_weight = features.get('risk_weight', 0.5)
            capabilities_count = features.get('capabilities_count', 0)

            if risk_weight < 0.5 and capabilities_count > 5:
                return (
                    'resource_mismatch',
                    f'Risk band baixo ({ticket.get("risk_band")}) mas {int(capabilities_count)} capabilities requeridas'
                )

            # QoS inconsistency: exactly_once com low risk
            qos_delivery = features.get('qos_delivery_score', 0.5)
            if qos_delivery >= 1.0 and risk_weight < 0.5:
                return (
                    'qos_inconsistency',
                    f'QoS exactly_once configurado para risk band {ticket.get("risk_band")}'
                )

            # Duration outlier: estimativa muito diferente do histórico
            estimated = features.get('estimated_duration_ms', 0)
            avg_historical = features.get('avg_duration_by_task', 60000)
            std_historical = features.get('std_duration_by_task', 15000)

            if std_historical > 0:
                z_score = abs(estimated - avg_historical) / std_historical
                if z_score > 3:
                    return (
                        'duration_outlier',
                        f'Duração estimada {int(estimated)}ms está {z_score:.1f} desvios padrão do histórico ({int(avg_historical)}ms)'
                    )

            # Capability anomaly: número anormal de capabilities
            if capabilities_count > 10:
                return (
                    'capability_anomaly',
                    f'Número anormal de capabilities: {int(capabilities_count)}'
                )

            # Anomalia genérica
            return (
                'unknown',
                'Padrão de features atípico detectado pelo modelo'
            )

        except Exception as e:
            self.logger.warning("anomaly_explanation_failed", error=str(e))
            return ('unknown', 'Anomalia detectada')

    def _heuristic_detection(
        self,
        features: Dict[str, float],
        ticket: Dict[str, Any]
    ) -> tuple[bool, Optional[str], str]:
        """
        Detecção heurística quando modelo não disponível.

        Args:
            features: Features extraídas
            ticket: Ticket original

        Returns:
            Tupla (is_anomaly, anomaly_type, explanation)
        """
        try:
            # Regra 1: Resource mismatch
            risk_weight = features.get('risk_weight', 0.5)
            capabilities_count = features.get('capabilities_count', 0)

            if risk_weight < 0.5 and capabilities_count > 5:
                return (
                    True,
                    'resource_mismatch',
                    f'Risk band baixo mas {int(capabilities_count)} capabilities requeridas'
                )

            # Regra 2: Duration outlier extremo
            estimated = features.get('estimated_duration_ms', 0)
            avg_historical = features.get('avg_duration_by_task', 60000)

            if estimated > avg_historical * 5 or estimated < avg_historical * 0.2:
                return (
                    True,
                    'duration_outlier',
                    f'Duração estimada muito diferente do histórico (est: {int(estimated)}ms, avg: {int(avg_historical)}ms)'
                )

            # Regra 3: Capabilities excessivas
            if capabilities_count > 15:
                return (
                    True,
                    'capability_anomaly',
                    f'{int(capabilities_count)} capabilities é anormalmente alto'
                )

            return (False, None, 'Ticket dentro do padrão esperado')

        except Exception as e:
            self.logger.warning("heuristic_detection_failed", error=str(e))
            return (False, None, 'Detecção falhou')

    async def train_model(
        self,
        training_window_days: Optional[int] = None,
        hyperparameter_tuning: bool = False
    ) -> Dict[str, float]:
        """
        Treina modelo com dados históricos do MongoDB.

        Usa prepare_anomaly_training_data para preparação avançada de dados
        incluindo labeling heurístico e geração de anomalias sintéticas.

        Args:
            training_window_days: Janela de dados (default: config value)
            hyperparameter_tuning: Se True, executa GridSearchCV (mais lento)

        Returns:
            Dict com métricas de avaliação (precision, recall, f1)
        """
        import time
        from datetime import datetime, timedelta

        start_time = time.time()
        window_days = training_window_days or self.config.ml_training_window_days

        with self.tracer.start_as_current_span(
            "anomaly.train_model",
            attributes={
                "neural.hive.ml.model_name": self.model_name,
                "neural.hive.ml.training_window_days": window_days
            }
        ) as span:
            try:
                cutoff_date = datetime.utcnow() - timedelta(days=window_days)

                # Query todos os tickets
                tickets = await self.mongodb_client.db['execution_tickets'].find({
                    'completed_at': {'$gte': cutoff_date}
                }).to_list(None)

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

                # Converter para DataFrame
                df = pd.DataFrame(tickets)

                # Preparar dados usando utilitários avançados
                X_train, X_test, y_train, y_test = prepare_anomaly_training_data(
                    df=df,
                    label_column='is_anomaly',
                    features_to_use=None,  # Auto-select
                    synthetic_ratio=0.1  # Adicionar 10% de anomalias sintéticas
                )

                # Validar dados de treinamento
                is_valid, issues = validate_anomaly_training_data(
                    X_train, y_train,
                    min_samples=self.config.ml_min_training_samples,
                    min_anomaly_ratio=0.01,
                    max_anomaly_ratio=0.5
                )

                if not is_valid and len(X_train) < 50:
                    self.logger.warning(
                        "training_data_validation_failed",
                        issues=issues
                    )
                    # Fallback para método antigo se preparação falhar
                    return await self._train_model_legacy(window_days, span)

                # Hyperparameter tuning opcional
                if hyperparameter_tuning and len(X_train) >= 200:
                    model, best_params = self._tune_hyperparameters(
                        X_train.values, y_train
                    )
                    self.logger.info(
                        "hyperparameter_tuning_completed",
                        best_params=best_params
                    )
                else:
                    # Treinar com hiperparâmetros padrão
                    model = self._create_default_model()
                    model.fit(X_train.values)
                    best_params = None

                # Avaliar no conjunto de teste
                predictions_test = model.predict(X_test.values)
                y_pred_test = np.where(predictions_test == -1, 1, 0)

                # Calcular métricas
                try:
                    precision = precision_score(y_test, y_pred_test, zero_division=0)
                    recall = recall_score(y_test, y_pred_test, zero_division=0)
                    f1 = f1_score(y_test, y_pred_test, zero_division=0)
                except Exception:
                    precision = recall = f1 = 0.0

                # Taxa de anomalia predita
                predictions_all = model.predict(X_train.values)
                anomaly_rate = np.mean(np.where(predictions_all == -1, 1, 0))

                metrics = {
                    'precision': float(precision),
                    'recall': float(recall),
                    'f1_score': float(f1),
                    'anomaly_rate': float(anomaly_rate),
                    'train_samples': len(X_train),
                    'test_samples': len(X_test),
                    'contamination': self.contamination,
                    'features_used': list(X_train.columns)
                }

                # Salvar modelo no registry
                params = {
                    'n_estimators': model.n_estimators,
                    'contamination': model.contamination,
                    'training_window_days': window_days,
                    'feature_count': X_train.shape[1],
                    'hyperparameter_tuning': hyperparameter_tuning
                }

                if best_params:
                    params.update(best_params)

                tags = {
                    'model_type': 'anomaly_detector',
                    'timestamp': datetime.utcnow().isoformat(),
                    'training_method': 'advanced'
                }

                run_id = await self.model_registry.save_model(
                    model=model,
                    model_name=self.model_name,
                    metrics=metrics,
                    params=params,
                    tags=tags
                )

                # Atualizar modelo em memória se precision suficiente
                promoted = False
                latest_version = await self._get_latest_version()
                metrics['version'] = latest_version

                # Critérios de promoção
                min_precision = getattr(
                    self.config, 'ml_validation_precision_threshold', 0.75
                )
                if precision >= min_precision:
                    self.model = model
                    self.logger.info(
                        "model_updated_in_memory",
                        precision=precision,
                        threshold=min_precision
                    )
                    promoted = True

                    # Promover modelo
                    if latest_version:
                        await self.model_registry.promote_model(
                            model_name=self.model_name,
                            version=latest_version,
                            stage='Production'
                        )
                else:
                    self.logger.warning(
                        "model_not_promoted_low_precision",
                        precision=precision,
                        threshold=min_precision
                    )

                metrics['promoted'] = promoted

                # Registrar métricas de treinamento
                training_duration = time.time() - start_time
                self.metrics.record_ml_training(
                    model_type='anomaly',
                    duration=training_duration,
                    metrics=metrics
                )

                self.logger.info(
                    "anomaly_model_trained",
                    metrics=metrics,
                    run_id=run_id,
                    duration_seconds=training_duration
                )
                span.set_attribute("neural.hive.ml.train_samples", len(X_train))
                span.set_attribute("neural.hive.ml.test_samples", len(X_test))
                span.set_attribute("neural.hive.ml.precision", float(precision))
                span.set_attribute("neural.hive.ml.recall", float(recall))
                span.set_attribute("neural.hive.ml.f1", float(f1))
                span.set_attribute("neural.hive.ml.promoted", promoted)

                return metrics

            except Exception as e:
                self.logger.error("training_failed", error=str(e))
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                self.metrics.record_ml_error('training')
                return {
                    'promoted': False,
                    'version': None,
                    'train_samples': 0,
                    'test_samples': 0
                }

    def _tune_hyperparameters(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray
    ) -> tuple:
        """
        Executa GridSearchCV para tuning de hiperparâmetros.

        Args:
            X_train: Features de treino
            y_train: Labels de treino

        Returns:
            Tupla (best_model, best_params)
        """
        param_grid = {
            'n_estimators': [50, 100, 200],
            'contamination': [0.05, 0.1, 0.15],
            'max_samples': [0.5, 0.75, 1.0]
        }

        # Scorer customizado para anomaly detection
        def anomaly_scorer(estimator, X, y):
            predictions = estimator.predict(X)
            y_pred = np.where(predictions == -1, 1, 0)
            return f1_score(y, y_pred, zero_division=0)

        base_model = IsolationForest(random_state=42, n_jobs=-1)

        grid_search = GridSearchCV(
            estimator=base_model,
            param_grid=param_grid,
            scoring=anomaly_scorer,
            cv=3,
            n_jobs=-1,
            verbose=0
        )

        grid_search.fit(X_train, y_train)

        self.logger.info(
            "grid_search_completed",
            best_score=grid_search.best_score_,
            best_params=grid_search.best_params_
        )

        return grid_search.best_estimator_, grid_search.best_params_

    async def _train_model_legacy(
        self,
        window_days: int,
        span
    ) -> Dict[str, float]:
        """
        Método de treinamento legado (fallback).

        Usado quando preparação avançada de dados falha.
        """
        from datetime import datetime, timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=window_days)

        # Query tickets
        tickets = await self.mongodb_client.db['execution_tickets'].find({
            'completed_at': {'$gte': cutoff_date}
        }).to_list(None)

        # Atualiza stats
        await self._refresh_historical_stats()

        # Extrai features método antigo
        X_list = []
        y_list = []

        for ticket in tickets:
            try:
                features_dict = extract_ticket_features(
                    ticket=ticket,
                    historical_stats=self.historical_stats
                )
                features = normalize_features(features_dict)
                is_anomaly, _, _ = self._heuristic_detection(features_dict, ticket)

                X_list.append(features[0])
                y_list.append(1 if is_anomaly else 0)
            except Exception:
                continue

        X = np.array(X_list)
        y = np.array(y_list)

        # Treina modelo
        model = self._create_default_model()
        model.fit(X)

        # Avalia
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        predictions_test = model.predict(X_test)
        y_pred_test = np.where(predictions_test == -1, 1, 0)

        precision = precision_score(y_test, y_pred_test, zero_division=0)
        recall = recall_score(y_test, y_pred_test, zero_division=0)
        f1 = f1_score(y_test, y_pred_test, zero_division=0)

        metrics = {
            'precision': float(precision),
            'recall': float(recall),
            'f1_score': float(f1),
            'train_samples': len(X),
            'test_samples': len(X_test),
            'contamination': self.contamination,
            'training_method': 'legacy',
            'promoted': False,
            'version': None
        }

        self.logger.info("anomaly_model_trained_legacy", metrics=metrics)

        return metrics

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
