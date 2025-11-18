import asyncio
from typing import Optional, List, Dict
import structlog

from ..models.pipeline_context import PipelineContext
from ..clients.sonarqube_client import SonarQubeClient
from ..clients.snyk_client import SnykClient
from ..clients.trivy_client import TrivyClient
from ..clients.mcp_tool_catalog_client import MCPToolCatalogClient

logger = structlog.get_logger()


class Validator:
    """Subpipeline 3: Validações Estáticas e Semânticas (SAST/DAST)"""

    def __init__(
        self,
        sonarqube_client: SonarQubeClient,
        snyk_client: SnykClient,
        trivy_client: TrivyClient,
        mcp_client: Optional[MCPToolCatalogClient] = None
    ):
        self.sonarqube_client = sonarqube_client
        self.snyk_client = snyk_client
        self.trivy_client = trivy_client
        self.mcp_client = mcp_client

    async def validate(self, context: PipelineContext):
        """
        Executa validações em paralelo

        Args:
            context: Contexto do pipeline
        """
        logger.info('validation_started', pipeline_id=context.pipeline_id)

        # === Obter informações dinâmicas do contexto ===
        # Extrair linguagem do ticket
        language = context.ticket.parameters.get('language', 'python')

        # Obter workspace path do contexto ou usar path temporário baseado no pipeline_id
        workspace_path = context.code_workspace_path or f'/tmp/code-forge/{context.pipeline_id}'

        # Obter project key do ticket ou usar ticket_id
        project_key = context.ticket.parameters.get('project_key', context.ticket.ticket_id)

        logger.info(
            'validation_context_extracted',
            language=language,
            workspace_path=workspace_path,
            project_key=project_key
        )

        # === INTEGRAÇÃO MCP: Validação dinâmica baseada em ferramentas selecionadas ===
        validation_tasks = []

        # Verificar se há ferramentas VALIDATION selecionadas via MCP
        selected_tools = getattr(context, 'selected_tools', [])
        validation_tools = [
            t for t in selected_tools
            if t.get('category') == 'VALIDATION'
        ]

        if validation_tools:
            # Usar ferramentas selecionadas dinamicamente
            logger.info('using_mcp_validation_tools', count=len(validation_tools))

            for tool in validation_tools:
                tool_name = tool.get('tool_name', '').lower()

                if 'sonarqube' in tool_name:
                    validation_tasks.append(
                        self.sonarqube_client.analyze_code(project_key, workspace_path)
                    )
                elif 'snyk' in tool_name:
                    validation_tasks.append(
                        self.snyk_client.scan_dependencies(workspace_path, language)
                    )
                elif 'trivy' in tool_name:
                    validation_tasks.append(
                        self.trivy_client.scan_filesystem(workspace_path)
                    )
                # Adicionar mais ferramentas conforme necessário

        else:
            # Fallback: validações fixas com parâmetros dinâmicos
            logger.info('using_default_validation_tools')
            validation_tasks = [
                self.sonarqube_client.analyze_code(project_key, workspace_path),
                self.snyk_client.scan_dependencies(workspace_path, language),
                self.trivy_client.scan_filesystem(workspace_path)
            ]

        # Executar validações em paralelo
        results = await asyncio.gather(*validation_tasks, return_exceptions=True)

        # Processar resultados
        validation_success_count = 0
        validation_failure_count = 0

        for result in results:
            if isinstance(result, Exception):
                logger.error('validation_error', error=str(result))
                validation_failure_count += 1
                continue

            context.add_validation(result)
            validation_success_count += 1
            logger.info(
                'validation_completed',
                type=result.validation_type,
                status=result.status,
                issues=result.issues_count
            )

        # Enviar feedback para MCP Tool Catalog
        if self.mcp_client and hasattr(context, 'mcp_selection_id'):
            await self._send_mcp_feedback(
                context,
                validation_success_count,
                validation_failure_count
            )

    async def _send_mcp_feedback(
        self,
        context: PipelineContext,
        success_count: int,
        failure_count: int
    ):
        """
        Envia feedback para MCP Tool Catalog sobre ferramentas de validação.

        Args:
            context: Contexto do pipeline
            success_count: Número de validações bem-sucedidas
            failure_count: Número de validações que falharam
        """
        try:
            # Calcular success rate
            total = success_count + failure_count
            success_rate = success_count / total if total > 0 else 0.0

            # Enviar feedback para cada ferramenta VALIDATION
            validation_tools = [
                t for t in getattr(context, 'selected_tools', [])
                if t.get('category') == 'VALIDATION'
            ]

            for tool in validation_tools:
                feedback = {
                    "selection_id": context.mcp_selection_id,
                    "tool_id": tool.get('tool_id'),
                    "success": success_rate > 0.5,  # Threshold 50%
                    "execution_time_ms": 0,  # TODO: medir tempo real
                    "metadata": {
                        "success_rate": success_rate,
                        "success_count": success_count,
                        "failure_count": failure_count
                    }
                }

                await self.mcp_client.send_tool_feedback(feedback)

            logger.info(
                'mcp_feedback_sent',
                selection_id=context.mcp_selection_id,
                success_rate=success_rate
            )

        except Exception as e:
            logger.error('mcp_feedback_failed', error=str(e))
