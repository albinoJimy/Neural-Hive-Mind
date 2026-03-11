import asyncio
import time
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Any
import structlog

from ..models.pipeline_context import PipelineContext
from ..clients.sonarqube_client import SonarQubeClient
from ..clients.snyk_client import SnykClient
from ..clients.trivy_client import TrivyClient
from ..clients.mcp_tool_catalog_client import MCPToolCatalogClient
from ..clients.mongodb_client import MongoDBClient
from ..observability.metrics import CodeForgeMetrics

logger = structlog.get_logger()


async def _run_with_timing(
    coro,
    validation_type: str,
    tool_name: str
) -> Tuple[Any, int]:
    """
    Wrapper que mede o tempo de execução de uma validação.

    Args:
        coro: Coroutine a executar
        validation_type: Tipo de validação (ex: 'sast', 'dast')
        tool_name: Nome da ferramenta (ex: 'sonarqube', 'snyk')

    Returns:
        Tupla (resultado, execution_time_ms)
    """
    start_time = time.perf_counter()
    try:
        result = await coro
        elapsed = time.perf_counter() - start_time
        execution_time_ms = int(elapsed * 1000)
        logger.info(
            'validation_timing_measured',
            validation_type=validation_type,
            tool_name=tool_name,
            execution_time_ms=execution_time_ms
        )
        return result, execution_time_ms
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        execution_time_ms = int(elapsed * 1000)
        logger.error(
            'validation_timing_error',
            validation_type=validation_type,
            tool_name=tool_name,
            execution_time_ms=execution_time_ms,
            error=str(e)
        )
        raise


class Validator:
    """Subpipeline 3: Validações Estáticas e Semânticas (SAST/DAST/License)"""

    def __init__(
        self,
        sonarqube_client: SonarQubeClient,
        snyk_client: SnykClient,
        trivy_client: TrivyClient,
        mcp_client: Optional[MCPToolCatalogClient] = None,
        mongodb_client: Optional[MongoDBClient] = None,
        metrics: Optional[CodeForgeMetrics] = None
    ):
        self.sonarqube_client = sonarqube_client
        self.snyk_client = snyk_client
        self.trivy_client = trivy_client
        self.mcp_client = mcp_client
        self.mongodb_client = mongodb_client
        self.metrics = metrics

        # Importar e inicializar LicenseValidator lazy
        self._license_validator = None

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
                        _run_with_timing(
                            self.sonarqube_client.analyze_code(project_key, workspace_path),
                            validation_type='sast',
                            tool_name='sonarqube'
                        )
                    )
                elif 'snyk' in tool_name:
                    validation_tasks.append(
                        _run_with_timing(
                            self.snyk_client.scan_dependencies(workspace_path, language),
                            validation_type='sca',
                            tool_name='snyk'
                        )
                    )
                elif 'trivy' in tool_name:
                    validation_tasks.append(
                        _run_with_timing(
                            self.trivy_client.scan_filesystem(workspace_path),
                            validation_type='sast',
                            tool_name='trivy'
                        )
                    )
                elif 'license' in tool_name or 'sbom' in tool_name:
                    # Validação de licenças via SBOM
                    validation_tasks.append(
                        _run_with_timing(
                            self._validate_license_from_sbom(context),
                            validation_type='license',
                            tool_name='license-validator'
                        )
                    )
                # Adicionar mais ferramentas conforme necessário

            if not validation_tasks:
                # Se MCP retornar ferramentas não mapeadas, usar fallback padrão
                logger.info('mcp_validation_tools_unmapped_fallback_default')
                validation_tasks = [
                    _run_with_timing(
                        self.sonarqube_client.analyze_code(project_key, workspace_path),
                        validation_type='sast',
                        tool_name='sonarqube'
                    ),
                    _run_with_timing(
                        self.snyk_client.scan_dependencies(workspace_path, language),
                        validation_type='sca',
                        tool_name='snyk'
                    ),
                    _run_with_timing(
                        self.trivy_client.scan_filesystem(workspace_path),
                        validation_type='sast',
                        tool_name='trivy'
                    )
                ]

                # Adicionar validação de licenças se mongodb_client disponível
                if self.mongodb_client:
                    validation_tasks.append(
                        _run_with_timing(
                            self._validate_license_from_sbom(context),
                            validation_type='license',
                            tool_name='license-validator'
                        )
                    )

        else:
            # Fallback: validações fixas com parâmetros dinâmicos
            logger.info('using_default_validation_tools')
            validation_tasks = [
                _run_with_timing(
                    self.sonarqube_client.analyze_code(project_key, workspace_path),
                    validation_type='sast',
                    tool_name='sonarqube'
                ),
                _run_with_timing(
                    self.snyk_client.scan_dependencies(workspace_path, language),
                    validation_type='sca',
                    tool_name='snyk'
                ),
                _run_with_timing(
                    self.trivy_client.scan_filesystem(workspace_path),
                    validation_type='sast',
                    tool_name='trivy'
                )
            ]

            # Adicionar validação de licenças se mongodb_client disponível
            if self.mongodb_client:
                validation_tasks.append(
                    _run_with_timing(
                        self._validate_license_from_sbom(context),
                        validation_type='license',
                        tool_name='license-validator'
                    )
                )

        # Executar validações em paralelo
        results_with_timing = await asyncio.gather(*validation_tasks, return_exceptions=True)

        # Inicializar contadores
        validation_success_count = 0
        validation_failure_count = 0

        # Separar resultados de tempos de execução
        results = []
        execution_times = {}  # {tool_name: execution_time_ms}

        for item in results_with_timing:
            if isinstance(item, Exception):
                # Se for exceção dentro da tupla (wrapper falhou)
                if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], int):
                    pass  # será tratado abaixo
                else:
                    logger.error('validation_error', error=str(item))
                    validation_failure_count += 1
                    continue

            if isinstance(item, tuple) and len(item) == 2:
                result, exec_time = item
                results.append(result)
                if result and hasattr(result, 'tool_name'):
                    execution_times[result.tool_name] = exec_time
                    # Armazenar tempo no resultado para uso posterior
                    if hasattr(result, 'metadata'):
                        result.metadata['execution_time_ms'] = exec_time
                    elif hasattr(result, '__dict__'):
                        result.__dict__['execution_time_ms'] = exec_time
            else:
                results.append(item)

        for result in results:
            if isinstance(result, Exception):
                logger.error('validation_error', error=str(result))
                validation_failure_count += 1
                continue

            context.add_validation(result)
            validation_success_count += 1

            if self.metrics:
                self.metrics.validations_run_total.labels(
                    validation_type=result.validation_type,
                    tool=result.tool_name
                ).inc()

                self.metrics.validation_issues_found.labels(
                    severity='critical'
                ).observe(result.critical_issues)
                self.metrics.validation_issues_found.labels(
                    severity='high'
                ).observe(result.high_issues)
                self.metrics.validation_issues_found.labels(
                    severity='medium'
                ).observe(result.medium_issues)
                self.metrics.validation_issues_found.labels(
                    severity='low'
                ).observe(result.low_issues)

                if result.score is not None:
                    self.metrics.quality_score.observe(result.score)

            logger.info(
                'validation_completed',
                type=result.validation_type,
                status=result.status,
                issues=result.issues_count
            )

        # Enviar feedback para MCP Tool Catalog
        if self.mcp_client and getattr(context, 'mcp_selection_id', None):
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
            validation_tools = [
                t for t in getattr(context, 'selected_tools', [])
                if t.get('category') == 'VALIDATION'
            ]

            if not context.mcp_selection_id or not validation_tools:
                return

            # Calcular success rate
            total = success_count + failure_count
            success_rate = success_count / total if total > 0 else 0.0

            # Obter tempos de execução dos resultados de validação
            validation_results = getattr(context, 'validation_results', [])
            execution_times_by_tool = {}
            for result in validation_results:
                if hasattr(result, 'tool_name') and hasattr(result, 'metadata'):
                    exec_time = result.metadata.get('execution_time_ms')
                    if exec_time:
                        execution_times_by_tool[result.tool_name] = exec_time

            # Enviar feedback para cada ferramenta VALIDATION
            for tool in validation_tools:
                tool_id = tool.get('tool_id', '')
                # Buscar tempo de execução ou usar média dos tempos disponíveis
                execution_time_ms = execution_times_by_tool.get(tool_id, 0)
                if execution_time_ms == 0 and execution_times_by_tool:
                    # Se não encontrou por tool_id exato, usar média
                    execution_time_ms = int(sum(execution_times_by_tool.values()) / len(execution_times_by_tool))

                feedback = {
                    "selection_id": context.mcp_selection_id,
                    "tool_id": tool_id,
                    "success": success_rate > 0.5,  # Threshold 50%
                    "execution_time_ms": execution_time_ms,
                    "metadata": {
                        "success_rate": success_rate,
                        "success_count": success_count,
                        "failure_count": failure_count
                    }
                }

                try:
                    result = await asyncio.wait_for(
                        self.mcp_client.send_tool_feedback(feedback),
                        timeout=3.0
                    )
                    status = 'success' if result else 'failure'
                    if self.metrics:
                        self.metrics.mcp_feedback_sent_total.labels(status=status).inc()
                    if result:
                        context.mcp_feedback_sent = True
                    logger.info(
                        'mcp_feedback_sent',
                        selection_id=context.mcp_selection_id,
                        tool_id=tool_id,
                        success=feedback.get('success'),
                        execution_time_ms=feedback.get('execution_time_ms')
                    )
                except (asyncio.TimeoutError, Exception) as e:
                    if self.metrics:
                        self.metrics.mcp_feedback_sent_total.labels(status='failure').inc()
                    logger.warning('mcp_feedback_timeout', error=str(e))
                    # Continuar execução sem bloquear

            logger.info('mcp_feedback_aggregate', selection_id=context.mcp_selection_id, success_rate=success_rate)

        except Exception as e:
            logger.error('mcp_feedback_failed', error=str(e))

    async def _validate_license_from_sbom(self, context: PipelineContext):
        """
        Valida licenças analisando o SBOM do artefato.

        Args:
            context: Contexto do pipeline

        Returns:
            ValidationResult com análise de licenças
        """
        from .license_validator import LicenseValidator

        # Lazy load do LicenseValidator
        if self._license_validator is None:
            self._license_validator = LicenseValidator(
                require_sbom=False  # SBOM opcional para não bloquear pipelines
            )

        # Obter artefato mais recente
        artifact = context.get_latest_artifact()
        if not artifact:
            logger.warning('no_artifact_for_license_validation', pipeline_id=context.pipeline_id)
            from ..models.artifact import ValidationResult, ValidationType, ValidationStatus
            return ValidationResult(
                validation_type=ValidationType.LICENSE_CHECK,
                tool_name='license-validator',
                tool_version='1.0.0',
                status=ValidationStatus.SKIPPED,
                score=0.0,
                issues_count=0,
                critical_issues=0,
                high_issues=0,
                medium_issues=0,
                low_issues=0,
                executed_at=datetime.now(),
                duration_ms=0,
                report_uri=None,
                metadata={'message': 'No artifact found for license validation'}
            )

        # Obter SBOM do MongoDB
        sbom_data = None
        if self.mongodb_client:
            sbom_data = await self.mongodb_client.get_artifact_sbom(artifact.artifact_id)

        # Executar validação de licenças
        result = await self._license_validator.validate_licenses(
            sbom_data=sbom_data,
            artifact_id=artifact.artifact_id,
            ticket_id=context.ticket.ticket_id
        )

        logger.info(
            'license_validation_completed',
            artifact_id=artifact.artifact_id,
            status=result.status,
            score=result.score
        )

        return result
