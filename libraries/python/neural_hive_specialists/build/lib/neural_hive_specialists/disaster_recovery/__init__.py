"""
Módulo de Disaster Recovery para Neural Hive Mind Specialists.

Fornece backup, restore e teste de recovery para o estado completo dos especialistas neurais.

Componentes principais:
- DisasterRecoveryManager: Orquestra backup e restore
- StorageClient: Abstração para S3/GCS/Local storage
- BackupManifest: Schema de metadados de backup
"""

from .disaster_recovery_manager import DisasterRecoveryManager
from .storage_client import (
    StorageClient,
    S3StorageClient,
    GCSStorageClient,
    LocalStorageClient
)
from .backup_manifest import BackupManifest

__all__ = [
    'DisasterRecoveryManager',
    'StorageClient',
    'S3StorageClient',
    'GCSStorageClient',
    'LocalStorageClient',
    'BackupManifest'
]
