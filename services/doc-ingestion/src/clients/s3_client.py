"""Cliente S3/MinIO para Doc Ingestion Service."""

from io import BytesIO
from typing import Optional

from minio import Minio
from minio.error import S3Error
from structlog import get_logger

from src.config.settings import get_settings

logger = get_logger(__name__)


class S3Client:
    """Cliente S3/MinIO para armazenamento de blobs."""

    _instance: Optional["S3Client"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        settings = get_settings()
        self._client: Optional[Minio] = None
        self._endpoint = settings.s3_endpoint
        self._access_key = settings.s3_access_key
        self._secret_key = settings.s3_secret_key
        self._bucket_name = settings.s3_bucket
        self._secure = settings.s3_secure
        self._initialized = False
        self._init_done = False

    async def initialize(self) -> None:
        """Inicializa o cliente MinIO e cria o bucket se necessário."""
        if self._init_done:
            return

        try:
            # Criar cliente MinIO
            self._client = Minio(
                self._endpoint,
                access_key=self._access_key,
                secret_key=self._secret_key,
                secure=self._secure,
            )

            # Verificar/criar bucket
            if not await self._bucket_exists():
                await self._create_bucket()

            self._init_done = True
            logger.info(
                "s3_client_initialized",
                endpoint=self._endpoint,
                bucket=self._bucket_name,
            )
        except S3Error as e:
            logger.error("s3_client_init_error", error=str(e), code=e.code)
            raise
        except Exception as e:
            logger.error("s3_client_init_unexpected_error", error=str(e))
            raise

    async def _bucket_exists(self) -> bool:
        """Verifica se o bucket existe.

        Returns:
            True se o bucket existe, False caso contrário.
        """
        if self._client is None:
            raise RuntimeError("S3 client not initialized. Call initialize() first.")

        try:
            return self._client.bucket_exists(self._bucket_name)
        except S3Error as e:
            logger.error("bucket_exists_check_error", error=str(e), code=e.code)
            return False

    async def _create_bucket(self) -> None:
        """Cria o bucket no S3/MinIO."""
        if self._client is None:
            raise RuntimeError("S3 client not initialized. Call initialize() first.")

        try:
            self._client.make_bucket(self._bucket_name)
            logger.info("bucket_created", bucket=self._bucket_name)
        except S3Error as e:
            logger.error("bucket_creation_error", error=str(e), code=e.code)
            raise

    def _build_s3_key(self, ingestion_id: str, filename: str, prefix: str = "raw") -> str:
        """Constrói a chave S3 para um arquivo.

        Args:
            ingestion_id: ID da ingestão.
            filename: Nome do arquivo.
            prefix: Prefixo do caminho (raw, parsed, etc.).

        Returns:
            Chave S3 no formato {ingestion_id}/{prefix}/{filename}.
        """
        return f"{ingestion_id}/{prefix}/{filename}"

    async def upload_file(
        self,
        ingestion_id: str,
        filename: str,
        content: bytes,
        metadata: Optional[dict[str, str]] = None,
    ) -> str:
        """Faz upload de um arquivo para o S3/MinIO.

        Args:
            ingestion_id: ID da ingestão.
            filename: Nome do arquivo.
            content: Conteúdo do arquivo em bytes.
            metadata: Metadados opcionais do arquivo.

        Returns:
            A chave S3 do arquivo uploaded.

        Raises:
            RuntimeError: Se o cliente não foi inicializado.
            S3Error: Se ocorrer erro no upload.
        """
        if self._client is None:
            raise RuntimeError("S3 client not initialized. Call initialize() first.")

        s3_key = self._build_s3_key(ingestion_id, filename)

        try:
            content_stream = BytesIO(content)
            length = len(content)

            self._client.put_object(
                bucket_name=self._bucket_name,
                object_name=s3_key,
                data=content_stream,
                length=length,
                metadata=metadata or {},
            )

            logger.info(
                "file_uploaded",
                s3_key=s3_key,
                size_bytes=length,
                ingestion_id=ingestion_id,
            )
            return s3_key
        except S3Error as e:
            logger.error(
                "file_upload_error",
                s3_key=s3_key,
                error=str(e),
                code=e.code,
            )
            raise

    async def download_file(self, s3_key: str) -> bytes:
        """Faz download de um arquivo do S3/MinIO.

        Args:
            s3_key: Chave S3 do arquivo.

        Returns:
            Conteúdo do arquivo em bytes.

        Raises:
            RuntimeError: Se o cliente não foi inicializado.
            S3Error: Se ocorrer erro no download.
        """
        if self._client is None:
            raise RuntimeError("S3 client not initialized. Call initialize() first.")

        try:
            response = self._client.get_object(
                bucket_name=self._bucket_name,
                object_name=s3_key,
            )
            content = response.read()
            response.close()
            response.release_conn()

            logger.info("file_downloaded", s3_key=s3_key, size_bytes=len(content))
            return content
        except S3Error as e:
            logger.error(
                "file_download_error",
                s3_key=s3_key,
                error=str(e),
                code=e.code,
            )
            raise

    async def delete_file(self, s3_key: str) -> None:
        """Deleta um arquivo do S3/MinIO.

        Args:
            s3_key: Chave S3 do arquivo.

        Raises:
            RuntimeError: Se o cliente não foi inicializado.
            S3Error: Se ocorrer erro na deleção.
        """
        if self._client is None:
            raise RuntimeError("S3 client not initialized. Call initialize() first.")

        try:
            self._client.remove_object(
                bucket_name=self._bucket_name,
                object_name=s3_key,
            )
            logger.info("file_deleted", s3_key=s3_key)
        except S3Error as e:
            logger.error(
                "file_deletion_error",
                s3_key=s3_key,
                error=str(e),
                code=e.code,
            )
            raise

    async def list_files(self, ingestion_id: str, prefix: str = "raw") -> list[str]:
        """Lista todos os arquivos de uma ingestão.

        Args:
            ingestion_id: ID da ingestão.
            prefix: Prefixo para filtrar (raw, parsed, etc.).

        Returns:
            Lista de chaves S3 dos arquivos encontrados.

        Raises:
            RuntimeError: Se o cliente não foi inicializado.
            S3Error: Se ocorrer erro na listagem.
        """
        if self._client is None:
            raise RuntimeError("S3 client not initialized. Call initialize() first.")

        s3_prefix = f"{ingestion_id}/{prefix}/"
        files = []

        try:
            objects = self._client.list_objects(
                bucket_name=self._bucket_name,
                prefix=s3_prefix,
                recursive=True,
            )

            for obj in objects:
                files.append(obj.object_name)

            logger.info(
                "files_listed",
                ingestion_id=ingestion_id,
                prefix=prefix,
                count=len(files),
            )
            return files
        except S3Error as e:
            logger.error(
                "files_list_error",
                ingestion_id=ingestion_id,
                prefix=prefix,
                error=str(e),
                code=e.code,
            )
            raise


_s3_client: Optional[S3Client] = None


async def get_s3_client() -> S3Client:
    """Retorna instância do cliente S3 (singleton).

    Returns:
        Instância inicializada do S3Client.
    """
    global _s3_client
    if _s3_client is None:
        _s3_client = S3Client()
        await _s3_client.initialize()
    return _s3_client
