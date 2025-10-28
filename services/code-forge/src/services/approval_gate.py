import structlog

from ..models.pipeline_context import PipelineContext
from ..clients.git_client import GitClient

logger = structlog.get_logger()


class ApprovalGate:
    """Subpipeline 6: Gate de Aprovação"""

    def __init__(
        self,
        git_client: GitClient,
        auto_approval_threshold: float = 0.9,
        min_quality_score: float = 0.5
    ):
        self.git_client = git_client
        self.auto_approval_threshold = auto_approval_threshold
        self.min_quality_score = min_quality_score

    async def check_approval(self, context: PipelineContext):
        """
        Verifica se requer aprovação manual

        Args:
            context: Contexto do pipeline
        """
        logger.info('approval_gate_started', pipeline_id=context.pipeline_id)

        # Calcular score de qualidade
        quality_score = context.calculate_quality_score()

        # Verificar issues críticos
        has_critical = context.has_critical_issues()

        # Determinar aprovação
        if quality_score >= self.auto_approval_threshold and not has_critical:
            logger.info('auto_approved', score=quality_score)
            context.metadata['approval'] = 'auto'

        elif quality_score < self.min_quality_score or has_critical:
            logger.warning('auto_rejected', score=quality_score, critical=has_critical)
            context.metadata['approval'] = 'rejected'

        else:
            # Requer revisão manual
            logger.info('requires_manual_review', score=quality_score)

            # Criar Merge Request
            branch_name = f'code-forge-{context.pipeline_id[:8]}'
            mr_url = await self.git_client.create_merge_request(
                branch_name,
                f'Code Forge Pipeline {context.pipeline_id[:8]}',
                f'Quality Score: {quality_score:.2f}\nArtifacts: {len(context.generated_artifacts)}'
            )

            context.metadata['approval'] = 'manual'
            context.metadata['git_mr_url'] = mr_url
