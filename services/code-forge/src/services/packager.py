import structlog

from ..models.pipeline_context import PipelineContext
from ..clients.sigstore_client import SigstoreClient

logger = structlog.get_logger()


class Packager:
    """Subpipeline 5: Empacotamento e Assinatura"""

    def __init__(self, sigstore_client: SigstoreClient):
        self.sigstore_client = sigstore_client

    async def package(self, context: PipelineContext):
        """
        Empacota e assina artefatos

        Args:
            context: Contexto do pipeline
        """
        logger.info('packaging_started', pipeline_id=context.pipeline_id)

        for artifact in context.generated_artifacts:
            # Gerar SBOM
            sbom_uri = await self.sigstore_client.generate_sbom(artifact.content_uri)
            artifact.sbom_uri = sbom_uri

            # Assinar artefato
            signature = await self.sigstore_client.sign_artifact(artifact.content_uri)
            artifact.signature = signature

            logger.info(
                'artifact_packaged',
                artifact_id=artifact.artifact_id,
                signed=bool(signature)
            )
