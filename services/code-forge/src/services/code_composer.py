import uuid
import hashlib
from datetime import datetime
from typing import Optional
import structlog

from ..models.pipeline_context import PipelineContext
from ..models.artifact import CodeForgeArtifact, ArtifactType, GenerationMethod
from ..clients.mongodb_client import MongoDBClient
from ..clients.llm_client import LLMClient
from ..clients.mcp_tool_catalog_client import MCPToolCatalogClient

logger = structlog.get_logger()


class CodeComposer:
    """Subpipeline 2: Composição de Código e IaC"""

    def __init__(
        self,
        mongodb_client: MongoDBClient,
        llm_client: Optional[LLMClient] = None,
        mcp_client: Optional[MCPToolCatalogClient] = None
    ):
        self.mongodb_client = mongodb_client
        self.llm_client = llm_client
        self.mcp_client = mcp_client

    async def compose(self, context: PipelineContext):
        """
        Gera artefatos baseados no template selecionado

        Args:
            context: Contexto do pipeline
        """
        template = context.selected_template
        ticket = context.ticket

        logger.info('code_composition_started', template_id=template.template_id)

        # === INTEGRAÇÃO MCP: Determinar método de geração ===
        generation_method = getattr(context, 'generation_method', 'TEMPLATE')

        if generation_method == 'LLM' and self.llm_client:
            code_content, confidence_score = await self._generate_via_llm(context)
        elif generation_method == 'HYBRID' and self.llm_client:
            code_content, confidence_score = await self._generate_hybrid(context)
        else:
            # Fallback para template (método original)
            code_content = self._generate_python_microservice(ticket.parameters)
            confidence_score = 0.85

        # Calcular hash
        content_hash = hashlib.sha256(code_content.encode()).hexdigest()

        # Salvar no MongoDB
        artifact_id = str(uuid.uuid4())
        await self.mongodb_client.save_artifact_content(artifact_id, code_content)

        # Criar artefato
        artifact = CodeForgeArtifact(
            artifact_id=artifact_id,
            ticket_id=ticket.ticket_id,
            plan_id=getattr(ticket, 'plan_id', None),
            intent_id=getattr(ticket, 'intent_id', None),
            decision_id=getattr(ticket, 'decision_id', None),
            correlation_id=getattr(ticket, 'correlation_id', str(uuid.uuid4())),
            trace_id=context.trace_id,
            span_id=context.span_id,
            artifact_type=ArtifactType.CODE,
            language=ticket.parameters.get('language', 'python'),
            template_id=template.template_id,
            confidence_score=confidence_score,
            generation_method=GenerationMethod[generation_method],
            content_uri=f'mongodb://artifacts/{artifact_id}',
            content_hash=content_hash,
            created_at=datetime.now(),
            metadata={
                'mcp_selection_id': getattr(context, 'mcp_selection_id', None),
                'mcp_tools_used': [
                    t.get('tool_name') for t in getattr(context, 'selected_tools', [])
                ]
            }
        )

        context.add_artifact(artifact)
        logger.info(
            'artifact_generated',
            artifact_id=artifact_id,
            type=artifact.artifact_type,
            generation_method=generation_method,
            confidence=confidence_score
        )

    async def _generate_via_llm(self, context: PipelineContext) -> tuple[str, float]:
        """
        Gera código via LLM com RAG context.

        Args:
            context: Contexto do pipeline

        Returns:
            Tupla (código_gerado, confidence_score)
        """
        ticket = context.ticket
        template = context.selected_template

        # Construir prompt
        prompt = f"""Generate production-ready {ticket.parameters.get('language', 'Python')} code for:

Service: {ticket.parameters.get('service_name', 'my-service')}
Type: {ticket.parameters.get('artifact_type', 'microservice')}

Requirements:
{chr(10).join(f'- {req}' for req in ticket.parameters.get('requirements', []))}

Template base: {template.metadata.name}

Generate complete, well-structured code following best practices."""

        # Gerar via LLM
        constraints = {
            'language': ticket.parameters.get('language', 'python'),
            'framework': ticket.parameters.get('framework', ''),
            'patterns': ticket.parameters.get('patterns', []),
            'max_lines': ticket.parameters.get('max_lines', 1000)
        }

        llm_result = await self.llm_client.generate_code(
            prompt=prompt,
            constraints=constraints,
            temperature=0.2
        )

        if not llm_result:
            # Fallback para template se LLM falhar
            return self._generate_python_microservice(ticket.parameters), 0.75

        code_content = llm_result.get('code', '')
        confidence_score = llm_result.get('confidence_score', 0.7)

        return code_content, confidence_score

    async def _generate_hybrid(self, context: PipelineContext) -> tuple[str, float]:
        """
        Gera código usando abordagem híbrida (Template + LLM).

        Args:
            context: Contexto do pipeline

        Returns:
            Tupla (código_gerado, confidence_score)
        """
        # 1. Gerar base via template
        base_code = self._generate_python_microservice(context.ticket.parameters)

        # 2. Enriquecer via LLM
        enhancement_prompt = f"""Enhance this code with production-ready features:

{base_code}

Add:
- Error handling
- Logging
- Configuration management
- Health checks
- Metrics

Maintain the existing structure."""

        constraints = {
            'language': context.ticket.parameters.get('language', 'python'),
            'framework': context.ticket.parameters.get('framework', ''),
            'patterns': ['error_handling', 'logging', 'metrics'],
            'max_lines': 2000
        }

        llm_result = await self.llm_client.generate_code(
            prompt=enhancement_prompt,
            constraints=constraints,
            temperature=0.3
        )

        if not llm_result:
            # Fallback para código base se enriquecimento falhar
            return base_code, 0.85

        enhanced_code = llm_result.get('code', base_code)
        llm_confidence = llm_result.get('confidence_score', 0.7)

        # Confidence híbrido (média ponderada)
        hybrid_confidence = (0.6 * llm_confidence) + (0.4 * 0.85)  # 0.85 = template confidence

        return enhanced_code, hybrid_confidence

    def _generate_python_microservice(self, params: dict) -> str:
        """Gera código Python baseado em template"""
        service_name = params.get('service_name', 'my-service')
        return f'''# {service_name} - Generated by Neural Code Forge
from fastapi import FastAPI

app = FastAPI(title="{service_name}")

@app.get("/health")
async def health():
    return {{"status": "healthy"}}
'''
