import asyncio
import structlog
import uuid
import time
from typing import List, Dict, Optional
from ..models.pipeline_context import PipelineContext
from ..models.template import Template, TemplateType, TemplateLanguage, TemplateMetadata, TemplateRegistry
from ..clients.git_client import GitClient
from ..clients.redis_client import RedisClient
from ..clients.mcp_tool_catalog_client import MCPToolCatalogClient
from ..observability.metrics import CodeForgeMetrics

logger = structlog.get_logger()


class TemplateSelector:
    """Subpipeline 1: Seleção de Template e Arquitetura"""

    def __init__(
        self,
        git_client: GitClient,
        redis_client: RedisClient,
        mcp_client: Optional[MCPToolCatalogClient] = None,
        metrics: Optional[CodeForgeMetrics] = None
    ):
        self.git_client = git_client
        self.redis_client = redis_client
        self.template_registry = TemplateRegistry()
        self.mcp_client = mcp_client  # Integração MCP Tool Catalog
        self.metrics = metrics

    async def select(self, context: PipelineContext) -> Template:
        """
        Seleciona template baseado em parâmetros do ticket

        Args:
            context: Contexto do pipeline

        Returns:
            Template selecionado
        """
        ticket = context.ticket
        params = ticket.parameters

        logger.info('template_selection_started', ticket_id=ticket.ticket_id)

        # === INTEGRAÇÃO MCP: Solicitar seleção de ferramentas ===
        if self.mcp_client:
            try:
                # Calcular complexity_score
                complexity_score = self._calculate_complexity_score(context)

                # Construir ToolSelectionRequest
                mcp_request = {
                    "request_id": str(uuid.uuid4()),
                    "ticket_id": ticket.ticket_id,
                    "plan_id": getattr(ticket, 'plan_id', None),
                    "intent_id": getattr(ticket, 'intent_id', None),
                    "correlation_id": getattr(ticket, 'correlation_id', str(uuid.uuid4())),
                    "artifact_type": params.get('artifact_type', 'CODE'),
                    "language": params.get('language', 'python'),
                    "complexity_score": complexity_score,
                    "required_categories": ["GENERATION", "VALIDATION"],
                    "constraints": {
                        "max_execution_time_ms": 300000,
                        "max_cost_score": 0.8,
                        "min_reputation_score": 0.6
                    },
                    "context": params
                }

                logger.info(
                    'mcp_selection_request_sent',
                    request_id=mcp_request['request_id'],
                    complexity_score=complexity_score,
                    required_categories=mcp_request['required_categories'],
                    artifact_type=mcp_request['artifact_type']
                )

                start_time = time.monotonic()

                # Chamar MCP Tool Catalog
                try:
                    mcp_response = await asyncio.wait_for(
                        self.mcp_client.request_tool_selection(mcp_request),
                        timeout=5.0
                    )
                    duration = time.monotonic() - start_time
                    if self.metrics:
                        status = 'success' if mcp_response else 'failure'
                        self.metrics.mcp_selection_requests_total.labels(status=status).inc()
                        self.metrics.mcp_selection_duration_seconds.observe(duration)
                except asyncio.TimeoutError as e:
                    duration = time.monotonic() - start_time
                    logger.warning('mcp_selection_timeout_using_fallback', error=str(e))
                    if self.metrics:
                        self.metrics.mcp_selection_requests_total.labels(status='timeout').inc()
                        self.metrics.mcp_selection_duration_seconds.observe(duration)
                    mcp_response = None
                except Exception as e:
                    duration = time.monotonic() - start_time
                    logger.warning('mcp_selection_timeout_using_fallback', error=str(e))
                    if self.metrics:
                        self.metrics.mcp_selection_requests_total.labels(status='failure').inc()
                        self.metrics.mcp_selection_duration_seconds.observe(duration)
                    mcp_response = None

                if mcp_response:
                    # Armazenar ferramentas selecionadas no contexto
                    context.mcp_selection_id = mcp_response.get("request_id")
                    context.selected_tools = mcp_response.get("selected_tools", [])

                    # Determinar generation_method baseado em ferramentas
                    generation_method = self._map_tools_to_generation_method(
                        context.selected_tools
                    )
                    context.generation_method = generation_method

                    logger.info(
                        'mcp_selection_response_received',
                        selection_id=mcp_response.get('request_id'),
                        tools_count=len(mcp_response.get('selected_tools', [])),
                        total_fitness=mcp_response.get('total_fitness_score'),
                        selection_method=mcp_response.get('selection_method')
                    )

                    if self.metrics:
                        for tool in context.selected_tools:
                            self.metrics.mcp_tools_selected_total.labels(
                                category=tool.get('category', 'unknown')
                            ).inc()

                    logger.info(
                        'mcp_tools_selected',
                        selection_id=context.mcp_selection_id,
                        tools_count=len(context.selected_tools),
                        generation_method=generation_method
                    )

            except Exception as e:
                logger.error('mcp_selection_failed', error=str(e))
                # Fallback para template normal
        # === FIM INTEGRAÇÃO MCP ===

        # Extrair critérios de seleção
        criteria = {
            'type': params.get('artifact_type', 'MICROSERVICE'),
            'language': params.get('language', 'PYTHON'),
            'tags': params.get('tags', [])
        }

        # Consultar cache Redis
        cached_template = await self.redis_client.get_cached_template(
            f"{criteria['type']}:{criteria['language']}"
        )

        if cached_template:
            logger.info('template_cache_hit', criteria=criteria)
            context.selected_template = cached_template
            return cached_template

        # Cache miss: carregar templates do Git
        await self.git_client.clone_templates_repo()

        # Mock: criar template genérico
        template = Template(
            template_id='microservice-python-v1',
            metadata=TemplateMetadata(
                name='Python Microservice',
                version='1.0.0',
                description='Template base para microserviço Python',
                author='Neural Hive Team',
                tags=['microservice', 'python', 'fastapi'],
                language=TemplateLanguage.PYTHON,
                type=TemplateType.MICROSERVICE
            ),
            parameters=[],
            content_path='/app/templates/microservice-python',
            examples={}
        )

        # Cachear template
        await self.redis_client.cache_template(template.template_id, template)

        context.selected_template = template
        logger.info('template_selected', template_id=template.template_id)

        return template

    def _calculate_complexity_score(self, context: PipelineContext) -> float:
        """
        Calcula complexity_score baseado em tarefas, dependências, risk_band.

        Args:
            context: Contexto do pipeline

        Returns:
            Score de complexidade entre 0.0 e 1.0
        """
        ticket = context.ticket

        # Número de tarefas (normalizado para max 20)
        num_tasks = len(ticket.parameters.get('tasks', []))
        task_score = min(num_tasks / 20.0, 1.0) * 0.4

        # Número de dependências (normalizado para max 50)
        num_dependencies = len(getattr(ticket, 'dependencies', []))
        dependency_score = min(num_dependencies / 50.0, 1.0) * 0.3

        # Risk band
        risk_band = context.metadata.get('risk_band', 'LOW')
        risk_scores = {
            'LOW': 0.2,
            'MEDIUM': 0.5,
            'HIGH': 0.8,
            'CRITICAL': 1.0
        }
        risk_score = risk_scores.get(risk_band, 0.2) * 0.3

        complexity = task_score + dependency_score + risk_score

        return min(complexity, 1.0)

    def _map_tools_to_generation_method(self, selected_tools: List[Dict]) -> str:
        """
        Mapeia ferramentas selecionadas para GenerationMethod.

        Args:
            selected_tools: Lista de ferramentas selecionadas pelo MCP

        Returns:
            Generation method: LLM, HYBRID, TEMPLATE, ou HEURISTIC
        """
        if not selected_tools:
            return "TEMPLATE"

        tool_names = [t.get('tool_name', '').lower() for t in selected_tools]

        # Verificar se há ferramentas LLM
        llm_tools = ['github copilot', 'openai codex', 'tabnine', 'copilot']
        has_llm = any(llm in name for name in tool_names for llm in llm_tools)

        # Verificar se há ferramentas de template
        template_tools = [
            'cookiecutter', 'yeoman', 'openapi generator',
            'swagger codegen', 'jhipster'
        ]
        has_template = any(tmpl in name for name in tool_names for tmpl in template_tools)

        if has_llm and has_template:
            return "HYBRID"
        elif has_llm:
            return "LLM"
        elif has_template:
            return "TEMPLATE"
        else:
            return "HEURISTIC"
