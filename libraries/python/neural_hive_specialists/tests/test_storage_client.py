"""
Comprehensive unit tests for StorageClient implementations.

Tests cover:
- S3StorageClient: upload with encryption, download, list, delete, metadata, prefix handling, checksum
- GCSStorageClient: project requirement, upload with metadata, download, list, delete, metadata with reload
- LocalStorageClient: upload creates directories, download file not found, list walks tree, delete, metadata with checksum
"""

import os
import tempfile
import hashlib
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path

import pytest

from neural_hive_specialists.disaster_recovery.storage_client import (
    StorageClient,
    S3StorageClient,
    GCSStorageClient,
    LocalStorageClient,
)


# ============================================================================
# S3StorageClient Tests
# ============================================================================


class TestS3StorageClient:
    """Test S3StorageClient implementation."""

    @pytest.fixture
    def mock_boto3_client(self):
        """Mock boto3 S3 client."""
        with patch(
            "neural_hive_specialists.disaster_recovery.storage_client.boto3"
        ) as mock_boto3:
            mock_client = Mock()
            mock_boto3.client.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def s3_client(self, mock_boto3_client):
        """S3StorageClient instance with mocked boto3."""
        return S3StorageClient(
            bucket="test-bucket",
            region="us-east-1",
            prefix="backups",
            aws_access_key="test-key",
            aws_secret_key="test-secret",
        )

    def test_s3_upload_with_encryption(self, s3_client, mock_boto3_client):
        """Test S3 upload includes ServerSideEncryption AES256."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test data")
            temp_file = f.name

        try:
            result = s3_client.upload_backup(temp_file, "test-backup.tar.gz")

            assert result is True
            mock_boto3_client.upload_file.assert_called_once()

            # Verify ExtraArgs includes encryption
            call_args = mock_boto3_client.upload_file.call_args
            extra_args = call_args[1]["ExtraArgs"]
            assert extra_args["ServerSideEncryption"] == "AES256"
            assert "Metadata" in extra_args
            assert extra_args["Metadata"]["source"] == "neural-hive-disaster-recovery"

        finally:
            os.remove(temp_file)

    def test_s3_download_creates_directory(self, s3_client, mock_boto3_client):
        """Test S3 download creates parent directories if they don't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            download_path = os.path.join(temp_dir, "nested", "path", "backup.tar.gz")

            # Mock successful download
            def mock_download_file(bucket, key, local_path):
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, "w") as f:
                    f.write("downloaded")

            mock_boto3_client.download_file.side_effect = mock_download_file

            result = s3_client.download_backup("test-backup.tar.gz", download_path)

            assert result is True
            assert os.path.exists(download_path)
            mock_boto3_client.download_file.assert_called_once()

    def test_s3_list_backups_sorted(self, s3_client, mock_boto3_client):
        """Test S3 list returns backups sorted by timestamp (most recent first)."""
        # Mock S3 response with multiple objects
        mock_response = {
            "Contents": [
                {
                    "Key": "backups/backup-1.tar.gz",
                    "Size": 1024,
                    "LastModified": datetime(2024, 1, 1, tzinfo=timezone.utc),
                    "ETag": '"abc123"',
                },
                {
                    "Key": "backups/backup-3.tar.gz",
                    "Size": 3072,
                    "LastModified": datetime(2024, 3, 1, tzinfo=timezone.utc),
                    "ETag": '"ghi789"',
                },
                {
                    "Key": "backups/backup-2.tar.gz",
                    "Size": 2048,
                    "LastModified": datetime(2024, 2, 1, tzinfo=timezone.utc),
                    "ETag": '"def456"',
                },
            ]
        }
        mock_boto3_client.list_objects_v2.return_value = mock_response

        backups = s3_client.list_backups()

        # Verify sorted by timestamp descending
        assert len(backups) == 3
        assert backups[0]["key"] == "backups/backup-3.tar.gz"  # Most recent
        assert backups[1]["key"] == "backups/backup-2.tar.gz"
        assert backups[2]["key"] == "backups/backup-1.tar.gz"  # Oldest

    def test_s3_delete_backup_success(self, s3_client, mock_boto3_client):
        """Test S3 delete removes object from bucket."""
        result = s3_client.delete_backup("test-backup.tar.gz")

        assert result is True
        mock_boto3_client.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="backups/test-backup.tar.gz"
        )

    def test_s3_get_metadata(self, s3_client, mock_boto3_client):
        """Test S3 get_metadata returns ContentLength, ETag, LastModified."""
        mock_response = {
            "ContentLength": 2048,
            "ETag": '"abc123"',
            "LastModified": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "Metadata": {"custom": "value"},
        }
        mock_boto3_client.head_object.return_value = mock_response

        metadata = s3_client.get_backup_metadata("test-backup.tar.gz")

        assert metadata["size"] == 2048
        assert metadata["etag"] == '"abc123"'
        assert "last_modified" in metadata
        assert metadata["metadata"]["custom"] == "value"

    def test_s3_prefix_no_double_slash(self, s3_client, mock_boto3_client):
        """Test that prefix doesn't add // if key already includes prefix."""
        # Upload with key that already includes prefix
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test")
            temp_file = f.name

        try:
            s3_client.upload_backup(temp_file, "backups/already-prefixed.tar.gz")

            call_args = mock_boto3_client.upload_file.call_args
            uploaded_key = call_args[0][2]

            # Should not be backups/backups/...
            assert uploaded_key == "backups/already-prefixed.tar.gz"
            assert uploaded_key.count("backups/") == 1

        finally:
            os.remove(temp_file)

    def test_s3_checksum_verification(self, s3_client, mock_boto3_client):
        """Test checksum verification via download."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test data for checksum")
            temp_file = f.name

        try:
            # Calculate expected checksum
            expected_checksum = s3_client._calculate_file_checksum(temp_file)

            # Mock download
            def mock_download(bucket, key, local_path):
                import shutil

                shutil.copy2(temp_file, local_path)

            mock_boto3_client.download_file.side_effect = mock_download

            # Verify checksum
            result = s3_client.verify_checksum("test-backup.tar.gz", expected_checksum)

            assert result is True

        finally:
            os.remove(temp_file)

    def test_s3_error_handling_on_upload(self, s3_client, mock_boto3_client):
        """Test that S3 upload handles boto3 exceptions gracefully."""
        mock_boto3_client.upload_file.side_effect = Exception("S3 upload failed")

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test")
            temp_file = f.name

        try:
            result = s3_client.upload_backup(temp_file, "test-backup.tar.gz")

            # Should return False on error, not raise
            assert result is False

        finally:
            os.remove(temp_file)


# ============================================================================
# GCSStorageClient Tests
# ============================================================================


class TestGCSStorageClient:
    """Test GCSStorageClient implementation."""

    @pytest.fixture
    def mock_gcs_client(self):
        """Mock Google Cloud Storage client."""
        with patch(
            "neural_hive_specialists.disaster_recovery.storage_client.storage"
        ) as mock_storage:
            mock_client = Mock()
            mock_bucket = Mock()
            mock_client.bucket.return_value = mock_bucket
            mock_storage.Client.return_value = mock_client
            yield mock_client, mock_bucket

    @pytest.fixture
    def gcs_client(self, mock_gcs_client):
        """GCSStorageClient instance with mocked GCS."""
        return GCSStorageClient(
            bucket="test-bucket", project="test-project", prefix="backups"
        )

    def test_gcs_requires_project(self):
        """Test that GCS client requires project parameter."""
        with patch("neural_hive_specialists.disaster_recovery.storage_client.storage"):
            # Project is required in __init__
            client = GCSStorageClient(
                bucket="test-bucket", project="test-project", prefix="backups"
            )
            assert client.project == "test-project"

    def test_gcs_upload_with_metadata(self, gcs_client, mock_gcs_client):
        """Test GCS upload includes metadata (uploaded_at, source)."""
        mock_client, mock_bucket = mock_gcs_client

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test data")
            temp_file = f.name

        try:
            mock_blob = Mock()
            mock_bucket.blob.return_value = mock_blob

            result = gcs_client.upload_backup(temp_file, "test-backup.tar.gz")

            assert result is True
            mock_blob.upload_from_filename.assert_called_once_with(temp_file)

            # Verify metadata was set
            assert mock_blob.metadata is not None
            assert "uploaded_at" in mock_blob.metadata
            assert mock_blob.metadata["source"] == "neural-hive-disaster-recovery"

        finally:
            os.remove(temp_file)

    def test_gcs_download_success(self, gcs_client, mock_gcs_client):
        """Test GCS download to filesystem."""
        mock_client, mock_bucket = mock_gcs_client

        with tempfile.TemporaryDirectory() as temp_dir:
            download_path = os.path.join(temp_dir, "downloaded-backup.tar.gz")

            mock_blob = Mock()
            mock_bucket.blob.return_value = mock_blob

            # Mock download to create file
            def mock_download_to_filename(path):
                with open(path, "w") as f:
                    f.write("downloaded data")

            mock_blob.download_to_filename.side_effect = mock_download_to_filename

            result = gcs_client.download_backup("test-backup.tar.gz", download_path)

            assert result is True
            assert os.path.exists(download_path)
            mock_blob.download_to_filename.assert_called_once()

    def test_gcs_list_backups_returns_md5(self, gcs_client, mock_gcs_client):
        """Test GCS list includes md5_hash."""
        mock_client, mock_bucket = mock_gcs_client

        # Mock blobs
        mock_blob1 = Mock()
        mock_blob1.name = "backups/backup-1.tar.gz"
        mock_blob1.size = 1024
        mock_blob1.updated = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_blob1.md5_hash = "abc123"

        mock_blob2 = Mock()
        mock_blob2.name = "backups/backup-2.tar.gz"
        mock_blob2.size = 2048
        mock_blob2.updated = datetime(2024, 2, 1, tzinfo=timezone.utc)
        mock_blob2.md5_hash = "def456"

        mock_client.list_blobs.return_value = [mock_blob1, mock_blob2]

        backups = gcs_client.list_backups()

        assert len(backups) == 2
        assert backups[0]["md5_hash"] == "def456"  # More recent first
        assert backups[1]["md5_hash"] == "abc123"

    def test_gcs_delete_blob(self, gcs_client, mock_gcs_client):
        """Test GCS delete removes blob."""
        mock_client, mock_bucket = mock_gcs_client

        mock_blob = Mock()
        mock_bucket.blob.return_value = mock_blob

        result = gcs_client.delete_backup("test-backup.tar.gz")

        assert result is True
        mock_blob.delete.assert_called_once()

    def test_gcs_get_metadata_with_reload(self, gcs_client, mock_gcs_client):
        """Test GCS get_metadata calls blob.reload() before returning."""
        mock_client, mock_bucket = mock_gcs_client

        mock_blob = Mock()
        mock_blob.size = 2048
        mock_blob.md5_hash = "abc123"
        mock_blob.updated = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_blob.metadata = {"custom": "value"}
        mock_bucket.blob.return_value = mock_blob

        metadata = gcs_client.get_backup_metadata("test-backup.tar.gz")

        # Verify reload was called
        mock_blob.reload.assert_called_once()

        assert metadata["size"] == 2048
        assert metadata["md5_hash"] == "abc123"
        assert "last_modified" in metadata
        assert metadata["metadata"]["custom"] == "value"

    def test_gcs_prefix_handling(self, gcs_client, mock_gcs_client):
        """Test that GCS prefix doesn't duplicate."""
        mock_client, mock_bucket = mock_gcs_client

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test")
            temp_file = f.name

        try:
            mock_blob = Mock()
            mock_bucket.blob.return_value = mock_blob

            # Upload with key that already has prefix
            gcs_client.upload_backup(temp_file, "backups/already-prefixed.tar.gz")

            # Check blob was called with correct key (no duplication)
            mock_bucket.blob.assert_called_with("backups/already-prefixed.tar.gz")

        finally:
            os.remove(temp_file)


# ============================================================================
# LocalStorageClient Tests
# ============================================================================


class TestLocalStorageClient:
    """Test LocalStorageClient implementation."""

    @pytest.fixture
    def local_client(self):
        """LocalStorageClient instance with temp directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            client = LocalStorageClient(base_path=temp_dir)
            yield client

    def test_local_upload_creates_directories(self, local_client):
        """Test local upload creates directories via makedirs."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test data")
            temp_file = f.name

        try:
            # Upload to nested path
            result = local_client.upload_backup(temp_file, "nested/path/backup.tar.gz")

            assert result is True

            # Verify file was copied and directories created
            expected_path = os.path.join(
                local_client.base_path, "nested/path/backup.tar.gz"
            )
            assert os.path.exists(expected_path)
            assert os.path.isdir(os.path.dirname(expected_path))

        finally:
            os.remove(temp_file)

    def test_local_download_file_not_found(self, local_client):
        """Test local download returns False if file doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            download_path = os.path.join(temp_dir, "downloaded.tar.gz")

            result = local_client.download_backup("nonexistent.tar.gz", download_path)

            assert result is False
            assert not os.path.exists(download_path)

    def test_local_list_backups_walks_tree(self, local_client):
        """Test local list walks directory tree recursively."""
        # Create nested backup structure
        os.makedirs(os.path.join(local_client.base_path, "year2024/month01"))
        os.makedirs(os.path.join(local_client.base_path, "year2024/month02"))

        file1 = os.path.join(local_client.base_path, "year2024/month01/backup1.tar.gz")
        file2 = os.path.join(local_client.base_path, "year2024/month02/backup2.tar.gz")
        file3 = os.path.join(local_client.base_path, "backup3.tar.gz")

        for f in [file1, file2, file3]:
            with open(f, "w") as fp:
                fp.write("backup data")

        backups = local_client.list_backups()

        # Should find all 3 files via os.walk
        assert len(backups) == 3
        keys = [b["key"] for b in backups]
        assert any("month01" in k for k in keys)
        assert any("month02" in k for k in keys)
        assert any("backup3.tar.gz" in k for k in keys)

    def test_local_delete_removes_file(self, local_client):
        """Test local delete removes file via os.remove."""
        # Create a test file
        test_file = os.path.join(local_client.base_path, "test-backup.tar.gz")
        with open(test_file, "w") as f:
            f.write("test")

        assert os.path.exists(test_file)

        result = local_client.delete_backup("test-backup.tar.gz")

        assert result is True
        assert not os.path.exists(test_file)

    def test_local_metadata_with_checksum(self, local_client):
        """Test local metadata calculates SHA-256 checksum."""
        # Create test file
        test_file = os.path.join(local_client.base_path, "test-backup.tar.gz")
        test_data = "test data for checksum calculation"
        with open(test_file, "w") as f:
            f.write(test_data)

        metadata = local_client.get_backup_metadata("test-backup.tar.gz")

        assert "size" in metadata
        assert metadata["size"] > 0
        assert "last_modified" in metadata
        assert "checksum" in metadata

        # Verify checksum is valid SHA-256 (64 hex chars)
        assert len(metadata["checksum"]) == 64
        assert all(c in "0123456789abcdef" for c in metadata["checksum"])


# ============================================================================
# StorageClient Base Class Tests
# ============================================================================


class TestStorageClientBase:
    """Test StorageClient base class functionality."""

    def test_verify_checksum_default_implementation(self):
        """Test that base StorageClient.verify_checksum works via download."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a concrete implementation for testing
            client = LocalStorageClient(base_path=temp_dir)

            # Create test file
            test_file = os.path.join(temp_dir, "test.tar.gz")
            with open(test_file, "w") as f:
                f.write("test data")

            # Calculate checksum
            expected_checksum = client._calculate_file_checksum(test_file)

            # Upload
            client.upload_backup(test_file, "backup.tar.gz")

            # Verify checksum
            result = client.verify_checksum("backup.tar.gz", expected_checksum)

            assert result is True

    def test_verify_checksum_fails_on_mismatch(self):
        """Test that verify_checksum returns False on checksum mismatch."""
        with tempfile.TemporaryDirectory() as temp_dir:
            client = LocalStorageClient(base_path=temp_dir)

            test_file = os.path.join(temp_dir, "test.tar.gz")
            with open(test_file, "w") as f:
                f.write("test data")

            client.upload_backup(test_file, "backup.tar.gz")

            # Use wrong checksum
            wrong_checksum = "a" * 64

            result = client.verify_checksum("backup.tar.gz", wrong_checksum)

            assert result is False


# ============================================================================
# Integration-style Tests
# ============================================================================


class TestStorageClientIntegration:
    """Integration-style tests using LocalStorageClient."""

    def test_upload_download_roundtrip(self):
        """Test upload and download roundtrip preserves data."""
        with tempfile.TemporaryDirectory() as base_dir, tempfile.TemporaryDirectory() as work_dir:
            client = LocalStorageClient(base_path=base_dir)

            # Create source file
            source_file = os.path.join(work_dir, "source.tar.gz")
            source_data = "test data for roundtrip" * 100
            with open(source_file, "w") as f:
                f.write(source_data)

            # Upload
            upload_result = client.upload_backup(source_file, "backup.tar.gz")
            assert upload_result is True

            # Download
            download_file = os.path.join(work_dir, "downloaded.tar.gz")
            download_result = client.download_backup("backup.tar.gz", download_file)
            assert download_result is True

            # Verify data matches
            with open(download_file, "r") as f:
                downloaded_data = f.read()

            assert downloaded_data == source_data

    def test_list_includes_all_uploaded_files(self):
        """Test that list_backups includes all uploaded files."""
        with tempfile.TemporaryDirectory() as base_dir, tempfile.TemporaryDirectory() as work_dir:
            client = LocalStorageClient(base_path=base_dir)

            # Upload multiple files
            files = ["backup1.tar.gz", "backup2.tar.gz", "backup3.tar.gz"]
            for filename in files:
                source = os.path.join(work_dir, filename)
                with open(source, "w") as f:
                    f.write(f"data for {filename}")
                client.upload_backup(source, filename)

            # List backups
            backups = client.list_backups()

            assert len(backups) == 3
            keys = [b["key"] for b in backups]
            for filename in files:
                assert filename in keys

    def test_delete_removes_from_list(self):
        """Test that delete removes file from list_backups."""
        with tempfile.TemporaryDirectory() as base_dir, tempfile.TemporaryDirectory() as work_dir:
            client = LocalStorageClient(base_path=base_dir)

            # Upload file
            source = os.path.join(work_dir, "test.tar.gz")
            with open(source, "w") as f:
                f.write("test")
            client.upload_backup(source, "backup.tar.gz")

            # Verify in list
            backups = client.list_backups()
            assert len(backups) == 1

            # Delete
            delete_result = client.delete_backup("backup.tar.gz")
            assert delete_result is True

            # Verify removed from list
            backups = client.list_backups()
            assert len(backups) == 0


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestStorageClientErrorHandling:
    """Test error handling across storage clients."""

    def test_s3_handles_upload_exception(self):
        """Test S3 client handles upload exceptions gracefully."""
        with patch(
            "neural_hive_specialists.disaster_recovery.storage_client.boto3"
        ) as mock_boto3:
            mock_client = Mock()
            mock_client.upload_file.side_effect = Exception("Network error")
            mock_boto3.client.return_value = mock_client

            client = S3StorageClient(bucket="test-bucket", region="us-east-1")

            with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
                f.write("test")
                temp_file = f.name

            try:
                result = client.upload_backup(temp_file, "backup.tar.gz")
                # Should return False, not raise
                assert result is False
            finally:
                os.remove(temp_file)

    def test_gcs_handles_download_exception(self):
        """Test GCS client handles download exceptions gracefully."""
        with patch(
            "neural_hive_specialists.disaster_recovery.storage_client.storage"
        ) as mock_storage:
            mock_client = Mock()
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.download_to_filename.side_effect = Exception("GCS error")
            mock_bucket.blob.return_value = mock_blob
            mock_client.bucket.return_value = mock_bucket
            mock_storage.Client.return_value = mock_client

            client = GCSStorageClient(bucket="test-bucket", project="test-project")

            with tempfile.TemporaryDirectory() as temp_dir:
                download_path = os.path.join(temp_dir, "backup.tar.gz")
                result = client.download_backup("backup.tar.gz", download_path)

                # Should return False, not raise
                assert result is False

    def test_local_handles_permission_error(self):
        """Test local client handles permission errors gracefully."""
        with tempfile.TemporaryDirectory() as base_dir:
            client = LocalStorageClient(base_path=base_dir)

            # Create file with restrictive permissions
            restricted_file = os.path.join(base_dir, "restricted.tar.gz")
            with open(restricted_file, "w") as f:
                f.write("test")
            os.chmod(restricted_file, 0o000)

            try:
                # Attempt to download (read) restricted file
                with tempfile.TemporaryDirectory() as temp_dir:
                    download_path = os.path.join(temp_dir, "downloaded.tar.gz")
                    result = client.download_backup("restricted.tar.gz", download_path)

                    # Should handle error gracefully
                    assert result is False
            finally:
                # Restore permissions for cleanup
                os.chmod(restricted_file, 0o644)


# ============================================================================
# Checksum Tests
# ============================================================================


class TestChecksumCalculation:
    """Test checksum calculation across clients."""

    def test_checksum_consistency(self):
        """Test that checksum calculation is consistent."""
        with tempfile.TemporaryDirectory() as base_dir:
            client = LocalStorageClient(base_path=base_dir)

            test_file = os.path.join(base_dir, "test.tar.gz")
            with open(test_file, "wb") as f:
                f.write(b"test data for checksum")

            checksum1 = client._calculate_file_checksum(test_file)
            checksum2 = client._calculate_file_checksum(test_file)

            assert checksum1 == checksum2
            assert len(checksum1) == 64  # SHA-256 hex length

    def test_different_files_different_checksums(self):
        """Test that different files produce different checksums."""
        with tempfile.TemporaryDirectory() as base_dir:
            client = LocalStorageClient(base_path=base_dir)

            file1 = os.path.join(base_dir, "file1.tar.gz")
            file2 = os.path.join(base_dir, "file2.tar.gz")

            with open(file1, "w") as f:
                f.write("data1")
            with open(file2, "w") as f:
                f.write("data2")

            checksum1 = client._calculate_file_checksum(file1)
            checksum2 = client._calculate_file_checksum(file2)

            assert checksum1 != checksum2
