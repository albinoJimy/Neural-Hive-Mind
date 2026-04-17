"""
Testes unitários para CDC Pipeline Service.

Cobre criação de connector Debezium, consumo de eventos CDC,
processamento de changes e gestão de status do connector.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.models.migration import (
    FieldMapping,
    SchemaMapping,
    TableMapping,
)
from src.services.cdc_pipeline import (
    CDCConnectorError,
    CDCPipeline,
    CDCPipelineError,
    CDCStatus,
    CDCTransformError,
    get_cdc_pipeline,
)


class TestCDCPipelineInitialization:
    """Testes para inicialização do CDC Pipeline."""

    def test_cdc_pipeline_initialization_default(self):
        """Verifica inicialização com valores padrão."""
        with patch("src.services.cdc_pipeline.get_settings") as mock_settings:
            mock_settings.return_value.kafka_bootstrap_servers = "localhost:9092"
            mock_settings.return_value.debezium_url = "http://localhost:8083"
            mock_settings.return_value.kafka_consumer_group = "test-group"

            pipeline = CDCPipeline(job_id="test-job")

            assert pipeline.job_id == "test-job"
            assert pipeline.kafka_bootstrap_servers == "localhost:9092"
            assert pipeline.debezium_url == "http://localhost:8083"
            assert pipeline.consumer_group == "test-group"
            assert pipeline._consumer is None
            assert pipeline._running is False

    def test_cdc_pipeline_initialization_custom(self):
        """Verifica inicialização com valores customizados."""
        pipeline = CDCPipeline(
            job_id="custom-job",
            kafka_bootstrap_servers="kafka:9092",
            debezium_url="http://debezium:8083",
            consumer_group="custom-group",
        )

        assert pipeline.job_id == "custom-job"
        assert pipeline.kafka_bootstrap_servers == "kafka:9092"
        assert pipeline.debezium_url == "http://debezium:8083"
        assert pipeline.consumer_group == "custom-group"


class TestCreateConnector:
    """Testes para criação de connector Debezium."""

    @pytest.mark.asyncio
    async def test_create_connector_success(self):
        """Verifica criação bem-sucedida de connector."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[
                        FieldMapping(
                            source_field="id",
                            target_field="id",
                            data_type="uuid",
                            is_primary_key=True,
                        ),
                        FieldMapping(
                            source_field="name",
                            target_field="name",
                            data_type="text",
                        ),
                    ],
                )
            ],
        )

        pipeline = CDCPipeline(job_id="test-job")

        # Mock do httpx
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "name": "postgres-connector-test-job",
            "config": {"connector.class": "io.debezium.connector.postgresql.PostgresConnector"},
        }

        with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
            connector_id = await pipeline.create_connector(
                schema_mapping=schema_mapping,
                database_hostname="localhost",
                database_port=5432,
                database_user="user",
                database_password="pass",
                database_dbname="legacy",
            )

            assert connector_id == "postgres-connector-test-job"
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "connectors" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_create_connector_with_transformations(self):
        """Verifica criação de connector com transformações SMT."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[
                        FieldMapping(
                            source_field="created_at",
                            target_field="created_at",
                            data_type="timestamptz",
                            transform="CAST_TIMESTAMP_UTC",
                        ),
                    ],
                )
            ],
        )

        pipeline = CDCPipeline(job_id="test-job")

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"name": "postgres-connector-test-job"}

        with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
            connector_id = await pipeline.create_connector(
                schema_mapping=schema_mapping,
                database_hostname="localhost",
                database_port=5432,
                database_user="user",
                database_password="pass",
                database_dbname="legacy",
            )

            assert connector_id == "postgres-connector-test-job"
            # Verificar que SMTs foram incluídas
            config = mock_post.call_args[1]["json"]["config"]
            assert "transforms" in config
            assert "transforms" in config

    @pytest.mark.asyncio
    async def test_create_connector_http_error(self):
        """Verifica tratamento de erro HTTP na criação."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[],
        )

        pipeline = CDCPipeline(job_id="test-job")

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            with pytest.raises(CDCConnectorError, match="Falha ao criar connector"):
                await pipeline.create_connector(
                    schema_mapping=schema_mapping,
                    database_hostname="localhost",
                    database_port=5432,
                    database_user="user",
                    database_password="pass",
                    database_dbname="legacy",
                )

    @pytest.mark.asyncio
    async def test_create_connector_with_filters(self):
        """Verifica criação de connector com filtros de tabela."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[],
                    source_filter="deleted_at IS NULL",
                )
            ],
        )

        pipeline = CDCPipeline(job_id="test-job")

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"name": "postgres-connector-test-job"}

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            connector_id = await pipeline.create_connector(
                schema_mapping=schema_mapping,
                database_hostname="localhost",
                database_port=5432,
                database_user="user",
                database_password="pass",
                database_dbname="legacy",
            )

            assert connector_id == "postgres-connector-test-job"


class TestStartCDC:
    """Testes para inicio de consumo CDC."""

    @pytest.mark.asyncio
    async def test_start_cdc_success(self):
        """Verifica inicio bem-sucedido de consumo CDC."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[],
                )
            ],
        )

        pipeline = CDCPipeline(job_id="test-job")

        # Mock do consumidor Kafka
        mock_consumer = AsyncMock()
        mock_consumer.start = AsyncMock()
        mock_consumer.stop = AsyncMock()

        with patch("aiokafka.AIOKafkaConsumer", return_value=mock_consumer):
            await pipeline.start_cdc(schema_mapping=schema_mapping)

            assert pipeline._running is True
            assert pipeline._consumer is not None
            mock_consumer.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_cdc_multiple_tables(self):
        """Verifica subscrição a múltiplos tópicos."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[],
                ),
                TableMapping(
                    source_schema="public",
                    source_table="orders",
                    target_table="nhm_orders",
                    fields=[],
                ),
            ],
        )

        pipeline = CDCPipeline(job_id="test-job", topic_prefix="pg-legacy")

        mock_consumer = AsyncMock()
        mock_consumer.start = AsyncMock()

        with patch("aiokafka.AIOKafkaConsumer", return_value=mock_consumer) as mock_kafka:
            await pipeline.start_cdc(schema_mapping=schema_mapping)

            # Verificar que AIOKafkaConsumer foi chamado
            mock_kafka.assert_called_once()
            # Os tópicos são passados como argumentos posicionais
            args = mock_kafka.call_args[0]
            assert "pg-legacy.public.users" in args
            assert "pg-legacy.public.orders" in args

    @pytest.mark.asyncio
    async def test_start_cdc_already_running(self):
        """Verifica erro ao tentar iniciar CDC já rodando."""
        pipeline = CDCPipeline(job_id="test-job")
        pipeline._running = True

        with pytest.raises(CDCPipelineError, match="CDC já está rodando"):
            await pipeline.start_cdc(schema_mapping=SchemaMapping(
                legacy_connection_id="test",
                nhm_target="test",
                tables=[],
            ))

    @pytest.mark.asyncio
    async def test_process_cdc_event_insert(self):
        """Verifica processamento de evento INSERT."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[
                        FieldMapping(
                            source_field="id",
                            target_field="id",
                            data_type="integer",
                            is_primary_key=True,
                        ),
                        FieldMapping(
                            source_field="name",
                            target_field="name",
                            data_type="text",
                        ),
                    ],
                )
            ],
        )

        pipeline = CDCPipeline(job_id="test-job")

        # Evento Debezium INSERT
        cdc_event = {
            "before": None,
            "after": {"id": 1, "name": "John Doe"},
            "op": "c",
            "ts_ms": 1234567890,
            "source": {
                "schema": "public",
                "table": "users",
            },
        }

        mock_target_client = AsyncMock()
        mock_target_client.insert = AsyncMock()

        with patch.object(pipeline, "_apply_transformations", return_value={"id": 1, "name": "John Doe"}):
            await pipeline._process_cdc_event(
                event=cdc_event,
                schema_mapping=schema_mapping,
                target_client=mock_target_client,
            )

            mock_target_client.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_cdc_event_update(self):
        """Verifica processamento de evento UPDATE."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[
                        FieldMapping(source_field="id", target_field="id", data_type="integer"),
                        FieldMapping(source_field="name", target_field="name", data_type="text"),
                    ],
                )
            ],
        )

        pipeline = CDCPipeline(job_id="test-job")

        cdc_event = {
            "before": {"id": 1, "name": "Old Name"},
            "after": {"id": 1, "name": "New Name"},
            "op": "u",
            "ts_ms": 1234567890,
            "source": {"schema": "public", "table": "users"},
        }

        mock_target_client = AsyncMock()
        mock_target_client.update = AsyncMock()

        with patch.object(pipeline, "_apply_transformations", return_value={"id": 1, "name": "New Name"}):
            await pipeline._process_cdc_event(
                event=cdc_event,
                schema_mapping=schema_mapping,
                target_client=mock_target_client,
            )

            mock_target_client.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_cdc_event_delete(self):
        """Verifica processamento de evento DELETE."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[
                        FieldMapping(source_field="id", target_field="id", data_type="integer"),
                    ],
                )
            ],
        )

        pipeline = CDCPipeline(job_id="test-job")

        cdc_event = {
            "before": {"id": 1},
            "after": None,
            "op": "d",
            "ts_ms": 1234567890,
            "source": {"schema": "public", "table": "users"},
        }

        mock_target_client = AsyncMock()
        mock_target_client.delete = AsyncMock()

        with patch.object(pipeline, "_apply_transformations", return_value={"id": 1}):
            await pipeline._process_cdc_event(
                event=cdc_event,
                schema_mapping=schema_mapping,
                target_client=mock_target_client,
            )

            mock_target_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_cdc_event_read_snapshot(self):
        """Verifica processamento de evento READ (snapshot inicial)."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[],
                )
            ],
        )

        pipeline = CDCPipeline(job_id="test-job")

        cdc_event = {
            "before": None,
            "after": {"id": 1, "name": "Snapshot User"},
            "op": "r",
            "ts_ms": 1234567890,
            "source": {"schema": "public", "table": "users"},
        }

        mock_target_client = AsyncMock()
        mock_target_client.insert = AsyncMock()

        with patch.object(pipeline, "_apply_transformations", return_value={"id": 1, "name": "Snapshot User"}):
            await pipeline._process_cdc_event(
                event=cdc_event,
                schema_mapping=schema_mapping,
                target_client=mock_target_client,
            )

            mock_target_client.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_cdc_event_unknown_operation(self):
        """Verifica tratamento de operação desconhecida."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[
                        FieldMapping(source_field="id", target_field="id", data_type="integer"),
                    ],
                )
            ],
        )

        pipeline = CDCPipeline(job_id="test-job")

        cdc_event = {
            "before": None,
            "after": {"id": 1},
            "op": "x",  # Operação inválida
            "ts_ms": 1234567890,
            "source": {"schema": "public", "table": "users"},
        }

        mock_target_client = AsyncMock()

        with pytest.raises(CDCTransformError, match="Falha ao processar evento"):
            await pipeline._process_cdc_event(
                event=cdc_event,
                schema_mapping=schema_mapping,
                target_client=mock_target_client,
            )


class TestApplyTransformations:
    """Testes para aplicação de transformações."""

    @pytest.mark.asyncio
    async def test_apply_transformations_no_transform(self):
        """Verifica pass-through sem transformações."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[
                        FieldMapping(source_field="id", target_field="id", data_type="integer"),
                        FieldMapping(source_field="name", target_field="name", data_type="text"),
                    ],
                )
            ],
        )

        pipeline = CDCPipeline(job_id="test-job")

        source_data = {"id": 1, "name": "John"}

        result = await pipeline._apply_transformations(
            source_data=source_data,
            table_mapping=schema_mapping.tables[0],
        )

        assert result["id"] == 1
        assert result["name"] == "John"

    @pytest.mark.asyncio
    async def test_apply_transformations_field_renaming(self):
        """Verifica renomeação de campos."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[
                        FieldMapping(source_field="user_id", target_field="id", data_type="integer"),
                        FieldMapping(source_field="user_name", target_field="name", data_type="text"),
                    ],
                )
            ],
        )

        pipeline = CDCPipeline(job_id="test-job")

        source_data = {"user_id": 1, "user_name": "John"}

        result = await pipeline._apply_transformations(
            source_data=source_data,
            table_mapping=schema_mapping.tables[0],
        )

        assert result["id"] == 1
        assert result["name"] == "John"
        assert "user_id" not in result
        assert "user_name" not in result

    @pytest.mark.asyncio
    async def test_apply_transformations_cast_timestamp(self):
        """Verifica transformação CAST_TIMESTAMP_UTC."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[
                        FieldMapping(
                            source_field="created_at",
                            target_field="created_at",
                            data_type="timestamptz",
                            transform="CAST_TIMESTAMP_UTC",
                        ),
                    ],
                )
            ],
        )

        pipeline = CDCPipeline(job_id="test-job")

        source_data = {"created_at": "2024-01-01 12:00:00"}

        result = await pipeline._apply_transformations(
            source_data=source_data,
            table_mapping=schema_mapping.tables[0],
        )

        assert "created_at" in result
        # Verificar que foi convertido para timestamp com timezone
        assert isinstance(result["created_at"], datetime) or "UTC" in str(result["created_at"])

    @pytest.mark.asyncio
    async def test_apply_transformations_with_default_value(self):
        """Verifica aplicação de valor default quando campo é None."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[
                        FieldMapping(
                            source_field="status",
                            target_field="status",
                            data_type="text",
                            default_value="active",
                        ),
                    ],
                )
            ],
        )

        pipeline = CDCPipeline(job_id="test-job")

        # Campo existe mas é None ou vazio
        source_data = {"status": None}

        result = await pipeline._apply_transformations(
            source_data=source_data,
            table_mapping=schema_mapping.tables[0],
        )

        # Default value aplicado quando campo é None
        assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_apply_transformations_no_default_when_field_exists(self):
        """Verifica que default não é aplicado quando campo existe."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[
                        FieldMapping(
                            source_field="status",
                            target_field="status",
                            data_type="text",
                            default_value="active",
                        ),
                    ],
                )
            ],
        )

        pipeline = CDCPipeline(job_id="test-job")

        source_data = {"status": "inactive"}  # Campo presente

        result = await pipeline._apply_transformations(
            source_data=source_data,
            table_mapping=schema_mapping.tables[0],
        )

        # Default não sobrescreve valor existente
        assert result["status"] == "inactive"


class TestStopCDC:
    """Testes para parada de CDC."""

    @pytest.mark.asyncio
    async def test_stop_cdc_success(self):
        """Verifica parada bem-sucedida de CDC."""
        pipeline = CDCPipeline(job_id="test-job")
        pipeline._running = True

        mock_consumer = AsyncMock()
        pipeline._consumer = mock_consumer

        await pipeline.stop_cdc()

        assert pipeline._running is False
        mock_consumer.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_cdc_not_running(self):
        """Verifica que stop é idempotente quando não está rodando."""
        pipeline = CDCPipeline(job_id="test-job")
        pipeline._running = False
        pipeline._consumer = None

        # Não deve levantar erro
        await pipeline.stop_cdc()

        assert pipeline._running is False


class TestGetCDCStatus:
    """Testes para obtenção de status do connector."""

    @pytest.mark.asyncio
    async def test_get_cdc_status_running(self):
        """Verifica obtenção de status quando connector está rodando."""
        pipeline = CDCPipeline(job_id="test-job")
        pipeline._connector_id = "postgres-connector-test-job"
        pipeline._running = True

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "postgres-connector-test-job",
            "connector": {
                "state": "RUNNING",
                "worker_id": "worker1",
            },
            "tasks": [
                {
                    "id": 0,
                    "state": "RUNNING",
                    "ts_lag": 100,
                }
            ],
        }

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            status = await pipeline.get_cdc_status()

            assert status.connector_id == "postgres-connector-test-job"
            assert status.connector_state == "RUNNING"
            assert status.running is True
            assert status.task_states == ["RUNNING"]
            assert status.lag_ms == 100

    @pytest.mark.asyncio
    async def test_get_cdc_status_paused(self):
        """Verifica status quando connector está pausado."""
        pipeline = CDCPipeline(job_id="test-job")
        pipeline._connector_id = "postgres-connector-test-job"
        pipeline._running = False

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "postgres-connector-test-job",
            "connector": {
                "state": "PAUSED",
                "worker_id": "worker1",
            },
            "tasks": [
                {
                    "id": 0,
                    "state": "PAUSED",
                    "ts_lag": 0,
                }
            ],
        }

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            status = await pipeline.get_cdc_status()

            assert status.connector_state == "PAUSED"
            assert status.running is False

    @pytest.mark.asyncio
    async def test_get_cdc_status_connector_not_found(self):
        """Verifica comportamento quando connector não existe."""
        pipeline = CDCPipeline(job_id="test-job")
        pipeline._connector_id = "non-existent-connector"

        mock_response = Mock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            status = await pipeline.get_cdc_status()

            assert status.connector_id == "non-existent-connector"
            assert status.running is False
            assert status.error is not None

    @pytest.mark.asyncio
    async def test_get_cdc_status_no_connector_id(self):
        """Verifica status quando connector não foi criado."""
        pipeline = CDCPipeline(job_id="test-job")
        pipeline._connector_id = None

        status = await pipeline.get_cdc_status()

        assert status.running is False
        assert "Connector não configurado" in status.error or status.error is None


class TestDeleteConnector:
    """Testes para deleção de connector."""

    @pytest.mark.asyncio
    async def test_delete_connector_success(self):
        """Verifica deleção bem-sucedida de connector."""
        pipeline = CDCPipeline(job_id="test-job")
        pipeline._connector_id = "postgres-connector-test-job"

        mock_response = Mock()
        mock_response.status_code = 204

        with patch("httpx.AsyncClient.delete", return_value=mock_response):
            await pipeline.delete_connector()

            assert pipeline._connector_id is None

    @pytest.mark.asyncio
    async def test_delete_connector_not_found(self):
        """Verifica deleção de connector inexistente não levanta erro."""
        pipeline = CDCPipeline(job_id="test-job")
        pipeline._connector_id = "non-existent-connector"

        mock_response = Mock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient.delete", return_value=mock_response):
            # Não deve levantar erro (idempotente)
            await pipeline.delete_connector()

            assert pipeline._connector_id is None

    @pytest.mark.asyncio
    async def test_delete_connector_no_id(self):
        """Verifica deleção quando não há connector configurado."""
        pipeline = CDCPipeline(job_id="test-job")
        pipeline._connector_id = None

        # Não deve levantar erro
        await pipeline.delete_connector()


class TestPauseResumeConnector:
    """Testes para pausa e retomada de connector."""

    @pytest.mark.asyncio
    async def test_pause_connector_success(self):
        """Verifica pausa bem-sucedida de connector."""
        pipeline = CDCPipeline(job_id="test-job")
        pipeline._connector_id = "postgres-connector-test-job"

        mock_response = Mock()
        mock_response.status_code = 204

        with patch("httpx.AsyncClient.put", return_value=mock_response):
            await pipeline.pause_connector()

    @pytest.mark.asyncio
    async def test_pause_connector_no_id(self):
        """Verifica erro ao pausar sem connector configurado."""
        pipeline = CDCPipeline(job_id="test-job")
        pipeline._connector_id = None

        with pytest.raises(CDCConnectorError, match="Connector não configurado"):
            await pipeline.pause_connector()

    @pytest.mark.asyncio
    async def test_resume_connector_success(self):
        """Verifica retomada bem-sucedida de connector."""
        pipeline = CDCPipeline(job_id="test-job")
        pipeline._connector_id = "postgres-connector-test-job"

        mock_response = Mock()
        mock_response.status_code = 204

        with patch("httpx.AsyncClient.put", return_value=mock_response):
            await pipeline.resume_connector()


class TestGetCDCPipeline:
    """Testes para singleton get_cdc_pipeline."""

    def test_get_cdc_pipeline_singleton(self):
        """Verifica que get_cdc_pipeline retorna singleton."""
        # Reset singleton primeiro
        from src.services import cdc_pipeline

        cdc_pipeline._cdc_pipeline = None

        pipeline1 = get_cdc_pipeline(job_id="test-job")
        pipeline2 = get_cdc_pipeline()

        assert pipeline1 is pipeline2

    def test_get_cdc_pipeline_requires_job_id(self):
        """Verifica que job_id é obrigatório na primeira chamada."""
        # Reset singleton
        from src.services import cdc_pipeline

        cdc_pipeline._cdc_pipeline = None

        with pytest.raises(ValueError, match="job_id é obrigatório"):
            get_cdc_pipeline()

    def test_get_cdc_pipeline_reset(self):
        """Verifica reset do singleton para testes."""
        # Reset singleton
        from src.services import cdc_pipeline

        cdc_pipeline._cdc_pipeline = None

        pipeline1 = get_cdc_pipeline(job_id="test-job1")

        # Reset para teste
        cdc_pipeline._cdc_pipeline = None

        pipeline2 = get_cdc_pipeline(job_id="test-job2")

        # São objetos diferentes após reset
        assert pipeline1 is not pipeline2


class TestCDCStatus:
    """Testes para modelo CDCStatus."""

    def test_cdc_status_creation(self):
        """Verifica criação de CDCStatus."""
        status = CDCStatus(
            connector_id="test-connector",
            connector_state="RUNNING",
            running=True,
            task_states=["RUNNING", "RUNNING"],
            lag_ms=100,
        )

        assert status.connector_id == "test-connector"
        assert status.connector_state == "RUNNING"
        assert status.running is True
        assert len(status.task_states) == 2
        assert status.lag_ms == 100
        assert status.error is None

    def test_cdc_status_with_error(self):
        """Verifica CDCStatus com erro."""
        status = CDCStatus(
            connector_id="test-connector",
            connector_state="FAILED",
            running=False,
            task_states=[],
            lag_ms=0,
            error="Connection failed",
        )

        assert status.running is False
        assert status.error == "Connection failed"


class TestBuildDebeziumConfig:
    """Testes para construção de config Debezium."""

    def test_build_debezium_config_basic(self):
        """Verifica configuração básica do Debezium."""
        import asyncio

        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[],
                )
            ],
        )

        pipeline = CDCPipeline(job_id="test-job", topic_prefix="pg-legacy")

        async def test():
            config = await pipeline._build_debezium_config(
                schema_mapping=schema_mapping,
                database_hostname="localhost",
                database_port=5432,
                database_user="user",
                database_password="pass",
                database_dbname="legacy",
            )

            assert config["connector.class"] == "io.debezium.connector.postgresql.PostgresConnector"
            assert config["database.hostname"] == "localhost"
            assert config["database.port"] == "5432"
            assert config["database.user"] == "user"
            assert config["database.password"] == "pass"
            assert config["database.dbname"] == "legacy"
            assert config["topic.prefix"] == "pg-legacy"
            assert "plugin.name" in config
            assert "table.include.list" in config

        asyncio.run(test())

    def test_build_debezium_config_with_multiple_tables(self):
        """Verifica configuração com múltiplas tabelas."""
        import asyncio

        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[],
                ),
                TableMapping(
                    source_schema="public",
                    source_table="orders",
                    target_table="nhm_orders",
                    fields=[],
                ),
            ],
        )

        pipeline = CDCPipeline(job_id="test-job")

        async def test():
            config = await pipeline._build_debezium_config(
                schema_mapping=schema_mapping,
                database_hostname="localhost",
                database_port=5432,
                database_user="user",
                database_password="pass",
                database_dbname="legacy",
            )

            table_list = config["table.include.list"]
            assert "public.users" in table_list
            assert "public.orders" in table_list

        asyncio.run(test())

    def test_build_debezium_config_with_snapshots_mode(self):
        """Verifica configuração com modo de snapshot customizado."""
        import asyncio

        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[],
            metadata={"snapshot_mode": "schema_only"},
        )

        pipeline = CDCPipeline(job_id="test-job")

        async def test():
            config = await pipeline._build_debezium_config(
                schema_mapping=schema_mapping,
                database_hostname="localhost",
                database_port=5432,
                database_user="user",
                database_password="pass",
                database_dbname="legacy",
            )

            assert config["snapshot.mode"] == "schema_only"

        asyncio.run(test())
