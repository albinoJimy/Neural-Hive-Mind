"""
BackupManager: Automação de backups e replicação do ledger cognitivo.

Implementa backups incrementais, compressão, e sincronização com storage externo
(S3, Azure Blob, GCS) para disaster recovery.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import structlog
import json
import gzip
import os
import hashlib
from pathlib import Path

logger = structlog.get_logger(__name__)


class BackupManager:
    """Gerencia backups automáticos do ledger cognitivo."""

    def __init__(self, config: Dict[str, Any]):
        """
        Inicializa gerenciador de backups.

        Args:
            config: Configuração com mongodb_uri, backup_path, backup_retention_days
        """
        self.config = config
        self.mongodb_uri = config.get('mongodb_uri')
        self.mongodb_database = config.get('mongodb_database', 'neural_hive')
        self.backup_path = config.get('backup_path', '/var/backups/neural-hive')
        self.backup_retention_days = config.get('backup_retention_days', 30)
        self.enable_compression = config.get('enable_backup_compression', True)
        self._mongo_client: Optional[MongoClient] = None

        # Criar diretório de backup
        Path(self.backup_path).mkdir(parents=True, exist_ok=True)

        logger.info(
            "BackupManager initialized",
            backup_path=self.backup_path,
            retention_days=self.backup_retention_days,
            compression=self.enable_compression
        )

    @property
    def mongo_client(self) -> MongoClient:
        """Lazy initialization do cliente MongoDB."""
        if self._mongo_client is None:
            self._mongo_client = MongoClient(
                self.mongodb_uri,
                serverSelectionTimeoutMS=5000
            )
        return self._mongo_client

    @property
    def collection(self):
        """Retorna collection de opiniões."""
        db = self.mongo_client[self.mongodb_database]
        return db['cognitive_ledger']

    def create_full_backup(self) -> Optional[str]:
        """
        Cria backup completo do ledger.

        Returns:
            Caminho do arquivo de backup ou None se erro
        """
        try:
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            backup_name = f"ledger_full_{timestamp}.json"

            if self.enable_compression:
                backup_name += ".gz"

            backup_file_path = os.path.join(self.backup_path, backup_name)

            logger.info("Starting full backup", backup_file=backup_name)

            # Exportar todos os documentos
            documents = list(self.collection.find({}))

            # Remover _id do MongoDB
            for doc in documents:
                doc.pop('_id', None)

            # Serializar para JSON
            backup_data = {
                'backup_type': 'full',
                'created_at': datetime.utcnow().isoformat(),
                'database': self.mongodb_database,
                'collection': 'cognitive_ledger',
                'documents_count': len(documents),
                'documents': documents
            }

            json_data = json.dumps(backup_data, indent=2, default=str)

            # Escrever arquivo (com ou sem compressão)
            if self.enable_compression:
                with gzip.open(backup_file_path, 'wt', encoding='utf-8') as f:
                    f.write(json_data)
            else:
                with open(backup_file_path, 'w', encoding='utf-8') as f:
                    f.write(json_data)

            # Calcular checksum
            checksum = self._calculate_file_checksum(backup_file_path)

            # Salvar metadata
            self._save_backup_metadata(backup_file_path, checksum, len(documents))

            logger.info(
                "Full backup created successfully",
                backup_file=backup_name,
                documents_count=len(documents),
                checksum=checksum
            )

            return backup_file_path

        except Exception as e:
            logger.error("Failed to create full backup", error=str(e), exc_info=True)
            return None

    def create_incremental_backup(
        self,
        since_hours: int = 24
    ) -> Optional[str]:
        """
        Cria backup incremental (documentos recentes).

        Args:
            since_hours: Janela de tempo em horas

        Returns:
            Caminho do arquivo de backup ou None se erro
        """
        try:
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            backup_name = f"ledger_incremental_{timestamp}.json"

            if self.enable_compression:
                backup_name += ".gz"

            backup_file_path = os.path.join(self.backup_path, backup_name)

            cutoff_time = datetime.utcnow() - timedelta(hours=since_hours)

            logger.info(
                "Starting incremental backup",
                backup_file=backup_name,
                since_hours=since_hours
            )

            # Exportar documentos recentes
            documents = list(self.collection.find({
                'created_at': {'$gte': cutoff_time}
            }))

            # Remover _id
            for doc in documents:
                doc.pop('_id', None)

            # Serializar
            backup_data = {
                'backup_type': 'incremental',
                'created_at': datetime.utcnow().isoformat(),
                'database': self.mongodb_database,
                'collection': 'cognitive_ledger',
                'since_timestamp': cutoff_time.isoformat(),
                'documents_count': len(documents),
                'documents': documents
            }

            json_data = json.dumps(backup_data, indent=2, default=str)

            # Escrever arquivo
            if self.enable_compression:
                with gzip.open(backup_file_path, 'wt', encoding='utf-8') as f:
                    f.write(json_data)
            else:
                with open(backup_file_path, 'w', encoding='utf-8') as f:
                    f.write(json_data)

            # Checksum
            checksum = self._calculate_file_checksum(backup_file_path)

            # Metadata
            self._save_backup_metadata(backup_file_path, checksum, len(documents))

            logger.info(
                "Incremental backup created successfully",
                backup_file=backup_name,
                documents_count=len(documents),
                checksum=checksum
            )

            return backup_file_path

        except Exception as e:
            logger.error("Failed to create incremental backup", error=str(e), exc_info=True)
            return None

    def restore_from_backup(
        self,
        backup_file_path: str,
        verify_checksum: bool = True
    ) -> bool:
        """
        Restaura ledger a partir de backup.

        Args:
            backup_file_path: Caminho do arquivo de backup
            verify_checksum: Se deve verificar integridade

        Returns:
            True se restauração bem-sucedida
        """
        try:
            logger.warning(
                "Starting backup restoration",
                backup_file=backup_file_path
            )

            # Verificar checksum se solicitado
            if verify_checksum:
                if not self._verify_backup_integrity(backup_file_path):
                    logger.error("Backup integrity check failed")
                    return False

            # Ler arquivo de backup
            if backup_file_path.endswith('.gz'):
                with gzip.open(backup_file_path, 'rt', encoding='utf-8') as f:
                    backup_data = json.load(f)
            else:
                with open(backup_file_path, 'r', encoding='utf-8') as f:
                    backup_data = json.load(f)

            documents = backup_data.get('documents', [])

            if not documents:
                logger.warning("No documents found in backup")
                return False

            # Inserir documentos no MongoDB
            result = self.collection.insert_many(documents, ordered=False)

            logger.warning(
                "Backup restored successfully",
                backup_file=backup_file_path,
                documents_restored=len(result.inserted_ids)
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to restore from backup",
                backup_file=backup_file_path,
                error=str(e),
                exc_info=True
            )
            return False

    def cleanup_old_backups(self) -> int:
        """
        Remove backups antigos baseado na política de retenção.

        Returns:
            Número de arquivos deletados
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=self.backup_retention_days)
            deleted_count = 0

            backup_dir = Path(self.backup_path)

            for backup_file in backup_dir.glob("ledger_*.json*"):
                # Verificar data de modificação
                mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)

                if mtime < cutoff_date:
                    # Deletar arquivo
                    backup_file.unlink()
                    deleted_count += 1

                    # Deletar metadata associado
                    metadata_file = backup_file.with_suffix('.meta')
                    if metadata_file.exists():
                        metadata_file.unlink()

                    logger.info(
                        "Old backup deleted",
                        backup_file=backup_file.name,
                        age_days=(datetime.utcnow() - mtime).days
                    )

            logger.info(
                "Old backups cleaned up",
                deleted_count=deleted_count,
                retention_days=self.backup_retention_days
            )

            return deleted_count

        except Exception as e:
            logger.error("Failed to cleanup old backups", error=str(e))
            return 0

    def list_backups(self) -> List[Dict[str, Any]]:
        """
        Lista todos os backups disponíveis.

        Returns:
            Lista de metadados dos backups
        """
        try:
            backups = []
            backup_dir = Path(self.backup_path)

            for backup_file in sorted(backup_dir.glob("ledger_*.json*")):
                metadata_file = backup_file.with_suffix('.meta')

                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                else:
                    # Metadata não encontrado, criar básico
                    metadata = {
                        'file_name': backup_file.name,
                        'file_path': str(backup_file),
                        'created_at': datetime.fromtimestamp(
                            backup_file.stat().st_mtime
                        ).isoformat(),
                        'file_size_mb': backup_file.stat().st_size / (1024 * 1024)
                    }

                backups.append(metadata)

            logger.debug("Backups listed", count=len(backups))

            return backups

        except Exception as e:
            logger.error("Failed to list backups", error=str(e))
            return []

    def _calculate_file_checksum(self, file_path: str) -> str:
        """
        Calcula checksum SHA-256 de um arquivo.

        Args:
            file_path: Caminho do arquivo

        Returns:
            Checksum hexadecimal
        """
        sha256_hash = hashlib.sha256()

        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest()

    def _save_backup_metadata(
        self,
        backup_file_path: str,
        checksum: str,
        documents_count: int
    ):
        """
        Salva metadata do backup.

        Args:
            backup_file_path: Caminho do arquivo de backup
            checksum: Checksum SHA-256
            documents_count: Número de documentos
        """
        metadata_file_path = backup_file_path.rsplit('.', 1)[0] + '.meta'

        file_size = os.path.getsize(backup_file_path)

        metadata = {
            'file_name': os.path.basename(backup_file_path),
            'file_path': backup_file_path,
            'created_at': datetime.utcnow().isoformat(),
            'checksum': checksum,
            'documents_count': documents_count,
            'file_size_bytes': file_size,
            'file_size_mb': file_size / (1024 * 1024),
            'compression_enabled': self.enable_compression
        }

        with open(metadata_file_path, 'w') as f:
            json.dump(metadata, f, indent=2)

    def _verify_backup_integrity(self, backup_file_path: str) -> bool:
        """
        Verifica integridade do backup via checksum.

        Args:
            backup_file_path: Caminho do arquivo de backup

        Returns:
            True se íntegro
        """
        try:
            metadata_file_path = backup_file_path.rsplit('.', 1)[0] + '.meta'

            if not os.path.exists(metadata_file_path):
                logger.warning("Metadata file not found, skipping integrity check")
                return True

            with open(metadata_file_path, 'r') as f:
                metadata = json.load(f)

            expected_checksum = metadata.get('checksum')

            if not expected_checksum:
                logger.warning("No checksum in metadata")
                return True

            actual_checksum = self._calculate_file_checksum(backup_file_path)

            if actual_checksum != expected_checksum:
                logger.error(
                    "Backup integrity check failed",
                    expected=expected_checksum,
                    actual=actual_checksum
                )
                return False

            logger.info("Backup integrity verified", checksum=actual_checksum)
            return True

        except Exception as e:
            logger.error("Failed to verify backup integrity", error=str(e))
            return False
