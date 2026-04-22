"""
Módulo de Disaster Recovery para Neural Hive Mind Specialists.

Fornece backup, restore e teste de recovery para o estado completo dos especialistas neurais.

Componentes principais:
- DisasterRecoveryManager: Orquestra backup e restore
- StorageClient: Abstração para S3/GCS/Local storage
- BackupManifest: Schema de metadados de backup
"""

from .backup_manifest import BackupManifest
from .disaster_recovery_manager import DisasterRecoveryManager
from .storage_client import (
    GCSStorageClient,
    LocalStorageClient,
    S3StorageClient,
    StorageClient,
)

__all__ = [
    "DisasterRecoveryManager",
    "StorageClient",
    "S3StorageClient",
    "GCSStorageClient",
    "LocalStorageClient",
    "BackupManifest",
]
