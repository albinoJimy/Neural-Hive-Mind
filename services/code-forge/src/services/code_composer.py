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
from ..clients.analyst_agents_client import AnalystAgentsClient

logger = structlog.get_logger()


class CodeComposer:
    """Subpipeline 2: Composição de Código e IaC"""

    def __init__(
        self,
        mongodb_client: MongoDBClient,
        llm_client: Optional[LLMClient] = None,
        analyst_client: Optional[AnalystAgentsClient] = None,
        mcp_client: Optional[MCPToolCatalogClient] = None
    ):
        self.mongodb_client = mongodb_client
        self.llm_client = llm_client
        self.analyst_client = analyst_client
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
        generation_method_str = getattr(context, 'generation_method', None)
        if generation_method_str:
            generation_method_str = generation_method_str.upper()
        if not generation_method_str or generation_method_str not in GenerationMethod.__members__:
            generation_method_str = 'TEMPLATE'

        # Validar e normalizar generation_method
        generation_method_enum = GenerationMethod.__members__.get(
            generation_method_str,
            GenerationMethod.TEMPLATE
        )

        if generation_method_str not in GenerationMethod.__members__:
            logger.warning(
                'invalid_generation_method_using_fallback',
                requested_method=generation_method_str,
                fallback_method='TEMPLATE'
            )
            generation_method_str = 'TEMPLATE'

        if generation_method_str == 'LLM' and self.llm_client:
            code_content, confidence_score, effective_method = await self._generate_via_llm(context)
            generation_method_enum = GenerationMethod.__members__.get(
                effective_method,
                GenerationMethod.LLM
            )
        elif generation_method_str == 'HYBRID' and self.llm_client:
            code_content, confidence_score = await self._generate_hybrid(context)
            effective_method = 'HYBRID'
        elif generation_method_str == 'HEURISTIC':
            code_content = self._generate_heuristic(ticket.parameters)
            confidence_score = 0.78
            effective_method = 'HEURISTIC'
            generation_method_enum = GenerationMethod.__members__.get(
                'HEURISTIC',
                GenerationMethod.HEURISTIC
            )
        else:
            # Fallback para template (método original)
            code_content = self._generate_python_microservice(ticket.parameters)
            confidence_score = 0.85
            effective_method = 'TEMPLATE'
            generation_method_enum = GenerationMethod.TEMPLATE

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
            generation_method=generation_method_enum,
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
            generation_method=generation_method_str,
            confidence=confidence_score
        )

    async def _generate_via_llm(self, context: PipelineContext) -> tuple[str, float, str]:
        """
        Gera código via LLM com RAG context.

        Args:
            context: Contexto do pipeline

        Returns:
            Tupla (código_gerado, confidence_score, método_efetivo)
        """
        ticket = context.ticket

        # Construir RAG context
        rag_context = {"similar_templates": [], "architectural_patterns": []}
        if self.analyst_client:
            rag_context = await self._build_rag_context(ticket)

        # Construir prompt com RAG context
        prompt = self._build_llm_prompt(ticket, rag_context)

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
            # Fallback para heurística se LLM falhar
            logger.warning('llm_generation_failed_using_heuristic', ticket_id=ticket.ticket_id)
            return self._generate_heuristic(ticket.parameters), 0.75, 'HEURISTIC'

        code_content = llm_result.get('code', '')
        confidence_score = llm_result.get('confidence_score', 0.7)

        return code_content, confidence_score, 'LLM'

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

    async def _build_rag_context(self, ticket) -> dict:
        """
        Constrói contexto RAG buscando templates similares e padrões arquiteturais.

        Args:
            ticket: Execution ticket

        Returns:
            Dict com similar_templates e architectural_patterns
        """
        if not self.analyst_client:
            return {"similar_templates": [], "architectural_patterns": []}

        try:
            # Query text para busca semântica
            query_text = f"{ticket.parameters.get('description', '')} {ticket.parameters.get('language', '')} {ticket.parameters.get('artifact_type', '')}"

            # Gerar embedding do query text
            embedding = await self.analyst_client.get_embedding(query_text)

            # Buscar templates similares usando embedding
            similar_templates = []
            if embedding:
                similar_templates = await self.analyst_client.find_similar_templates(
                    embedding=embedding,
                    top_k=5
                )
            else:
                logger.warning(
                    'embedding_generation_failed_skipping_template_search',
                    ticket_id=ticket.ticket_id
                )

            # Buscar padrões arquiteturais
            architectural_patterns = await self.analyst_client.get_architectural_patterns(
                domain=ticket.parameters.get('domain', 'TECHNICAL')
            )

            logger.info(
                'rag_context_built',
                ticket_id=ticket.ticket_id,
                similar_templates_count=len(similar_templates),
                patterns_count=len(architectural_patterns)
            )

            return {
                "similar_templates": similar_templates,
                "architectural_patterns": architectural_patterns
            }

        except Exception as e:
            logger.error(
                'rag_context_failed',
                ticket_id=ticket.ticket_id,
                error=str(e)
            )
            return {"similar_templates": [], "architectural_patterns": []}

    def _build_llm_prompt(self, ticket, rag_context: dict) -> str:
        """
        Constrói prompt estruturado para LLM com contexto RAG.

        Args:
            ticket: Execution ticket
            rag_context: Contexto RAG com templates similares e padrões arquiteturais

        Returns:
            Prompt estruturado para LLM
        """
        similar_templates = rag_context.get('similar_templates', [])
        architectural_patterns = rag_context.get('architectural_patterns', [])

        # Construir seção de templates similares
        templates_section = ""
        if similar_templates:
            templates_section = "\nSimilar Templates (for reference):\n"
            templates_section += "\n".join([
                f"- {t.get('text', 'Unknown')[:100]}... (similarity: {t.get('similarity', 0.0):.2f})"
                for t in similar_templates[:3]
            ])

        # Construir seção de padrões arquiteturais
        patterns_section = ""
        if architectural_patterns:
            patterns_section = "\nArchitectural Patterns to follow:\n"
            patterns_section += "\n".join([f"- {p}" for p in architectural_patterns[:5]])

        # Prompt completo
        prompt = f"""Generate a {ticket.parameters.get('artifact_type', 'microservice')} in {ticket.parameters.get('language', 'Python')}.

Service: {ticket.parameters.get('service_name', 'my-service')}

Requirements:
{ticket.parameters.get('description', 'No description provided')}
{chr(10).join(f'- {req}' for req in ticket.parameters.get('requirements', []))}
{templates_section}
{patterns_section}

Generate production-ready code with:
- Proper error handling
- Type hints and docstrings
- Unit tests
- Logging and observability hooks
- Following best practices for {ticket.parameters.get('language', 'Python')}
"""

        return prompt

    def _generate_heuristic(self, parameters: dict) -> str:
        """
        Geração baseada em regras determinísticas.

        Args:
            parameters: Parâmetros do ticket

        Returns:
            Código gerado via heurística
        """
        artifact_type = parameters.get('artifact_type', 'MICROSERVICE').upper()
        language = parameters.get('language', 'python').lower()
        service_name = parameters.get('service_name', 'my-service')

        logger.info(
            'heuristic_generation_started',
            artifact_type=artifact_type,
            language=language,
            service_name=service_name
        )

        if artifact_type == 'MICROSERVICE':
            code = self._generate_python_microservice(parameters)
        elif artifact_type == 'LIBRARY':
            code = self._generate_python_library(parameters)
        elif artifact_type == 'SCRIPT':
            code = self._generate_python_script(parameters)
        else:
            # Default para microservice
            code = self._generate_python_microservice(parameters)

        logger.info(
            'heuristic_generation_completed',
            artifact_type=artifact_type,
            code_length=len(code)
        )

        return code

    def _generate_python_library(self, params: dict) -> str:
        """Gera biblioteca Python baseada em template"""
        library_name = params.get('service_name', 'my-lib')
        return f'''# {library_name} - Generated by Neural Code Forge
"""
{library_name} - A Python library
"""

__version__ = "0.1.0"


class {library_name.replace('-', '_').title()}:
    """Main library class"""

    def __init__(self):
        pass

    def process(self, data):
        """Process data"""
        return data
'''

    def _generate_python_script(self, params: dict) -> str:
        """Gera script Python baseado em template"""
        script_name = params.get('service_name', 'my-script')
        return f'''#!/usr/bin/env python3
# {script_name} - Generated by Neural Code Forge
"""
{script_name} - A Python script
"""

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Main function"""
    logger.info("Script started")
    # Add your logic here
    logger.info("Script completed")


if __name__ == "__main__":
    main()
'''

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
