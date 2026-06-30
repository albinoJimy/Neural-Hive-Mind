"""
Configuracao do Approval Service

Gerencia todas as configuracoes usando Pydantic Settings com suporte a variaveis de ambiente.
"""

import os
import sys
from typing import Optional

import structlog
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings

from neural_hive_security.cors import CORSConfig

logger = structlog.get_logger()


def require_mongodb_database_explicit(environment: str, explicit: bool, under_pytest: bool) -> None:
    """
    Nucleo testavel do fail-fast de MONGODB_DATABASE (convergencia DBs, Fase 5, 8.1).

    Levanta ``ValueError`` quando, fora de pytest e fora de ambiente test/local, a
    env var MONGODB_DATABASE NAO foi definida explicitamente — forcando configuracao
    explicita da DB e eliminando o default implicito que gerou drift.

    Args:
        environment: valor de ``settings.environment``.
        explicit: True se MONGODB_DATABASE veio do ambiente (nao do default).
        under_pytest: True se a correr sob pytest (entao nunca falha).
    """
    if not under_pytest and environment.lower() not in ("test", "local") and not explicit:
        raise ValueError(
            "MONGODB_DATABASE tem de ser definido explicitamente em ambiente "
            f"'{environment}' (convergencia DBs Fase 5: sem default implicito de DB; "
            "defina a env var MONGODB_DATABASE no deployment)."
        )


class Settings(BaseSettings):
    """Configuracoes do Approval Service"""

    # Configuracao da aplicacao
    environment: str = Field(default="dev", description="Ambiente (dev, staging, production)")
    debug: bool = Field(default=False, description="Modo debug")
    log_level: str = Field(default="INFO", description="Nivel de log")
    service_name: str = Field(default="approval-service", description="Nome do servico")
    service_version: str = Field(default="1.0.0", description="Versao do servico")

    # CORS - Approval service é API pública
    is_public_api: bool = Field(default=True, description="API pública requer CORS")

    @property
    def cors_origins(self) -> list[str]:
        """CORS origins dinâmicas por ambiente."""
        return CORSConfig.get_origins_for_environment(
            self.environment, is_public_api=self.is_public_api
        )

    # Kafka Consumer configuration
    kafka_bootstrap_servers: str = Field(..., description="Servidores Kafka bootstrap")
    kafka_consumer_group_id: str = Field(
        default="approval-service", description="ID do grupo de consumer Kafka"
    )
    kafka_approval_requests_topic: str = Field(
        default="cognitive-plans-approval-requests", description="Topico para requests de aprovacao"
    )
    kafka_approval_responses_topic: str = Field(
        default="cognitive-plans-approval-responses",
        description="Topico para responses de aprovacao",
    )
    kafka_auto_offset_reset: str = Field(default="earliest", description="Auto offset reset")
    kafka_enable_auto_commit: bool = Field(default=False, description="Enable auto commit")
    kafka_session_timeout_ms: int = Field(default=30000, description="Session timeout (ms)")
    kafka_max_poll_interval_ms: int = Field(default=300000, description="Max poll interval (ms)")

    # Kafka Producer configuration
    kafka_enable_idempotence: bool = Field(default=True, description="Habilitar idempotencia")
    kafka_transactional_id: Optional[str] = Field(None, description="ID transacional")

    # Kafka Security
    kafka_security_protocol: str = Field(default="PLAINTEXT", description="Protocolo de seguranca")
    kafka_sasl_mechanism: Optional[str] = Field(None, description="Mecanismo SASL")
    kafka_sasl_username: Optional[str] = Field(None, description="Usuario SASL")
    kafka_sasl_password: Optional[str] = Field(None, description="Senha SASL")

    # Kafka Startup Resilience (retry com backoff exponencial na validacao de topicos)
    kafka_startup_max_retries: int = Field(
        default=10,
        description="Numero maximo de tentativas de conexao ao Kafka no startup",
    )
    kafka_startup_initial_backoff_seconds: float = Field(
        default=1.0,
        description="Backoff inicial (s) entre tentativas de conexao Kafka no startup",
    )
    kafka_startup_max_backoff_seconds: float = Field(
        default=30.0,
        description="Backoff maximo (s) entre tentativas de conexao Kafka no startup",
    )
    kafka_startup_retry_missing_topics: bool = Field(
        default=True,
        description=(
            "Se True, faz retry quando topicos estao em falta (apropriado apenas "
            "durante o bootstrap inicial do cluster, onde os topicos sao criados em "
            "paralelo). ATENCAO: em producao, manter True atrasa a deteccao de "
            "misconfiguracoes deterministicas (nome de topico/namespace errado) ate "
            "esgotar todas as tentativas (~max_retries * max_backoff segundos). Em "
            "producao, preferir False (fail-fast) salvo durante bootstrap explicito."
        ),
    )

    # Schema Registry
    schema_registry_url: Optional[str] = Field(None, description="URL do Schema Registry")

    # MongoDB configuration
    mongodb_uri: str = Field(
        default="mongodb://mongodb.mongodb-cluster.svc.cluster.local:27017",
        description="URI do MongoDB",
    )
    mongodb_database: str = Field(default="neural_hive", description="Database do MongoDB")
    mongodb_collection: str = Field(
        default="plan_approvals", description="Collection para aprovacoes"
    )
    mongodb_max_pool_size: int = Field(default=100, description="Tamanho maximo do pool")
    mongodb_timeout_ms: int = Field(default=5000, description="Timeout (ms)")

    # Feedback Collection Configuration (para ML continuous learning)
    enable_feedback_collection: bool = Field(
        default=True, description="Habilitar coleta de feedback para ML"
    )
    feedback_mongodb_collection: str = Field(
        default="specialist_feedback", description="Collection MongoDB para feedback"
    )
    mongodb_opinions_collection: str = Field(
        default="specialist_opinions", description="Collection do ledger cognitivo"
    )
    feedback_rating_min: float = Field(default=0.0, description="Rating minimo")
    feedback_rating_max: float = Field(default=1.0, description="Rating maximo")
    feedback_on_approval_failure_mode: str = Field(
        default="log_and_continue",
        description="Comportamento em falha de feedback: log_and_continue ou raise_error",
    )

    # Active Learning Configuration
    # Activado em producao em 2026-03-30 (Epic G001 - GAP-02-05-06)
    # Pre-requisitos implementados: feedback_consumer, online_learning_service, integracao main.py
    # ROLLBACK: Mudar para False e redeloyar approval-service
    enable_active_learning: bool = Field(
        default=True, description="Habilitar active learning para coleta de feedbacks balanceados"
    )
    active_learning_queue_collection: str = Field(
        default="active_learning_queue",
        description="Collection MongoDB para fila de active learning",
    )
    active_learning_min_information_value: float = Field(
        default=0.5, description="Valor informacional minimo para enfileirar (0-1)"
    )
    active_learning_enqueue_rate: float = Field(
        default=0.2, description="Taxa de casos para enfileirar (0-1, 20% dos casos)"
    )

    # Online Learning Configuration
    enable_online_learning: bool = Field(
        default=False, description="Habilitar online learning para aprendizado incremental"
    )
    online_learning_buffer_size: int = Field(
        default=100, description="Tamanho do buffer de feedbacks para partial_fit"
    )
    online_learning_retrain_interval_hours: int = Field(
        default=24, description="Intervalo em horas para retreino periodico"
    )
    kafka_specialist_feedback_topic: str = Field(
        default="specialist-feedback", description="Topico Kafka para feedback de especialistas"
    )
    online_learning_checkpoint_path: str = Field(
        default="/data/online_learning/checkpoints",
        description="Caminho para salvar checkpoints dos modelos online",
    )
    online_learning_algorithm: str = Field(
        default="sgd", description="Algoritmo incremental: sgd, passive_aggressive, perceptron"
    )
    online_learning_learning_rate: float = Field(
        default=0.001, description="Taxa de aprendizado para SGD"
    )
    online_learning_checkpoint_interval_updates: int = Field(
        default=100, description="Intervalo de updates para salvar checkpoint"
    )

    # Keycloak configuration
    keycloak_url: str = Field(
        default="http://keycloak.keycloak.svc.cluster.local:8080", description="URL do Keycloak"
    )
    keycloak_realm: str = Field(default="neural-hive", description="Realm do Keycloak")
    keycloak_client_id: str = Field(default="approval-service", description="Client ID")
    admin_role_name: str = Field(default="neural-hive-admin", description="Nome da role admin")
    require_auth: bool = Field(
        default=True,
        description="Require JWT authentication",
        validation_alias="APPROVAL_SERVICE_REQUIRE_AUTH",
    )

    # Observability configuration
    otel_endpoint: str = Field(
        default="https://opentelemetry-collector.observability.svc.cluster.local:4317",
        description="Endpoint do OpenTelemetry",
    )
    otel_tls_verify: bool = Field(
        default=True, description="Verificar certificado TLS do OTEL Collector"
    )
    prometheus_port: int = Field(default=8000, description="Porta do Prometheus metrics")
    jaeger_sampling_rate: float = Field(default=1.0, description="Taxa de amostragem Jaeger")

    # Rate Limiting
    rate_limit_requests_per_minute: int = Field(
        default=100, description="Limite de requests por minuto por usuario"
    )

    # ML Predictor Configuration
    enable_ml_prediction: bool = Field(
        default=False, description="Habilitar predicao ML automatica para aprovacoes"
    )
    ml_model_path: str = Field(
        default="/app/ml_models/nhm_approval_model.pkl",
        description="Caminho para o modelo ML de aprovacao",
    )
    ml_auto_approve_threshold: float = Field(
        default=0.7, description="Confianca minima para auto-aprovacao (0.0-1.0)"
    )
    ml_auto_reject_threshold: float = Field(
        default=0.7, description="Confianca minima para auto-rejeicao (0.0-1.0)"
    )
    ml_max_risk_for_auto: str = Field(
        default="low",
        description="Risco maximo para decisao automatica (low, medium, high, critical)",
    )

    @field_validator("kafka_security_protocol")
    @classmethod
    def validate_security_in_production(cls, v, info):
        """Valida que seguranca esta habilitada em producao"""
        values = info.data
        if values.get("environment") == "production" and v == "PLAINTEXT":
            raise ValueError("Ambiente de producao requer conexao Kafka encriptada")
        return v

    @model_validator(mode="after")
    def validate_cors_in_production(self) -> "Settings":
        """
        Valida que serviços públicos não usam wildcard CORS em produção.
        """
        is_prod = self.environment.lower() in ("production", "prod")

        if not is_prod:
            return self

        # Valida que não tem wildcard nas origens
        CORSConfig.validate_no_wildcard(self.cors_origins, self.environment)

        return self

    @model_validator(mode="after")
    def validate_https_in_production(self) -> "Settings":
        """
        Valida que endpoints HTTP criticos usam HTTPS em producao/staging.
        """
        is_prod_staging = self.environment.lower() in ("production", "staging", "prod")
        if not is_prod_staging:
            return self

        # Endpoints criticos que devem usar HTTPS em producao
        http_endpoints = []
        if self.otel_endpoint.startswith("http://"):
            http_endpoints.append(("otel_endpoint", self.otel_endpoint))
        if self.keycloak_url.startswith("http://"):
            http_endpoints.append(("keycloak_url", self.keycloak_url))

        if http_endpoints:
            endpoint_list = ", ".join(f"{name}={url}" for name, url in http_endpoints)
            raise ValueError(
                f"Endpoints HTTP inseguros detectados em ambiente {self.environment}: {endpoint_list}. "
                "Use HTTPS em producao/staging para garantir seguranca de dados em transito."
            )

        return self

    @model_validator(mode="after")
    def warn_kafka_retry_missing_topics_in_production(self) -> "Settings":
        """
        Emite aviso proeminente quando o retry de topicos em falta esta ativo em producao.

        Em producao, ``kafka_startup_retry_missing_topics=True`` atrasa a deteccao de
        misconfiguracoes deterministicas (nome de topico ou namespace errado) ate
        esgotar todas as tentativas (~max_retries * max_backoff segundos), em vez de
        falhar de imediato. Mantemos o default True para suportar bootstrap do cluster,
        mas alertamos os operadores do risco de falha tardia.
        """
        is_prod = self.environment.lower() in ("production", "prod")
        if is_prod and self.kafka_startup_retry_missing_topics:
            logger.warning(
                "kafka_startup_retry_missing_topics=True em producao: deteccao de "
                "topicos mal configurados sera atrasada ate esgotar as tentativas. "
                "Considere False para fail-fast salvo durante bootstrap do cluster.",
                environment=self.environment,
                max_retries=self.kafka_startup_max_retries,
                max_backoff_seconds=self.kafka_startup_max_backoff_seconds,
            )
        return self

    @model_validator(mode="after")
    def require_explicit_mongodb_database(self) -> "Settings":
        """
        Anti-regressao da convergencia DBs (Fase 5, Task 8.1).

        Em ambiente de deployment real, MONGODB_DATABASE tem de ser definido
        EXPLICITAMENTE — elimina o default implicito 'neural_hive' que gerou o drift
        que partiu o pipeline (f786fb16/6fddd01d). Sob pytest ou em ambiente
        test/local o default mantem-se (nao quebra testes/CI). Em
        production/staging/development sem MONGODB_DATABASE explicito, falha-fast.

        A logica esta extraida em ``require_mongodb_database_explicit`` (funcao pura,
        testavel sem depender do guard de pytest).
        """
        under_pytest = "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules
        explicit = "MONGODB_DATABASE" in os.environ or "mongodb_database" in os.environ
        require_mongodb_database_explicit(self.environment, explicit, under_pytest)
        return self

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Obtem instancia singleton das configuracoes"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
