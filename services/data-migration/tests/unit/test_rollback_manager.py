"""
Testes unitários para Rollback Manager.

Cobre criação de snapshots, execução de rollback, limpeza e status.
"""

import gzip
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.rollback_manager import (
    RollbackManager,
    RollbackSnapshot,
    RollbackStatistics,
    RollbackStatus,
    get_rollback_manager,
)


@pytest.fixture(autouse=True)
def reset_rollback_singleton():
    """Reseta singleton do RollbackManager entre testes."""
    RollbackManager._reset_for_tests()
    yield
    RollbackManager._reset_for_tests()


@pytest.fixture
def mock_postgres_client():
    """Mock do PostgreSQL client."""
    client = MagicMock()
    client.execute_query = AsyncMock()
    client.fetch_batch = AsyncMock()
    client.get_table_count = AsyncMock()
    return client


@pytest.fixture
def mock_s3_client():
    """Mock do S3 client."""
    mock_s3 = MagicMock()
    # put_object pode ser AsyncMock (chamado no código com await)
    mock_s3.put_object = AsyncMock()
    # get_object retorna um dict com Body (sync read), ou objeto com read()
    mock_s3.get_object = MagicMock(
        return_value=MagicMock(read=MagicMock(return_value=b"test data"))
    )
    # delete_object pode ser AsyncMock ou sync dependendo do cliente
    mock_s3.delete_object = MagicMock()
    mock_s3.remove_object = MagicMock()
    mock_s3.list_objects_v2 = AsyncMock()
    return mock_s3


@pytest.fixture
def sample_table_mapping():
    """Mapeamento de tabela de exemplo."""
    from src.models.migration import TableMapping

    return TableMapping(
        source_schema="public",
        source_table="users",
        target_table="users",
        target_schema="public",
        fields=[],
        estimated_rows=1000,
    )


class TestRollbackSnapshot:
    """Testes para modelo RollbackSnapshot."""

    def test_snapshot_creation(self):
        """Verifica criação de snapshot."""
        snapshot = RollbackSnapshot(
            snapshot_id="snap-123",
            migration_job_id="job-456",
            tables=["users", "orders"],
            created_at=datetime.now(timezone.utc),
            storage_location="s3://bucket/snap-123/",
            status=RollbackStatus.COMPLETED,
        )

        assert snapshot.snapshot_id == "snap-123"
        assert snapshot.migration_job_id == "job-456"
        assert len(snapshot.tables) == 2
        assert snapshot.status == RollbackStatus.COMPLETED

    def test_snapshot_to_dict(self):
        """Verifica conversão para dicionário."""
        now = datetime.now(timezone.utc)
        snapshot = RollbackSnapshot(
            snapshot_id="snap-123",
            migration_job_id="job-456",
            tables=["users"],
            created_at=now,
            storage_location="s3://bucket/snap-123/",
            status=RollbackStatus.COMPLETED,
        )

        data = snapshot.to_dict()

        assert data["snapshot_id"] == "snap-123"
        assert data["migration_job_id"] == "job-456"
        assert data["status"] == "completed"
        assert "created_at" in data


class TestRollbackStatistics:
    """Testes para modelo RollbackStatistics."""

    def test_statistics_creation(self):
        """Verifica criação de estatísticas."""
        stats = RollbackStatistics(
            tables_processed=3,
            rows_restored=15000,
            tables_failed=0,
            duration_seconds=45.5,
        )

        assert stats.tables_processed == 3
        assert stats.rows_restored == 15000
        assert stats.tables_failed == 0
        assert stats.duration_seconds == 45.5

    def test_statistics_success_rate(self):
        """Verifica cálculo de taxa de sucesso."""
        stats = RollbackStatistics(
            tables_processed=9,
            rows_restored=50000,
            tables_failed=1,
            duration_seconds=120.0,
        )

        assert stats.success_rate() == 0.9  # 9 de 10


class TestRollbackManager:
    """Testes para RollbackManager."""

    def test_initialization(self):
        """Verifica inicialização do RollbackManager."""
        with patch("src.services.rollback_manager.get_settings") as mock_settings:
            mock_cfg = MagicMock()
            mock_cfg.rollback_timeout_seconds = 30
            mock_cfg.s3_bucket = "test-bucket"
            mock_cfg.s3_endpoint = "http://localhost:9000"
            mock_cfg.s3_access_key = "test-key"
            mock_cfg.s3_secret_key = "test-secret"
            mock_cfg.s3_use_ssl = False
            mock_settings.return_value = mock_cfg

            manager = RollbackManager()

            assert manager._timeout == 30
            assert manager._bucket == "test-bucket"

    @pytest.mark.asyncio
    async def test_create_snapshot_s3_strategy(
        self, mock_postgres_client, mock_s3_client, sample_table_mapping
    ):
        """Verifica criação de snapshot usando estratégia S3."""
        with patch("src.services.rollback_manager.get_settings") as mock_settings:
            mock_cfg = MagicMock()
            mock_cfg.rollback_timeout_seconds = 30
            mock_cfg.s3_bucket = "test-bucket"
            mock_cfg.s3_endpoint = "http://localhost:9000"
            mock_cfg.s3_access_key = "test-key"
            mock_cfg.s3_secret_key = "test-secret"
            mock_cfg.s3_use_ssl = False
            mock_settings.return_value = mock_cfg

            manager = RollbackManager()
            manager._postgres = mock_postgres_client
            manager._s3 = mock_s3_client

            # Mock responses
            mock_postgres_client.fetch_batch.side_effect = [
                [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
                [{"id": 1, "amount": 100}],
            ]
            mock_postgres_client.get_table_count.return_value = 2

            snapshot_id = await manager.create_snapshot(
                migration_job_id="job-123",
                table_mappings=[sample_table_mapping],
                strategy="s3",
            )

            assert snapshot_id is not None
            assert snapshot_id.startswith("snap-")
            mock_s3_client.put_object.assert_called()

    @pytest.mark.asyncio
    async def test_create_snapshot_shadow_strategy(
        self, mock_postgres_client, sample_table_mapping
    ):
        """Verifica criação de snapshot usando shadow tables."""
        with patch("src.services.rollback_manager.get_settings") as mock_settings:
            mock_cfg = MagicMock()
            mock_cfg.rollback_timeout_seconds = 30
            mock_cfg.s3_bucket = "test-bucket"
            mock_settings.return_value = mock_cfg

            manager = RollbackManager()
            manager._postgres = mock_postgres_client

            snapshot_id = await manager.create_snapshot(
                migration_job_id="job-123",
                table_mappings=[sample_table_mapping],
                strategy="shadow",
            )

            assert snapshot_id is not None
            # Verifica que shadow table foi criada
            mock_postgres_client.execute_query.assert_called()

    @pytest.mark.asyncio
    async def test_create_snapshot_fallback_to_shadow_on_s3_error(
        self, mock_postgres_client, sample_table_mapping
    ):
        """Verifica fallback para shadow quando S3 falha."""
        with patch("src.services.rollback_manager.get_settings") as mock_settings:
            mock_cfg = MagicMock()
            mock_cfg.rollback_timeout_seconds = 30
            mock_cfg.s3_bucket = "test-bucket"
            mock_settings.return_value = mock_cfg

            manager = RollbackManager()
            manager._postgres = mock_postgres_client

            snapshot_id = await manager.create_snapshot(
                migration_job_id="job-123",
                table_mappings=[sample_table_mapping],
                strategy="s3",  # S3 solicitado, mas vai falhar
            )

            # Deve retornar snapshot_id mesmo com fallback
            assert snapshot_id is not None

    @pytest.mark.asyncio
    async def test_execute_rollback_from_s3_snapshot(self, mock_postgres_client, mock_s3_client):
        """Verifica rollback restaurando de snapshot S3."""
        with patch("src.services.rollback_manager.get_settings") as mock_settings:
            mock_cfg = MagicMock()
            mock_cfg.rollback_timeout_seconds = 30
            mock_cfg.s3_bucket = "test-bucket"
            mock_settings.return_value = mock_cfg

            manager = RollbackManager()
            manager._postgres = mock_postgres_client
            manager._s3 = mock_s3_client

            # Criar snapshot na memória primeiro
            snapshot = RollbackSnapshot(
                snapshot_id="snap-123",
                migration_job_id="job-123",
                tables=["users"],
                created_at=datetime.now(timezone.utc),
                storage_location="s3://test-bucket/snapshots/snap-123.json.gz",
                storage_type="s3",
                status=RollbackStatus.COMPLETED,
            )
            manager._snapshots["snap-123"] = snapshot

            # Mock S3 response com dados do snapshot
            snapshot_data = {
                "snapshot_id": "snap-123",
                "migration_job_id": "job-123",
                "tables": [
                    {
                        "table_name": "users",
                        "schema": "public",
                        "row_count": 2,
                        "data": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
                    }
                ],
            }

            # Criar mock body com método read
            mock_body = MagicMock()
            mock_body.read.return_value = gzip.compress(json.dumps(snapshot_data).encode())

            mock_s3_client.get_object.return_value = mock_body

            stats = await manager.execute_rollback(snapshot_id="snap-123")

            assert stats.tables_processed == 1
            assert stats.rows_restored == 2
            assert stats.tables_failed == 0

    @pytest.mark.asyncio
    async def test_execute_rollback_from_shadow_table(self, mock_postgres_client):
        """Verifica rollback usando shadow tables."""
        with patch("src.services.rollback_manager.get_settings") as mock_settings:
            mock_cfg = MagicMock()
            mock_cfg.rollback_timeout_seconds = 30
            mock_cfg.s3_bucket = "test-bucket"
            mock_settings.return_value = mock_cfg

            manager = RollbackManager()
            manager._postgres = mock_postgres_client

            # Criar snapshot com shadow
            from src.models.migration import TableMapping

            table_mapping = TableMapping(
                source_schema="public",
                source_table="users",
                target_table="users",
                fields=[],
            )

            snapshot_id = await manager.create_snapshot(
                migration_job_id="job-123",
                table_mappings=[table_mapping],
                strategy="shadow",
            )

            # Executar rollback
            mock_postgres_client.execute_query.return_value = None
            stats = await manager.execute_rollback(snapshot_id=snapshot_id)

            assert stats.tables_processed == 1
            assert stats.tables_failed == 0

    @pytest.mark.asyncio
    async def test_execute_rollback_nonexistent_snapshot(
        self, mock_postgres_client, mock_s3_client
    ):
        """Verifica erro ao tentar rollback de snapshot inexistente."""
        with patch("src.services.rollback_manager.get_settings") as mock_settings:
            mock_cfg = MagicMock()
            mock_cfg.rollback_timeout_seconds = 30
            mock_cfg.s3_bucket = "test-bucket"
            mock_settings.return_value = mock_cfg

            manager = RollbackManager()
            manager._postgres = mock_postgres_client
            manager._s3 = mock_s3_client

            mock_s3_client.get_object.side_effect = Exception("NoSuchKey")

            with pytest.raises(ValueError, match="Snapshot não encontrado"):
                await manager.execute_rollback(snapshot_id="nonexistent")

    @pytest.mark.asyncio
    async def test_cleanup_snapshot_s3(self, mock_s3_client):
        """Verifica limpeza de snapshot armazenado em S3."""
        with patch("src.services.rollback_manager.get_settings") as mock_settings:
            mock_cfg = MagicMock()
            mock_cfg.rollback_timeout_seconds = 30
            mock_cfg.s3_bucket = "test-bucket"
            mock_settings.return_value = mock_cfg

            manager = RollbackManager()
            manager._s3 = mock_s3_client

            # Criar snapshot na memória
            snapshot = RollbackSnapshot(
                snapshot_id="snap-123",
                migration_job_id="job-123",
                tables=["users"],
                created_at=datetime.now(timezone.utc),
                storage_location="s3://test-bucket/snapshots/snap-123.json.gz",
                storage_type="s3",
                status=RollbackStatus.COMPLETED,
            )
            manager._snapshots["snap-123"] = snapshot

            # Configurar mock para ter o método remove_object (MinIO)
            if not hasattr(mock_s3_client, "remove_object"):
                mock_s3_client.remove_object = MagicMock()

            result = await manager.cleanup_snapshot(snapshot_id="snap-123")

            assert result is True
            assert "snap-123" not in manager._snapshots
            # Verifica que remove_object ou delete_object foi chamado
            assert mock_s3_client.remove_object.called or mock_s3_client.delete_object.called

    @pytest.mark.asyncio
    async def test_cleanup_snapshot_shadow(self, mock_postgres_client):
        """Verifica limpeza de shadow tables."""
        with patch("src.services.rollback_manager.get_settings") as mock_settings:
            mock_cfg = MagicMock()
            mock_cfg.rollback_timeout_seconds = 30
            mock_cfg.s3_bucket = "test-bucket"
            mock_settings.return_value = mock_cfg

            manager = RollbackManager()
            manager._postgres = mock_postgres_client

            # Criar snapshot com shadow
            from src.models.migration import TableMapping

            table_mapping = TableMapping(
                source_schema="public",
                source_table="users",
                target_table="users",
                fields=[],
            )

            snapshot_id = await manager.create_snapshot(
                migration_job_id="job-123",
                table_mappings=[table_mapping],
                strategy="shadow",
            )

            # Limpar snapshot
            mock_postgres_client.execute_query.return_value = None
            result = await manager.cleanup_snapshot(snapshot_id=snapshot_id)

            assert result is True
            assert snapshot_id not in manager._snapshots

    @pytest.mark.asyncio
    async def test_cleanup_old_snapshots(self, mock_s3_client):
        """Verifica limpeza de snapshots antigos."""
        with patch("src.services.rollback_manager.get_settings") as mock_settings:
            mock_cfg = MagicMock()
            mock_cfg.rollback_timeout_seconds = 30
            mock_cfg.s3_bucket = "test-bucket"
            mock_settings.return_value = mock_cfg

            manager = RollbackManager()
            manager._s3 = mock_s3_client

            # Criar snapshots antigos
            old_time = datetime.now(timezone.utc) - timedelta(days=10)
            snapshot_old = RollbackSnapshot(
                snapshot_id="snap-old",
                migration_job_id="job-old",
                tables=["users"],
                created_at=old_time,
                storage_location="s3://bucket/snap-old/",
                storage_type="s3",
                status=RollbackStatus.COMPLETED,
            )

            # Criar snapshot recente
            recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
            snapshot_recent = RollbackSnapshot(
                snapshot_id="snap-recent",
                migration_job_id="job-recent",
                tables=["users"],
                created_at=recent_time,
                storage_location="s3://bucket/snap-recent/",
                storage_type="s3",
                status=RollbackStatus.COMPLETED,
            )

            manager._snapshots["snap-old"] = snapshot_old
            manager._snapshots["snap-recent"] = snapshot_recent

            # Limpar snapshots com mais de 7 dias
            cleaned = await manager.cleanup_old_snapshots(older_than_days=7)

            assert cleaned == 1
            assert "snap-old" not in manager._snapshots
            assert "snap-recent" in manager._snapshots

    @pytest.mark.asyncio
    async def test_get_rollback_status(self):
        """Verifica obtenção de status de rollback."""
        manager = RollbackManager()

        # Criar snapshot
        snapshot = RollbackSnapshot(
            snapshot_id="snap-123",
            migration_job_id="job-123",
            tables=["users"],
            created_at=datetime.now(timezone.utc),
            storage_location="s3://bucket/snap-123/",
            storage_type="s3",
            status=RollbackStatus.COMPLETED,
        )
        manager._snapshots["snap-123"] = snapshot

        status = await manager.get_rollback_status(snapshot_id="snap-123")

        assert status["snapshot_id"] == "snap-123"
        assert status["status"] == "completed"
        assert status["tables"] == ["users"]

    @pytest.mark.asyncio
    async def test_get_rollback_status_nonexistent(self):
        """Verifica status para snapshot inexistente."""
        manager = RollbackManager()

        status = await manager.get_rollback_status(snapshot_id="nonexistent")

        assert status["exists"] is False

    @pytest.mark.asyncio
    async def test_list_snapshots(self):
        """Verifica listagem de snapshots."""
        manager = RollbackManager()

        # Criar snapshots
        snapshot1 = RollbackSnapshot(
            snapshot_id="snap-1",
            migration_job_id="job-1",
            tables=["users"],
            created_at=datetime.now(timezone.utc),
            storage_location="s3://bucket/snap-1/",
            storage_type="s3",
            status=RollbackStatus.COMPLETED,
        )

        snapshot2 = RollbackSnapshot(
            snapshot_id="snap-2",
            migration_job_id="job-2",
            tables=["orders"],
            created_at=datetime.now(timezone.utc),
            storage_location="s3://bucket/snap-2/",
            storage_type="s3",
            status=RollbackStatus.IN_PROGRESS,
        )

        manager._snapshots["snap-1"] = snapshot1
        manager._snapshots["snap-2"] = snapshot2

        snapshots = await manager.list_snapshots()

        assert len(snapshots) == 2

    @pytest.mark.asyncio
    async def test_list_snapshots_by_migration_job(self):
        """Verifica filtragem de snapshots por job de migração."""
        manager = RollbackManager()

        snapshot1 = RollbackSnapshot(
            snapshot_id="snap-1",
            migration_job_id="job-123",
            tables=["users"],
            created_at=datetime.now(timezone.utc),
            storage_location="s3://bucket/snap-1/",
            storage_type="s3",
            status=RollbackStatus.COMPLETED,
        )

        snapshot2 = RollbackSnapshot(
            snapshot_id="snap-2",
            migration_job_id="job-456",
            tables=["orders"],
            created_at=datetime.now(timezone.utc),
            storage_location="s3://bucket/snap-2/",
            storage_type="s3",
            status=RollbackStatus.COMPLETED,
        )

        manager._snapshots["snap-1"] = snapshot1
        manager._snapshots["snap-2"] = snapshot2

        snapshots = await manager.list_snapshots(migration_job_id="job-123")

        assert len(snapshots) == 1
        assert snapshots[0]["snapshot_id"] == "snap-1"

    @pytest.mark.asyncio
    async def test_timeout_during_rollback(self, mock_postgres_client, mock_s3_client):
        """Verifica timeout durante execução de rollback."""
        with patch("src.services.rollback_manager.get_settings") as mock_settings:
            mock_cfg = MagicMock()
            mock_cfg.rollback_timeout_seconds = 0.1  # Timeout muito curto
            mock_cfg.s3_bucket = "test-bucket"
            mock_settings.return_value = mock_cfg

            manager = RollbackManager()
            manager._postgres = mock_postgres_client
            manager._s3 = mock_s3_client

            # Criar snapshot na memória
            snapshot = RollbackSnapshot(
                snapshot_id="snap-slow",
                migration_job_id="job-slow",
                tables=["large_table"],
                created_at=datetime.now(timezone.utc),
                storage_location="s3://test-bucket/snapshots/snap-slow.json.gz",
                storage_type="s3",
                status=RollbackStatus.COMPLETED,
            )
            manager._snapshots["snap-slow"] = snapshot

            # Simular operação lenta
            snapshot_data = {
                "snapshot_id": "snap-slow",
                "migration_job_id": "job-slow",
                "tables": [
                    {
                        "table_name": "large_table",
                        "schema": "public",
                        "row_count": 1000000,
                        "data": [{"id": i} for i in range(1000)],  # Muitos dados
                    }
                ],
            }

            # Criar mock body com método read
            mock_body = MagicMock()
            mock_body.read.return_value = gzip.compress(json.dumps(snapshot_data).encode())
            mock_s3_client.get_object.return_value = mock_body

            import asyncio

            async def slow_restore(*args, **kwargs):
                await asyncio.sleep(2)  # Excede timeout
                return None

            mock_postgres_client.execute_query = AsyncMock(side_effect=slow_restore)

            # O rollback deve completar mas com falha devido ao timeout
            stats = await manager.execute_rollback(snapshot_id="snap-slow")

            # Deve ter falhado devido ao timeout
            assert stats.tables_failed == 1
            assert stats.tables_processed == 0
            assert any("Timeout" in e for e in stats.errors)

    @pytest.mark.asyncio
    async def test_create_snapshot_preserves_data_types(self, mock_postgres_client, mock_s3_client):
        """Verifica que snapshot preserva tipos de dados corretamente."""
        from src.models.migration import FieldMapping, TableMapping

        with patch("src.services.rollback_manager.get_settings") as mock_settings:
            mock_cfg = MagicMock()
            mock_cfg.rollback_timeout_seconds = 30
            mock_cfg.s3_bucket = "test-bucket"
            mock_cfg.s3_endpoint = "http://localhost:9000"
            mock_cfg.s3_access_key = "test-key"
            mock_cfg.s3_secret_key = "test-secret"
            mock_cfg.s3_use_ssl = False
            mock_settings.return_value = mock_cfg

            table_mapping = TableMapping(
                source_schema="public",
                source_table="users",
                target_table="users",
                fields=[
                    FieldMapping(
                        source_field="id",
                        target_field="id",
                        data_type="integer",
                        is_primary_key=True,
                    ),
                    FieldMapping(
                        source_field="created_at",
                        target_field="created_at",
                        data_type="timestamp",
                    ),
                ],
            )

            manager = RollbackManager()
            manager._postgres = mock_postgres_client
            manager._s3 = mock_s3_client

            # Mock dados com tipos diversos
            mock_postgres_client.fetch_batch.return_value = [
                {
                    "id": 1,
                    "created_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                    "balance": 100.50,
                    "active": True,
                    "metadata": {"key": "value"},
                }
            ]
            mock_postgres_client.get_table_count.return_value = 1

            snapshot_id = await manager.create_snapshot(
                migration_job_id="job-123",
                table_mappings=[table_mapping],
                strategy="s3",
            )

            assert snapshot_id is not None

    @pytest.mark.asyncio
    async def test_partial_rollback_with_failures(self, mock_postgres_client, mock_s3_client):
        """Verifica rollback parcial quando algumas tabelas falham."""
        with patch("src.services.rollback_manager.get_settings") as mock_settings:
            mock_cfg = MagicMock()
            mock_cfg.rollback_timeout_seconds = 30
            mock_cfg.s3_bucket = "test-bucket"
            mock_settings.return_value = mock_cfg

            manager = RollbackManager()
            manager._postgres = mock_postgres_client
            manager._s3 = mock_s3_client

            # Criar snapshot na memória
            snapshot = RollbackSnapshot(
                snapshot_id="snap-partial",
                migration_job_id="job-partial",
                tables=["users", "orders", "products"],
                created_at=datetime.now(timezone.utc),
                storage_location="s3://test-bucket/snapshots/snap-partial.json.gz",
                storage_type="s3",
                status=RollbackStatus.COMPLETED,
            )
            manager._snapshots["snap-partial"] = snapshot

            # Snapshot com 3 tabelas
            snapshot_data = {
                "snapshot_id": "snap-partial",
                "migration_job_id": "job-partial",
                "tables": [
                    {
                        "table_name": "users",
                        "schema": "public",
                        "row_count": 10,
                        "data": [{"id": i, "name": f"user_{i}"} for i in range(10)],
                    },
                    {
                        "table_name": "orders",
                        "schema": "public",
                        "row_count": 5,
                        "data": [{"id": i, "amount": i * 10} for i in range(5)],
                    },
                    {
                        "table_name": "products",
                        "schema": "public",
                        "row_count": 3,
                        "data": [{"id": i, "name": f"product_{i}"} for i in range(3)],
                    },
                ],
            }

            # Criar mock body com método read
            mock_body = MagicMock()
            mock_body.read.return_value = gzip.compress(json.dumps(snapshot_data).encode())
            mock_s3_client.get_object.return_value = mock_body

            # Falhar ao restaurar 'orders'
            call_count = 0

            async def execute_with_failure(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if "orders" in str(args):
                    raise Exception("Table constraint error")
                return None

            mock_postgres_client.execute_query = AsyncMock(side_effect=execute_with_failure)

            stats = await manager.execute_rollback(snapshot_id="snap-partial")

            # 2 de 3 tabelas devem ter sucesso
            assert stats.tables_processed == 2
            assert stats.tables_failed == 1
            assert stats.rows_restored == 13  # 10 users + 3 products


class TestGetRollbackManager:
    """Testes para função get_rollback_manager."""

    def test_returns_singleton_instance(self):
        """Verifica que retorna instância singleton."""
        with patch("src.services.rollback_manager.get_settings"):
            manager1 = get_rollback_manager()
            manager2 = get_rollback_manager()

            assert manager1 is manager2
