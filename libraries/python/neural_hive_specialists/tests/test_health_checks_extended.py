"""
Testes unitários para HealthChecks.

Cobertura para observability/health_checks.py
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from typing import Dict, Any
from datetime import datetime


class TestHealthChecks:
    """Testes para HealthChecks."""

    @pytest.fixture
    def config(self):
        """Configuração de teste."""
        return {
            "mongodb_uri": "mongodb://localhost:27017",
            "mongodb_database": "test_db",
            "redis_cluster_nodes": "localhost:6379",
            "neo4j_uri": "bolt://localhost:7687",
            "neo4j_user": "neo4j",
            "neo4j_password": "password",
        }

    @pytest.fixture
    def mock_dependencies(self):
        """Mock de dependências externas."""
        with patch('neural_hive_specialists.observability.health_checks.MongoClient') as mock_mongo:
            with patch('neural_hive_specialists.observability.health_checks.Redis') as mock_redis:
                with patch('neural_hive_specialists.observability.health_checks.GraphDatabase') as mock_neo4j:
                    yield {
                        "mongo": mock_mongo,
                        "redis": mock_redis,
                        "neo4j": mock_neo4j,
                    }

    def test_init_with_config(self, config, mock_dependencies):
        """Testa inicialização com configuração."""
        from neural_hive_specialists.observability.health_checks import HealthChecks

        health = HealthChecks(config)

        assert health.config == config
        assert health.mongodb_uri == "mongodb://localhost:27017"

    def test_check_mongodb_healthy(self, config):
        """Testa check de MongoDB quando saudável."""
        with patch('neural_hive_specialists.observability.health_checks.MongoClient') as mock_mongo_class:
            mock_client = MagicMock()
            mock_db = MagicMock()
            mock_client.server_info.return_value = {"version": "5.0.0"}
            mock_client.__getitem__.return_value = mock_db
            mock_mongo_class.return_value = mock_client

            from neural_hive_specialists.observability.health_checks import HealthChecks

            health = HealthChecks(config)
            result = health.check_mongodb()

            assert result["status"] == "healthy"
            assert "version" in result["details"]
            assert result["latency_ms"] >= 0

    def test_check_mongodb_unhealthy(self, config):
        """Testa check de MongoDB quando não saudável."""
        with patch('neural_hive_specialists.observability.health_checks.MongoClient') as mock_mongo_class:
            mock_client = MagicMock()
            mock_client.server_info.side_effect = Exception("Connection error")
            mock_mongo_class.return_value = mock_client

            from neural_hive_specialists.observability.health_checks import HealthChecks

            health = HealthChecks(config)
            result = health.check_mongodb()

            assert result["status"] == "unhealthy"
            assert "error" in result["details"]

    def test_check_redis_healthy(self, config):
        """Testa check de Redis quando saudável."""
        with patch('neural_hive_specialists.observability.health_checks.Redis') as mock_redis_class:
            mock_redis = MagicMock()
            mock_redis.ping.return_value = True
            mock_redis_class.return_value = mock_redis

            from neural_hive_specialists.observability.health_checks import HealthChecks

            health = HealthChecks(config)
            result = health.check_redis()

            assert result["status"] == "healthy"
            assert result["latency_ms"] >= 0

    def test_check_redis_unhealthy(self, config):
        """Testa check de Redis quando não saudável."""
        with patch('neural_hive_specialists.observability.health_checks.Redis') as mock_redis_class:
            mock_redis = MagicMock()
            mock_redis.ping.side_effect = Exception("Connection error")
            mock_redis_class.return_value = mock_redis

            from neural_hive_specialists.observability.health_checks import HealthChecks

            health = HealthChecks(config)
            result = health.check_redis()

            assert result["status"] == "unhealthy"
            assert "error" in result["details"]

    def test_check_neo4j_healthy(self, config):
        """Testa check de Neo4j quando saudável."""
        with patch('neural_hive_specialists.observability.health_checks.GraphDatabase') as mock_neo4j_class:
            mock_driver = MagicMock()
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.single.return_value = {"version": "4.4.0"}
            mock_session.run.return_value = mock_result
            mock_driver.session.return_value = mock_session
            mock_neo4j_class.driver.return_value = mock_driver

            from neural_hive_specialists.observability.health_checks import HealthChecks

            health = HealthChecks(config)
            result = health.check_neo4j()

            assert result["status"] == "healthy"
            assert "version" in result["details"]

    def test_check_neo4j_unhealthy(self, config):
        """Testa check de Neo4j quando não saudável."""
        with patch('neural_hive_specialists.observability.health_checks.GraphDatabase') as mock_neo4j_class:
            mock_driver = MagicMock()
            mock_driver.session.side_effect = Exception("Connection error")
            mock_neo4j_class.driver.return_value = mock_driver

            from neural_hive_specialists.observability.health_checks import HealthChecks

            health = HealthChecks(config)
            result = health.check_neo4j()

            assert result["status"] == "unhealthy"
            assert "error" in result["details"]

    def test_check_all_services(self, config):
        """Testa check de todos os serviços."""
        with patch('neural_hive_specialists.observability.health_checks.MongoClient') as mock_mongo:
            with patch('neural_hive_specialists.observability.health_checks.Redis') as mock_redis:
                with patch('neural_hive_specialists.observability.health_checks.GraphDatabase') as mock_neo4j:
                    # Setup mocks
                    mock_client = MagicMock()
                    mock_client.server_info.return_value = {"version": "5.0.0"}
                    mock_mongo.return_value = mock_client

                    mock_redis_instance = MagicMock()
                    mock_redis_instance.ping.return_value = True
                    mock_redis.return_value = mock_redis_instance

                    mock_driver = MagicMock()
                    mock_session = MagicMock()
                    mock_result = MagicMock()
                    mock_result.single.return_value = {"version": "4.4.0"}
                    mock_session.run.return_value = mock_result
                    mock_driver.session.return_value = mock_session
                    mock_neo4j.driver.return_value = mock_driver

                    from neural_hive_specialists.observability.health_checks import HealthChecks

                    health = HealthChecks(config)
                    result = health.check_all()

                    assert "overall_status" in result
                    assert "mongodb" in result["services"]
                    assert "redis" in result["services"]
                    assert "neo4j" in result["services"]
                    assert "timestamp" in result

    def test_get_health_summary_degraded(self, config):
        """Testa resumo de saúde com serviços degradados."""
        with patch('neural_hive_specialists.observability.health_checks.MongoClient') as mock_mongo:
            with patch('neural_hive_specialists.observability.health_checks.Redis') as mock_redis:
                with patch('neural_hive_specialists.observability.health_checks.GraphDatabase') as mock_neo4j:
                    # Mongo healthy, Redis unhealthy, Neo4j healthy
                    mock_client = MagicMock()
                    mock_client.server_info.return_value = {"version": "5.0.0"}
                    mock_mongo.return_value = mock_client

                    mock_redis_instance = MagicMock()
                    mock_redis_instance.ping.side_effect = Exception("Error")
                    mock_redis.return_value = mock_redis_instance

                    mock_driver = MagicMock()
                    mock_session = MagicMock()
                    mock_result = MagicMock()
                    mock_result.single.return_value = {"version": "4.4.0"}
                    mock_session.run.return_value = mock_result
                    mock_driver.session.return_value = mock_session
                    mock_neo4j.driver.return_value = mock_driver

                    from neural_hive_specialists.observability.health_checks import HealthChecks

                    health = HealthChecks(config)
                    result = health.check_all()

                    # Deve ser degraded pois um serviço está unhealthy
                    assert result["overall_status"] in ["degraded", "unhealthy"]

    def test_get_health_summary_unhealthy(self, config):
        """Testa resumo de saúde com todos serviços não saudáveis."""
        with patch('neural_hive_specialists.observability.health_checks.MongoClient') as mock_mongo:
            with patch('neural_hive_specialists.observability.health_checks.Redis') as mock_redis:
                with patch('neural_hive_specialists.observability.health_checks.GraphDatabase') as mock_neo4j:
                    # Todos unhealthy
                    mock_client = MagicMock()
                    mock_client.server_info.side_effect = Exception("Error")
                    mock_mongo.return_value = mock_client

                    mock_redis_instance = MagicMock()
                    mock_redis_instance.ping.side_effect = Exception("Error")
                    mock_redis.return_value = mock_redis_instance

                    mock_driver = MagicMock()
                    mock_driver.session.side_effect = Exception("Error")
                    mock_neo4j.driver.return_value = mock_driver

                    from neural_hive_specialists.observability.health_checks import HealthChecks

                    health = HealthChecks(config)
                    result = health.check_all()

                    assert result["overall_status"] == "unhealthy"

    def test_check_disk_space(self, config):
        """Testa check de espaço em disco."""
        with patch('neural_hive_specialists.observability.health_checks.shutil') as mock_shutil:
            mock_shutil.disk_usage.return_value = MagicMock(
                total=1000000000,  # 1GB
                used=500000000,   # 500MB
                free=500000000,   # 500MB
            )

            from neural_hive_specialists.observability.health_checks import HealthChecks

            health = HealthChecks(config)
            result = health.check_disk_space("/")

            assert "status" in result
            assert "usage_percent" in result["details"]
            assert result["details"]["usage_percent"] == 50.0

    def test_check_disk_space_high_usage(self, config):
        """Testa check de espaço em disco com uso alto."""
        with patch('neural_hive_specialists.observability.health_checks.shutil') as mock_shutil:
            mock_shutil.disk_usage.return_value = MagicMock(
                total=1000000000,
                used=900000000,  # 90%
                free=100000000,
            )

            from neural_hive_specialists.observability.health_checks import HealthChecks

            health = HealthChecks(config)
            result = health.check_disk_space("/")

            # Uso > 80% deve ser degraded ou unhealthy
            assert result["status"] in ["degraded", "unhealthy"]

    def test_check_memory_usage(self, config):
        """Testa check de uso de memória."""
        with patch('neural_hive_specialists.observability.health_checks.psutil') as mock_psutil:
            mock_psutil.virtual_memory.return_value = MagicMock(
                total=8000000000,   # 8GB
                available=4000000000,  # 4GB livre
                percent=50.0,
            )

            from neural_hive_specialists.observability.health_checks import HealthChecks

            health = HealthChecks(config)
            result = health.check_memory_usage()

            assert "status" in result
            assert "usage_percent" in result["details"]
            assert result["details"]["usage_percent"] == 50.0

    def test_check_cpu_usage(self, config):
        """Testa check de uso de CPU."""
        with patch('neural_hive_specialists.observability.health_checks.psutil') as mock_psutil:
            mock_psutil.cpu_percent.return_value = 45.0

            from neural_hive_specialists.observability.health_checks import HealthChecks

            health = HealthChecks(config)
            result = health.check_cpu_usage()

            assert "status" in result
            assert "usage_percent" in result["details"]
            assert result["details"]["usage_percent"] == 45.0

    def test_check_cpu_usage_high(self, config):
        """Testa check de CPU com uso alto."""
        with patch('neural_hive_specialists.observability.health_checks.psutil') as mock_psutil:
            mock_psutil.cpu_percent.return_value = 95.0

            from neural_hive_specialists.observability.health_checks import HealthChecks

            health = HealthChecks(config)
            result = health.check_cpu_usage()

            # CPU > 90% deve ser degraded ou unhealthy
            assert result["status"] in ["degraded", "unhealthy"]

    def test_readiness_check(self, config):
        """Testa check de prontidão (readiness)."""
        with patch('neural_hive_specialists.observability.health_checks.MongoClient') as mock_mongo:
            mock_client = MagicMock()
            mock_client.server_info.return_value = {"version": "5.0.0"}
            mock_mongo.return_value = mock_client

            from neural_hive_specialists.observability.health_checks import HealthChecks

            health = HealthChecks(config)
            result = health.readiness_check()

            assert "ready" in result
            assert isinstance(result["ready"], bool)

    def test_liveness_check(self, config):
        """Testa check de vivacidade (liveness)."""
        from neural_hive_specialists.observability.health_checks import HealthChecks

        health = HealthChecks(config)
        result = health.liveness_check()

        assert "alive" in result
        assert result["alive"] is True

    def test_check_service_dependencies(self, config):
        """Testa check de dependências de serviço."""
        with patch('neural_hive_specialists.observability.health_checks.MongoClient') as mock_mongo:
            with patch('neural_hive_specialists.observability.health_checks.Redis') as mock_redis:
                mock_client = MagicMock()
                mock_client.server_info.return_value = {"version": "5.0.0"}
                mock_mongo.return_value = mock_client

                mock_redis_instance = MagicMock()
                mock_redis_instance.ping.return_value = True
                mock_redis.return_value = mock_redis_instance

                from neural_hive_specialists.observability.health_checks import HealthChecks

                health = HealthChecks(config)
                dependencies = ["mongodb", "redis"]
                result = health.check_dependencies(dependencies)

                assert "mongodb" in result
                assert "redis" in result

    def test_get_metrics_summary(self, config):
        """Testa resumo de métricas."""
        from neural_hive_specialists.observability.health_checks import HealthChecks

        health = HealthChecks(config)
        result = health.get_metrics_summary()

        assert "uptime_seconds" in result
        assert "timestamp" in result

    def test_is_healthy_true(self, config):
        """Testa is_healthy retorna True quando tudo está saudável."""
        with patch('neural_hive_specialists.observability.health_checks.MongoClient') as mock_mongo:
            mock_client = MagicMock()
            mock_client.server_info.return_value = {"version": "5.0.0"}
            mock_mongo.return_value = mock_client

            from neural_hive_specialists.observability.health_checks import HealthChecks

            health = HealthChecks(config)
            assert health.is_healthy() is True

    def test_is_healthy_false(self, config):
        """Testa is_healthy retorna False quando algo está não saudável."""
        with patch('neural_hive_specialists.observability.health_checks.MongoClient') as mock_mongo:
            mock_client = MagicMock()
            mock_client.server_info.side_effect = Exception("Error")
            mock_mongo.return_value = mock_client

            from neural_hive_specialists.observability.health_checks import HealthChecks

            health = HealthChecks(config)
            assert health.is_healthy() is False

    def test_timeout_handling(self, config):
        """Testa handling de timeout em checks."""
        with patch('neural_hive_specialists.observability.health_checks.MongoClient') as mock_mongo:
            import time

            def slow_server_info():
                time.sleep(0.1)
                return {"version": "5.0.0"}

            mock_client = MagicMock()
            mock_client.server_info.side_effect = slow_server_info
            mock_mongo.return_value = mock_client

            from neural_hive_specialists.observability.health_checks import HealthChecks

            health = HealthChecks(config)
            result = health.check_mongodb(timeout_ms=50)

            # Deve retornar algo mesmo com timeout curto
            assert "status" in result
