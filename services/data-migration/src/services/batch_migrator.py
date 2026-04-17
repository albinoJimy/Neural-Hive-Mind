"""
Batch Migrator Service para Data Migration System.

Implementa migração de dados históricos do PostgreSQL legado em batches,
aplicando transformações do SchemaMapping e reportando progresso via Kafka.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from src.models.migration import SchemaMapping, TableMapping

__all__ = [
    "BatchMigrator",
    "BatchMigratorError",
    "MigrationProgress",
    "get_batch_migrator",
]

logger = structlog.get_logger()


class BatchMigratorError(Exception):
    """Exceção base para erros do Batch Migrator."""


@dataclass
class MigrationProgress:
    """
    Progresso de migração de uma tabela.

    Attributes:
        job_id: ID do job de migração
        table: Nome da tabela sendo migrada
        total_rows: Total estimado de linhas
        rows_migrated: Linhas já migradas
        rows_failed: Linhas que falharam
        batches_processed: Número de batches processados
        status: Status da migração
        started_at: Timestamp de início
        last_batch_at: Timestamp do último batch
        progress_percentage: Percentual de progresso
    """

    job_id: str
    table: str
    total_rows: int
    rows_migrated: int = 0
    rows_failed: int = 0
    batches_processed: int = 0
    status: str = "pending"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_batch_at: Optional[datetime] = None
    progress_percentage: float = 0.0

    def update_migrated(self, count: int) -> None:
        """
        Atualiza contador de linhas migradas.

        Args:
            count: Número de linhas migradas no batch
        """
        self.rows_migrated += count
        self.batches_processed += 1
        self.last_batch_at = datetime.now(timezone.utc)
        if self.total_rows > 0:
            self.progress_percentage = (self.rows_migrated / self.total_rows) * 100.0

    def update_failed(self, count: int) -> None:
        """
        Atualiza contador de linhas falhadas.

        Args:
            count: Número de linhas que falharam no batch
        """
        self.rows_failed += count

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "job_id": self.job_id,
            "table": self.table,
            "total_rows": self.total_rows,
            "rows_migrated": self.rows_migrated,
            "rows_failed": self.rows_failed,
            "batches_processed": self.batches_processed,
            "status": self.status,
            "progress_percentage": round(self.progress_percentage, 2),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_batch_at": self.last_batch_at.isoformat() if self.last_batch_at else None,
        }


class BatchMigrator:
    """
    Migrador de dados em batch.

    Migra dados históricos do banco legado em batches configuráveis,
    aplicando transformações definidas no SchemaMapping e reportando
    progresso via eventos Kafka.
    """

    def __init__(
        self,
        job_id: str,
        schema_mapping_id: str,
        batch_size: int = 1000,
        max_parallel_tables: int = 1,
    ):
        """
        Inicializa Batch Migrator.

        Args:
            job_id: ID do job de migração
            schema_mapping_id: ID do mapeamento de schema a usar
            batch_size: Tamanho do batch para migração (default: 1000)
            max_parallel_tables: Máximo de tabelas em paralelo
        """
        self.job_id = job_id
        self.schema_mapping_id = schema_mapping_id
        self.batch_size = batch_size
        self.max_parallel_tables = max_parallel_tables

        # Estado de controle
        self._paused: bool = False
        self._running: bool = False
        self._stopped: bool = False

        # Progresso por tabela
        self._progress: Dict[str, MigrationProgress] = {}

        # Estatísticas globais
        self._total_migrated: int = 0
        self._total_failed: int = 0
        self._tables_completed: List[str] = []

    async def run_batch_migration(
        self,
        legacy_client: Any,
        target_client: Any,
        schema_mapping: SchemaMapping,
        kafka_producer: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Executa migração batch completa.

        Migra todas as tabelas definidas no SchemaMapping, processando
        em batches e reportando progresso via Kafka.

        Args:
            legacy_client: Cliente do banco legado (PostgreSQL)
            target_client: Cliente do banco alvo (MongoDB ou moderno)
            schema_mapping: Mapeamento de schema a aplicar
            kafka_producer: Producer Kafka para eventos (opcional)

        Returns:
            Dicionário com estatísticas da migração

        Raises:
            BatchMigratorError: Se ocorrer erro fatal durante migração
        """
        if self._running:
            raise BatchMigratorError("Migração já está em andamento")

        self._running = True
        self._stopped = False
        self._paused = False

        logger.info(
            "batch_migration_started",
            job_id=self.job_id,
            tables_count=len(schema_mapping.tables),
            batch_size=self.batch_size,
        )

        # Emitir evento de início
        if kafka_producer:
            await self._emit_progress_event(
                kafka_producer=kafka_producer,
                event_type="migration.batch_started",
                progress=None,
                extra_data={
                    "tables": [t.target_table for t in schema_mapping.tables],
                    "batch_size": self.batch_size,
                },
            )

        try:
            # Processar cada tabela sequencialmente (ou em paralelo se configurado)
            if self.max_parallel_tables > 1:
                # Migração paralela de tabelas
                tasks = [
                    self._migrate_table(
                        legacy_client=legacy_client,
                        target_client=target_client,
                        table_mapping=table,
                        kafka_producer=kafka_producer,
                    )
                    for table in schema_mapping.tables
                ]
                await asyncio.gather(*tasks, return_exceptions=True)
            else:
                # Migração sequencial de tabelas
                for table_mapping in schema_mapping.tables:
                    await self._migrate_table(
                        legacy_client=legacy_client,
                        target_client=target_client,
                        table_mapping=table_mapping,
                        kafka_producer=kafka_producer,
                    )

                    # Verificar se foi pausado/parado entre tabelas
                    if self._stopped:
                        break

            # Emitir evento de conclusão
            if kafka_producer:
                await self._emit_progress_event(
                    kafka_producer=kafka_producer,
                    event_type="migration.batch_completed",
                    progress=None,
                    extra_data={
                        "total_migrated": self._total_migrated,
                        "total_failed": self._total_failed,
                        "tables_processed": len(self._tables_completed),
                    },
                )

            logger.info(
                "batch_migration_completed",
                job_id=self.job_id,
                total_migrated=self._total_migrated,
                total_failed=self._total_failed,
            )

            return {
                "job_id": self.job_id,
                "total_migrated": self._total_migrated,
                "total_failed": self._total_failed,
                "batches_processed": sum(p.batches_processed for p in self._progress.values()),
                "tables_processed": len(self._tables_completed),
                "paused": self._paused,
            }

        except Exception as e:
            logger.error(
                "batch_migration_failed",
                job_id=self.job_id,
                error=str(e),
            )

            # Emitir evento de falha
            if kafka_producer:
                await self._emit_progress_event(
                    kafka_producer=kafka_producer,
                    event_type="migration.batch_failed",
                    progress=None,
                    extra_data={"error": str(e)},
                )

            raise BatchMigratorError(f"Erro durante migração: {e}") from e
        finally:
            self._running = False

    async def _migrate_table(
        self,
        legacy_client: Any,
        target_client: Any,
        table_mapping: TableMapping,
        kafka_producer: Optional[Any] = None,
    ) -> None:
        """
        Migra uma tabela específica em batches.

        Args:
            legacy_client: Cliente do banco legado
            target_client: Cliente do banco alvo
            table_mapping: Mapeamento da tabela
            kafka_producer: Producer Kafka para eventos
        """
        table_name = table_mapping.target_table
        source_schema = table_mapping.source_schema
        source_table = table_mapping.source_table

        # Obter total estimado de linhas
        estimated_rows = table_mapping.estimated_rows
        if estimated_rows is None and hasattr(legacy_client, "get_table_count"):
            try:
                estimated_rows = await legacy_client.get_table_count(
                    table_name=source_table,
                    schema=source_schema,
                    where=table_mapping.source_filter,
                )
            except Exception as e:
                logger.warning(
                    "table_count_failed",
                    table=source_table,
                    error=str(e),
                )
                estimated_rows = 0

        # Inicializar progresso
        progress = MigrationProgress(
            job_id=self.job_id,
            table=table_name,
            total_rows=estimated_rows or 0,
        )
        progress.status = "migrating"
        self._progress[table_name] = progress

        logger.info(
            "table_migration_started",
            job_id=self.job_id,
            table=table_name,
            estimated_rows=estimated_rows,
        )

        offset = 0
        batch_number = 0

        try:
            # Executar pre-actions se definidas
            if table_mapping.target_pre_actions:
                await self._execute_pre_actions(
                    target_client=target_client,
                    table_mapping=table_mapping,
                )

            # Loop de batches
            while True:
                # Verificar pausa/parada
                if self._paused:
                    logger.info(
                        "table_migration_paused",
                        job_id=self.job_id,
                        table=table_name,
                        offset=offset,
                    )
                    progress.status = "paused"
                    await self._emit_progress_event(
                        kafka_producer=kafka_producer,
                        event_type="migration.batch_paused",
                        progress=progress,
                    )
                    break

                if self._stopped:
                    logger.info(
                        "table_migration_stopped",
                        job_id=self.job_id,
                        table=table_name,
                        offset=offset,
                    )
                    progress.status = "stopped"
                    break

                # Buscar batch do legado
                try:
                    batch = await legacy_client.fetch_batch(
                        table_name=source_table,
                        offset=offset,
                        batch_size=self.batch_size,
                        schema=source_schema,
                        where=table_mapping.source_filter,
                        order_by=table_mapping.batch_key_field,
                    )
                except Exception as e:
                    logger.error(
                        "batch_fetch_failed",
                        table=source_table,
                        offset=offset,
                        error=str(e),
                    )
                    raise

                # Se batch vazio, migração concluída
                if not batch:
                    progress.status = "completed"
                    self._tables_completed.append(table_name)
                    logger.info(
                        "table_migration_completed",
                        job_id=self.job_id,
                        table=table_name,
                        total_migrated=progress.rows_migrated,
                    )
                    break

                batch_number += 1

                # Aplicar transformações
                try:
                    transformed = await self._apply_transformations(
                        source_data=batch,
                        table_mapping=table_mapping,
                    )
                except Exception as e:
                    logger.error(
                        "batch_transform_failed",
                        table=source_table,
                        batch_number=batch_number,
                        error=str(e),
                    )
                    # Contar como falhadas
                    progress.update_failed(len(batch))
                    self._total_failed += len(batch)
                    offset += len(batch)
                    continue

                # Inserir no alvo
                try:
                    if hasattr(target_client, "insert_batch"):
                        await target_client.insert_batch(
                            table=table_name,
                            data=transformed,
                        )
                    elif hasattr(target_client, "insert_many"):
                        # MongoDB style
                        collection = target_client.database[table_name]
                        await collection.insert_many(transformed)
                    else:
                        raise BatchMigratorError(
                            "Target client não suporta insert_batch ou insert_many"
                        )

                    # Atualizar progresso
                    progress.update_migrated(len(transformed))
                    self._total_migrated += len(transformed)

                except Exception as e:
                    logger.error(
                        "batch_insert_failed",
                        table=table_name,
                        batch_number=batch_number,
                        error=str(e),
                    )
                    # Contar como falhadas
                    progress.update_failed(len(transformed))
                    self._total_failed += len(transformed)

                # Emitir evento de progresso
                if kafka_producer:
                    await self._emit_progress_event(
                        kafka_producer=kafka_producer,
                        event_type="migration.batch_progress",
                        progress=progress,
                        extra_data={
                            "batch_number": batch_number,
                            "batch_size": len(batch),
                            "offset": offset,
                        },
                    )

                offset += len(batch)

            # Executar post-actions se definidas
            if progress.status == "completed" and table_mapping.target_post_actions:
                await self._execute_post_actions(
                    target_client=target_client,
                    table_mapping=table_mapping,
                )

        except Exception as e:
            progress.status = "failed"
            logger.error(
                "table_migration_error",
                job_id=self.job_id,
                table=table_name,
                error=str(e),
            )
            raise

    async def _apply_transformations(
        self,
        source_data: List[Dict[str, Any]],
        table_mapping: TableMapping,
    ) -> List[Dict[str, Any]]:
        """
        Aplica transformações baseadas no TableMapping.

        Args:
            source_data: Dados originais do batch
            table_mapping: Mapeamento da tabela

        Returns:
            Lista de registros transformados
        """
        transformed_data = []

        for source_row in source_data:
            transformed_row = {}

            for field_mapping in table_mapping.fields:
                source_value = source_row.get(field_mapping.source_field)

                # Aplicar valor default se ausente
                if source_value is None and field_mapping.default_value is not None:
                    source_value = self._parse_default_value(field_mapping.default_value)

                # Aplicar transformação se especificada
                if source_value is not None and field_mapping.transform:
                    source_value = await self._apply_field_transform(
                        value=source_value,
                        transform=field_mapping.transform,
                        data_type=field_mapping.data_type,
                    )

                transformed_row[field_mapping.target_field] = source_value

            transformed_data.append(transformed_row)

        return transformed_data

    async def _apply_field_transform(
        self,
        value: Any,
        transform: str,
        data_type: str,
    ) -> Any:
        """
        Aplica transformação em um campo.

        Args:
            value: Valor original
            transform: Nome da transformação
            data_type: Tipo de dados alvo

        Returns:
            Valor transformado
        """
        if transform == "CAST_TIMESTAMP_UTC":
            return await self._cast_timestamp_utc(value)

        elif transform == "CAST_TO_UUID":
            return str(value)

        elif transform == "CAST_TO_INT":
            return int(value) if value is not None else None

        elif transform == "CAST_TO_FLOAT":
            return float(value) if value is not None else None

        elif transform == "PARSE_JSON":
            import json

            if isinstance(value, str):
                return json.loads(value)
            return value

        elif transform == "UPPERCASE":
            return str(value).upper() if value is not None else None

        elif transform == "LOWERCASE":
            return str(value).lower() if value is not None else None

        # Sem transformação reconhecida, retornar original
        return value

    async def _cast_timestamp_utc(self, value: Any) -> Any:
        """
        Converte valor para timestamp UTC.

        Args:
            value: Valor a converter

        Returns:
            Datetime UTC ou valor original se falhar
        """
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)

        if isinstance(value, str):
            # Tentar parse de formatos comuns
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%d",
            ):
                try:
                    parsed = datetime.strptime(value, fmt)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return parsed
                except ValueError:
                    continue

        # Retornar original se não conseguir converter
        return value

    def _parse_default_value(self, value: str) -> Any:
        """
        Faz parse de valor default.

        Args:
            value: String de valor default

        Returns:
            Valor parseado
        """
        import json

        # Valores especiais
        if value.lower() == "null":
            return None
        elif value.lower() == "true":
            return True
        elif value.lower() == "false":
            return False

        # Tentar números
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # Tentar JSON
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            pass

        # Retornar como string
        return value

    async def _execute_pre_actions(
        self,
        target_client: Any,
        table_mapping: TableMapping,
    ) -> None:
        """
        Executa ações SQL antes da migração.

        Args:
            target_client: Cliente do banco alvo
            table_mapping: Mapeamento da tabela
        """
        if not table_mapping.target_pre_actions:
            return

        logger.info(
            "executing_pre_actions",
            table=table_mapping.target_table,
            actions_count=len(table_mapping.target_pre_actions),
        )

        for action in table_mapping.target_pre_actions:
            try:
                if hasattr(target_client, "execute"):
                    await target_client.execute(action)
                elif hasattr(target_client, "database"):
                    # MongoDB - executar comando
                    await target_client.database.command(action)
            except Exception as e:
                logger.warning(
                    "pre_action_failed",
                    action=action[:100],
                    error=str(e),
                )

    async def _execute_post_actions(
        self,
        target_client: Any,
        table_mapping: TableMapping,
    ) -> None:
        """
        Executa ações SQL após a migração.

        Args:
            target_client: Cliente do banco alvo
            table_mapping: Mapeamento da tabela
        """
        if not table_mapping.target_post_actions:
            return

        logger.info(
            "executing_post_actions",
            table=table_mapping.target_table,
            actions_count=len(table_mapping.target_post_actions),
        )

        for action in table_mapping.target_post_actions:
            try:
                if hasattr(target_client, "execute"):
                    await target_client.execute(action)
                elif hasattr(target_client, "database"):
                    # MongoDB - executar comando
                    await target_client.database.command(action)
            except Exception as e:
                logger.warning(
                    "post_action_failed",
                    action=action[:100],
                    error=str(e),
                )

    async def _emit_progress_event(
        self,
        kafka_producer: Any,
        event_type: str,
        progress: Optional[MigrationProgress],
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Emite evento de progresso para o Kafka.

        Args:
            kafka_producer: Producer Kafka
            event_type: Tipo do evento
            progress: Objeto de progresso (opcional)
            extra_data: Dados extras para o evento
        """
        if not kafka_producer:
            return

        event_data = {
            "job_id": self.job_id,
            "schema_mapping_id": self.schema_mapping_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
        }

        if progress:
            event_data.update(progress.to_dict())

        if extra_data:
            event_data.update(extra_data)

        try:
            if hasattr(kafka_producer, "produce"):
                await kafka_producer.produce(
                    topic="migration.progress",
                    value=event_data,
                    key=self.job_id,
                )
            elif hasattr(kafka_producer, "send_and_wait"):
                # Confluent Kafka style
                await kafka_producer.send_and_wait(
                    topic="migration.progress",
                    value=event_data,
                    key=self.job_id,
                )
        except Exception as e:
            # Não falhar migração por erro no Kafka
            logger.warning(
                "kafka_event_failed",
                event_type=event_type,
                error=str(e),
            )

    def get_migration_progress(self) -> Dict[str, Any]:
        """
        Retorna progresso atual da migração.

        Returns:
            Dicionário com informações de progresso
        """
        return {
            "job_id": self.job_id,
            "total_migrated": self._total_migrated,
            "total_failed": self._total_failed,
            "tables_completed": self._tables_completed.copy(),
            "running": self._running,
            "paused": self._paused,
            "tables_progress": {
                table: progress.to_dict() for table, progress in self._progress.items()
            },
            "status": self._get_status(),
        }

    def _get_status(self) -> str:
        """Retorna status atual da migração."""
        if self._stopped:
            return "stopped"
        if self._paused:
            return "paused"
        if self._running:
            return "running"
        return "idle"

    def pause_migration(self) -> None:
        """Pausa a migração entre batches."""
        logger.info("migration_paused", job_id=self.job_id)
        self._paused = True

    def resume_migration(self) -> None:
        """Retoma migração pausada."""
        logger.info("migration_resumed", job_id=self.job_id)
        self._paused = False

    def stop_migration(self) -> None:
        """Para a migração completamente."""
        logger.info("migration_stopped", job_id=self.job_id)
        self._stopped = True
        self._paused = False

    def is_paused(self) -> bool:
        """Verifica se migração está pausada."""
        return self._paused

    def is_running(self) -> bool:
        """Verifica se migração está em andamento."""
        return self._running

    def is_stopped(self) -> bool:
        """Verifica se migração foi parada."""
        return self._stopped


# Singleton instance (por job_id)
_batch_migrators: Dict[str, BatchMigrator] = {}


def get_batch_migrator(
    job_id: str,
    schema_mapping_id: str,
    batch_size: int = 1000,
) -> BatchMigrator:
    """
    Retorna instância do Batch Migrator (singleton por job_id).

    Args:
        job_id: ID do job de migração
        schema_mapping_id: ID do mapeamento de schema
        batch_size: Tamanho do batch

    Returns:
        Instância de BatchMigrator
    """
    global _batch_migrators

    if job_id not in _batch_migrators:
        _batch_migrators[job_id] = BatchMigrator(
            job_id=job_id,
            schema_mapping_id=schema_mapping_id,
            batch_size=batch_size,
        )

    return _batch_migrators[job_id]


def clear_batch_migrator(job_id: str) -> None:
    """
    Remove migrator da cache (para testes ou cleanup).

    Args:
        job_id: ID do job a remover
    """
    global _batch_migrators
    _batch_migrators.pop(job_id, None)
