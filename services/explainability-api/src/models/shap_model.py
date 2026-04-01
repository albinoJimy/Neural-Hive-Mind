"""
DecisionWrapperModel - Wrapper sklearn para SHAP values.

Implementa modelo sklearn compatível com SHAP para explicar decisões
de consenso do Neural-Hive-Mind.

EPIC-204-01: Modelo ML para SHAP
"""

from typing import Any, Dict, List

import joblib
import numpy as np
import structlog
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler

logger = structlog.get_logger(__name__)


class DecisionWrapperModel:
    """
    Wrapper que transforma decisões de consenso em features para sklearn.

    Este modelo serve como função f(x) para o calculo de SHAP values,
    permitindo explicar quanto cada feature contribuiu para a decisão.
    """

    def __init__(
        self,
        model_type: str = "random_forest",
        n_estimators: int = 100,
        max_depth: int = 10,
        random_state: int = 42,
    ):
        """
        Inicializa o wrapper de modelo.

        Args:
            model_type: Tipo de modelo ('random_forest' ou 'gradient_boosting')
            n_estimators: Numero de estimadores para ensemble
            max_depth: Profundidade maxima das arvores
            random_state: Semente aleatoria para reprodutibilidade
        """
        self.feature_names = [
            "confidence",  # Confiança agregada
            "risk",  # Risco agregado
            "divergence_score",  # Divergência entre especialistas
            "seniority_multiplier",  # Multiplicador de senioridade
            "processing_time_ms",  # Tempo de processamento
            "unanimous",  # Se houve unanimidade (0/1)
            "bayesian_confidence",  # Confiança bayesiana
            "voting_confidence",  # Confiança do voting
        ]

        self.scaler = StandardScaler()

        # Inicializar modelo baseado no tipo
        if model_type == "gradient_boosting":
            self.model = GradientBoostingClassifier(
                n_estimators=n_estimators, max_depth=max_depth, random_state=random_state
            )
        else:
            self.model = RandomForestClassifier(
                n_estimators=n_estimators, max_depth=max_depth, random_state=random_state, n_jobs=-1
            )

        self.model_type = model_type
        self.is_trained = False

    def extract_features(self, decision_data: Dict[str, Any]) -> np.ndarray:
        """
        Extrai features de uma decisão consolidada.

        Args:
            decision_data: Dicionário com dados da decisão (ConsolidatedDecision)

        Returns:
            Array numpy com shape (1, n_features)
        """
        features = []

        # Feature 1: aggregated_confidence (normalizada 0-1)
        confidence = decision_data.get("aggregated_confidence", 0.5)
        features.append(float(confidence))

        # Feature 2: aggregated_risk (normalizada 0-1)
        risk = decision_data.get("aggregated_risk", 0.5)
        features.append(float(risk))

        # Feature 3: divergence_score (consensus_metrics)
        consensus_metrics = decision_data.get("consensus_metrics", {})
        divergence = consensus_metrics.get("divergence_score", 0.0)
        features.append(float(divergence))

        # Feature 4: seniority_multiplier medio dos votos
        specialist_votes = decision_data.get("specialist_votes", [])
        if specialist_votes:
            seniority_multipliers = [
                v.get("seniority_multiplier", 1.0)
                for v in specialist_votes
                if v.get("seniority_multiplier") is not None
            ]
            seniority_avg = np.mean(seniority_multipliers) if seniority_multipliers else 1.0
        else:
            seniority_avg = 1.0
        features.append(float(seniority_avg))

        # Feature 5: processing_time_ms medio dos votos
        if specialist_votes:
            processing_times = [v.get("processing_time_ms", 0) for v in specialist_votes]
            # Normalizar para 0-1 (assumindo max de 10000ms)
            processing_avg = np.mean(processing_times) / 10000.0
        else:
            processing_avg = 0.0
        features.append(float(processing_avg))

        # Feature 6: unanimous (0 ou 1)
        unanimous = 1.0 if consensus_metrics.get("unanimous", False) else 0.0
        features.append(unanimous)

        # Feature 7: bayesian_confidence
        bayesian_conf = consensus_metrics.get("bayesian_confidence", 0.5)
        features.append(float(bayesian_conf))

        # Feature 8: voting_confidence
        voting_conf = consensus_metrics.get("voting_confidence", 0.5)
        features.append(float(voting_conf))

        return np.array(features).reshape(1, -1)

    def train(self, historical_decisions: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Treina modelo com decisões históricas.

        Args:
            historical_decisions: Lista de decisões (dict ou ConsolidatedDecision)

        Returns:
            Dicionário com métricas do treinamento
        """
        if len(historical_decisions) < 10:
            raise ValueError(
                f"Insufficient samples for training: {len(historical_decisions)}. "
                "Minimum 10 decisions required."
            )

        # Extrair features e labels
        X_list = []
        y_list = []

        for decision in historical_decisions:
            # Converter dict para se necessário
            if hasattr(decision, "model_dump"):
                decision_dict = decision.model_dump()
            elif hasattr(decision, "dict"):
                decision_dict = decision.dict()
            else:
                decision_dict = decision

            try:
                X = self.extract_features(decision_dict)
                X_list.append(X[0])

                # Label: 1 para approve, 0 para outros
                final_decision = decision_dict.get("final_decision", "approve")
                if isinstance(final_decision, str):
                    approved = 1.0 if final_decision.lower() in ["approve", "approved"] else 0.0
                else:
                    # Enum com .value
                    approved = (
                        1.0 if str(final_decision).lower() in ["approve", "approved"] else 0.0
                    )

                y_list.append(approved)
            except Exception as e:
                logger.warning(
                    "failed_to_extract_features",
                    decision_id=decision_dict.get("decision_id", "unknown"),
                    error=str(e),
                )
                continue

        if not X_list:
            raise ValueError("No valid features extracted from decisions")

        X = np.array(X_list)
        y = np.array(y_list)

        logger.info(
            "training_shap_model",
            samples=len(X_list),
            features=len(self.feature_names),
            approval_rate=float(np.mean(y)),
        )

        # Normalizar features
        X_scaled = self.scaler.fit_transform(X)

        # Treinar modelo
        self.model.fit(X_scaled, y)
        self.is_trained = True

        # Métricas
        accuracy = self.model.score(X_scaled, y)

        # Cross-validation para estimar generalização
        if len(X_list) >= 20:
            cv_scores = cross_val_score(
                self.model, X_scaled, y, cv=min(5, len(X_list) // 4), scoring="accuracy"
            )
            cv_mean = float(np.mean(cv_scores))
            cv_std = float(np.std(cv_scores))
        else:
            cv_mean = accuracy
            cv_std = 0.0

        metrics = {
            "accuracy": float(accuracy),
            "cv_accuracy_mean": cv_mean,
            "cv_accuracy_std": cv_std,
            "samples": len(X_list),
            "approval_rate": float(np.mean(y)),
            "model_type": self.model_type,
        }

        logger.info("shap_model_trained", **metrics)

        return metrics

    def predict_proba(self, decision_data: Dict[str, Any]) -> float:
        """
        Prediz probabilidade de aprovação.

        Args:
            decision_data: Dados da decisão

        Returns:
            Probabilidade de aprovação (0-1)
        """
        if not self.is_trained:
            raise RuntimeError("Model must be trained before prediction")

        X = self.extract_features(decision_data)
        X_scaled = self.scaler.transform(X)

        # predict_proba retorna [prob_class_0, prob_class_1]
        proba = self.model.predict_proba(X_scaled)[0]

        # Retornar probabilidade de classe 1 (approve)
        return float(proba[1])

    def predict(self, decision_data: Dict[str, Any]) -> int:
        """
        Prediz classe (0=reject, 1=approve).

        Args:
            decision_data: Dados da decisão

        Returns:
            0 ou 1
        """
        if not self.is_trained:
            raise RuntimeError("Model must be trained before prediction")

        X = self.extract_features(decision_data)
        X_scaled = self.scaler.transform(X)

        return int(self.model.predict(X_scaled)[0])

    def save(self, path: str) -> None:
        """
        Salva modelo treinado em disco.

        Args:
            path: Caminho para salvar o modelo (.joblib)
        """
        if not self.is_trained:
            raise RuntimeError("Cannot save untrained model")

        model_data = {
            "model": self.model,
            "scaler": self.scaler,
            "feature_names": self.feature_names,
            "model_type": self.model_type,
            "is_trained": self.is_trained,
        }

        joblib.dump(model_data, path)
        logger.info("shap_model_saved", path=path)

    def load(self, path: str) -> None:
        """
        Carrega modelo treinado do disco.

        Args:
            path: Caminho do modelo salvo (.joblib)
        """
        model_data = joblib.load(path)

        self.model = model_data["model"]
        self.scaler = model_data["scaler"]
        self.feature_names = model_data["feature_names"]
        self.model_type = model_data.get("model_type", "random_forest")
        self.is_trained = model_data.get("is_trained", True)

        logger.info("shap_model_loaded", path=path)

    def get_feature_importance(self) -> Dict[str, float]:
        """
        Retorna importância das features do modelo treinado.

        Returns:
            Dicionário {feature_name: importance}
        """
        if not self.is_trained:
            raise RuntimeError("Model must be trained before getting importance")

        if hasattr(self.model, "feature_importances_"):
            importances = self.model.feature_importances_
        else:
            # Para modelos sem feature_importances_, retornar zeros
            importances = np.zeros(len(self.feature_names))

        return dict(zip(self.feature_names, importances.tolist()))


class FeatureExtractor:
    """
    Extrator de features especializado para decisões de consenso.

    Fornece métodos para extração e validação de features usadas
    no treinamento do modelo SHAP.
    """

    def __init__(self):
        self.feature_names = [
            "confidence",
            "risk",
            "divergence_score",
            "seniority_multiplier",
            "processing_time_ms",
            "unanimous",
            "bayesian_confidence",
            "voting_confidence",
        ]

    def extract_batch(self, decisions: List[Dict[str, Any]]) -> np.ndarray:
        """
        Extrai features de um lote de decisões.

        Args:
            decisions: Lista de decisões

        Returns:
            Array numpy com shape (n_samples, n_features)
        """
        wrapper = DecisionWrapperModel()
        features_list = []

        for decision in decisions:
            try:
                feat = wrapper.extract_features(decision)
                features_list.append(feat[0])
            except Exception as e:
                logger.warning(
                    "feature_extraction_failed",
                    decision_id=decision.get("decision_id", "unknown"),
                    error=str(e),
                )
                # Adicionar features zeros como fallback
                features_list.append(np.zeros(len(self.feature_names)))

        return np.array(features_list)

    def validate_features(self, features: np.ndarray) -> Dict[str, Any]:
        """
        Valida array de features.

        Args:
            features: Array numpy de features

        Returns:
            Dicionário com resultado da validação
        """
        validation_result = {"is_valid": True, "issues": []}

        # Verificar shape
        if len(features.shape) != 2:
            validation_result["is_valid"] = False
            validation_result["issues"].append(
                f"Invalid shape: {features.shape}, expected (n_samples, n_features)"
            )
            return validation_result

        n_features = features.shape[1]
        if n_features != len(self.feature_names):
            validation_result["is_valid"] = False
            validation_result["issues"].append(
                f"Invalid number of features: {n_features}, expected {len(self.feature_names)}"
            )

        # Verificar NaN/Inf
        if np.isnan(features).any():
            validation_result["is_valid"] = False
            validation_result["issues"].append("Contains NaN values")

        if np.isinf(features).any():
            validation_result["is_valid"] = False
            validation_result["issues"].append("Contains Inf values")

        return validation_result


class ModelTrainer:
    """
    Treinador de modelo com pipeline completo.

    Implementa coleta de decisões históricas, treinamento,
    validação e persistência do modelo.
    """

    def __init__(
        self, model_type: str = "random_forest", min_samples: int = 10, target_accuracy: float = 0.7
    ):
        """
        Inicializa o treinador.

        Args:
            model_type: Tipo de modelo a treinar
            min_samples: Mínimo de amostras para treino
            target_accuracy: Acurácia alvo para validação
        """
        self.model_type = model_type
        self.min_samples = min_samples
        self.target_accuracy = target_accuracy
        self.model = DecisionWrapperModel(model_type=model_type)

    def train_from_decisions(self, decisions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Treina modelo a partir de lista de decisões.

        Args:
            decisions: Lista de decisões históricas

        Returns:
            Dicionário com métricas e status do treinamento
        """
        if len(decisions) < self.min_samples:
            return {
                "success": False,
                "error": f"Insufficient samples: {len(decisions)} < {self.min_samples}",
                "samples": len(decisions),
            }

        try:
            # Treinar modelo
            metrics = self.model.train(decisions)

            # Validar se atingiu target
            accuracy = metrics["accuracy"]
            success = accuracy >= self.target_accuracy

            return {
                "success": success,
                "metrics": metrics,
                "feature_importance": self.model.get_feature_importance(),
                "meets_target": success,
                "target_accuracy": self.target_accuracy,
            }

        except Exception as e:
            logger.error("model_training_failed", error=str(e))
            return {"success": False, "error": str(e)}

    def save_trained_model(self, path: str) -> None:
        """Salva modelo treinado."""
        if not self.model.is_trained:
            raise RuntimeError("No trained model to save")
        self.model.save(path)

    def load_model(self, path: str) -> None:
        """Carrega modelo salvo."""
        self.model.load(path)
