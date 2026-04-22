"""Tests for neural_hive_exceptions library."""

import grpc

from neural_hive_exceptions import (
    ConfigErrorCode,
    ConfigurationError,
    ConnectionError,
    DatabaseError,
    GRPCError,
    InfrastructureErrorCode,
    KafkaError,
    NeuralHiveError,
    TimeoutError,
    ValidationError,
    ValidationErrorCode,
    error_code,
    grpc_error_to_status,
)


class TestNeuralHiveError:
    """Test base exception class."""

    def test_basic_creation(self):
        """Test creating basic error."""
        error = NeuralHiveError(message="Test error", code="NHM_TEST_001")
        assert error.message == "Test error"
        assert error.code == "NHM_TEST_001"
        assert error.http_status == 500

    def test_to_dict(self):
        """Test conversion to dictionary."""
        error = NeuralHiveError(message="Test error", code="NHM_TEST_001", details={"key": "value"})
        result = error.to_dict()
        assert result["error"] == "NHM_TEST_001"
        assert result["message"] == "Test error"
        assert result["details"]["key"] == "value"


class TestErrorCode:
    """Test error code generation."""

    def test_error_code_with_prefix(self):
        """Test error code that already has prefix."""
        code = error_code("NHM_VALIDATION_001")
        assert code == "NHM_VALIDATION_001"

    def test_error_code_without_prefix(self):
        """Test error code without prefix."""
        code = error_code("VALIDATION_001")
        assert code == "NHM_VALIDATION_001"


class TestValidationError:
    """Test validation exception."""

    def test_missing_field(self):
        """Test missing field helper."""
        error = ValidationError.missing_field("email")
        assert error.code == ValidationErrorCode.MISSING_REQUIRED_FIELD
        assert error.details["field"] == "email"
        assert error.http_status == 400

    def test_invalid_format(self):
        """Test invalid format helper."""
        error = ValidationError.invalid_format(
            field="email", value="invalid", expected_format="user@domain.com"
        )
        assert "email" in error.details["field"]
        assert "invalid" in error.details["provided_value"]

    def test_out_of_range(self):
        """Test out of range helper."""
        error = ValidationError.out_of_range(field="age", value=150, min_val=0, max_val=120)
        assert error.details["reason"]
        assert "min=0" in error.details["reason"]


class TestConfigurationError:
    """Test configuration exception."""

    def test_missing_required(self):
        """Test missing required config helper."""
        error = ConfigurationError.missing_required("DATABASE_URL")
        assert error.code == ConfigErrorCode.MISSING_REQUIRED_CONFIG
        assert error.details["config_key"] == "DATABASE_URL"

    def test_invalid_value(self):
        """Test invalid value helper."""
        error = ConfigurationError.invalid_value(config_key="PORT", value="abc", expected="numeric")
        assert error.code == ConfigErrorCode.INVALID_VALUE
        assert "abc" in error.details["reason"]

    def test_missing_env_var(self):
        """Test missing env var helper."""
        error = ConfigurationError.missing_env_var("API_KEY")
        assert error.code == ConfigErrorCode.MISSING_ENV_VAR
        assert error.details["config_key"] == "API_KEY"


class TestGRPCError:
    """Test gRPC exception."""

    def test_creation_with_status(self):
        """Test creating gRPC error with status code."""
        error = GRPCError(message="Resource not found", status_code=grpc.StatusCode.NOT_FOUND)
        assert error.grpc_status_code == grpc.StatusCode.NOT_FOUND
        assert error.http_status == 404

    def test_to_dict_includes_grpc_info(self):
        """Test dictionary includes gRPC status."""
        error = GRPCError(message="Test", status_code=grpc.StatusCode.INVALID_ARGUMENT)
        result = error.to_dict()
        assert "grpc_status" in result["details"]
        assert result["details"]["grpc_status"] == "INVALID_ARGUMENT"


class TestGRPCErrorConversion:
    """Test gRPC error to status conversion."""

    def test_neural_hive_error_conversion(self):
        """Test converting NeuralHiveError to gRPC status."""
        error = NeuralHiveError("Test error", http_status=404)
        status = grpc_error_to_status(error)
        assert status == grpc.StatusCode.NOT_FOUND

    def test_validation_error_conversion(self):
        """Test converting ValidationError to gRPC status."""
        error = ValidationError("Test error")
        status = grpc_error_to_status(error)
        assert status == grpc.StatusCode.INVALID_ARGUMENT

    def test_key_error_conversion(self):
        """Test converting KeyError to NOT_FOUND."""
        status = grpc_error_to_status(KeyError("test"))
        assert status == grpc.StatusCode.NOT_FOUND

    def test_value_error_conversion(self):
        """Test converting ValueError to INVALID_ARGUMENT."""
        status = grpc_error_to_status(ValueError("test"))
        assert status == grpc.StatusCode.INVALID_ARGUMENT


class TestConnectionError:
    """Test connection exception."""

    def test_service_unavailable(self):
        """Test service unavailable helper."""
        error = ConnectionError.service_unavailable(
            service="postgresql", host="localhost", port=5432
        )
        assert error.code == InfrastructureErrorCode.CONNECTION_FAILED
        assert error.details["service"] == "postgresql"
        assert error.http_status == 503

    def test_connection_error_details(self):
        """Test connection error includes details."""
        error = ConnectionError(
            message="Cannot connect",
            service="redis",
            host="localhost",
            port=6379,
            reason="Connection refused",
        )
        assert error.details["host"] == "localhost"
        assert error.details["port"] == 6379
        assert error.details["reason"] == "Connection refused"


class TestTimeoutError:
    """Test timeout exception."""

    def test_operation_timeout(self):
        """Test operation timeout helper."""
        error = TimeoutError.operation_timeout(
            operation="database_query", timeout_seconds=30.0, service="postgresql"
        )
        assert error.code == InfrastructureErrorCode.CONNECTION_TIMEOUT
        assert error.details["operation"] == "database_query"
        assert error.details["timeout_seconds"] == 30.0
        assert error.http_status == 504


class TestDatabaseError:
    """Test database exception."""

    def test_query_failed(self):
        """Test query failed helper."""
        error = DatabaseError.query_failed(
            query="SELECT * FROM users", reason="Table does not exist", database="mydb"
        )
        assert error.code == InfrastructureErrorCode.DATABASE_ERROR
        assert "SELECT" in error.details["query"]
        assert error.details["database"] == "mydb"

    def test_long_query_truncation(self):
        """Test long queries are truncated in details."""
        long_query = "SELECT * FROM users WHERE " + " AND ".join(
            [f"field{i} = {i}" for i in range(50)]
        )
        error = DatabaseError.query_failed(query=long_query, reason="Error")
        assert len(error.details["query"]) <= 203  # 200 + "..."


class TestKafkaError:
    """Test Kafka exception."""

    def test_producer_error(self):
        """Test producer error helper."""
        error = KafkaError.producer_error(topic="test-topic", reason="Broker not available")
        assert error.code == InfrastructureErrorCode.KAFKA_PRODUCER_ERROR
        assert error.details["topic"] == "test-topic"

    def test_consumer_error(self):
        """Test consumer error helper."""
        error = KafkaError.consumer_error(topic="test-topic", reason="Consumer group not found")
        assert error.code == InfrastructureErrorCode.KAFKA_CONSUMER_ERROR
        assert error.details["topic"] == "test-topic"

    def test_generic_error_conversion(self):
        """Test converting generic error to UNKNOWN."""
        status = grpc_error_to_status(RuntimeError("test"))
        assert status == grpc.StatusCode.UNKNOWN
