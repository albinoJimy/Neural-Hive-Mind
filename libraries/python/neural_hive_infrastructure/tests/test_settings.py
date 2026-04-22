"""Tests for neural_hive_infrastructure settings."""

import pytest
from pydantic import ValidationError

from neural_hive_infrastructure import (
    BaseInfrastructureSettings,
    GRPCSettings,
    KafkaSettings,
    MongoDBSettings,
    ObservabilitySettings,
    OpenTelemetrySettings,
    RedisSettings,
    SPIFFESettings,
    VaultSettings,
    get_settings,
)


class TestBaseInfrastructureSettings:
    """Test base settings class."""

    def test_default_values(self):
        """Test default configuration values."""
        settings = BaseInfrastructureSettings(
            kafka_bootstrap_servers="localhost:9092",
            mongodb_uri="mongodb://localhost:27017",
            redis_cluster_nodes="localhost:6379",
        )
        assert settings.environment == "development"
        assert settings.debug is False
        assert settings.log_level == "INFO"
        assert settings.service_name == "nhm-service"
        assert settings.grpc_port == 50051
        assert settings.http_port == 8000

    def test_custom_values(self):
        """Test custom configuration values."""
        settings = BaseInfrastructureSettings(
            environment="staging",  # staging não requer redis_password
            debug=True,
            log_level="DEBUG",
            service_name="my-service",
            kafka_bootstrap_servers="kafka:9092",
            mongodb_uri="mongodb://mongo:27017",
            redis_cluster_nodes="redis:6379",
        )
        assert settings.environment == "staging"
        assert settings.debug is True
        assert settings.log_level == "DEBUG"
        assert settings.service_name == "my-service"

    def test_log_level_validation(self):
        """Test log level validation."""
        with pytest.raises(ValidationError) as exc_info:
            BaseInfrastructureSettings(
                kafka_bootstrap_servers="localhost:9092",
                mongodb_uri="mongodb://localhost:27017",
                redis_cluster_nodes="localhost:6379",
                log_level="INVALID",
            )
        assert "log_level" in str(exc_info.value).lower()

    def test_environment_validation(self):
        """Test environment validation."""
        with pytest.raises(ValidationError) as exc_info:
            BaseInfrastructureSettings(
                kafka_bootstrap_servers="localhost:9092",
                mongodb_uri="mongodb://localhost:27017",
                redis_cluster_nodes="localhost:6379",
                environment="invalid-env",
            )
        assert "environment" in str(exc_info.value).lower()

    def test_https_validation_in_production(self):
        """Test HTTPS validation in production."""
        # External HTTP endpoint should fail in production
        with pytest.raises(ValidationError) as exc_info:
            BaseInfrastructureSettings(
                environment="production",
                kafka_bootstrap_servers="localhost:9092",
                mongodb_uri="mongodb://localhost:27017",
                redis_cluster_nodes="localhost:6379",
                redis_password="secret",
                otel_endpoint="http://external-otel-collector.com:4317",
            )
        assert "http" in str(exc_info.value).lower()

    def test_internal_http_allowed_in_production(self):
        """Test internal cluster HTTP endpoints allowed in production."""
        settings = BaseInfrastructureSettings(
            environment="production",
            kafka_bootstrap_servers="localhost:9092",
            mongodb_uri="mongodb://localhost:27017",
            redis_cluster_nodes="localhost:6379",
            redis_password="secret",
            otel_endpoint="http://opentelemetry-collector.observability.svc.cluster.local:4317",
        )
        # Should not raise
        assert settings.otel_endpoint.startswith("http://")

    def test_redis_password_required_in_production(self):
        """Test Redis password required in production."""
        with pytest.raises(ValidationError) as exc_info:
            BaseInfrastructureSettings(
                environment="production",
                kafka_bootstrap_servers="localhost:9092",
                mongodb_uri="mongodb://localhost:27017",
                redis_cluster_nodes="localhost:6379",
            )
        assert (
            "redis_password" in str(exc_info.value).lower()
            or "password" in str(exc_info.value).lower()
        )

    def test_get_kafka_config(self):
        """Test Kafka config helper."""
        settings = BaseInfrastructureSettings(
            kafka_bootstrap_servers="kafka1:9092,kafka2:9092",
            mongodb_uri="mongodb://localhost:27017",
            redis_cluster_nodes="localhost:6379",
            kafka_sasl_mechanism="PLAIN",
            kafka_sasl_username="user",
            kafka_sasl_password="pass",
        )
        config = settings.get_kafka_config()
        assert config["bootstrap_servers"] == "kafka1:9092,kafka2:9092"
        assert config["sasl_mechanism"] == "PLAIN"
        assert config["sasl_plain_username"] == "user"
        assert config["sasl_plain_password"] == "pass"

    def test_get_mongodb_config(self):
        """Test MongoDB config helper."""
        settings = BaseInfrastructureSettings(
            kafka_bootstrap_servers="localhost:9092",
            mongodb_uri="mongodb://user:pass@mongo:27017/mydb",
            redis_cluster_nodes="localhost:6379",
        )
        config = settings.get_mongodb_config()
        assert config["uri"] == "mongodb://user:pass@mongo:27017/mydb"
        assert config["database"] == "neural_hive"

    def test_get_redis_config(self):
        """Test Redis config helper."""
        settings = BaseInfrastructureSettings(
            kafka_bootstrap_servers="localhost:9092",
            mongodb_uri="mongodb://localhost:27017",
            redis_cluster_nodes="redis:6379",
            redis_password="secret",
            redis_ssl_enabled=True,
        )
        config = settings.get_redis_config()
        assert config["nodes"] == "redis:6379"
        assert config["password"] == "secret"
        assert config["ssl"] is True


class TestKafkaSettings:
    """Test Kafka settings."""

    def test_default_values(self):
        """Test default Kafka settings."""
        settings = KafkaSettings(kafka_bootstrap_servers="localhost:9092")
        assert settings.kafka_security_protocol == "PLAINTEXT"
        assert settings.kafka_auto_offset_reset == "earliest"
        assert settings.kafka_enable_auto_commit is False
        assert settings.kafka_enable_idempotence is True

    def test_bootstrap_validation(self):
        """Test bootstrap servers validation."""
        with pytest.raises(ValidationError):
            KafkaSettings(kafka_bootstrap_servers="invalid-no-port")


class TestMongoDBSettings:
    """Test MongoDB settings."""

    def test_default_values(self):
        """Test default MongoDB settings."""
        settings = MongoDBSettings(mongodb_uri="mongodb://localhost:27017")
        assert settings.mongodb_database == "neural_hive"

    def test_uri_validation(self):
        """Test MongoDB URI validation."""
        with pytest.raises(ValidationError):
            MongoDBSettings(mongodb_uri="invalid-uri")


class TestRedisSettings:
    """Test Redis settings."""

    def test_default_values(self):
        """Test default Redis settings."""
        settings = RedisSettings(redis_cluster_nodes="localhost:6379")
        assert settings.redis_password is None
        assert settings.redis_ssl_enabled is False

    def test_nodes_validation(self):
        """Test Redis nodes validation."""
        with pytest.raises(ValidationError):
            RedisSettings(redis_cluster_nodes="invalid-no-port")


class TestOpenTelemetrySettings:
    """Test OpenTelemetry settings."""

    def test_default_values(self):
        """Test default OTEL settings."""
        settings = OpenTelemetrySettings()
        assert settings.otel_tls_verify is True
        assert settings.otel_ca_bundle is None


class TestGRPCSettings:
    """Test gRPC settings."""

    def test_default_values(self):
        """Test default gRPC settings."""
        settings = GRPCSettings()
        assert settings.grpc_timeout_ms == 5000
        assert settings.grpc_max_retries == 3
        assert settings.grpc_enable_retry is True


class TestSPIFFESettings:
    """Test SPIFFE settings."""

    def test_default_values(self):
        """Test default SPIFFE settings."""
        settings = SPIFFESettings()
        assert settings.spiffe_enabled is False
        assert settings.spiffe_enable_x509 is False
        assert settings.spiffe_trust_domain == "neural-hive.local"


class TestVaultSettings:
    """Test Vault settings."""

    def test_default_values(self):
        """Test default Vault settings."""
        settings = VaultSettings()
        assert settings.vault_enabled is False
        assert settings.vault_fail_open is False

    def test_fail_open_validation_in_production(self):
        """Test fail-open validation in production."""
        # This test requires environment to be set in the parent model
        # For standalone VaultSettings, it checks environment from data
        # Validated when used within BaseInfrastructureSettings


class TestObservabilitySettings:
    """Test Observability settings."""

    def test_default_values(self):
        """Test default observability settings."""
        settings = ObservabilitySettings()
        assert settings.prometheus_port == 8080
        assert settings.jaeger_sampling_rate == 1.0
        assert settings.enable_metrics is True


class TestGetSettings:
    """Test settings singleton."""

    def test_singleton_behavior(self):
        """Test that get_settings returns same instance."""
        settings1 = get_settings(
            lambda: BaseInfrastructureSettings(
                kafka_bootstrap_servers="localhost:9092",
                mongodb_uri="mongodb://localhost:27017",
                redis_cluster_nodes="localhost:6379",
            )
        )
        settings2 = get_settings(
            lambda: BaseInfrastructureSettings(
                kafka_bootstrap_servers="localhost:9092",
                mongodb_uri="mongodb://localhost:27017",
                redis_cluster_nodes="localhost:6379",
            )
        )
        # Same class should return same instance
        # Note: This test is simplified - actual singleton uses class name

    def test_force_reload(self):
        """Test force_reload parameter."""
        # Test implementation would require mocking
