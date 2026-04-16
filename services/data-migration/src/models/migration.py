"""
Modelos de Dados para Data Migration System.

Define os modelos Pydantic para jobs de migração, mapeamentos de schema
e status de migração.
"""

import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class MigrationStatus(str, Enum):
    """Status de uma migração."""

    PENDING = "pending"
    ANALYZING = "analyzing"
    MAPPING = "mapping"
    MAPPING_APPROVED = "mapping_approved"
    SNAPSHOT_CREATED = "snapshot_created"
    BATCH_MIGRATING = "batch_migrating"
    CDC_RUNNING = "cdc_running"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"

    def is_valid_transition(self, new_status: "MigrationStatus") -> bool:
        """
        Verifica se a transição de status é válida.

        Args:
            new_status: Novo status desejado

        Returns:
            True se a transição é válida
        """
        valid_transitions = {
            MigrationStatus.PENDING: [MigrationStatus.ANALYZING, MigrationStatus.FAILED],
            MigrationStatus.ANALYZING: [
                MigrationStatus.MAPPING,
                MigrationStatus.FAILED,
            ],
            MigrationStatus.MAPPING: [
                MigrationStatus.MAPPING_APPROVED,
                MigrationStatus.FAILED,
            ],
            MigrationStatus.MAPPING_APPROVED: [
                MigrationStatus.SNAPSHOT_CREATED,
                MigrationStatus.FAILED,
            ],
            MigrationStatus.SNAPSHOT_CREATED: [
                MigrationStatus.BATCH_MIGRATING,
                MigrationStatus.FAILED,
            ],
            MigrationStatus.BATCH_MIGRATING: [
                MigrationStatus.CDC_RUNNING,
                MigrationStatus.VALIDATING,
                MigrationStatus.FAILED,
                MigrationStatus.ROLLED_BACK,
            ],
            MigrationStatus.CDC_RUNNING: [
                MigrationStatus.VALIDATING,
                MigrationStatus.FAILED,
                MigrationStatus.ROLLED_BACK,
            ],
            MigrationStatus.VALIDATING: [
                MigrationStatus.COMPLETED,
                MigrationStatus.FAILED,
                MigrationStatus.ROLLED_BACK,
            ],
            MigrationStatus.COMPLETED: [MigrationStatus.ROLLED_BACK],
            MigrationStatus.FAILED: [],  # Terminal
            MigrationStatus.ROLLED_BACK: [],  # Terminal
        }

        return new_status in valid_transitions.get(self, [])


class FieldMapping(BaseModel):
    """Mapeamento de um campo legado para o novo schema."""

    source_field: str = Field(..., description="Nome do campo no sistema legado")
    target_field: str = Field(..., description="Nome do campo no novo sistema")
    data_type: str = Field(..., description="Tipo de dados do campo")
    nullable: bool = Field(default=True, description="Se o campo aceita NULL")
    is_primary_key: bool = Field(default=False, description="Se é chave primária")
    is_foreign_key: bool = Field(default=False, description="Se é chave estrangeira")
    foreign_key_reference: Optional[str] = Field(None, description="Referência da FK se aplicável")
    transform: Optional[str] = Field(None, description="Transformação a aplicar (ex: CAST_TIMESTAMP_UTC)")
    default_value: Optional[str] = Field(None, description="Valor default se aplicável")
    description: Optional[str] = Field(None, description="Descrição do campo")
    constraints: Optional[Dict[str, Any]] = Field(None, description="Restrições adicionais")

    model_config = ConfigDict(use_enum_values=True)


class TableMapping(BaseModel):
    """Mapeamento de uma tabela legada para o novo schema."""

    source_schema: str = Field(..., description="Schema da tabela legada")
    source_table: str = Field(..., description="Nome da tabela legada")
    target_table: str = Field(..., description="Nome da tabela no novo sistema")
    target_schema: str = Field(default="public", description="Schema da tabela no novo sistema")
    fields: List[FieldMapping] = Field(..., description="Mapeamento dos campos")
    source_filter: Optional[str] = Field(None, description="Filtro WHERE para extração (ex: deleted_at IS NULL)")
    target_pre_actions: Optional[List[str]] = Field(
        None, description="Ações SQL antes da migração (ex: DROP INDEX)"
    )
    target_post_actions: Optional[List[str]] = Field(
        None, description="Ações SQL após a migração (ex: CREATE INDEX)"
    )
    batch_key_field: Optional[str] = Field(
        None, description="Campo usado como chave para批次processamento"
    )
    estimated_rows: Optional[int] = Field(None, description="Estimativa de linhas")

    model_config = ConfigDict(use_enum_values=True)


class SchemaMapping(BaseModel):
    """Mapeamento completo de schema legado → novo."""

    legacy_connection_id: str = Field(..., description="ID da conexão com banco legado")
    nhm_target: str = Field(..., description="Serviço NHM de destino (ex: feature-store)")
    tables: List[TableMapping] = Field(..., description="Mapeamento das tabelas")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata adicional (estimativas, contexto de negócio, etc)",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = Field(None, description="Usuário ou serviço que criou o mapeamento")
    version: int = Field(default=1, description="Versão do mapeamento")

    model_config = ConfigDict(use_enum_values=True)


class MigrationJob(BaseModel):
    """Job de migração de dados."""

    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="ID único do job")
    schema_mapping_id: str = Field(..., description="ID do SchemaMapping a utilizar")
    status: MigrationStatus = Field(
        default=MigrationStatus.PENDING, description="Status atual do job"
    )
    batch_size: int = Field(default=1000, description="Tamanho do lote para migração")
    max_parallel_migrations: int = Field(default=5, description="Máximo de migrações em paralelo")

    # Progresso
    rows_migrated: int = Field(default=0, description="Número de linhas migradas")
    total_rows: Optional[int] = Field(None, description="Total estimado de linhas")
    rows_failed: int = Field(default=0, description="Número de linhas que falharam")
    progress_percentage: float = Field(default=0.0, ge=0.0, le=100.0, description="Progresso em %")

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = Field(None, description="Inicio da execução")
    completed_at: Optional[datetime] = Field(None, description="Fim da execução")
    failed_at: Optional[datetime] = Field(None, description="Momento da falha")
    rolled_back_at: Optional[datetime] = Field(None, description="Momento do rollback")

    # Error handling
    error_message: Optional[str] = Field(None, description="Mensagem de erro se falhou")
    rollback_reason: Optional[str] = Field(None, description="Motivo do rollback se aplicável")

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Metadata adicional do job"
    )

    model_config = ConfigDict(use_enum_values=True)

    def calculate_eta(self) -> Optional[timedelta]:
        """
        Calcula tempo estimado restante baseado no progresso.

        Returns:
            timedelta estimado ou None se não for possível calcular
        """
        if not self.started_at or self.total_rows is None or self.rows_migrated == 0:
            return None

        elapsed = datetime.now(timezone.utc) - self.started_at
        elapsed_seconds = elapsed.total_seconds()

        if elapsed_seconds == 0:
            return None

        rows_per_second = self.rows_migrated / elapsed_seconds
        if rows_per_second == 0:
            return None

        remaining_rows = self.total_rows - self.rows_migrated
        remaining_seconds = remaining_rows / rows_per_second

        return timedelta(seconds=int(remaining_seconds))

    def update_status(
        self, new_status: MigrationStatus, error_message: Optional[str] = None
    ) -> None:
        """
        Atualiza status do job com validação de transição.

        Args:
            new_status: Novo status
            error_message: Mensagem de erro (para FAILED)

        Raises:
            ValueError: Se transição for inválida
        """
        # Converter self.status (pode ser string ou enum) para MigrationStatus
        current_status = (
            MigrationStatus(self.status)
            if isinstance(self.status, str)
            else self.status
        )

        if not current_status.is_valid_transition(new_status):
            raise ValueError(
                f"Transição inválida: {current_status} → {new_status}. "
                f"Use force=True para forçar."
            )

        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)

        if new_status == MigrationStatus.ANALYZING and self.started_at is None:
            self.started_at = datetime.now(timezone.utc)
        elif new_status == MigrationStatus.COMPLETED:
            self.completed_at = datetime.now(timezone.utc)
            self.progress_percentage = 100.0
        elif new_status == MigrationStatus.FAILED:
            self.failed_at = datetime.now(timezone.utc)
            self.error_message = error_message
        elif new_status == MigrationStatus.ROLLED_BACK:
            self.rolled_back_at = datetime.now(timezone.utc)

    def update_progress(self, rows_migrated: int, total_rows: Optional[int] = None) -> None:
        """
        Atualiza progresso do job.

        Args:
            rows_migrated: Número de linhas migradas
            total_rows: Total de linhas (opcional, para atualizar estimativa)
        """
        self.rows_migrated = rows_migrated
        if total_rows is not None:
            self.total_rows = total_rows

        if self.total_rows and self.total_rows > 0:
            self.progress_percentage = (self.rows_migrated / self.total_rows) * 100.0

        self.updated_at = datetime.now(timezone.utc)
