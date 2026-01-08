"""
Cliente S3 para armazenamento de artefatos e SBOMs.

Baseado no padrão S3StorageClient do módulo de disaster recovery.
"""

import os
import hashlib
import time
from datetime import datetime
from typing import List, Dict, Optional, TYPE_CHECKING
import structlog

if TYPE_CHECKING:
    from ..observability.metrics import CodeForgeMetrics

logger = structlog.get_logger()


class S3ArtifactClient:
    """
    Cliente S3 para upload/download de artefatos e SBOMs.

    Features:
    - Upload com server-side encryption (AES256)
    - Retry logic adaptativo (3 tentativas)
    - Verificação de integridade via SHA-256
    - Logging estruturado
    - Métricas Prometheus
    """

    def __init__(
        self,
        bucket: str,
        region: str,
        endpoint: Optional[str] = None,
        metrics: Optional['CodeForgeMetrics'] = None
    ):
        """
        Inicializa cliente S3 para artefatos.

        Args:
            bucket: Nome do bucket S3
            region: Região AWS
            endpoint: Endpoint S3 customizado (para MinIO/LocalStack)
            metrics: Instância de CodeForgeMetrics para instrumentação
        """
        self.bucket = bucket
        self.region = region
        self.endpoint = endpoint
        self.metrics = metrics
        self._s3_client = None

        logger.info(
            's3_artifact_client_initialized',
            bucket=bucket,
            region=region,
            endpoint=endpoint or 'default'
        )

    def _get_client(self):
        """Lazy initialization do cliente boto3."""
        if self._s3_client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError:
                raise ImportError(
                    "boto3 não instalado. Instale com: pip install boto3>=1.34.0"
                )

            config = Config(
                region_name=self.region,
                retries={
                    'max_attempts': 3,
                    'mode': 'adaptive'
                }
            )

            client_kwargs = {'config': config}
            if self.endpoint:
                client_kwargs['endpoint_url'] = self.endpoint

            self._s3_client = boto3.client('s3', **client_kwargs)

        return self._s3_client

    def _calculate_file_checksum(self, file_path: str) -> str:
        """Calcula SHA-256 checksum de arquivo."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    async def upload_sbom(
        self,
        local_path: str,
        artifact_id: str,
        ticket_id: str
    ) -> str:
        """
        Upload de SBOM para S3.

        Args:
            local_path: Caminho local do SBOM
            artifact_id: ID do artefato
            ticket_id: ID do ticket de execução

        Returns:
            URI S3 do SBOM (s3://bucket/sboms/...)
        """
        filename = os.path.basename(local_path)
        remote_key = f"sboms/{ticket_id}/{artifact_id}/{filename}"

        return await self._upload_file(
            local_path=local_path,
            remote_key=remote_key,
            artifact_id=artifact_id,
            ticket_id=ticket_id,
            artifact_type='sbom'
        )

    async def upload_artifact(
        self,
        local_path: str,
        artifact_id: str,
        ticket_id: str
    ) -> str:
        """
        Upload de artefato para S3.

        Args:
            local_path: Caminho local do artefato
            artifact_id: ID do artefato
            ticket_id: ID do ticket de execução

        Returns:
            URI S3 do artefato (s3://bucket/artifacts/...)
        """
        filename = os.path.basename(local_path)
        remote_key = f"artifacts/{ticket_id}/{artifact_id}/{filename}"

        return await self._upload_file(
            local_path=local_path,
            remote_key=remote_key,
            artifact_id=artifact_id,
            ticket_id=ticket_id,
            artifact_type='artifact'
        )

    async def _upload_file(
        self,
        local_path: str,
        remote_key: str,
        artifact_id: str,
        ticket_id: str,
        artifact_type: str
    ) -> str:
        """
        Upload genérico de arquivo para S3.

        Args:
            local_path: Caminho local do arquivo
            remote_key: Chave remota no S3
            artifact_id: ID do artefato
            ticket_id: ID do ticket
            artifact_type: Tipo do artefato (sbom, artifact)

        Returns:
            URI S3 do arquivo
        """
        start_time = time.perf_counter()

        try:
            file_size = os.path.getsize(local_path)
            checksum = self._calculate_file_checksum(local_path)

            logger.info(
                's3_upload_started',
                local_path=local_path,
                remote_key=remote_key,
                size_bytes=file_size,
                artifact_type=artifact_type
            )

            client = self._get_client()

            client.upload_file(
                local_path,
                self.bucket,
                remote_key,
                ExtraArgs={
                    'ServerSideEncryption': 'AES256',
                    'Metadata': {
                        'uploaded_at': datetime.utcnow().isoformat(),
                        'source': 'code-forge',
                        'ticket_id': ticket_id,
                        'artifact_id': artifact_id,
                        'artifact_type': artifact_type,
                        'sha256': checksum
                    }
                }
            )

            duration = time.perf_counter() - start_time
            s3_uri = f"s3://{self.bucket}/{remote_key}"

            logger.info(
                's3_upload_completed',
                remote_key=remote_key,
                s3_uri=s3_uri,
                size_bytes=file_size,
                duration_seconds=round(duration, 3),
                artifact_type=artifact_type
            )

            if self.metrics:
                self.metrics.s3_upload_duration_seconds.labels(
                    operation=artifact_type
                ).observe(duration)
                self.metrics.s3_upload_total.labels(
                    status='success',
                    operation=artifact_type
                ).inc()

            return s3_uri

        except Exception as e:
            duration = time.perf_counter() - start_time

            logger.error(
                's3_upload_failed',
                remote_key=remote_key,
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(duration, 3),
                artifact_type=artifact_type
            )

            if self.metrics:
                self.metrics.s3_upload_total.labels(
                    status='failure',
                    operation=artifact_type
                ).inc()

            raise

    async def download_sbom(self, sbom_uri: str, local_path: str) -> bool:
        """
        Download de SBOM do S3.

        Args:
            sbom_uri: URI S3 do SBOM (s3://bucket/key)
            local_path: Caminho local de destino

        Returns:
            True se sucesso, False se falha
        """
        return await self._download_file(sbom_uri, local_path)

    async def _download_file(self, s3_uri: str, local_path: str) -> bool:
        """
        Download genérico de arquivo do S3.

        Args:
            s3_uri: URI S3 do arquivo
            local_path: Caminho local de destino

        Returns:
            True se sucesso, False se falha
        """
        try:
            # Parse URI s3://bucket/key
            if not s3_uri.startswith('s3://'):
                logger.error('invalid_s3_uri', uri=s3_uri)
                return False

            parts = s3_uri[5:].split('/', 1)
            if len(parts) != 2:
                logger.error('invalid_s3_uri_format', uri=s3_uri)
                return False

            bucket, key = parts

            logger.info(
                's3_download_started',
                s3_uri=s3_uri,
                local_path=local_path
            )

            start_time = time.perf_counter()
            client = self._get_client()

            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            client.download_file(bucket, key, local_path)

            duration = time.perf_counter() - start_time
            file_size = os.path.getsize(local_path)

            logger.info(
                's3_download_completed',
                s3_uri=s3_uri,
                local_path=local_path,
                size_bytes=file_size,
                duration_seconds=round(duration, 3)
            )

            return True

        except Exception as e:
            logger.error(
                's3_download_failed',
                s3_uri=s3_uri,
                error=str(e),
                error_type=type(e).__name__
            )
            return False

    async def get_sbom_metadata(self, sbom_uri: str) -> Dict:
        """
        Obtém metadados de SBOM do S3.

        Args:
            sbom_uri: URI S3 do SBOM

        Returns:
            Dict com metadados (size, last_modified, sha256, etc)
        """
        try:
            if not sbom_uri.startswith('s3://'):
                return {}

            parts = sbom_uri[5:].split('/', 1)
            if len(parts) != 2:
                return {}

            bucket, key = parts
            client = self._get_client()

            response = client.head_object(Bucket=bucket, Key=key)

            return {
                'size': response['ContentLength'],
                'etag': response['ETag'],
                'last_modified': response['LastModified'],
                'metadata': response.get('Metadata', {})
            }

        except Exception as e:
            logger.error(
                's3_get_metadata_failed',
                sbom_uri=sbom_uri,
                error=str(e),
                error_type=type(e).__name__
            )
            return {}

    async def list_sboms(self, ticket_id: str) -> List[Dict]:
        """
        Lista SBOMs de um ticket.

        Args:
            ticket_id: ID do ticket

        Returns:
            Lista de dicts com: key, size, timestamp, etag
        """
        prefix = f"sboms/{ticket_id}/"

        try:
            client = self._get_client()

            response = client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix
            )

            if 'Contents' not in response:
                return []

            sboms = []
            for obj in response['Contents']:
                sboms.append({
                    'key': obj['Key'],
                    's3_uri': f"s3://{self.bucket}/{obj['Key']}",
                    'size': obj['Size'],
                    'timestamp': obj['LastModified'],
                    'etag': obj['ETag']
                })

            sboms.sort(key=lambda x: x['timestamp'], reverse=True)

            logger.info(
                's3_sboms_listed',
                ticket_id=ticket_id,
                count=len(sboms)
            )

            return sboms

        except Exception as e:
            logger.error(
                's3_list_sboms_failed',
                ticket_id=ticket_id,
                error=str(e),
                error_type=type(e).__name__
            )
            return []

    async def delete_sbom(self, sbom_uri: str) -> bool:
        """
        Deleta SBOM do S3.

        Args:
            sbom_uri: URI S3 do SBOM

        Returns:
            True se sucesso, False se falha
        """
        try:
            if not sbom_uri.startswith('s3://'):
                return False

            parts = sbom_uri[5:].split('/', 1)
            if len(parts) != 2:
                return False

            bucket, key = parts
            client = self._get_client()

            logger.info('s3_delete_started', s3_uri=sbom_uri)

            client.delete_object(Bucket=bucket, Key=key)

            logger.info('s3_delete_completed', s3_uri=sbom_uri)

            return True

        except Exception as e:
            logger.error(
                's3_delete_failed',
                sbom_uri=sbom_uri,
                error=str(e),
                error_type=type(e).__name__
            )
            return False

    async def verify_sbom_integrity(
        self,
        sbom_uri: str,
        expected_checksum: Optional[str] = None
    ) -> bool:
        """
        Verifica integridade de SBOM.

        Se expected_checksum não for fornecido, usa o checksum armazenado nos metadados.

        Args:
            sbom_uri: URI S3 do SBOM
            expected_checksum: Checksum SHA-256 esperado (opcional)

        Returns:
            True se íntegro, False caso contrário
        """
        import tempfile

        try:
            # Obter checksum esperado dos metadados se não fornecido
            if not expected_checksum:
                metadata = await self.get_sbom_metadata(sbom_uri)
                expected_checksum = metadata.get('metadata', {}).get('sha256')

                if not expected_checksum:
                    logger.warning(
                        's3_integrity_no_checksum',
                        sbom_uri=sbom_uri
                    )
                    return True  # Sem checksum para verificar

            # Download e verificar
            with tempfile.NamedTemporaryFile(delete=True) as tmp:
                if not await self._download_file(sbom_uri, tmp.name):
                    if self.metrics:
                        self.metrics.s3_integrity_check_total.labels(
                            status='failure'
                        ).inc()
                    return False

                calculated = self._calculate_file_checksum(tmp.name)
                is_valid = calculated == expected_checksum

                if is_valid:
                    logger.info(
                        's3_integrity_verified',
                        sbom_uri=sbom_uri
                    )
                else:
                    logger.error(
                        's3_integrity_mismatch',
                        sbom_uri=sbom_uri,
                        expected=expected_checksum[:16],
                        calculated=calculated[:16]
                    )

                if self.metrics:
                    status = 'success' if is_valid else 'failure'
                    self.metrics.s3_integrity_check_total.labels(
                        status=status
                    ).inc()

                return is_valid

        except Exception as e:
            logger.error(
                's3_integrity_check_failed',
                sbom_uri=sbom_uri,
                error=str(e),
                error_type=type(e).__name__
            )
            if self.metrics:
                self.metrics.s3_integrity_check_total.labels(
                    status='failure'
                ).inc()
            return False

    async def health_check(self) -> bool:
        """
        Verifica saúde da conexão S3.

        Returns:
            True se bucket acessível
        """
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self.bucket)
            return True
        except Exception as e:
            logger.error(
                's3_health_check_failed',
                bucket=self.bucket,
                error=str(e)
            )
            return False
