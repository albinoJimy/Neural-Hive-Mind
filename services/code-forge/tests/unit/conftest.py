"""
Configuracao pytest e fixtures para testes unitarios do Code Forge.

Este modulo fornece:
- Fixtures para configuracao
- Mocks para clientes externos
- Fixtures para dados de teste (tickets, contexts, templates)
- Fixtures para metricas Prometheus
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================
# Event Loop Configuration
# ============================================


@pytest.fixture(scope='session')
def event_loop():
    """Cria event loop para sessao de testes."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# ============================================
# Settings Fixtures
# ============================================


@pytest.fixture
def code_forge_settings():
    """Configuracoes do Code Forge para testes."""
    settings = MagicMock()
    settings.service_name = 'code-forge-test'
    settings.mongodb_uri = 'mongodb://localhost:27017'
    settings.mongodb_database = 'code_forge_test'
    settings.redis_url = 'redis://localhost:6379'
    settings.kafka_bootstrap_servers = 'localhost:9092'
    settings.mcp_tool_catalog_url = 'http://localhost:8080'
    settings.mcp_timeout_seconds = 5
    settings.sonarqube_url = 'http://localhost:9000'
    settings.sonarqube_token = 'test-token'
    settings.snyk_token = 'test-snyk-token'
    settings.trivy_enabled = True
    settings.llm_provider = 'openai'
    settings.openai_api_key = 'test-key'
    settings.anthropic_api_key = 'test-anthropic-key'
    settings.ollama_url = 'http://localhost:11434'
    settings.analyst_agents_url = 'http://localhost:8082'
    settings.s3_bucket = 'code-forge-test'
    settings.s3_region = 'us-east-1'
    return settings


# ============================================
# Metrics Fixtures
# ============================================


@pytest.fixture
def mock_metrics():
    """Mock para metricas Prometheus do Code Forge."""
    metrics = MagicMock()

    # MCP selection metrics
    metrics.mcp_selection_requests_total = MagicMock()
    metrics.mcp_selection_requests_total.labels.return_value.inc = MagicMock()
    metrics.mcp_selection_duration_seconds = MagicMock()
    metrics.mcp_selection_duration_seconds.observe = MagicMock()
    metrics.mcp_tools_selected_total = MagicMock()
    metrics.mcp_tools_selected_total.labels.return_value.inc = MagicMock()
    metrics.mcp_feedback_sent_total = MagicMock()
    metrics.mcp_feedback_sent_total.labels.return_value.inc = MagicMock()

    # Code generation metrics
    metrics.code_generation_total = MagicMock()
    metrics.code_generation_total.labels.return_value.inc = MagicMock()
    metrics.code_generation_duration_seconds = MagicMock()
    metrics.code_generation_duration_seconds.labels.return_value.observe = MagicMock()
    metrics.llm_api_calls_total = MagicMock()
    metrics.llm_api_calls_total.labels.return_value.inc = MagicMock()
    metrics.llm_tokens_consumed_total = MagicMock()
    metrics.llm_tokens_consumed_total.labels.return_value.inc = MagicMock()

    # Validation metrics
    metrics.validations_run_total = MagicMock()
    metrics.validations_run_total.labels.return_value.inc = MagicMock()
    metrics.validation_issues_found = MagicMock()
    metrics.validation_issues_found.labels.return_value.observe = MagicMock()
    metrics.quality_score = MagicMock()
    metrics.quality_score.observe = MagicMock()

    # Test metrics
    metrics.tests_run_total = MagicMock()
    metrics.tests_run_total.labels.return_value.inc = MagicMock()
    metrics.test_duration_seconds = MagicMock()
    metrics.test_duration_seconds.observe = MagicMock()

    # Packaging metrics
    metrics.artifacts_packaged_total = MagicMock()
    metrics.artifacts_packaged_total.labels.return_value.inc = MagicMock()
    metrics.sbom_generated_total = MagicMock()
    metrics.sbom_generated_total.labels.return_value.inc = MagicMock()

    # Pipeline metrics
    metrics.pipelines_total = MagicMock()
    metrics.pipelines_total.labels.return_value.inc = MagicMock()
    metrics.pipeline_duration_seconds = MagicMock()
    metrics.pipeline_duration_seconds.labels.return_value.observe = MagicMock()

    return metrics


# ============================================
# Client Mock Fixtures
# ============================================


@pytest.fixture
def mock_git_client():
    """Mock para GitClient."""
    client = AsyncMock()
    client.clone_templates_repo = AsyncMock(return_value='/tmp/templates')
    client.create_merge_request = AsyncMock(return_value='https://github.com/org/repo/pull/123')
    client.push_branch = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_redis_client():
    """Mock para RedisClient."""
    client = AsyncMock()
    client.get_cached_template = AsyncMock(return_value=None)
    client.cache_template = AsyncMock(return_value=True)
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_mongodb_client():
    """Mock para MongoDBClient."""
    client = AsyncMock()
    client.save_artifact_content = AsyncMock(return_value=True)
    client.get_artifact_content = AsyncMock(return_value='# Generated code')
    client.save_pipeline_result = AsyncMock(return_value=True)
    client.get_pipeline_result = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_mcp_client():
    """Mock para MCPToolCatalogClient."""
    client = AsyncMock()
    client.request_tool_selection = AsyncMock(return_value={
        'request_id': str(uuid.uuid4()),
        'selected_tools': [
            {
                'tool_id': 'tool-001',
                'tool_name': 'SonarQube',
                'category': 'VALIDATION',
                'fitness_score': 0.85
            },
            {
                'tool_id': 'tool-002',
                'tool_name': 'GitHub Copilot',
                'category': 'GENERATION',
                'fitness_score': 0.92
            }
        ],
        'total_fitness_score': 0.88,
        'selection_method': 'GENETIC_ALGORITHM'
    })
    client.send_tool_feedback = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_llm_client():
    """Mock para LLMClient."""
    client = AsyncMock()
    client.generate_code = AsyncMock(return_value={
        'code': '# Generated by LLM\ndef main():\n    pass',
        'confidence_score': 0.85,
        'tokens_used': 150,
        'model': 'gpt-4'
    })
    client.enhance_code = AsyncMock(return_value={
        'code': '# Enhanced code\ndef main():\n    print("Hello")',
        'confidence_score': 0.9
    })
    return client


@pytest.fixture
def mock_analyst_client():
    """Mock para AnalystAgentsClient."""
    client = AsyncMock()
    client.get_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3] * 512)
    client.find_similar_templates = AsyncMock(return_value=[
        {'text': 'Similar template 1', 'similarity': 0.92},
        {'text': 'Similar template 2', 'similarity': 0.85}
    ])
    client.get_architectural_patterns = AsyncMock(return_value=[
        'Repository Pattern',
        'Service Layer',
        'Dependency Injection'
    ])
    return client


@pytest.fixture
def mock_sonarqube_client():
    """Mock para SonarQubeClient."""
    from services.code_forge.src.models.artifact import (
        ValidationResult,
        ValidationType,
        ValidationStatus
    )

    client = AsyncMock()
    client.analyze_code = AsyncMock(return_value=ValidationResult(
        validation_type=ValidationType.SAST,
        tool_name='SonarQube',
        tool_version='10.0.0',
        status=ValidationStatus.PASSED,
        score=0.85,
        issues_count=3,
        critical_issues=0,
        high_issues=1,
        medium_issues=2,
        low_issues=0,
        executed_at=datetime.now(),
        duration_ms=5000
    ))
    return client


@pytest.fixture
def mock_snyk_client():
    """Mock para SnykClient."""
    from services.code_forge.src.models.artifact import (
        ValidationResult,
        ValidationType,
        ValidationStatus
    )

    client = AsyncMock()
    client.scan_dependencies = AsyncMock(return_value=ValidationResult(
        validation_type=ValidationType.SCA,
        tool_name='Snyk',
        tool_version='1.1200.0',
        status=ValidationStatus.PASSED,
        score=0.95,
        issues_count=1,
        critical_issues=0,
        high_issues=0,
        medium_issues=1,
        low_issues=0,
        executed_at=datetime.now(),
        duration_ms=3000
    ))
    return client


@pytest.fixture
def mock_trivy_client():
    """Mock para TrivyClient."""
    from services.code_forge.src.models.artifact import (
        ValidationResult,
        ValidationType,
        ValidationStatus
    )

    client = AsyncMock()
    client.scan_filesystem = AsyncMock(return_value=ValidationResult(
        validation_type=ValidationType.CONTAINER_SCAN,
        tool_name='Trivy',
        tool_version='0.50.0',
        status=ValidationStatus.PASSED,
        score=0.90,
        issues_count=2,
        critical_issues=0,
        high_issues=0,
        medium_issues=1,
        low_issues=1,
        executed_at=datetime.now(),
        duration_ms=2000
    ))
    return client


@pytest.fixture
def mock_sigstore_client():
    """Mock para SigstoreClient."""
    client = AsyncMock()
    client.generate_sbom = AsyncMock(return_value='s3://code-forge/sboms/artifact-123.json')
    client.sign_artifact = AsyncMock(return_value='signature-abc123')
    client.verify_signature = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_s3_client():
    """Mock para S3ArtifactClient."""
    client = AsyncMock()
    client.upload_sbom = AsyncMock(return_value='s3://code-forge/sboms/artifact-123.json')
    client.download_sbom = AsyncMock(return_value={'components': []})
    client.verify_sbom_integrity = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_artifact_registry_client():
    """Mock para ArtifactRegistryClient."""
    client = AsyncMock()
    client.register_sbom = AsyncMock(return_value='registry://sboms/artifact-123')
    client.get_sbom_reference = AsyncMock(return_value='registry://sboms/artifact-123')
    return client


# ============================================
# Data Fixtures - Tickets
# ============================================


@pytest.fixture
def sample_ticket():
    """Ticket de execucao sample."""
    ticket_id = str(uuid.uuid4())
    return MagicMock(
        ticket_id=ticket_id,
        plan_id=f'plan-{ticket_id[:8]}',
        intent_id=f'intent-{ticket_id[:8]}',
        decision_id=f'decision-{ticket_id[:8]}',
        correlation_id=str(uuid.uuid4()),
        parameters={
            'artifact_type': 'MICROSERVICE',
            'language': 'python',
            'service_name': 'test-service',
            'description': 'A test microservice for unit testing',
            'requirements': ['FastAPI', 'PostgreSQL', 'Redis'],
            'framework': 'fastapi',
            'patterns': ['repository', 'service_layer'],
            'tasks': ['task-1', 'task-2', 'task-3'],
            'project_key': 'test-project'
        },
        dependencies=[]
    )


@pytest.fixture
def sample_ticket_llm():
    """Ticket configurado para geracao LLM."""
    ticket_id = str(uuid.uuid4())
    return MagicMock(
        ticket_id=ticket_id,
        plan_id=f'plan-{ticket_id[:8]}',
        intent_id=f'intent-{ticket_id[:8]}',
        correlation_id=str(uuid.uuid4()),
        parameters={
            'artifact_type': 'MICROSERVICE',
            'language': 'python',
            'service_name': 'llm-service',
            'description': 'A service generated via LLM',
            'requirements': ['Authentication', 'Authorization', 'Logging'],
            'framework': 'fastapi',
            'max_lines': 500
        },
        dependencies=[]
    )


@pytest.fixture
def sample_ticket_library():
    """Ticket para geracao de biblioteca."""
    ticket_id = str(uuid.uuid4())
    return MagicMock(
        ticket_id=ticket_id,
        parameters={
            'artifact_type': 'LIBRARY',
            'language': 'python',
            'service_name': 'my-lib'
        },
        dependencies=[]
    )


@pytest.fixture
def sample_ticket_script():
    """Ticket para geracao de script."""
    ticket_id = str(uuid.uuid4())
    return MagicMock(
        ticket_id=ticket_id,
        parameters={
            'artifact_type': 'SCRIPT',
            'language': 'python',
            'service_name': 'my-script'
        },
        dependencies=[]
    )


# ============================================
# Data Fixtures - Pipeline Context
# ============================================


@pytest.fixture
def sample_pipeline_context(sample_ticket):
    """PipelineContext sample."""
    from services.code_forge.src.models.pipeline_context import PipelineContext
    from services.code_forge.src.models.template import (
        Template, TemplateMetadata, TemplateType, TemplateLanguage
    )

    context = PipelineContext(
        pipeline_id=str(uuid.uuid4()),
        ticket=sample_ticket
    )
    context.trace_id = str(uuid.uuid4())
    context.span_id = str(uuid.uuid4())
    context.metadata = {'risk_band': 'MEDIUM'}

    # Template sample
    template = Template(
        template_id='microservice-python-v1',
        metadata=TemplateMetadata(
            name='Python Microservice',
            version='1.0.0',
            description='Template base para microservico Python',
            author='Neural Hive Team',
            tags=['microservice', 'python', 'fastapi'],
            language=TemplateLanguage.PYTHON,
            type=TemplateType.MICROSERVICE
        ),
        parameters=[],
        content_path='/app/templates/microservice-python',
        examples={}
    )
    context.selected_template = template

    return context


@pytest.fixture
def sample_pipeline_context_with_mcp(sample_pipeline_context):
    """PipelineContext com selecao MCP."""
    sample_pipeline_context.mcp_selection_id = str(uuid.uuid4())
    sample_pipeline_context.selected_tools = [
        {
            'tool_id': 'tool-001',
            'tool_name': 'SonarQube',
            'category': 'VALIDATION',
            'fitness_score': 0.85
        },
        {
            'tool_id': 'tool-002',
            'tool_name': 'GitHub Copilot',
            'category': 'GENERATION',
            'fitness_score': 0.92
        }
    ]
    sample_pipeline_context.generation_method = 'LLM'
    return sample_pipeline_context


@pytest.fixture
def sample_pipeline_context_with_artifacts(sample_pipeline_context):
    """PipelineContext com artefatos gerados."""
    from services.code_forge.src.models.artifact import (
        CodeForgeArtifact, ArtifactType, GenerationMethod
    )

    artifact = CodeForgeArtifact(
        artifact_id=str(uuid.uuid4()),
        ticket_id=sample_pipeline_context.ticket.ticket_id,
        plan_id=sample_pipeline_context.ticket.plan_id,
        intent_id=sample_pipeline_context.ticket.intent_id,
        correlation_id=sample_pipeline_context.ticket.correlation_id,
        trace_id=sample_pipeline_context.trace_id,
        span_id=sample_pipeline_context.span_id,
        artifact_type=ArtifactType.CODE,
        language='python',
        template_id='microservice-python-v1',
        confidence_score=0.85,
        generation_method=GenerationMethod.TEMPLATE,
        content_uri='mongodb://artifacts/test-123',
        content_hash='abc123',
        created_at=datetime.now(),
        metadata={}
    )
    sample_pipeline_context.add_artifact(artifact)

    return sample_pipeline_context


@pytest.fixture
def sample_pipeline_context_with_validations(sample_pipeline_context_with_artifacts):
    """PipelineContext com validacoes."""
    from services.code_forge.src.models.artifact import (
        ValidationResult, ValidationType, ValidationStatus
    )

    validation = ValidationResult(
        validation_type=ValidationType.SAST,
        tool_name='SonarQube',
        tool_version='10.0.0',
        status=ValidationStatus.PASSED,
        score=0.85,
        issues_count=3,
        critical_issues=0,
        high_issues=1,
        medium_issues=2,
        low_issues=0,
        executed_at=datetime.now(),
        duration_ms=5000
    )
    sample_pipeline_context_with_artifacts.add_validation(validation)

    return sample_pipeline_context_with_artifacts


# ============================================
# Data Fixtures - Templates
# ============================================


@pytest.fixture
def sample_template():
    """Template sample."""
    from services.code_forge.src.models.template import (
        Template, TemplateMetadata, TemplateType, TemplateLanguage
    )

    return Template(
        template_id='microservice-python-v1',
        metadata=TemplateMetadata(
            name='Python Microservice',
            version='1.0.0',
            description='Template base para microservico Python',
            author='Neural Hive Team',
            tags=['microservice', 'python', 'fastapi'],
            language=TemplateLanguage.PYTHON,
            type=TemplateType.MICROSERVICE
        ),
        parameters=[],
        content_path='/app/templates/microservice-python',
        examples={}
    )


@pytest.fixture
def cached_template(sample_template):
    """Template cacheado no Redis."""
    return sample_template


# ============================================
# Data Fixtures - MCP Tools
# ============================================


@pytest.fixture
def sample_mcp_response():
    """Resposta MCP Tool Catalog sample."""
    return {
        'request_id': str(uuid.uuid4()),
        'selected_tools': [
            {
                'tool_id': 'tool-001',
                'tool_name': 'SonarQube',
                'category': 'VALIDATION',
                'fitness_score': 0.85
            },
            {
                'tool_id': 'tool-002',
                'tool_name': 'Cookiecutter',
                'category': 'GENERATION',
                'fitness_score': 0.80
            }
        ],
        'total_fitness_score': 0.82,
        'selection_method': 'GENETIC_ALGORITHM'
    }


@pytest.fixture
def sample_mcp_response_llm_tools():
    """Resposta MCP com ferramentas LLM."""
    return {
        'request_id': str(uuid.uuid4()),
        'selected_tools': [
            {
                'tool_id': 'tool-003',
                'tool_name': 'GitHub Copilot',
                'category': 'GENERATION',
                'fitness_score': 0.95
            }
        ],
        'total_fitness_score': 0.95,
        'selection_method': 'GENETIC_ALGORITHM'
    }


@pytest.fixture
def sample_mcp_response_hybrid_tools():
    """Resposta MCP com ferramentas hibridas (LLM + Template)."""
    return {
        'request_id': str(uuid.uuid4()),
        'selected_tools': [
            {
                'tool_id': 'tool-003',
                'tool_name': 'GitHub Copilot',
                'category': 'GENERATION',
                'fitness_score': 0.95
            },
            {
                'tool_id': 'tool-004',
                'tool_name': 'Cookiecutter',
                'category': 'GENERATION',
                'fitness_score': 0.80
            }
        ],
        'total_fitness_score': 0.87,
        'selection_method': 'GENETIC_ALGORITHM'
    }


# ============================================
# Validation Fixtures
# ============================================


@pytest.fixture
def sample_validation_result():
    """ValidationResult sample."""
    from services.code_forge.src.models.artifact import (
        ValidationResult, ValidationType, ValidationStatus
    )

    return ValidationResult(
        validation_type=ValidationType.SAST,
        tool_name='SonarQube',
        tool_version='10.0.0',
        status=ValidationStatus.PASSED,
        score=0.85,
        issues_count=3,
        critical_issues=0,
        high_issues=1,
        medium_issues=2,
        low_issues=0,
        executed_at=datetime.now(),
        duration_ms=5000
    )


@pytest.fixture
def sample_validation_result_failed():
    """ValidationResult com falha."""
    from services.code_forge.src.models.artifact import (
        ValidationResult, ValidationType, ValidationStatus
    )

    return ValidationResult(
        validation_type=ValidationType.SAST,
        tool_name='SonarQube',
        tool_version='10.0.0',
        status=ValidationStatus.FAILED,
        score=0.35,
        issues_count=15,
        critical_issues=3,
        high_issues=5,
        medium_issues=4,
        low_issues=3,
        executed_at=datetime.now(),
        duration_ms=8000
    )
