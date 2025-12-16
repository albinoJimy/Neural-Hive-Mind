"""Módulo de governança e versionamento do ledger cognitivo."""

from .opinion_schema_v2 import (
    OpinionDocumentV2,
    Opinion,
    ReasoningFactor,
    Mitigation,
    SchemaVersionManager
)
from .digital_signer import DigitalSigner
from .query_api import LedgerQueryAPI
from .retention_manager import RetentionManager
from .backup_manager import BackupManager

__all__ = [
    'OpinionDocumentV2',
    'Opinion',
    'ReasoningFactor',
    'Mitigation',
    'SchemaVersionManager',
    'DigitalSigner',
    'LedgerQueryAPI',
    'RetentionManager',
    'BackupManager'
]
