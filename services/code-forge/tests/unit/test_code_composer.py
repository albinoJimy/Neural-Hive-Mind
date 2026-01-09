"""
Testes unitarios para CodeComposer.

Cobertura:
- Geracao via LLM (OpenAI/Anthropic/Ollama)
- Geracao HYBRID (Template + LLM enhancement)
- Geracao HEURISTIC (regras deterministicas)
- Geracao TEMPLATE (puro)
- RAG context via Analyst Agents
- Fallbacks em cascata
- Confidence scoring
- Metricas Prometheus
"""

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCodeComposerLLMGeneration:
    """Testes de geracao via LLM."""

    @pytest.mark.asyncio
    async def test_compose_via_llm_success(
        self,
        mock_mongodb_client,
        mock_llm_client,
        mock_analyst_client,
        sample_pipeline_context_with_mcp
    ):
        """Deve gerar codigo via LLM com sucesso."""
        from services.code_forge.src.services.code_composer import CodeComposer

        sample_pipeline_context_with_mcp.generation_method = 'LLM'

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=mock_llm_client,
            analyst_client=mock_analyst_client,
            mcp_client=None
        )

        await composer.compose(sample_pipeline_context_with_mcp)

        assert len(sample_pipeline_context_with_mcp.generated_artifacts) == 1
        artifact = sample_pipeline_context_with_mcp.generated_artifacts[0]
        assert artifact.confidence_score == 0.85
        mock_llm_client.generate_code.assert_called_once()

    @pytest.mark.asyncio
    async def test_compose_llm_with_rag_context(
        self,
        mock_mongodb_client,
        mock_llm_client,
        mock_analyst_client,
        sample_pipeline_context_with_mcp
    ):
        """Deve usar RAG context na geracao LLM."""
        from services.code_forge.src.services.code_composer import CodeComposer

        sample_pipeline_context_with_mcp.generation_method = 'LLM'

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=mock_llm_client,
            analyst_client=mock_analyst_client,
            mcp_client=None
        )

        await composer.compose(sample_pipeline_context_with_mcp)

        mock_analyst_client.get_embedding.assert_called_once()
        mock_analyst_client.find_similar_templates.assert_called_once()
        mock_analyst_client.get_architectural_patterns.assert_called_once()

    @pytest.mark.asyncio
    async def test_compose_llm_fallback_on_failure(
        self,
        mock_mongodb_client,
        mock_llm_client,
        sample_pipeline_context_with_mcp
    ):
        """Deve usar fallback heuristica quando LLM falha."""
        from services.code_forge.src.services.code_composer import CodeComposer

        sample_pipeline_context_with_mcp.generation_method = 'LLM'
        mock_llm_client.generate_code.return_value = None  # LLM falhou

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=mock_llm_client,
            analyst_client=None,
            mcp_client=None
        )

        await composer.compose(sample_pipeline_context_with_mcp)

        assert len(sample_pipeline_context_with_mcp.generated_artifacts) == 1
        artifact = sample_pipeline_context_with_mcp.generated_artifacts[0]
        # Fallback para heuristica tem confidence 0.75
        assert artifact.confidence_score == 0.75


class TestCodeComposerHybridGeneration:
    """Testes de geracao HYBRID."""

    @pytest.mark.asyncio
    async def test_compose_hybrid_success(
        self,
        mock_mongodb_client,
        mock_llm_client,
        sample_pipeline_context_with_mcp
    ):
        """Deve gerar codigo via HYBRID com sucesso."""
        from services.code_forge.src.services.code_composer import CodeComposer

        sample_pipeline_context_with_mcp.generation_method = 'HYBRID'

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=mock_llm_client,
            analyst_client=None,
            mcp_client=None
        )

        await composer.compose(sample_pipeline_context_with_mcp)

        assert len(sample_pipeline_context_with_mcp.generated_artifacts) == 1
        mock_llm_client.generate_code.assert_called_once()

    @pytest.mark.asyncio
    async def test_compose_hybrid_fallback_to_template(
        self,
        mock_mongodb_client,
        mock_llm_client,
        sample_pipeline_context_with_mcp
    ):
        """Deve usar template base quando LLM enhancement falha."""
        from services.code_forge.src.services.code_composer import CodeComposer

        sample_pipeline_context_with_mcp.generation_method = 'HYBRID'
        mock_llm_client.generate_code.return_value = None  # Enhancement falhou

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=mock_llm_client,
            analyst_client=None,
            mcp_client=None
        )

        await composer.compose(sample_pipeline_context_with_mcp)

        assert len(sample_pipeline_context_with_mcp.generated_artifacts) == 1
        artifact = sample_pipeline_context_with_mcp.generated_artifacts[0]
        # Fallback para template base tem confidence 0.85
        assert artifact.confidence_score == 0.85

    @pytest.mark.asyncio
    async def test_compose_hybrid_confidence_calculation(
        self,
        mock_mongodb_client,
        mock_llm_client,
        sample_pipeline_context_with_mcp
    ):
        """Deve calcular confidence hibrido corretamente."""
        from services.code_forge.src.services.code_composer import CodeComposer

        sample_pipeline_context_with_mcp.generation_method = 'HYBRID'
        mock_llm_client.generate_code.return_value = {
            'code': '# Enhanced code',
            'confidence_score': 0.9
        }

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=mock_llm_client,
            analyst_client=None,
            mcp_client=None
        )

        await composer.compose(sample_pipeline_context_with_mcp)

        artifact = sample_pipeline_context_with_mcp.generated_artifacts[0]
        # Hybrid confidence = (0.6 * 0.9) + (0.4 * 0.85) = 0.54 + 0.34 = 0.88
        assert 0.87 <= artifact.confidence_score <= 0.89


class TestCodeComposerHeuristicGeneration:
    """Testes de geracao HEURISTIC."""

    @pytest.mark.asyncio
    async def test_compose_heuristic_microservice(
        self,
        mock_mongodb_client,
        sample_pipeline_context
    ):
        """Deve gerar microservico via heuristica."""
        from services.code_forge.src.services.code_composer import CodeComposer

        sample_pipeline_context.generation_method = 'HEURISTIC'
        sample_pipeline_context.ticket.parameters['artifact_type'] = 'MICROSERVICE'

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

        await composer.compose(sample_pipeline_context)

        assert len(sample_pipeline_context.generated_artifacts) == 1
        artifact = sample_pipeline_context.generated_artifacts[0]
        assert artifact.confidence_score == 0.78

    @pytest.mark.asyncio
    async def test_compose_heuristic_library(
        self,
        mock_mongodb_client,
        sample_ticket_library
    ):
        """Deve gerar biblioteca via heuristica."""
        from services.code_forge.src.services.code_composer import CodeComposer
        from services.code_forge.src.models.pipeline_context import PipelineContext
        from services.code_forge.src.models.template import (
            Template, TemplateMetadata, TemplateType, TemplateLanguage
        )

        context = PipelineContext(
            pipeline_id=str(uuid.uuid4()),
            ticket=sample_ticket_library
        )
        context.generation_method = 'HEURISTIC'
        context.selected_template = Template(
            template_id='lib-python-v1',
            metadata=TemplateMetadata(
                name='Python Library',
                version='1.0.0',
                description='Template para biblioteca Python',
                author='Neural Hive Team',
                tags=['library', 'python'],
                language=TemplateLanguage.PYTHON,
                type=TemplateType.LIBRARY
            ),
            parameters=[],
            content_path='/app/templates/lib-python',
            examples={}
        )

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

        await composer.compose(context)

        assert len(context.generated_artifacts) == 1

    @pytest.mark.asyncio
    async def test_compose_heuristic_script(
        self,
        mock_mongodb_client,
        sample_ticket_script
    ):
        """Deve gerar script via heuristica."""
        from services.code_forge.src.services.code_composer import CodeComposer
        from services.code_forge.src.models.pipeline_context import PipelineContext
        from services.code_forge.src.models.template import (
            Template, TemplateMetadata, TemplateType, TemplateLanguage
        )

        context = PipelineContext(
            pipeline_id=str(uuid.uuid4()),
            ticket=sample_ticket_script
        )
        context.generation_method = 'HEURISTIC'
        context.selected_template = Template(
            template_id='script-python-v1',
            metadata=TemplateMetadata(
                name='Python Script',
                version='1.0.0',
                description='Template para script Python',
                author='Neural Hive Team',
                tags=['script', 'python'],
                language=TemplateLanguage.PYTHON,
                type=TemplateType.SCRIPT
            ),
            parameters=[],
            content_path='/app/templates/script-python',
            examples={}
        )

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

        await composer.compose(context)

        assert len(context.generated_artifacts) == 1


class TestCodeComposerTemplateGeneration:
    """Testes de geracao TEMPLATE."""

    @pytest.mark.asyncio
    async def test_compose_template_success(
        self,
        mock_mongodb_client,
        sample_pipeline_context
    ):
        """Deve gerar codigo via template com sucesso."""
        from services.code_forge.src.services.code_composer import CodeComposer

        sample_pipeline_context.generation_method = 'TEMPLATE'

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

        await composer.compose(sample_pipeline_context)

        assert len(sample_pipeline_context.generated_artifacts) == 1
        artifact = sample_pipeline_context.generated_artifacts[0]
        assert artifact.confidence_score == 0.85

    @pytest.mark.asyncio
    async def test_compose_default_to_template(
        self,
        mock_mongodb_client,
        sample_pipeline_context
    ):
        """Deve usar template como default quando generation_method nao definido."""
        from services.code_forge.src.services.code_composer import CodeComposer

        # Sem generation_method definido
        sample_pipeline_context.generation_method = None

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

        await composer.compose(sample_pipeline_context)

        assert len(sample_pipeline_context.generated_artifacts) == 1
        artifact = sample_pipeline_context.generated_artifacts[0]
        assert artifact.confidence_score == 0.85


class TestCodeComposerRAGContext:
    """Testes de construcao de contexto RAG."""

    @pytest.mark.asyncio
    async def test_build_rag_context_success(
        self,
        mock_mongodb_client,
        mock_analyst_client,
        sample_ticket
    ):
        """Deve construir RAG context com sucesso."""
        from services.code_forge.src.services.code_composer import CodeComposer

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=mock_analyst_client,
            mcp_client=None
        )

        rag_context = await composer._build_rag_context(sample_ticket)

        assert 'similar_templates' in rag_context
        assert 'architectural_patterns' in rag_context
        assert len(rag_context['similar_templates']) == 2
        assert len(rag_context['architectural_patterns']) == 3

    @pytest.mark.asyncio
    async def test_build_rag_context_without_analyst(
        self,
        mock_mongodb_client,
        sample_ticket
    ):
        """Deve retornar contexto vazio sem analyst client."""
        from services.code_forge.src.services.code_composer import CodeComposer

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

        rag_context = await composer._build_rag_context(sample_ticket)

        assert rag_context['similar_templates'] == []
        assert rag_context['architectural_patterns'] == []

    @pytest.mark.asyncio
    async def test_build_rag_context_embedding_failure(
        self,
        mock_mongodb_client,
        mock_analyst_client,
        sample_ticket
    ):
        """Deve continuar quando embedding falha."""
        from services.code_forge.src.services.code_composer import CodeComposer

        mock_analyst_client.get_embedding.return_value = None

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=mock_analyst_client,
            mcp_client=None
        )

        rag_context = await composer._build_rag_context(sample_ticket)

        assert rag_context['similar_templates'] == []
        mock_analyst_client.find_similar_templates.assert_not_called()

    @pytest.mark.asyncio
    async def test_build_rag_context_exception_handling(
        self,
        mock_mongodb_client,
        mock_analyst_client,
        sample_ticket
    ):
        """Deve tratar excecoes e retornar contexto vazio."""
        from services.code_forge.src.services.code_composer import CodeComposer

        mock_analyst_client.get_embedding.side_effect = Exception('Connection error')

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=mock_analyst_client,
            mcp_client=None
        )

        rag_context = await composer._build_rag_context(sample_ticket)

        assert rag_context['similar_templates'] == []
        assert rag_context['architectural_patterns'] == []


class TestCodeComposerLLMPrompt:
    """Testes de construcao de prompt LLM."""

    @pytest.mark.asyncio
    async def test_build_llm_prompt_with_rag(
        self,
        mock_mongodb_client,
        sample_ticket
    ):
        """Deve construir prompt com RAG context."""
        from services.code_forge.src.services.code_composer import CodeComposer

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

        rag_context = {
            'similar_templates': [
                {'text': 'Template example', 'similarity': 0.9}
            ],
            'architectural_patterns': ['Repository Pattern']
        }

        prompt = composer._build_llm_prompt(sample_ticket, rag_context)

        assert 'MICROSERVICE' in prompt
        assert 'python' in prompt.lower()
        assert 'Similar Templates' in prompt
        assert 'Architectural Patterns' in prompt

    @pytest.mark.asyncio
    async def test_build_llm_prompt_without_rag(
        self,
        mock_mongodb_client,
        sample_ticket
    ):
        """Deve construir prompt sem RAG context."""
        from services.code_forge.src.services.code_composer import CodeComposer

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

        rag_context = {
            'similar_templates': [],
            'architectural_patterns': []
        }

        prompt = composer._build_llm_prompt(sample_ticket, rag_context)

        assert 'MICROSERVICE' in prompt
        assert 'Similar Templates' not in prompt


class TestCodeComposerArtifactCreation:
    """Testes de criacao de artefatos."""

    @pytest.mark.asyncio
    async def test_artifact_has_correct_metadata(
        self,
        mock_mongodb_client,
        sample_pipeline_context_with_mcp
    ):
        """Deve criar artefato com metadata correta."""
        from services.code_forge.src.services.code_composer import CodeComposer
        from services.code_forge.src.models.artifact import ArtifactType

        sample_pipeline_context_with_mcp.generation_method = 'TEMPLATE'

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

        await composer.compose(sample_pipeline_context_with_mcp)

        artifact = sample_pipeline_context_with_mcp.generated_artifacts[0]

        assert artifact.ticket_id == sample_pipeline_context_with_mcp.ticket.ticket_id
        assert artifact.artifact_type == ArtifactType.CODE
        assert artifact.language == 'python'
        assert artifact.template_id == 'microservice-python-v1'
        assert artifact.content_hash is not None

    @pytest.mark.asyncio
    async def test_artifact_has_mcp_metadata(
        self,
        mock_mongodb_client,
        sample_pipeline_context_with_mcp
    ):
        """Deve incluir metadata MCP no artefato."""
        from services.code_forge.src.services.code_composer import CodeComposer

        sample_pipeline_context_with_mcp.generation_method = 'TEMPLATE'

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

        await composer.compose(sample_pipeline_context_with_mcp)

        artifact = sample_pipeline_context_with_mcp.generated_artifacts[0]

        assert 'mcp_selection_id' in artifact.metadata
        assert 'mcp_tools_used' in artifact.metadata

    @pytest.mark.asyncio
    async def test_artifact_saved_to_mongodb(
        self,
        mock_mongodb_client,
        sample_pipeline_context
    ):
        """Deve salvar artefato no MongoDB."""
        from services.code_forge.src.services.code_composer import CodeComposer

        sample_pipeline_context.generation_method = 'TEMPLATE'

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

        await composer.compose(sample_pipeline_context)

        mock_mongodb_client.save_artifact_content.assert_called_once()


class TestCodeComposerGenerationMethodValidation:
    """Testes de validacao de generation_method."""

    @pytest.mark.asyncio
    async def test_invalid_generation_method_fallback(
        self,
        mock_mongodb_client,
        sample_pipeline_context
    ):
        """Deve usar TEMPLATE para generation_method invalido."""
        from services.code_forge.src.services.code_composer import CodeComposer
        from services.code_forge.src.models.artifact import GenerationMethod

        sample_pipeline_context.generation_method = 'INVALID_METHOD'

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

        await composer.compose(sample_pipeline_context)

        artifact = sample_pipeline_context.generated_artifacts[0]
        assert artifact.generation_method == GenerationMethod.TEMPLATE

    @pytest.mark.asyncio
    async def test_llm_without_client_uses_template(
        self,
        mock_mongodb_client,
        sample_pipeline_context
    ):
        """Deve usar TEMPLATE quando LLM solicitado mas sem client."""
        from services.code_forge.src.services.code_composer import CodeComposer

        sample_pipeline_context.generation_method = 'LLM'

        composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,  # Sem LLM client
            analyst_client=None,
            mcp_client=None
        )

        await composer.compose(sample_pipeline_context)

        assert len(sample_pipeline_context.generated_artifacts) == 1
        artifact = sample_pipeline_context.generated_artifacts[0]
        assert artifact.confidence_score == 0.85  # Template confidence
