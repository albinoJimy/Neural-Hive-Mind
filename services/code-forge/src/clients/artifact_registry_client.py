"""
Cliente para Artifact Registry (OCI).

Registra referências de SBOMs no registry para rastreabilidade.
"""

import httpx
import structlog
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..observability.metrics import CodeForgeMetrics

logger = structlog.get_logger()


class ArtifactRegistryClient:
    """
    Cliente para registrar SBOMs no OCI registry.

    Utiliza OCI Distribution Spec para armazenar referências.
    """

    def __init__(
        self,
        registry_url: str,
        timeout: int = 30,
        metrics: Optional['CodeForgeMetrics'] = None
    ):
        """
        Inicializa cliente do Artifact Registry.

        Args:
            registry_url: URL do OCI registry
            timeout: Timeout para requisições HTTP
            metrics: Instância de CodeForgeMetrics para instrumentação
        """
        self.registry_url = registry_url.rstrip('/')
        self.timeout = timeout
        self.metrics = metrics
        self._client: Optional[httpx.AsyncClient] = None

        logger.info(
            'artifact_registry_client_initialized',
            registry_url=self.registry_url
        )

    async def start(self):
        """Inicializa cliente HTTP assíncrono."""
        self._client = httpx.AsyncClient(
            base_url=self.registry_url,
            timeout=self.timeout
        )
        logger.info('artifact_registry_client_started')

    async def stop(self):
        """Fecha cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info('artifact_registry_client_stopped')

    async def register_sbom(
        self,
        sbom_uri: str,
        artifact_id: str,
        metadata: Dict
    ) -> Optional[str]:
        """
        Registra referência de SBOM no registry.

        Args:
            sbom_uri: URI S3 do SBOM
            artifact_id: ID do artefato
            metadata: Metadados adicionais (ticket_id, etc)

        Returns:
            Referência do registry ou None se falhar
        """
        if not self._client:
            logger.warning('artifact_registry_client_not_started')
            return None

        try:
            payload = {
                'artifact_id': artifact_id,
                'sbom_uri': sbom_uri,
                'metadata': metadata
            }

            logger.info(
                'registering_sbom',
                artifact_id=artifact_id,
                sbom_uri=sbom_uri
            )

            response = await self._client.post(
                '/v2/sboms/register',
                json=payload
            )

            if response.status_code in (200, 201):
                result = response.json()
                reference = result.get('reference')
                logger.info(
                    'sbom_registered',
                    artifact_id=artifact_id,
                    reference=reference
                )
                return reference
            else:
                logger.error(
                    'sbom_registration_failed',
                    artifact_id=artifact_id,
                    status_code=response.status_code,
                    response=response.text[:200]
                )
                return None

        except Exception as e:
            logger.error(
                'sbom_registration_error',
                artifact_id=artifact_id,
                error=str(e),
                error_type=type(e).__name__
            )
            return None

    async def get_sbom_reference(self, artifact_id: str) -> Optional[str]:
        """
        Obtém referência de SBOM pelo artifact_id.

        Args:
            artifact_id: ID do artefato

        Returns:
            URI do SBOM ou None se não encontrado
        """
        if not self._client:
            return None

        try:
            response = await self._client.get(
                f'/v2/sboms/{artifact_id}'
            )

            if response.status_code == 200:
                result = response.json()
                return result.get('sbom_uri')

            return None

        except Exception as e:
            logger.error(
                'get_sbom_reference_error',
                artifact_id=artifact_id,
                error=str(e)
            )
            return None

    async def register_artifact(
        self,
        artifact_uri: str,
        artifact_type: str,
        metadata: Dict
    ) -> Optional[Dict]:
        """
        Registra artefato de container no registry.

        Args:
            artifact_uri: URI completa da imagem (ex: ghcr.io/user/repo:tag)
            artifact_type: Tipo do artefato (CONTAINER_IMAGE, etc)
            metadata: Metadados do artefato (digest, size, etc)

        Returns:
            Dict com artifact_id e referências ou None se falhar
        """
        if not self._client:
            logger.warning('artifact_registry_client_not_started')
            return None

        try:
            payload = {
                'artifact_uri': artifact_uri,
                'artifact_type': artifact_type,
                'metadata': metadata
            }

            logger.info(
                'registering_artifact',
                artifact_uri=artifact_uri,
                artifact_type=artifact_type
            )

            response = await self._client.post(
                '/v2/artifacts/register',
                json=payload
            )

            if response.status_code in (200, 201):
                result = response.json()
                logger.info(
                    'artifact_registered',
                    artifact_uri=artifact_uri,
                    artifact_id=result.get('artifact_id')
                )
                return result
            else:
                logger.error(
                    'artifact_registration_failed',
                    artifact_uri=artifact_uri,
                    status_code=response.status_code,
                    response=response.text[:200]
                )
                return None

        except Exception as e:
            logger.error(
                'artifact_registration_error',
                artifact_uri=artifact_uri,
                error=str(e),
                error_type=type(e).__name__
            )
            return None

    async def get_artifact_metadata(self, artifact_id: str) -> Optional[Dict]:
        """
        Obtém metadados de um artefato registrado.

        Args:
            artifact_id: ID do artefato

        Returns:
            Dict com metadados ou None se não encontrado
        """
        if not self._client:
            return None

        try:
            response = await self._client.get(
                f'/v2/artifacts/{artifact_id}'
            )

            if response.status_code == 200:
                result = response.json()
                logger.debug(
                    'artifact_metadata_retrieved',
                    artifact_id=artifact_id
                )
                return result

            if response.status_code == 404:
                logger.debug(
                    'artifact_metadata_not_found',
                    artifact_id=artifact_id
                )
                return None

            logger.warning(
                'artifact_metadata_failed',
                artifact_id=artifact_id,
                status_code=response.status_code
            )
            return None

        except Exception as e:
            logger.error(
                'get_artifact_metadata_error',
                artifact_id=artifact_id,
                error=str(e)
            )
            return None

    async def list_artifacts(
        self,
        artifact_type: Optional[str] = None,
        limit: int = 100
    ) -> list:
        """
        Lista artefatos registrados.

        Args:
            artifact_type: Filtra por tipo (opcional)
            limit: Limite de resultados

        Returns:
            Lista de dicts com artifact_id, uri, tipo, etc
        """
        if not self._client:
            return []

        try:
            params = {}
            if artifact_type:
                params['type'] = artifact_type
            params['limit'] = limit

            response = await self._client.get(
                '/v2/artifacts',
                params=params
            )

            if response.status_code == 200:
                result = response.json()
                artifacts = result.get('artifacts', [])
                logger.info(
                    'artifacts_listed',
                    count=len(artifacts)
                )
                return artifacts

            logger.warning(
                'list_artifacts_failed',
                status_code=response.status_code
            )
            return []

        except Exception as e:
            logger.error(
                'list_artifacts_error',
                error=str(e)
            )
            return []

    async def health_check(self) -> bool:
        """
        Verifica saúde do registry.

        Returns:
            True se registry acessível
        """
        if not self._client:
            return False

        try:
            response = await self._client.get('/v2/')
            return response.status_code == 200
        except Exception:
            return False
