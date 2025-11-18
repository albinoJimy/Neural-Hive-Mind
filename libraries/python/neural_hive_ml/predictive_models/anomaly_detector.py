"""Detector de anomalias usando Isolation Forest/Autoencoders."""

from typing import Dict, Any, Tuple, Optional
import logging
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import precision_score, recall_score, f1_score
import tensorflow as tf
from tensorflow import keras

from neural_hive_ml.predictive_models.base_predictor import BasePredictor
from neural_hive_ml.predictive_models.feature_engineering import (
    extract_ticket_features,
    create_feature_vector
)

logger = logging.getLogger(__name__)


class AnomalyDetector(BasePredictor):
    """Detector de anomalias usando Isolation Forest ou Autoencoders."""

    def __init__(
        self,
        config: Dict[str, Any],
        model_registry: Optional[Any] = None,
        metrics: Optional[Any] = None
    ):
        """
        Inicializa o detector de anomalias.

        Args:
            config: Configuração do modelo
                - model_type: 'isolation_forest' ou 'autoencoder'
                - contamination: taxa esperada de anomalias (0.05 = 5%)
            model_registry: Registry MLflow
            metrics: Cliente de métricas Prometheus
        """
        super().__init__(config, model_registry, metrics)

        self.model_type = config.get('model_type', 'isolation_forest')
        self.contamination = config.get('contamination', 0.05)
        self.feature_names = self._get_feature_names()
        self.scaler = StandardScaler()
        self.autoencoder_threshold = None

    async def initialize(self) -> None:
        """Carrega modelo do registry com scaler e threshold."""
        try:
            import mlflow
            import joblib
            import os

            model_name = f"anomaly-detector-{self.model_type}"

            # Tentar carregar modelo do registry
            if not self.model_registry:
                logger.warning("Model registry não disponível")
                return

            try:
                # Construir URI do modelo
                model_uri = f"models:/{model_name}/Production"

                # Carregar modelo (sklearn ou keras dependendo do tipo)
                if self.model_type == 'isolation_forest':
                    self.model = mlflow.sklearn.load_model(model_uri)
                else:  # autoencoder
                    self.model = mlflow.keras.load_model(model_uri)

                # Carregar artifacts (scaler e threshold)
                # Baixar artifacts para diretório temporário
                import tempfile
                with tempfile.TemporaryDirectory() as tmpdir:
                    # Baixar artifacts do run
                    client = mlflow.tracking.MlflowClient()
                    versions = client.get_latest_versions(model_name, stages=["Production"])
                    if versions:
                        run_id = versions[0].run_id

                        # Baixar scaler
                        try:
                            scaler_path = client.download_artifacts(run_id, "artifacts/scaler.joblib", tmpdir)
                            self.scaler = joblib.load(scaler_path)
                            logger.info("Scaler carregado com sucesso")
                        except Exception as e:
                            logger.warning(f"Erro ao carregar scaler: {e}, usando scaler padrão")

                        # Baixar threshold para autoencoder
                        if self.model_type == 'autoencoder':
                            try:
                                threshold_path = client.download_artifacts(run_id, "artifacts/threshold.npy", tmpdir)
                                self.autoencoder_threshold = np.load(threshold_path)
                                logger.info(f"Threshold carregado: {self.autoencoder_threshold}")
                            except Exception as e:
                                logger.warning(f"Erro ao carregar threshold: {e}, usando threshold padrão")
                                self.autoencoder_threshold = 0.1  # Fallback

                logger.info(f"AnomalyDetector inicializado com {self.model_type}")

            except Exception as e:
                logger.warning(f"Erro ao carregar modelo {model_name}: {e}")
                self.model = None

            if not self.model:
                logger.warning("Modelo não carregado, usando detecção heurística")

        except Exception as e:
            logger.error(f"Erro ao inicializar AnomalyDetector: {e}")

    async def detect_anomaly(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detecta se ticket é anômalo.

        Args:
            ticket: Dados do ticket

        Returns:
            Dict com is_anomaly, score, type, explanation
        """
        try:
            # Extrai features
            features_dict = extract_ticket_features(ticket)
            features = create_feature_vector(features_dict, self.feature_names)
            features = features.reshape(1, -1)

            # Normaliza
            if hasattr(self.scaler, 'mean_'):
                features_scaled = self.scaler.transform(features)
            else:
                features_scaled = features

            # Detecta anomalia com ML
            if self.model:
                if self.model_type == 'isolation_forest':
                    prediction = self.model.predict(features_scaled)[0]
                    score = self.model.score_samples(features_scaled)[0]
                    is_anomaly = (prediction == -1)
                else:  # autoencoder
                    reconstruction = self.model.predict(features_scaled)
                    reconstruction_error = np.mean(np.square(features_scaled - reconstruction))
                    is_anomaly = reconstruction_error > self.autoencoder_threshold
                    score = float(reconstruction_error)
            else:
                # Fallback heurístico
                is_anomaly, anomaly_type, explanation = self._heuristic_detection(
                    features_dict,
                    ticket
                )
                score = 1.0 if is_anomaly else 0.0

                result = {
                    'is_anomaly': is_anomaly,
                    'anomaly_score': score,
                    'anomaly_type': anomaly_type,
                    'explanation': explanation,
                    'model_type': 'heuristic'
                }

                if is_anomaly and self.metrics:
                    await self.metrics.record_anomaly_detection(
                        anomaly_type=anomaly_type,
                        severity='MEDIUM',
                        score=score
                    )

                return result

            # Identifica tipo e explica anomalia
            anomaly_type, explanation = self._explain_anomaly(features_dict, ticket)

            result = {
                'is_anomaly': bool(is_anomaly),
                'anomaly_score': float(score),
                'anomaly_type': anomaly_type if is_anomaly else None,
                'explanation': explanation if is_anomaly else None,
                'model_type': self.model_type
            }

            # Registra métricas
            if is_anomaly and self.metrics:
                severity = self._determine_severity(score)
                await self.metrics.record_anomaly_detection(
                    anomaly_type=anomaly_type,
                    severity=severity,
                    score=score
                )

            return result

        except Exception as e:
            logger.error(f"Erro ao detectar anomalia: {e}")
            return {
                'is_anomaly': False,
                'anomaly_score': 0.0,
                'error': str(e)
            }

    async def train_model(
        self,
        training_data: pd.DataFrame,
        labels: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """
        Treina modelo de detecção de anomalias.

        Args:
            training_data: DataFrame com features
            labels: Labels opcionais (1=normal, -1=anomaly) para avaliação

        Returns:
            Dict com métricas de treinamento
        """
        try:
            logger.info(f"Treinando {self.model_type} com {len(training_data)} amostras")

            # Extrai features
            X = training_data[self.feature_names].values

            # Normaliza
            self.scaler.fit(X)
            X_scaled = self.scaler.transform(X)

            # Treina modelo
            if self.model_type == 'isolation_forest':
                self.model = IsolationForest(
                    contamination=self.contamination,
                    n_estimators=100,
                    max_samples='auto',
                    random_state=42
                )
                self.model.fit(X_scaled)

            else:  # autoencoder
                input_dim = X_scaled.shape[1]
                self.model = self._build_autoencoder(input_dim)

                # Treina autoencoder
                history = self.model.fit(
                    X_scaled,
                    X_scaled,
                    epochs=50,
                    batch_size=32,
                    validation_split=0.15,
                    verbose=0
                )

                # Define threshold (95º percentil de reconstruction error)
                reconstructions = self.model.predict(X_scaled)
                reconstruction_errors = np.mean(np.square(X_scaled - reconstructions), axis=1)
                self.autoencoder_threshold = np.percentile(reconstruction_errors, 95)

            # Avalia se temos labels
            metrics = {}
            if labels is not None:
                predictions = self._predict_labels(X_scaled)
                metrics = {
                    'precision': float(precision_score(labels, predictions)),
                    'recall': float(recall_score(labels, predictions)),
                    'f1_score': float(f1_score(labels, predictions)),
                    'anomaly_rate': float((predictions == -1).mean())
                }
            else:
                # Sem labels, apenas reporta taxa de anomalias detectadas
                predictions = self._predict_labels(X_scaled)
                metrics = {
                    'anomaly_rate': float((predictions == -1).mean()),
                    'training_samples': len(training_data)
                }

            # Salva modelo com scaler e threshold
            import joblib
            import tempfile
            import os

            model_name = f"anomaly-detector-{self.model_type}"

            # Salvar artefatos adicionais (scaler e threshold) em arquivos temporários
            with tempfile.TemporaryDirectory() as tmpdir:
                scaler_path = os.path.join(tmpdir, 'scaler.joblib')
                joblib.dump(self.scaler, scaler_path)

                # Salvar modelo com artefatos adicionais
                import mlflow

                experiment_name = f"neural-hive-ml-{model_name}"
                experiment = mlflow.get_experiment_by_name(experiment_name)
                if experiment is None:
                    mlflow.create_experiment(experiment_name)
                else:
                    mlflow.set_experiment(experiment_name)

                with mlflow.start_run():
                    # Log parameters
                    mlflow.log_param('contamination', self.contamination)
                    mlflow.log_param('model_type', self.model_type)
                    mlflow.log_param('feature_count', len(self.feature_names))

                    # Log metrics
                    for metric_name, metric_value in metrics.items():
                        mlflow.log_metric(metric_name, metric_value)

                    # Log tags
                    mlflow.set_tag('contamination', str(self.contamination))
                    mlflow.set_tag('training_date', pd.Timestamp.now().isoformat())

                    # Log scaler artifact
                    mlflow.log_artifact(scaler_path, artifact_path='artifacts')

                    # Log model (diferente para sklearn vs keras)
                    if self.model_type == 'isolation_forest':
                        mlflow.sklearn.log_model(
                            self.model,
                            artifact_path="model",
                            registered_model_name=model_name
                        )
                    else:  # autoencoder
                        # Salvar threshold
                        threshold_path = os.path.join(tmpdir, 'threshold.npy')
                        np.save(threshold_path, self.autoencoder_threshold)
                        mlflow.log_artifact(threshold_path, artifact_path='artifacts')

                        mlflow.keras.log_model(
                            self.model,
                            artifact_path="model",
                            registered_model_name=model_name
                        )
                        mlflow.log_param('autoencoder_threshold', float(self.autoencoder_threshold))

            logger.info(f"Treinamento concluído: {metrics}")
            return metrics

        except Exception as e:
            logger.error(f"Erro ao treinar modelo: {e}")
            raise

    def _extract_features(self, data: Dict[str, Any]) -> np.ndarray:
        """Extrai features de um ticket."""
        features_dict = extract_ticket_features(data)
        return create_feature_vector(features_dict, self.feature_names)

    def _get_feature_names(self) -> list:
        """Define features para detecção de anomalias."""
        return [
            'risk_weight',
            'capabilities_count',
            'parameters_size',
            'qos_priority',
            'qos_consistency',
            'qos_durability',
            'task_type_encoded',
            'hour_of_day',
            'day_of_week',
            'is_weekend',
            'is_business_hours',
            'estimated_duration_ms',
            'sla_timeout_ms',
            'retry_count',
            'avg_duration_by_task',
            'std_duration_by_task',
            'success_rate_by_task',
            'avg_duration_by_risk',
            'risk_to_capabilities_ratio',
            'estimated_to_sla_ratio'
        ]

    def _explain_anomaly(
        self,
        features: Dict[str, Any],
        ticket: Dict[str, Any]
    ) -> Tuple[str, str]:
        """
        Identifica tipo de anomalia e gera explicação.

        Args:
            features: Features extraídas
            ticket: Dados do ticket

        Returns:
            Tuple (anomaly_type, explanation)
        """
        # Resource mismatch
        if features['risk_weight'] < 25 and features['capabilities_count'] > 8:
            return (
                'resource_mismatch',
                'Ticket com baixo risco mas muitas capabilities requeridas'
            )

        # QoS inconsistency
        if features['qos_consistency'] == 1.0 and features['risk_weight'] < 30:
            return (
                'qos_inconsistency',
                'EXACTLY_ONCE garantido para ticket de baixo risco (overhead desnecessário)'
            )

        # Duration outlier
        if features.get('avg_duration_by_task', 0) > 0:
            expected = features['avg_duration_by_task']
            actual = features['estimated_duration_ms']
            if abs(actual - expected) > 3 * features.get('std_duration_by_task', 10000):
                return (
                    'duration_outlier',
                    f'Duração estimada ({actual}ms) muito diferente da média histórica ({expected}ms)'
                )

        # Capability anomaly
        if features['capabilities_count'] > 10:
            return (
                'capability_anomaly',
                f'Número anormal de capabilities: {features["capabilities_count"]}'
            )

        return ('unknown', 'Padrão anômalo detectado pelo modelo ML')

    def _heuristic_detection(
        self,
        features: Dict[str, Any],
        ticket: Dict[str, Any]
    ) -> Tuple[bool, str, str]:
        """
        Detecção heurística de anomalias (fallback).

        Args:
            features: Features extraídas
            ticket: Dados do ticket

        Returns:
            Tuple (is_anomaly, anomaly_type, explanation)
        """
        # Regra 1: Capabilities excessivas
        if features['capabilities_count'] > 12:
            return (
                True,
                'capability_anomaly',
                f'Capabilities excessivas: {features["capabilities_count"]}'
            )

        # Regra 2: Risk/QoS mismatch
        if features['risk_weight'] > 75 and features['qos_priority'] < 0.5:
            return (
                True,
                'qos_inconsistency',
                'Alto risco com baixa prioridade QoS'
            )

        # Regra 3: Timeout inadequado
        if features['estimated_to_sla_ratio'] > 0.95:
            return (
                True,
                'timeout_risk',
                'SLA timeout muito próximo da duração estimada'
            )

        # Regra 4: Retry count alto
        if features['retry_count'] > 3:
            return (
                True,
                'excessive_retries',
                f'Número excessivo de retries: {features["retry_count"]}'
            )

        return (False, None, None)

    def _build_autoencoder(self, input_dim: int) -> keras.Model:
        """
        Constrói arquitetura de Autoencoder.

        Args:
            input_dim: Dimensão de entrada

        Returns:
            Modelo Keras compilado
        """
        # Encoder
        encoder_input = keras.layers.Input(shape=(input_dim,))
        encoded = keras.layers.Dense(64, activation='relu')(encoder_input)
        encoded = keras.layers.Dense(32, activation='relu')(encoded)
        encoded = keras.layers.Dense(16, activation='relu')(encoded)

        # Decoder
        decoded = keras.layers.Dense(32, activation='relu')(encoded)
        decoded = keras.layers.Dense(64, activation='relu')(decoded)
        decoder_output = keras.layers.Dense(input_dim, activation='linear')(decoded)

        # Autoencoder completo
        autoencoder = keras.Model(encoder_input, decoder_output)

        autoencoder.compile(
            optimizer='adam',
            loss='mse'
        )

        return autoencoder

    def _predict_labels(self, X: np.ndarray) -> np.ndarray:
        """Gera predições de labels (-1=anomaly, 1=normal)."""
        if self.model_type == 'isolation_forest':
            return self.model.predict(X)
        else:  # autoencoder
            reconstructions = self.model.predict(X)
            reconstruction_errors = np.mean(np.square(X - reconstructions), axis=1)
            predictions = np.where(
                reconstruction_errors > self.autoencoder_threshold,
                -1,
                1
            )
            return predictions

    def _determine_severity(self, score: float) -> str:
        """Determina severidade baseada no score de anomalia."""
        if self.model_type == 'isolation_forest':
            # Scores mais negativos = mais anômalos
            if score < -0.5:
                return 'CRITICAL'
            elif score < -0.3:
                return 'HIGH'
            else:
                return 'MEDIUM'
        else:  # autoencoder
            # Reconstruction error maior = mais anômalo
            if score > self.autoencoder_threshold * 2:
                return 'CRITICAL'
            elif score > self.autoencoder_threshold * 1.5:
                return 'HIGH'
            else:
                return 'MEDIUM'
