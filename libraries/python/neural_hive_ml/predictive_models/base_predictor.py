"""Classe base abstrata para todos os preditores."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging
import mlflow
import numpy as np
import pandas as pd
from prometheus_client import Histogram, Counter, Gauge

logger = logging.getLogger(__name__)


class BasePredictor(ABC):
    """Classe base para modelos preditivos com funcionalidades comuns."""

    def __init__(
        self,
        config: Dict[str, Any],
        model_registry: Optional[Any] = None,
        metrics: Optional[Any] = None
    ):
        """
        Inicializa o preditor base.

        Args:
            config: Configuração do modelo
            model_registry: Registry MLflow para gerenciamento de modelos
            metrics: Cliente de métricas Prometheus
        """
        self.config = config
        self.model_registry = model_registry
        self.metrics = metrics
        self.model = None
        self.model_name = None
        self.model_version = None

        self._validate_config(config)

    @abstractmethod
    async def initialize(self) -> None:
        """Carrega o modelo do registry."""
        pass

    @abstractmethod
    async def train_model(self, training_data: pd.DataFrame) -> Dict[str, Any]:
        """Treina o modelo com dados fornecidos."""
        pass

    @abstractmethod
    def _extract_features(self, data: Dict[str, Any]) -> np.ndarray:
        """Extrai features dos dados de entrada."""
        pass

    def _validate_config(self, config: Dict[str, Any]) -> None:
        """
        Valida parâmetros de configuração.

        Args:
            config: Dicionário de configuração

        Raises:
            ValueError: Se configuração for inválida
        """
        required_keys = ['model_name', 'model_type']
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Configuração faltando chave obrigatória: {key}")

    def _log_metrics(
        self,
        metrics: Dict[str, float],
        model_name: str,
        stage: str = "training"
    ) -> None:
        """
        Registra métricas no Prometheus e MLflow.

        Args:
            metrics: Dicionário de métricas
            model_name: Nome do modelo
            stage: Estágio (training/prediction)
        """
        # Log to MLflow
        if mlflow.active_run():
            for metric_name, value in metrics.items():
                mlflow.log_metric(f"{stage}_{metric_name}", value)

        # Log to Prometheus
        if self.metrics:
            for metric_name, value in metrics.items():
                metric_key = f"{model_name}_{stage}_{metric_name}"
                if hasattr(self.metrics, metric_key):
                    getattr(self.metrics, metric_key).set(value)

        logger.info(f"Métricas registradas para {model_name} ({stage}): {metrics}")

    def _save_to_registry(
        self,
        model: Any,
        model_name: str,
        metrics: Dict[str, float],
        params: Dict[str, Any],
        tags: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Salva modelo no MLflow registry.

        Args:
            model: Modelo treinado
            model_name: Nome do modelo
            metrics: Métricas do modelo
            params: Parâmetros de treinamento
            tags: Tags adicionais

        Returns:
            Model version
        """
        if not self.model_registry:
            logger.warning("Model registry não disponível, modelo não salvo")
            return "unknown"

        try:
            model_version = self.model_registry.save_model(
                model=model,
                model_name=model_name,
                metrics=metrics,
                params=params,
                tags=tags or {}
            )
            logger.info(f"Modelo {model_name} salvo com versão {model_version}")
            return model_version
        except Exception as e:
            logger.error(f"Erro ao salvar modelo: {e}")
            raise

    def _load_from_registry(
        self,
        model_name: str,
        stage: str = "Production"
    ) -> Any:
        """
        Carrega modelo do MLflow registry.

        Args:
            model_name: Nome do modelo
            stage: Estágio (Production/Staging)

        Returns:
            Modelo carregado
        """
        if not self.model_registry:
            logger.warning("Model registry não disponível")
            return None

        try:
            model = self.model_registry.load_model(
                model_name=model_name,
                stage=stage
            )
            logger.info(f"Modelo {model_name} carregado do estágio {stage}")
            return model
        except Exception as e:
            logger.error(f"Erro ao carregar modelo: {e}")
            return None

    def _calculate_feature_importance(
        self,
        model: Any,
        feature_names: list
    ) -> Dict[str, float]:
        """
        Calcula importância de features para modelos baseados em árvore.

        Args:
            model: Modelo treinado
            feature_names: Lista de nomes das features

        Returns:
            Dicionário com importância de cada feature
        """
        if not hasattr(model, 'feature_importances_'):
            return {}

        importances = model.feature_importances_
        feature_importance = {
            name: float(imp)
            for name, imp in zip(feature_names, importances)
        }

        # Ordena por importância
        return dict(
            sorted(
                feature_importance.items(),
                key=lambda x: x[1],
                reverse=True
            )
        )

    def _normalize_features(
        self,
        features: np.ndarray,
        min_vals: Optional[np.ndarray] = None,
        max_vals: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Normaliza features para range [0, 1].

        Args:
            features: Array de features
            min_vals: Valores mínimos (opcional)
            max_vals: Valores máximos (opcional)

        Returns:
            Features normalizadas
        """
        if min_vals is None:
            min_vals = features.min(axis=0)
        if max_vals is None:
            max_vals = features.max(axis=0)

        # Evita divisão por zero
        range_vals = max_vals - min_vals
        range_vals[range_vals == 0] = 1

        return (features - min_vals) / range_vals
