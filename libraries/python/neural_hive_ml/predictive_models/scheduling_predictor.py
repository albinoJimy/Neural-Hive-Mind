"""Preditor de duração e recursos para scheduling de tickets."""

from typing import Dict, Any, List, Optional
import logging
import numpy as np
import pandas as pd
import xgboost as xgb
import lightgbm as lgb
import optuna
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from neural_hive_ml.predictive_models.base_predictor import BasePredictor
from neural_hive_ml.predictive_models.feature_engineering import (
    extract_ticket_features,
    create_feature_vector,
    get_feature_importance
)

logger = logging.getLogger(__name__)


class SchedulingPredictor(BasePredictor):
    """Preditor de duração e recursos usando XGBoost/LightGBM."""

    def __init__(
        self,
        config: Dict[str, Any],
        model_registry: Optional[Any] = None,
        metrics: Optional[Any] = None
    ):
        """
        Inicializa o preditor de scheduling.

        Args:
            config: Configuração do modelo
                - model_type: 'xgboost', 'lightgbm' ou 'ensemble'
                - hyperparameters: dict com hiperparâmetros
            model_registry: Registry MLflow
            metrics: Cliente de métricas Prometheus
        """
        super().__init__(config, model_registry, metrics)

        self.model_type = config.get('model_type', 'xgboost')
        self.hyperparameters = config.get('hyperparameters', {})
        self.feature_names = self._get_feature_names()
        self.historical_stats = {}

        # Modelos para ensemble
        self.xgb_model = None
        self.lgb_model = None

    async def initialize(self) -> None:
        """Carrega modelo(s) do registry."""
        try:
            if self.model_type == 'ensemble':
                self.xgb_model = self._load_from_registry(
                    f"scheduling-predictor-xgboost",
                    stage="Production"
                )
                self.lgb_model = self._load_from_registry(
                    f"scheduling-predictor-lightgbm",
                    stage="Production"
                )
                self.model = self.xgb_model or self.lgb_model
            else:
                model_name = f"scheduling-predictor-{self.model_type}"
                self.model = self._load_from_registry(model_name, stage="Production")

            if self.model:
                logger.info(f"SchedulingPredictor inicializado com {self.model_type}")
            else:
                logger.warning("Nenhum modelo carregado, usando fallback")

        except Exception as e:
            logger.error(f"Erro ao inicializar SchedulingPredictor: {e}")

    async def predict_duration(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prediz duração de execução do ticket.

        Args:
            ticket: Dados do ticket

        Returns:
            Dict com predicted_duration_ms e confidence
        """
        try:
            features_dict = extract_ticket_features(ticket, self.historical_stats)
            features = create_feature_vector(features_dict, self.feature_names)
            features = features.reshape(1, -1)

            if self.model_type == 'ensemble' and self.xgb_model and self.lgb_model:
                xgb_pred = self.xgb_model.predict(features)[0]
                lgb_pred = self.lgb_model.predict(features)[0]
                prediction = (xgb_pred + lgb_pred) / 2
            elif self.model:
                prediction = self.model.predict(features)[0]
            else:
                # Fallback heurístico
                prediction = self._heuristic_duration_estimate(ticket)

            confidence = self._calculate_confidence(prediction, features_dict)

            result = {
                "predicted_duration_ms": max(float(prediction), 0),
                "confidence": confidence,
                "model_type": self.model_type
            }

            # Registra métricas
            if self.metrics:
                self.metrics.record_prediction(
                    model_type="scheduling",
                    predicted_value=result["predicted_duration_ms"],
                    actual_value=None,  # Será atualizado após execução
                    latency=0.0,  # TODO: medir latência
                    confidence=confidence
                )

            return result

        except Exception as e:
            logger.error(f"Erro ao prever duração: {e}")
            return {
                "predicted_duration_ms": ticket.get('estimated_duration_ms', 60000),
                "confidence": 0.0,
                "error": str(e)
            }

    async def predict_resources(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prediz requisitos de recursos (CPU/memória).

        Args:
            ticket: Dados do ticket

        Returns:
            Dict com cpu_cores e memory_mb
        """
        try:
            duration_result = await self.predict_duration(ticket)
            predicted_duration_ms = duration_result['predicted_duration_ms']

            # Estimativa heurística baseada em duração e risco
            risk_weight = ticket.get('risk_weight', 0)
            capabilities_count = len(ticket.get('capabilities', []))

            # CPU: mais capacidades = mais CPU
            cpu_cores = min(0.5 + (capabilities_count * 0.1), 4.0)

            # Memória: baseado em duração e risco
            base_memory = 256
            duration_factor = min(predicted_duration_ms / 60000, 5)  # Normaliza para minutos
            risk_factor = risk_weight / 100
            memory_mb = base_memory * (1 + duration_factor * 0.2 + risk_factor * 0.5)

            return {
                "cpu_cores": round(cpu_cores, 2),
                "memory_mb": int(memory_mb),
                "confidence": duration_result['confidence']
            }

        except Exception as e:
            logger.error(f"Erro ao prever recursos: {e}")
            return {
                "cpu_cores": 1.0,
                "memory_mb": 512,
                "confidence": 0.0
            }

    async def train_model(
        self,
        training_data: pd.DataFrame,
        enable_tuning: bool = True
    ) -> Dict[str, Any]:
        """
        Treina modelo com dados históricos.

        Args:
            training_data: DataFrame com colunas de features e 'actual_duration_ms'
            enable_tuning: Se True, executa otimização de hiperparâmetros

        Returns:
            Dict com métricas de treinamento
        """
        try:
            logger.info(f"Iniciando treinamento com {len(training_data)} amostras")

            # Prepara dados
            X = training_data[self.feature_names].values
            y = training_data['actual_duration_ms'].values

            # Split train/validation/test
            X_train, X_temp, y_train, y_temp = train_test_split(
                X, y, test_size=0.3, random_state=42
            )
            X_val, X_test, y_val, y_test = train_test_split(
                X_temp, y_temp, test_size=0.5, random_state=42
            )

            # Otimização de hiperparâmetros
            if enable_tuning:
                best_params = self._hyperparameter_tuning(X_train, y_train)
            else:
                best_params = self.hyperparameters

            # Treina modelo
            if self.model_type == 'xgboost':
                self.model = xgb.XGBRegressor(**best_params)
            elif self.model_type == 'lightgbm':
                self.model = lgb.LGBMRegressor(**best_params)
            elif self.model_type == 'ensemble':
                self.xgb_model = xgb.XGBRegressor(**best_params)
                self.lgb_model = lgb.LGBMRegressor(**best_params)
                self.xgb_model.fit(X_train, y_train)
                self.lgb_model.fit(X_train, y_train)
                self.model = self.xgb_model

            if self.model_type != 'ensemble':
                self.model.fit(X_train, y_train)

            # Avalia modelo
            metrics = self._evaluate_model(X_test, y_test)
            metrics['training_samples'] = len(training_data)

            # Feature importance
            feature_importance = self._calculate_feature_importance(
                self.model,
                self.feature_names
            )
            logger.info(f"Top 5 features: {list(feature_importance.items())[:5]}")

            # Salva no registry
            self._save_to_registry(
                model=self.model,
                model_name=f"scheduling-predictor-{self.model_type}",
                metrics=metrics,
                params=best_params,
                tags={"feature_count": str(len(self.feature_names))}
            )

            return metrics

        except Exception as e:
            logger.error(f"Erro ao treinar modelo: {e}")
            raise

    def _extract_features(self, data: Dict[str, Any]) -> np.ndarray:
        """Extrai features de um ticket."""
        features_dict = extract_ticket_features(data, self.historical_stats)
        return create_feature_vector(features_dict, self.feature_names)

    def _get_feature_names(self) -> List[str]:
        """Define lista ordenada de nomes de features."""
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

    def _calculate_confidence(
        self,
        prediction: float,
        features: Dict[str, Any]
    ) -> float:
        """
        Calcula score de confiança da predição.

        Baseado em:
        - Presença de estatísticas históricas
        - Valores de features dentro de ranges esperados
        - Predição dentro de range razoável
        """
        confidence = 1.0

        # Penaliza se não temos estatísticas históricas
        if features.get('avg_duration_by_task', 0) == 0:
            confidence *= 0.7

        # Penaliza se predição está muito alta
        if prediction > 600000:  # > 10 minutos
            confidence *= 0.8

        # Boost se temos retry_count (mais dados históricos)
        if features.get('retry_count', 0) > 0:
            confidence *= 1.1

        return min(max(confidence, 0.0), 1.0)

    def _hyperparameter_tuning(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray
    ) -> Dict[str, Any]:
        """Otimiza hiperparâmetros usando Optuna."""

        def objective(trial):
            if self.model_type == 'xgboost':
                params = {
                    'max_depth': trial.suggest_int('max_depth', 3, 10),
                    'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3),
                    'n_estimators': trial.suggest_int('n_estimators', 50, 300),
                    'subsample': trial.suggest_float('subsample', 0.6, 1.0),
                    'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
                    'random_state': 42
                }
                model = xgb.XGBRegressor(**params)
            else:  # lightgbm
                params = {
                    'max_depth': trial.suggest_int('max_depth', 3, 10),
                    'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3),
                    'n_estimators': trial.suggest_int('n_estimators', 50, 300),
                    'subsample': trial.suggest_float('subsample', 0.6, 1.0),
                    'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
                    'random_state': 42
                }
                model = lgb.LGBMRegressor(**params)

            scores = cross_val_score(
                model, X_train, y_train,
                cv=5,
                scoring='neg_mean_absolute_error'
            )
            return -scores.mean()

        study = optuna.create_study(direction='minimize')
        study.optimize(objective, n_trials=20, show_progress_bar=False)

        logger.info(f"Melhores hiperparâmetros: {study.best_params}")
        return study.best_params

    def _evaluate_model(
        self,
        X_test: np.ndarray,
        y_test: np.ndarray
    ) -> Dict[str, float]:
        """Calcula métricas de avaliação."""
        if self.model_type == 'ensemble':
            xgb_pred = self.xgb_model.predict(X_test)
            lgb_pred = self.lgb_model.predict(X_test)
            y_pred = (xgb_pred + lgb_pred) / 2
        else:
            y_pred = self.model.predict(X_test)

        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        r2 = r2_score(y_test, y_pred)

        # MAPE (Mean Absolute Percentage Error)
        mape = np.mean(np.abs((y_test - y_pred) / np.maximum(y_test, 1))) * 100

        return {
            'mae': float(mae),
            'rmse': float(rmse),
            'r2': float(r2),
            'mape': float(mape)
        }

    def _heuristic_duration_estimate(self, ticket: Dict[str, Any]) -> float:
        """Estimativa heurística de duração como fallback."""
        base_duration = ticket.get('estimated_duration_ms', 60000)
        risk_weight = ticket.get('risk_weight', 0)
        capabilities_count = len(ticket.get('capabilities', []))

        # Ajusta baseado em risco e complexidade
        adjustment = 1.0 + (risk_weight / 200) + (capabilities_count * 0.05)
        return base_duration * adjustment
