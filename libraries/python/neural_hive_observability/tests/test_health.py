"""
Testes para o módulo health.py da biblioteca neural_hive_observability.

Este arquivo contém testes unitários para validar:
- HealthStatus enum
- HealthCheckResult dataclass
- HealthCheck base class
- DatabaseHealthCheck
- KafkaHealthCheck
- MemoryHealthCheck
- RedisHealthCheck
- CustomHealthCheck
- HealthChecker
- HealthManager alias
"""

import asyncio
import pytest
from unittest.mock import Mock, patch

from neural_hive_observability.config import ObservabilityConfig
from neural_hive_observability.health import (
    HealthStatus,
    HealthCheckResult,
    HealthCheck,
    DatabaseHealthCheck,
    KafkaHealthCheck,
    MemoryHealthCheck,
    RedisHealthCheck,
    CustomHealthCheck,
    HealthChecker,
    HealthManager,
)


class TestHealthStatus:
    """Testes para HealthStatus enum."""

    def test_health_status_values(self):
        """Testa valores do enum HealthStatus."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestHealthCheckResult:
    """Testes para HealthCheckResult."""

    def test_create_result(self):
        """Testa criação de resultado."""
        result = HealthCheckResult(
            name="test-check", status=HealthStatus.HEALTHY, message="Test OK"
        )

        assert result.name == "test-check"
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "Test OK"
        assert result.details == {}
        assert result.duration_seconds == 0.0

    def test_create_result_with_details(self):
        """Testa criação com detalhes."""
        result = HealthCheckResult(
            name="test-check", status=HealthStatus.HEALTHY, details={"key": "value", "count": 42}
        )

        assert result.details == {"key": "value", "count": 42}

    def test_create_result_with_duration(self):
        """Testa criação com duração."""
        result = HealthCheckResult(
            name="test-check", status=HealthStatus.HEALTHY, duration_seconds=1.5
        )

        assert result.duration_seconds == 1.5


class TestHealthCheck:
    """Testes para HealthCheck base class."""

    def test_health_check_is_abstract(self):
        """Testa que HealthCheck é abstrata."""
        with pytest.raises(TypeError):
            HealthCheck(name="test")

    def test_health_check_initialization(self):
        """Testa inicialização de subclass."""

        class ConcreteHealthCheck(HealthCheck):
            async def check(self):
                return self._create_result(HealthStatus.HEALTHY)

        hc = ConcreteHealthCheck(name="concrete", timeout_seconds=10.0)

        assert hc.name == "concrete"
        assert hc.timeout_seconds == 10.0

    def test_create_result_helper(self):
        """Testa método helper _create_result."""

        class ConcreteHealthCheck(HealthCheck):
            async def check(self):
                return self._create_result(HealthStatus.HEALTHY, "Test OK", {"key": "value"}, 0.0)

        hc = ConcreteHealthCheck(name="concrete")

        # Executar check
        result = asyncio.run(hc.check())

        assert result.status == HealthStatus.HEALTHY
        assert result.message == "Test OK"
        assert result.details == {"key": "value"}


class TestDatabaseHealthCheck:
    """Testes para DatabaseHealthCheck."""

    @pytest.mark.asyncio
    async def test_check_with_connection(self):
        """Testa check com conexão ativa."""
        connection_check = Mock(return_value=True)

        db_check = DatabaseHealthCheck(name="database", connection_check=connection_check)

        result = await db_check.check()

        assert result.status == HealthStatus.HEALTHY
        assert "OK" in result.message

    @pytest.mark.asyncio
    async def test_check_with_no_connection(self):
        """Testa check sem conexão."""
        connection_check = Mock(return_value=False)

        db_check = DatabaseHealthCheck(name="database", connection_check=connection_check)

        result = await db_check.check()

        assert result.status == HealthStatus.UNHEALTHY
        assert "Falha" in result.message

    @pytest.mark.asyncio
    async def test_check_without_config(self):
        """Testa check sem configuração."""
        db_check = DatabaseHealthCheck(name="database")

        result = await db_check.check()

        assert result.status == HealthStatus.UNKNOWN
        assert "não configurado" in result.message

    @pytest.mark.asyncio
    async def test_check_with_timeout(self):
        """Testa check com timeout."""

        async def slow_check():
            await asyncio.sleep(10)
            return True

        db_check = DatabaseHealthCheck(
            name="database", connection_check=slow_check, timeout_seconds=0.1
        )

        result = await db_check.check()

        assert result.status == HealthStatus.UNHEALTHY
        assert "Timeout" in result.message

    @pytest.mark.asyncio
    async def test_check_with_exception(self):
        """Testa check com exceção."""
        connection_check = Mock(side_effect=Exception("Connection error"))

        db_check = DatabaseHealthCheck(name="database", connection_check=connection_check)

        result = await db_check.check()

        assert result.status == HealthStatus.UNHEALTHY
        assert "Connection error" in result.message


class TestKafkaHealthCheck:
    """Testes para KafkaHealthCheck."""

    @pytest.mark.asyncio
    async def test_check_with_connection(self):
        """Testa check com conexão ativa."""
        producer_check = Mock(return_value=True)

        kafka_check = KafkaHealthCheck(name="kafka", producer_check=producer_check)

        result = await kafka_check.check()

        assert result.status == HealthStatus.HEALTHY
        assert "OK" in result.message

    @pytest.mark.asyncio
    async def test_check_with_no_connection(self):
        """Testa check sem conexão."""
        producer_check = Mock(return_value=False)

        kafka_check = KafkaHealthCheck(name="kafka", producer_check=producer_check)

        result = await kafka_check.check()

        assert result.status == HealthStatus.UNHEALTHY
        assert "Falha" in result.message

    @pytest.mark.asyncio
    async def test_check_without_config(self):
        """Testa check sem configuração."""
        kafka_check = KafkaHealthCheck(name="kafka")

        result = await kafka_check.check()

        assert result.status == HealthStatus.UNKNOWN
        assert "não configurado" in result.message

    @pytest.mark.asyncio
    async def test_check_with_timeout(self):
        """Testa check com timeout."""

        async def slow_check():
            await asyncio.sleep(10)
            return True

        kafka_check = KafkaHealthCheck(name="kafka", producer_check=slow_check, timeout_seconds=0.1)

        result = await kafka_check.check()

        assert result.status == HealthStatus.UNHEALTHY
        assert "Timeout" in result.message


class TestMemoryHealthCheck:
    """Testes para MemoryHealthCheck."""

    @pytest.mark.asyncio
    async def test_check_with_psutil_available(self):
        """Testa check com psutil disponível."""
        with patch("neural_hive_observability.health.psutil") as mock_psutil:
            mock_process = Mock()
            mock_process.memory_percent.return_value = 50.0
            mock_process.memory_info.return_value = Mock(
                rss=1024 * 1024 * 100, vms=1024 * 1024 * 200
            )
            mock_psutil.Process.return_value = mock_process

            mem_check = MemoryHealthCheck(name="memory", max_memory_percent=80.0)

            result = await mem_check.check()

            assert result.status == HealthStatus.HEALTHY
            assert "normal" in result.message.lower()
            assert result.details is not None
            assert "memory_percent" in result.details

    @pytest.mark.asyncio
    async def test_check_with_high_memory(self):
        """Testa check com memória alta."""
        with patch("neural_hive_observability.health.psutil") as mock_psutil:
            mock_process = Mock()
            mock_process.memory_percent.return_value = 90.0
            mock_process.memory_info.return_value = Mock(
                rss=1024 * 1024 * 500, vms=1024 * 1024 * 1000
            )
            mock_psutil.Process.return_value = mock_process

            mem_check = MemoryHealthCheck(name="memory", max_memory_percent=80.0)

            result = await mem_check.check()

            assert result.status == HealthStatus.UNHEALTHY
            assert "alto" in result.message.lower()

    @pytest.mark.asyncio
    async def test_check_with_degraded_memory(self):
        """Testa check com memória degradada."""
        with patch("neural_hive_observability.health.psutil") as mock_psutil:
            mock_process = Mock()
            mock_process.memory_percent.return_value = 75.0
            mock_process.memory_info.return_value = Mock(
                rss=1024 * 1024 * 400, vms=1024 * 1024 * 800
            )
            mock_psutil.Process.return_value = mock_process

            mem_check = MemoryHealthCheck(name="memory", max_memory_percent=80.0)

            result = await mem_check.check()

            assert result.status == HealthStatus.DEGRADED
            assert "elevado" in result.message.lower()

    @pytest.mark.asyncio
    async def test_check_without_psutil(self):
        """Testa check sem psutil."""
        with patch("neural_hive_observability.health.psutil", side_effect=ImportError):
            mem_check = MemoryHealthCheck(name="memory")

            result = await mem_check.check()

            assert result.status == HealthStatus.UNKNOWN
            assert "psutil não disponível" in result.message


class TestRedisHealthCheck:
    """Testes para RedisHealthCheck."""

    @pytest.mark.asyncio
    async def test_check_with_sync_connection(self):
        """Testa check com conexão síncrona."""
        connection_check = Mock(return_value=True)

        redis_check = RedisHealthCheck(name="redis", connection_check=connection_check)

        result = await redis_check.check()

        assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_with_async_connection(self):
        """Testa check com conexão assíncrona."""

        async def async_ping():
            return True

        redis_check = RedisHealthCheck(name="redis", connection_check=async_ping)

        result = await redis_check.check()

        assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_with_no_connection(self):
        """Testa check sem conexão."""
        connection_check = Mock(return_value=False)

        redis_check = RedisHealthCheck(name="redis", connection_check=connection_check)

        result = await redis_check.check()

        assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_check_without_config(self):
        """Testa check sem configuração."""
        redis_check = RedisHealthCheck(name="redis")

        result = await redis_check.check()

        assert result.status == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_check_with_exception(self):
        """Testa check com exceção."""
        connection_check = Mock(side_effect=Exception("Redis error"))

        redis_check = RedisHealthCheck(name="redis", connection_check=connection_check)

        result = await redis_check.check()

        assert result.status == HealthStatus.UNHEALTHY


class TestCustomHealthCheck:
    """Testes para CustomHealthCheck."""

    @pytest.mark.asyncio
    async def test_check_with_sync_function(self):
        """Testa check com função síncrona."""
        check_func = Mock(return_value=True)

        custom_check = CustomHealthCheck(
            name="custom", check_func=check_func, description="Custom check"
        )

        result = await custom_check.check()

        assert result.status == HealthStatus.HEALTHY
        assert "saudável" in result.message.lower()

    @pytest.mark.asyncio
    async def test_check_with_async_function(self):
        """Testa check com função assíncrona."""

        async def async_check():
            return True

        custom_check = CustomHealthCheck(
            name="custom", check_func=async_check, description="Async custom check"
        )

        result = await custom_check.check()

        assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_returns_false(self):
        """Testa check que retorna False."""
        check_func = Mock(return_value=False)

        custom_check = CustomHealthCheck(name="custom", check_func=check_func)

        result = await custom_check.check()

        assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_check_with_exception(self):
        """Testa check que lança exceção."""
        check_func = Mock(side_effect=Exception("Check error"))

        custom_check = CustomHealthCheck(name="custom", check_func=check_func)

        result = await custom_check.check()

        assert result.status == HealthStatus.UNHEALTHY


class TestHealthChecker:
    """Testes para HealthChecker."""

    def test_initialization(self):
        """Testa inicialização do HealthChecker."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        checker = HealthChecker(config)

        assert checker.config == config
        assert checker.checks == {}

    def test_register_check(self):
        """Testa registro de health check."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        checker = HealthChecker(config)

        class TestCheck(HealthCheck):
            async def check(self):
                return self._create_result(HealthStatus.HEALTHY)

        test_check = TestCheck(name="test")
        checker.register_check(test_check)

        assert "test" in checker.checks
        assert checker.checks["test"] == test_check

    def test_register_default_checks(self):
        """Testa registro de checks padrão."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        checker = HealthChecker(config)
        checker.register_default_checks()

        # Deve ter check de memória
        assert "memory" in checker.checks

    @pytest.mark.asyncio
    async def test_check_all(self):
        """Testa execução de todos os checks."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        checker = HealthChecker(config)
        checker.register_default_checks()

        results = await checker.check_all()

        assert "memory" in results
        assert results["memory"].status in [
            HealthStatus.HEALTHY,
            HealthStatus.DEGRADED,
            HealthStatus.UNHEALTHY,
            HealthStatus.UNKNOWN,
        ]

    @pytest.mark.asyncio
    async def test_check_single(self):
        """Testa execução de check único."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        checker = HealthChecker(config)
        checker.register_default_checks()

        result = await checker.check_single("memory")

        assert result is not None
        assert result.name == "memory"

    @pytest.mark.asyncio
    async def test_check_single_not_found(self):
        """Testa check único não encontrado."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        checker = HealthChecker(config)

        result = await checker.check_single("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_check_single_with_exception(self):
        """Testa check único com exceção."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        checker = HealthChecker(config)

        class FailingCheck(HealthCheck):
            async def check(self):
                raise Exception("Check failed")

        checker.register_check(FailingCheck(name="failing"))

        result = await checker.check_single("failing")

        assert result is not None
        assert result.status == HealthStatus.UNHEALTHY
        assert "Erro interno" in result.message

    def test_get_last_results(self):
        """Testa obtenção dos últimos resultados."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        checker = HealthChecker(config)

        # Sem resultados ainda
        results = checker.get_last_results()
        assert results == {}

    def test_get_overall_status_without_results(self):
        """Testa status geral sem resultados."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        checker = HealthChecker(config)

        status = checker.get_overall_status()
        assert status == HealthStatus.UNKNOWN

    def test_get_overall_status_with_all_healthy(self):
        """Testa status geral com todos healthy."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        checker = HealthChecker(config)

        # Simular resultados todos healthy
        checker._last_results = {
            "check1": Mock(status=HealthStatus.HEALTHY),
            "check2": Mock(status=HealthStatus.HEALTHY),
        }

        status = checker.get_overall_status()
        assert status == HealthStatus.HEALTHY

    def test_get_overall_status_with_unhealthy(self):
        """Testa status geral com um unhealthy."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        checker = HealthChecker(config)

        checker._last_results = {
            "check1": Mock(status=HealthStatus.HEALTHY),
            "check2": Mock(status=HealthStatus.UNHEALTHY),
        }

        status = checker.get_overall_status()
        assert status == HealthStatus.UNHEALTHY

    def test_get_overall_status_with_degraded(self):
        """Testa status geral com degraded."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        checker = HealthChecker(config)

        checker._last_results = {
            "check1": Mock(status=HealthStatus.HEALTHY),
            "check2": Mock(status=HealthStatus.DEGRADED),
        }

        status = checker.get_overall_status()
        assert status == HealthStatus.DEGRADED

    def test_to_dict(self):
        """Testa conversão para dicionário."""
        config = ObservabilityConfig(
            service_name="test-service",
            service_version="1.0.0",
            neural_hive_component="test-component",
            neural_hive_layer="test-layer",
        )

        checker = HealthChecker(config)

        result_dict = checker.to_dict()

        assert result_dict["overall_status"] == "unknown"
        assert result_dict["service"]["name"] == "test-service"
        assert result_dict["service"]["version"] == "1.0.0"
        assert result_dict["service"]["component"] == "test-component"
        assert "checks" in result_dict


class TestHealthManagerAlias:
    """Testes para HealthManager alias."""

    def test_health_manager_is_health_checker(self):
        """Testa que HealthManager é alias para HealthChecker."""
        assert HealthManager == HealthChecker


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
