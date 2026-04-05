"""
Testes TDD para Code Forge MCP Tools.

TDD: Testes escritos ANTES da implementação.
Ferramentas:
- generate_artifact: Gerar artefatos de código/IaC
- validate_template: Validar templates de código
- optimize_generation: Otimizar geração com caching
- select_template: Selecionar templates baseado em contexto
- pipeline_execute: Executar pipelines de geração
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGenerateArtifactTool:
    """Testes da ferramenta generate_artifact."""

    @pytest.mark.asyncio
    async def test_generate_artifact_success(self):
        """Testa geração de artefato com sucesso."""
        from code_forge_mcp_server.tools.code_forge_tools import generate_artifact

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._invoke_llm_generation",
            new_callable=AsyncMock,
        ) as mock_llm:
            mock_llm.return_value = {
                "artifact_id": "artifact-123",
                "content": "def hello():\n    print('Hello World')",
                "language": "python",
                "lines": 2,
                "generated_at": datetime.now().isoformat(),
            }

            result = await generate_artifact(
                artifact_type="function",
                description="Create a hello world function",
                language="python",
            )

            assert result["language"] == "python"
            assert result["lines"] == 2
            assert "artifact_id" in result
            mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_artifact_invalid_language(self):
        """Testa erro para linguagem inválida."""
        from code_forge_mcp_server.tools.code_forge_tools import generate_artifact

        with pytest.raises(ValueError, match="Invalid language"):
            await generate_artifact(
                artifact_type="function", description="Test", language="brainfuck"
            )

    @pytest.mark.asyncio
    async def test_generate_artifact_all_valid_languages(self):
        """Testa todas as linguagens válidas."""
        from code_forge_mcp_server.tools.code_forge_tools import generate_artifact

        valid_languages = ["python", "javascript", "typescript", "go", "rust", "java", "yaml", "json"]

        # Testar que linguagens inválidas são rejeitadas e válidas aceites
        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._invoke_llm_generation",
            new_callable=AsyncMock,
            return_value={"artifact_id": "test", "content": "", "language": "python", "lines": 0},
        ):
            for lang in valid_languages:
                # Não deve lançar exceção para linguagens válidas
                result = await generate_artifact(
                    artifact_type="function", description="Test", language=lang
                )
                assert "artifact_id" in result

    @pytest.mark.asyncio
    async def test_generate_artifact_with_requirements(self):
        """Testa geração com requisitos específicos."""
        from code_forge_mcp_server.tools.code_forge_tools import generate_artifact

        requirements = ["async", "type hints", "error handling"]

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._invoke_llm_generation",
            new_callable=AsyncMock,
            return_value={
                "artifact_id": "test",
                "content": "async def func() -> None: pass",
                "language": "python",
                "lines": 1,
            },
        ) as mock_llm:
            await generate_artifact(
                artifact_type="function",
                description="Create function",
                language="python",
                requirements=requirements,
            )

            call_args = mock_llm.call_args
            assert "requirements" in str(call_args)

    @pytest.mark.asyncio
    async def test_generate_artifact_with_context(self):
        """Testa geração com contexto adicional."""
        from code_forge_mcp_server.tools.code_forge_tools import generate_artifact

        context = {
            "existing_code": "class Service:\n    pass",
            "design_pattern": "singleton",
        }

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._invoke_llm_generation",
            new_callable=AsyncMock,
            return_value={"artifact_id": "test", "content": "", "language": "python", "lines": 0},
        ):
            result = await generate_artifact(
                artifact_type="class",
                description="Extend Service",
                language="python",
                context=context,
            )

            assert "artifact_id" in result

    @pytest.mark.asyncio
    async def test_generate_artifact_empty_description(self):
        """Testa erro para descrição vazia."""
        from code_forge_mcp_server.tools.code_forge_tools import generate_artifact

        with pytest.raises(ValueError, match="Description is required"):
            await generate_artifact(artifact_type="function", description="", language="python")

    @pytest.mark.asyncio
    async def test_generate_artifact_iac_type(self):
        """Testa geração de artefato IaC (Terraform/Kubernetes)."""
        from code_forge_mcp_server.tools.code_forge_tools import generate_artifact

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._invoke_llm_generation",
            new_callable=AsyncMock,
            return_value={
                "artifact_id": "test",
                "content": 'resource "aws_s3_bucket" "example" {}',
                "language": "hcl",
                "lines": 1,
            },
        ):
            result = await generate_artifact(
                artifact_type="iac",
                description="S3 bucket",
                language="terraform",
            )

            assert result["language"] in ["hcl", "yaml"]

    @pytest.mark.asyncio
    async def test_generate_artifact_with_quality_check(self):
        """Testa geração com verificação de qualidade."""
        from code_forge_mcp_server.tools.code_forge_tools import generate_artifact

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._invoke_llm_generation",
            new_callable=AsyncMock,
            return_value={
                "artifact_id": "test",
                "content": "def func(): pass",
                "language": "python",
                "lines": 1,
                "quality_score": 0.95,
                "lint_errors": [],
            },
        ):
            result = await generate_artifact(
                artifact_type="function", description="Test", language="python", run_quality_check=True
            )

            assert "quality_score" in result
            assert result["quality_score"] >= 0.0


class TestValidateTemplateTool:
    """Testes da ferramenta validate_template."""

    @pytest.mark.asyncio
    async def test_validate_template_success(self):
        """Testa validação de template com sucesso."""
        from code_forge_mcp_server.tools.code_forge_tools import validate_template

        template = "Hello {{ name }}!"

        result = await validate_template(
            template=template, template_type="jinja2", variables={"name": "World"}
        )

        assert result["valid"] is True
        assert result["rendered"] == "Hello World!"
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_validate_template_invalid_type(self):
        """Testa erro para tipo de template inválido."""
        from code_forge_mcp_server.tools.code_forge_tools import validate_template

        with pytest.raises(ValueError, match="Invalid template type"):
            await validate_template(
                template="Test", template_type="mustache", variables={}
            )

    @pytest.mark.asyncio
    async def test_validate_template_all_valid_types(self):
        """Testa todos os tipos de template válidos."""
        from code_forge_mcp_server.tools.code_forge_tools import validate_template

        valid_types = ["jinja2", "fstring", "yaml", "json"]

        for template_type in valid_types:
            if template_type == "jinja2":
                template = "Hello {{ name }}"
            elif template_type == "fstring":
                template = "Hello {name}"
            elif template_type == "yaml":
                template = "name: {{ name }}"
            else:  # json
                template = '{"name": "{{ name }}"}'

            result = await validate_template(
                template=template, template_type=template_type, variables={"name": "Test"}
            )

            assert "valid" in result

    @pytest.mark.asyncio
    async def test_validate_template_syntax_error(self):
        """Testa detecção de erro de sintaxe."""
        from code_forge_mcp_server.tools.code_forge_tools import validate_template

        result = await validate_template(
            template="Hello {{ name }", template_type="jinja2", variables={}
        )

        assert result["valid"] is False
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_validate_template_missing_variable(self):
        """Testa detecção de variável em falta."""
        from code_forge_mcp_server.tools.code_forge_tools import validate_template

        result = await validate_template(
            template="Hello {{ name }} {{ email }}",
            template_type="jinja2",
            variables={"name": "Test"},
        )

        # Template é válido, mas com avisos
        assert "valid" in result
        assert "warnings" in result

    @pytest.mark.asyncio
    async def test_validate_template_with_schema(self):
        """Testa validação com schema JSON."""
        from code_forge_mcp_server.tools.code_forge_tools import validate_template

        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }

        # Usar template JSON para validação de schema
        result = await validate_template(
            template='{"name": "{{ name }}"}',
            template_type="json",
            variables={"name": "Test"},
            schema=schema,
        )

        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_template_yaml_structure(self):
        """Testa validação de estrutura YAML."""
        from code_forge_mcp_server.tools.code_forge_tools import validate_template

        template = """
        service:
          name: {{ name }}
          port: {{ port }}
        """

        result = await validate_template(
            template=template, template_type="yaml", variables={"name": "api", "port": 8080}
        )

        assert result["valid"] is True
        assert "yaml" in result.get("metadata", {})

    @pytest.mark.asyncio
    async def test_validate_template_empty_template(self):
        """Testa erro para template vazio."""
        from code_forge_mcp_server.tools.code_forge_tools import validate_template

        with pytest.raises(ValueError, match="Template is required"):
            await validate_template(template="", template_type="jinja2", variables={})


class TestOptimizeGenerationTool:
    """Testes da ferramenta optimize_generation."""

    @pytest.mark.asyncio
    async def test_optimize_generation_cache_hit(self):
        """Testa cache hit otimização."""
        from code_forge_mcp_server.tools.code_forge_tools import optimize_generation

        cache_key = "cache-test-123"

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._check_cache", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = {
                "hit": True,
                "artifact_id": "cached-123",
                "content": "cached content",
                "cached_at": datetime.now().isoformat(),
            }

            result = await optimize_generation(
                cache_key=cache_key, description="Test", language="python"
            )

            assert result["cached"] is True
            assert result["artifact_id"] == "cached-123"

    @pytest.mark.asyncio
    async def test_optimize_generation_cache_miss(self):
        """Testa cache miss com geração."""
        from code_forge_mcp_server.tools.code_forge_tools import optimize_generation

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._check_cache",
            new_callable=AsyncMock,
            return_value={"hit": False, "artifact_id": None},
        ):
            with patch(
                "code_forge_mcp_server.tools.code_forge_tools._generate_and_cache",
                new_callable=AsyncMock,
                return_value={
                    "artifact_id": "new-123",
                    "content": "new content",
                    "cached": False,
                },
            ):
                result = await optimize_generation(
                    cache_key="miss-key", description="Test", language="python"
                )

                assert result["cached"] is False

    @pytest.mark.asyncio
    async def test_optimize_generation_with_ttl(self):
        """Testa otimização com TTL customizado."""
        from code_forge_mcp_server.tools.code_forge_tools import optimize_generation

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._check_cache", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = {"hit": True, "artifact_id": "cached-123", "content": "test"}

            result = await optimize_generation(
                cache_key="ttl-key", description="Test", language="python", ttl_seconds=7200
            )

            assert result["cached"] is True

    @pytest.mark.asyncio
    async def test_optimize_generation_invalidation_strategy(self):
        """Testa estratégia de invalidação de cache."""
        from code_forge_mcp_server.tools.code_forge_tools import optimize_generation

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._invalidate_cache",
            new_callable=AsyncMock,
            return_value={"invalidated": True, "keys_affected": 5},
        ):
            result = await optimize_generation(
                cache_key="invalidate-key",
                description="Test",
                language="python",
                invalidate=True,
            )

            assert "invalidated" in result or "cached" in result

    @pytest.mark.asyncio
    async def test_optimize_generation_with_embeddings(self):
        """Testa otimização com embeddings semânticos."""
        from code_forge_mcp_server.tools.code_forge_tools import optimize_generation

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._check_cache",
            new_callable=AsyncMock,
            return_value={"hit": False, "artifact_id": None},
        ):
            with patch(
                "code_forge_mcp_server.tools.code_forge_tools._find_similar_cached",
                new_callable=AsyncMock,
                return_value={
                    "similar_artifacts": [
                        {"artifact_id": "sim-1", "similarity": 0.92},
                        {"artifact_id": "sim-2", "similarity": 0.85},
                    ]
                },
            ):
                with patch(
                    "code_forge_mcp_server.tools.code_forge_tools._generate_and_cache",
                    new_callable=AsyncMock,
                    return_value={"artifact_id": "new-123", "content": "new"},
                ):
                    result = await optimize_generation(
                        cache_key="embedding-key",
                        description="Create REST API",
                        language="python",
                        use_semantic_search=True,
                    )

                    assert "similar_artifacts" in result
                    assert len(result["similar_artifacts"]) == 2

    @pytest.mark.asyncio
    async def test_optimize_generation_with_compression(self):
        """Testa otimização com compressão de cache."""
        from code_forge_mcp_server.tools.code_forge_tools import optimize_generation

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._check_cache", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = {
                "hit": True,
                "artifact_id": "compressed-123",
                "content": "compressed data",
                "compressed": True,
                "original_size": 1024,
                "compressed_size": 256,
            }

            result = await optimize_generation(
                cache_key="compress-key", description="Test", language="python", compress=True
            )

            assert result["cached"] is True

    @pytest.mark.asyncio
    async def test_optimize_generation_cache_stats(self):
        """Testa estatísticas de cache."""
        from code_forge_mcp_server.tools.code_forge_tools import optimize_generation

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._get_cache_stats",
            new_callable=AsyncMock,
            return_value={
                "hit_rate": 0.75,
                "total_entries": 150,
                "size_mb": 45.2,
            },
        ):
            result = await optimize_generation(
                cache_key="stats-key", description="Test", language="python", include_stats=True
            )

            assert "cache_stats" in result


class TestSelectTemplateTool:
    """Testes da ferramenta select_template."""

    @pytest.mark.asyncio
    async def test_select_template_by_language(self):
        """Testa seleção de template por linguagem."""
        from code_forge_mcp_server.tools.code_forge_tools import select_template

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._query_template_store",
            new_callable=AsyncMock,
        ) as mock_query:
            mock_query.return_value = {
                "templates": [
                    {
                        "template_id": "tpl-1",
                        "name": "fastapi-service",
                        "language": "python",
                        "category": "web-service",
                    }
                ],
                "total": 1,
            }

            result = await select_template(language="python", category="web-service")

            assert result["total"] == 1
            assert result["templates"][0]["language"] == "python"

    @pytest.mark.asyncio
    async def test_select_template_by_pattern(self):
        """Testa seleção de template por padrão."""
        from code_forge_mcp_server.tools.code_forge_tools import select_template

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._query_template_store",
            new_callable=AsyncMock,
            return_value={
                "templates": [
                    {
                        "template_id": "tpl-2",
                        "name": "singleton-class",
                        "pattern": "singleton",
                        "language": "python",
                    }
                ],
                "total": 1,
            },
        ):
            result = await select_template(
                language="python", design_pattern="singleton"
            )

            assert result["templates"][0]["pattern"] == "singleton"

    @pytest.mark.asyncio
    async def test_select_template_all_categories(self):
        """Testa todas as categorias válidas."""
        from code_forge_mcp_server.tools.code_forge_tools import select_template

        valid_categories = [
            "web-service",
            "cli",
            "library",
            "microservice",
            "lambda",
            "batch-job",
            "data-pipeline",
        ]

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._query_template_store",
            new_callable=AsyncMock,
            return_value={"templates": [], "total": 0},
        ):
            for category in valid_categories:
                result = await select_template(language="python", category=category)
                assert "templates" in result

    @pytest.mark.asyncio
    async def test_select_template_with_tags(self):
        """Testa seleção com tags."""
        from code_forge_mcp_server.tools.code_forge_tools import select_template

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._query_template_store",
            new_callable=AsyncMock,
            return_value={
                "templates": [
                    {
                        "template_id": "tpl-3",
                        "name": "auth-middleware",
                        "tags": ["auth", "jwt", "middleware"],
                    }
                ],
                "total": 1,
            },
        ):
            result = await select_template(language="python", tags=["auth", "jwt"])

            assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_select_template_with_complexity_filter(self):
        """Testa filtro de complexidade."""
        from code_forge_mcp_server.tools.code_forge_tools import select_template

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._query_template_store",
            new_callable=AsyncMock,
            return_value={
                "templates": [
                    {"template_id": "tpl-4", "name": "simple-func", "complexity": "basic"},
                ],
                "total": 1,
                "complexity": "basic",
            },
        ):
            result = await select_template(language="python", complexity="basic")

            # Verificar que o parâmetro foi passado corretamente
            assert result.get("complexity") == "basic" or all(
                tpl.get("complexity") == "basic" for tpl in result.get("templates", [])
            )

    @pytest.mark.asyncio
    async def test_select_template_empty_results(self):
        """Testa resultado vazio."""
        from code_forge_mcp_server.tools.code_forge_tools import select_template

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._query_template_store",
            new_callable=AsyncMock,
            return_value={"templates": [], "total": 0},
        ):
            result = await select_template(language="cobol", category="web-service")

            assert result["total"] == 0
            assert result["templates"] == []

    @pytest.mark.asyncio
    async def test_select_template_with_versioning(self):
        """Testa seleção com versionamento."""
        from code_forge_mcp_server.tools.code_forge_tools import select_template

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._query_template_store",
            new_callable=AsyncMock,
            return_value={
                "templates": [
                    {
                        "template_id": "tpl-6",
                        "name": "fastapi-service",
                        "version": "2.0.0",
                        "deprecated": False,
                    }
                ],
                "total": 1,
            },
        ):
            result = await select_template(
                language="python", template_name="fastapi-service", version="2.0.0"
            )

            assert result["templates"][0]["version"] == "2.0.0"

    @pytest.mark.asyncio
    async def test_select_template_recommendation(self):
        """Testa recomendação baseada em contexto."""
        from code_forge_mcp_server.tools.code_forge_tools import select_template

        context = {
            "use_case": "api",
            "framework": "fastapi",
            "requirements": ["async", "docker"],
        }

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._recommend_template",
            new_callable=AsyncMock,
            return_value={
                "recommended": {
                    "template_id": "tpl-rec-1",
                    "name": "fastapi-docker",
                    "score": 0.95,
                }
            },
        ):
            result = await select_template(language="python", context=context)

            assert "recommended" in result


class TestPipelineExecuteTool:
    """Testes da ferramenta pipeline_execute."""

    @pytest.mark.asyncio
    async def test_pipeline_execute_single_stage(self):
        """Testa execução de pipeline com estágio único."""
        from code_forge_mcp_server.tools.code_forge_tools import pipeline_execute

        stages = [{"name": "generate", "type": "generate", "params": {"description": "Test"}}]

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._execute_pipeline_stages",
            new_callable=AsyncMock,
        ) as mock_exec:
            mock_exec.return_value = {
                "pipeline_id": "pipe-1",
                "stages_completed": 1,
                "artifacts": [{"stage": "generate", "artifact_id": "art-1"}],
                "status": "completed",
            }

            result = await pipeline_execute(stages=stages)

            assert result["status"] == "completed"
            assert result["stages_completed"] == 1

    @pytest.mark.asyncio
    async def test_pipeline_execute_multiple_stages(self):
        """Testa execução de pipeline com múltiplos estágios."""
        from code_forge_mcp_server.tools.code_forge_tools import pipeline_execute

        stages = [
            {"name": "generate", "type": "generate", "params": {"description": "API service"}},
            {"name": "validate", "type": "validate", "params": {"run_lint": True}},
            {"name": "test", "type": "test", "params": {"coverage": 80}},
        ]

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._execute_pipeline_stages",
            new_callable=AsyncMock,
            return_value={
                "pipeline_id": "pipe-2",
                "stages_completed": 3,
                "artifacts": [
                    {"stage": "generate", "artifact_id": "art-1"},
                    {"stage": "validate", "artifact_id": "art-2"},
                    {"stage": "test", "artifact_id": "art-3"},
                ],
                "status": "completed",
            },
        ):
            result = await pipeline_execute(stages=stages)

            assert result["stages_completed"] == 3
            assert len(result["artifacts"]) == 3

    @pytest.mark.asyncio
    async def test_pipeline_execute_with_failure(self):
        """Testa pipeline com falha em estágio."""
        from code_forge_mcp_server.tools.code_forge_tools import pipeline_execute

        stages = [
            {"name": "generate", "type": "generate", "params": {}},
            {"name": "broken", "type": "invalid", "params": {}},
        ]

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._execute_pipeline_stages",
            new_callable=AsyncMock,
            return_value={
                "pipeline_id": "pipe-3",
                "stages_completed": 1,
                "stages_total": 2,
                "failed_at": "broken",
                "error": "Invalid stage type",
                "status": "failed",
            },
        ):
            result = await pipeline_execute(stages=stages)

            assert result["status"] == "failed"
            assert result["failed_at"] == "broken"

    @pytest.mark.asyncio
    async def test_pipeline_execute_with_dependencies(self):
        """Testa pipeline com dependências entre estágios."""
        from code_forge_mcp_server.tools.code_forge_tools import pipeline_execute

        stages = [
            {"name": "base", "type": "generate", "params": {}, "depends_on": []},
            {"name": "extend", "type": "generate", "params": {}, "depends_on": ["base"]},
            {"name": "test", "type": "test", "params": {}, "depends_on": ["extend"]},
        ]

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._execute_pipeline_stages",
            new_callable=AsyncMock,
            return_value={
                "pipeline_id": "pipe-4",
                "stages_completed": 3,
                "execution_order": ["base", "extend", "test"],
                "status": "completed",
            },
        ):
            result = await pipeline_execute(stages=stages)

            assert "execution_order" in result

    @pytest.mark.asyncio
    async def test_pipeline_execute_parallel_stages(self):
        """Testa execução paralela de estágios independentes."""
        from code_forge_mcp_server.tools.code_forge_tools import pipeline_execute

        stages = [
            {"name": "gen1", "type": "generate", "params": {}},
            {"name": "gen2", "type": "generate", "params": {}},
            {"name": "merge", "type": "merge", "params": {}, "depends_on": ["gen1", "gen2"]},
        ]

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._execute_pipeline_stages",
            new_callable=AsyncMock,
            return_value={
                "pipeline_id": "pipe-5",
                "stages_completed": 3,
                "parallel_executed": ["gen1", "gen2"],
                "status": "completed",
            },
        ):
            result = await pipeline_execute(stages=stages, parallel=True)

            assert "parallel_executed" in result

    @pytest.mark.asyncio
    async def test_pipeline_execute_empty_stages(self):
        """Testa erro para lista de estágios vazia."""
        from code_forge_mcp_server.tools.code_forge_tools import pipeline_execute

        with pytest.raises(ValueError, match="At least one stage"):
            await pipeline_execute(stages=[])

    @pytest.mark.asyncio
    async def test_pipeline_execute_with_artifact_passing(self):
        """Testa passagem de artefatos entre estágios."""
        from code_forge_mcp_server.tools.code_forge_tools import pipeline_execute

        stages = [
            {"name": "gen", "type": "generate", "params": {"output": "base.py"}},
            {"name": "enhance", "type": "transform", "params": {"input": "base.py"}},
        ]

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._execute_pipeline_stages",
            new_callable=AsyncMock,
            return_value={
                "pipeline_id": "pipe-6",
                "stages_completed": 2,
                "artifacts": [
                    {"stage": "gen", "artifact_id": "art-1", "outputs": ["base.py"]},
                    {
                        "stage": "enhance",
                        "artifact_id": "art-2",
                        "inputs": ["base.py"],
                        "outputs": ["enhanced.py"],
                    },
                ],
                "status": "completed",
            },
        ):
            result = await pipeline_execute(stages=stages)

            assert "outputs" in result["artifacts"][0]
            assert "inputs" in result["artifacts"][1]

    @pytest.mark.asyncio
    async def test_pipeline_execute_with_timeout(self):
        """Testa pipeline com timeout."""
        from code_forge_mcp_server.tools.code_forge_tools import pipeline_execute

        stages = [{"name": "long", "type": "generate", "params": {}}]

        with patch(
            "code_forge_mcp_server.tools.code_forge_tools._execute_pipeline_stages",
            new_callable=AsyncMock,
            return_value={
                "pipeline_id": "pipe-7",
                "stages_completed": 0,
                "timeout_seconds": 60,
                "timed_out": True,
                "status": "timeout",
            },
        ):
            result = await pipeline_execute(stages=stages, timeout_seconds=60)

            assert result["status"] == "timeout"


class TestHelperFunctions:
    """Testes das funções auxiliares."""

    @pytest.mark.asyncio
    async def test_invoke_llm_generation_success(self):
        """Testa invocação do LLM para geração."""
        from code_forge_mcp_server.tools.code_forge_tools import _invoke_llm_generation

        # Patch no settings para ter API key
        with patch("code_forge_mcp_server.tools.code_forge_tools.settings") as mock_settings:
            mock_settings.anthropic_api_key = "test-key"

            with patch("anthropic.Anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_anthropic.return_value = mock_client

                # Criar response mock
                mock_response = MagicMock()
                mock_response.content = [MagicMock(text="def hello(): pass")]
                mock_response.usage = MagicMock(input_tokens=10, output_tokens=20)

                mock_client.messages.create = MagicMock(return_value=mock_response)

                result = await _invoke_llm_generation(
                    artifact_type="function",
                    description="Create hello function",
                    language="python",
                    requirements=[],
                    context={},
                    run_quality_check=False,
                )

                assert "content" in result

    @pytest.mark.asyncio
    async def test_check_cache_success(self):
        """Testa verificação de cache."""
        from code_forge_mcp_server.tools.code_forge_tools import _check_cache

        result = await _check_cache(cache_key="test-key")

        assert "hit" in result

    @pytest.mark.asyncio
    async def test_query_template_store_success(self):
        """Testa consulta ao template store."""
        from code_forge_mcp_server.tools.code_forge_tools import _query_template_store

        result = await _query_template_store(
            language="python", category="web-service", tags=[]
        )

        assert "templates" in result
        assert "total" in result


class TestCodeForgeMCPServerIntegration:
    """Testes de integração do Code Forge MCP Server."""

    def test_tools_have_metadata(self):
        """Testa que ferramentas têm metadata descritiva."""
        from code_forge_mcp_server.tools.code_forge_tools import (
            generate_artifact,
            optimize_generation,
            pipeline_execute,
            select_template,
            validate_template,
        )

        assert generate_artifact.__doc__
        assert validate_template.__doc__
        assert optimize_generation.__doc__
        assert select_template.__doc__
        assert pipeline_execute.__doc__

    def test_register_code_forge_tools_function_exists(self):
        """Testa que função de registro existe."""
        from code_forge_mcp_server.tools.code_forge_tools import register_code_forge_tools

        assert register_code_forge_tools is not None
        assert callable(register_code_forge_tools)
