import asyncio
import structlog
import uuid
import time
from pathlib import Path
from typing import List, Dict, Optional, Any
from ..models.pipeline_context import PipelineContext
from ..models.template import Template, TemplateType, TemplateMetadata, TemplateRegistry
from ..types.artifact_types import CodeLanguage
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
            'tags': params.get('tags', []),
            'template_version': params.get('template_version')  # Suporte a templates versionados
        }

        # Consultar cache Redis
        cached_template = await self.redis_client.get_cached_template(
            f"{criteria['type']}:{criteria['language']}"
        )

        if cached_template:
            logger.info('template_cache_hit', criteria=criteria)
            context.selected_template = cached_template
            return cached_template

        # Cache miss: carregar templates do Git e indexá-los
        await self._load_and_index_templates(criteria)

        # Buscar melhor template no registro
        search_results = self.template_registry.search(criteria)

        if search_results:
            template, score = search_results[0]
            logger.info(
                'template_selected_from_registry',
                template_id=template.template_id,
                match_score=score
            )
        else:
            # Fallback: criar template genérico baseado nos critérios
            template = self._create_fallback_template(criteria)
            logger.warning(
                'no_template_found_using_fallback',
                criteria=criteria,
                fallback_template_id=template.template_id
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
        llm_tools = ['github copilot', 'openai', 'openai codex', 'tabnine', 'copilot']
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

    async def _load_and_index_templates(self, criteria: Dict[str, Any]):
        """
        Carrega templates do repositório Git e indexa no TemplateRegistry.

        Suporta versionamento de templates via Git tags. Se template_version
        for especificado nos parâmetros, faz checkout da tag correspondente.

        Args:
            criteria: Critérios de busca para filtrar templates relevantes
        """
        try:
            # Verificar se foi solicitada uma versão específica de template
            template_version = criteria.get('template_version')
            current_tag = None

            if template_version:
                logger.info('template_version_requested', version=template_version)

                # Listar tags disponíveis
                tags = await self.git_client.list_tags()
                tag_names = [t['name'] for t in tags]

                # Encontrar a tag solicitada
                if template_version in tag_names:
                    success = await self.git_client.checkout_tag(template_version)
                    if success:
                        logger.info('template_version_checked_out', version=template_version)
                        current_tag = template_version
                    else:
                        logger.warning('template_version_checkout_failed', version=template_version)
                else:
                    logger.warning(
                        'template_version_not_found',
                        requested=template_version,
                        available=tag_names[:5]
                    )

            # Clone ou pull do repositório de templates
            await self.git_client.clone_templates_repo()

            # Se não fez checkout de tag, verificar se já estava em uma tag
            if not current_tag:
                current_tag = await self.git_client.get_current_tag()
                if current_tag:
                    logger.info('using_current_template_version', version=current_tag)

            # Escanear diretório de templates e criar entradas no registro
            templates_path = self.git_client.local_path / "templates"

            if not templates_path.exists():
                logger.warning('templates_directory_not_found', path=str(templates_path))
                return

            # Mapeamento de padrões de template para tipos
            type_patterns = {
                'microservice': TemplateType.MICROSERVICE,
                'function': TemplateType.FUNCTION,
                'terraform': TemplateType.IAC_TERRAFORM,
                'helm': TemplateType.IAC_HELM,
                'test': TemplateType.TEST_SUITE,
                'opa': TemplateType.POLICY_OPA
            }

            # Mapeamento de extensões para linguagens
            lang_extensions = {
                'py': CodeLanguage.PYTHON,
                'js': CodeLanguage.JAVASCRIPT,
                'ts': CodeLanguage.TYPESCRIPT,
                'go': CodeLanguage.GO,
                'java': CodeLanguage.JAVA,
                'rs': CodeLanguage.RUST
            }

            templates_count = 0
            for template_dir in templates_path.iterdir():
                if not template_dir.is_dir():
                    continue

                # Ler metadados do template (se existirem)
                metadata_file = template_dir / "template.yaml"
                if metadata_file.exists():
                    template = self._load_template_from_yaml(template_dir, metadata_file)
                else:
                    template = self._create_template_from_directory(template_dir, type_patterns, lang_extensions)

                if template:
                    self.template_registry.add_template(template)
                    templates_count += 1

            logger.info(
                'templates_indexed',
                count=templates_count,
                registry_size=len(self.template_registry.templates)
            )

        except Exception as e:
            logger.error('template_indexing_failed', error=str(e))

    def _load_template_from_yaml(self, template_dir, metadata_file) -> Optional[Template]:
        """Carrega template a partir de arquivo YAML de metadados."""
        try:
            import yaml
            with open(metadata_file) as f:
                metadata = yaml.safe_load(f)

            return Template(
                template_id=metadata.get('id', template_dir.name),
                metadata=TemplateMetadata(
                    name=metadata.get('name', template_dir.name),
                    version=metadata.get('version', '1.0.0'),
                    description=metadata.get('description', ''),
                    author=metadata.get('author', 'Neural Hive Team'),
                    tags=metadata.get('tags', []),
                    language=CodeLanguage(metadata.get('language', 'PYTHON')),
                    type=TemplateType(metadata.get('type', 'MICROSERVICE'))
                ),
                parameters=[],
                content_path=str(template_dir),
                examples=metadata.get('examples', {})
            )
        except Exception as e:
            logger.warning('yaml_template_load_failed', dir=str(template_dir), error=str(e))
            return None

    def _create_template_from_directory(
        self, template_dir, type_patterns, lang_extensions
    ) -> Optional[Template]:
        """Cria entrada de template a partir da estrutura do diretório."""
        dir_name = template_dir.name.lower()
        template_id = f"auto-{dir_name}"

        # Inferir tipo
        template_type = TemplateType.MICROSERVICE
        for pattern, ptype in type_patterns.items():
            if pattern in dir_name:
                template_type = ptype
                break

        # Inferir linguagem
        template_lang = CodeLanguage.PYTHON
        for ext, lang in lang_extensions.items():
            if any(f.suffix == f'.{ext}' for f in template_dir.iterdir() if f.is_file()):
                template_lang = lang
                break

        return Template(
            template_id=template_id,
            metadata=TemplateMetadata(
                name=dir_name.replace('-', ' ').title(),
                version='1.0.0',
                description=f'Template auto-detectado: {dir_name}',
                author='Neural Hive Team',
                tags=[template_type.value.lower(), template_lang.value.lower()],
                language=template_lang,
                type=template_type
            ),
            parameters=[],
            content_path=str(template_dir),
            examples={}
        )

    def _create_fallback_template(self, criteria: Dict[str, Any]) -> Template:
        """
        Cria template genérico baseado nos critérios quando nenhum template é encontrado.

        Args:
            criteria: Critérios de seleção

        Returns:
            Template de fallback
        """
        artifact_type = criteria.get('type', 'MICROSERVICE')
        language = criteria.get('language', 'PYTHON')

        # Mapear tipos para templates de fallback
        type_to_template_id = {
            'MICROSERVICE': f'microservice-{language.lower()}-v1',
            'FUNCTION': f'function-{language.lower()}-v1',
            'IAC_TERRAFORM': 'terraform-module-v1',
            'IAC_HELM': 'helm-chart-v1',
            'TEST_SUITE': f'test-suite-{language.lower()}-v1',
            'POLICY_OPA': 'opa-policy-v1'
        }

        template_id = type_to_template_id.get(artifact_type, 'generic-template-v1')

        # Normalizar linguagem para enum
        try:
            template_lang = CodeLanguage[language.upper()]
        except KeyError:
            template_lang = CodeLanguage.PYTHON

        # Normalizar tipo para enum
        try:
            template_type = TemplateType[artifact_type]
        except KeyError:
            template_type = TemplateType.MICROSERVICE

        return Template(
            template_id=template_id,
            metadata=TemplateMetadata(
                name=f'{language} {artifact_type.replace("_", " ")}',
                version='1.0.0',
                description=f'Template base para {artifact_type} em {language}',
                author='Neural Hive Team',
                tags=[artifact_type.lower(), language.lower()],
                language=template_lang,
                type=template_type
            ),
            parameters=[],
            content_path=f'/app/templates/{template_id}',
            examples={}
        )
