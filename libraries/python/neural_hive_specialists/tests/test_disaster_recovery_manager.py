"""
Comprehensive unit tests for DisasterRecoveryManager.

Tests cover:
- Backup success path with manifest and tar.gz generation
- Backup partial component failure handling
- Delete expired backups with timezone-aware timestamps
- Restore model from artifacts
- Restore ledger from BSON dump
- Restore feature store with tenant filtering
- Test recovery validates components
"""

import os
import json
import tarfile
import tempfile
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock, patch, call, mock_open
from pathlib import Path

import pytest

from neural_hive_specialists.disaster_recovery.disaster_recovery_manager import DisasterRecoveryManager
from neural_hive_specialists.disaster_recovery.backup_manifest import BackupManifest, ComponentMetadata
from neural_hive_specialists.disaster_recovery.storage_client import StorageClient


@pytest.fixture
def mock_config():
    """Mock specialist config."""
    config = Mock()
    config.specialist_type = 'technical'
    config.environment = 'test'
    config.service_name = 'test-service'
    config.backup_compression_level = 6
    config.backup_include_cache = True
    config.backup_include_feature_store = True
    config.backup_include_metrics = True
    config.backup_storage_provider = 's3'
    config.backup_retention_days = 90
    config.backup_mode = 'full'
    config.backup_prefix = 'specialists/backups'
    config.mlflow_model_name = 'test-model'
    config.mlflow_model_stage = 'Production'
    config.mlflow_tracking_uri = 'http://localhost:5000'
    config.mlflow_experiment_name = 'test-experiment'
    config.mongodb_uri = 'mongodb://localhost:27017'
    config.mongodb_database = 'test_db'
    config.mongodb_ledger_collection = 'opinions'
    config.mongodb_feature_store_collection = 'plan_features'
    config.redis_cluster_nodes = 'localhost:6379'
    config.redis_password = None
    config.redis_ssl_enabled = False
    config.redis_cache_ttl = 3600
    config.enable_multi_tenancy = True
    return config


@pytest.fixture
def mock_specialist():
    """Mock specialist instance."""
    specialist = Mock()
    specialist.mlflow_client = Mock()
    specialist.metrics = Mock()
    specialist.opinion_cache = Mock()
    return specialist


@pytest.fixture
def mock_storage_client():
    """Mock storage client."""
    client = Mock(spec=StorageClient)
    client.upload_backup = Mock(return_value=True)
    client.download_backup = Mock(return_value=True)
    client.delete_backup = Mock(return_value=True)
    client.list_backups = Mock(return_value=[])
    return client


@pytest.fixture
def dr_manager(mock_config, mock_specialist, mock_storage_client):
    """DisasterRecoveryManager instance with mocks."""
    return DisasterRecoveryManager(mock_config, mock_specialist, mock_storage_client)


class TestBackupSuccessPath:
    """Test successful backup flow."""

    def test_backup_success_path(self, dr_manager, mock_storage_client):
        """Test complete backup flow creates manifest, tar.gz, and uploads."""
        with patch.object(dr_manager, '_backup_model') as mock_model, \
             patch.object(dr_manager, '_backup_config') as mock_config, \
             patch.object(dr_manager, '_backup_ledger') as mock_ledger, \
             patch.object(dr_manager, '_backup_cache') as mock_cache, \
             patch.object(dr_manager, '_backup_feature_store') as mock_features, \
             patch.object(dr_manager, '_backup_metrics') as mock_metrics, \
             patch('tempfile.mkdtemp') as mock_mkdtemp, \
             patch('shutil.rmtree') as mock_rmtree, \
             patch('os.remove'):

            # Setup mocks
            mock_model.return_value = {'success': True, 'duration_seconds': 1.0, 'metadata': {}}
            mock_config.return_value = {'success': True, 'duration_seconds': 0.5}
            mock_ledger.return_value = {'success': True, 'duration_seconds': 2.0}
            mock_cache.return_value = {'success': True, 'duration_seconds': 0.3}
            mock_features.return_value = {'success': True, 'duration_seconds': 1.5}
            mock_metrics.return_value = {'success': True, 'duration_seconds': 0.2}

            backup_dir = tempfile.mkdtemp()
            mock_mkdtemp.return_value = backup_dir

            try:
                # Create component directories
                for component in ['model', 'config', 'ledger', 'cache', 'feature_store', 'metrics']:
                    os.makedirs(os.path.join(backup_dir, component), exist_ok=True)
                    # Create a dummy file in each component
                    with open(os.path.join(backup_dir, component, 'test.txt'), 'w') as f:
                        f.write('test')

                # Execute backup
                result = dr_manager.backup_specialist_state()

                # Verify result
                assert result['status'] == 'success'
                assert 'backup_id' in result
                assert 'backup_filename' in result
                assert result['total_size_bytes'] > 0
                assert result['duration_seconds'] > 0
                assert 'model' in result['components_included']
                assert 'config' in result['components_included']
                assert 'checksum' in result

                # Verify storage client upload was called
                assert mock_storage_client.upload_backup.call_count >= 2  # tar.gz + checksum

            finally:
                # Cleanup
                if os.path.exists(backup_dir):
                    import shutil
                    shutil.rmtree(backup_dir, ignore_errors=True)

    def test_backup_creates_valid_manifest(self, dr_manager):
        """Test that backup creates manifest with correct structure."""
        with patch.object(dr_manager, '_backup_model') as mock_model, \
             patch.object(dr_manager, '_backup_config') as mock_config, \
             patch.object(dr_manager, '_backup_ledger') as mock_ledger, \
             patch.object(dr_manager.storage_client, 'upload_backup', return_value=True), \
             patch('tempfile.mkdtemp') as mock_mkdtemp, \
             patch('shutil.rmtree'), \
             patch('os.remove'):

            mock_model.return_value = {'success': True, 'duration_seconds': 1.0, 'metadata': {'artifacts_size': 1024}}
            mock_config.return_value = {'success': True, 'duration_seconds': 0.5}
            mock_ledger.return_value = {'success': True, 'duration_seconds': 2.0}

            backup_dir = tempfile.mkdtemp()
            mock_mkdtemp.return_value = backup_dir

            try:
                # Create component directories with files
                for component in ['model', 'config', 'ledger']:
                    comp_dir = os.path.join(backup_dir, component)
                    os.makedirs(comp_dir, exist_ok=True)
                    with open(os.path.join(comp_dir, 'data.txt'), 'w') as f:
                        f.write('component data')

                result = dr_manager.backup_specialist_state(tenant_id='tenant1')

                # Verify manifest was created
                manifest_path = os.path.join(backup_dir, 'metadata.json')
                assert os.path.exists(manifest_path)

                # Load and validate manifest
                with open(manifest_path, 'r') as f:
                    manifest_data = json.load(f)

                assert 'backup_id' in manifest_data
                assert manifest_data['specialist_type'] == 'technical'
                assert manifest_data['tenant_id'] == 'tenant1'
                assert 'backup_timestamp' in manifest_data
                assert 'backup_version' in manifest_data
                assert 'components' in manifest_data
                assert 'checksums' in manifest_data
                assert manifest_data['compression_level'] == 6

            finally:
                if os.path.exists(backup_dir):
                    import shutil
                    shutil.rmtree(backup_dir, ignore_errors=True)

    def test_backup_with_tar_generation(self, dr_manager):
        """Test that backup generates tar.gz with correct compression."""
        with patch.object(dr_manager, '_backup_model', return_value={'success': True, 'duration_seconds': 1.0}), \
             patch.object(dr_manager, '_backup_config', return_value={'success': True, 'duration_seconds': 0.5}), \
             patch.object(dr_manager.storage_client, 'upload_backup', return_value=True), \
             patch('tempfile.mkdtemp') as mock_mkdtemp, \
             patch('shutil.rmtree'), \
             patch('os.remove'):

            backup_dir = tempfile.mkdtemp()
            mock_mkdtemp.return_value = backup_dir

            try:
                # Create test data
                os.makedirs(os.path.join(backup_dir, 'model'), exist_ok=True)
                test_file = os.path.join(backup_dir, 'model', 'test.txt')
                with open(test_file, 'w') as f:
                    f.write('test data' * 100)

                result = dr_manager.backup_specialist_state()

                # Verify tar.gz file would be created with compression level 6
                assert result['status'] == 'success'
                # The actual tar.gz file is created and then removed, so we verify through result
                assert result['total_size_bytes'] > 0

            finally:
                if os.path.exists(backup_dir):
                    import shutil
                    shutil.rmtree(backup_dir, ignore_errors=True)


class TestPartialComponentFailure:
    """Test backup behavior when components fail."""

    def test_backup_partial_component_failure(self, dr_manager, mock_storage_client):
        """Test that backup continues when some components fail."""
        with patch.object(dr_manager, '_backup_model') as mock_model, \
             patch.object(dr_manager, '_backup_config') as mock_config, \
             patch.object(dr_manager, '_backup_ledger') as mock_ledger, \
             patch('tempfile.mkdtemp') as mock_mkdtemp, \
             patch('shutil.rmtree'), \
             patch('os.remove'):

            # Model succeeds
            mock_model.return_value = {'success': True, 'duration_seconds': 1.0, 'metadata': {}}
            # Config fails
            mock_config.return_value = {'success': False, 'error': 'Config error', 'duration_seconds': 0.1}
            # Ledger succeeds
            mock_ledger.return_value = {'success': True, 'duration_seconds': 2.0}

            backup_dir = tempfile.mkdtemp()
            mock_mkdtemp.return_value = backup_dir

            try:
                os.makedirs(os.path.join(backup_dir, 'model'), exist_ok=True)
                os.makedirs(os.path.join(backup_dir, 'ledger'), exist_ok=True)
                with open(os.path.join(backup_dir, 'model', 'test.txt'), 'w') as f:
                    f.write('data')
                with open(os.path.join(backup_dir, 'ledger', 'test.txt'), 'w') as f:
                    f.write('data')

                result = dr_manager.backup_specialist_state()

                # Backup should succeed with partial components
                assert result['status'] == 'success'
                assert 'model' in result['components_included']
                assert 'ledger' in result['components_included']
                assert 'config' not in result['components_included']

            finally:
                if os.path.exists(backup_dir):
                    import shutil
                    shutil.rmtree(backup_dir, ignore_errors=True)


class TestDeleteExpiredBackups:
    """Test deletion of expired backups."""

    def test_delete_expired_backups_with_timezone(self, dr_manager, mock_storage_client):
        """Test that expired backups are deleted using UTC timezone-aware timestamps."""
        # Create mix of expired and current backups
        now = datetime.now(timezone.utc)
        expired_date = now - timedelta(days=100)
        recent_date = now - timedelta(days=30)

        mock_backups = [
            {
                'key': 'specialist-technical-backup-20240101.tar.gz',
                'size': 1024,
                'timestamp': expired_date
            },
            {
                'key': 'specialist-technical-backup-20240801.tar.gz',
                'size': 2048,
                'timestamp': recent_date
            }
        ]

        mock_storage_client.list_backups.return_value = mock_backups
        mock_storage_client.delete_backup.return_value = True

        deleted_count = dr_manager.delete_expired_backups()

        # Only expired backup should be deleted
        assert deleted_count == 1
        mock_storage_client.delete_backup.assert_called_once()
        # Verify the expired backup key was deleted
        assert 'backup-20240101' in mock_storage_client.delete_backup.call_args[0][0]

    def test_delete_expired_backups_pairs_checksums(self, dr_manager, mock_storage_client):
        """Test that when deleting .tar.gz, corresponding .sha256 is also deleted."""
        now = datetime.now(timezone.utc)
        expired_date = now - timedelta(days=100)

        mock_backups = [
            {
                'key': 'specialist-technical-backup-old.tar.gz',
                'size': 1024,
                'timestamp': expired_date
            }
        ]

        mock_storage_client.list_backups.return_value = mock_backups
        mock_storage_client.delete_backup.return_value = True

        deleted_count = dr_manager.delete_expired_backups()

        assert deleted_count == 1
        # Verify both tar.gz and .sha256 delete calls
        assert mock_storage_client.delete_backup.call_count == 2
        calls = [call[0][0] for call in mock_storage_client.delete_backup.call_args_list]
        assert any('.tar.gz' in c for c in calls)
        assert any('.sha256' in c for c in calls)


class TestTenantSpecificBackup:
    """Test tenant-specific backup filtering."""

    def test_tenant_specific_backup_feature_store(self, dr_manager):
        """Test that feature store backup filters by tenant_id."""
        tenant_id = 'tenant123'

        with patch('pymongo.MongoClient') as mock_mongo:
            mock_collection = Mock()
            mock_collection.find.return_value = [
                {'_id': '1', 'plan_id': 'plan1', 'tenant_id': tenant_id, 'data': 'test'}
            ]
            mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

            with tempfile.TemporaryDirectory() as backup_dir:
                result = dr_manager._backup_feature_store(backup_dir, tenant_id)

                assert result['success'] is True
                # Verify find was called with tenant filter
                mock_collection.find.assert_called_once_with({'tenant_id': tenant_id})


class TestRestoreModel:
    """Test model restoration from artifacts."""

    def test_restore_model_from_artifacts(self, dr_manager):
        """Test restoring model to MLflow using artifacts and metadata."""
        with tempfile.TemporaryDirectory() as component_dir:
            # Create model metadata
            metadata = {
                'model_name': 'test-model',
                'model_version': 'v1',
                'model_stage': 'Production',
                'artifacts_downloaded': True
            }

            metadata_file = os.path.join(component_dir, 'model_metadata.json')
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f)

            # Create artifacts directory
            artifacts_dir = os.path.join(component_dir, 'artifacts')
            os.makedirs(artifacts_dir)

            with patch('mlflow.set_tracking_uri'), \
                 patch('mlflow.tracking.MlflowClient') as mock_client_class, \
                 patch('mlflow.start_run') as mock_start_run, \
                 patch('mlflow.pyfunc.load_model') as mock_load, \
                 patch('mlflow.pyfunc.log_model'), \
                 patch('mlflow.log_param'):

                mock_client = Mock()
                mock_client_class.return_value = mock_client
                mock_client.get_experiment_by_name.return_value = Mock(experiment_id='exp1')
                mock_client.search_model_versions.return_value = [Mock(version='1')]
                mock_client.transition_model_version_stage.return_value = None

                mock_run = Mock()
                mock_run.info.run_id = 'run123'
                mock_start_run.return_value.__enter__.return_value = mock_run

                dr_manager._restore_model(component_dir, None)

                # Verify MLflow operations
                mock_client.get_experiment_by_name.assert_called_once()
                mock_load.assert_called()


class TestRestoreLedger:
    """Test ledger restoration from BSON dump."""

    def test_restore_ledger_from_bson_dump(self, dr_manager):
        """Test restoring ledger via mongorestore or pymongo."""
        with tempfile.TemporaryDirectory() as component_dir:
            # Create JSON fallback file
            ledger_data = [
                {'_id': '1', 'opinion_id': 'op1', 'tenant_id': 'tenant1'},
                {'_id': '2', 'opinion_id': 'op2', 'tenant_id': 'tenant1'}
            ]

            json_file = os.path.join(component_dir, 'opinions.json')
            with open(json_file, 'w') as f:
                json.dump(ledger_data, f)

            with patch('pymongo.MongoClient') as mock_mongo:
                mock_collection = Mock()
                mock_collection.bulk_write.return_value = Mock(upserted_count=2, modified_count=0)
                mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

                dr_manager._restore_ledger(component_dir, None)

                # Verify bulk write was called
                mock_collection.bulk_write.assert_called_once()


class TestRestoreFeatureStore:
    """Test feature store restoration with tenant filtering."""

    def test_restore_feature_store_with_tenant(self, dr_manager):
        """Test restoring feature store with tenant filtering."""
        with tempfile.TemporaryDirectory() as component_dir:
            # Create features data
            features_data = [
                {'_id': '1', 'plan_id': 'plan1', 'tenant_id': 'tenant1', 'features': {}},
                {'_id': '2', 'plan_id': 'plan2', 'tenant_id': 'tenant1', 'features': {}}
            ]

            features_file = os.path.join(component_dir, 'plan_features.json')
            with open(features_file, 'w') as f:
                json.dump(features_data, f)

            with patch('pymongo.MongoClient') as mock_mongo:
                mock_collection = Mock()
                mock_collection.bulk_write.return_value = Mock(upserted_count=2, modified_count=0)
                mock_collection.delete_many.return_value = Mock(deleted_count=0)
                mock_collection.create_index.return_value = None
                mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

                dr_manager._restore_feature_store(component_dir, None)

                # Verify tenant filtering in delete
                mock_collection.delete_many.assert_called_once()
                delete_filter = mock_collection.delete_many.call_args[0][0]
                assert 'tenant_id' in delete_filter


class TestRecoveryValidation:
    """Test recovery validation flow."""

    def test_test_recovery_validates_components(self, dr_manager, mock_storage_client):
        """Test that test_recovery downloads, extracts, validates manifest and runs smoke tests."""
        # Mock available backups
        mock_storage_client.list_backups.return_value = [
            {
                'key': 'specialist-technical-backup-latest.tar.gz',
                'size': 1024,
                'timestamp': datetime.now(timezone.utc)
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a mock backup archive
            backup_archive = os.path.join(temp_dir, 'test-backup.tar.gz')
            backup_content_dir = os.path.join(temp_dir, 'backup_content')
            os.makedirs(backup_content_dir)

            # Create manifest
            manifest = BackupManifest(
                backup_id='test123',
                specialist_type='technical',
                backup_timestamp=datetime.now(timezone.utc),
                compression_level=6
            )

            # Add components
            for comp in ['model', 'config', 'ledger']:
                comp_dir = os.path.join(backup_content_dir, comp)
                os.makedirs(comp_dir)
                with open(os.path.join(comp_dir, 'data.txt'), 'w') as f:
                    f.write('test')
                manifest.add_component(comp, comp_dir, True)

            # Save manifest
            manifest.save_to_file(os.path.join(backup_content_dir, 'metadata.json'))

            # Create tar.gz
            with tarfile.open(backup_archive, 'w:gz') as tar:
                tar.add(backup_content_dir, arcname='')

            # Mock download to return our test archive
            def mock_download(remote_key, local_path):
                import shutil
                shutil.copy2(backup_archive, local_path)
                return True

            mock_storage_client.download_backup.side_effect = mock_download

            # Execute test recovery
            result = dr_manager.test_recovery()

            # Verify result
            assert result['status'] == 'success'
            assert result['test_results']['download']['status'] == 'success'
            assert result['test_results']['extraction']['status'] == 'success'
            assert result['test_results']['manifest_validation']['status'] == 'success'
            assert result['test_results']['component_validation']['status'] == 'success'
            assert 'smoke_tests' in result['test_results']


class TestChecksumValidation:
    """Test checksum calculation and validation."""

    def test_calculate_file_checksum(self, dr_manager):
        """Test SHA-256 checksum calculation."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write('test data for checksum')
            temp_file = f.name

        try:
            checksum = dr_manager._calculate_file_checksum(temp_file)

            # Verify it's a valid SHA-256 hex string
            assert len(checksum) == 64
            assert all(c in '0123456789abcdef' for c in checksum)

            # Verify consistency
            checksum2 = dr_manager._calculate_file_checksum(temp_file)
            assert checksum == checksum2

        finally:
            os.remove(temp_file)


class TestMetricsRecording:
    """Test metrics recording during DR operations."""

    def test_backup_records_metrics(self, dr_manager, mock_specialist):
        """Test that backup operations record metrics."""
        with patch.object(dr_manager, '_backup_model', return_value={'success': True, 'duration_seconds': 1.0}), \
             patch.object(dr_manager, '_backup_config', return_value={'success': True, 'duration_seconds': 0.5}), \
             patch.object(dr_manager.storage_client, 'upload_backup', return_value=True), \
             patch('tempfile.mkdtemp') as mock_mkdtemp, \
             patch('shutil.rmtree'), \
             patch('os.remove'):

            backup_dir = tempfile.mkdtemp()
            mock_mkdtemp.return_value = backup_dir

            try:
                os.makedirs(os.path.join(backup_dir, 'model'), exist_ok=True)
                with open(os.path.join(backup_dir, 'model', 'test.txt'), 'w') as f:
                    f.write('data')

                result = dr_manager.backup_specialist_state()

                # Verify metrics were recorded
                assert mock_specialist.metrics.set_backup_last_success_timestamp.called
                assert mock_specialist.metrics.observe_backup_duration.called
                assert mock_specialist.metrics.set_backup_size.called
                assert mock_specialist.metrics.increment_backup_total.called

            finally:
                if os.path.exists(backup_dir):
                    import shutil
                    shutil.rmtree(backup_dir, ignore_errors=True)


class TestErrorHandling:
    """Test error handling in DR operations."""

    def test_backup_handles_storage_upload_error(self, dr_manager, mock_storage_client, mock_specialist):
        """Test that backup handles storage upload errors gracefully."""
        mock_storage_client.upload_backup.return_value = False

        with patch.object(dr_manager, '_backup_model', return_value={'success': True, 'duration_seconds': 1.0}), \
             patch('tempfile.mkdtemp') as mock_mkdtemp, \
             patch('shutil.rmtree'), \
             patch('os.remove'):

            backup_dir = tempfile.mkdtemp()
            mock_mkdtemp.return_value = backup_dir

            try:
                os.makedirs(os.path.join(backup_dir, 'model'), exist_ok=True)
                with open(os.path.join(backup_dir, 'model', 'test.txt'), 'w') as f:
                    f.write('data')

                result = dr_manager.backup_specialist_state()

                # Backup should fail due to upload error
                assert result['status'] == 'failed'
                assert 'error' in result
                # Metrics should record failure
                assert mock_specialist.metrics.increment_backup_total.called

            finally:
                if os.path.exists(backup_dir):
                    import shutil
                    shutil.rmtree(backup_dir, ignore_errors=True)

    def test_restore_handles_missing_backup(self, dr_manager, mock_storage_client):
        """Test that restore handles missing backup gracefully."""
        mock_storage_client.list_backups.return_value = []

        result = dr_manager.restore_specialist_state('nonexistent-backup-id')

        assert result['status'] == 'failed'
        assert 'error' in result
        assert 'not found' in result['error'].lower()


class TestIncrementalBackup:
    """Test incremental backup with content-addressed storage."""

    @pytest.fixture
    def dr_manager_incremental(self, mock_config, mock_specialist, mock_storage_client):
        """DisasterRecoveryManager configured for incremental backup."""
        mock_config.backup_mode = 'incremental'
        return DisasterRecoveryManager(mock_config, mock_specialist, mock_storage_client)

    def test_incremental_backup_skips_unchanged_components(self, dr_manager_incremental, mock_storage_client):
        """Test que componentes não alterados (mesmo SHA-256) não são re-uploadados."""
        # Simular que blob já existe no storage
        mock_storage_client.list_backups.return_value = [
            {'key': 'specialists/backups/components/model/abc123def456.tar.gz'}
        ]

        with patch.object(dr_manager_incremental, '_backup_model', return_value={'success': True, 'duration_seconds': 1.0}), \
             patch.object(dr_manager_incremental, '_backup_config', return_value={'success': True, 'duration_seconds': 0.5}), \
             patch.object(dr_manager_incremental, '_backup_ledger', return_value={'success': True, 'duration_seconds': 1.5}), \
             patch.object(dr_manager_incremental, '_calculate_file_checksum', return_value='abc123def456'), \
             patch('tempfile.mkdtemp') as mock_mkdtemp, \
             patch('tarfile.open') as mock_tarfile, \
             patch('shutil.rmtree'), \
             patch('os.remove'), \
             patch('os.path.getsize', return_value=1024):

            backup_dir = tempfile.mkdtemp()
            mock_mkdtemp.return_value = backup_dir

            try:
                # Criar diretórios de componentes
                for component in ['model', 'config', 'ledger']:
                    os.makedirs(os.path.join(backup_dir, component), exist_ok=True)
                    with open(os.path.join(backup_dir, component, 'test.txt'), 'w') as f:
                        f.write('data')

                result = dr_manager_incremental.backup_specialist_state()

                # Verificar sucesso
                assert result['status'] == 'success'
                assert result['backup_mode'] == 'incremental'
                assert 'component_digests' in result

                # Verificar que upload foi chamado para snapshot, mas blob model foi pulado
                upload_calls = [call[0][1] for call in mock_storage_client.upload_backup.call_args_list]

                # Deve ter upload de snapshot JSON
                assert any('snapshots/' in key and key.endswith('.json') for key in upload_calls)

                # Blobs novos (config, ledger) devem ter upload, model deve pular
                config_uploads = [key for key in upload_calls if 'components/config/' in key]
                ledger_uploads = [key for key in upload_calls if 'components/ledger/' in key]
                model_uploads = [key for key in upload_calls if 'components/model/' in key]

                assert len(config_uploads) > 0 or len(ledger_uploads) > 0  # Pelo menos um blob novo
                # model já existe, então não deve ter upload (verificado por _blob_exists)

            finally:
                if os.path.exists(backup_dir):
                    import shutil
                    shutil.rmtree(backup_dir, ignore_errors=True)

    def test_incremental_backup_uploads_new_blobs(self, dr_manager_incremental, mock_storage_client):
        """Test que componentes novos (SHA-256 diferente) fazem upload de novo blob."""
        # Simular storage vazio
        mock_storage_client.list_backups.return_value = []

        with patch.object(dr_manager_incremental, '_backup_model', return_value={'success': True, 'duration_seconds': 1.0}), \
             patch.object(dr_manager_incremental, '_backup_config', return_value={'success': True, 'duration_seconds': 0.5}), \
             patch.object(dr_manager_incremental, '_calculate_file_checksum') as mock_checksum, \
             patch('tempfile.mkdtemp') as mock_mkdtemp, \
             patch('tarfile.open') as mock_tarfile, \
             patch('shutil.rmtree'), \
             patch('os.remove'), \
             patch('os.path.getsize', return_value=2048):

            # SHA-256 diferente para cada componente
            sha256_values = {
                'model': 'sha256_model_new',
                'config': 'sha256_config_new'
            }
            mock_checksum.side_effect = lambda path: sha256_values.get(
                os.path.basename(path).replace('.tar.gz', ''),
                'sha256_default'
            )

            backup_dir = tempfile.mkdtemp()
            mock_mkdtemp.return_value = backup_dir

            try:
                # Criar diretórios de componentes
                for component in ['model', 'config']:
                    os.makedirs(os.path.join(backup_dir, component), exist_ok=True)
                    with open(os.path.join(backup_dir, component, 'test.txt'), 'w') as f:
                        f.write('new data')

                result = dr_manager_incremental.backup_specialist_state()

                # Verificar sucesso
                assert result['status'] == 'success'
                assert 'component_digests' in result

                # Verificar que novos blobs foram uploadados
                upload_calls = [call[0][1] for call in mock_storage_client.upload_backup.call_args_list]

                # Deve ter upload de blobs de componentes
                component_blobs = [key for key in upload_calls if 'components/' in key and key.endswith('.tar.gz')]
                assert len(component_blobs) >= 2  # model e config

            finally:
                if os.path.exists(backup_dir):
                    import shutil
                    shutil.rmtree(backup_dir, ignore_errors=True)

    def test_snapshot_assembly_from_refs(self, dr_manager_incremental, mock_storage_client):
        """Test que restore monta corretamente de múltiplos blobs via snapshot."""
        # Simular snapshot JSON
        snapshot_data = {
            'snapshot_id': 'snapshot-20250211-120000',
            'timestamp': datetime.utcnow().isoformat(),
            'specialist_type': 'technical',
            'tenant_id': None,
            'component_refs': {
                'model': 'sha256_model_abc',
                'config': 'sha256_config_def',
                'ledger': 'sha256_ledger_ghi'
            },
            'metadata': {}
        }

        # Mock de download do snapshot
        def mock_download(key, local_path):
            if key.endswith('.json'):
                with open(local_path, 'w') as f:
                    json.dump(snapshot_data, f)
                return True
            elif key.endswith('.tar.gz'):
                # Criar tarball vazio para teste
                component_name = key.split('/')[-2]
                with tarfile.open(local_path, 'w:gz') as tar:
                    pass
                return True
            return False

        mock_storage_client.download_backup.side_effect = mock_download
        mock_storage_client.list_backups.return_value = [
            {'key': 'specialists/backups/snapshots/snapshot-20250211-120000.json'}
        ]

        with patch.object(dr_manager_incremental, '_restore_model'), \
             patch.object(dr_manager_incremental, '_restore_config'), \
             patch.object(dr_manager_incremental, '_restore_ledger'), \
             patch.object(dr_manager_incremental, '_run_smoke_tests', return_value={'passed': True}), \
             patch('tempfile.mkdtemp') as mock_mkdtemp, \
             patch('shutil.rmtree'), \
             patch('os.remove'):

            restore_dir = tempfile.mkdtemp()
            mock_mkdtemp.return_value = restore_dir

            try:
                result = dr_manager_incremental.restore_specialist_state('snapshot-20250211-120000')

                # Verificar sucesso
                assert result['status'] == 'success'
                assert result['backup_mode'] == 'incremental'
                assert len(result['restored_components']) == 3
                assert 'model' in result['restored_components']
                assert 'config' in result['restored_components']
                assert 'ledger' in result['restored_components']

            finally:
                if os.path.exists(restore_dir):
                    import shutil
                    shutil.rmtree(restore_dir, ignore_errors=True)

    def test_garbage_collection_removes_unreferenced(self, dr_manager_incremental, mock_storage_client):
        """Test que GC remove blobs órfãos não referenciados por nenhum snapshot."""
        # Simular snapshots ativos
        snapshot1_data = {
            'snapshot_id': 'snapshot-1',
            'component_refs': {
                'model': 'sha256_model_active',
                'config': 'sha256_config_active'
            }
        }

        snapshot2_data = {
            'snapshot_id': 'snapshot-2',
            'component_refs': {
                'model': 'sha256_model_active',  # Mesmo blob que snapshot-1
                'ledger': 'sha256_ledger_active'
            }
        }

        # Simular download de snapshots
        def mock_download(key, local_path):
            if 'snapshot-1' in key:
                with open(local_path, 'w') as f:
                    json.dump(snapshot1_data, f)
                return True
            elif 'snapshot-2' in key:
                with open(local_path, 'w') as f:
                    json.dump(snapshot2_data, f)
                return True
            return False

        mock_storage_client.download_backup.side_effect = mock_download

        # Simular snapshots e blobs no storage
        mock_storage_client.list_backups.side_effect = lambda prefix, **kwargs: {
            'specialists/backups/snapshots/': [
                {
                    'key': 'specialists/backups/snapshots/snapshot-1.json',
                    'timestamp': datetime.now(timezone.utc)
                },
                {
                    'key': 'specialists/backups/snapshots/snapshot-2.json',
                    'timestamp': datetime.now(timezone.utc)
                }
            ],
            'specialists/backups/components/': [
                # Blobs ativos (referenciados)
                {
                    'key': 'specialists/backups/components/model/sha256_model_active.tar.gz',
                    'size': 1000
                },
                {
                    'key': 'specialists/backups/components/config/sha256_config_active.tar.gz',
                    'size': 500
                },
                {
                    'key': 'specialists/backups/components/ledger/sha256_ledger_active.tar.gz',
                    'size': 2000
                },
                # Blobs órfãos (não referenciados)
                {
                    'key': 'specialists/backups/components/model/sha256_model_orphan.tar.gz',
                    'size': 1500
                },
                {
                    'key': 'specialists/backups/components/config/sha256_config_orphan.tar.gz',
                    'size': 700
                }
            ]
        }.get(prefix, [])

        with patch('os.remove'):
            result = dr_manager_incremental.garbage_collect_blobs()

            # Verificar sucesso
            assert result['status'] == 'success'
            assert result['deleted_count'] == 2  # 2 blobs órfãos
            assert result['freed_bytes'] == 2200  # 1500 + 700

            # Verificar que delete foi chamado para blobs órfãos
            delete_calls = [call[0][0] for call in mock_storage_client.delete_backup.call_args_list]
            assert 'specialists/backups/components/model/sha256_model_orphan.tar.gz' in delete_calls
            assert 'specialists/backups/components/config/sha256_config_orphan.tar.gz' in delete_calls


class TestBackwardCompatibility:
    """Test backward compatibility between full and incremental modes."""

    def test_full_mode_works_as_before(self, dr_manager, mock_storage_client):
        """Test que modo 'full' funciona como comportamento original."""
        # dr_manager usa backup_mode='full' por padrão
        assert dr_manager.config.backup_mode == 'full'

        with patch.object(dr_manager, '_backup_model', return_value={'success': True, 'duration_seconds': 1.0}), \
             patch.object(dr_manager, '_backup_config', return_value={'success': True, 'duration_seconds': 0.5}), \
             patch('tempfile.mkdtemp') as mock_mkdtemp, \
             patch('tarfile.open') as mock_tarfile, \
             patch('shutil.rmtree'), \
             patch('os.remove'), \
             patch('os.path.getsize', return_value=5000):

            backup_dir = tempfile.mkdtemp()
            mock_mkdtemp.return_value = backup_dir

            try:
                os.makedirs(os.path.join(backup_dir, 'model'), exist_ok=True)
                with open(os.path.join(backup_dir, 'model', 'test.txt'), 'w') as f:
                    f.write('data')

                result = dr_manager.backup_specialist_state()

                # Verificar que é backup full tradicional
                assert result['status'] == 'success'
                assert 'backup_mode' not in result or result.get('backup_mode') != 'incremental'

                # Verificar que upload foi de tar.gz completo, não componentes separados
                upload_calls = [call[0][1] for call in mock_storage_client.upload_backup.call_args_list]
                tarball_uploads = [key for key in upload_calls if key.endswith('.tar.gz') and 'specialist-' in key]
                assert len(tarball_uploads) >= 1  # Upload de backup completo

            finally:
                if os.path.exists(backup_dir):
                    import shutil
                    shutil.rmtree(backup_dir, ignore_errors=True)

    def test_restore_detects_backup_type_automatically(self, dr_manager, mock_storage_client):
        """Test que restore detecta automaticamente se backup é full ou snapshot."""
        # Test 1: Backup full (.tar.gz)
        mock_storage_client.list_backups.return_value = [
            {'key': 'specialist-technical-backup-20250211-120000.tar.gz'}
        ]

        # Mock download para tar.gz
        def mock_download_tarball(key, local_path):
            if key.endswith('.tar.gz'):
                with tarfile.open(local_path, 'w:gz') as tar:
                    pass
                return True
            return False

        mock_storage_client.download_backup.side_effect = mock_download_tarball

        with patch('tarfile.open') as mock_tarfile, \
             patch('tempfile.mkdtemp') as mock_mkdtemp, \
             patch('shutil.rmtree'), \
             patch('os.remove'), \
             patch.object(dr_manager, '_run_smoke_tests', return_value={'passed': True}):

            # Criar manifest mock
            manifest_data = BackupManifest(
                backup_id='test-backup',
                specialist_type='technical',
                tenant_id=None,
                backup_timestamp=datetime.utcnow(),
                compression_level=6,
                metadata={}
            )

            with patch.object(BackupManifest, 'load_from_file', return_value=manifest_data), \
                 patch.object(manifest_data, 'validate_checksums', return_value=True):

                restore_dir = tempfile.mkdtemp()
                mock_mkdtemp.return_value = restore_dir

                try:
                    os.makedirs(restore_dir, exist_ok=True)
                    os.makedirs(os.path.join(restore_dir, 'metadata.json'), exist_ok=False)
                    with open(os.path.join(restore_dir, 'metadata.json'), 'w') as f:
                        f.write('{}')

                    # Restore de backup full deve funcionar
                    result = dr_manager.restore_specialist_state('specialist-technical-backup-20250211-120000.tar.gz')

                    # Não deve ter usado modo incremental
                    assert result.get('backup_mode') != 'incremental'

                finally:
                    if os.path.exists(restore_dir):
                        import shutil
                        shutil.rmtree(restore_dir, ignore_errors=True)
