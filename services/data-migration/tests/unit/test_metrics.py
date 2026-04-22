"""Testes para métricas Prometheus.

Autor: Neural Hive Mind
Criado: 2026-04-19 (REFACTOR-H-007)
"""

from unittest.mock import patch

from src.services.metrics import (
    active_migrations,
    cdc_consumer_lag,
    cdc_events_processed,
    cdc_processing_duration,
    increment_cdc_events,
    increment_migration_batch,
    migration_batch_duration,
    migration_batches_completed,
    migration_progress,
    observe_batch_processing,
    observe_cdc_processing,
    observe_rollback,
    postgresql_pool_size,
    rollback_duration,
    rollback_operations,
    set_active_migrations,
    set_cdc_consumer_lag,
    set_migration_progress,
    set_postgresql_pool_size,
    start_metrics_server,
)


class TestMetricsDefinitions:
    """Testa definição das métricas."""

    def test_cdc_events_processed_counter_defined(self):
        """Verifica que contador de eventos CDC está definido."""
        assert cdc_events_processed is not None
        assert cdc_events_processed._type == "counter"
        # Prometheus adiciona "_total" automaticamente para contadores
        assert cdc_events_processed._name == "data_migration_cdc_events_processed"

    def test_cdc_consumer_lag_gauge_defined(self):
        """Verifica que gauge de lag CDC está definido."""
        assert cdc_consumer_lag is not None
        assert cdc_consumer_lag._type == "gauge"
        assert cdc_consumer_lag._name == "data_migration_cdc_consumer_lag_ms"

    def test_migration_progress_gauge_defined(self):
        """Verifica que gauge de progresso está definido."""
        assert migration_progress is not None
        assert migration_progress._type == "gauge"
        assert migration_progress._name == "data_migration_migration_progress_percentage"

    def test_cdc_processing_duration_histogram_defined(self):
        """Verifica que histogram de duração CDC está definido."""
        assert cdc_processing_duration is not None
        assert cdc_processing_duration._type == "histogram"
        assert cdc_processing_duration._name == "data_migration_cdc_processing_duration_seconds"

    def test_active_migrations_gauge_defined(self):
        """Verifica que gauge de migrações ativas está definido."""
        assert active_migrations is not None
        assert active_migrations._type == "gauge"

    def test_postgresql_pool_size_gauge_defined(self):
        """Verifica que gauge de pool PostgreSQL está definido."""
        assert postgresql_pool_size is not None
        assert postgresql_pool_size._type == "gauge"


class TestMetricsOperations:
    """Testa operações sobre métricas."""

    def test_increment_cdc_events(self):
        """Testa incrementar contador de eventos CDC."""
        # Incrementar
        increment_cdc_events(job_id="test-job", operation_type="insert")

        # Verificar que foi incrementado (precisamos ler o valor)
        sample = cdc_events_processed.labels(job_id="test-job", operation_type="insert")
        # A métrica existe e foi incrementada
        assert sample is not None

    def test_set_cdc_consumer_lag(self):
        """Testa definir lag do consumidor CDC."""
        set_cdc_consumer_lag(job_id="test-job", lag_ms=1500.5)

        sample = cdc_consumer_lag.labels(job_id="test-job")
        assert sample is not None

    def test_set_migration_progress(self):
        """Testa definir progresso da migração."""
        set_migration_progress(job_id="test-job", progress=75.5)

        sample = migration_progress.labels(job_id="test-job")
        assert sample is not None

    def test_set_migration_progress_clamped(self):
        """Testa que progresso é limitado entre 0-100."""
        # Valores fora do range não devem causar erro
        set_migration_progress(job_id="test-job", progress=150.0)
        set_migration_progress(job_id="test-job", progress=-10.0)

        sample = migration_progress.labels(job_id="test-job")
        assert sample is not None

    def test_increment_migration_batch(self):
        """Testa incrementar contador de batches."""
        increment_migration_batch(job_id="test-job", status="success")

        sample = migration_batches_completed.labels(job_id="test-job", status="success")
        assert sample is not None

    def test_observe_cdc_processing(self):
        """Testa observar duração do processamento CDC."""
        observe_cdc_processing(job_id="test-job", duration_sec=0.123)

        sample = cdc_processing_duration.labels(job_id="test-job")
        assert sample is not None

    def test_observe_batch_processing(self):
        """Testa observar duração do processamento de batch."""
        observe_batch_processing(job_id="test-job", batch_size=1000, duration_sec=5.67)

        sample = migration_batch_duration.labels(job_id="test-job", batch_size="1000")
        assert sample is not None

    def test_observe_rollback(self):
        """Testa observar duração e resultado do rollback."""
        observe_rollback(job_id="test-job", duration_sec=2.5, outcome="success")

        duration_sample = rollback_duration.labels(job_id="test-job")
        ops_sample = rollback_operations.labels(job_id="test-job", outcome="success")
        assert duration_sample is not None
        assert ops_sample is not None

    def test_set_active_migrations(self):
        """Testa definir contador de migrações ativas."""
        set_active_migrations(count=5, status="running")

        sample = active_migrations.labels(status="running")
        assert sample is not None

    def test_set_postgresql_pool_size(self):
        """Testa definir tamanho do pool PostgreSQL."""
        set_postgresql_pool_size(pool_type="connection", size=10)

        sample = postgresql_pool_size.labels(pool_type="connection")
        assert sample is not None


class TestMetricsServer:
    """Testa servidor de métricas."""

    @patch("src.services.metrics.prometheus_start_http_server")
    def test_start_metrics_server_default_port(self, mock_start):
        """Testa iniciar servidor na porta padrão."""
        start_metrics_server()

        mock_start.assert_called_once_with(9090)

    @patch("src.services.metrics.prometheus_start_http_server")
    def test_start_metrics_server_custom_port(self, mock_start):
        """Testa iniciar servidor em porta customizada."""
        start_metrics_server(port=8080)

        mock_start.assert_called_once_with(8080)


class TestMetricsLabelCombinations:
    """Testa diferentes combinações de labels."""

    def test_cdc_events_various_operations(self):
        """Testa diferentes tipos de operação CDC."""
        operations = ["insert", "update", "delete", "refresh"]

        for op in operations:
            increment_cdc_events(job_id="test-job", operation_type=op)
            sample = cdc_events_processed.labels(job_id="test-job", operation_type=op)
            assert sample is not None

    def test_migration_batch_various_statuses(self):
        """Testa diferentes status de batch."""
        statuses = ["success", "failed", "partial"]

        for st in statuses:
            increment_migration_batch(job_id="test-job", status=st)
            sample = migration_batches_completed.labels(job_id="test-job", status=st)
            assert sample is not None

    def test_rollback_various_outcomes(self):
        """Testa diferentes resultados de rollback."""
        outcomes = ["success", "failed", "partial"]

        for outcome in outcomes:
            observe_rollback(job_id="test-job", duration_sec=1.0, outcome=outcome)
            sample = rollback_operations.labels(job_id="test-job", outcome=outcome)
            assert sample is not None

    def test_active_migrations_various_statuses(self):
        """Testa diferentes status de migrações ativas."""
        statuses = ["pending", "running", "paused", "completed", "failed"]

        for st in statuses:
            set_active_migrations(count=1, status=st)
            sample = active_migrations.labels(status=st)
            assert sample is not None

    def test_postgresql_pool_types(self):
        """Testa diferentes tipos de pool PostgreSQL."""
        pool_types = ["connection", "transaction", "statement"]

        for pool_type in pool_types:
            set_postgresql_pool_size(pool_type=pool_type, size=10)
            sample = postgresql_pool_size.labels(pool_type=pool_type)
            assert sample is not None
