"""Testes unitários para Settings."""



from src.config.settings import Settings, get_settings


def test_default_settings():
    """Testa configurações padrão."""
    settings = Settings()
    assert settings.service_name == "data-migration"
    assert settings.port == 8019
    assert settings.api_prefix == "/api/v1"
    assert settings.api_version == "1.0.0"


def test_get_settings_singleton():
    """Testa que get_settings retorna singleton."""
    settings1 = get_settings()
    settings2 = get_settings()
    assert settings1 is settings2


def test_settings_from_env(monkeypatch):
    """Testa configurações de variáveis de ambiente."""
    monkeypatch.setenv("DATA_MIGRATION_PORT", "8080")
    monkeypatch.setenv("DATA_MIGRATION_DEBUG", "true")
    monkeypatch.setenv("DATA_MIGRATION_BATCH_SIZE", "500")

    settings = Settings()
    assert settings.port == 8080
    assert settings.debug is True
    assert settings.batch_size == 500


def test_llm_settings():
    """Testa configurações de LLM."""
    settings = Settings()
    assert settings.llm_provider == "openai"
    assert settings.llm_model == "gpt-4-turbo-preview"
    assert settings.llm_temperature == 0.3
    assert settings.llm_max_tokens == 8000


def test_database_settings():
    """Testa configurações de banco de dados."""
    settings = Settings()
    assert settings.postgres_url == "postgresql://localhost:5432/legacy"
    assert settings.mongodb_url == "mongodb://localhost:27017"
    assert settings.redis_url == "redis://localhost:6379/1"


def test_migration_settings():
    """Testa configurações de migração."""
    settings = Settings()
    assert settings.batch_size == 1000
    assert settings.max_parallel_migrations == 5
    assert settings.rollback_timeout_seconds == 30


def test_service_registry_settings():
    """Testa configurações do Service Registry."""
    settings = Settings()
    assert settings.service_registry_grpc_host == "service-registry"
    assert settings.service_registry_grpc_port == 50051
    assert settings.service_registry_namespace == "default"
    assert settings.service_registry_cluster == "neural-hive"


def test_s3_settings():
    """Testa configurações de S3/MinIO."""
    settings = Settings()
    assert settings.s3_endpoint == "http://localhost:9000"
    assert settings.s3_bucket == "nhm-migration-dumps"
    assert settings.s3_use_ssl is False


def test_debezium_settings():
    """Testa configurações do Debezium."""
    settings = Settings()
    assert settings.debezium_url == "http://localhost:8083"


def test_kafka_settings():
    """Testa configurações do Kafka."""
    settings = Settings()
    assert settings.kafka_bootstrap_servers == "localhost:9092"
    assert settings.kafka_consumer_group == "data-migration-consumers"
    assert settings.kafka_output_topic == "migration.progress"
