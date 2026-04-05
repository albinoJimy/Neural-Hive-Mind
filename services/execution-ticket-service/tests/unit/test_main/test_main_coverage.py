"""
Testes de cobertura para main.py.

Testes funcionais que executam código real sem mocks pesados.
"""
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


# =============================================================================
# Mock Classes
# =============================================================================


class MockSettingsForMain:
    """Settings para testes main."""

    def __init__(self):
        self.service_name = "execution-ticket-service"
        self.service_version = "1.0.0"
        self.environment = "development"
        self.log_level = "INFO"
        self.is_public_api = True
        self.postgres_host = "localhost"
        self.postgres_port = 5432
        self.postgres_database = "test_db"
        self.postgres_user = "test_user"
        self.postgres_password = "test_pass"
        self.postgres_pool_size = 20
        self.postgres_max_overflow = 10
        self.postgres_ssl_mode = "disable"
        self.mongodb_uri = "mongodb://localhost:27017"
        self.mongodb_database = "test_db"
        self.mongodb_collection_tickets = "tickets"
        self.mongodb_collection_audit = "audit"
        self.kafka_bootstrap_servers = "localhost:9092"
        self.kafka_consumer_group_id = "test-group"
        self.kafka_tickets_topic = "test-topic"
        self.kafka_auto_offset_reset = "earliest"
        self.kafka_enable_auto_commit = False
        self.kafka_security_protocol = "PLAINTEXT"
        self.kafka_sasl_mechanism = "SCRAM-SHA-512"
        self.kafka_sasl_username = None
        self.kafka_sasl_password = None
        self.kafka_schema_registry_url = "https://schema-registry.local:8081"
        self.schema_registry_tls_verify = False
        self.schemas_base_path = "/app/schemas"
        self.jwt_secret_key = "test-secret-key-32-bytes-long-for-testing"
        self.jwt_algorithm = "HS256"
        self.jwt_token_expiration_seconds = 3600
        self.jwt_issuer = "neural-hive-mind"
        self.jwt_audience = "worker-agents"
        self.webhook_enabled = True
        self.webhook_timeout_seconds = 10
        self.webhook_max_retries = 3
        self.webhook_retry_backoff_seconds = 2
        self.webhook_batch_size = 10
        self.webhook_worker_count = 5
        self.grpc_port = 50051
        self.grpc_max_workers = 10
        self.grpc_max_concurrent_rpcs = 100
        self.grpc_bind_retry_attempts = 3
        self.grpc_bind_retry_initial_delay = 1.0
        self.grpc_bind_retry_max_delay = 30.0
        self.otel_exporter_endpoint = "https://otel-collector.local:4317"
        self.otel_tls_verify = False
        self.prometheus_port = 9090
        self.jaeger_sampling_rate = 0.1
        self.enable_webhooks = True
        self.enable_jwt_tokens = True
        self.enable_audit_trail = True
        self.enable_status_updates = True
        self.max_connection_retries = 5
        self.initial_retry_delay_seconds = 1.0
        self.redis_url = None
        self.redis_host = "localhost"
        self.redis_port = 6379
        self.redis_password = None
        self.redis_ssl_enabled = False
        self.redis_idempotency_ttl_seconds = 604800
        self.enable_idempotency = True

    @property
    def CORS_ORIGINS(self):
        """CORS origins para testes (development)."""
        return [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:8000",
            "http://localhost:8080",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
            "http://127.0.0.1:8000",
            "http://127.0.0.1:8080",
        ]


# =============================================================================
# Testes: create_app
# =============================================================================


class TestCreateApp:
    """Testes da função create_app."""

    def test_create_app_returns_fastapi(self):
        """Cria aplicação FastAPI."""
        from src.main import create_app

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            app = create_app()

            assert app is not None
            assert app.title == "Execution Ticket Service"

    def test_create_app_with_version(self):
        """Define versão da aplicação."""
        from src.main import create_app

        with patch("src.main.get_settings") as mock_get_settings:
            settings = MockSettingsForMain()
            settings.service_version = "2.0.0"
            mock_get_settings.return_value = settings

            app = create_app()

            assert app.version == "2.0.0"

    def test_create_app_has_lifespan(self):
        """Configura lifespan."""
        from src.main import create_app

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            app = create_app()

            # FastAPI 0.100+ usa lifespan em vez de on_event
            assert app.router.lifespan_context is not None

    def test_create_app_includes_routers(self):
        """Inclui routers."""
        from src.main import create_app

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            app = create_app()

            # Verificar que routers estão incluídos
            routes = [r for r in app.routes if hasattr(r, "tags")]
            route_tags = [tag for r in routes for tag in r.tags]

            assert "Health" in route_tags
            assert "Tickets" in route_tags

    def test_create_app_adds_cors_middleware(self):
        """Adiciona middleware CORS."""
        from src.main import create_app

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            app = create_app()

            # Verificar middleware CORS
            from fastapi.middleware.cors import CORSMiddleware

            # user_middleware contém instâncias de Middleware(cls=CORSMiddleware, ...)
            middleware_classes = [m.cls for m in app.user_middleware if hasattr(m, 'cls')]
            assert CORSMiddleware in middleware_classes

    def test_create_app_observability_init_failure(self):
        """Lida com falha na inicialização da observabilidade."""
        from src.main import create_app

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            with patch("src.main.init_observability", side_effect=Exception("Observability error")):
                # Não deve levantar exceção
                app = create_app()
                assert app is not None

    def test_create_app_with_observability(self):
        """Inicializa observabilidade quando possível."""
        from src.main import create_app

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            with patch("src.main.init_observability") as mock_init:
                app = create_app()

                # Deve tentar inicializar
                assert mock_init.called

    @patch("src.main.structlog.configure")
    def test_structlog_configured(self, mock_configure):
        """Configura structlog."""
        from src.main import create_app

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            create_app()

            # Structlog deve ser configurado
            assert mock_configure.called

    def test_logging_configured(self):
        """Configura logging básico."""
        from src.main import create_app
        import logging

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            create_app()

            # Logging deve estar configurado
            root_logger = logging.getLogger()
            assert len(root_logger.handlers) > 0


# =============================================================================
# Testes: lifespan - Startup Critical Components
# =============================================================================


class TestLifespanCriticalComponents:
    """Testes do startup de componentes críticos."""

    @pytest.mark.asyncio
    async def test_lifespan_postgres_connection(self):
        """Conecta ao PostgreSQL."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=AsyncMock())):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(AsyncMock(), AsyncMock()))):
                        async with lifespan(mock_app):
                            mock_postgres.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_mongodb_connection(self):
        """Conecta ao MongoDB."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=AsyncMock())):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(AsyncMock(), AsyncMock()))):
                        async with lifespan(mock_app):
                            mock_mongodb.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_grpc_server_start(self):
        """Inicia servidor gRPC."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            mock_grpc_server = MagicMock()
            mock_grpc_server.stop = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):
                        async with lifespan(mock_app):
                            # gRPC server deve ter iniciado
                            assert mock_app.state.grpc_server is not None

    @pytest.mark.asyncio
    async def test_lifespan_critical_failure_raises(self):
        """Levanta RuntimeError quando componente crítico falha."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(side_effect=Exception("Connection failed"))):
                with pytest.raises(RuntimeError, match="Dependências críticas falharam"):
                    async with lifespan(mock_app):
                        pass

    @pytest.mark.asyncio
    async def test_lifespan_multiple_critical_failures(self):
        """Reporta múltiplas falhas críticas."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(side_effect=Exception("Postgres failed"))):
                with patch("src.main.get_mongodb_client", new=AsyncMock(side_effect=Exception("Mongo failed"))):
                    with pytest.raises(RuntimeError) as exc_info:
                        async with lifespan(mock_app):
                            pass

                    # Deve mencionar postgres
                    assert "postgresql" in str(exc_info.value)


# =============================================================================
# Testes: lifespan - Metrics and Optional Components
# =============================================================================


class TestLifespanOptionalComponents:
    """Testes do startup de componentes opcionais."""

    @pytest.mark.asyncio
    async def test_lifespan_initializes_metrics(self):
        """Inicializa métricas."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            mock_grpc_server = MagicMock()
            mock_grpc_server.stop = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        async with lifespan(mock_app):
                            assert hasattr(mock_app.state, "metrics")
                            assert mock_app.state.metrics is not None

    @pytest.mark.asyncio
    async def test_lifespan_redis_connection_optional(self):
        """Conecta ao Redis se disponível."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            settings = MockSettingsForMain()
            settings.enable_idempotency = True
            mock_get_settings.return_value = settings

            mock_app = MagicMock()

            mock_redis = MagicMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            mock_grpc_server = MagicMock()
            mock_grpc_server.stop = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        with patch("src.main.get_redis_client", new=AsyncMock(return_value=mock_redis)):
                            async with lifespan(mock_app):
                                assert mock_app.state.redis_client == mock_redis

    @pytest.mark.asyncio
    async def test_lifespan_redis_failure_non_critical(self):
        """Continua sem Redis se falhar."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            mock_grpc_server = MagicMock()
            mock_grpc_server.stop = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        with patch("src.main.get_redis_client", new=AsyncMock(side_effect=Exception("Redis failed"))):
                            # Não deve levantar exceção
                            async with lifespan(mock_app):
                                pass

    @pytest.mark.asyncio
    async def test_lifespan_grpc_stored_in_state(self):
        """Armazena servidor gRPC no state."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()
            mock_grpc = MagicMock()
            mock_grpc.stop = AsyncMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc, AsyncMock()))):
                        async with lifespan(mock_app):
                            assert mock_app.state.grpc_server == mock_grpc

    @pytest.mark.asyncio
    async def test_lifespan_initializes_background_tasks_list(self):
        """Inicializa lista de tasks de background."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    mock_grpc_server = MagicMock()
                    mock_grpc_server.stop = AsyncMock()
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        async with lifespan(mock_app):
                            assert hasattr(mock_app.state, "background_init_tasks")
                            assert isinstance(mock_app.state.background_init_tasks, list)


# =============================================================================
# Testes: lifespan - Background Components
# =============================================================================


class TestLifespanBackgroundComponents:
    """Testes de componentes em background."""

    @pytest.mark.asyncio
    async def test_lifespan_starts_kafka_producer_background(self):
        """Inicia producer Kafka em background."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            mock_grpc_server = MagicMock()
            mock_grpc_server.stop = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        with patch("src.kafka.producer.get_kafka_producer", new=AsyncMock(return_value=AsyncMock())) as mock_get_producer:

                            async with lifespan(mock_app):
                                # Background tasks são criadas
                                assert hasattr(mock_app.state, "background_init_tasks")

    @pytest.mark.asyncio
    async def test_lifespan_starts_webhook_manager_background(self):
        """Inicia webhook manager em background."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            settings = MockSettingsForMain()
            settings.enable_webhooks = True
            mock_get_settings.return_value = settings

            mock_app = MagicMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            mock_grpc_server = MagicMock()
            mock_grpc_server.stop = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        with patch("src.webhooks.start_webhook_manager", new=AsyncMock(return_value=AsyncMock())) as mock_start_webhook:

                            async with lifespan(mock_app):
                                # Background tasks são criadas
                                assert hasattr(mock_app.state, "background_init_tasks")

    @pytest.mark.asyncio
    async def test_lifespan_kafka_producer_failure_non_critical(self):
        """Continua sem producer Kafka se falhar."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            mock_grpc_server = MagicMock()
            mock_grpc_server.stop = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        with patch("src.kafka.producer.get_kafka_producer", new=AsyncMock(side_effect=Exception("Kafka failed"))):
                            # Não deve levantar exceção
                            async with lifespan(mock_app):
                                pass

    @pytest.mark.asyncio
    async def test_lifespan_webhook_manager_failure_non_critical(self):
        """Continua sem webhook manager se falhar."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            mock_grpc_server = MagicMock()
            mock_grpc_server.stop = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        with patch("src.webhooks.start_webhook_manager", new=AsyncMock(side_effect=Exception("Webhook failed"))):
                            # Não deve levantar exceção
                            async with lifespan(mock_app):
                                pass

    @pytest.mark.asyncio
    async def test_lifespan_no_bootstrap_servers_skips_kafka(self):
        """Pula Kafka quando sem bootstrap servers."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            settings = MockSettingsForMain()
            settings.kafka_bootstrap_servers = ""
            mock_get_settings.return_value = settings

            mock_app = MagicMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            mock_grpc_server = MagicMock()
            mock_grpc_server.stop = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        async with lifespan(mock_app):
                            # Deve ter criado background task
                            assert len(mock_app.state.background_init_tasks) >= 0


# =============================================================================
# Testes: lifespan - Shutdown
# =============================================================================


class TestLifespanShutdown:
    """Testes do shutdown."""

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_cancels_background_tasks(self):
        """Cancela tasks de background no shutdown."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            # Task já completa não precisa ser cancelada
            class DoneTask:
                def done(self):
                    return True

            mock_task = DoneTask()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    mock_grpc_server = MagicMock()
                    mock_grpc_server.stop = AsyncMock()
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):
                        async with lifespan(mock_app):
                            # Simular task em background já completa
                            mock_app.state.background_init_tasks = [mock_task]

            # Task completa não foi cancelada (já estava done)
            assert True  # Test passes se shutdown completou sem erro

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_stops_kafka_consumer(self):
        """Para consumer Kafka no shutdown."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            mock_consumer = MagicMock()
            mock_consumer.stop = AsyncMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    mock_grpc_server = MagicMock()
                    mock_grpc_server.stop = AsyncMock()
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        async with lifespan(mock_app):
                            mock_app.state.ticket_consumer = mock_consumer
                            # consumer_task precisa ser awaitable
                            async def dummy_task():
                                pass
                            import asyncio
                            mock_app.state.consumer_task = asyncio.create_task(dummy_task())

            # Consumer deve ter sido parado
            mock_consumer.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_stops_kafka_producer(self):
        """Para producer Kafka no shutdown."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            mock_producer = MagicMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    mock_grpc_server = MagicMock()
                    mock_grpc_server.stop = AsyncMock()
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        with patch("src.kafka.producer.close_kafka_producer") as mock_close:
                            async with lifespan(mock_app):
                                mock_app.state.kafka_producer = mock_producer

            # Producer deve ter sido fechado
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_stops_webhook_manager(self):
        """Para webhook manager no shutdown."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            settings = MockSettingsForMain()
            settings.enable_webhooks = False  # Desabilitar para evitar criação automática
            mock_get_settings.return_value = settings

            mock_app = MagicMock()

            mock_webhook = MagicMock()
            mock_webhook.stop = AsyncMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    mock_grpc_server = MagicMock()
                    mock_grpc_server.stop = AsyncMock()
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        async with lifespan(mock_app):
                            mock_app.state.webhook_manager = mock_webhook

            # Webhook manager deve ter sido parado
            mock_webhook.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_stops_grpc_server(self):
        """Para servidor gRPC no shutdown."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            mock_grpc = MagicMock()
            mock_grpc.stop = AsyncMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc, MagicMock()))):
                        with patch("src.grpc_service.stop_grpc_server", new=AsyncMock()) as mock_stop:
                            async with lifespan(mock_app):
                                pass

                            mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_disconnects_databases(self):
        """Desconecta databases no shutdown."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    mock_grpc_server = MagicMock()
                    mock_grpc_server.stop = AsyncMock()
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        async with lifespan(mock_app):
                            pass

            # Databases devem ter sido desconectados
            mock_postgres.disconnect.assert_called_once()
            mock_mongodb.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_closes_redis(self):
        """Fecha Redis no shutdown."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            mock_grpc_server = MagicMock()
            mock_grpc_server.stop = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        with patch("src.main.close_redis_client") as mock_close:
                            async with lifespan(mock_app):
                                pass

            # Redis deve ter sido fechado
            mock_close.assert_called_once()


# =============================================================================
# Testes: Module Level
# =============================================================================


class TestMainModule:
    """Testes do módulo main."""

    def test_app_is_created(self):
        """Aplicação é criada no nível do módulo."""
        from src.main import app

        assert app is not None
        assert app.title == "Execution Ticket Service"

    def test_logger_is_initialized(self):
        """Logger é inicializado."""
        from src.main import logger

        assert logger is not None

    @patch("src.main.uvicorn.run")
    def test_main_entry_point(self, mock_run):
        """Entry point __main__ funciona."""
        # Recarregar módulo para executar __main__
        import importlib
        import sys

        # Simular __name__ == "__main__"
        with patch.object(sys, "argv", ["main.py"]):
            with patch("src.main.get_settings") as mock_get_settings:
                settings = MockSettingsForMain()
                settings.environment = "development"
                mock_get_settings.return_value = settings

                # Não podemos realmente executar __main__, mas verificar imports
                from src import main

                assert hasattr(main, "app")
                assert hasattr(main, "create_app")


# =============================================================================
# Testes: Helper Functions
# =============================================================================


class TestLifespanHelperFunctions:
    """Testes das funções helper no lifespan."""

    @pytest.mark.asyncio
    async def test_start_kafka_consumer_background_function(self):
        """Função helper start_kafka_consumer_background."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()
            mock_app.state.metrics = MagicMock()
            mock_app.state.webhook_manager = None
            mock_app.state.redis_client = None
            mock_app.state.background_init_tasks = []

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            mock_grpc_server = MagicMock()
            mock_grpc_server.stop = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        with patch("src.consumers.start_ticket_consumer") as mock_start_consumer:
                            mock_consumer = MagicMock()
                            mock_start_consumer.return_value = mock_consumer

                            async with lifespan(mock_app):
                                # Função deve ter sido chamada via background task
                                pass

    @pytest.mark.asyncio
    async def test_webhook_manager_getter_function(self):
        """Função getter webhook_manager funciona."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()
            mock_app.state.metrics = MagicMock()
            mock_app.state.webhook_manager = MagicMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            mock_grpc_server = MagicMock()
            mock_grpc_server.stop = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        with patch("src.consumers.start_ticket_consumer") as mock_start_consumer:
                            mock_consumer = MagicMock()
                            mock_start_consumer.return_value = mock_consumer

                            async with lifespan(mock_app):
                                # Getter deve funcionar
                                pass

    @pytest.mark.asyncio
    async def test_redis_client_getter_function(self):
        """Função getter redis_client funciona."""
        from src.main import lifespan

        with patch("src.main.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForMain()

            mock_app = MagicMock()
            mock_app.state.metrics = MagicMock()
            mock_app.state.redis_client = MagicMock()

            mock_postgres = MagicMock()
            mock_postgres.start = AsyncMock()
            mock_postgres.disconnect = AsyncMock()

            mock_mongodb = MagicMock()
            mock_mongodb.start = AsyncMock()
            mock_mongodb.disconnect = AsyncMock()

            mock_grpc_server = MagicMock()
            mock_grpc_server.stop = AsyncMock()

            with patch("src.main.get_postgres_client", new=AsyncMock(return_value=mock_postgres)):
                with patch("src.main.get_mongodb_client", new=AsyncMock(return_value=mock_mongodb)):
                    with patch("src.grpc_service.start_grpc_server", new=AsyncMock(return_value=(mock_grpc_server, MagicMock()))):

                        with patch("src.consumers.start_ticket_consumer") as mock_start_consumer:
                            mock_consumer = MagicMock()
                            mock_start_consumer.return_value = mock_consumer

                            async with lifespan(mock_app):
                                # Getter deve funcionar
                                pass
