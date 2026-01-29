"""
StorageClient abstraction para upload/download de backups de disaster recovery.

Implementações:
- S3StorageClient: AWS S3 via boto3
- GCSStorageClient: Google Cloud Storage via google-cloud-storage
- LocalStorageClient: Filesystem local (desenvolvimento/testes)
"""

import os
import hashlib
import shutil
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime
import structlog

logger = structlog.get_logger()


class StorageClient(ABC):
    """
    Interface abstrata para storage de backups.

    Métodos principais:
    - upload_backup: Upload de arquivo de backup
    - download_backup: Download de backup
    - list_backups: Listar backups disponíveis
    - delete_backup: Deletar backup
    - get_backup_metadata: Obter metadados
    - verify_checksum: Verificar integridade
    """

    @abstractmethod
    def upload_backup(self, local_path: str, remote_key: str) -> bool:
        """
        Faz upload de arquivo de backup.

        Args:
            local_path: Caminho local do arquivo
            remote_key: Chave remota (path no storage)

        Returns:
            True se sucesso, False se falha
        """
        pass

    @abstractmethod
    def download_backup(self, remote_key: str, local_path: str) -> bool:
        """
        Faz download de backup.

        Args:
            remote_key: Chave remota do backup
            local_path: Caminho local de destino

        Returns:
            True se sucesso, False se falha
        """
        pass

    @abstractmethod
    def list_backups(self, prefix: str = "") -> List[Dict]:
        """
        Lista backups disponíveis.

        Args:
            prefix: Prefixo para filtrar backups

        Returns:
            Lista de dicts com: key, size, timestamp
        """
        pass

    @abstractmethod
    def delete_backup(self, remote_key: str) -> bool:
        """
        Deleta backup.

        Args:
            remote_key: Chave remota do backup

        Returns:
            True se sucesso, False se falha
        """
        pass

    @abstractmethod
    def get_backup_metadata(self, remote_key: str) -> Dict:
        """
        Obtém metadados de backup.

        Args:
            remote_key: Chave remota do backup

        Returns:
            Dict com: size, etag, last_modified
        """
        pass

    def verify_checksum(self, remote_key: str, expected_checksum: str) -> bool:
        """
        Verifica checksum de backup (implementação padrão via download).

        Args:
            remote_key: Chave remota do backup
            expected_checksum: Checksum esperado (SHA-256)

        Returns:
            True se checksum válido, False caso contrário
        """
        # Implementação padrão: download e calcular checksum
        # Subclasses podem otimizar (ex: usar ETag do S3)
        import tempfile

        with tempfile.NamedTemporaryFile(delete=True) as tmp:
            if not self.download_backup(remote_key, tmp.name):
                return False

            calculated_checksum = self._calculate_file_checksum(tmp.name)
            return calculated_checksum == expected_checksum

    def _calculate_file_checksum(self, file_path: str) -> str:
        """Calcula SHA-256 checksum de arquivo."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()


class S3StorageClient(StorageClient):
    """
    Cliente S3 para backup via boto3.

    Features:
    - Upload com server-side encryption (AES256)
    - Retry logic automático
    - Logging detalhado
    """

    def __init__(
        self,
        bucket: str,
        region: str,
        prefix: str = "",
        aws_access_key: Optional[str] = None,
        aws_secret_key: Optional[str] = None,
    ):
        """
        Inicializa cliente S3.

        Args:
            bucket: Nome do bucket S3
            region: Região AWS
            prefix: Prefixo de chaves (ex: 'specialists/backups')
            aws_access_key: Access key (opcional, usar IAM role se possível)
            aws_secret_key: Secret key (opcional)
        """
        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            raise ImportError(
                "boto3 não instalado. Instale com: pip install boto3>=1.34.0"
            )

        self.bucket = bucket
        self.region = region
        self.prefix = prefix.rstrip("/")

        # Configurar retry logic
        config = Config(
            region_name=region, retries={"max_attempts": 3, "mode": "adaptive"}
        )

        # Criar cliente boto3
        if aws_access_key and aws_secret_key:
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                config=config,
            )
        else:
            # Usar IAM role
            self.s3_client = boto3.client("s3", config=config)

        logger.info(
            "S3StorageClient inicializado", bucket=bucket, region=region, prefix=prefix
        )

    def _get_full_key(self, remote_key: str) -> str:
        """
        Retorna chave completa com prefixo.

        Se a chave já contém o prefix, não adiciona novamente.
        """
        if self.prefix:
            # Verificar se a chave já começa com o prefix
            if remote_key.startswith(f"{self.prefix}/"):
                return remote_key
            return f"{self.prefix}/{remote_key}"
        return remote_key

    def upload_backup(self, local_path: str, remote_key: str) -> bool:
        """Upload de backup para S3 com server-side encryption."""
        full_key = self._get_full_key(remote_key)

        try:
            file_size = os.path.getsize(local_path)

            logger.info(
                "Iniciando upload S3",
                local_path=local_path,
                remote_key=full_key,
                size_bytes=file_size,
            )

            import time

            start_time = time.time()

            # Upload com server-side encryption
            self.s3_client.upload_file(
                local_path,
                self.bucket,
                full_key,
                ExtraArgs={
                    "ServerSideEncryption": "AES256",
                    "Metadata": {
                        "uploaded_at": datetime.utcnow().isoformat(),
                        "source": "neural-hive-disaster-recovery",
                    },
                },
            )

            duration = time.time() - start_time

            logger.info(
                "Upload S3 concluído com sucesso",
                remote_key=full_key,
                size_bytes=file_size,
                duration_seconds=round(duration, 2),
            )

            return True

        except Exception as e:
            logger.error(
                "Erro no upload S3",
                remote_key=full_key,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    def download_backup(self, remote_key: str, local_path: str) -> bool:
        """Download de backup do S3."""
        full_key = self._get_full_key(remote_key)

        try:
            logger.info(
                "Iniciando download S3", remote_key=full_key, local_path=local_path
            )

            import time

            start_time = time.time()

            # Criar diretório se não existir
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            self.s3_client.download_file(self.bucket, full_key, local_path)

            duration = time.time() - start_time
            file_size = os.path.getsize(local_path)

            logger.info(
                "Download S3 concluído com sucesso",
                remote_key=full_key,
                size_bytes=file_size,
                duration_seconds=round(duration, 2),
            )

            return True

        except Exception as e:
            logger.error(
                "Erro no download S3",
                remote_key=full_key,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    def list_backups(self, prefix: str = "") -> List[Dict]:
        """Lista backups no S3."""
        full_prefix = self._get_full_key(prefix) if prefix else self.prefix

        try:
            logger.debug("Listando backups S3", bucket=self.bucket, prefix=full_prefix)

            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket, Prefix=full_prefix
            )

            if "Contents" not in response:
                return []

            backups = []
            for obj in response["Contents"]:
                backups.append(
                    {
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "timestamp": obj["LastModified"],
                        "etag": obj["ETag"],
                    }
                )

            # Ordenar por timestamp (mais recente primeiro)
            backups.sort(key=lambda x: x["timestamp"], reverse=True)

            logger.info("Backups S3 listados", count=len(backups))

            return backups

        except Exception as e:
            logger.error(
                "Erro ao listar backups S3", error=str(e), error_type=type(e).__name__
            )
            return []

    def delete_backup(self, remote_key: str) -> bool:
        """Deleta backup do S3."""
        full_key = self._get_full_key(remote_key)

        try:
            logger.info("Deletando backup S3", remote_key=full_key)

            self.s3_client.delete_object(Bucket=self.bucket, Key=full_key)

            logger.info("Backup S3 deletado com sucesso", remote_key=full_key)

            return True

        except Exception as e:
            logger.error(
                "Erro ao deletar backup S3",
                remote_key=full_key,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    def get_backup_metadata(self, remote_key: str) -> Dict:
        """Obtém metadados de backup do S3."""
        full_key = self._get_full_key(remote_key)

        try:
            response = self.s3_client.head_object(Bucket=self.bucket, Key=full_key)

            return {
                "size": response["ContentLength"],
                "etag": response["ETag"],
                "last_modified": response["LastModified"],
                "metadata": response.get("Metadata", {}),
            }

        except Exception as e:
            logger.error(
                "Erro ao obter metadados S3",
                remote_key=full_key,
                error=str(e),
                error_type=type(e).__name__,
            )
            return {}


class GCSStorageClient(StorageClient):
    """
    Cliente Google Cloud Storage para backup.

    Features:
    - Upload com metadata
    - Retry logic automático
    - Logging detalhado
    """

    def __init__(
        self,
        bucket: str,
        project: str,
        prefix: str = "",
        credentials_path: Optional[str] = None,
    ):
        """
        Inicializa cliente GCS.

        Args:
            bucket: Nome do bucket GCS
            project: Projeto GCP
            prefix: Prefixo de chaves
            credentials_path: Path para service account JSON (opcional)
        """
        try:
            from google.cloud import storage
            from google.oauth2 import service_account
        except ImportError:
            raise ImportError(
                "google-cloud-storage não instalado. Instale com: pip install google-cloud-storage>=2.14.0"
            )

        self.bucket_name = bucket
        self.project = project
        self.prefix = prefix.rstrip("/")

        # Criar cliente GCS
        if credentials_path:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path
            )
            self.client = storage.Client(project=project, credentials=credentials)
        else:
            # Usar credenciais padrão (ADC)
            self.client = storage.Client(project=project)

        self.bucket = self.client.bucket(bucket)

        logger.info(
            "GCSStorageClient inicializado",
            bucket=bucket,
            project=project,
            prefix=prefix,
        )

    def _get_full_key(self, remote_key: str) -> str:
        """
        Retorna chave completa com prefixo.

        Se a chave já contém o prefix, não adiciona novamente.
        """
        if self.prefix:
            # Verificar se a chave já começa com o prefix
            if remote_key.startswith(f"{self.prefix}/"):
                return remote_key
            return f"{self.prefix}/{remote_key}"
        return remote_key

    def upload_backup(self, local_path: str, remote_key: str) -> bool:
        """Upload de backup para GCS."""
        full_key = self._get_full_key(remote_key)

        try:
            file_size = os.path.getsize(local_path)

            logger.info(
                "Iniciando upload GCS",
                local_path=local_path,
                remote_key=full_key,
                size_bytes=file_size,
            )

            import time

            start_time = time.time()

            blob = self.bucket.blob(full_key)
            blob.metadata = {
                "uploaded_at": datetime.utcnow().isoformat(),
                "source": "neural-hive-disaster-recovery",
            }

            blob.upload_from_filename(local_path)

            duration = time.time() - start_time

            logger.info(
                "Upload GCS concluído com sucesso",
                remote_key=full_key,
                size_bytes=file_size,
                duration_seconds=round(duration, 2),
            )

            return True

        except Exception as e:
            logger.error(
                "Erro no upload GCS",
                remote_key=full_key,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    def download_backup(self, remote_key: str, local_path: str) -> bool:
        """Download de backup do GCS."""
        full_key = self._get_full_key(remote_key)

        try:
            logger.info(
                "Iniciando download GCS", remote_key=full_key, local_path=local_path
            )

            import time

            start_time = time.time()

            # Criar diretório se não existir
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            blob = self.bucket.blob(full_key)
            blob.download_to_filename(local_path)

            duration = time.time() - start_time
            file_size = os.path.getsize(local_path)

            logger.info(
                "Download GCS concluído com sucesso",
                remote_key=full_key,
                size_bytes=file_size,
                duration_seconds=round(duration, 2),
            )

            return True

        except Exception as e:
            logger.error(
                "Erro no download GCS",
                remote_key=full_key,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    def list_backups(self, prefix: str = "") -> List[Dict]:
        """Lista backups no GCS."""
        full_prefix = self._get_full_key(prefix) if prefix else self.prefix

        try:
            logger.debug(
                "Listando backups GCS", bucket=self.bucket_name, prefix=full_prefix
            )

            blobs = self.client.list_blobs(self.bucket_name, prefix=full_prefix)

            backups = []
            for blob in blobs:
                backups.append(
                    {
                        "key": blob.name,
                        "size": blob.size,
                        "timestamp": blob.updated,
                        "md5_hash": blob.md5_hash,
                    }
                )

            # Ordenar por timestamp (mais recente primeiro)
            backups.sort(key=lambda x: x["timestamp"], reverse=True)

            logger.info("Backups GCS listados", count=len(backups))

            return backups

        except Exception as e:
            logger.error(
                "Erro ao listar backups GCS", error=str(e), error_type=type(e).__name__
            )
            return []

    def delete_backup(self, remote_key: str) -> bool:
        """Deleta backup do GCS."""
        full_key = self._get_full_key(remote_key)

        try:
            logger.info("Deletando backup GCS", remote_key=full_key)

            blob = self.bucket.blob(full_key)
            blob.delete()

            logger.info("Backup GCS deletado com sucesso", remote_key=full_key)

            return True

        except Exception as e:
            logger.error(
                "Erro ao deletar backup GCS",
                remote_key=full_key,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    def get_backup_metadata(self, remote_key: str) -> Dict:
        """Obtém metadados de backup do GCS."""
        full_key = self._get_full_key(remote_key)

        try:
            blob = self.bucket.blob(full_key)
            blob.reload()

            return {
                "size": blob.size,
                "md5_hash": blob.md5_hash,
                "last_modified": blob.updated,
                "metadata": blob.metadata or {},
            }

        except Exception as e:
            logger.error(
                "Erro ao obter metadados GCS",
                remote_key=full_key,
                error=str(e),
                error_type=type(e).__name__,
            )
            return {}


class LocalStorageClient(StorageClient):
    """
    Cliente de filesystem local para backups (desenvolvimento/testes).

    Features:
    - Simula upload/download via cópia
    - Útil para testes
    """

    def __init__(self, base_path: str):
        """
        Inicializa cliente local.

        Args:
            base_path: Path base para backups
        """
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)

        logger.info("LocalStorageClient inicializado", base_path=base_path)

    def _get_full_path(self, remote_key: str) -> str:
        """Retorna path completo local."""
        return os.path.join(self.base_path, remote_key)

    def upload_backup(self, local_path: str, remote_key: str) -> bool:
        """Upload de backup (copia para base_path)."""
        full_path = self._get_full_path(remote_key)

        try:
            logger.info(
                "Copiando backup para storage local",
                source=local_path,
                destination=full_path,
            )

            # Criar diretório se não existir
            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            shutil.copy2(local_path, full_path)

            file_size = os.path.getsize(full_path)

            logger.info(
                "Backup copiado com sucesso",
                destination=full_path,
                size_bytes=file_size,
            )

            return True

        except Exception as e:
            logger.error(
                "Erro ao copiar backup",
                destination=full_path,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    def download_backup(self, remote_key: str, local_path: str) -> bool:
        """Download de backup (copia de base_path)."""
        full_path = self._get_full_path(remote_key)

        try:
            if not os.path.exists(full_path):
                logger.error("Backup não encontrado", backup_path=full_path)
                return False

            logger.info(
                "Copiando backup do storage local",
                source=full_path,
                destination=local_path,
            )

            # Criar diretório se não existir
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            shutil.copy2(full_path, local_path)

            file_size = os.path.getsize(local_path)

            logger.info(
                "Backup copiado com sucesso",
                destination=local_path,
                size_bytes=file_size,
            )

            return True

        except Exception as e:
            logger.error(
                "Erro ao copiar backup",
                source=full_path,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    def list_backups(self, prefix: str = "") -> List[Dict]:
        """Lista backups no storage local."""
        try:
            search_path = self._get_full_path(prefix) if prefix else self.base_path

            logger.debug("Listando backups locais", path=search_path)

            backups = []

            if os.path.isdir(search_path):
                for root, dirs, files in os.walk(search_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, self.base_path)

                        stat = os.stat(file_path)

                        backups.append(
                            {
                                "key": rel_path,
                                "size": stat.st_size,
                                "timestamp": datetime.fromtimestamp(stat.st_mtime),
                            }
                        )

            # Ordenar por timestamp (mais recente primeiro)
            backups.sort(key=lambda x: x["timestamp"], reverse=True)

            logger.info("Backups locais listados", count=len(backups))

            return backups

        except Exception as e:
            logger.error(
                "Erro ao listar backups locais",
                error=str(e),
                error_type=type(e).__name__,
            )
            return []

    def delete_backup(self, remote_key: str) -> bool:
        """Deleta backup do storage local."""
        full_path = self._get_full_path(remote_key)

        try:
            if not os.path.exists(full_path):
                logger.warning("Backup não encontrado para deletar", path=full_path)
                return False

            logger.info("Deletando backup local", path=full_path)

            os.remove(full_path)

            logger.info("Backup local deletado com sucesso", path=full_path)

            return True

        except Exception as e:
            logger.error(
                "Erro ao deletar backup local",
                path=full_path,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    def get_backup_metadata(self, remote_key: str) -> Dict:
        """Obtém metadados de backup local."""
        full_path = self._get_full_path(remote_key)

        try:
            if not os.path.exists(full_path):
                return {}

            stat = os.stat(full_path)

            return {
                "size": stat.st_size,
                "last_modified": datetime.fromtimestamp(stat.st_mtime),
                "checksum": self._calculate_file_checksum(full_path),
            }

        except Exception as e:
            logger.error(
                "Erro ao obter metadados locais",
                path=full_path,
                error=str(e),
                error_type=type(e).__name__,
            )
            return {}
