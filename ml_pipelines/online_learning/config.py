"""
Configuração do Pipeline de Online Learning.

Define todas as configurações para incremental learning, shadow validation,
rollback automático e deployment gradual.
"""

import os
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
import structlog

logger = structlog.get_logger(__name__)


class OnlineLearningConfig(BaseSettings):
    """Configuração completa do pipeline de online learning."""

    # =========================================================================
    # Incremental Learning
    # =========================================================================
    online_learning_enabled: bool = Field(
        default=True,
        env="ONLINE_LEARNING_ENABLED",
        description="Feature flag para habilitar online learning"
    )
    incremental_algorithm: str = Field(
        default="sgd",
        env="INCREMENTAL_ALGORITHM",
        description="Algoritmo incremental: sgd, passive_aggressive"
    )
    mini_batch_size: int = Field(
        default=32,
        env="MINI_BATCH_SIZE",
        description="Tamanho do mini-batch para partial_fit"
    )
    learning_rate: float = Field(
        default=0.001,
        env="ONLINE_LEARNING_RATE",
        description="Taxa de aprendizado para SGD"
    )
    update_frequency_minutes: int = Field(
        default=30,
        env="ONLINE_UPDATE_FREQUENCY_MINUTES",
        description="Frequência de atualização em minutos"
    )
    checkpoint_interval_updates: int = Field(
        default=100,
        env="CHECKPOINT_INTERVAL_UPDATES",
        description="Intervalo de updates para salvar checkpoint"
    )
    max_updates_before_full_retrain: int = Field(
        default=10000,
        env="MAX_UPDATES_BEFORE_FULL_RETRAIN",
        description="Máximo de updates antes de retreinamento completo"
    )

    # =========================================================================
    # Shadow Validation
    # =========================================================================
    shadow_validation_enabled: bool = Field(
        default=True,
        env="SHADOW_VALIDATION_ENABLED",
        description="Habilitar validação em shadow mode"
    )
    shadow_sample_size: int = Field(
        default=1000,
        env="SHADOW_SAMPLE_SIZE",
        description="Número de amostras para validação shadow"
    )
    shadow_accuracy_threshold: float = Field(
        default=0.95,
        env="SHADOW_ACCURACY_THRESHOLD",
        description="Threshold de accuracy relativo ao baseline (95%)"
    )
    shadow_latency_threshold: float = Field(
        default=1.5,
        env="SHADOW_LATENCY_THRESHOLD",
        description="Threshold de latência relativo ao baseline (150%)"
    )
    shadow_kl_divergence_threshold: float = Field(
        default=0.1,
        env="SHADOW_KL_DIVERGENCE_THRESHOLD",
        description="Threshold de KL divergence máxima permitida"
    )

    # =========================================================================
    # Rollback Configuration
    # =========================================================================
    rollback_enabled: bool = Field(
        default=True,
        env="ROLLBACK_ENABLED",
        description="Habilitar rollback automático"
    )
    rollback_f1_drop_threshold: float = Field(
        default=0.05,
        env="ROLLBACK_F1_DROP_THRESHOLD",
        description="Drop máximo de F1 antes de rollback (5%)"
    )
    rollback_latency_increase_threshold: float = Field(
        default=0.5,
        env="ROLLBACK_LATENCY_INCREASE_THRESHOLD",
        description="Aumento máximo de latência antes de rollback (50%)"
    )
    max_model_versions: int = Field(
        default=10,
        env="MAX_MODEL_VERSIONS",
        description="Número máximo de versões de modelo mantidas"
    )
    rollback_cooldown_minutes: int = Field(
        default=60,
        env="ROLLBACK_COOLDOWN_MINUTES",
        description="Cooldown entre rollbacks consecutivos"
    )

    # =========================================================================
    # Deployment Configuration
    # =========================================================================
    gradual_rollout_enabled: bool = Field(
        default=True,
        env="GRADUAL_ROLLOUT_ENABLED",
        description="Habilitar rollout gradual"
    )
    rollout_stages: List[int] = Field(
        default=[10, 50, 100],
        env="ROLLOUT_STAGES",
        description="Estágios de rollout (percentual de tráfego)"
    )
    rollout_stage_duration_minutes: int = Field(
        default=60,
        env="ROLLOUT_STAGE_DURATION_MINUTES",
        description="Duração de cada estágio de rollout"
    )
    deployment_cooldown_minutes: int = Field(
        default=30,
        env="DEPLOYMENT_COOLDOWN_MINUTES",
        description="Cooldown entre deployments"
    )

    # =========================================================================
    # Ensemble Configuration
    # =========================================================================
    ensemble_strategy: str = Field(
        default="weighted_average",
        env="ONLINE_ENSEMBLE_STRATEGY",
        description="Estratégia: weighted_average, stacking, dynamic_routing"
    )
    batch_model_weight: float = Field(
        default=0.7,
        env="BATCH_MODEL_WEIGHT",
        description="Peso do modelo batch no ensemble"
    )
    online_model_weight: float = Field(
        default=0.3,
        env="ONLINE_MODEL_WEIGHT",
        description="Peso do modelo online no ensemble"
    )
    dynamic_weight_window_hours: int = Field(
        default=1,
        env="DYNAMIC_WEIGHT_WINDOW_HOURS",
        description="Janela para cálculo de pesos dinâmicos"
    )
    fallback_to_batch_on_online_failure: bool = Field(
        default=True,
        env="FALLBACK_TO_BATCH_ON_ONLINE_FAILURE",
        description="Fallback para batch model se online falhar"
    )

    # =========================================================================
    # Monitoring Configuration
    # =========================================================================
    monitoring_enabled: bool = Field(
        default=True,
        env="ONLINE_MONITORING_ENABLED",
        description="Habilitar monitoramento de online learning"
    )
    convergence_stall_threshold_hours: int = Field(
        default=2,
        env="CONVERGENCE_STALL_THRESHOLD_HOURS",
        description="Horas sem redução de loss para detectar stall"
    )
    memory_leak_threshold_mb: int = Field(
        default=500,
        env="MEMORY_LEAK_THRESHOLD_MB",
        description="Crescimento de memória para detectar leak"
    )
    prediction_stability_variance_threshold: float = Field(
        default=0.1,
        env="PREDICTION_STABILITY_VARIANCE_THRESHOLD",
        description="Variância máxima entre predições consecutivas"
    )

    # =========================================================================
    # MLflow Configuration
    # =========================================================================
    mlflow_tracking_uri: str = Field(
        default="http://localhost:5000",
        env="MLFLOW_TRACKING_URI",
        description="URI do servidor MLflow"
    )
    mlflow_online_experiment_prefix: str = Field(
        default="online-learning",
        env="MLFLOW_ONLINE_EXPERIMENT_PREFIX",
        description="Prefixo para experimentos de online learning"
    )

    # =========================================================================
    # Storage Configuration
    # =========================================================================
    mongodb_uri: str = Field(
        default="mongodb://localhost:27017",
        env="MONGODB_URI",
        description="URI do MongoDB"
    )
    mongodb_database: str = Field(
        default="neural_hive",
        env="MONGODB_DATABASE",
        description="Database do MongoDB"
    )
    online_models_collection: str = Field(
        default="online_models",
        env="ONLINE_MODELS_COLLECTION",
        description="Collection para modelos online"
    )
    checkpoint_storage_path: str = Field(
        default="/data/online_learning/checkpoints",
        env="CHECKPOINT_STORAGE_PATH",
        description="Path para checkpoints de modelos"
    )
    max_checkpoint_size_mb: int = Field(
        default=100,
        env="MAX_CHECKPOINT_SIZE_MB",
        description="Tamanho máximo de checkpoint em MB"
    )

    # =========================================================================
    # Notification Configuration
    # =========================================================================
    notification_channels: List[str] = Field(
        default=["slack"],
        env="ONLINE_NOTIFICATION_CHANNELS",
        description="Canais de notificação: slack, email"
    )
    slack_webhook_url: Optional[str] = Field(
        default=None,
        env="SLACK_WEBHOOK_URL",
        description="Webhook URL do Slack"
    )
    email_recipients: Optional[str] = Field(
        default=None,
        env="EMAIL_RECIPIENTS",
        description="Destinatários de email separados por vírgula"
    )

    # =========================================================================
    # Validators
    # =========================================================================
    @field_validator('incremental_algorithm')
    @classmethod
    def validate_incremental_algorithm(cls, v):
        """Valida que algoritmo incremental é suportado."""
        valid_algorithms = ['sgd', 'passive_aggressive', 'perceptron']
        if v not in valid_algorithms:
            raise ValueError(
                f"incremental_algorithm deve ser um de {valid_algorithms}, recebido: {v}"
            )
        return v

    @field_validator('ensemble_strategy')
    @classmethod
    def validate_ensemble_strategy(cls, v):
        """Valida que estratégia de ensemble é suportada."""
        valid_strategies = ['weighted_average', 'stacking', 'dynamic_routing']
        if v not in valid_strategies:
            raise ValueError(
                f"ensemble_strategy deve ser um de {valid_strategies}, recebido: {v}"
            )
        return v

    @field_validator('shadow_accuracy_threshold')
    @classmethod
    def validate_shadow_accuracy_threshold(cls, v):
        """Valida que threshold de accuracy está em range válido."""
        if not 0.5 <= v <= 1.0:
            raise ValueError(
                f"shadow_accuracy_threshold deve estar entre 0.5 e 1.0, recebido: {v}"
            )
        return v

    @field_validator('rollout_stages')
    @classmethod
    def validate_rollout_stages(cls, v):
        """Valida que estágios de rollout são válidos."""
        if not v:
            raise ValueError("rollout_stages não pode ser vazio")
        for stage in v:
            if not 0 < stage <= 100:
                raise ValueError(
                    f"Cada estágio de rollout deve estar entre 1 e 100, recebido: {stage}"
                )
        if v[-1] != 100:
            raise ValueError("Último estágio de rollout deve ser 100%")
        return v

    @field_validator('batch_model_weight', 'online_model_weight')
    @classmethod
    def validate_model_weights(cls, v):
        """Valida que pesos de modelo estão em range válido."""
        if not 0.0 <= v <= 1.0:
            raise ValueError(
                f"Peso de modelo deve estar entre 0.0 e 1.0, recebido: {v}"
            )
        return v

    @field_validator('mini_batch_size')
    @classmethod
    def validate_mini_batch_size(cls, v):
        """Valida que mini_batch_size é positivo."""
        if v <= 0:
            raise ValueError(f"mini_batch_size deve ser maior que 0, recebido: {v}")
        if v > 1000:
            logger.warning(
                "mini_batch_size muito alto pode impactar performance",
                mini_batch_size=v
            )
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def load_config() -> OnlineLearningConfig:
    """
    Carrega configuração do ambiente.

    Returns:
        OnlineLearningConfig configurado
    """
    try:
        config = OnlineLearningConfig()
        logger.info(
            "online_learning_config_loaded",
            enabled=config.online_learning_enabled,
            algorithm=config.incremental_algorithm,
            shadow_validation=config.shadow_validation_enabled,
            rollback_enabled=config.rollback_enabled
        )
        return config
    except Exception as e:
        logger.error("failed_to_load_config", error=str(e))
        raise
