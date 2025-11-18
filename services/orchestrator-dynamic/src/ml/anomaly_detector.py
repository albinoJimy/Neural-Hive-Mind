"""
Anomaly Detector para detecção de anomalias em tickets.

Usa Isolation Forest para detectar tickets com características anômalas
que podem indicar problemas de configuração ou comportamento inesperado.
"""

from typing import Dict, Any, Optional, List
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_score, recall_score, f1_score
import structlog

from .feature_engineering import (
    extract_ticket_features,
    normalize_features,
    compute_historical_stats
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

        # Modelo em memória
        self.model: Optional[IsolationForest] = None

        # Cache de estatísticas históricas
        self.historical_stats: Dict = {}
        self.stats_cache_timestamp: Optional[float] = None

        # Nome do modelo no registry
        self.model_name = 'ticket-anomaly-detector'

        # Contamination esperada (% de anomalias)
        self.contamination = config.ml_anomaly_contamination

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

        Returns:
            Modelo carregado ou None
        """
        try:
            model = self.model_registry.load_model(
                model_name=self.model_name,
                stage='Production'
            )

            if model:
                self.logger.info("anomaly_model_loaded", model_name=self.model_name)
                return model
            else:
                self.logger.warning("anomaly_model_not_found", model_name=self.model_name)
                return self._create_default_model()

        except Exception as e:
            self.logger.error("anomaly_model_load_failed", error=str(e))
            self.metrics.record_ml_error('model_load')
            return None

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

            # Detecta anomalia
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

            return {
                'is_anomaly': is_anomaly,
                'anomaly_score': anomaly_score,
                'anomaly_type': anomaly_type,
                'explanation': explanation
            }

        except Exception as e:
            self.logger.error("detect_anomaly_failed", error=str(e), ticket_id=ticket.get('ticket_id'))
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

    async def train_model(self, training_window_days: Optional[int] = None) -> Dict[str, float]:
        """
        Treina modelo com dados históricos do MongoDB.

        Args:
            training_window_days: Janela de dados (default: config value)

        Returns:
            Dict com métricas de avaliação (precision, recall, f1)
        """
        import time
        from datetime import datetime, timedelta

        start_time = time.time()

        try:
            window_days = training_window_days or self.config.ml_training_window_days
            cutoff_date = datetime.utcnow() - timedelta(days=window_days)

            # Query todos os tickets (anomalias são raras)
            tickets = await self.mongodb_client.db['execution_tickets'].find({
                'completed_at': {'$gte': cutoff_date}
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

            # Extrai features
            X_list = []
            y_list = []  # Labels de anomalia (heurístico)

            for ticket in tickets:
                try:
                    features_dict = extract_ticket_features(
                        ticket=ticket,
                        historical_stats=self.historical_stats
                    )
                    features = normalize_features(features_dict)

                    # Label de anomalia baseado em heurística
                    is_anomaly, _, _ = self._heuristic_detection(features_dict, ticket)

                    X_list.append(features[0])
                    y_list.append(1 if is_anomaly else 0)

                except Exception as e:
                    self.logger.warning("feature_extraction_failed", error=str(e))
                    continue

            X = np.array(X_list)
            y = np.array(y_list)

            # Treina modelo (unsupervised, não usa y)
            model = self._create_default_model()
            model.fit(X)

            # Avalia com labels heurísticos
            predictions = model.predict(X)
            y_pred = np.where(predictions == -1, 1, 0)  # -1 = anomalia

            # Split para métricas
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )

            predictions_test = model.predict(X_test)
            y_pred_test = np.where(predictions_test == -1, 1, 0)

            # Calcula métricas (pode ter warnings se sem anomalias)
            try:
                precision = precision_score(y_test, y_pred_test, zero_division=0)
                recall = recall_score(y_test, y_pred_test, zero_division=0)
                f1 = f1_score(y_test, y_pred_test, zero_division=0)
            except:
                precision = recall = f1 = 0.0

            anomaly_rate = np.mean(y_pred)

            metrics = {
                'precision': float(precision),
                'recall': float(recall),
                'f1_score': float(f1),
                'anomaly_rate': float(anomaly_rate),
                'train_samples': len(X),
                'contamination': self.contamination
            }

            # Salva modelo no registry
            params = {
                'n_estimators': 100,
                'contamination': self.contamination,
                'training_window_days': window_days,
                'feature_count': X.shape[1]
            }

            tags = {
                'model_type': 'anomaly_detector',
                'timestamp': datetime.utcnow().isoformat()
            }

            run_id = self.model_registry.save_model(
                model=model,
                model_name=self.model_name,
                metrics=metrics,
                params=params,
                tags=tags
            )

            # Atualiza modelo em memória se precision razoável
            if precision >= 0.6:
                self.model = model
                self.logger.info("model_updated_in_memory", precision=precision)

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
