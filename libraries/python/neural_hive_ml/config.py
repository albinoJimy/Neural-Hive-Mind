"""Configurações para MLflow e Online Learning."""

from typing import Optional
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings


class MLflowSettings(BaseSettings):
    """Configurações do MLflow."""

    model_config = ConfigDict(env_prefix="MLFLOW_", env_file=".env")

    tracking_uri: str = Field(default="http://localhost:5000", description="URI do servidor MLflow")
    experiment_prefix: str = Field(
        default="approval-models", description="Prefixo para nomes de experimentos"
    )
    enabled: bool = Field(default=True, description="Se MLflow está habilitado")
    async_logging: bool = Field(default=True, description="Se logging assíncrono está habilitado")


class OnlineLearningSettings(BaseSettings):
    """Configurações de Online Learning."""

    model_config = ConfigDict(env_prefix="ONLINE_LEARNING_", env_file=".env")

    retrain_threshold: int = Field(default=100, description="Mínimo de novos samples para retreino")
    retrain_interval_hours: int = Field(
        default=24, description="Intervalo mínimo entre retreinos (horas)"
    )
    min_f1_improvement: float = Field(
        default=0.05, description="Melhoria mínima de F1 para deploy (5%)"
    )
    canary_duration_minutes: int = Field(
        default=60, description="Duração do canary deployment (minutos)"
    )
    canary_traffic_percentage: int = Field(
        default=10, description="Percentual de tráfego para canary"
    )
    drift_check_interval_hours: int = Field(
        default=1, description="Intervalo de checagem de drift (horas)"
    )
    drift_confidence_threshold: float = Field(
        default=0.10, description="Threshold de alerta de drift (10%)"
    )
    drift_approve_rate_threshold: float = Field(
        default=0.15, description="Threshold de drift para approve_rate (15%)"
    )


# Instâncias globais (lazy loading)
_mlflow_settings: Optional[MLflowSettings] = None
_online_learning_settings: Optional[OnlineLearningSettings] = None


def get_mlflow_settings() -> MLflowSettings:
    """Obtém configurações do MLflow."""
    global _mlflow_settings
    if _mlflow_settings is None:
        _mlflow_settings = MLflowSettings()
    return _mlflow_settings


def get_online_learning_settings() -> OnlineLearningSettings:
    """Obtém configurações de Online Learning."""
    global _online_learning_settings
    if _online_learning_settings is None:
        _online_learning_settings = OnlineLearningSettings()
    return _online_learning_settings
