"""
AnomalyDetector: Detecta anomalias em métricas de especialistas usando Isolation Forest.

Responsável por:
- Treinar modelo Isolation Forest em métricas históricas
- Detectar anomalias em métricas atuais
- Identificar features anômalas
- Calcular severidade de anomalias
- Persistir e carregar modelos treinados
"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import joblib
import os
import structlog
from datetime import datetime

logger = structlog.get_logger(__name__)


class AnomalyDetector:
    """Detecta anomalias em métricas de especialistas usando Isolation Forest."""

    def __init__(self, config: Dict[str, Any]):
        """
        Inicializa detector de anomalias.

        Args:
            config: Configuração do sistema
        """
        self.config = config

        # Configurações de anomaly detection
        self.enable_anomaly_detection = config.get("enable_anomaly_detection", True)
        self.contamination = config.get("anomaly_contamination", 0.1)
        self.n_estimators = config.get("anomaly_n_estimators", 100)
        self.model_path = config.get(
            "anomaly_model_path", "/data/models/anomaly_detector_{specialist_type}.pkl"
        )
        self.alert_threshold = config.get("anomaly_alert_threshold", -0.3)

        # Features usadas para detecção
        self.feature_names = [
            "consensus_agreement_rate",
            "false_positive_rate",
            "false_negative_rate",
            "avg_confidence_score",
            "avg_risk_score",
            "avg_processing_time_ms",
            "evaluation_count",
            "precision",
            "recall",
        ]

        # Modelo e scaler (lazy initialization)
        self._model: Optional[IsolationForest] = None
        self._scaler: Optional[StandardScaler] = None
        self._is_trained: bool = False

        logger.info(
            "AnomalyDetector initialized",
            contamination=self.contamination,
            n_estimators=self.n_estimators,
            features_count=len(self.feature_names),
        )

    def train_on_historical_data(
        self,
        metrics_history: List[Dict[str, float]],
        specialist_type: Optional[str] = None,
    ) -> bool:
        """
        Treina modelo Isolation Forest em dados históricos.

        Args:
            metrics_history: Lista de dicts com métricas históricas
            specialist_type: Tipo do especialista (para salvar modelo)

        Returns:
            True se treinamento bem-sucedido, False caso contrário
        """
        if not self.enable_anomaly_detection:
            logger.info("Anomaly detection disabled, skipping training")
            return False

        if not metrics_history:
            logger.warning("No historical data provided for training")
            return False

        try:
            # Preparar features
            X = self._prepare_features_batch(metrics_history)

            if X.shape[0] < 100:
                logger.warning(
                    "Insufficient data for training",
                    samples=X.shape[0],
                    minimum_required=100,
                )
                return False

            logger.info(
                "Training Isolation Forest",
                samples=X.shape[0],
                features=X.shape[1],
                contamination=self.contamination,
            )

            # Treinar scaler
            self._scaler = StandardScaler()
            X_normalized = self._scaler.fit_transform(X)

            # Treinar modelo
            self._model = IsolationForest(
                contamination=self.contamination,
                n_estimators=self.n_estimators,
                max_samples="auto",
                random_state=42,
                n_jobs=-1,
            )

            self._model.fit(X_normalized)
            self._is_trained = True

            # Salvar modelo se specialist_type fornecido
            if specialist_type:
                model_path = self.model_path.format(specialist_type=specialist_type)
                self._save_model(model_path)

            # Calcular estatísticas de treinamento
            anomaly_predictions = self._model.predict(X_normalized)
            anomaly_count = np.sum(anomaly_predictions == -1)
            anomaly_percentage = (anomaly_count / X.shape[0]) * 100

            logger.info(
                "Training completed successfully",
                samples=X.shape[0],
                features=X.shape[1],
                anomalies_detected=int(anomaly_count),
                anomaly_percentage=f"{anomaly_percentage:.2f}%",
            )

            return True

        except Exception as e:
            logger.error("Error training anomaly detector", error=str(e), exc_info=True)
            return False

    def detect_anomalies(self, current_metrics: Dict[str, float]) -> Dict[str, Any]:
        """
        Detecta anomalias em métricas atuais.

        Args:
            current_metrics: Dict com métricas atuais

        Returns:
            Dict com resultado da detecção:
            {
                'is_anomaly': bool,
                'anomaly_score': float,
                'severity': str,  # 'info', 'warning', 'critical'
                'anomalous_features': List[str],
                'confidence': float
            }
        """
        if not self.enable_anomaly_detection:
            return {
                "is_anomaly": False,
                "anomaly_score": 0.0,
                "severity": "info",
                "anomalous_features": [],
                "confidence": 0.0,
            }

        if not self._is_trained:
            logger.warning("Model not trained, cannot detect anomalies")
            return {
                "is_anomaly": False,
                "anomaly_score": 0.0,
                "severity": "info",
                "anomalous_features": [],
                "confidence": 0.0,
                "error": "model_not_trained",
            }

        try:
            # Preparar features
            X = self._prepare_features(current_metrics)

            if X is None:
                return {
                    "is_anomaly": False,
                    "anomaly_score": 0.0,
                    "severity": "info",
                    "anomalous_features": [],
                    "confidence": 0.0,
                    "error": "invalid_features",
                }

            # Normalizar
            X_normalized = self._scaler.transform(X.reshape(1, -1))

            # Predizer
            prediction = self._model.predict(X_normalized)[0]
            anomaly_score = self._model.score_samples(X_normalized)[0]

            is_anomaly = prediction == -1

            # Calcular severidade
            severity = self._calculate_severity(anomaly_score)

            # Identificar features anômalas
            anomalous_features = (
                self._identify_anomalous_features(current_metrics, X)
                if is_anomaly
                else []
            )

            # Confidence (inverso do anomaly score normalizado)
            confidence = 1.0 / (1.0 + abs(anomaly_score))

            result = {
                "is_anomaly": bool(is_anomaly),
                "anomaly_score": float(anomaly_score),
                "severity": severity,
                "anomalous_features": anomalous_features,
                "confidence": float(confidence),
            }

            if is_anomaly:
                logger.warning("Anomaly detected", **result)
            else:
                logger.debug("No anomaly detected", anomaly_score=anomaly_score)

            return result

        except Exception as e:
            logger.error("Error detecting anomalies", error=str(e), exc_info=True)
            return {
                "is_anomaly": False,
                "anomaly_score": 0.0,
                "severity": "info",
                "anomalous_features": [],
                "confidence": 0.0,
                "error": str(e),
            }

    def _prepare_features(self, metrics: Dict[str, float]) -> Optional[np.ndarray]:
        """
        Prepara features de um dict de métricas.

        Args:
            metrics: Dict com métricas

        Returns:
            Array numpy com features ou None se inválido
        """
        try:
            features = []

            for feature_name in self.feature_names:
                value = metrics.get(feature_name, 0.0)

                # Tratar valores None ou inválidos
                if value is None or not isinstance(value, (int, float)):
                    value = 0.0

                features.append(float(value))

            return np.array(features)

        except Exception as e:
            logger.error("Error preparing features", error=str(e), metrics=metrics)
            return None

    def _prepare_features_batch(
        self, metrics_list: List[Dict[str, float]]
    ) -> np.ndarray:
        """
        Prepara features de lista de métricas.

        Args:
            metrics_list: Lista de dicts com métricas

        Returns:
            Array numpy 2D com features
        """
        features_list = []

        for metrics in metrics_list:
            features = self._prepare_features(metrics)
            if features is not None:
                features_list.append(features)

        return np.array(features_list)

    def _calculate_severity(self, anomaly_score: float) -> str:
        """
        Calcula severidade da anomalia baseado no anomaly score.

        Args:
            anomaly_score: Score de anomalia (valores negativos = anômalo)

        Returns:
            'critical', 'warning', ou 'info'
        """
        if anomaly_score < -0.5:
            return "critical"
        elif anomaly_score < -0.3:
            return "warning"
        else:
            return "info"

    def _identify_anomalous_features(
        self, metrics: Dict[str, float], features: np.ndarray
    ) -> List[str]:
        """
        Identifica quais features são mais anômalas.

        Args:
            metrics: Dict com métricas
            features: Array de features

        Returns:
            Lista de nomes de features anômalas
        """
        # Estratégia simples: identificar features com valores extremos
        # (mais de 2 desvios padrão da média)
        anomalous = []

        if not hasattr(self._scaler, "mean_") or not hasattr(self._scaler, "scale_"):
            return []

        for i, feature_name in enumerate(self.feature_names):
            feature_value = features[i]
            mean = self._scaler.mean_[i]
            std = self._scaler.scale_[i]

            # Calcular z-score
            if std > 0:
                z_score = abs((feature_value - mean) / std)

                if z_score > 2.0:
                    anomalous.append(feature_name)

        return anomalous

    def _save_model(self, model_path: str) -> bool:
        """
        Salva modelo treinado em arquivo.

        Args:
            model_path: Caminho do arquivo

        Returns:
            True se salvou com sucesso
        """
        try:
            # Criar diretório se não existir
            os.makedirs(os.path.dirname(model_path), exist_ok=True)

            # Adicionar timestamp ao nome do arquivo
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_path = model_path.replace(".pkl", "")
            versioned_path = f"{base_path}_{timestamp}.pkl"

            # Salvar modelo e scaler
            joblib.dump(
                {
                    "model": self._model,
                    "scaler": self._scaler,
                    "feature_names": self.feature_names,
                    "contamination": self.contamination,
                    "n_estimators": self.n_estimators,
                    "timestamp": timestamp,
                },
                versioned_path,
            )

            # Criar symlink para versão latest
            latest_path = f"{base_path}_latest.pkl"
            if os.path.exists(latest_path):
                os.remove(latest_path)
            os.symlink(os.path.basename(versioned_path), latest_path)

            logger.info(
                "Model saved successfully",
                versioned_path=versioned_path,
                latest_path=latest_path,
            )

            return True

        except Exception as e:
            logger.error("Error saving model", model_path=model_path, error=str(e))
            return False

    def _load_model(self, model_path: str) -> bool:
        """
        Carrega modelo treinado de arquivo.

        Args:
            model_path: Caminho do arquivo

        Returns:
            True se carregou com sucesso
        """
        try:
            # Tentar carregar versão latest
            base_path = model_path.replace(".pkl", "")
            latest_path = f"{base_path}_latest.pkl"

            if not os.path.exists(latest_path):
                logger.warning("Model file not found", model_path=latest_path)
                return False

            # Carregar modelo
            data = joblib.load(latest_path)

            self._model = data["model"]
            self._scaler = data["scaler"]
            self.feature_names = data["feature_names"]
            self._is_trained = True

            logger.info(
                "Model loaded successfully",
                model_path=latest_path,
                features_count=len(self.feature_names),
                timestamp=data.get("timestamp", "unknown"),
            )

            return True

        except Exception as e:
            logger.error("Error loading model", model_path=model_path, error=str(e))
            return False

    def load_model_for_specialist(self, specialist_type: str) -> bool:
        """
        Carrega modelo para especialista específico.

        Args:
            specialist_type: Tipo do especialista

        Returns:
            True se carregou com sucesso
        """
        model_path = self.model_path.format(specialist_type=specialist_type)
        return self._load_model(model_path)

    def get_feature_importance(self) -> Dict[str, float]:
        """
        Retorna importância de features (aproximada).

        Returns:
            Dict mapeando feature name para importância
        """
        if not self._is_trained:
            return {}

        # Isolation Forest não fornece feature importance diretamente
        # Retornar pesos uniformes
        importance = {
            feature_name: 1.0 / len(self.feature_names)
            for feature_name in self.feature_names
        }

        return importance

    def get_anomaly_threshold(self) -> float:
        """
        Retorna threshold de anomalia configurado.

        Returns:
            Threshold value
        """
        return self.alert_threshold

    @property
    def is_trained(self) -> bool:
        """Retorna se modelo está treinado."""
        return self._is_trained
