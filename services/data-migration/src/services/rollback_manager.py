"""
Rollback Manager para Data Migration Service.

Implementa criação de snapshots e rollback automático de migrações falhadas.
Suporta estratégias S3 e shadow tables.
"""

import asyncio
import gzip
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog
import tempfile

from src.config.settings import get_settings
from src.db.postgresql import get_postgresql_client
from src.models.migration import TableMapping

logger = structlog.get_logger()


class RollbackStatus(str, Enum):
    """Status de um snapshot/rollback."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CLEANED = "cleaned"


@dataclass
class RollbackStatistics:
    """Estatísticas de uma operação de rollback."""

    tables_processed: int = 0
    rows_restored: int = 0
    tables_failed: int = 0
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)

    def success_rate(self) -> float:
        """Calcula taxa de sucesso."""
        total = self.tables_processed + self.tables_failed
        if total == 0:
            return 1.0
        # Taxa baseada apenas nas tabelas que foram processadas (sucesso / total)
        return self.tables_processed / total if total > 0 else 0.0


@dataclass
class RollbackSnapshot:
    """Representa um snapshot de dados para rollback."""

    snapshot_id: str
    migration_job_id: str
    tables: List[str]
    created_at: datetime
    storage_location: str
    storage_type: str = "s3"  # 's3' ou 'shadow'
    status: RollbackStatus = RollbackStatus.PENDING
    row_counts: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "snapshot_id": self.snapshot_id,
            "migration_job_id": self.migration_job_id,
            "tables": self.tables,
            "created_at": self.created_at.isoformat(),
            "storage_location": self.storage_location,
            "storage_type": self.storage_type,
            "status": self.status.value,
            "row_counts": self.row_counts,
            "metadata": self.metadata,
        }


class RollbackManager:
    """
    Gerenciador de rollback para migrações de dados.

    Oferece duas estratégias de rollback:
    - S3: Dump de tabelas para S3 antes da migração
    - Shadow: Cria tabelas "_shadow" e restaura via rename

    Thread-safe: Usa locks para operações concorrentes.
    """

    def __init__(
        self,
        timeout_seconds: Optional[int] = None,
        postgres_client=None,
    ):
        """
        Inicializa RollbackManager.

        Args:
            timeout_seconds: Timeout para operações de rollback
            postgres_client: Cliente PostgreSQL (para injeção de dependência)
        """
        settings = get_settings()
        self._timeout = timeout_seconds or settings.rollback_timeout_seconds
        self._bucket = settings.s3_bucket
        self._snapshots: Dict[str, RollbackSnapshot] = {}
        self._snapshots_lock = asyncio.Lock()  # BUG-H-003: proteção concorrência
        self._postgres = postgres_client
        self._s3: Optional[Any] = None

    async def _get_postgres(self):
        """Obtém ou cria cliente PostgreSQL."""
        if self._postgres is None:
            self._postgres = get_postgresql_client()
            if not await self._postgres.is_connected():
                await self._postgres.connect()
        return self._postgres

    async def _get_s3_client(self):
        """Obtém ou cria cliente S3/MinIO."""
        if self._s3 is not None:
            return self._s3

        settings = get_settings()

        try:
            # Tentar usar MinIO (cliente nativo mais rápido)
            from minio import Minio

            client = Minio(
                settings.s3_endpoint.replace("http://", "").replace("https://", ""),
                access_key=settings.s3_access_key,
                secret_key=settings.s3_secret_key,
                secure=settings.s3_use_ssl,
            )
            self._s3 = client
            return client
        except ImportError:
            # Fallback para boto3
            import boto3
            from botocore.client import Config

            endpoint_url = settings.s3_endpoint
            self._s3 = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                config=Config(signature_version="s3v4"),
                use_ssl=settings.s3_use_ssl,
            )
            return self._s3

    async def create_snapshot(
        self,
        migration_job_id: str,
        table_mappings: List[TableMapping],
        strategy: str = "s3",
    ) -> str:
        """
        Cria snapshot dos dados antes da migração.

        Args:
            migration_job_id: ID do job de migração
            table_mappings: Lista de tabelas a serem migradas
            strategy: Estratégia de snapshot ('s3' ou 'shadow')

        Returns:
            ID do snapshot criado

        Raises:
            ValueError: Se estratégia for inválida
        """
        snapshot_id = f"snap-{uuid.uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc)

        tables_to_snapshot = [tm.source_table for tm in table_mappings]
        row_counts: Dict[str, int] = {}

        logger.info(
            "creating_snapshot",
            snapshot_id=snapshot_id,
            migration_job_id=migration_job_id,
            strategy=strategy,
            tables_count=len(tables_to_snapshot),
        )

        try:
            if strategy == "s3":
                storage_location, row_counts = await self._create_s3_snapshot(
                    snapshot_id=snapshot_id,
                    migration_job_id=migration_job_id,
                    table_mappings=table_mappings,
                )
            elif strategy == "shadow":
                storage_location, row_counts = await self._create_shadow_snapshot(
                    snapshot_id=snapshot_id,
                    migration_job_id=migration_job_id,
                    table_mappings=table_mappings,
                )
            else:
                raise ValueError(f"Estratégia de snapshot inválida: {strategy}")

            snapshot = RollbackSnapshot(
                snapshot_id=snapshot_id,
                migration_job_id=migration_job_id,
                tables=tables_to_snapshot,
                created_at=created_at,
                storage_location=storage_location,
                storage_type=strategy,
                status=RollbackStatus.COMPLETED,
                row_counts=row_counts,
            )

            # BUG-H-003: Lock para proteger acesso concorrente
            async with self._snapshots_lock:
                self._snapshots[snapshot_id] = snapshot

            logger.info(
                "snapshot_created",
                snapshot_id=snapshot_id,
                storage_location=storage_location,
                total_rows=sum(row_counts.values()),
            )

            return snapshot_id

        except Exception as e:
            logger.error(
                "snapshot_creation_failed",
                snapshot_id=snapshot_id,
                error=str(e),
                strategy=strategy,
            )
            # Tentar fallback para shadow se S3 falhar
            if strategy == "s3":
                logger.info("fallback_to_shadow_tables", snapshot_id=snapshot_id)
                return await self.create_snapshot(
                    migration_job_id=migration_job_id,
                    table_mappings=table_mappings,
                    strategy="shadow",
                )
            raise

    async def _create_s3_snapshot(
        self,
        snapshot_id: str,
        migration_job_id: str,
        table_mappings: List[TableMapping],
    ) -> tuple[str, Dict[str, int]]:
        """
        Cria snapshot armazenando dados no S3 com streaming (evita OOM).

        Args:
            snapshot_id: ID do snapshot
            migration_job_id: ID do job de migração
            table_mappings: Lista de tabelas a fazer snapshot

        Returns:
            Tupla (localização, contagem de linhas por tabela)
        """
        postgres = await self._get_postgres()
        s3_client = await self._get_s3_client()

        row_counts: Dict[str, int] = {}

        # BUG-H-003: Incluir snapshot_id no nome para evitar conflitos em snapshots concorrentes
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=f"_{snapshot_id}.json.gz",
            delete=False
        ) as tmp_file:
            tmp_path = tmp_file.name

        try:
            with gzip.open(tmp_path, "wt", encoding="utf-8") as gz_file:
                # Escrever header do JSON
                gz_file.write('{"snapshot_id":"')
                gz_file.write(snapshot_id)
                gz_file.write('","migration_job_id":"')
                gz_file.write(migration_job_id)
                gz_file.write('","created_at":"')
                gz_file.write(datetime.now(timezone.utc).isoformat())
                gz_file.write('","tables":[')

                first_table = True

                for table_mapping in table_mappings:
                    table_name = table_mapping.source_table
                    schema = table_mapping.source_schema

                    logger.debug("snapshotting_table", table=table_name, schema=schema)

                    # Obter count total
                    total_count = await postgres.get_table_count(table_name, schema=schema)
                    row_counts[table_name] = total_count

                    # Escrever início da tabela
                    if not first_table:
                        gz_file.write(",")
                    first_table = False

                    gz_file.write('{"table_name":"')
                    gz_file.write(table_name)
                    gz_file.write('","schema":"')
                    gz_file.write(schema)
                    gz_file.write('","row_count":')
                    gz_file.write(str(total_count))
                    gz_file.write(',"data":[')

                    # Extrair dados em batches com streaming
                    offset = 0
                    batch_size = 1000
                    first_row = True

                    while offset < total_count:
                        batch = await postgres.fetch_batch(
                            table_name=table_name,
                            offset=offset,
                            batch_size=batch_size,
                            schema=schema,
                        )

                        if not batch:
                            break

                        # Converter e escrever batch imediatamente
                        for row in batch:
                            if not first_row:
                                gz_file.write(",")
                            first_row = False

                            # Converter datetime para string
                            processed_row = {
                                k: v.isoformat() if isinstance(v, datetime) else v
                                for k, v in row.items()
                            }
                            gz_file.write(json.dumps(processed_row))

                        offset += len(batch)
                        # Libera memória do batch
                        del batch

                    # Fechar array de dados da tabela
                    gz_file.write("]}")

                # Fechar JSON
                gz_file.write("]}")

            # Ler arquivo comprimido e enviar para S3
            with open(tmp_path, "rb") as f:
                compressed_data = f.read()

            key = f"snapshots/{snapshot_id}.json.gz"

            try:
                # Tenta MinIO primeiro
                from io import BytesIO

                s3_client.put_object(
                    bucket_name=self._bucket,
                    key=key,
                    data=BytesIO(compressed_data),
                    length=len(compressed_data),
                    content_type="application/gzip",
                )
            except (AttributeError, TypeError):
                # Fallback para boto3
                s3_client.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=compressed_data,
                    ContentEncoding="gzip",
                )

            return f"s3://{self._bucket}/{key}", row_counts

        finally:
            # Sempre limpar arquivo temporário
            import os

            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    async def _create_shadow_snapshot(
        self,
        snapshot_id: str,
        migration_job_id: str,
        table_mappings: List[TableMapping],
    ) -> tuple[str, Dict[str, int]]:
        """
        Cria snapshot usando shadow tables.

        Args:
            snapshot_id: ID do snapshot
            migration_job_id: ID do job de migração
            table_mappings: Lista de tabelas a fazer snapshot

        Returns:
            Tupla (localização, contagem de linhas por tabela)
        """
        postgres = await self._get_postgres()

        row_counts: Dict[str, int] = {}

        for table_mapping in table_mappings:
            source_table = table_mapping.source_table
            schema = table_mapping.source_schema
            shadow_table = f"{source_table}_shadow_{snapshot_id}"

            logger.debug("creating_shadow_table", source=source_table, shadow=shadow_table)

            # Criar shadow table como cópia da original
            create_query = f"""
                CREATE TABLE {schema}.{shadow_table} AS
                SELECT * FROM {schema}.{source_table}
            """

            await postgres.execute_query(create_query)

            # Obter count
            count = await postgres.get_table_count(shadow_table, schema=schema)
            row_counts[source_table] = count

        return f"shadow://{snapshot_id}", row_counts

    async def execute_rollback(
        self,
        snapshot_id: str,
    ) -> RollbackStatistics:
        """
        Executa rollback baseado em snapshot.

        Args:
            snapshot_id: ID do snapshot para restaurar

        Returns:
            Estatísticas do rollback

        Raises:
            ValueError: Se snapshot não existe
            TimeoutError: Se operação exceder timeout
        """
        # BUG-H-003: Lock para leitura atômica do snapshot
        async with self._snapshots_lock:
            if snapshot_id not in self._snapshots:
                raise ValueError(f"Snapshot não encontrado: {snapshot_id}")
            snapshot = self._snapshots[snapshot_id]

        start_time = datetime.now(timezone.utc)

        logger.info(
            "executing_rollback",
            snapshot_id=snapshot_id,
            storage_type=snapshot.storage_type,
        )

        stats = RollbackStatistics()

        try:
            if snapshot.storage_type == "s3":
                stats = await self._rollback_from_s3(snapshot, start_time)
            elif snapshot.storage_type == "shadow":
                stats = await self._rollback_from_shadow(snapshot, start_time)
            else:
                raise ValueError(f"Tipo de storage não suportado: {snapshot.storage_type}")

            # BUG-H-003: Lock para proteção de status
            async with self._snapshots_lock:
                snapshot.status = RollbackStatus.COMPLETED

            logger.info(
                "rollback_completed",
                snapshot_id=snapshot_id,
                tables_processed=stats.tables_processed,
                rows_restored=stats.rows_restored,
                duration_seconds=stats.duration_seconds,
            )

        except asyncio.TimeoutError:
            # BUG-H-003: Lock para proteção de status
            async with self._snapshots_lock:
                snapshot.status = RollbackStatus.FAILED
            raise TimeoutError(f"Rollback excedeu timeout de {self._timeout} segundos")
        except Exception as e:
            # BUG-H-003: Lock para proteção de status
            async with self._snapshots_lock:
                snapshot.status = RollbackStatus.FAILED
            logger.error("rollback_failed", snapshot_id=snapshot_id, error=str(e))
            raise

        return stats

    async def _rollback_from_s3(
        self,
        snapshot: RollbackSnapshot,
        start_time: datetime,
    ) -> RollbackStatistics:
        """Restaura dados de snapshot S3 com streaming (evita OOM)."""
        postgres = await self._get_postgres()
        s3_client = await self._get_s3_client()

        stats = RollbackStatistics()

        # Obter dados do S3
        key = snapshot.storage_location.replace(f"s3://{self._bucket}/", "")

        try:
            # Tenta MinIO primeiro (get_object retorna objeto com read())
            response = s3_client.get_object(self._bucket, key)
            if hasattr(response, "read"):
                compressed_data = response.read()
            elif isinstance(response, dict) and "Body" in response:
                # Formato boto3 (dict com Body)
                body = response["Body"]
                if hasattr(body, "read"):
                    compressed_data = body.read()
                else:
                    compressed_data = body
            else:
                compressed_data = response
        except (AttributeError, TypeError):
            # Fallback para boto3 (get_object retorna dict)
            response = s3_client.get_object(Bucket=self._bucket, Key=key)
            body = response.get("Body")
            if hasattr(body, "read"):
                compressed_data = body.read()
            else:
                compressed_data = body

        # Usar arquivo temporário para processamento streaming
        tmp_path = None
        try:
            # Salvar dados comprimidos em arquivo temporário
            with tempfile.NamedTemporaryFile(mode="wb", suffix=".json.gz", delete=False) as tmp_file:
                tmp_path = tmp_file.name
                tmp_file.write(compressed_data)

            # Liberar memória dos dados comprimidos
            del compressed_data

            # Processar cada tabela separadamente com streaming
            tables_count = 0
            with gzip.open(tmp_path, "rt", encoding="utf-8") as gz_file:
                # Ler arquivo JSON em streaming
                tables_data = self._extract_tables_from_json(gz_file)

                for table_name, schema, rows in tables_data:
                    tables_count += 1
                    try:
                        await asyncio.wait_for(
                            self._restore_table_data(postgres, table_name, schema, rows),
                            timeout=self._timeout / max(tables_count, 1),
                        )
                        stats.tables_processed += 1
                        stats.rows_restored += len(rows)
                    except asyncio.TimeoutError:
                        stats.tables_failed += 1
                        stats.errors.append(f"Timeout restaurando {table_name}")
                    except Exception as e:
                        stats.tables_failed += 1
                        stats.errors.append(f"Erro em {table_name}: {str(e)}")

        finally:
            # Sempre limpar arquivo temporário
            if tmp_path:
                import os

                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        stats.duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
        return stats

    def _extract_tables_from_json(self, gz_file):
        """
        Extrai tabelas de arquivo JSON streaming.

        Yield tuplas (table_name, schema, rows_list) para cada tabela.
        Processa linha por linha para evitar carregar tudo na memória.
        """
        import json

        # Encontrar início das tables
        char = gz_file.read(1)
        while char and char != "[":
            char = gz_file.read(1)

        if not char:
            return

        # Processar cada tabela
        depth = 1
        buffer = ""
        in_string = False
        escape = False

        while True:
            char = gz_file.read(1)
            if not char:
                break

            if escape:
                buffer += char
                escape = False
                continue

            if char == "\\":
                buffer += char
                escape = True
                continue

            if char == '"' and not escape:
                in_string = not in_string
                buffer += char
                continue

            if not in_string:
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1

            buffer += char

            # Quando fechamos um objeto de tabela, processamos
            if depth == 1 and char == "]":
                # Fim do array de tabelas
                break
            elif depth == 1 and char == ",":
                # Próxima tabela
                table_data = json.loads(buffer[:-1])  # Remove vírgula
                rows = table_data.get("data", [])
                yield (
                    table_data.get("table_name", ""),
                    table_data.get("schema", "public"),
                    rows,
                )
                buffer = ""

        # Processar última tabela
        if buffer.strip():
            table_data = json.loads(buffer.strip("] "))
            rows = table_data.get("data", [])
            yield (
                table_data.get("table_name", ""),
                table_data.get("schema", "public"),
                rows,
            )

    async def _rollback_from_shadow(
        self,
        snapshot: RollbackSnapshot,
        start_time: datetime,
    ) -> RollbackStatistics:
        """Restaura dados de shadow tables."""
        postgres = await self._get_postgres()

        stats = RollbackStatistics()

        for table_name in snapshot.tables:
            schema = "public"  # Default
            shadow_table = f"{table_name}_shadow_{snapshot.snapshot_id}"

            try:
                await asyncio.wait_for(
                    self._restore_from_shadow_table(postgres, table_name, schema, shadow_table),
                    timeout=self._timeout / len(snapshot.tables),
                )
                stats.tables_processed += 1
            except asyncio.TimeoutError:
                stats.tables_failed += 1
                stats.errors.append(f"Timeout restaurando {table_name}")
            except Exception as e:
                stats.tables_failed += 1
                stats.errors.append(f"Erro em {table_name}: {str(e)}")

        stats.duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
        return stats

    async def _restore_table_data(
        self,
        postgres,
        table_name: str,
        schema: str,
        rows: List[Dict[str, Any]],
    ) -> None:
        """Restaura dados em uma tabela."""
        # Deletar dados existentes
        await postgres.execute_query(
            f"DELETE FROM {schema}.{table_name}",
            fetch="none",
        )

        # Inserir dados do snapshot
        if rows:
            # Obter colunas e valores
            columns = list(rows[0].keys())
            placeholders = ", ".join([f"${i + 1}" for i in range(len(columns))])
            col_names = ", ".join(columns)

            insert_query = f"""
                INSERT INTO {schema}.{table_name} ({col_names})
                VALUES ({placeholders})
            """

            for row in rows:
                values = tuple(row[col] for col in columns)
                await postgres.execute_query(insert_query, params=values, fetch="none")

    async def _restore_from_shadow_table(
        self,
        postgres,
        table_name: str,
        schema: str,
        shadow_table: str,
    ) -> None:
        """Restaura dados de shadow table."""
        # Deletar dados existentes
        await postgres.execute_query(
            f"DELETE FROM {schema}.{table_name}",
            fetch="none",
        )

        # Inserir dados da shadow table
        await postgres.execute_query(
            f"""
            INSERT INTO {schema}.{table_name}
            SELECT * FROM {schema}.{shadow_table}
            """,
            fetch="none",
        )

    async def cleanup_snapshot(self, snapshot_id: str) -> bool:
        """
        Limpa snapshot após migração bem-sucedida.

        Args:
            snapshot_id: ID do snapshot a limpar

        Returns:
            True se limpeza foi bem-sucedida
        """
        # BUG-H-003: Lock para leitura atômica do snapshot
        async with self._snapshots_lock:
            if snapshot_id not in self._snapshots:
                logger.warning("snapshot_not_found_for_cleanup", snapshot_id=snapshot_id)
                return False
            snapshot = self._snapshots[snapshot_id]

        logger.info(
            "cleaning_snapshot", snapshot_id=snapshot_id, storage_type=snapshot.storage_type
        )

        try:
            if snapshot.storage_type == "s3":
                await self._cleanup_s3_snapshot(snapshot)
            elif snapshot.storage_type == "shadow":
                await self._cleanup_shadow_snapshot(snapshot)

            # BUG-H-003: Lock para proteção de status e deleção
            async with self._snapshots_lock:
                snapshot.status = RollbackStatus.CLEANED
                # Recarregar do dict para garantir que ainda existe (double-check)
                if snapshot_id in self._snapshots:
                    del self._snapshots[snapshot_id]

            logger.info("snapshot_cleaned", snapshot_id=snapshot_id)
            return True

        except Exception as e:
            logger.error("snapshot_cleanup_failed", snapshot_id=snapshot_id, error=str(e))
            return False

    async def _cleanup_s3_snapshot(self, snapshot: RollbackSnapshot) -> None:
        """Limpa snapshot do S3."""
        s3_client = await self._get_s3_client()
        key = snapshot.storage_location.replace(f"s3://{self._bucket}/", "")

        try:
            # Tenta MinIO primeiro
            s3_client.remove_object(self._bucket, key)
        except (AttributeError, TypeError):
            # Fallback para boto3
            s3_client.delete_object(Bucket=self._bucket, Key=key)

    async def _cleanup_shadow_snapshot(self, snapshot: RollbackSnapshot) -> None:
        """Limpa shadow tables."""
        postgres = await self._get_postgres()

        for table_name in snapshot.tables:
            schema = "public"  # Default
            shadow_table = f"{table_name}_shadow_{snapshot.snapshot_id}"

            try:
                await postgres.execute_query(
                    f"DROP TABLE IF EXISTS {schema}.{shadow_table}",
                    fetch="none",
                )
            except Exception as e:
                logger.warning(
                    "failed_to_drop_shadow_table",
                    table=shadow_table,
                    error=str(e),
                )

    async def cleanup_old_snapshots(self, older_than_days: int = 7) -> int:
        """
        Limpa snapshots mais antigos que X dias.

        Args:
            older_than_days: Limite de dias para considerar snapshot antigo

        Returns:
            Número de snapshots limpos
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        cleaned_count = 0

        # BUG-H-003: Lock para leitura atômica da lista
        async with self._snapshots_lock:
            to_remove = [
                sid for sid, snap in self._snapshots.items()
                if snap.created_at < cutoff_time
            ]

        for snapshot_id in to_remove:
            if await self.cleanup_snapshot(snapshot_id):
                cleaned_count += 1

        logger.info("old_snapshots_cleaned", count=cleaned_count, older_than_days=older_than_days)
        return cleaned_count

    async def get_rollback_status(self, snapshot_id: str) -> Dict[str, Any]:
        """
        Retorna status de um snapshot/rollback.

        Args:
            snapshot_id: ID do snapshot

        Returns:
            Dicionário com informações do snapshot
        """
        # BUG-H-003: Lock para leitura atômica
        async with self._snapshots_lock:
            if snapshot_id not in self._snapshots:
                return {
                    "exists": False,
                    "snapshot_id": snapshot_id,
                }

            snapshot = self._snapshots[snapshot_id]
            # Copiar dados fora do lock
            result = {
                "exists": True,
                **snapshot.to_dict(),
            }
        return result

    async def list_snapshots(
        self,
        migration_job_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lista snapshots disponíveis.

        Args:
            migration_job_id: Filtrar por job de migração (opcional)

        Returns:
            Lista de snapshots
        """
        # BUG-H-003: Lock para leitura atômica
        async with self._snapshots_lock:
            snapshots = list(self._snapshots.values())

        if migration_job_id:
            snapshots = [s for s in snapshots if s.migration_job_id == migration_job_id]

        return [s.to_dict() for s in snapshots]

    @classmethod
    def _reset_for_tests(cls) -> None:
        """Reseta singleton para testes."""
        global _rollback_manager
        _rollback_manager = None


_rollback_manager: Optional[RollbackManager] = None


def get_rollback_manager() -> RollbackManager:
    """
    Retorna singleton do RollbackManager.

    Returns:
        Instância de RollbackManager
    """
    global _rollback_manager
    if _rollback_manager is None:
        _rollback_manager = RollbackManager()
    return _rollback_manager
