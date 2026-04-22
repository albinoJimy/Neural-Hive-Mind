"""Modelos de domínio para Data Migration Workflow.

Autor: Neural Hive Mind
Criado: 2026-04-20
"""

from enum import Enum


class MigrationStatus(str, Enum):
    """Status de uma migração de dados."""

    PENDING = "pending"
    ANALYZING = "analyzing"
    MAPPING = "mapping"
    SNAPSHOT_CREATED = "snapshot_created"
    BATCH_MIGRATING = "batch_migrating"
    CDC_RUNNING = "cdc_running"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    PAUSED = "paused"
