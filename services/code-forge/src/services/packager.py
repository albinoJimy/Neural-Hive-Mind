import structlog
from typing import Optional, TYPE_CHECKING

from ..models.pipeline_context import PipelineContext
from ..clients.sigstore_client import SigstoreClient

if TYPE_CHECKING:
    from ..clients.s3_artifact_client import S3ArtifactClient
    from ..clients.artifact_registry_client import ArtifactRegistryClient

logger = structlog.get_logger()


class Packager:
    """Subpipeline 5: Empacotamento e Assinatura"""

    def __init__(
        self,
        sigstore_client: SigstoreClient,
        s3_artifact_client: Optional['S3ArtifactClient'] = None,
        artifact_registry_client: Optional['ArtifactRegistryClient'] = None
    ):
        self.sigstore_client = sigstore_client
        self.s3_artifact_client = s3_artifact_client
        self.artifact_registry_client = artifact_registry_client

    async def package(self, context: PipelineContext):
        """
        Empacota e assina artefatos

        Args:
            context: Contexto do pipeline
        """
        logger.info('packaging_started', pipeline_id=context.pipeline_id)

        # Obter ticket_id do contexto
        ticket_id = getattr(context.ticket, 'ticket_id', None) if context.ticket else None

        for artifact in context.generated_artifacts:
            # Gerar SBOM com IDs para upload S3
            sbom_uri = await self.sigstore_client.generate_sbom(
                artifact_path=artifact.content_uri,
                artifact_id=artifact.artifact_id,
                ticket_id=ticket_id
            )
            artifact.sbom_uri = sbom_uri

            # Verificar integridade pós-upload S3
            if self.s3_artifact_client and sbom_uri and sbom_uri.startswith('s3://'):
                integrity_ok = await self._verify_sbom_integrity_with_retry(
                    sbom_uri=sbom_uri,
                    artifact_id=artifact.artifact_id,
                    ticket_id=ticket_id,
                    artifact_path=artifact.content_uri
                )
                if not integrity_ok:
                    logger.error(
                        'sbom_integrity_verification_failed_after_retry',
                        artifact_id=artifact.artifact_id,
                        sbom_uri=sbom_uri
                    )

            # Registrar SBOM no Artifact Registry
            if self.artifact_registry_client and sbom_uri and sbom_uri.startswith('s3://'):
                metadata = {
                    'ticket_id': ticket_id,
                    'pipeline_id': context.pipeline_id,
                    'artifact_type': getattr(artifact, 'artifact_type', 'unknown')
                }
                registry_ref = await self.artifact_registry_client.register_sbom(
                    sbom_uri=sbom_uri,
                    artifact_id=artifact.artifact_id,
                    metadata=metadata
                )
                if registry_ref:
                    artifact.registry_reference = registry_ref
                    logger.info(
                        'sbom_registered_in_artifact_registry',
                        artifact_id=artifact.artifact_id,
                        registry_reference=registry_ref
                    )

            # Assinar artefato
            signature = await self.sigstore_client.sign_artifact(artifact.content_uri)
            artifact.signature = signature

            logger.info(
                'artifact_packaged',
                artifact_id=artifact.artifact_id,
                sbom_uri=sbom_uri,
                signed=bool(signature)
            )

    async def _verify_sbom_integrity_with_retry(
        self,
        sbom_uri: str,
        artifact_id: str,
        ticket_id: Optional[str],
        artifact_path: str,
        max_retries: int = 1
    ) -> bool:
        """
        Verifica integridade do SBOM com retry de re-upload em caso de falha.

        Args:
            sbom_uri: URI S3 do SBOM
            artifact_id: ID do artefato
            ticket_id: ID do ticket
            artifact_path: Caminho do artefato original (para re-geração)
            max_retries: Número máximo de retries

        Returns:
            True se íntegro, False se falhou após retry
        """
        for attempt in range(max_retries + 1):
            is_valid = await self.s3_artifact_client.verify_sbom_integrity(sbom_uri)

            if is_valid:
                logger.info(
                    'sbom_integrity_verified',
                    artifact_id=artifact_id,
                    sbom_uri=sbom_uri,
                    attempt=attempt + 1
                )
                return True

            if attempt < max_retries:
                logger.warning(
                    'sbom_integrity_failed_retrying',
                    artifact_id=artifact_id,
                    sbom_uri=sbom_uri,
                    attempt=attempt + 1
                )
                # Re-gerar e re-upload SBOM
                new_sbom_uri = await self.sigstore_client.generate_sbom(
                    artifact_path=artifact_path,
                    artifact_id=artifact_id,
                    ticket_id=ticket_id
                )
                if new_sbom_uri and new_sbom_uri.startswith('s3://'):
                    sbom_uri = new_sbom_uri
                else:
                    logger.error(
                        'sbom_reupload_failed',
                        artifact_id=artifact_id
                    )
                    return False
            else:
                logger.error(
                    'sbom_integrity_failed_max_retries',
                    artifact_id=artifact_id,
                    sbom_uri=sbom_uri,
                    attempts=max_retries + 1
                )

        return False
