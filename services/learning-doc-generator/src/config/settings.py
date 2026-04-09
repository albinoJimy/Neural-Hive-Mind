"""Configurações do Learning Documentation Generator"""

from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações do Learning Documentation Generator"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )

    # Aplicação
    environment: str = Field(default="dev", description="Ambiente de execução")
    debug: bool = Field(default=False, description="Modo debug")
    log_level: str = Field(default="INFO", description="Nível de log")
    service_name: str = Field(default="learning-doc-generator", description="Nome do serviço")
    service_version: str = Field(default="1.0.0", description="Versão do serviço")

    # API
    api_host: str = Field(default="0.0.0.0", description="Host da API")
    api_port: int = Field(default=8009, description="Porta da API", gt=0)
    api_workers: int = Field(default=1, description="Número de workers", gt=0)

    # Prometheus
    prometheus_port: int = Field(default=8089, description="Porta do Prometheus", gt=0)

    # OpenTelemetry
    otel_endpoint: str = Field(
        default="http://otel-collector.neural-hive.svc.cluster.local:4317",
        description="Endpoint OTEL",
    )
    otel_exporter_otlp_headers: Optional[str] = Field(
        default=None, description="Headers OTEL (key=value;key2=value2)"
    )

    # Kafka
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092", description="Kafka bootstrap servers"
    )
    kafka_consumer_group: str = Field(
        default="learning-doc-generator", description="Consumer group ID"
    )
    kafka_topic_experiments: str = Field(
        default="experiments", description="Tópico de experimentos"
    )
    kafka_topic_models: str = Field(
        default="models", description="Tópico de modelos"
    )
    kafka_topic_deployments: str = Field(
        default="deployments", description="Tópico de deployments"
    )
    kafka_enable_consumer: bool = Field(
        default=True, description="Habilitar consumer Kafka"
    )
    kafka_security_protocol: str = Field(default="PLAINTEXT", description="Security protocol")
    kafka_sasl_mechanism: Optional[str] = Field(default=None, description="SASL mechanism")
    kafka_sasl_username: Optional[str] = Field(default=None, description="SASL username")
    kafka_sasl_password: Optional[str] = Field(default=None, description="SASL password")

    # Tópicos Kafka
    kafka_experiment_completed_topic: str = Field(
        default="experiment.completed", description="Tópico de experimento concluído"
    )
    kafka_model_promoted_topic: str = Field(
        default="model.promoted", description="Tópico de modelo promovido"
    )
    kafka_deployment_rollback_topic: str = Field(
        default="deployment.rolled_back", description="Tópico de rollback"
    )
    kafka_learning_doc_generated_topic: str = Field(
        default="learning.doc.generated", description="Tópico de documento gerado"
    )

    # MongoDB
    mongodb_uri: str = Field(
        default="mongodb://localhost:27017", description="URI do MongoDB"
    )
    mongodb_database: str = Field(default="neural_hive", description="Database MongoDB")
    mongodb_collection: str = Field(
        default="learning_documents", description="Collection de documentos"
    )

    # MLflow
    mlflow_tracking_uri: str = Field(
        default="http://mlflow.neural-hive.svc.cluster.local:5000",
        description="URI do MLflow Tracking Server",
    )
    mlflow_timeout_seconds: int = Field(default=30, description="Timeout MLflow", gt=0)

    # Document Generation
    docs_output_dir: str = Field(
        default="/tmp/learning_docs", description="Diretório de saída dos documentos"
    )
    docs_template_dir: str = Field(
        default="/app/templates", description="Diretório de templates Jinja2"
    )
    docs_include_plots: bool = Field(default=True, description="Incluir gráficos nos documentos")
    docs_plot_format: str = Field(
        default="png", description="Formato dos gráficos (png/svg)"
    )

    # Scheduler
    scheduler_enabled: bool = Field(default=True, description="Habilitar scheduler")
    scheduler_daily_hour: int = Field(default=9, description="Hora do relatório diário", ge=0, le=23)
    scheduler_daily_minute: int = Field(default=0, description="Minuto do relatório diário", ge=0, le=59)
    scheduler_weekly_day: int = Field(
        default=0, description="Dia do relatório semanal (0=Monday)", ge=0, le=6
    )
    scheduler_monthly_day: int = Field(
        default=1, description="Dia do relatório mensal", ge=1, le=28
    )

    # Limites
    max_experiments_per_doc: int = Field(
        default=100, description="Máximo de experimentos por documento", gt=0
    )
    doc_generation_timeout_seconds: int = Field(
        default=300, description="Timeout de geração", gt=0
    )

    # Feature Flags
    enable_pdf_generation: bool = Field(default=False, description="Habilitar geração de PDF")
    enable_slack_notifications: bool = Field(default=False, description="Notificar Slack")

    # Slack (opcional)
    slack_webhook_url: Optional[str] = Field(default=None, description="Slack webhook URL")
    slack_channel: Optional[str] = Field(default=None, description="Slack channel")

    @field_validator("docs_plot_format")
    @classmethod
    def validate_plot_format(cls, v: str) -> str:
        """Valida formato do gráfico"""
        if v not in ("png", "svg", "html"):
            raise ValueError('docs_plot_format deve ser "png", "svg" ou "html"')
        return v


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """Singleton para Settings"""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
